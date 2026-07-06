"""Repository abstraction over persistence.

`SqlAlchemyRepository` is used at runtime; `InMemoryRepository` lets tests run the
full request path without a Postgres instance.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..clients.clinicaltrials import TrialRecord
from ..schemas.visualization import Citation
from .models import CitationRecord, EventRecord, QueryRecord, SearchCache, TrialCache

_TRIAL_COLS = [
    "title",
    "overall_status",
    "study_type",
    "phases",
    "start_date",
    "start_year",
    "conditions",
    "interventions",
    "lead_sponsor",
    "countries",
    "enrollment",
    "completion_date",
    "duration_months",
]


class Repository(ABC):
    @abstractmethod
    async def upsert_trials(self, records: list[TrialRecord]) -> None: ...

    @abstractmethod
    async def get_trials_by_ids(self, nct_ids: list[str]) -> list[TrialRecord]: ...

    @abstractmethod
    async def get_cached_search(self, cache_key: str) -> dict[str, Any] | None: ...

    @abstractmethod
    async def save_cached_search(self, cache_key: str, nct_ids: list[str], total: int) -> None: ...

    @abstractmethod
    async def save_query(self, **fields: Any) -> int: ...

    @abstractmethod
    async def save_citations(self, query_id: int, citations: list[Citation]) -> None: ...

    @abstractmethod
    async def get_query(self, query_id: int) -> dict[str, Any] | None: ...

    @abstractmethod
    async def list_queries(self, limit: int = 50) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def save_event(
        self, event_id: str, query: str, response_json: dict[str, Any]
    ) -> None: ...

    @abstractmethod
    async def get_event(self, event_id: str) -> dict[str, Any] | None: ...


class SqlAlchemyRepository(Repository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        # A single AsyncSession is NOT safe for concurrent use. The comparison path fans out
        # cached_search() across entities with asyncio.gather, so guard every session access
        # with a per-request lock to serialize it (network fetches still overlap between calls).
        self._lock = asyncio.Lock()

    async def upsert_trials(self, records: list[TrialRecord]) -> None:
        if not records:
            return
        # Dedupe by nct_id: a single INSERT ... ON CONFLICT cannot touch a row twice
        # (comparison queries fetch overlapping result sets).
        unique = list({r.nct_id: r for r in records}.values())
        values = [{"nct_id": r.nct_id, **{c: getattr(r, c) for c in _TRIAL_COLS}} for r in unique]
        stmt = insert(TrialCache).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["nct_id"],
            set_={col: getattr(stmt.excluded, col) for col in _TRIAL_COLS},
        )
        async with self._lock:
            await self.session.execute(stmt)
            await self.session.commit()

    async def get_trials_by_ids(self, nct_ids: list[str]) -> list[TrialRecord]:
        if not nct_ids:
            return []
        async with self._lock:
            result = await self.session.execute(
                select(TrialCache).where(TrialCache.nct_id.in_(nct_ids))
            )
            return [_trial_to_record(row) for row in result.scalars().all()]

    async def get_cached_search(self, cache_key: str) -> dict[str, Any] | None:
        async with self._lock:
            row = await self.session.get(SearchCache, cache_key)
        if row is None:
            return None
        return {"nct_ids": row.nct_ids, "total": row.total, "fetched_at": row.fetched_at}

    async def save_cached_search(self, cache_key: str, nct_ids: list[str], total: int) -> None:
        stmt = insert(SearchCache).values(cache_key=cache_key, nct_ids=nct_ids, total=total)
        stmt = stmt.on_conflict_do_update(
            index_elements=["cache_key"],
            set_={
                "nct_ids": stmt.excluded.nct_ids,
                "total": stmt.excluded.total,
                "fetched_at": func.now(),
            },
        )
        async with self._lock:
            await self.session.execute(stmt)
            await self.session.commit()

    async def save_query(self, **fields: Any) -> int:
        row = QueryRecord(**fields)
        async with self._lock:
            self.session.add(row)
            await self.session.commit()
            await self.session.refresh(row)
        return row.id

    async def save_citations(self, query_id: int, citations: list[Citation]) -> None:
        async with self._lock:
            for c in citations:
                self.session.add(
                    CitationRecord(
                        query_id=query_id, bucket=c.bucket, value=c.value, nct_ids=c.nct_ids
                    )
                )
            await self.session.commit()

    async def get_query(self, query_id: int) -> dict[str, Any] | None:
        async with self._lock:
            row = await self.session.get(QueryRecord, query_id)
        return _query_to_dict(row) if row else None

    async def list_queries(self, limit: int = 50) -> list[dict[str, Any]]:
        async with self._lock:
            result = await self.session.execute(
                select(QueryRecord).order_by(QueryRecord.id.desc()).limit(limit)
            )
            return [_query_to_dict(row) for row in result.scalars().all()]

    async def save_event(self, event_id: str, query: str, response_json: dict[str, Any]) -> None:
        async with self._lock:
            self.session.add(
                EventRecord(event_id=event_id, query=query, response_json=response_json)
            )
            await self.session.commit()

    async def get_event(self, event_id: str) -> dict[str, Any] | None:
        async with self._lock:
            row = await self.session.get(EventRecord, event_id)
        return row.response_json if row else None


class InMemoryRepository(Repository):
    """Test/dev double — no database required."""

    def __init__(self) -> None:
        self.trials: dict[str, TrialRecord] = {}
        self.queries: list[dict[str, Any]] = []
        self.citations: dict[int, list[Citation]] = {}
        self.events: dict[str, dict[str, Any]] = {}
        self.search_cache: dict[str, dict[str, Any]] = {}
        self._next_id = 1

    async def upsert_trials(self, records: list[TrialRecord]) -> None:
        for r in records:
            self.trials[r.nct_id] = r

    async def get_trials_by_ids(self, nct_ids: list[str]) -> list[TrialRecord]:
        return [self.trials[n] for n in nct_ids if n in self.trials]

    async def get_cached_search(self, cache_key: str) -> dict[str, Any] | None:
        return self.search_cache.get(cache_key)

    async def save_cached_search(self, cache_key: str, nct_ids: list[str], total: int) -> None:
        self.search_cache[cache_key] = {
            "nct_ids": nct_ids,
            "total": total,
            "fetched_at": datetime.now(UTC),
        }

    async def save_query(self, **fields: Any) -> int:
        qid = self._next_id
        self._next_id += 1
        self.queries.append({"id": qid, **fields})
        return qid

    async def save_citations(self, query_id: int, citations: list[Citation]) -> None:
        self.citations[query_id] = citations

    async def get_query(self, query_id: int) -> dict[str, Any] | None:
        return next((q for q in self.queries if q["id"] == query_id), None)

    async def list_queries(self, limit: int = 50) -> list[dict[str, Any]]:
        return list(reversed(self.queries))[:limit]

    async def save_event(self, event_id: str, query: str, response_json: dict[str, Any]) -> None:
        self.events[event_id] = response_json

    async def get_event(self, event_id: str) -> dict[str, Any] | None:
        return self.events.get(event_id)


def _trial_to_record(row: TrialCache) -> TrialRecord:
    return TrialRecord(nct_id=row.nct_id, **{c: getattr(row, c) for c in _TRIAL_COLS})


def _query_to_dict(row: QueryRecord) -> dict[str, Any]:
    return {
        "id": row.id,
        "raw_query": row.raw_query,
        "parsed_parameters": row.parsed_parameters,
        "query_type": row.query_type,
        "supported": row.supported,
        "rejection_reason": row.rejection_reason,
        "chart_type": row.chart_type,
        "total_records": row.total_records,
        "latency_ms": row.latency_ms,
        "model": row.model,
        "trace_id": row.trace_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
