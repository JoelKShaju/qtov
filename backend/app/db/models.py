"""SQLAlchemy 2.0 models: query history, trial cache, search cache, citations, events.

Kept intentionally lean — only what the pipeline reads or writes.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class QueryRecord(Base):
    __tablename__ = "queries"

    id: Mapped[int] = mapped_column(primary_key=True)
    raw_query: Mapped[str] = mapped_column(String)
    parsed_parameters: Mapped[dict] = mapped_column(JSONB, default=dict)
    query_type: Mapped[str] = mapped_column(String(32))
    supported: Mapped[bool] = mapped_column(Boolean, default=True)
    rejection_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    chart_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    total_records: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    citations: Mapped[list[CitationRecord]] = relationship(
        back_populates="query", cascade="all, delete-orphan"
    )


class TrialCache(Base):
    __tablename__ = "trials"

    nct_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    title: Mapped[str] = mapped_column(String, default="")
    overall_status: Mapped[str | None] = mapped_column(String, nullable=True)
    study_type: Mapped[str | None] = mapped_column(String, nullable=True)
    phases: Mapped[list] = mapped_column(JSONB, default=list)
    start_date: Mapped[str | None] = mapped_column(String, nullable=True)
    start_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    conditions: Mapped[list] = mapped_column(JSONB, default=list)
    interventions: Mapped[list] = mapped_column(JSONB, default=list)
    lead_sponsor: Mapped[str | None] = mapped_column(String, nullable=True)
    countries: Mapped[list] = mapped_column(JSONB, default=list)
    enrollment: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_date: Mapped[str | None] = mapped_column(String, nullable=True)
    duration_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SearchCache(Base):
    """Read-through cache of a search's result set, keyed by a hash of the query params.

    Lets a repeated query skip the (paginated) ClinicalTrials.gov fetch + normalization:
    on a fresh hit the trial records are re-hydrated from `trials` by NCT id. Exact
    per-bucket counts are intentionally *not* cached — they stay live for accuracy.
    """

    __tablename__ = "search_cache"

    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    nct_ids: Mapped[list] = mapped_column(JSONB, default=list)
    total: Mapped[int] = mapped_column(Integer, default=0)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EventRecord(Base):
    """Full rendered response for a query, addressable by a shareable event_id."""

    __tablename__ = "events"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    query: Mapped[str] = mapped_column(String)
    response_json: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CitationRecord(Base):
    __tablename__ = "query_citations"

    id: Mapped[int] = mapped_column(primary_key=True)
    query_id: Mapped[int] = mapped_column(ForeignKey("queries.id", ondelete="CASCADE"))
    bucket: Mapped[str] = mapped_column(String)
    value: Mapped[float] = mapped_column(Float, default=0.0)
    nct_ids: Mapped[list] = mapped_column(JSONB, default=list)

    query: Mapped[QueryRecord] = relationship(back_populates="citations")
