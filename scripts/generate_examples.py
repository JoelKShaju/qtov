"""Generate real example outputs by running the full agent pipeline.

Hits the live ClinicalTrials.gov API and the real LLM (key from backend/.env), but uses an
in-memory repository so no Postgres is required. Writes one <slug>.json per query to examples/.

Run from the backend dir:  uv run python ../scripts/generate_examples.py
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from app.agent.interpreter import interpret
from app.agent.summarize import summarize
from app.clients.clinicaltrials import ClinicalTrialsClient
from app.db.repositories import InMemoryRepository
from app.schemas.query import QueryRequest
from app.agent.orchestrator import run_query

OUT_DIR = Path(__file__).resolve().parent.parent / "examples"

QUERIES = [
    "How has the number of trials for pembrolizumab changed per year since 2015?",
    "How are diabetes trials distributed across phases?",
    "Compare phases for trials involving metformin vs semaglutide.",
    "Which countries have the most recruiting trials for breast cancer?",
    "Show a network of sponsors and drugs for Alzheimer's trials.",
    "Is there a relationship between enrollment size and trial duration for diabetes trials?",
    "Compare the number of metformin vs semaglutide trials per year since 2018.",
]


def _slug(query: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")[:60]


async def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    repo = InMemoryRepository()
    for query in QUERIES:
        try:
            async with ClinicalTrialsClient() as client:
                resp = await run_query(
                    QueryRequest(query=query),
                    interpret_fn=interpret,
                    client=client,
                    repo=repo,
                    summarize_fn=summarize,
                )
            path = OUT_DIR / f"{_slug(query)}.json"
            path.write_text(json.dumps(resp.model_dump(mode="json"), indent=2))
            viz = resp.visualization
            print(f"[ok ] {viz.type.value:11} {len(resp.citations):>3} citations :: {path.name}")
        except Exception as exc:  # noqa: BLE001
            print(f"[ERR] {type(exc).__name__}: {exc} :: {query}")


if __name__ == "__main__":
    asyncio.run(main())
