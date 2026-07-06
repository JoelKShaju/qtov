from __future__ import annotations

from app.ratelimit import FixedWindowLimiter


def test_allows_up_to_limit_then_denies_within_window():
    lim = FixedWindowLimiter(window_seconds=60)
    # First `limit` calls in the same window pass; the next is denied.
    assert lim.allow("ip", limit=2, now=0.0) is True
    assert lim.allow("ip", limit=2, now=1.0) is True
    assert lim.allow("ip", limit=2, now=2.0) is False


def test_window_resets_after_elapsed():
    lim = FixedWindowLimiter(window_seconds=60)
    assert lim.allow("ip", limit=1, now=0.0) is True
    assert lim.allow("ip", limit=1, now=30.0) is False  # still in window
    assert lim.allow("ip", limit=1, now=61.0) is True  # window elapsed -> reset


def test_keys_are_isolated_per_client():
    lim = FixedWindowLimiter(window_seconds=60)
    assert lim.allow("a", limit=1, now=0.0) is True
    assert lim.allow("b", limit=1, now=0.0) is True  # different key, own budget
    assert lim.allow("a", limit=1, now=0.5) is False
