"""Static catalog describing the closed set of supported query types.

This is the single source of truth for "what the agent can answer". It powers
both the capability gate's rejection payload and the LLM system prompt.
"""

from __future__ import annotations

SUPPORTED_QUERY_TYPES: list[dict[str, str]] = [
    {
        "type": "time_trend",
        "chart": "line",
        "example": "How has the number of trials for pembrolizumab changed per year since 2015?",
    },
    {
        "type": "distribution",
        "chart": "bar",
        "example": "How are diabetes trials distributed across phases?",
    },
    {
        "type": "comparison",
        "chart": "grouped_bar",
        "example": "Compare phases for trials involving metformin vs semaglutide.",
    },
    {
        "type": "geographic",
        "chart": "bar",
        "example": "Which countries have the most recruiting trials for breast cancer?",
    },
    {
        "type": "relationship",
        "chart": "network",
        "example": "Show a network of sponsors and drugs for Alzheimer's trials.",
    },
    {
        "type": "correlation",
        "chart": "scatter",
        "example": "Is there a relationship between enrollment size and trial duration for diabetes trials?",  # noqa: E501
    },
]

UNSUPPORTED_MESSAGE = (
    "I can't answer that. I support questions about ClinicalTrials.gov data in five shapes: "
    "time trends over years, distributions across categories (e.g. phases), comparisons between "
    "interventions, geographic breakdowns by country, and relationship/network queries."
)


def supported_query_types_payload() -> list[dict[str, str]]:
    """The list returned to clients when a query is rejected."""
    return [{"type": q["type"], "example": q["example"]} for q in SUPPORTED_QUERY_TYPES]
