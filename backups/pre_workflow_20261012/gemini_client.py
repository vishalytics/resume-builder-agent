import time
from google import genai
from google.genai import types, errors


# ============================================================
# GEMINI MODEL FALLBACK CHAIN
# ============================================================

MODELS = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
]


# Number of attempts for each model.
# The SDK itself is configured to make only ONE HTTP attempt.
RETRIES_PER_MODEL = 2

# Retry delays:
# attempt 1 failure -> 2 seconds
# attempt 2 failure -> move to next model
INITIAL_DELAY = 2


# ============================================================
# GEMINI CLIENT
# ============================================================

client = genai.Client(
    http_options=types.HttpOptions(
        retry_options=types.HttpRetryOptions(
            attempts=1
        )
    )
)


# ============================================================
# MAIN GEMINI FUNCTION
# ============================================================

def generate_with_fallback(
    prompt,
    models=None,
    retries_per_model=RETRIES_PER_MODEL
):
    """
    Generate text using Gemini with:

    • Multiple model fallbacks
    • Short retries
    • Exponential backoff
    • 503/429/5xx handling
    • Authentication error handling
    • Empty-response handling

    Returns:
        str: Gemini response text
    """

    if models is None:
        models = MODELS

    last_error = None

    for model in models:

        print()
        print("=" * 60)
        print(f"Trying model: {model}")
        print("=" * 60)

        for attempt in range(1, retries_per_model + 1):

            try:

                print(
                    f"Attempt {attempt}/{retries_per_model}..."
                )

                # ------------------------------------------------
                # Use Google's current Interactions API
                # ------------------------------------------------

                interaction = client.interactions.create(
                    model=model,
                    input=prompt,
                    generation_config={
                        "thinking_level": "low"
                    }
                )

                response_text = interaction.output_text

                if not response_text:
                    raise RuntimeError(
                        f"{model} returned an empty response."
                    )

                print()
                print(f"SUCCESS: {model}")

                return response_text

            # ====================================================
            # GEMINI API ERRORS
            # ====================================================

            except errors.APIError as e:

                last_error = e

                status = getattr(e, "code", None)

                print(
                    f"ERROR from {model}: HTTP {status}"
                )

                # ------------------------------------------------
                # TEMPORARY ERRORS
                # ------------------------------------------------

                if status in (408, 429, 500, 502, 503, 504):

                    if attempt < retries_per_model:

                        delay = INITIAL_DELAY * (
                            2 ** (attempt - 1)
                        )

                        print(
                            f"Temporary error."
                            f" Retrying in {delay} seconds..."
                        )

                        time.sleep(delay)

                        continue

                    print(
                        f"{model} unavailable after "
                        f"{retries_per_model} attempts."
                    )

                    print(
                        "Falling back to next model..."
                    )

                    break

                # ------------------------------------------------
                # MODEL NOT AVAILABLE
                # ------------------------------------------------

                elif status == 404:

                    print(
                        f"{model} is not available "
                        f"for this project."
                    )

                    print(
                        "Skipping to next model..."
                    )

                    break

                # ------------------------------------------------
                # AUTHENTICATION / PERMISSION
                # ------------------------------------------------

                elif status in (401, 403):

                    raise RuntimeError(
                        f"Gemini authentication/permission "
                        f"error ({status}).\n"
                        f"Check GEMINI_API_KEY and project access."
                    ) from e

                # ------------------------------------------------
                # OTHER API ERRORS
                # ------------------------------------------------

                else:

                    raise

            # ====================================================
            # NETWORK / UNEXPECTED ERRORS
            # ====================================================

            except Exception as e:

                last_error = e

                print(
                    f"Unexpected error from {model}: {e}"
                )

                if attempt < retries_per_model:

                    delay = INITIAL_DELAY * (
                        2 ** (attempt - 1)
                    )

                    print(
                        f"Retrying in {delay} seconds..."
                    )

                    time.sleep(delay)

                    continue

                print(
                    f"Skipping {model} and trying "
                    f"the next model..."
                )

                break

    # ============================================================
    # EVERYTHING FAILED
    # ============================================================

    raise RuntimeError(
        "\nAll Gemini models failed.\n"
        "The Resume Agent could not complete the request."
    ) from last_error