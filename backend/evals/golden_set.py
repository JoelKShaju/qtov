"""Labeled golden set for the classification eval.

A small, hand-labeled set of natural-language queries with their expected `query_type`, used to
*measure* (not assert) how well the agent classifies into the closed taxonomy. Paraphrases and a
few deliberately tricky cases (medical advice, free-text summaries, a status-breakdown comparison)
are included so the numbers reflect real ambiguity, not just the canonical example phrasings.
"""

from __future__ import annotations

from app.schemas.query import QueryType

# (query, expected_query_type)
GOLDEN_SET: list[tuple[str, QueryType]] = [
    # --- time_trend ---
    ("How has the number of trials for pembrolizumab changed per year since 2015?", QueryType.TIME_TREND),
    ("How many diabetes trials started each year?", QueryType.TIME_TREND),
    ("Show the yearly trend of melanoma trials.", QueryType.TIME_TREND),
    ("Trials for semaglutide over time.", QueryType.TIME_TREND),
    ("What is the annual count of lung cancer trials since 2010?", QueryType.TIME_TREND),
    # --- distribution ---
    ("How are diabetes trials distributed across phases?", QueryType.DISTRIBUTION),
    ("Break down asthma trials by phase.", QueryType.DISTRIBUTION),
    ("What is the phase distribution of breast cancer trials?", QueryType.DISTRIBUTION),
    ("Show the spread of obesity trials across phases.", QueryType.DISTRIBUTION),
    ("Which phases do HIV trials fall into?", QueryType.DISTRIBUTION),
    # --- comparison ---
    ("Compare phases for trials involving metformin vs semaglutide.", QueryType.COMPARISON),
    ("Metformin versus insulin: how do their trials compare?", QueryType.COMPARISON),
    ("Compare the number of pembrolizumab vs nivolumab trials per year.", QueryType.COMPARISON),
    ("Compare recruiting status for diabetes and obesity trials.", QueryType.COMPARISON),
    ("How do trial phases differ between drug A and drug B?", QueryType.COMPARISON),
    # --- geographic ---
    ("Which countries have the most recruiting trials for breast cancer?", QueryType.GEOGRAPHIC),
    ("Where are diabetes trials being run?", QueryType.GEOGRAPHIC),
    ("Top countries for HIV trials.", QueryType.GEOGRAPHIC),
    ("Geographic distribution of COVID-19 trials.", QueryType.GEOGRAPHIC),
    ("Which countries lead in Alzheimer's trials?", QueryType.GEOGRAPHIC),
    # --- relationship ---
    ("Show a network of sponsors and drugs for Alzheimer's trials.", QueryType.RELATIONSHIP),
    ("Map the relationship between sponsors and interventions in cancer trials.", QueryType.RELATIONSHIP),
    ("Drug co-occurrence network for diabetes combination studies.", QueryType.RELATIONSHIP),
    ("Which sponsors are connected to which drugs for obesity?", QueryType.RELATIONSHIP),
    ("Network of drugs studied together in melanoma trials.", QueryType.RELATIONSHIP),
    # --- correlation ---
    ("Is there a relationship between enrollment size and trial duration for diabetes trials?", QueryType.CORRELATION),
    ("Do larger cancer trials tend to run longer?", QueryType.CORRELATION),
    ("Plot enrollment against trial duration for asthma trials.", QueryType.CORRELATION),
    ("Correlation between enrollment and how long obesity trials last.", QueryType.CORRELATION),
    ("Scatter of participants vs study length for HIV trials.", QueryType.CORRELATION),
    # --- unsupported ---
    ("What's the weather in Paris today?", QueryType.UNSUPPORTED),
    ("Write me a poem about oncology.", QueryType.UNSUPPORTED),
    ("Should I take aspirin for my headache?", QueryType.UNSUPPORTED),
    ("Summarize the latest cancer research news.", QueryType.UNSUPPORTED),
    ("What is the capital of France?", QueryType.UNSUPPORTED),
    ("Translate 'clinical trial' into German.", QueryType.UNSUPPORTED),
]
