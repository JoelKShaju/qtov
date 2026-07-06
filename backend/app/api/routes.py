"""HTTP routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ..agent.orchestrator import run_query
from ..clients.clinicaltrials import ClinicalTrialsClient
from ..db.repositories import Repository
from ..ratelimit import rate_limit
from ..schemas.query import QueryRequest
from ..schemas.visualization import QueryResponse
from .deps import (
    InterpretFn,
    SummarizeFn,
    get_client,
    get_interpreter,
    get_repository,
    get_summarizer,
)

router = APIRouter(prefix="/api", tags=["queries"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "qtov-backend", "version": "0.1.0"}


@router.post("/query", response_model=QueryResponse, dependencies=[Depends(rate_limit)])
async def post_query(
    request: QueryRequest,
    interpret_fn: InterpretFn = Depends(get_interpreter),
    client: ClinicalTrialsClient = Depends(get_client),
    repo: Repository = Depends(get_repository),
    summarize_fn: SummarizeFn = Depends(get_summarizer),
) -> QueryResponse:
    async with client:
        return await run_query(
            request,
            interpret_fn=interpret_fn,
            client=client,
            repo=repo,
            summarize_fn=summarize_fn,
        )


@router.get("/queries")
async def list_queries(
    limit: int = 50, repo: Repository = Depends(get_repository)
) -> list[dict[str, Any]]:
    return await repo.list_queries(limit=limit)


@router.get("/queries/{query_id}")
async def get_query(query_id: int, repo: Repository = Depends(get_repository)) -> dict[str, Any]:
    record = await repo.get_query(query_id)
    if record is None:
        raise HTTPException(status_code=404, detail="query not found")
    return record


@router.get("/events/{event_id}")
async def get_event(event_id: str, repo: Repository = Depends(get_repository)) -> dict[str, Any]:
    """Return the full saved result for a shareable event_id (powers the /<event_id> permalink)."""
    event = await repo.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")
    return event
