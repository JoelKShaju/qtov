from __future__ import annotations

import respx
from httpx import Response

from app.api.deps import get_interpreter
from app.config import settings
from app.schemas.query import QuerySpec, QueryType

from .conftest import SAMPLE_STUDY


async def test_health(api):
    resp = await api.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@respx.mock
async def test_query_returns_line_visualization(api):
    respx.get(url__startswith=settings.clinicaltrials_base_url).mock(
        return_value=Response(200, json={"totalCount": 1, "studies": [SAMPLE_STUDY]})
    )
    resp = await api.post(
        "/api/query",
        json={"query": "How have diabetes trials changed per year since 2015?"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["visualization"]["type"] == "line"
    assert body["visualization"]["data"] == [{"x": "2019", "y": 1}]
    assert body["interpretation"]["query_type"] == "time_trend"
    assert body["citations"][0]["trials"][0]["nct_id"] == "NCT00000001"
    assert body["summary"] == "Stub summary citing sources."


@respx.mock
async def test_alternatives_are_mapped_and_filtered(api, app):
    from app.schemas.query import GroupBy

    async def fake(_request):
        return QuerySpec(
            query_type=QueryType.TIME_TREND,
            condition="diabetes",
            group_by=GroupBy.YEAR,
            confidence=0.5,
            # includes a dup of the chosen type and 'unsupported' — both should be dropped
            alternative_query_types=[
                QueryType.COMPARISON,
                QueryType.TIME_TREND,
                QueryType.UNSUPPORTED,
            ],
        )

    app.dependency_overrides[get_interpreter] = lambda: fake
    respx.get(url__startswith=settings.clinicaltrials_base_url).mock(
        return_value=Response(200, json={"totalCount": 1, "studies": [SAMPLE_STUDY]})
    )
    resp = await api.post("/api/query", json={"query": "diabetes trials per year"})
    body = resp.json()
    assert body["interpretation"]["confidence"] == 0.5
    assert body["interpretation"]["alternatives"] == [
        {"query_type": "comparison", "chart": "grouped_bar"}
    ]


@respx.mock
async def test_unsupported_query_returns_422(api, app):
    async def fake(_request):
        return QuerySpec(
            query_type=QueryType.UNSUPPORTED,
            supported=False,
            rejection_reason="That's not about clinical trials.",
        )

    app.dependency_overrides[get_interpreter] = lambda: fake
    resp = await api.post("/api/query", json={"query": "What's the weather in Paris?"})
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "unsupported_query"
    assert len(body["supported_query_types"]) == 6
    # No upstream call should have been made for an unsupported query.
    assert not respx.calls

    # An event is still created so the rejection has a shareable permalink.
    event_id = body["event_id"]
    assert event_id
    saved = await api.get(f"/api/events/{event_id}")
    assert saved.status_code == 200
    payload = saved.json()
    assert payload["error"] == "unsupported_query"
    assert payload["query"] == "What's the weather in Paris?"


def _study(nct="NCT00000001", phases=("PHASE2", "PHASE3"), year="2019", status="RECRUITING"):
    """Minimal study object; normalize_study fills the rest with defaults."""
    return {
        "protocolSection": {
            "identificationModule": {"nctId": nct, "briefTitle": "T"},
            "statusModule": {"overallStatus": status, "startDateStruct": {"date": year}},
            "designModule": {"phases": list(phases)},
        }
    }


@respx.mock
async def test_comparison_by_country_keeps_entities_distinct(api, app):
    """Distinct per-(entity, phase) counts prove the orchestrator doesn't swap entities."""
    counts = {
        ("United States", "PHASE2"): 10, ("United States", "PHASE3"): 20,
        ("China", "PHASE2"): 3, ("China", "PHASE3"): 4,
    }

    def handler(request):
        p = request.url.params
        entity = "China" if "China" in p.get("query.locn", "") else "United States"
        adv = p.get("filter.advanced", "")
        if "AREA[Phase]" in adv:
            phase = "PHASE2" if "PHASE2" in adv else "PHASE3"
            return Response(200, json={"totalCount": counts[(entity, phase)], "studies": []})
        if p.get("pageSize") == "1":  # a count query
            locn = p.get("query.locn", "")
            if " OR " in locn:  # deduplicated union population (both entities OR'd into one query)
                return Response(200, json={"totalCount": 33, "studies": []})  # < 30+7: 4 overlap
            return Response(200, json={"totalCount": sum(v for (e, _), v in counts.items() if e == entity), "studies": []})
        return Response(200, json={"totalCount": 999, "studies": [_study()]})  # sample

    async def fake(_request):
        return QuerySpec(
            query_type=QueryType.COMPARISON,
            comparison_entities=["United States", "China"],
            comparison_dimension="country",
        )

    app.dependency_overrides[get_interpreter] = lambda: fake
    respx.get(url__startswith=settings.clinicaltrials_base_url).mock(side_effect=handler)
    resp = await api.post("/api/query", json={"query": "compare US and China trials"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["visualization"]["type"] == "grouped_bar"
    rows = {r["bucket"]: r for r in body["visualization"]["data"]}
    # Each entity's per-phase value is exactly its own — not swapped.
    assert rows["Phase 2"]["United States"] == 10 and rows["Phase 2"]["China"] == 3
    assert rows["Phase 3"]["United States"] == 20 and rows["Phase 3"]["China"] == 4
    # Deduplicated population from the single OR union count — NOT 30+7=37, which would
    # double-count trials running in both countries.
    assert body["visualization"]["metadata"]["total_records"] == 33
    # the dimension's filter must NOT leak into the chart subtitle
    assert "country=" not in body["visualization"]["metadata"]["filters_applied"]


@respx.mock
async def test_comparison_with_one_entity_falls_back_to_bar(api, app):
    async def fake(_request):
        return QuerySpec(query_type=QueryType.COMPARISON, comparison_entities=["China"])

    app.dependency_overrides[get_interpreter] = lambda: fake
    respx.get(url__startswith=settings.clinicaltrials_base_url).mock(
        return_value=Response(200, json={"totalCount": 1, "studies": [SAMPLE_STUDY]})
    )
    resp = await api.post("/api/query", json={"query": "China trials"})
    body = resp.json()
    assert body["visualization"]["type"] == "bar"  # valid single-series shape, not grouped_bar
    assert all("x" in pt and "y" in pt for pt in body["visualization"]["data"])
    # The silent downgrade is now surfaced as a caveat.
    assert "single-series distribution" in (body["visualization"]["metadata"]["data_caveat"] or "")


@respx.mock
async def test_comparison_backfills_citations_for_unsampled_bucket(api, app):
    # Entity 'a' has a bucket (Phase 3) that its sample never surfaced but that exact-counts > 0 —
    # its citation NCT IDs must be backfilled so the datum stays traceable (not left empty).
    def handler(request):
        p = request.url.params
        entity = p.get("query.intr", "")
        page_size = p.get("pageSize")
        adv = p.get("filter.advanced", "")
        if page_size == "1":  # exact count (per-bucket or per-entity total) -> non-zero
            return Response(200, json={"totalCount": 5, "studies": []})
        if "AREA[Phase]" in adv:  # fetch_sample backfill (pageSize == citation limit)
            return Response(200, json={"totalCount": 5, "studies": [_study(nct="NCT00009999")]})
        # main sample: 'a' only has Phase 2, 'b' has Phase 2 + Phase 3
        if entity == "a":
            return Response(200, json={"totalCount": 50, "studies": [_study(nct="NCTA", phases=("PHASE2",))]})
        return Response(200, json={"totalCount": 50, "studies": [_study(nct="NCTB")]})

    async def fake(_request):
        return QuerySpec(
            query_type=QueryType.COMPARISON,
            comparison_entities=["a", "b"],
            comparison_dimension="intervention",
        )

    app.dependency_overrides[get_interpreter] = lambda: fake
    respx.get(url__startswith=settings.clinicaltrials_base_url).mock(side_effect=handler)
    resp = await api.post("/api/query", json={"query": "compare a vs b"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    cite = {c["bucket"]: c for c in body["citations"]}
    # 'a · Phase 3' was never in a's sample, but its citation was backfilled.
    assert cite["a · Phase 3"]["value"] == 5
    assert cite["a · Phase 3"]["nct_ids"] == ["NCT00009999"]


@respx.mock
async def test_event_permalink_roundtrip(api):
    respx.get(url__startswith=settings.clinicaltrials_base_url).mock(
        return_value=Response(200, json={"totalCount": 1, "studies": [SAMPLE_STUDY]})
    )
    resp = await api.post("/api/query", json={"query": "diabetes trials per year"})
    body = resp.json()
    event_id = body["event_id"]
    assert event_id

    saved = await api.get(f"/api/events/{event_id}")
    assert saved.status_code == 200
    data = saved.json()
    assert data["event_id"] == event_id
    assert data["query"] == body["query"]
    assert data["visualization"]["type"] == body["visualization"]["type"]


async def test_event_not_found_returns_404(api):
    resp = await api.get("/api/events/nope")
    assert resp.status_code == 404


async def test_blank_query_returns_422(api):
    resp = await api.post("/api/query", json={"query": "  "})
    assert resp.status_code == 422


async def test_agent_failure_returns_503(api, app):
    async def boom(_request):
        raise RuntimeError("invalid api key")

    app.dependency_overrides[get_interpreter] = lambda: boom
    resp = await api.post("/api/query", json={"query": "diabetes trials by phase"})
    assert resp.status_code == 503
    assert resp.json()["error"] == "agent_error"


@respx.mock
async def test_upstream_failure_returns_502(api):
    # The default interpreter (conftest) is a supported time_trend query, so the gate passes and
    # the pipeline reaches the upstream fetch — which fails with a 5xx -> UpstreamError -> HTTP 502.
    respx.get(url__startswith=settings.clinicaltrials_base_url).mock(return_value=Response(503))
    resp = await api.post("/api/query", json={"query": "diabetes trials per year"})
    assert resp.status_code == 502
    assert resp.json()["error"] == "upstream_error"


@respx.mock
async def test_comparison_year_breakdown(api, app):
    counts = {("a", "2019"): 5, ("a", "2020"): 7, ("b", "2019"): 2, ("b", "2020"): 9}

    def handler(request):
        p = request.url.params
        entity = p.get("query.intr", "")
        adv = p.get("filter.advanced", "")
        if "AREA[StartDate]RANGE[" in adv:
            year = adv.split("RANGE[")[1][:4]
            return Response(200, json={"totalCount": counts.get((entity, year), 0), "studies": []})
        if p.get("pageSize") == "1":
            return Response(200, json={"totalCount": sum(v for (e, _), v in counts.items() if e == entity), "studies": []})
        return Response(200, json={"totalCount": 999, "studies": [_study(year="2019"), _study(nct="NCT00000002", year="2020")]})

    async def fake(_request):
        from app.schemas.query import GroupBy
        return QuerySpec(
            query_type=QueryType.COMPARISON,
            comparison_entities=["a", "b"],
            comparison_dimension="intervention",
            group_by=GroupBy.YEAR,
        )

    app.dependency_overrides[get_interpreter] = lambda: fake
    respx.get(url__startswith=settings.clinicaltrials_base_url).mock(side_effect=handler)
    resp = await api.post("/api/query", json={"query": "a vs b per year"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["visualization"]["metadata"]["chart_config"]["x_label"] == "Year"
    rows = {r["bucket"]: r for r in body["visualization"]["data"]}
    assert rows["2019"]["a"] == 5 and rows["2019"]["b"] == 2
    assert rows["2020"]["a"] == 7 and rows["2020"]["b"] == 9


@respx.mock
async def test_comparison_status_breakdown(api, app):
    counts = {("a", "RECRUITING"): 6, ("a", "COMPLETED"): 1, ("b", "RECRUITING"): 2, ("b", "COMPLETED"): 8}

    def handler(request):
        p = request.url.params
        entity = p.get("query.intr", "")
        ov = p.get("filter.overallStatus", "")
        if ov:
            return Response(200, json={"totalCount": counts.get((entity, ov), 0), "studies": []})
        if p.get("pageSize") == "1":
            return Response(200, json={"totalCount": sum(v for (e, _), v in counts.items() if e == entity), "studies": []})
        return Response(200, json={"totalCount": 999, "studies": [_study(status="RECRUITING"), _study(nct="NCT00000002", status="COMPLETED")]})

    async def fake(_request):
        from app.schemas.query import GroupBy
        return QuerySpec(
            query_type=QueryType.COMPARISON,
            comparison_entities=["a", "b"],
            comparison_dimension="intervention",
            group_by=GroupBy.STATUS,
        )

    app.dependency_overrides[get_interpreter] = lambda: fake
    respx.get(url__startswith=settings.clinicaltrials_base_url).mock(side_effect=handler)
    resp = await api.post("/api/query", json={"query": "a vs b by status"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["visualization"]["metadata"]["chart_config"]["x_label"] == "Status"
    rows = {r["bucket"]: r for r in body["visualization"]["data"]}
    assert rows["Recruiting"]["a"] == 6 and rows["Recruiting"]["b"] == 2
    assert rows["Completed"]["a"] == 1 and rows["Completed"]["b"] == 8


@respx.mock
async def test_comparison_exact_count_failure_falls_back_to_sample(api, app):
    # When a per-bucket count() fails upstream, that cell falls back to the entity's SAMPLE count
    # (a real lower bound) — not a misleading 0 — and the response is flagged as approximate.
    def handler(request):
        p = request.url.params
        entity = "China" if "China" in p.get("query.locn", "") else "United States"
        adv = p.get("filter.advanced", "")
        if "AREA[Phase]" in adv:
            if entity == "China" and "PHASE3" in adv:
                return Response(503)  # this single bucket's exact count fails (after retries)
            return Response(200, json={"totalCount": 11, "studies": []})
        if p.get("pageSize") == "1":
            return Response(200, json={"totalCount": 22, "studies": []})
        return Response(200, json={"totalCount": 999, "studies": [_study()]})  # sample: 1 study

    async def fake(_request):
        return QuerySpec(
            query_type=QueryType.COMPARISON,
            comparison_entities=["United States", "China"],
            comparison_dimension="country",
        )

    app.dependency_overrides[get_interpreter] = lambda: fake
    respx.get(url__startswith=settings.clinicaltrials_base_url).mock(side_effect=handler)
    resp = await api.post("/api/query", json={"query": "compare US and China trials"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    rows = {r["bucket"]: r for r in body["visualization"]["data"]}
    # China/Phase 3 fell back to its sample count (1 study), not 0; other buckets exact.
    assert rows["Phase 3"]["China"] == 1
    assert rows["Phase 2"]["China"] == 11
    meta = body["visualization"]["metadata"]
    assert meta["bucket_set_complete"] is False
    assert meta["data_caveat"] and "approximate" in meta["data_caveat"]


@respx.mock
async def test_time_trend_counts_reconcile_with_total(api, app):
    # Reconciliation: the sum of per-year exact counts must equal the reported total_records
    # (the property the README claims). Verified through the real HTTP -> exact-count path.
    from app.schemas.query import GroupBy

    year_counts = {"2015": 4, "2016": 6, "2017": 5}
    total = sum(year_counts.values())  # 15

    def handler(request):
        p = request.url.params
        adv = p.get("filter.advanced", "")
        if p.get("pageSize") == "1" and "RANGE[" in adv:  # per-year exact count
            year = adv.split("RANGE[")[1][:4]
            return Response(200, json={"totalCount": year_counts.get(year, 0), "studies": []})
        # main sample: a couple of studies per year so every year is discovered
        studies = [
            _study(nct=f"NCT{y}{i:04d}", year=y) for y in year_counts for i in range(2)
        ]
        return Response(200, json={"totalCount": total, "studies": studies})

    async def fake(_request):
        return QuerySpec(
            query_type=QueryType.TIME_TREND, condition="x", start_year=2015, group_by=GroupBy.YEAR
        )

    app.dependency_overrides[get_interpreter] = lambda: fake
    respx.get(url__startswith=settings.clinicaltrials_base_url).mock(side_effect=handler)
    resp = await api.post("/api/query", json={"query": "trials per year"})
    assert resp.status_code == 200, resp.text
    viz = resp.json()["visualization"]
    assert sum(p["y"] for p in viz["data"]) == viz["metadata"]["total_records"] == total


def _network_study(nct: str, sponsor: str = "Pfizer", drug: str = "Metformin") -> dict:
    return {
        "protocolSection": {
            "identificationModule": {"nctId": nct, "briefTitle": "T"},
            "sponsorCollaboratorsModule": {"leadSponsor": {"name": sponsor}},
            "armsInterventionsModule": {"interventions": [{"type": "DRUG", "name": drug}]},
        }
    }


def _scatter_study(nct: str, enroll: int = 100) -> dict:
    return {
        "protocolSection": {
            "identificationModule": {"nctId": nct, "briefTitle": "T"},
            "statusModule": {
                "startDateStruct": {"date": "2019-01"},
                "completionDateStruct": {"date": "2021-01"},
            },
            "designModule": {"enrollmentInfo": {"count": enroll}, "phases": ["PHASE2"]},
        }
    }


@respx.mock
async def test_relationship_flags_sampled_network(api, app):
    # Edge weights are computed over the fetched sample; when the population exceeds the sample,
    # the response must say so (bucket_set_complete False + an "edge weights" caveat).
    async def fake(_request):
        return QuerySpec(query_type=QueryType.RELATIONSHIP, condition="alzheimer")

    app.dependency_overrides[get_interpreter] = lambda: fake
    respx.get(url__startswith=settings.clinicaltrials_base_url).mock(
        return_value=Response(200, json={"totalCount": 500, "studies": [_network_study("NCT1")]})
    )
    resp = await api.post("/api/query", json={"query": "sponsor-drug network for alzheimer"})
    assert resp.status_code == 200, resp.text
    meta = resp.json()["visualization"]["metadata"]
    assert meta["sampled"] == 1 and meta["total_records"] == 500
    assert meta["bucket_set_complete"] is False
    assert meta["data_caveat"] and "edge weights" in meta["data_caveat"]


@respx.mock
async def test_relationship_no_caveat_when_fully_sampled(api, app):
    # When the whole population is fetched (sample == total), no sampling caveat.
    async def fake(_request):
        return QuerySpec(query_type=QueryType.RELATIONSHIP, condition="alzheimer")

    app.dependency_overrides[get_interpreter] = lambda: fake
    respx.get(url__startswith=settings.clinicaltrials_base_url).mock(
        return_value=Response(200, json={"totalCount": 1, "studies": [_network_study("NCT1")]})
    )
    resp = await api.post("/api/query", json={"query": "sponsor-drug network for alzheimer"})
    assert resp.status_code == 200, resp.text
    meta = resp.json()["visualization"]["metadata"]
    assert meta["bucket_set_complete"] is True
    assert meta["data_caveat"] is None


@respx.mock
async def test_correlation_flags_sampled_scatter(api, app):
    # A scatter over a capped fetch of a larger population must flag that its points are a sample.
    async def fake(_request):
        return QuerySpec(query_type=QueryType.CORRELATION, condition="diabetes")

    app.dependency_overrides[get_interpreter] = lambda: fake
    respx.get(url__startswith=settings.clinicaltrials_base_url).mock(
        return_value=Response(200, json={"totalCount": 500, "studies": [_scatter_study("NCT1")]})
    )
    resp = await api.post("/api/query", json={"query": "enrollment vs duration for diabetes"})
    assert resp.status_code == 200, resp.text
    meta = resp.json()["visualization"]["metadata"]
    assert meta["sampled"] == 1 and meta["total_records"] == 500
    assert meta["bucket_set_complete"] is False
    assert meta["data_caveat"] and "capped sample" in meta["data_caveat"]
