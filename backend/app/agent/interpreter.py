"""Pydantic AI interpretation step: NL query -> validated QuerySpec (structured output)."""

from __future__ import annotations

import re

from pydantic_ai import Agent

from ..config import settings
from ..schemas.query import GroupBy, QueryRequest, QuerySpec, QueryType
from .llm import run_structured
from .prompts import SYSTEM_PROMPT

# Deterministic breakdown-axis hints for comparison queries (a safety net for when the
# model defaults to phase despite an explicit "per year" / "by status" in the text).
_YEAR_BREAKDOWN = re.compile(r"\b(per year|by year|over time|annually?|each year|yearly)\b", re.I)
_STATUS_BREAKDOWN = re.compile(r"\b(by status|recruiting status|by recruitment)\b", re.I)


def infer_comparison_breakdown(query: str) -> GroupBy | None:
    if _YEAR_BREAKDOWN.search(query):
        return GroupBy.YEAR
    if _STATUS_BREAKDOWN.search(query):
        return GroupBy.STATUS
    return None

# Keyword signals per query type — a deterministic safety net for ambiguity the LLM
# may be overconfident about. Geographic/relationship patterns are deliberately strict
# so a mere country filter (e.g. "US trials") isn't mistaken for a geographic breakdown.
_SIGNALS: list[tuple[QueryType, re.Pattern[str]]] = [
    (QueryType.COMPARISON, re.compile(r"\b(vs\.?|versus|compare|compared to)\b", re.I)),
    (
        QueryType.TIME_TREND,
        re.compile(r"\b(per year|over time|since \d{4}|by year|annual|trend)\b", re.I),
    ),
    (
        QueryType.GEOGRAPHIC,
        re.compile(r"\b(which countr\w+|by country|across countries|geograph\w+)\b", re.I),
    ),
    (QueryType.RELATIONSHIP, re.compile(r"\b(network|relationship between|map of)\b", re.I)),
    (
        QueryType.CORRELATION,
        re.compile(r"\b(enrollment|enrolment|duration|correlat\w+|vs\.? duration)\b", re.I),
    ),
    (
        QueryType.DISTRIBUTION,
        re.compile(r"\b(across phases|by phase|distribution|breakdown)\b", re.I),
    ),
]


def signal_alternatives(query: str, chosen: QueryType) -> list[QueryType]:
    """Competing intents present in the text; only when 2+ distinct signals appear."""
    present = [qt for qt, rx in _SIGNALS if rx.search(query)]
    if len(set(present)) < 2:
        return []
    return [qt for qt in present if qt != chosen]


def _user_prompt(request: QueryRequest) -> str:
    lines = [f"Question: {request.query}"]
    hints: list[str] = []
    if request.condition:
        hints.append(f"condition={request.condition}")
    if request.intervention:
        hints.append(f"intervention={request.intervention}")
    if request.study_type:
        hints.append(f"study_type={request.study_type.value}")
    if request.intervention_type:
        hints.append(f"intervention_type={request.intervention_type}")
    if request.sponsor:
        hints.append(f"sponsor={request.sponsor}")
    if request.country:
        hints.append(f"country={request.country}")
    if request.phase:
        hints.append(f"phase={request.phase}")
    if request.status:
        hints.append(f"status={','.join(request.status)}")
    if request.start_year:
        hints.append(f"start_year={request.start_year}")
    if request.end_year:
        hints.append(f"end_year={request.end_year}")
    if request.date_range and request.date_range.from_:
        hints.append(f"date_from={request.date_range.from_}")
    if request.date_range and request.date_range.to:
        hints.append(f"date_to={request.date_range.to}")
    if hints:
        lines.append("Caller-provided filters (authoritative): " + ", ".join(hints))
    return "\n".join(lines)


def _year_of(value: str) -> int | None:
    head = value.strip()[:4]
    return int(head) if head.isdigit() else None


def apply_request_overrides(spec: QuerySpec, request: QueryRequest) -> QuerySpec:
    """Caller-provided structured filters win over the LLM's inference."""
    if request.condition:
        spec.condition = request.condition
    if request.intervention:
        spec.intervention = request.intervention
    if request.study_type is not None:
        spec.study_type = request.study_type
    if request.intervention_type:
        spec.intervention_type = request.intervention_type
    if request.sponsor:
        spec.sponsor = request.sponsor
    if request.country:
        spec.country = request.country
    if request.phase:
        spec.phase = request.phase
    if request.status:
        spec.status = request.status
    if request.start_year:
        spec.start_year = request.start_year
    if request.end_year:
        spec.end_year = request.end_year
    if request.date_range:
        if request.date_range.from_ and (year := _year_of(request.date_range.from_)):
            spec.start_year = year
        if request.date_range.to and (year := _year_of(request.date_range.to)):
            spec.end_year = year
    return spec


async def interpret(
    request: QueryRequest, agent: Agent[None, QuerySpec] | None = None
) -> QuerySpec:
    prompt = _user_prompt(request)
    if agent is not None:
        raw = (await agent.run(prompt)).output  # test/explicit-agent path
    else:
        raw = await run_structured(
            prompt,
            QuerySpec,
            models=settings.classifier_model_list,
            system_prompt=SYSTEM_PROMPT,
            name="classifier",
        )
    spec = apply_request_overrides(raw, request)

    # For comparisons, pin the breakdown axis from the text when the model left it on the
    # phase default but the user clearly asked for a per-year / by-status comparison.
    if spec.query_type == QueryType.COMPARISON and spec.group_by not in (
        GroupBy.YEAR,
        GroupBy.STATUS,
    ):
        if breakdown := infer_comparison_breakdown(request.query):
            spec.group_by = breakdown

    # Merge the LLM's alternatives with deterministic keyword signals.
    if spec.query_type != QueryType.UNSUPPORTED:
        extra = signal_alternatives(request.query, spec.query_type)
        spec.alternative_query_types = list(
            dict.fromkeys([*spec.alternative_query_types, *extra])
        )
        if spec.alternative_query_types and spec.confidence > 0.85:
            spec.confidence = 0.7  # reflect the ambiguity in the surfaced confidence

    if request.force_query_type and request.force_query_type != QueryType.UNSUPPORTED:
        # User picked an alternative chart: pin the type and let its defaults apply.
        spec.query_type = request.force_query_type
        spec.supported = True
        spec.group_by = None
        spec.alternative_query_types = []
        spec.confidence = 1.0
    return spec
