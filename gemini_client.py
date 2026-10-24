import json
import logging
import os
import re
import time

from google import genai
from google.genai import types


MODELS = (
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.7-flash",
    "gemini-3.8-flash",
)
RETRIES_PER_MODEL = 2
MAX_ATTEMPTS_PER_TASK = len(MODELS) * RETRIES_PER_MODEL
INITIAL_DELAY = 1
MAX_RATE_LIMIT_WAIT_SECONDS = 15
logger = logging.getLogger("resume_agent.gemini")

client = genai.Client(
    http_options=types.HttpOptions(
        retry_options=types.HttpRetryOptions(attempts=1)
    )
)


class GeminiGenerationError(RuntimeError):
    def __init__(self, stage, events):
        self.stage = stage
        self.events = tuple(events)
        classifications = tuple(dict.fromkeys(
            event["error_classification"] for event in events
        ))
        self.classifications = classifications
        if "authentication" in classifications:
            message = "Gemini authentication failed; verify GEMINI_API_KEY or GOOGLE_API_KEY and project access."
        elif "invalid_request" in classifications:
            message = "Gemini rejected the request; review the request configuration."
        elif "daily_quota" in classifications:
            message = "Gemini daily quota was exhausted for the configured model attempts."
        else:
            message = "All eligible configured Gemini attempts failed or returned invalid output."
        super().__init__(f"{message} Stage: {stage}.")


def redact_sensitive_text(value):
    text = str(value)
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        secret = os.environ.get(name)
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text


def parse_json_response(response_text):
    """Parse a JSON object from plain or fenced model output."""
    text = str(response_text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.IGNORECASE | re.DOTALL)
    candidates = [fenced.group(1).strip()] if fenced else []
    candidates.append(text)
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            start, end = candidate.find("{"), candidate.rfind("}")
            if start < 0 or end <= start:
                continue
            try:
                value = json.loads(candidate[start:end + 1])
            except json.JSONDecodeError:
                continue
        if isinstance(value, dict):
            return value
    raise ValueError("Gemini response did not contain a valid JSON object.")


def _error_code(error):
    for candidate in (getattr(error, "code", None), getattr(error, "status_code", None)):
        try:
            return int(candidate)
        except (TypeError, ValueError):
            continue
    match = re.search(r"\b(?:http|error code:?)[\s:]+(\d{3})\b", str(error), re.I)
    return int(match.group(1)) if match else None


def _error_text(error):
    values = (getattr(error, "message", None), getattr(error, "details", None), error)
    return redact_sensitive_text(" ".join(str(value) for value in values if value)).lower()


def classify_error(error):
    code = _error_code(error)
    text = _error_text(error)
    if code in (401, 403) or any(
        term in text for term in ("unauthorized", "invalid api key", "authentication", "permission denied")
    ):
        return "authentication"
    if any(term in text for term in (
        "requests per day", "per day on free tier", "daily quota",
        "quota exceeded for today", "daily limit",
    )):
        return "daily_quota"
    if code == 404 or any(term in text for term in (
        "model not found", "model is not available", "not found for api version",
    )):
        return "model_unavailable"
    if code in (400, 422) or any(term in text for term in (
        "invalid argument", "invalid request", "unsupported parameter",
    )):
        return "invalid_request"
    if code == 429 or any(term in text for term in (
        "rate limit", "too many requests", "resource exhausted",
    )):
        return "short_rate_limit"
    if code in (408, 500, 502, 503, 504):
        return "transient_server"
    error_name = type(error).__name__.lower()
    if isinstance(error, (TimeoutError, ConnectionError, OSError)) or any(
        term in error_name for term in ("timeout", "connecterror", "networkerror")
    ):
        return "transient_network"
    return "nonrecoverable"


