from __future__ import annotations

from pydantic_ai.models.test import TestModel

from app.agent.interpreter import (
    apply_request_overrides,
    infer_comparison_breakdown,
    interpret,
    signal_alternatives,
)
from app.agent.llm import build_agent
from app.agent.prompts import SYSTEM_PROMPT
from app.schemas.query import DateRange, GroupBy, QueryRequest, QuerySpec, QueryType, StudyType


def test_request_overrides_take_precedence():
    spec = QuerySpec(query_type=QueryType.TIME_TREND, country="France", condition="cancer")
    request = QueryRequest(
        query="trials per year",
        condition="diabetes",
        drug_name="metformin",
        sponsor="Pfizer",
        study_type=StudyType.INTERVENTIONAL,
        country="Canada",
        trial_phase="Phase 3",
        start_year=2016,
        date_range=DateRange.model_validate({"from": "2015", "to": "2020-06"}),
    )
    out = apply_request_overrides(spec, request)
    assert out.study_type == StudyType.INTERVENTIONAL
    assert out.country == "Canada"  # caller override wins over the LLM's "France"
    assert out.condition == "diabetes"  # caller override wins over the LLM's "cancer"
    assert out.intervention == "metformin"  # drug_name alias maps to intervention
    assert out.sponsor == "Pfizer"
    assert out.phase == "Phase 3"  # trial_phase alias maps to phase
    # date_range is applied after the explicit start_year, so its 2015 wins as the final word
    assert out.start_year == 2015
    assert out.end_year == 2020


def test_infer_comparison_breakdown_from_text():
    assert infer_comparison_breakdown("metformin vs semaglutide per year") == GroupBy.YEAR
    assert infer_comparison_breakdown("compare A vs B by status") == GroupBy.STATUS
    assert infer_comparison_breakdown("compare phases for A vs B") is None


def test_signal_alternatives_detects_competing_intents():
    # "vs" (comparison) + "per year" (time_trend) -> both signals present
    alts = signal_alternatives("metformin vs semaglutide trials per year", QueryType.COMPARISON)
    assert alts == [QueryType.TIME_TREND]


def test_signal_alternatives_quiet_when_single_intent():
    assert signal_alternatives("diabetes trials across phases", QueryType.DISTRIBUTION) == []
    # a country filter alone is not a geographic-breakdown signal
    assert signal_alternatives("US diabetes trials by phase", QueryType.DISTRIBUTION) == []


async def test_force_query_type_overrides_classification():
    agent = build_agent(QuerySpec, model=TestModel(), system_prompt=SYSTEM_PROMPT, name="classifier")
    request = QueryRequest(query="diabetes trials", force_query_type=QueryType.COMPARISON)
    spec = await interpret(request, agent=agent)
    assert spec.query_type == QueryType.COMPARISON
    assert spec.supported is True
