import pytest

from app.ai.rate_limit import RateLimitedError, SlidingWindowLimiter


def test_limit_enforced_per_window_and_key():
    clock = [0.0]
    limiter = SlidingWindowLimiter(limit=3, window_s=60, now=lambda: clock[0])
    for _ in range(3):
        limiter.check("ask")
    with pytest.raises(RateLimitedError) as e:
        limiter.check("ask")
    assert e.value.status_code == 429 and e.value.code == "rate_limited"
    limiter.check("other-key")  # separate bucket
    clock[0] = 61.0
    limiter.check("ask")  # window has passed
