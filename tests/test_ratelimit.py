"""Tests for the token-bucket ``RateLimiter`` (deterministic clock + sleeper)."""

from __future__ import annotations

import pytest

from file_mover.transfer.ratelimit import RateLimiter


class _Clock:
    """A manually-advanced monotonic clock for deterministic pacing tests."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _limiter(rate: int, clock: _Clock) -> tuple[RateLimiter, list[float]]:
    slept: list[float] = []
    return RateLimiter(rate, clock=clock, sleeper=slept.append), slept


@pytest.mark.requirement("L2-BWL-004")
def test_zero_rate_is_unlimited_and_never_sleeps() -> None:
    clock = _Clock()
    limiter, slept = _limiter(0, clock)
    assert limiter.is_unlimited() is True
    assert limiter.bytes_per_second == 0
    limiter.throttle(1_000_000_000)
    assert slept == []  # unlimited imposes no delay


@pytest.mark.requirement("L2-BWL-001")
def test_spends_burst_then_sleeps_for_the_deficit() -> None:
    clock = _Clock()  # frozen: no tokens accrue between calls
    limiter, slept = _limiter(100, clock)  # capacity = one second = 100 tokens
    limiter.throttle(100)  # drains the initial burst exactly, no wait
    assert slept == []
    limiter.throttle(100)  # bucket empty, 100-byte deficit at 100 B/s -> 1.0s
    assert slept == [pytest.approx(1.0)]
    limiter.throttle(50)  # a further 50-byte deficit -> 0.5s
    assert slept == [pytest.approx(1.0), pytest.approx(0.5)]


@pytest.mark.requirement("L2-BWL-001")
def test_elapsed_time_refills_the_bucket() -> None:
    clock = _Clock()
    limiter, slept = _limiter(100, clock)
    limiter.throttle(100)  # empty the bucket
    clock.advance(0.5)  # 0.5s * 100 B/s = 50 tokens refilled
    limiter.throttle(50)  # covered by the refill, no wait
    assert slept == []
    limiter.throttle(50)  # now empty again -> 0.5s deficit
    assert slept == [pytest.approx(0.5)]


@pytest.mark.requirement("L2-BWL-001")
def test_burst_capacity_is_capped_at_one_second() -> None:
    clock = _Clock()
    limiter, slept = _limiter(100, clock)
    limiter.throttle(1)  # prime the fill clock, bucket ~99
    clock.advance(10.0)  # 10s would be 1000 tokens, but capacity caps at 100
    limiter.throttle(100)  # fully covered by the capped burst, no wait
    assert slept == []
    limiter.throttle(1)  # bucket exhausted -> a small deficit sleep
    assert slept == [pytest.approx(0.01)]


@pytest.mark.requirement("L2-BWL-002")
def test_set_rate_changes_the_limit_live() -> None:
    clock = _Clock()
    limiter, slept = _limiter(0, clock)
    assert limiter.set_rate(200) == 200
    assert limiter.bytes_per_second == 200
    assert limiter.is_unlimited() is False
    # Switching from unlimited grants no free burst: the bucket starts empty, so the first
    # 200-byte chunk already incurs a full 1.0s deficit at 200 B/s.
    limiter.throttle(200)
    assert slept == [pytest.approx(1.0)]
    # Returning to unlimited removes throttling immediately.
    assert limiter.set_rate(0) == 0
    limiter.throttle(10_000_000)
    assert slept == [pytest.approx(1.0)]  # no new sleep recorded


@pytest.mark.requirement("L2-BWL-002")
def test_set_rate_clamps_negative_to_zero() -> None:
    clock = _Clock()
    limiter, _ = _limiter(100, clock)
    assert limiter.set_rate(-5) == 0
    assert limiter.is_unlimited() is True


@pytest.mark.requirement("L2-BWL-003")
def test_one_limiter_enforces_the_cap_across_concurrent_streams() -> None:
    # A single shared limiter models two files copying concurrently. The cap is aggregate:
    # bytes spent by "file A" leave fewer tokens for "file B", so B is throttled even though
    # it has moved only 60 bytes itself — a per-file limiter would not have slept here.
    clock = _Clock()  # frozen: the only tokens are the shared initial burst
    limiter, slept = _limiter(100, clock)  # 100 B/s shared ceiling
    limiter.throttle(60)  # file A: 100 -> 40 tokens, no wait
    assert slept == []
    limiter.throttle(60)  # file B: 40 tokens, 20-byte deficit -> 0.2s
    assert slept == [pytest.approx(0.2)]


@pytest.mark.requirement("L2-BWL-001")
def test_non_positive_byte_count_is_a_noop() -> None:
    clock = _Clock()
    limiter, slept = _limiter(100, clock)
    limiter.throttle(0)
    limiter.throttle(-10)
    assert slept == []
