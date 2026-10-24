import json
import logging
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from google.genai.errors import APIError

import gemini_client


def api_error(code, message):
    status = {401: "UNAUTHENTICATED", 400: "INVALID_ARGUMENT", 429: "RESOURCE_EXHAUSTED", 503: "UNAVAILABLE"}.get(code, "ERROR")
    return APIError(code, {"error": {"message": message, "status": status}})


class SequenceInteractions:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.active = 0
        self.max_active = 0

    def create(self, model, **kwargs):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.calls.append((model, kwargs["input"]))
        try:
            response = self.responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return SimpleNamespace(output_text=response)
        finally:
            self.active -= 1


class GeminiFallbackTests(unittest.TestCase):
    def setUp(self):
        self.sleep = patch("gemini_client.time.sleep").start()
        self.addCleanup(patch.stopall)

    def install(self, responses):
        interactions = SequenceInteractions(responses)
        patcher = patch.object(gemini_client, "client", SimpleNamespace(interactions=interactions))
        patcher.start()
        self.addCleanup(patcher.stop)
        return interactions

    def test_default_order_prioritizes_reported_headroom_and_excludes_unverified_model(self):
        self.assertEqual(gemini_client.MODELS[:2], (
            "gemini-3.1-flash-lite", "gemini-3.5-flash-lite",
        ))
        self.assertEqual(gemini_client.MODELS[-1], "gemini-3.8-flash")
        self.assertNotIn("gemini-3.5-flash", gemini_client.MODELS)
        self.assertEqual(gemini_client.MAX_ATTEMPTS_PER_TASK, 10)

    def test_primary_success_calls_one_model_and_stops(self):
        interactions = self.install(["valid"])
        events = []
        result = gemini_client.generate_with_fallback(
            "prompt", models=("primary", "secondary"), event_sink=events
        )
        self.assertEqual(result, "valid")
        self.assertEqual([call[0] for call in interactions.calls], ["primary"])
        self.assertEqual(interactions.max_active, 1)
        self.assertEqual(events[0]["outcome"], "success")

    def test_primary_failure_falls_back_sequentially(self):
        interactions = self.install([api_error(404, "model is not available"), "fallback result"])
        result = gemini_client.generate_with_fallback(
            "prompt", models=("primary", "secondary"), retries_per_model=2
        )
        self.assertEqual(result, "fallback result")
        self.assertEqual([call[0] for call in interactions.calls], ["primary", "secondary"])
        self.assertEqual(interactions.max_active, 1)

    def test_primary_transient_retry_success_does_not_call_secondary(self):
        interactions = self.install([api_error(503, "service unavailable"), "valid"])
        result = gemini_client.generate_with_fallback(
            "prompt", models=("primary", "secondary"), retries_per_model=2
        )
        self.assertEqual(result, "valid")
        self.assertEqual([call[0] for call in interactions.calls], ["primary", "primary"])

    def test_daily_quota_skips_model_without_retry(self):
        interactions = self.install([
            api_error(429, "Rate limit exceeded: 20 requests per day on Free Tier"),
            "fallback result",
        ])
        events = []
        result = gemini_client.generate_with_fallback(
            "prompt", models=("quota-model", "eligible-model"),
            retries_per_model=2, event_sink=events,
        )
        self.assertEqual(result, "fallback result")
        self.assertEqual([call[0] for call in interactions.calls], ["quota-model", "eligible-model"])
        self.assertEqual(events[0]["error_classification"], "daily_quota")

    def test_wrapped_daily_quota_error_from_actual_log_format_skips_retry(self):
        wrapped_error = RuntimeError(
            "Error code: 429 - {'error': {'message': 'Rate limit exceeded for model "
            "primary (limit: 20 requests per day on Free Tier).'}}"
        )
        interactions = self.install([wrapped_error, "fallback result"])
        events = []
        result = gemini_client.generate_with_fallback(
            "prompt", models=("primary", "secondary"),
            retries_per_model=2, event_sink=events,
        )
        self.assertEqual(result, "fallback result")
        self.assertEqual([call[0] for call in interactions.calls], ["primary", "secondary"])
        self.assertEqual(events[0]["error_classification"], "daily_quota")

    def test_short_rate_limit_honors_small_retry_delay(self):
        interactions = self.install([
            api_error(429, "Rate limit exceeded; retry in 2s"), "valid",
        ])
        result = gemini_client.generate_with_fallback(
            "prompt", models=("primary", "secondary"), retries_per_model=2
        )
        self.assertEqual(result, "valid")
        self.assertEqual([call[0] for call in interactions.calls], ["primary", "primary"])
        self.sleep.assert_called_once_with(2.0)

    def test_all_models_stop_at_configured_task_ceiling(self):
        interactions = self.install([api_error(503, "unavailable") for _ in range(3)])
        events = []
        with self.assertRaises(gemini_client.GeminiGenerationError):
            gemini_client.generate_with_fallback(
                "prompt", models=("one", "two", "three"), retries_per_model=2,
                max_attempts_per_task=3, event_sink=events,
            )
        self.assertEqual(len(interactions.calls), 3)
        self.assertEqual([event["task_attempt"] for event in events], [1, 2, 3])

    def test_authentication_error_stops_without_model_cycling(self):
        interactions = self.install([api_error(401, "invalid API key")])
        with self.assertRaises(gemini_client.GeminiGenerationError) as caught:
            gemini_client.generate_with_fallback(
                "prompt", models=("one", "two", "three"), retries_per_model=2
            )
        self.assertEqual(len(interactions.calls), 1)
        self.assertIn("authentication", caught.exception.classifications)

    def test_malformed_json_has_one_recovery_then_falls_back(self):
        interactions = self.install(["not json", "still invalid", '{"ok":true}'])
        validator = lambda text: gemini_client.parse_json_response(text).get("ok") is True
        result = gemini_client.generate_with_fallback(
            "prompt", models=("primary", "secondary"), retries_per_model=2,
            response_validator=validator,
        )
        self.assertEqual(result, '{"ok":true}')
        self.assertEqual([call[0] for call in interactions.calls], ["primary", "primary", "secondary"])
        self.assertIn("previous response", interactions.calls[1][1])

    def test_nonrecoverable_invalid_request_stops_immediately(self):
        interactions = self.install([api_error(400, "invalid argument")])
        with self.assertRaises(gemini_client.GeminiGenerationError) as caught:
            gemini_client.generate_with_fallback("prompt", models=("one", "two"))
        self.assertEqual(len(interactions.calls), 1)
        self.assertIn("invalid_request", caught.exception.classifications)

    def test_attempt_log_has_safe_stage_model_and_classification(self):
        interactions = self.install([api_error(503, "unavailable"), "valid"])
        events = []
        with self.assertLogs("resume_agent.gemini", level=logging.INFO) as captured:
            gemini_client.generate_with_fallback(
                "prompt", models=("primary",), retries_per_model=2,
                stage="jd_analysis", event_sink=events,
            )
        self.assertEqual(len(interactions.calls), 2)
        self.assertEqual(events[0]["stage"], "jd_analysis")
        self.assertEqual(events[0]["error_classification"], "transient_server")
        self.assertIn("model=primary", captured.output[0])
        self.assertNotIn(os.environ.get("GEMINI_API_KEY", "__no_key__"), captured.output[0])


if __name__ == "__main__":
    unittest.main()