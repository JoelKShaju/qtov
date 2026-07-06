from __future__ import annotations

from app.clients.clinicaltrials import TrialRecord
from app.schemas.query import GroupBy
from app.services.aggregate import Bucket
from app.services.citations import build_citations, citations_from_links


def test_build_citations_links_trials():
    trials = {"N1": TrialRecord(nct_id="N1", title="Trial One")}
    buckets = [Bucket(label="2015", value=1, nct_ids=["N1"])]
    citations = build_citations(buckets, trials)
    assert citations[0].bucket == "2015"
    assert citations[0].trials[0].title == "Trial One"
    assert citations[0].trials[0].url == "https://clinicaltrials.gov/study/N1"


def test_build_citations_excerpt_quotes_the_grouped_field():
    trials = {
        "N1": TrialRecord(nct_id="N1", title="Trial One", phases=["Phase 3"], start_date="2019-04")
    }
    phase_cite = build_citations(
        [Bucket(label="Phase 3", value=1, nct_ids=["N1"])], trials, GroupBy.PHASE
    )
    assert phase_cite[0].trials[0].excerpt == "Phase: Phase 3"

    year_cite = build_citations(
        [Bucket(label="2019", value=1, nct_ids=["N1"])], trials, GroupBy.YEAR
    )
    assert year_cite[0].trials[0].excerpt == "Start date: 2019-04"

    # No group dimension -> no excerpt.
    plain = build_citations([Bucket(label="x", value=1, nct_ids=["N1"])], trials)
    assert plain[0].trials[0].excerpt is None


def test_citations_from_links_formats_edge_label():
    trials = {"N1": TrialRecord(nct_id="N1", title="Trial One")}
    links = [{"source": "sponsor:Acme", "target": "drug:Metformin", "value": 1, "nct_ids": ["N1"]}]
    citations = citations_from_links(links, trials)
    assert citations[0].bucket == "Acme → Metformin"
    assert citations[0].trials[0].nct_id == "N1"


def test_link_excerpt_quotes_only_the_edge_drug():
    # The trial also tests a placebo + a behavioral arm, which the network excludes from the edge.
    trials = {
        "N1": TrialRecord(
            nct_id="N1",
            title="Trial One",
            lead_sponsor="Acme",
            interventions=[
                {"type": "DRUG", "name": "Metformin"},
                {"type": "DRUG", "name": "Placebo"},
                {"type": "BEHAVIORAL", "name": "Coaching"},
            ],
        )
    }
    links = [{"source": "sponsor:Acme", "target": "drug:Metformin", "value": 1, "nct_ids": ["N1"]}]
    excerpt = citations_from_links(links, trials)[0].trials[0].excerpt
    assert "Metformin" in excerpt and "Acme" in excerpt
    assert "Placebo" not in excerpt and "Coaching" not in excerpt  # only the edge's drug
