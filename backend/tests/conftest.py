from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_interpreter, get_repository, get_summarizer
from app.db.repositories import InMemoryRepository
from app.main import create_app
from app.schemas.query import GroupBy, QueryRequest, QuerySpec, QueryType

SAMPLE_STUDY = {
    "protocolSection": {
        "identificationModule": {"nctId": "NCT00000001", "briefTitle": "A Diabetes Trial"},
        "statusModule": {
            "overallStatus": "RECRUITING",
            "startDateStruct": {"date": "2019-04"},
            "completionDateStruct": {"date": "2021-04"},
        },
        "designModule": {
            "studyType": "INTERVENTIONAL",
            "phases": ["PHASE2", "PHASE3"],
            "enrollmentInfo": {"count": 100},
        },
        "conditionsModule": {"conditions": ["Diabetes Mellitus"]},
        "armsInterventionsModule": {"interventions": [{"type": "DRUG", "name": "Metformin"}]},
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Acme Labs"}},
        "contactsLocationsModule": {"locations": [{"country": "United States"}, {"country": "Canada"}]},
    }
}


@pytest.fixture(autouse=True)
def _instant_retries():
    """Zero the upstream backoff so retry tests don't actually sleep."""
    from app.config import settings

    original = settings.upstream_backoff_base
    settings.upstream_backoff_base = 0.0
    yield
    settings.upstream_backoff_base = original


@pytest.fixture
def repo() -> InMemoryRepository:
    return InMemoryRepository()


@pytest.fixture
def app(repo: InMemoryRepository):
    application = create_app()

    async def fake_interpret(request: QueryRequest) -> QuerySpec:
        return QuerySpec(
            query_type=QueryType.TIME_TREND,
            condition="diabetes",
            start_year=2015,
            group_by=GroupBy.YEAR,
            title="Diabetes trials per year",
            reasoning="Counts trials per start year.",
        )

    async def fake_summarize(query, viz, citations):
        return "Stub summary citing sources."

    application.dependency_overrides[get_interpreter] = lambda: fake_interpret
    application.dependency_overrides[get_repository] = lambda: repo
    application.dependency_overrides[get_summarizer] = lambda: fake_summarize
    return application


@pytest.fixture
async def api(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
