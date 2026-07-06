from __future__ import annotations

from app.schemas.query import GroupBy, QuerySpec, QueryType
from app.services.counts import exact_count


class FakeClient:
    def __init__(self, total: int = 42) -> None:
        self.total = total
        self.calls: list[tuple[QuerySpec, str | None]] = []

    async def count(self, spec: QuerySpec, *, extra_advanced: str | None = None) -> int:
        self.calls.append((spec, extra_advanced))
        return self.total


async def test_exact_count_year_sets_year_bounds():
    client = FakeClient()
    n = await exact_count(
        client, QuerySpec(query_type=QueryType.TIME_TREND, condition="x"), GroupBy.YEAR, "2019"
    )
    assert n == 42
    spec, _ = client.calls[0]
    assert spec.start_year == 2019 and spec.end_year == 2019


async def test_exact_count_phase_uses_advanced_clause():
    client = FakeClient()
    await exact_count(client, QuerySpec(query_type=QueryType.DISTRIBUTION), GroupBy.PHASE, "Phase 2")
    _, advanced = client.calls[0]
    assert advanced == "AREA[Phase]PHASE2"


async def test_exact_count_country_sets_country():
    client = FakeClient()
    await exact_count(
        client, QuerySpec(query_type=QueryType.GEOGRAPHIC), GroupBy.COUNTRY, "United States"
    )
    spec, _ = client.calls[0]
    assert spec.country == "United States"


async def test_exact_count_status_denormalizes_label():
    client = FakeClient()
    await exact_count(
        client, QuerySpec(query_type=QueryType.DISTRIBUTION), GroupBy.STATUS, "Active Not Recruiting"
    )
    spec, _ = client.calls[0]
    assert spec.status == ["ACTIVE_NOT_RECRUITING"]
