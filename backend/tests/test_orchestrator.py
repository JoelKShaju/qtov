from __future__ import annotations

import asyncio

from app.agent import orchestrator


async def test_bounded_gather_caps_concurrency(monkeypatch):
    monkeypatch.setattr(orchestrator.settings, "upstream_concurrency", 3)
    active = 0
    peak = 0

    async def task() -> int:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return 1

    results = await orchestrator._bounded_gather([task for _ in range(12)])
    assert results == [1] * 12
    assert peak <= 3  # never more than the configured limit in flight at once


async def test_bounded_gather_propagates_or_captures_exceptions(monkeypatch):
    monkeypatch.setattr(orchestrator.settings, "upstream_concurrency", 5)

    async def boom() -> int:
        raise ValueError("upstream failed")

    async def ok() -> int:
        return 7

    # return_exceptions=True keeps siblings alive and surfaces the error object (used by the
    # exact-count fan-out so one failed bucket degrades to 0 instead of failing the request).
    out = await orchestrator._bounded_gather([boom, ok], return_exceptions=True)
    assert out[1] == 7
    assert isinstance(out[0], ValueError)
