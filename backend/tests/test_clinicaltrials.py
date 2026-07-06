from __future__ import annotations

import pytest
import respx
from httpx import Response

from app.clients.clinicaltrials import (
    ClinicalTrialsClient,
    build_params,
    intervention_type_token,
    normalize_study,
)
from app.config import settings
from app.errors import UpstreamError
from app.schemas.query import GroupBy, QuerySpec, QueryType, StudyType

from .conftest import SAMPLE_STUDY

_SPEC = QuerySpec(query_type=QueryType.DISTRIBUTION, condition="diabetes")
_BASE = settings.clinicaltrials_base_url


@respx.mock
async def test_search_retries_transient_then_succeeds():
    route = respx.get(url__startswith=_BASE).mock(
        side_effect=[Response(503), Response(200, json={"totalCount": 1, "studies": [SAMPLE_STUDY]})]
    )
    async with ClinicalTrialsClient() as client:
        records, total = await client.search(_SPEC)
    assert total == 1 and len(records) == 1
    assert route.call_count == 2  # retried the 503 once, then succeeded


@respx.mock
async def test_count_fails_fast_on_4xx_without_retry():
    route = respx.get(url__startswith=_BASE).mock(return_value=Response(400))
    async with ClinicalTrialsClient() as client:
        with pytest.raises(UpstreamError) as exc:
            await client.count(_SPEC)
    assert exc.value.status_code == 400
    assert route.call_count == 1  # 4xx is not retried


@respx.mock
async def test_retry_after_honored_on_429():
    route = respx.get(url__startswith=_BASE).mock(
        side_effect=[
            Response(429, headers={"retry-after": "0"}),
            Response(200, json={"totalCount": 7, "studies": []}),
        ]
    )
    async with ClinicalTrialsClient() as client:
        assert await client.count(_SPEC) == 7
    assert route.call_count == 2


@respx.mock
async def test_malformed_json_raises_upstream_error():
    respx.get(url__startswith=_BASE).mock(return_value=Response(200, content=b"<html>nope</html>"))
    async with ClinicalTrialsClient() as client:
        with pytest.raises(UpstreamError):
            await client.count(_SPEC)


def _study_min(nct):
    return {"protocolSection": {"identificationModule": {"nctId": nct, "briefTitle": "t"}}}


@respx.mock
async def test_search_never_overshoots_max_records():
    # 3 studies per page, cap of 5 -> the loop must stop at exactly 5, not 6.
    page = {
        "totalCount": 9,
        "studies": [_study_min(f"NCT{i:08d}") for i in range(3)],
        "nextPageToken": "more",
    }
    respx.get(url__startswith=_BASE).mock(return_value=Response(200, json=page))
    async with ClinicalTrialsClient(page_size=3, max_records=5) as client:
        records, _ = await client.search(_SPEC)
    assert len(records) == 5


def test_normalize_study_extracts_fields():
    rec = normalize_study(SAMPLE_STUDY)
    assert rec is not None
    assert rec.nct_id == "NCT00000001"
    assert rec.title == "A Diabetes Trial"
    assert rec.overall_status == "RECRUITING"
    assert rec.study_type == "INTERVENTIONAL"
    assert rec.phases == ["Phase 2", "Phase 3"]
    assert rec.start_year == 2019
    assert rec.conditions == ["Diabetes Mellitus"]
    assert rec.interventions == [{"type": "DRUG", "name": "Metformin"}]
    assert rec.lead_sponsor == "Acme Labs"
    assert rec.countries == ["United States", "Canada"]
    assert rec.enrollment == 100
    assert rec.completion_date == "2021-04"
    assert rec.duration_months == 24  # 2019-04 -> 2021-04


def test_build_params_maps_phase_filter():
    spec = QuerySpec(query_type=QueryType.DISTRIBUTION, condition="diabetes", phase="Phase 3")
    params = build_params(spec, page_size=50)
    assert "AREA[Phase]PHASE3" in params["filter.advanced"]


def test_build_params_projects_fields_for_search_but_not_count():
    spec = QuerySpec(query_type=QueryType.DISTRIBUTION, condition="diabetes")
    # A record search restricts the payload to the leaves normalize_study reads.
    search = build_params(spec, page_size=50)
    assert "fields" in search
    fields = search["fields"].split(",")
    assert "protocolSection.identificationModule.nctId" in fields
    assert "protocolSection.contactsLocationsModule.locations.country" in fields
    # A count query pulls no records, so it omits the projection.
    count = build_params(spec, page_size=1, project=False)
    assert "fields" not in count


def test_intervention_type_token_allowlists():
    assert intervention_type_token("Drug") == "DRUG"
    assert intervention_type_token("dietary supplement") == "DIETARY_SUPPLEMENT"
    assert intervention_type_token("bogus") is None
    assert intervention_type_token("Drug] OR AREA[Phase]PHASE3") is None  # injection -> rejected


def test_build_params_sanitizes_intervention_type():
    # Valid type -> emitted as a safe token.
    ok = build_params(
        QuerySpec(query_type=QueryType.DISTRIBUTION, condition="x", intervention_type="Drug"), 50
    )
    assert "AREA[InterventionType]DRUG" in ok["filter.advanced"]

    # Injection attempt -> dropped entirely, never interpolated into the Essie string.
    evil = build_params(
        QuerySpec(
            query_type=QueryType.DISTRIBUTION,
            condition="x",
            intervention_type="Drug] OR AREA[Phase]PHASE3",
        ),
        50,
    )
    assert "InterventionType" not in evil.get("filter.advanced", "")
    assert "OR AREA[Phase]" not in evil.get("filter.advanced", "")


def test_normalize_study_without_nct_returns_none():
    assert normalize_study({"protocolSection": {}}) is None


def test_build_params_maps_filters():
    spec = QuerySpec(
        query_type=QueryType.TIME_TREND,
        condition="breast cancer",
        intervention="pembrolizumab",
        sponsor="Mayo Clinic",
        study_type=StudyType.INTERVENTIONAL,
        country="United States",
        status=["recruiting"],
        start_year=2015,
        group_by=GroupBy.YEAR,
    )
    params = build_params(spec, page_size=100)
    assert params["query.cond"] == "breast cancer"
    assert params["query.intr"] == "pembrolizumab"
    assert params["query.spons"] == "Mayo Clinic"
    assert params["query.locn"] == "United States"
    assert params["filter.overallStatus"] == "RECRUITING"
    assert "AREA[StudyType]INTERVENTIONAL" in params["filter.advanced"]
    assert "AREA[StartDate]RANGE[2015-01-01,MAX]" in params["filter.advanced"]
    assert params["pageSize"] == 100
    assert params["countTotal"] == "true"
