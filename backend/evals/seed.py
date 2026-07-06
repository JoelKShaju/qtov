"""Warm the trial cache by sending the demo queries to a running backend.

Run with the stack up:  API_BASE=http://localhost:8000 uv run python evals/seed.py
"""

from __future__ import annotations

import asyncio
import os

import httpx

DEMO_QUERIES = [
    "How has the number of trials for pembrolizumab changed per year since 2015?",
    "How are diabetes trials distributed across phases?",
    "Compare phases for trials involving metformin vs semaglutide.",
    "Which countries have the most recruiting trials for breast cancer?",
    "Show a network of sponsors and drugs for Alzheimer's trials.",
]


async def main() -> None:
    base = os.environ.get("API_BASE", "http://localhost:8000")
    async with httpx.AsyncClient(timeout=60.0) as client:
        for query in DEMO_QUERIES:
            try:
                resp = await client.post(f"{base}/api/query", json={"query": query})
                viz = resp.json().get("visualization", {}) if resp.status_code == 200 else {}
                print(f"[{resp.status_code}] {viz.get('type', '-'):11} :: {query}")
            except Exception as exc:  # noqa: BLE001
                print(f"[ERR] {exc} :: {query}")


if __name__ == "__main__":
    asyncio.run(main())
