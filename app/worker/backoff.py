"""Backoff schedule for retries.

Exponential base so each failure waits roughly twice as long as the last, capped so
it never grows absurdly. Jitter (a random fraction added on top) is not cosmetic:
without it, every delivery that failed during the same outage retries at the exact
same instant, and when the receiver comes back you hammer it with a synchronized
burst. Jitter smears those retries across a window so the recovering endpoint is
not re-overwhelmed.
"""

import random

BASE_SECONDS = 5
CAP_SECONDS = 3600  # an hour between tries at most


def next_delay(attempt_number: int) -> float:
    """Seconds to wait before the given attempt number (1-based).

    attempt 1 -> ~5s, 2 -> ~10s, 3 -> ~20s, 4 -> ~40s, ... capped at one hour,
    each with up to 50% added jitter.
    """
    exponential = BASE_SECONDS * (2 ** (attempt_number - 1))
    capped = min(exponential, CAP_SECONDS)
    jitter = capped * random.uniform(0, 0.5)
    return capped + jitter
