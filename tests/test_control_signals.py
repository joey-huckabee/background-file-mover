"""Tests for the thread-safe pause/cancel signal registry."""

from __future__ import annotations

import pytest

from file_mover.exceptions import CopyInterrupted
from file_mover.jobs.models import ControlSignal
from file_mover.transfer.control_signals import JobControlSignals


@pytest.mark.requirement("L2-LIF-002")
def test_request_poll_and_clear() -> None:
    signals = JobControlSignals()
    assert signals.poll("j1") is None
    signals.request("j1", ControlSignal.PAUSE)
    assert signals.poll("j1") is ControlSignal.PAUSE
    signals.request("j1", ControlSignal.CANCEL)  # overwrites
    assert signals.poll("j1") is ControlSignal.CANCEL
    signals.clear("j1")
    assert signals.poll("j1") is None
    signals.clear("j1")  # idempotent


@pytest.mark.requirement("L2-LIF-002")
def test_interrupt_check_raises_only_when_signalled() -> None:
    signals = JobControlSignals()
    check = signals.interrupt_check_for("j1")
    check()  # not signalled -> no-op
    signals.request("j1", ControlSignal.PAUSE)
    with pytest.raises(CopyInterrupted):
        check()
    # A different job's check is unaffected.
    signals.interrupt_check_for("other")()
