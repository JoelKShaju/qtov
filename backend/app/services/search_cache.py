"""Read-through cache around `ClinicalTrialsClient.search`.

A query's result set (the sampled NCT ids + true total) is cached, keyed by a hash of the
exact API params. On a fresh hit the trial records are re-hydrated from the `trials` table
instead of re-fetching and re-normalizing from ClinicalTrials.gov. A stale entry (older than
`CACHE_TTL_SECONDS`) or a partial cache (some trials evicted) falls through to a live fetch,
which repopulates both the trial cache and this index.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

from ..clients.clinicaltrials import ClinicalTrialsClient, TrialRecord, build_params
from ..config import settings
from ..db.repositories import Repository
from ..observability.logging import get_logger
from ..schemas.query import QuerySpec

log = get_logger(__name__)


def cache_key(spec: QuerySpec, page_size: int, max_records: int) -> str:
    """Stable key for a search: the API params plus the fetch bounds that shape the result set."""
    params = build_params(spec, page_size)
    payload = json.dumps({"params": params, "max_records": max_records}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _is_fresh(fetched_at: datetime | None) -> bool:
    if fetched_at is None:
        return False
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=UTC)
    return datetime.now(UTC) - fetched_at < timedelta(seconds=settings.cache_ttl_seconds)


async def cached_search(
    repo: Repository, client: ClinicalTrialsClient, spec: QuerySpec
) -> tuple[list[TrialRecord], int]:
    """Return (records, total) for a spec, served from cache when fresh."""
    key = cache_key(spec, client.page_size, client.max_records)
    entry = await repo.get_cached_search(key)
    if entry and _is_fresh(entry.get("fetched_at")):
        nct_ids = entry["nct_ids"]
        records = await repo.get_trials_by_ids(nct_ids)
        if len(records) == len(nct_ids):  # complete hit — nothing evicted
            log.info("cache.hit", key=key[:12], records=len(records))
            return records, entry["total"]

    records, total = await client.search(spec)
    await repo.upsert_trials(records)
    await repo.save_cached_search(key, [r.nct_id for r in records], total)
    log.info("cache.miss", key=key[:12], records=len(records))
    return records, total
