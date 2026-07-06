from __future__ import annotations

from app.clients.clinicaltrials import TrialRecord
from app.schemas.query import ChartType, QuerySpec, QueryType
from app.services.citations import citations_from_points
from app.services.scatter import build_scatter_points, plottable_count
from app.services.visualize import build_scatter_visualization


def _rec(nct: str, enrollment, duration, phases=("Phase 2",)) -> TrialRecord:
    return TrialRecord(
        nct_id=nct,
        title=f"Trial {nct}",
        phases=list(phases),
        enrollment=enrollment,
        duration_months=duration,
        start_date="2019-01",
        completion_date="2020-01",
    )


def test_scatter_points_drop_incomplete():
    records = [
        _rec("N1", 50, 12),
        _rec("N2", None, 12),  # no enrollment -> dropped
        _rec("N3", 200, None),  # no duration -> dropped
        _rec("N4", 300, 24),
        _rec("N5", 0, 10),  # non-positive enrollment -> dropped
    ]
    points = build_scatter_points(records)
    assert [p["nct_id"] for p in points] == ["N1", "N4"]  # stable nct_id order, only plottable
    assert {"nct_id": "N1", "title": "Trial N1", "phase": "Phase 2", "x": 50, "y": 12} in points


def test_scatter_points_respect_cap():
    records = [_rec(f"N{i}", i + 1, 10) for i in range(10)]
    assert len(build_scatter_points(records, max_points=3)) == 3


def test_scatter_subsample_is_representative_not_top_enrollment():
    # 90 small trials + 10 huge ones. A top-N-by-enrollment cap would show ONLY the 10 huge
    # (distorting the cloud); a representative random sample must include small trials too.
    small = [_rec(f"S{i:03d}", 10, 12) for i in range(90)]
    huge = [_rec(f"H{i:03d}", 100_000, 12) for i in range(10)]
    points = build_scatter_points(small + huge, max_points=20)
    assert len(points) == 20
    shown_huge = sum(1 for p in points if p["nct_id"].startswith("H"))
    assert shown_huge < 10  # not the biased top-10-by-enrollment; small trials are represented


def test_scatter_subsample_is_deterministic():
    records = [_rec(f"N{i:03d}", i + 1, 12) for i in range(50)]
    a = build_scatter_points(records, max_points=10)
    b = build_scatter_points(records, max_points=10)
    assert [p["nct_id"] for p in a] == [p["nct_id"] for p in b]  # fixed seed -> stable


def test_plottable_count():
    records = [_rec("N1", 50, 12), _rec("N2", None, 12), _rec("N3", 0, 5), _rec("N4", 9, 3)]
    assert plottable_count(records) == 2  # N1 and N4 only


def test_scatter_visualization_shape():
    spec = QuerySpec(query_type=QueryType.CORRELATION, condition="diabetes")
    points = build_scatter_points([_rec("N1", 50, 12)])
    viz = build_scatter_visualization(spec, points, total_records=1, filters_applied="condition=diabetes")
    assert viz.type == ChartType.SCATTER
    assert viz.encoding.x.type == "quantitative"
    assert viz.encoding.color.field == "phase"


def test_citations_from_points_have_excerpt():
    rec = _rec("N1", 50, 12)
    points = build_scatter_points([rec])
    citations = citations_from_points(points, {"N1": rec})
    assert citations[0].bucket == "N1"
    assert citations[0].nct_ids == ["N1"]
    assert "Enrollment: 50" in citations[0].trials[0].excerpt
