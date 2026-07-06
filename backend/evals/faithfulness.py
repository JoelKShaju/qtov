"""Deterministic data-faithfulness checks for the eval (no LLM, no network).

Runs the *real* orchestrator pipeline against fixed fixtures + a fake upstream client, then measures
two downstream properties the assignment actually cares about:

- **Count reconciliation** — for `time_trend`, the per-year exact counts sum to the reported total
  (the README's headline property). NOT checked for phase/geographic: a trial can belong to multiple
  phases / countries, so those bucket sums legitimately exceed the total (double-counting).
- **Citation coverage** — every shown data point with `value > 0` carries at least one NCT id, so
  nothing is uncitable (this is what catches the empty-`nct_ids` bucket class).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from app.agent.orchestrator import run_query
from app.clients.clinicaltrials import TrialRecord
from app.db.repositories import InMemoryRepository
from app.schemas.query import GroupBy, QueryRequest, QuerySpec, QueryType


def _rec(nct: str, *, year: int | None = None, phases=(), country: str | None = None) -> TrialRecord:
    return TrialRecord(
        nct_id=nct,
        title=nct,
        start_date=f"{year}-01" if year else None,
        start_year=year,
        phases=list(phases),
        countries=[country] if country else [],
        lead_sponsor="Sponsor",
    )


class _FakeClient:
    """Minimal deterministic upstream: counts keyed by ('year'|'phase'|'country', value)."""

    page_size = 50
    max_records = 1000

    def __init__(self, records: list[TrialRecord], counts: dict, total: int) -> None:
        self._records, self._counts, self._total = records, counts, total

    async def search(self, spec):  # type: ignore[no-untyped-def]
        return list(self._records), self._total

    async def count(self, spec, *, extra_advanced: str | None = None) -> int:  # type: ignore[no-untyped-def]
        if extra_advanced and "AREA[Phase]" in extra_advanced:
            token = extra_advanced.split("AREA[Phase]")[1].split()[0]
            return self._counts.get(("phase", token), 0)
        if spec.country:
            return self._counts.get(("country", spec.country), 0)
        if spec.start_year and spec.start_year == spec.end_year:
            return self._counts.get(("year", spec.start_year), 0)
        return self._total

    async def fetch_sample(self, spec, limit: int):  # type: ignore[no-untyped-def]
        return list(self._records)[:limit]


@dataclass
class _Case:
    name: str
    spec: QuerySpec
    client: _FakeClient
    reconciles: bool  # whether count-reconciliation applies (time_trend only)


def _cases() -> list[_Case]:
    return [
        _Case(
            "time_trend",
            QuerySpec(query_type=QueryType.TIME_TREND, condition="x", start_year=2015, group_by=GroupBy.YEAR),
            _FakeClient(
                [_rec("NCT1", year=2015), _rec("NCT2", year=2015), _rec("NCT3", year=2016), _rec("NCT4", year=2017)],
                {("year", 2015): 2, ("year", 2016): 1, ("year", 2017): 1},
                total=4,
            ),
            reconciles=True,
        ),
        _Case(
            "distribution",
            QuerySpec(query_type=QueryType.DISTRIBUTION, condition="x", group_by=GroupBy.PHASE),
            _FakeClient(
                [_rec("NCT5", phases=("Phase 2",)), _rec("NCT6", phases=("Phase 3",))],
                {("phase", "PHASE2"): 5, ("phase", "PHASE3"): 3},
                total=8,
            ),
            reconciles=False,
        ),
        _Case(
            "geographic",
            QuerySpec(query_type=QueryType.GEOGRAPHIC, condition="x", group_by=GroupBy.COUNTRY),
            _FakeClient(
                [_rec("NCT7", country="United States"), _rec("NCT8", country="China")],
                {("country", "United States"): 7, ("country", "China"): 3},
                total=10,
            ),
            reconciles=False,
        ),
    ]


@dataclass
class FaithfulnessResult:
    recon_total: int = 0
    recon_passed: int = 0
    points_total: int = 0
    points_cited: int = 0
    failures: list[str] = field(default_factory=list)

    @property
    def coverage(self) -> float:
        return self.points_cited / self.points_total if self.points_total else 1.0

    @property
    def reconciliation_ok(self) -> bool:
        return self.recon_passed == self.recon_total

    def passed(self, min_coverage: float = 1.0) -> bool:
        return self.coverage >= min_coverage and self.reconciliation_ok


async def run_faithfulness() -> FaithfulnessResult:
    """Run every case through the pipeline and aggregate reconciliation + coverage."""
    out = FaithfulnessResult()
    for case in _cases():
        async def _interp(_req, _spec=case.spec):  # type: ignore[no-untyped-def]
            return _spec

        resp = await run_query(
            QueryRequest(query=f"eval {case.name}"),
            interpret_fn=_interp,
            client=case.client,  # type: ignore[arg-type]
            repo=InMemoryRepository(),
        )
        # Citation coverage: each citation is a data point; value>0 must have >=1 NCT id.
        for c in resp.citations:
            if c.value > 0:
                out.points_total += 1
                if c.nct_ids:
                    out.points_cited += 1
                else:
                    out.failures.append(f"{case.name}: data point '{c.bucket}' has no citations")
        # Reconciliation (time_trend only).
        if case.reconciles:
            out.recon_total += 1
            total = resp.visualization.metadata.total_records
            shown = sum(p["y"] for p in resp.visualization.data)  # type: ignore[index]
            if shown == total:
                out.recon_passed += 1
            else:
                out.failures.append(f"{case.name}: sum(buckets)={shown} != total={total}")
    return out


if __name__ == "__main__":
    r = asyncio.run(run_faithfulness())
    print(f"coverage={r.coverage:.0%} reconciliation={r.recon_passed}/{r.recon_total} failures={r.failures}")
