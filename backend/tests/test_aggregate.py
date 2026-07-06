from __future__ import annotations

from app.clients.clinicaltrials import TrialRecord
from app.services.aggregate import (
    aggregate_by_country,
    aggregate_by_phase,
    aggregate_by_year,
)


def _rec(nct, year=None, phases=None, countries=None, sponsor=None):
    return TrialRecord(
        nct_id=nct,
        title=nct,
        start_year=year,
        phases=phases or [],
        countries=countries or [],
        lead_sponsor=sponsor,
    )


def test_aggregate_by_year_counts_and_sorts():
    recs = [_rec("N1", 2015), _rec("N2", 2015), _rec("N3", 2016)]
    buckets = aggregate_by_year(recs)
    assert [(b.label, b.value) for b in buckets] == [("2015", 2), ("2016", 1)]
    assert set(buckets[0].nct_ids) == {"N1", "N2"}


def test_aggregate_by_phase_membership():
    recs = [_rec("N1", phases=["Phase 2", "Phase 3"]), _rec("N2", phases=["Phase 3"])]
    buckets = {b.label: b for b in aggregate_by_phase(recs)}
    assert buckets["Phase 2"].value == 1
    assert buckets["Phase 3"].value == 2
    assert set(buckets["Phase 3"].nct_ids) == {"N1", "N2"}


def test_aggregate_by_phase_defaults_to_not_applicable():
    buckets = {b.label: b for b in aggregate_by_phase([_rec("N1")])}
    assert "Not Applicable" in buckets


def test_aggregate_by_country_top_n_sorted_desc():
    recs = [
        _rec("N1", countries=["United States", "Canada"]),
        _rec("N2", countries=["United States"]),
    ]
    buckets = aggregate_by_country(recs)
    assert buckets[0].label == "United States"
    assert buckets[0].value == 2
