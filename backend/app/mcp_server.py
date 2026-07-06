"""MCP server: exposes the query agent as Model Context Protocol tools.

A thin stdio wrapper over the running HTTP API — the same `POST /api/query`
contract the React UI consumes — so MCP clients (Claude Code, Claude Desktop,
any MCP-capable agent) can ask natural-language questions about clinical
trials and get back structured, cited results.

Run it (the backend API must be up first, e.g. `make up` or `make dev`):

    cd backend && uv run --extra mcp python -m app.mcp_server

Or let an MCP client launch it via the repo-root `.mcp.json`.

Configuration (env vars):
    QTOV_API_URL  backend base URL   (default http://localhost:8000)
    QTOV_UI_URL   UI base URL, used to build shareable permalinks
                  (default http://localhost:5173)
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

QTOV_API_URL = os.environ.get("QTOV_API_URL", "http://localhost:8000")
QTOV_UI_URL = os.environ.get("QTOV_UI_URL", "http://localhost:5173")

# /api/query runs two LLM calls plus ClinicalTrials.gov fetches on a cold cache.
REQUEST_TIMEOUT_S = 120.0

# Keep tool output compact: cap the per-data-point source trials we echo back.
# The full trail is always available at the permalink.
MAX_TRIALS_PER_CITATION = 5

mcp = FastMCP(
    "qtov",
    instructions=(
        "Query ClinicalTrials.gov in natural language and get back a structured, "
        "cited result: an interpretation, aggregated chart data, and per-data-point "
        "citations tracing every value to the trials (NCT IDs) that produced it."
    ),
)


def shape_success(payload: dict[str, Any]) -> dict[str, Any]:
    """Trim a QueryResponse body to a compact, model-friendly result."""
    interpretation = payload.get("interpretation", {})
    viz = payload.get("visualization", {})
    meta = viz.get("metadata", {})
    event_id = payload.get("event_id")
    return {
        "supported": True,
        "summary": payload.get("summary", ""),
        "interpretation": {
            "query_type": interpretation.get("query_type"),
            "reasoning": interpretation.get("reasoning"),
            "confidence": interpretation.get("confidence"),
            "parameters": interpretation.get("parameters"),
        },
        "chart": {
            "type": viz.get("type"),
            "title": viz.get("title"),
            "data": viz.get("data"),
            "total_records": meta.get("total_records"),
            "filters_applied": meta.get("filters_applied"),
            "data_caveat": meta.get("data_caveat"),
        },
        "citations": [
            {
                "bucket": c.get("bucket"),
                "value": c.get("value"),
                "trial_count": len(c.get("nct_ids", [])),
                "trials": [
                    {key: trial.get(key) for key in ("nct_id", "title", "url", "excerpt")}
                    for trial in c.get("trials", [])[:MAX_TRIALS_PER_CITATION]
                ],
            }
            for c in payload.get("citations", [])
        ],
        "permalink": f"{QTOV_UI_URL}/{event_id}" if event_id else None,
    }


def shape_unsupported(payload: dict[str, Any]) -> dict[str, Any]:
    """Shape the 422 unsupported-query body into actionable tool output.

    Returned (not raised) so the calling model sees WHY the query was rejected
    and which query types it can rephrase into.
    """
    return {
        "supported": False,
        "message": payload.get("message", "Query type not supported."),
        "supported_query_types": payload.get("supported_query_types", []),
    }


def _raise_for_error(response: httpx.Response) -> None:
    """Convert structured API errors (502 upstream / 503 agent) into tool errors."""
    if response.status_code in (502, 503):
        body = response.json()
        raise RuntimeError(f"{body.get('error', 'error')}: {body.get('message', '')}")
    response.raise_for_status()


@mcp.tool()
async def query_clinical_trials(
    query: str,
    condition: str | None = None,
    intervention: str | None = None,
    phase: str | None = None,
    country: str | None = None,
    sponsor: str | None = None,
    status: list[str] | None = None,
    start_year: int | None = None,
    end_year: int | None = None,
) -> dict[str, Any]:
    """Ask a natural-language question about ClinicalTrials.gov data.

    Supported analyses: time trends, phase/status distributions, drug or country
    comparisons, geographic breakdowns, sponsor-drug relationship networks, and
    enrollment/duration correlations. Every data point in the result carries
    citations back to the source trials (NCT IDs with supporting excerpts).

    The optional filters are authoritative: when set, they override whatever the
    agent infers from the prose (e.g. phase='Phase 3', country='United States',
    status=['RECRUITING']). If the query is outside the supported set, the result
    has supported=false plus the list of query types to rephrase into.
    """
    body: dict[str, Any] = {"query": query}
    filters = {
        "condition": condition,
        "intervention": intervention,
        "phase": phase,
        "country": country,
        "sponsor": sponsor,
        "status": status,
        "start_year": start_year,
        "end_year": end_year,
    }
    body.update({k: v for k, v in filters.items() if v is not None})

    async with httpx.AsyncClient(base_url=QTOV_API_URL, timeout=REQUEST_TIMEOUT_S) as client:
        try:
            response = await client.post("/api/query", json=body)
        except httpx.ConnectError as exc:
            raise RuntimeError(
                f"qtov backend not reachable at {QTOV_API_URL} — start it with `make up`"
            ) from exc

    if response.status_code == 422:
        payload = response.json()
        if payload.get("error") == "unsupported_query":
            return shape_unsupported(payload)
        raise RuntimeError(f"invalid request: {payload.get('detail')}")
    _raise_for_error(response)
    return shape_success(response.json())


@mcp.tool()
async def get_saved_result(event_id: str) -> dict[str, Any]:
    """Fetch a previously saved query result by its shareable event_id."""
    async with httpx.AsyncClient(base_url=QTOV_API_URL, timeout=30.0) as client:
        try:
            response = await client.get(f"/api/events/{event_id}")
        except httpx.ConnectError as exc:
            raise RuntimeError(
                f"qtov backend not reachable at {QTOV_API_URL} — start it with `make up`"
            ) from exc
    if response.status_code == 404:
        raise RuntimeError(f"no saved result for event_id {event_id!r}")
    _raise_for_error(response)
    payload = response.json()
    # Rejected queries are persisted too — their saved body is the 422 shape.
    if payload.get("error") == "unsupported_query":
        return shape_unsupported(payload)
    return shape_success(payload)


if __name__ == "__main__":
    mcp.run()  # stdio transport
