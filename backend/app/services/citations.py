"""Build the source trail: map each data point (bucket / edge / point) back to trials.

Beyond the list of NCT IDs, each `TrialRef` carries an `excerpt` — the exact field/value
from that trial's API record that supports the datum it backs. The
excerpt is dimension-aware: a phase bucket quotes the trial's phases, a year bucket quotes its
start date, and so on, so a reader can verify *why* a trial was counted under a given bucket.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..clients.clinicaltrials import TrialRecord
from ..schemas.query import GroupBy
from ..schemas.visualization import Citation, TrialRef
from .aggregate import Bucket

TRIAL_URL = "https://clinicaltrials.gov/study/{}"
DEFAULT_LIMIT = 25

ExcerptFn = Callable[[TrialRecord], str | None]


def _join(values: list[str]) -> str:
    return ", ".join(v for v in values if v)


# Per-dimension excerpt builders: quote the actual record field that put the trial in a bucket.
_GROUP_EXCERPT: dict[GroupBy, ExcerptFn] = {
    GroupBy.YEAR: lambda r: f"Start date: {r.start_date}" if r.start_date else None,
    GroupBy.PHASE: lambda r: f"Phase: {_join(r.phases)}" if r.phases else "Phase: Not Applicable",
    GroupBy.COUNTRY: lambda r: f"Locations: {_join(r.countries)}" if r.countries else None,
    GroupBy.SPONSOR: lambda r: f"Lead sponsor: {r.lead_sponsor}" if r.lead_sponsor else None,
    GroupBy.STATUS: lambda r: f"Overall status: {r.overall_status}" if r.overall_status else None,
}


def _no_excerpt(_r: TrialRecord) -> str | None:
    return None


def _excerpt_fn(group_by: GroupBy | None) -> ExcerptFn:
    return _GROUP_EXCERPT.get(group_by, _no_excerpt) if group_by else _no_excerpt


def _refs(
    nct_ids: list[str],
    trials_by_nct: dict[str, TrialRecord],
    limit: int,
    excerpt: ExcerptFn,
) -> list[TrialRef]:
    refs: list[TrialRef] = []
    for nct in nct_ids[:limit]:
        rec = trials_by_nct.get(nct)
        refs.append(
            TrialRef(
                nct_id=nct,
                title=rec.title if rec else nct,
                url=TRIAL_URL.format(nct),
                excerpt=excerpt(rec) if rec else None,
            )
        )
    return refs


def build_citations(
    buckets: list[Bucket],
    trials_by_nct: dict[str, TrialRecord],
    group_by: GroupBy | None = None,
    limit: int = DEFAULT_LIMIT,
) -> list[Citation]:
    excerpt = _excerpt_fn(group_by)
    return [
        Citation(
            bucket=b.label,
            value=b.value,
            nct_ids=b.nct_ids,
            trials=_refs(b.nct_ids, trials_by_nct, limit, excerpt),
        )
        for b in buckets
    ]


def citations_from_links(
    links: list[dict[str, Any]], trials_by_nct: dict[str, TrialRecord], limit: int = DEFAULT_LIMIT
) -> list[Citation]:
    citations: list[Citation] = []
    for link in links:
        source = str(link["source"]).split(":", 1)[-1]
        target = str(link["target"]).split(":", 1)[-1]
        nct_ids = link["nct_ids"]

        # Quote ONLY the intervention this edge represents (its target drug) — not every
        # intervention on the trial. build_network drops placebo/sham and non-drug types, so
        # joining all interventions would cite drugs that don't justify the rendered edge.
        def excerpt(r: TrialRecord, sponsor: str = source, drug: str = target) -> str:
            return f'Lead sponsor: {r.lead_sponsor or sponsor} · intervention: {drug}'

        citations.append(
            Citation(
                bucket=f"{source} → {target}",
                value=link["value"],
                nct_ids=nct_ids,
                trials=_refs(nct_ids, trials_by_nct, limit, excerpt),
            )
        )
    return citations


def citations_from_points(
    points: list[dict[str, Any]], trials_by_nct: dict[str, TrialRecord]
) -> list[Citation]:
    """One citation per scatter point (each point is a single trial)."""

    def excerpt(r: TrialRecord) -> str:
        span = f"{r.start_date or '?'} → {r.completion_date or '?'}"
        return f"Enrollment: {r.enrollment}; {span} ({r.duration_months} months)"

    citations: list[Citation] = []
    for p in points:
        nct = str(p["nct_id"])
        citations.append(
            Citation(
                bucket=nct,
                value=float(p.get("x", 0) or 0),
                nct_ids=[nct],
                trials=_refs([nct], trials_by_nct, 1, excerpt),
            )
        )
    return citations
