import time

# Reasoning: The Mistral free/low tier enforces a strict requests-per-second rate limit.
# Under eval load (dozens of queries fired back-to-back) we regularly hit 429s.
# Rather than faking a response, retry with exponential backoff — a real reliability
# pattern, not a substitute for the real model call.
def call_mistral_with_retry(fn, max_retries: int = 6, base_delay: float = 2.0):
    """Call a zero-arg function wrapping a Mistral SDK request, retrying on 429 rate limits."""
    last_err = None
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            if "429" not in str(e) and "rate_limited" not in str(e):
                raise
            last_err = e
            if attempt < max_retries - 1:
                time.sleep(base_delay * (2 ** attempt))
    raise last_err
