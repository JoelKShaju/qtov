"""Classification eval: measure how well the agent maps NL queries to the closed taxonomy.

Runs the interpreter over a labeled golden set (`golden_set.py`) and reports overall accuracy,
per-query-type precision/recall/F1, and a confusion matrix — so the AI-design quality is measured,
not asserted. Writes a markdown snapshot to `evals/eval_report.md`.

Run (needs OPENAI_API_KEY):  uv run python evals/run_evals.py
Exits non-zero if accuracy < EVAL_MIN_ACCURACY (default 0.85), so it can gate CI when a key is set.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from app.config import settings
from app.schemas.query import QueryRequest, QueryType
from evals.faithfulness import FaithfulnessResult, run_faithfulness
from evals.golden_set import GOLDEN_SET
from evals.metrics import Pair, accuracy, confusion_matrix, macro_f1, per_class_metrics

LABELS = [qt.value for qt in QueryType]  # fixed ordering for the matrix
# Short, collision-free column headers for the confusion matrix.
ABBR = {
    "time_trend": "TT",
    "distribution": "DI",
    "comparison": "CMP",
    "geographic": "GEO",
    "relationship": "REL",
    "correlation": "COR",
    "unsupported": "UNS",
}
REPORT_PATH = Path(__file__).resolve().parent / "eval_report.md"
_CONCURRENCY = 5


async def _classify_all() -> list[Pair]:
    """Run interpret() over the golden set (bounded concurrency) -> (gold, predicted) pairs."""
    from app.agent.interpreter import interpret

    sem = asyncio.Semaphore(_CONCURRENCY)

    async def one(query: str, expected: QueryType) -> Pair:
        async with sem:
            spec = await interpret(QueryRequest(query=query))
        return (expected.value, spec.query_type.value)

    return await asyncio.gather(*(one(q, e) for q, e in GOLDEN_SET))


def _matrix_table(pairs: list[Pair]) -> str:
    matrix = confusion_matrix(pairs, LABELS)
    header = f"{'gold/pred':>15} | " + " ".join(f"{ABBR[c]:>3}" for c in LABELS)
    lines = [header, "-" * len(header)]
    for g in LABELS:
        row = " ".join(f"{matrix[g][p]:>3}" for p in LABELS)
        lines.append(f"{ABBR[g]:>3} {g:11.11s} | {row}")
    legend = "  ".join(f"{ABBR[v]}={v}" for v in LABELS)
    return "\n".join(lines) + "\n\nLegend: " + legend


def _report(pairs: list[Pair], model: str) -> str:
    acc = accuracy(pairs)
    macro = macro_f1(pairs, LABELS)
    pcm = per_class_metrics(pairs, LABELS)
    rows = [
        "| query_type | precision | recall | f1 | support |",
        "|---|---|---|---|---|",
    ]
    for label in LABELS:
        m = pcm[label]
        if not m.support:
            continue
        rows.append(
            f"| `{label}` | {m.precision:.2f} | {m.recall:.2f} | {m.f1:.2f} | {m.support} |"
        )
    return (
        f"# Classification eval report\n\n"
        f"- Model: `{model}`\n"
        f"- Cases: {len(pairs)}\n"
        f"- **Accuracy: {acc:.1%}**  ·  Macro-F1: {macro:.2f}\n\n"
        f"## Per-query-type metrics\n\n" + "\n".join(rows) + "\n\n"
        f"## Confusion matrix (rows = gold, cols = predicted)\n\n"
        f"```\n{_matrix_table(pairs)}\n```\n"
    )


def _faithfulness_report(r: FaithfulnessResult, min_coverage: float) -> str:
    status = "PASS" if r.passed(min_coverage) else "FAIL"
    lines = [
        "## Data faithfulness (deterministic — no LLM/network)\n",
        f"- **Citation coverage: {r.coverage:.0%}** ({r.points_cited}/{r.points_total} "
        f"value>0 data points cited; gate ≥ {min_coverage:.0%})",
        f"- **Count reconciliation (time_trend): {r.recon_passed}/{r.recon_total}** "
        "(per-year exact counts sum to the reported total)",
        f"- Result: **{status}**",
    ]
    if r.failures:
        lines.append("- Failures:\n" + "\n".join(f"  - {f}" for f in r.failures))
    return "\n".join(lines) + "\n"


async def main() -> int:
    min_coverage = float(os.environ.get("EVAL_MIN_COVERAGE", "1.0"))
    min_accuracy = float(os.environ.get("EVAL_MIN_ACCURACY", "0.85"))

    # 1. Data faithfulness — always runs (deterministic, no key required).
    faith = await run_faithfulness()
    faith_section = _faithfulness_report(faith, min_coverage)
    sections = [faith_section]
    ok = faith.passed(min_coverage)

    # 2. Classification — needs a live LLM; skip LOUDLY if no key.
    if os.environ.get("OPENAI_API_KEY"):
        pairs = await _classify_all()
        for (gold, pred), (query, _) in zip(pairs, GOLDEN_SET, strict=True):
            print(f"[{'PASS' if gold == pred else 'FAIL'}] "
                  f"expected={gold:13} got={pred:13} :: {query}")
        sections.insert(0, _report(pairs, settings.classifier_model_list[0]))
        ok = ok and accuracy(pairs) >= min_accuracy
    else:
        print("=" * 70)
        print("!! OPENAI_API_KEY not set — SKIPPING the classification eval.")
        print("!! Only the deterministic data-faithfulness checks ran.")
        print("=" * 70)
        sections.insert(0, "# Eval report\n\n> Classification eval SKIPPED (no OPENAI_API_KEY).\n")

    report = "\n\n".join(sections)
    REPORT_PATH.write_text(report)
    print("\n" + report)
    print(f"Wrote {REPORT_PATH}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
