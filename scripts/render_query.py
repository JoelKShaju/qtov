"""Render a query's visualization to a PNG (used by the `query-to-image` skill).

Usage (from the backend dir so httpx is available; matplotlib/networkx pulled by uv --with):
    uv run --with matplotlib --with networkx python ../scripts/render_query.py "<query>" [out.png]

Prints `WROTE <path>` on success, or `UNSUPPORTED: ...` for a rejected query.
"""

from __future__ import annotations

import os
import sys

import httpx

API_BASE = os.environ.get("API_BASE", "http://localhost:8000")


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: render_query.py '<query>' [out.png]")
        return 1
    query = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else "/tmp/qtov_chart.png"

    resp = httpx.post(f"{API_BASE}/api/query", json={"query": query}, timeout=180)
    if resp.status_code == 422:
        body = resp.json()
        print("UNSUPPORTED:", body.get("message", "unsupported query"))
        for t in body.get("supported_query_types", []):
            print(f"  - {t['type']}: {t['example']}")
        return 2
    resp.raise_for_status()

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    data = resp.json()
    viz = data["visualization"]
    cc = viz["metadata"]["chart_config"]
    chart, points = viz["type"], viz["data"]
    fig, ax = plt.subplots(figsize=(11, 6.5))

    if chart == "line":
        ax.plot([str(p["x"]) for p in points], [p["y"] for p in points], marker="o", color="#6366f1")
    elif chart == "bar":
        ax.bar([str(p["x"]) for p in points], [p["y"] for p in points], color="#6366f1")
        plt.setp(ax.get_xticklabels(), rotation=cc.get("x_axis_rotation", 0), ha="right")
    elif chart == "grouped_bar":
        import numpy as np

        buckets = [r["bucket"] for r in points]
        entities = [k for k in points[0] if k != "bucket"] if points else []
        x = np.arange(len(buckets))
        width = 0.8 / max(1, len(entities))
        for i, entity in enumerate(entities):
            ax.bar(x + i * width, [r.get(entity, 0) for r in points], width, label=entity)
        ax.set_xticks(x + width * (len(entities) - 1) / 2)
        ax.set_xticklabels(buckets, rotation=cc.get("x_axis_rotation", 0), ha="right")
        ax.legend()
    elif chart == "scatter":
        palette = ["#6366f1", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#0ea5e9"]
        phases = sorted({p.get("phase", "—") for p in points})
        cmap = {ph: palette[i % len(palette)] for i, ph in enumerate(phases)}
        for ph in phases:
            sub = [p for p in points if p.get("phase", "—") == ph]
            ax.scatter(
                [p["x"] for p in sub], [p["y"] for p in sub],
                s=24, alpha=0.6, color=cmap[ph], label=ph, edgecolors="none",
            )
        ax.legend(fontsize=8, title="Phase")
    elif chart == "network":
        import networkx as nx

        graph = nx.Graph()
        for node in points["nodes"]:
            graph.add_node(node["id"], name=node["name"], category=node["category"])
        for link in points["links"]:
            graph.add_edge(link["source"], link["target"], weight=link.get("value", 1))
        pos = nx.spring_layout(graph, seed=42, k=0.6)
        colors = ["#6366f1" if graph.nodes[n]["category"] == "Sponsor" else "#10b981" for n in graph]
        nx.draw_networkx_nodes(graph, pos, node_color=colors, node_size=320, ax=ax)
        nx.draw_networkx_edges(graph, pos, alpha=0.35, ax=ax)
        nx.draw_networkx_labels(
            graph, pos, labels={n: graph.nodes[n]["name"] for n in graph}, font_size=7, ax=ax
        )
        ax.axis("off")
    else:
        print(f"unknown chart type: {chart}")
        return 3

    ax.set_title(viz["title"], fontsize=13, fontweight="bold")
    if chart in ("line", "bar", "grouped_bar", "scatter"):
        ax.set_xlabel(cc.get("x_label", ""))
        ax.set_ylabel(cc.get("y_label", ""))
    fig.tight_layout()
    # Surface the time-trend caveat (in-progress / projected years) on the static image too.
    caveat = viz["metadata"].get("data_caveat")
    if caveat:
        fig.subplots_adjust(bottom=0.18)
        fig.text(0.5, 0.035, f"⚠ {caveat}", ha="center", fontsize=7.5, color="#b45309", wrap=True)
    fig.savefig(out, dpi=130)
    print("WROTE", os.path.abspath(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
