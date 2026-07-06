"""Assemble the Visualization envelope (encoding, chart_config, metadata) per query type."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ..schemas.query import (
    QUERY_TYPE_TO_CHART,
    ChartType,
    GroupBy,
    QuerySpec,
    QueryType,
)
from ..schemas.visualization import (
    AxisEncoding,
    ChartConfig,
    Encoding,
    Visualization,
    VizMetadata,
)
from .aggregate import Bucket

GROUP_LABELS = {
    GroupBy.YEAR: "Year",
    GroupBy.PHASE: "Phase",
    GroupBy.COUNTRY: "Country",
    GroupBy.SPONSOR: "Sponsor",
    GroupBy.STATUS: "Status",
}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _current_year() -> int:
    return datetime.now(UTC).year


def _title(spec: QuerySpec, fallback: str) -> str:
    return spec.title.strip() or fallback


def points_from_buckets(buckets: list[Bucket]) -> list[dict[str, Any]]:
    return [{"x": b.label, "y": b.value} for b in buckets]


def _time_trend_points(buckets: list[Bucket], current_year: int) -> list[dict[str, Any]]:
    """Year points, flagging the current year as `partial` and future years as `projected`.

    Trials carry anticipated start dates, so the latest/future buckets are incomplete and must
    not be read as a real decline — the flags let the chart and the summary say so.
    """
    points: list[dict[str, Any]] = []
    for b in buckets:
        point: dict[str, Any] = {"x": b.label, "y": b.value}
        year = int(b.label) if str(b.label).isdigit() else None
        if year is not None and year > current_year:
            point["projected"] = True
        elif year == current_year:
            point["partial"] = True
        points.append(point)
    return points


def _time_trend_caveat(buckets: list[Bucket], current_year: int) -> str | None:
    """Human-readable note about incomplete year buckets (None when all years are complete)."""
    years = [int(b.label) for b in buckets if str(b.label).isdigit()]
    partial = current_year in years
    projected = sorted(y for y in years if y > current_year)
    if not partial and not projected:
        return None
    parts: list[str] = []
    if partial:
        parts.append(f"{current_year} is still in progress")
    if projected:
        span = f"{projected[0]}" if len(projected) == 1 else f"{projected[0]}–{projected[-1]}"
        parts.append(f"{span} reflect anticipated (future) start dates")
    return "; ".join(parts) + " — these periods are incomplete and not a real decline."


def build_chart_visualization(
    spec: QuerySpec, buckets: list[Bucket], total_records: int, filters_applied: str
) -> Visualization:
    """Line / bar visualization (time_trend, distribution, geographic)."""
    chart_type = QUERY_TYPE_TO_CHART[spec.query_type]
    group_by = spec.effective_group_by()
    x_label = GROUP_LABELS.get(group_by, "Category") if group_by else "Category"

    data_caveat: str | None = None
    if spec.query_type == QueryType.TIME_TREND:
        encoding = Encoding(
            x=AxisEncoding(field="x", type="temporal"),
            y=AxisEncoding(field="y", type="quantitative"),
        )
        chart_config = ChartConfig(
            x_label="Year", y_label="Number of trials", x_axis_rotation=0, time_format="%Y"
        )
        current_year = _current_year()
        data = _time_trend_points(buckets, current_year)
        data_caveat = _time_trend_caveat(buckets, current_year)
    else:
        rotation = 35 if group_by in (GroupBy.COUNTRY, GroupBy.SPONSOR) else 0
        encoding = Encoding(
            x=AxisEncoding(field="x", type="ordinal"),
            y=AxisEncoding(field="y", type="quantitative"),
        )
        chart_config = ChartConfig(
            x_label=x_label, y_label="Number of trials", x_axis_rotation=rotation
        )
        data = points_from_buckets(buckets)

    return Visualization(
        type=chart_type,
        title=_title(spec, f"Clinical trials by {x_label.lower()}"),
        data=data,
        encoding=encoding,
        metadata=VizMetadata(
            total_records=total_records,
            filters_applied=filters_applied,
            timestamp=_now_iso(),
            chart_config=chart_config,
            data_caveat=data_caveat,
        ),
    )


def build_comparison_visualization(
    spec: QuerySpec,
    series: list[dict[str, Any]],
    total_records: int,
    filters_applied: str,
    group_by: GroupBy = GroupBy.PHASE,
) -> Visualization:
    """Grouped bar: one row per breakdown bucket with a count column per compared entity."""
    entities = spec.comparison_entities or []
    x_label = GROUP_LABELS.get(group_by, "Phase")
    rotation = 35 if group_by in (GroupBy.YEAR, GroupBy.STATUS) else 0
    encoding = Encoding(
        x=AxisEncoding(field="bucket", type="temporal" if group_by == GroupBy.YEAR else "ordinal"),
        y=AxisEncoding(field="value", type="quantitative"),
        color=AxisEncoding(field="series", type="nominal"),
    )
    return Visualization(
        type=ChartType.GROUPED_BAR,
        title=_title(spec, f"{x_label} comparison: {' vs '.join(entities)}"),
        data=series,
        encoding=encoding,
        metadata=VizMetadata(
            total_records=total_records,
            filters_applied=filters_applied,
            timestamp=_now_iso(),
            chart_config=ChartConfig(
                x_label=x_label, y_label="Number of trials", x_axis_rotation=rotation
            ),
        ),
    )


def build_scatter_visualization(
    spec: QuerySpec, points: list[dict[str, Any]], total_records: int, filters_applied: str
) -> Visualization:
    """Scatter: one point per trial — x=enrollment, y=duration (months), color=phase."""
    encoding = Encoding(
        x=AxisEncoding(field="x", type="quantitative"),
        y=AxisEncoding(field="y", type="quantitative"),
        color=AxisEncoding(field="phase", type="nominal"),
    )
    return Visualization(
        type=ChartType.SCATTER,
        title=_title(spec, "Enrollment vs. trial duration"),
        data=points,
        encoding=encoding,
        metadata=VizMetadata(
            total_records=total_records,
            filters_applied=filters_applied,
            timestamp=_now_iso(),
            chart_config=ChartConfig(
                x_label="Enrollment (participants)", y_label="Duration (months)"
            ),
        ),
    )


def build_network_visualization(
    spec: QuerySpec, network: dict[str, Any], total_records: int, filters_applied: str
) -> Visualization:
    return Visualization(
        type=ChartType.NETWORK,
        title=_title(spec, "Sponsor–drug network"),
        data=network,
        encoding=Encoding(color=AxisEncoding(field="category", type="nominal")),
        metadata=VizMetadata(
            total_records=total_records,
            filters_applied=filters_applied,
            timestamp=_now_iso(),
            chart_config=ChartConfig(x_label="", y_label=""),
        ),
    )
