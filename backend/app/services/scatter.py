"""Build a per-trial scatter (enrollment vs. duration) from normalized records.

Unlike the bucketed charts, a scatter has one point *per trial*, so it is inherently
sample-based (capped at MAX_POINTS) rather than backed by exact per-bucket counts. Only
trials that report both an enrollment count and a derivable duration are plottable.

When more trials are plottable than the cap, we take a **uniform random subsample** (fixed
seed for reproducibility) rather than the largest-enrollment trials — keeping the visible cloud
representative of the real enrollment-vs-duration relationship instead of biasing it toward
mega-trials. `plottable_count()` reports how many were eligible so callers can say so honestly.
"""

from __future__ import annotations

import random
from collections.abc import Iterable
from typing import Any

from ..clients.clinicaltrials import TrialRecord

MAX_POINTS = 300
_SAMPLE_SEED = 0  # fixed so the same record set always yields the same subsample


def _is_plottable(r: TrialRecord) -> bool:
    return r.enrollment is not None and r.enrollment > 0 and r.duration_months is not None


def plottable_count(records: Iterable[TrialRecord]) -> int:
    """How many records have both an enrollment count and a derivable duration."""
    return sum(1 for r in records if _is_plottable(r))


def build_scatter_points(
    records: Iterable[TrialRecord], max_points: int = MAX_POINTS
) -> list[dict[str, Any]]:
    """x = enrollment (participants), y = duration (months); color/series = phase.

    Down to `max_points` via a deterministic uniform random sample (not a top-N by enrollment),
    so the plotted distribution is unbiased.
    """
    points = [
        {
            "nct_id": r.nct_id,
            "title": r.title,
            "phase": r.phases[-1] if r.phases else "Not Applicable",
            "x": r.enrollment,
            "y": r.duration_months,
        }
        for r in records
        if _is_plottable(r)
    ]
    # Sort by nct_id first so the subsample is deterministic regardless of upstream record order.
    points.sort(key=lambda p: str(p["nct_id"]))
    if len(points) > max_points:
        points = random.Random(_SAMPLE_SEED).sample(points, max_points)
        points.sort(key=lambda p: str(p["nct_id"]))  # stable output ordering
    return points
