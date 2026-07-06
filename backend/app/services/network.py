"""Build a sponsor<->drug co-occurrence network from trial records.

An edge links a lead sponsor to each intervention it runs, weighted by the number of
shared trials; the edge carries those NCT IDs so it is fully citable.

Selection is **edge-first**: we keep the strongest relationships (by shared-trial count)
within a node budget and include only the nodes those edges touch. This guarantees a
connected graph with no orphan nodes (every node has at least one relationship).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ..clients.clinicaltrials import TrialRecord

# A "drugs" network only includes pharmacological interventions — not behavioral,
# device, procedure, or other intervention types (e.g. "bulk outreach").
DRUG_TYPES = frozenset({"DRUG", "BIOLOGICAL"})

# Controls/comparators aren't therapeutics of interest and would form misleading hubs.
CONTROL_TERMS = ("placebo", "sham", "vehicle")


def _is_control(name: str) -> bool:
    low = name.lower()
    return any(term in low for term in CONTROL_TERMS)


def build_network(
    records: Iterable[TrialRecord],
    max_nodes: int = 40,
    max_links: int = 100,
    intervention_types: frozenset[str] = DRUG_TYPES,
) -> dict[str, Any]:
    edge_trials: dict[tuple[str, str], set[str]] = {}
    sponsor_trials: dict[str, set[str]] = {}
    drug_trials: dict[str, set[str]] = {}

    for r in records:
        sponsor = r.lead_sponsor
        if not sponsor:
            continue
        # Drug names are kept verbatim from the API (source of truth); we do not
        # normalize spelling variants. We only drop non-drug types and controls.
        drug_names = {
            i["name"]
            for i in r.interventions
            if i.get("name")
            and i.get("type", "").upper() in intervention_types
            and not _is_control(i["name"])
        }
        for drug in drug_names:
            edge_trials.setdefault((sponsor, drug), set()).add(r.nct_id)
            sponsor_trials.setdefault(sponsor, set()).add(r.nct_id)
            drug_trials.setdefault(drug, set()).add(r.nct_id)

    # Strongest relationships first; add an edge only if it fits the node budget.
    ranked = sorted(edge_trials.items(), key=lambda kv: len(kv[1]), reverse=True)

    links: list[dict[str, Any]] = []
    used: set[str] = set()
    # A node's count/citations must reflect ONLY the edges that survive into the rendered graph
    # (not edges dropped by the budget), or a node could display more trials than its visible
    # edges back. Accumulate per-node trials from the kept edges as we add them.
    node_trials: dict[str, set[str]] = {}
    for (sponsor, drug), trials in ranked:
        if len(links) >= max_links:
            break
        s_id, d_id = f"sponsor:{sponsor}", f"drug:{drug}"
        endpoints = {s_id, d_id}
        # Skip only if the edge would introduce a NEW node beyond the budget.
        if not endpoints <= used and len(used | endpoints) > max_nodes:
            continue
        links.append(
            {"source": s_id, "target": d_id, "value": len(trials), "nct_ids": sorted(trials)}
        )
        used |= endpoints
        node_trials.setdefault(s_id, set()).update(trials)
        node_trials.setdefault(d_id, set()).update(trials)

    # Nodes are derived strictly from kept edges -> no orphans, and each node's value is the
    # distinct trials across its *visible* edges (always <= the sum of its visible edge weights).
    nodes: list[dict[str, Any]] = []
    for sponsor in sponsor_trials:
        s_id = f"sponsor:{sponsor}"
        if s_id in used:
            nodes.append(_node(s_id, sponsor, "Sponsor", node_trials[s_id]))
    for drug in drug_trials:
        d_id = f"drug:{drug}"
        if d_id in used:
            nodes.append(_node(d_id, drug, "Drug", node_trials[d_id]))

    return {
        "nodes": nodes,
        "links": links,
        "categories": [{"name": "Sponsor"}, {"name": "Drug"}],
    }


def _node(node_id: str, name: str, category: str, trials: set[str]) -> dict[str, Any]:
    return {
        "id": node_id,
        "name": name,
        "category": category,
        "value": len(trials),
        "nct_ids": sorted(trials),
    }
