import os
import time

# Reasoning: A request that never returns is worse than one that fails. Two long runs
# (the hallucination audit and a 35-query eval) each hung indefinitely mid-run on a
# Mistral call that simply never came back — CPU flat, no error, no progress — because
# the SDK was invoked with no timeout and the retry loop below only ever sees an
# exception. A bounded request turns that silent hang into a retryable error.
REQUEST_TIMEOUT_MS = int(os.getenv("MISTRAL_TIMEOUT_MS", "60000"))

# Reasoning: The Mistral free/low tier enforces a strict requests-per-second rate limit.
# Under eval load (dozens of queries fired back-to-back) we regularly hit 429s.
# Rather than faking a response, retry with exponential backoff — a real reliability
# pattern, not a substitute for the real model call.
RETRYABLE = ("429", "rate_limited", "timeout", "timed out", "connection", "read operation")


def call_mistral_with_retry(fn, max_retries: int = 6, base_delay: float = 2.0):
    """Call a zero-arg function wrapping a Mistral SDK request, retrying on rate limits and timeouts."""
    last_err = None
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            message = str(e).lower()
            # Reasoning: Retry timeouts and transport errors as well as 429s. Previously
            # only rate limits were retried, so any other transient network fault killed
            # a run outright — and a hang, having raised nothing at all, was never even
            # reached by this handler.
            if not any(token in message for token in RETRYABLE):
                raise
            last_err = e
            if attempt < max_retries - 1:
                time.sleep(base_delay * (2 ** attempt))
    raise last_err
