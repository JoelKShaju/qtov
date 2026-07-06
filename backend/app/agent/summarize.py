"""Second agent: write a short, source-cited explanation of the rendered chart.

It is given only the already-computed data and the NCT IDs behind each point (never the
raw trials), so it narrates facts the deterministic pipeline produced. A post-hoc sanitizer
strips any cited NCT ID that wasn't in the data, so the summary cannot fabricate citations.
"""

from __future__ import annotations

import json
import re

from pydantic_ai import Agent

from ..config import settings
from ..schemas.visualization import Citation, Visualization
from .llm import run_text

SYSTEM_PROMPT = """You explain clinical-trials data visualizations for a research audience.

Given a chart's type, title, and its data points (each with the exact NCT trial IDs that
produced it), write a SHORT analysis (2-4 sentences, plain prose, no markdown headings):
- State what the chart shows and call out the notable points (largest/smallest, trend direction).
- Only use the numbers provided; never invent or estimate figures.
- A point with "status":"partial" is the current, still-in-progress period; "status":"projected"
  is a future period backed only by anticipated start dates. These are INCOMPLETE — never describe
  them as a decline/drop/decrease. Judge the trend from the complete periods only, and if you
  mention the latest/future points, note they are in progress or anticipated. Honor any "caveat".
- Ground claims by citing real trial IDs from the data, in parentheses, e.g. (NCT..., NCT...).
  ONLY cite NCT IDs that appear in the provided data; never invent IDs and never reuse the
  example IDs in these instructions. If a point lists no IDs, mention it without a citation.
- Be precise and neutral. Do not give medical advice.
"""

_MAX_POINTS = 24
_MAX_IDS_PER_POINT = 6
_NCT_RE = re.compile(r"NCT\d{8}")


def _incomplete_buckets(viz: Visualization) -> dict[str, str]:
    """Map bucket label -> 'partial' | 'projected' for points the chart flagged as incomplete."""
    if not isinstance(viz.data, list):
        return {}
    status: dict[str, str] = {}
    for point in viz.data:
        if point.get("projected"):
            status[str(point.get("x"))] = "projected"
        elif point.get("partial"):
            status[str(point.get("x"))] = "partial"
    return status


def _payload(viz: Visualization, citations: list[Citation]) -> tuple[dict, set[str]]:
    """Build the JSON shown to the LLM and the set of NCT IDs it is allowed to cite."""
    points: list[dict] = []
    allowed: set[str] = set()
    if isinstance(viz.data, dict):  # network
        for node in viz.data.get("nodes", [])[:_MAX_POINTS]:
            ids = list(node.get("nct_ids", []))[:_MAX_IDS_PER_POINT]
            allowed.update(ids)
            points.append({"name": node.get("name"), "trials": node.get("value"), "nct_ids": ids})
    else:
        incomplete = _incomplete_buckets(viz)
        for c in citations[:_MAX_POINTS]:
            ids = c.nct_ids[:_MAX_IDS_PER_POINT]
            allowed.update(ids)
            point = {"bucket": c.bucket, "value": c.value, "nct_ids": ids}
            if status := incomplete.get(str(c.bucket)):
                point["status"] = status  # 'partial' (current year) or 'projected' (future)
            points.append(point)
    payload = {
        "chart_type": viz.type.value,
        "title": viz.title,
        "total_records": viz.metadata.total_records,
        "filters_applied": viz.metadata.filters_applied,
        "caveat": viz.metadata.data_caveat,
        "points": points,
    }
    return payload, allowed


def sanitize_citations(text: str, allowed: set[str]) -> str:
    """Remove any cited NCT ID not present in `allowed`, then tidy leftover punctuation."""
    text = _NCT_RE.sub(lambda m: m.group(0) if m.group(0) in allowed else "", text)
    text = re.sub(r",\s*,+", ", ", text)  # collapse repeated commas
    text = re.sub(r"\(\s*,\s*", "(", text)  # leading comma in a group
    text = re.sub(r"\s*,\s*\)", ")", text)  # trailing comma in a group
    text = re.sub(r"\s*\(\s*\)", "", text)  # empty parentheses
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\s+([.,;:])", r"\1", text)
    return text.strip()


async def summarize(
    query: str,
    viz: Visualization,
    citations: list[Citation],
    agent: Agent[None, str] | None = None,
) -> str:
    payload, allowed = _payload(viz, citations)
    prompt = (
        f"User question: {query}\n\n"
        f"Chart and data (JSON):\n{json.dumps(payload, default=str)}"
    )
    text = await run_text(
        prompt,
        models=settings.summarizer_model_list,
        system_prompt=SYSTEM_PROMPT,
        agent=agent,
        name="summarizer",
    )
    return sanitize_citations(text, allowed)
