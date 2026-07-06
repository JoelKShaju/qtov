from __future__ import annotations

from evals.faithfulness import run_faithfulness


async def test_faithfulness_eval_passes_on_fixtures():
    """The data-faithfulness eval runs the real pipeline deterministically (no LLM/network)."""
    result = await run_faithfulness()
    assert result.coverage == 1.0, result.failures  # every value>0 datum is cited
    assert result.reconciliation_ok, result.failures  # time_trend counts reconcile to total
    assert result.recon_total >= 1
    assert result.points_total >= 5
