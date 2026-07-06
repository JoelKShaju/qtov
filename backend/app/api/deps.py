"""FastAPI dependency providers (overridable in tests)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..agent.interpreter import interpret as agent_interpret
from ..agent.summarize import summarize as agent_summarize
from ..clients.clinicaltrials import ClinicalTrialsClient
from ..db.repositories import Repository, SqlAlchemyRepository
from ..db.session import get_session
from ..schemas.query import QueryRequest, QuerySpec
from ..schemas.visualization import Citation, Visualization

InterpretFn = Callable[[QueryRequest], Awaitable[QuerySpec]]
SummarizeFn = Callable[[str, Visualization, list[Citation]], Awaitable[str]]


async def get_repository(session: AsyncSession = Depends(get_session)) -> Repository:
    return SqlAlchemyRepository(session)


def get_client() -> ClinicalTrialsClient:
    return ClinicalTrialsClient()


def get_interpreter() -> InterpretFn:
    return agent_interpret


def get_summarizer() -> SummarizeFn:
    return agent_summarize
