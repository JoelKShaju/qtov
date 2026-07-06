"""Exact per-bucket counts via the API's countTotal.

The sampled fetch discovers which buckets to show and provides citation NCT IDs;
this turns each bucket's *value* into the true total for that slice (not the sample
count, which would cap at MAX_RECORDS).
"""

from __future__ import annotations

from ..clients.clinicaltrials import PHASE_TOKENS, ClinicalTrialsClient
from ..schemas.query import GroupBy, QuerySpec


def bucket_spec(base_spec: QuerySpec, group_by: GroupBy, label: str) -> QuerySpec | None:
    """A QuerySpec narrowed to one bucket of `group_by` — for fetching that bucket's records.

    Returns None when the label can't be turned into a filter (so the caller skips it). Phase is
    expressed via the spec's `phase` field (build_params emits the same AREA[Phase] clause).
    """
    if group_by == GroupBy.YEAR:
        try:
            year = int(label)
        except ValueError:
            return None
        return base_spec.model_copy(update={"start_year": year, "end_year": year})
    if group_by == GroupBy.PHASE:
        return base_spec.model_copy(update={"phase": label}) if label in PHASE_TOKENS else None
    if group_by == GroupBy.COUNTRY:
        return base_spec.model_copy(update={"country": label})
    if group_by == GroupBy.SPONSOR:
        return base_spec.model_copy(update={"sponsor": label})
    if group_by == GroupBy.STATUS:
        return base_spec.model_copy(update={"status": [label.upper().replace(" ", "_")]})
    return None


async def exact_count(
    client: ClinicalTrialsClient, base_spec: QuerySpec, group_by: GroupBy, label: str
) -> int:
    """True count of trials in one bucket of `group_by` (combined with base filters)."""
    if group_by == GroupBy.YEAR:
        try:
            year = int(label)
        except ValueError:
            return 0
        sub = base_spec.model_copy(update={"start_year": year, "end_year": year})
        return await client.count(sub)
    if group_by == GroupBy.PHASE:
        token = PHASE_TOKENS.get(label)
        if not token:
            return 0
        return await client.count(base_spec, extra_advanced=f"AREA[Phase]{token}")
    if group_by == GroupBy.COUNTRY:
        return await client.count(base_spec.model_copy(update={"country": label}))
    if group_by == GroupBy.SPONSOR:
        return await client.count(base_spec.model_copy(update={"sponsor": label}))
    if group_by == GroupBy.STATUS:
        status_token = label.upper().replace(" ", "_")
        return await client.count(base_spec.model_copy(update={"status": [status_token]}))
    return 0
