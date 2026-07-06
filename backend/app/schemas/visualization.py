"""Response schema: the structured visualization object returned to clients."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, model_validator

from .query import ChartType, QueryType


class AxisEncoding(BaseModel):
    field: str
    type: str  # temporal | ordinal | nominal | quantitative


class Encoding(BaseModel):
    x: AxisEncoding | None = None
    y: AxisEncoding | None = None
    color: AxisEncoding | None = None


class ChartConfig(BaseModel):
    x_label: str = ""
    y_label: str = ""
    x_axis_rotation: int = 0
    time_format: str | None = None


class VizMetadata(BaseModel):
    total_records: int
    # Number of trials actually fetched for citations/discovery (<= MAX_RECORDS).
    sampled: int = 0
    # True when the displayed SET of buckets is exhaustive (e.g. the fixed phase enum, or
    # every matching trial was examined). False for open-ended top-N (country/sponsor) drawn
    # from a capped sample — each shown bucket's *count* is still exact, but the long tail of
    # categories may be unrepresented. Lets consumers be honest about coverage.
    bucket_set_complete: bool = True
    # Set when some data points are inherently incomplete (e.g. a time trend whose latest year
    # is in progress / future years carry only anticipated start dates). Drives the chart caption
    # and tells the summarizer not to read the tail as a real decline.
    data_caveat: str | None = None
    filters_applied: str
    source: str = "ClinicalTrials.gov"
    timestamp: str
    chart_config: ChartConfig


class Visualization(BaseModel):
    type: ChartType
    title: str
    # list of points for line/bar/grouped_bar/scatter; {"nodes": [...], "links": [...]} for network
    data: list[dict[str, Any]] | dict[str, Any]
    encoding: Encoding
    metadata: VizMetadata

    @model_validator(mode="after")
    def _data_matches_type(self) -> Visualization:
        """Self-describing: a network is a dict {nodes, links}; every other type is a list."""
        if self.type == ChartType.NETWORK:
            if not (isinstance(self.data, dict) and {"nodes", "links"} <= self.data.keys()):
                raise ValueError("network data must be a dict with 'nodes' and 'links'")
        elif not isinstance(self.data, list):
            raise ValueError(f"{self.type.value} data must be a list of points")
        return self


class TrialRef(BaseModel):
    nct_id: str
    title: str
    url: str
    # Bonus (source traceability): the exact field/value from this trial's API record
    # that supports the data point it backs, e.g. 'Phase: Phase 3' or 'Start date: 2019-04'.
    excerpt: str | None = None


class Citation(BaseModel):
    """Source trail: which trials produced a single data point."""

    bucket: str
    value: float
    nct_ids: list[str]
    trials: list[TrialRef]


class AlternativeViz(BaseModel):
    """A plausible alternative interpretation the user can switch to."""

    query_type: QueryType
    chart: ChartType


class Interpretation(BaseModel):
    query_type: QueryType
    parameters: dict[str, Any]
    reasoning: str
    confidence: float = 1.0
    alternatives: list[AlternativeViz] = []


class QueryResponse(BaseModel):
    event_id: str = ""  # shareable id; permalink is /<event_id> in the UI
    query: str
    interpretation: Interpretation
    visualization: Visualization
    citations: list[Citation]
    summary: str = ""
    trace_id: str | None = None


class SupportedQueryType(BaseModel):
    type: str
    example: str


class UnsupportedQueryResponse(BaseModel):
    error: str = "unsupported_query"
    message: str
    supported_query_types: list[SupportedQueryType]
    event_id: str = ""  # shareable id; permalink is /<event_id> in the UI
    query: str = ""