def _retry_after_seconds(error):
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", {}) or {}
    try:
        return max(0.0, float(headers.get("Retry-After")))
    except (TypeError, ValueError):
        pass
    text = _error_text(error)
    match = re.search(r"retry in\s+((?:\d+h)?(?:\d+m)?(?:\d+(?:\.\d+)?s)?)", text)
    if not match:
        return None
    duration = match.group(1)
    hours = re.search(r"(\d+)h", duration)
    minutes = re.search(r"(\d+)m", duration)
    seconds = re.search(r"(\d+(?:\.\d+)?)s", duration)
    return (
        (int(hours.group(1)) * 3600 if hours else 0)
        + (int(minutes.group(1)) * 60 if minutes else 0)
        + (float(seconds.group(1)) if seconds else 0)
    )


def _record_attempt(stage, model, attempt, task_attempt, outcome, classification, events, event_sink):
    event = {
        "stage": stage,
        "model": model,
        "attempt": attempt,
        "task_attempt": task_attempt,
        "outcome": outcome,
        "error_classification": classification,
    }
    events.append(event)
    if event_sink is not None:
        event_sink.append(dict(event))
    logger.info(
        "gemini_attempt stage=%s model=%s attempt=%d task_attempt=%d outcome=%s error_classification=%s",
        stage, model, attempt, task_attempt, outcome, classification,
    )


def _valid_response(response_text, validator):
    if not isinstance(response_text, str) or not response_text.strip():
        return False
    if validator is None:
        return True
    try:
        result = validator(response_text)
    except (ValueError, TypeError, json.JSONDecodeError):
        return False
    return bool(result[0]) if isinstance(result, tuple) else result is not False


def generate_with_fallback(
    prompt,
    models=None,
    retries_per_model=RETRIES_PER_MODEL,
    *,
    stage="generation",
    response_validator=None,
    max_attempts_per_task=MAX_ATTEMPTS_PER_TASK,
    event_sink=None,
):
    """Attempt configured models sequentially and stop at the first valid response."""
    model_chain = tuple(dict.fromkeys(MODELS if models is None else models))
    if not model_chain:
        raise ValueError("At least one Gemini model must be configured.")
    if retries_per_model < 1 or max_attempts_per_task < 1:
        raise ValueError("Gemini attempt limits must be positive integers.")

    events = []
    task_attempt = 0
    for model in model_chain:
        active_prompt = prompt
        for model_attempt in range(1, retries_per_model + 1):
            if task_attempt >= max_attempts_per_task:
                break
            task_attempt += 1
            try:
                interaction = client.interactions.create(
                    model=model,
                    input=active_prompt,
                    generation_config={"thinking_level": "low"},
                )
                response_text = getattr(interaction, "output_text", None)
                if _valid_response(response_text, response_validator):
                    _record_attempt(stage, model, model_attempt, task_attempt, "success", "none", events, event_sink)
                    return response_text
                _record_attempt(stage, model, model_attempt, task_attempt, "invalid_output", "invalid_output", events, event_sink)
                if model_attempt < retries_per_model:
                    active_prompt = (
                        prompt + "\n\nYour previous response did not meet the required "
                        "output structure. Return a complete valid response only."
                    )
                    continue
                break
            except Exception as error:
                classification = classify_error(error)
                _record_attempt(stage, model, model_attempt, task_attempt, "failure", classification, events, event_sink)
                if classification in ("authentication", "invalid_request", "nonrecoverable"):
                    raise GeminiGenerationError(stage, events) from None
                if classification in ("model_unavailable", "daily_quota"):
                    break
                if classification == "short_rate_limit":
                    delay = _retry_after_seconds(error)
                    if delay is None or delay > MAX_RATE_LIMIT_WAIT_SECONDS:
                        break
                    if model_attempt < retries_per_model:
                        time.sleep(delay)
                        continue
                    break
                if classification in ("transient_server", "transient_network"):
                    if model_attempt < retries_per_model:
                        time.sleep(INITIAL_DELAY * (2 ** (model_attempt - 1)))
                        continue
                    break
                break
        if task_attempt >= max_attempts_per_task:
            break
    raise GeminiGenerationError(stage, events) from None