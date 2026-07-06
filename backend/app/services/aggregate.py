"""Deterministic aggregation of normalized trial records into chart buckets.

Every bucket keeps the list of contributing NCT IDs so citations are exact.
"""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel

from ..clients.clinicaltrials import TrialRecord
from ..schemas.query import GroupBy

PHASE_ORDER = ["Early Phase 1", "Phase 1", "Phase 2", "Phase 3", "Phase 4", "Not Applicable"]
TOP_N = 15


class Bucket(BaseModel):
    label: str
    value: float
    nct_ids: list[str]


def _buckets_from_map(mapping: dict[str, list[str]]) -> list[Bucket]:
    return [Bucket(label=label, value=len(ncts), nct_ids=ncts) for label, ncts in mapping.items()]


def _top_n(mapping: dict[str, list[str]], n: int = TOP_N) -> list[Bucket]:
    buckets = _buckets_from_map(mapping)
    buckets.sort(key=lambda b: b.value, reverse=True)
    return buckets[:n]


def aggregate_by_year(records: Iterable[TrialRecord]) -> list[Bucket]:
    mapping: dict[str, list[str]] = {}
    for r in records:
        if r.start_year:
            mapping.setdefault(str(r.start_year), []).append(r.nct_id)
    buckets = _buckets_from_map(mapping)
    buckets.sort(key=lambda b: b.label)
    return buckets


def aggregate_by_phase(records: Iterable[TrialRecord]) -> list[Bucket]:
    mapping: dict[str, list[str]] = {}
    for r in records:
        for phase in r.phases or ["Not Applicable"]:
            mapping.setdefault(phase, []).append(r.nct_id)
    buckets = _buckets_from_map(mapping)
    buckets.sort(key=lambda b: PHASE_ORDER.index(b.label) if b.label in PHASE_ORDER else 99)
    return buckets


def aggregate_by_country(records: Iterable[TrialRecord]) -> list[Bucket]:
    mapping: dict[str, list[str]] = {}
    for r in records:
        for country in r.countries or []:
            mapping.setdefault(country, []).append(r.nct_id)
    return _top_n(mapping)


def aggregate_by_sponsor(records: Iterable[TrialRecord]) -> list[Bucket]:
    mapping: dict[str, list[str]] = {}
    for r in records:
        if r.lead_sponsor:
            mapping.setdefault(r.lead_sponsor, []).append(r.nct_id)
    return _top_n(mapping)


def aggregate_by_status(records: Iterable[TrialRecord]) -> list[Bucket]:
    mapping: dict[str, list[str]] = {}
    for r in records:
        if r.overall_status:
            mapping.setdefault(r.overall_status.replace("_", " ").title(), []).append(r.nct_id)
    return _top_n(mapping)


_DISPATCH = {
    GroupBy.YEAR: aggregate_by_year,
    GroupBy.PHASE: aggregate_by_phase,
    GroupBy.COUNTRY: aggregate_by_country,
    GroupBy.SPONSOR: aggregate_by_sponsor,
    GroupBy.STATUS: aggregate_by_status,
}


def aggregate(records: Iterable[TrialRecord], group_by: GroupBy | None) -> list[Bucket]:
    fn = _DISPATCH.get(group_by or GroupBy.PHASE, aggregate_by_phase)
    return fn(records)
