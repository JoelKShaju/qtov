"""Request schema, the closed query-type taxonomy, and the LLM's structured output."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator


class QueryType(str, Enum):
    """Closed taxonomy of supported query types. Anything else -> UNSUPPORTED -> 422."""

    TIME_TREND = "time_trend"
    DISTRIBUTION = "distribution"
    COMPARISON = "comparison"
    GEOGRAPHIC = "geographic"
    RELATIONSHIP = "relationship"
    CORRELATION = "correlation"
    UNSUPPORTED = "unsupported"


class ChartType(str, Enum):
    LINE = "line"
    BAR = "bar"
    GROUPED_BAR = "grouped_bar"
    NETWORK = "network"
    SCATTER = "scatter"


class StudyType(str, Enum):
    INTERVENTIONAL = "Interventional"
    OBSERVATIONAL = "Observational"


class GroupBy(str, Enum):
    YEAR = "year"
    PHASE = "phase"
    COUNTRY = "country"
    SPONSOR = "sponsor"
    STATUS = "status"


# Fixed query_type -> chart type mapping. The LLM only classifies; it never picks a chart.
QUERY_TYPE_TO_CHART: dict[QueryType, ChartType] = {
    QueryType.TIME_TREND: ChartType.LINE,
    QueryType.DISTRIBUTION: ChartType.BAR,
    QueryType.COMPARISON: ChartType.GROUPED_BAR,
    QueryType.GEOGRAPHIC: ChartType.BAR,
    QueryType.RELATIONSHIP: ChartType.NETWORK,
    QueryType.CORRELATION: ChartType.SCATTER,
}

# Default aggregation dimension per query type, used when the LLM leaves group_by unset.
DEFAULT_GROUP_BY: dict[QueryType, GroupBy] = {
    QueryType.TIME_TREND: GroupBy.YEAR,
    QueryType.DISTRIBUTION: GroupBy.PHASE,
    QueryType.COMPARISON: GroupBy.PHASE,
    QueryType.GEOGRAPHIC: GroupBy.COUNTRY,
}


class DateRange(BaseModel):
    model_config = {"populate_by_name": True}

    from_: str | None = Field(
        default=None, alias="from", description="ISO date or year lower bound"
    )
    to: str | None = Field(default=None, description="ISO date or year upper bound")


class QueryRequest(BaseModel):
    """Layer-1 (deterministic) input validation happens here via Pydantic.

    Beyond the required `query`, every field is an OPTIONAL structured filter. When
    provided it is authoritative — it overrides whatever the LLM infers from the prose
    (see `apply_request_overrides`). `drug_name` and `trial_phase` are accepted as
    aliases for `intervention`/`phase` as friendlier client-facing vocabulary.
    """

    model_config = {"populate_by_name": True}

    query: str = Field(..., min_length=3, max_length=500)
    condition: str | None = Field(default=None, description="Disease/condition filter.")
    intervention: str | None = Field(
        default=None, alias="drug_name", description="Drug/intervention filter."
    )
    intervention_type: str | None = None
    study_type: StudyType | None = None
    sponsor: str | None = Field(default=None, description="Sponsor/organization filter.")
    country: str | None = None
    phase: str | None = Field(
        default=None, alias="trial_phase", description="Trial phase, e.g. 'Phase 3'."
    )
    status: list[str] | None = Field(default=None, description="Overall-status enum filters.")
    start_year: int | None = Field(default=None, description="Lower-bound start year.")
    end_year: int | None = Field(default=None, description="Upper-bound start year.")
    date_range: DateRange | None = None
    # Force a specific query type (used when the user picks an alternative chart).
    force_query_type: QueryType | None = None

    @field_validator("query")
    @classmethod
    def _strip_query(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("query must not be blank")
        return stripped


class QuerySpec(BaseModel):
    """Pydantic AI structured output: the agent's interpretation of the NL query.

    Field descriptions double as instructions to the LLM.
    """

    query_type: QueryType = Field(
        description="The analysis requested. Use 'unsupported' for anything outside the five types."
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence in query_type; use < 0.7 if the query also fits another type.",
    )
    alternative_query_types: list[QueryType] = Field(
        default_factory=list,
        description="Other plausible query types, most likely first. Never include 'unsupported'.",
    )
    supported: bool = Field(default=True, description="False only when query_type == unsupported.")
    rejection_reason: str | None = Field(
        default=None, description="If unsupported, a short, friendly user-facing reason."
    )
    condition: str | None = Field(
        default=None, description="Disease/condition term, e.g. 'breast cancer'."
    )
    intervention: str | None = Field(default=None, description="Primary drug/intervention term.")
    intervention_type: str | None = Field(
        default=None, description="Intervention type, e.g. Drug, Biological, Device, Procedure."
    )
    study_type: StudyType | None = Field(
        default=None, description="Interventional or Observational."
    )
    sponsor: str | None = Field(
        default=None, description="Sponsor/organization running the trials, e.g. 'Mayo Clinic'."
    )
    country: str | None = Field(
        default=None, description="Country name filter, e.g. 'United States'."
    )
    status: list[str] | None = Field(
        default=None,
        description="Overall status filters using API enums, e.g. ['RECRUITING', 'COMPLETED'].",
    )
    start_year: int | None = Field(default=None, description="Lower-bound start year, e.g. 2015.")
    end_year: int | None = Field(default=None, description="Upper-bound start year.")
    phase: str | None = Field(
        default=None, description="Single trial-phase filter, e.g. 'Phase 3' or 'Phase 2'."
    )
    group_by: GroupBy | None = Field(
        default=None, description="Aggregation dimension: year, phase, country, sponsor, or status."
    )
    comparison_entities: list[str] | None = Field(
        default=None,
        description="ALL items to compare, e.g. ['metformin', 'semaglutide'] or ['United States', 'China'].",  # noqa: E501
    )
    comparison_dimension: str | None = Field(
        default=None,
        description="Entity kind: 'intervention' (default), 'country', 'condition', or 'sponsor'.",
    )
    title: str = Field(default="", description="Concise, human-readable chart title.")
    reasoning: str = Field(default="", description="One sentence explaining the interpretation.")

    def effective_group_by(self) -> GroupBy | None:
        return self.group_by or DEFAULT_GROUP_BY.get(self.query_type)
