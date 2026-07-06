from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.clients.clinicaltrials import TrialRecord
from app.db.repositories import InMemoryRepository
from app.schemas.query import GroupBy, QuerySpec, QueryType
from app.services.search_cache import cache_key, cached_search


class FakeClient:
    """Minimal stand-in for ClinicalTrialsClient that counts fetches."""

    page_size = 50
    max_records = 100

    def __init__(self, records: list[TrialRecord], total: int) -> None:
        self._records = records
        self._total = total
        self.calls = 0

    async def search(self, spec) -> tuple[list[TrialRecord], int]:
        self.calls += 1
        return self._records, self._total


def _spec() -> QuerySpec:
    return QuerySpec(query_type=QueryType.TIME_TREND, condition="diabetes", group_by=GroupBy.YEAR)


async def test_cached_search_serves_second_call_from_cache():
    repo = InMemoryRepository()
    client = FakeClient([TrialRecord(nct_id="N1", title="One")], total=42)
    spec = _spec()

    recs1, total1 = await cached_search(repo, client, spec)
    recs2, total2 = await cached_search(repo, client, spec)

    assert client.calls == 1  # second call hit the cache, no refetch
    assert total1 == total2 == 42
    assert [r.nct_id for r in recs1] == [r.nct_id for r in recs2] == ["N1"]


async def test_cached_search_refetches_when_stale():
    repo = InMemoryRepository()
    client = FakeClient([TrialRecord(nct_id="N1", title="One")], total=42)
    spec = _spec()

    await cached_search(repo, client, spec)
    # Force the entry to look older than the TTL.
    key = cache_key(spec, client.page_size, client.max_records)
    repo.search_cache[key]["fetched_at"] = datetime.now(UTC) - timedelta(days=400)

    await cached_search(repo, client, spec)
    assert client.calls == 2  # stale -> live refetch


async def test_cached_search_refetches_when_trial_evicted():
    repo = InMemoryRepository()
    client = FakeClient([TrialRecord(nct_id="N1", title="One")], total=42)
    spec = _spec()

    await cached_search(repo, client, spec)
    repo.trials.clear()  # trial gone from cache -> partial hit

    await cached_search(repo, client, spec)
    assert client.calls == 2
