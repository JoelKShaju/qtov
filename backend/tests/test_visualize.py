from __future__ import annotations

from app.schemas.query import GroupBy, QuerySpec, QueryType
from app.services.aggregate import Bucket
from app.services.visualize import (
    build_chart_visualization,
    build_comparison_visualization,
    build_network_visualization,
)


def test_time_trend_builds_line_chart():
    spec = QuerySpec(query_type=QueryType.TIME_TREND, group_by=GroupBy.YEAR, title="Trend")
    buckets = [Bucket(label="2015", value=2, nct_ids=["N1", "N2"]), Bucket(label="2016", value=1, nct_ids=["N3"])]
    viz = build_chart_visualization(spec, buckets, total_records=3, filters_applied="condition=x")
    assert viz.type.value == "line"
    assert viz.data == [{"x": "2015", "y": 2}, {"x": "2016", "y": 1}]
    assert viz.metadata.chart_config.time_format == "%Y"
    assert viz.metadata.total_records == 3
    assert viz.encoding.x.type == "temporal"


def test_time_trend_flags_partial_and_projected_years():
    from datetime import UTC, datetime

    this_year = datetime.now(UTC).year
    spec = QuerySpec(query_type=QueryType.TIME_TREND, group_by=GroupBy.YEAR, title="Trend")
    buckets = [
        Bucket(label=str(this_year - 1), value=50, nct_ids=["N1"]),  # complete
        Bucket(label=str(this_year), value=30, nct_ids=["N2"]),  # partial
        Bucket(label=str(this_year + 1), value=2, nct_ids=["N3"]),  # projected
    ]
    viz = build_chart_visualization(spec, buckets, total_records=82, filters_applied="x")
    complete, partial, projected = viz.data
    assert "partial" not in complete and "projected" not in complete
    assert partial["partial"] is True
    assert projected["projected"] is True
    # The caveat names both the in-progress and the anticipated periods.
    assert viz.metadata.data_caveat is not None
    assert str(this_year) in viz.metadata.data_caveat
    assert "anticipated" in viz.metadata.data_caveat


def test_time_trend_no_caveat_when_all_years_complete():
    spec = QuerySpec(query_type=QueryType.TIME_TREND, group_by=GroupBy.YEAR)
    buckets = [Bucket(label="2015", value=5, nct_ids=["N1"])]
    viz = build_chart_visualization(spec, buckets, total_records=5, filters_applied="x")
    assert viz.metadata.data_caveat is None
    assert viz.data[0] == {"x": "2015", "y": 5}


def test_geographic_builds_bar_with_rotation():
    spec = QuerySpec(query_type=QueryType.GEOGRAPHIC, group_by=GroupBy.COUNTRY, title="Geo")
    buckets = [Bucket(label="United States", value=5, nct_ids=["N1"])]
    viz = build_chart_visualization(spec, buckets, total_records=5, filters_applied="condition=x")
    assert viz.type.value == "bar"
    assert viz.metadata.chart_config.x_axis_rotation == 35
    assert viz.metadata.chart_config.x_label == "Country"


def test_comparison_visualization_uses_breakdown_dimension():
    spec = QuerySpec(
        query_type=QueryType.COMPARISON,
        comparison_entities=["metformin", "semaglutide"],
        group_by=GroupBy.YEAR,
    )
    series = [{"bucket": "2020", "metformin": 5, "semaglutide": 2}]
    viz = build_comparison_visualization(
        spec, series, total_records=7, filters_applied="x", group_by=GroupBy.YEAR
    )
    assert viz.type.value == "grouped_bar"
    assert viz.metadata.chart_config.x_label == "Year"  # not hardcoded to "Phase"
    assert viz.encoding.x.type == "temporal"


def test_network_visualization_passthrough():
    spec = QuerySpec(query_type=QueryType.RELATIONSHIP, title="Net")
    network = {"nodes": [{"id": "a"}], "links": [], "categories": []}
    viz = build_network_visualization(spec, network, total_records=1, filters_applied="x")
    assert viz.type.value == "network"
    assert viz.data == network
