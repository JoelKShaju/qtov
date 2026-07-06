from __future__ import annotations

from app.clients.clinicaltrials import TrialRecord
from app.services.network import build_network


def _rec(nct, sponsor, drugs, interventions=None):
    return TrialRecord(
        nct_id=nct,
        title=nct,
        lead_sponsor=sponsor,
        interventions=interventions or [{"type": "DRUG", "name": d} for d in drugs],
    )


def test_network_excludes_non_drug_and_control_interventions():
    records = [
        _rec(
            "N1",
            "Acme",
            [],
            interventions=[
                {"type": "DRUG", "name": "Donepezil"},
                {"type": "BEHAVIORAL", "name": "Bulk Outreach"},
                {"type": "DRUG", "name": "Placebo"},
            ],
        )
    ]
    net = build_network(records)
    names = {n["name"] for n in net["nodes"] if n["category"] == "Drug"}
    assert names == {"Donepezil"}  # behavioral + placebo dropped


def test_network_has_no_orphan_nodes():
    # A high-volume sponsor whose drugs are each low-volume used to become an orphan.
    records = [
        _rec("N1", "Acme", ["DrugA"]),
        _rec("N2", "Acme", ["DrugB"]),
        _rec("N3", "Acme", ["DrugC"]),
        _rec("N4", "Beta", ["DrugA"]),
        _rec("N5", "Beta", ["DrugA"]),
    ]
    net = build_network(records, max_nodes=6, max_links=10)
    linked = {link["source"] for link in net["links"]} | {link["target"] for link in net["links"]}
    node_ids = {n["id"] for n in net["nodes"]}
    assert node_ids, "expected some nodes"
    assert node_ids == linked, f"orphan nodes present: {node_ids - linked}"


def test_network_keeps_strongest_edges_and_respects_node_budget():
    records = [_rec(f"N{i}", "Acme", ["DrugA"]) for i in range(5)] + [
        _rec("M1", "Beta", ["DrugB"]),
    ]
    net = build_network(records, max_nodes=4, max_links=10)
    assert len(net["nodes"]) <= 4
    # The Acme->DrugA edge (5 shared trials) must be the strongest and present.
    top = max(net["links"], key=lambda link_: link_["value"])
    assert {top["source"], top["target"]} == {"sponsor:Acme", "drug:DrugA"}
    assert top["value"] == 5


def test_node_value_reflects_only_visible_edges():
    # Acme runs DrugA (3 trials) and DrugB (2 trials), but the node budget only admits the
    # Acme->DrugA edge. The Acme node's value must be 3 (its visible edge), not 5 (all its drugs).
    records = [_rec(f"A{i}", "Acme", ["DrugA"]) for i in range(3)] + [
        _rec(f"B{i}", "Acme", ["DrugB"]) for i in range(2)
    ]
    net = build_network(records, max_nodes=2, max_links=10)
    acme = next(n for n in net["nodes"] if n["id"] == "sponsor:Acme")
    visible_edge_sum = sum(link["value"] for link in net["links"] if link["source"] == "sponsor:Acme")
    assert acme["value"] == 3
    assert acme["value"] <= visible_edge_sum  # never exceeds the trials its visible edges back
    assert len(acme["nct_ids"]) == 3


def test_network_keeps_api_drug_names_verbatim():
    # API is the source of truth: spelling variants are NOT merged.
    records = [
        _rec("N1", "Acme", [], interventions=[{"type": "DRUG", "name": "C-11 PiB"}]),
        _rec("N2", "Acme", [], interventions=[{"type": "DRUG", "name": "C11 PiB"}]),
    ]
    net = build_network(records)
    names = {n["name"] for n in net["nodes"] if n["category"] == "Drug"}
    assert names == {"C-11 PiB", "C11 PiB"}
