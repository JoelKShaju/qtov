from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

mcp_server = pytest.importorskip("app.mcp_server", reason="mcp extra not installed")

SUCCESS_PAYLOAD = {
    "event_id": "evt123",
    "query": "diabetes trials by phase",
    "interpretation": {
        "query_type": "distribution",
        "parameters": {"condition": "diabetes"},
        "reasoning": "Counts trials per phase.",
        "confidence": 0.95,
        "alternatives": [],
    },
    "visualization": {
        "type": "bar",
        "title": "Diabetes trials by phase",
        "data": [{"phase": "Phase 3", "count": 42}],
        "encoding": {},
        "metadata": {
            "total_records": 42,
            "filters_applied": "condition=diabetes",
            "data_caveat": None,
            "timestamp": "2026-01-01T00:00:00Z",
            "chart_config": {},
        },
    },
    "citations": [
        {
            "bucket": "Phase 3",
            "value": 42,
            "nct_ids": [f"NCT{i:08d}" for i in range(8)],
            "trials": [
                {
                    "nct_id": f"NCT{i:08d}",
                    "title": f"Trial {i}",
                    "url": f"https://clinicaltrials.gov/study/NCT{i:08d}",
                    "excerpt": "Phase: Phase 3",
                }
                for i in range(8)
            ],
        }
    ],
    "summary": "42 Phase 3 diabetes trials.",
}

UNSUPPORTED_PAYLOAD = {
    "error": "unsupported_query",
    "message": "Survival analysis is not supported.",
    "supported_query_types": [{"type": "time_trend", "example": "Trials per year?"}],
    "event_id": "evt456",
    "query": "plot survival curves",
}


def test_shape_success_is_compact_and_cited():
    shaped = mcp_server.shape_success(SUCCESS_PAYLOAD)
    assert shaped["supported"] is True
    assert shaped["summary"] == "42 Phase 3 diabetes trials."
    assert shaped["interpretation"]["query_type"] == "distribution"
    assert shaped["chart"]["type"] == "bar"
    assert shaped["chart"]["data"] == [{"phase": "Phase 3", "count": 42}]
    assert shaped["chart"]["total_records"] == 42
    citation = shaped["citations"][0]
    # trial_count reflects ALL backing trials; the echoed refs are capped.
    assert citation["trial_count"] == 8
    assert len(citation["trials"]) == mcp_server.MAX_TRIALS_PER_CITATION
    assert citation["trials"][0]["nct_id"] == "NCT00000000"
    assert shaped["permalink"].endswith("/evt123")


def test_shape_success_without_event_id_has_no_permalink():
    shaped = mcp_server.shape_success({**SUCCESS_PAYLOAD, "event_id": ""})
    assert shaped["permalink"] is None


def test_shape_unsupported_carries_guidance():
    shaped = mcp_server.shape_unsupported(UNSUPPORTED_PAYLOAD)
    assert shaped["supported"] is False
    assert "not supported" in shaped["message"]
    assert shaped["supported_query_types"][0]["type"] == "time_trend"


@respx.mock
async def test_query_tool_posts_filters_and_shapes_response():
    route = respx.post(f"{mcp_server.QTOV_API_URL}/api/query").mock(
        return_value=Response(200, json=SUCCESS_PAYLOAD)
    )
    result = await mcp_server.query_clinical_trials(
        "diabetes trials by phase", condition="diabetes", status=["RECRUITING"]
    )
    assert result["supported"] is True
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "query": "diabetes trials by phase",
        "condition": "diabetes",
        "status": ["RECRUITING"],
    }  # None filters are omitted, set ones pass through


@respx.mock
async def test_query_tool_returns_unsupported_guidance_on_422():
    respx.post(f"{mcp_server.QTOV_API_URL}/api/query").mock(
        return_value=Response(422, json=UNSUPPORTED_PAYLOAD)
    )
    result = await mcp_server.query_clinical_trials("plot survival curves")
    assert result["supported"] is False
    assert result["supported_query_types"]


@respx.mock
async def test_query_tool_surfaces_agent_errors():
    respx.post(f"{mcp_server.QTOV_API_URL}/api/query").mock(
        return_value=Response(503, json={"error": "agent_error", "message": "LLM unavailable"})
    )
    with pytest.raises(RuntimeError, match="agent_error: LLM unavailable"):
        await mcp_server.query_clinical_trials("diabetes trials by phase")


@respx.mock
async def test_get_saved_result_404():
    respx.get(f"{mcp_server.QTOV_API_URL}/api/events/nope").mock(return_value=Response(404))
    with pytest.raises(RuntimeError, match="no saved result"):
        await mcp_server.get_saved_result("nope")


@respx.mock
async def test_get_saved_result_returns_shaped_success():
    respx.get(f"{mcp_server.QTOV_API_URL}/api/events/evt123").mock(
        return_value=Response(200, json=SUCCESS_PAYLOAD)
    )
    result = await mcp_server.get_saved_result("evt123")
    assert result["supported"] is True and result["chart"]["type"] == "bar"
