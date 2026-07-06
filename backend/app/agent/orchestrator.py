"""Multi-step agent pipeline: interpret -> gate -> search -> aggregate -> visualize -> cite."""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from collections.abc import Awaitable, Callable, Iterator
from functools import partial
from typing import Any

from ..catalog import UNSUPPORTED_MESSAGE, supported_query_types_payload
from ..clients.clinicaltrials import ClinicalTrialsClient, TrialRecord, filters_summary
from ..config import settings
from ..db.repositories import Repository
from ..errors import AgentError, UnsupportedQueryError
from ..observability.logging import get_logger
from ..schemas.query import QUERY_TYPE_TO_CHART, GroupBy, QueryRequest, QuerySpec, QueryType
from ..schemas.visualization import (
    AlternativeViz,
    Citation,
    Interpretation,
    QueryResponse,
    SupportedQueryType,
    UnsupportedQueryResponse,
    Visualization,
)
from ..services.aggregate import PHASE_ORDER, Bucket, aggregate
from ..services.citations import (
    DEFAULT_LIMIT,
    build_citations,
    citations_from_links,
    citations_from_points,
)
from ..services.counts import bucket_spec, exact_count
from ..services.network import build_network
from ..services.scatter import build_scatter_points, plottable_count
from ..services.search_cache import cached_search
from ..services.visualize import (
    build_chart_visualization,
    build_comparison_visualization,
    build_network_visualization,
    build_scatter_visualization,
)
from ..validation import ensure_supported

InterpretFn = Callable[[QueryRequest], Awaitable[QuerySpec]]
SummarizeFn = Callable[[str, Visualization, list[Citation]], Awaitable[str]]
PipelineResult = tuple[Visualization, list[Citation], int, list[TrialRecord]]

_tracer: Any
try:
    from opentelemetry import trace as _otel_trace

    _tracer = _otel_trace.get_tracer("qtov.orchestrator")
except Exception:  # pragma: no cover - OpenTelemetry ships with the app image
    _tracer = None


@contextlib.contextmanager
def _query_span(name: str) -> Iterator[Any]:
    """Parent span so a request's agent steps share one trace. No-op when tracing is off."""
    if _tracer is None:
        yield None
    else:
        with _tracer.start_as_current_span(name) as span:
            yield span


def _trace_id_of(span: Any) -> str | None:
    if span is None:
        return None
    ctx = span.get_span_context()
    return format(ctx.trace_id, "032x") if ctx and ctx.trace_id else None


async def run_query(
    request: QueryRequest,
    *,
    interpret_fn: InterpretFn,
    client: ClinicalTrialsClient,
    repo: Repository,
    summarize_fn: SummarizeFn | None = None,
    logger: Any | None = None,
) -> QueryResponse:
    """Wrap the pipeline in one parent span so its agent steps link into a single trace."""
    with _query_span("qtov.query") as span:
        if span is not None:
            span.set_attribute("qtov.query", request.query)
        response = await _run_query_inner(
            request,
            interpret_fn=interpret_fn,
            client=client,
            repo=repo,
            summarize_fn=summarize_fn,
            logger=logger,
            trace_id=_trace_id_of(span),
        )
        if span is not None:
            span.set_attribute("qtov.query_type", response.interpretation.query_type.value)
            span.set_attribute("qtov.total_records", response.visualization.metadata.total_records)
        return response


async def _run_query_inner(
    request: QueryRequest,
    *,
    interpret_fn: InterpretFn,
    client: ClinicalTrialsClient,
    repo: Repository,
    summarize_fn: SummarizeFn | None = None,
    logger: Any | None = None,
    trace_id: str | None = None,
) -> QueryResponse:
    log = logger or get_logger(__name__)
    started = time.perf_counter()
    event_id = uuid.uuid4().hex

    # 1. Interpret + classify (Pydantic AI structured output).
    try:
        spec = await interpret_fn(request)
    except UnsupportedQueryError:
        raise
    except Exception as exc:  # bad API key, rate limit, model/network failure
        log.warning("agent.interpret_failed", error=str(exc))
        raise AgentError(
            "The query-understanding step failed. Check the LLM API key / connectivity."
        ) from exc
    log.info("agent.interpreted", query_type=spec.query_type.value, supported=spec.supported)

    # 2. Capability gate (L2): reject unsupported queries — but first persist them as an event
    #    so the rejection is shareable (/<event_id>) and shows up in history.
    try:
        ensure_supported(spec)
    except UnsupportedQueryError as err:
        err.event_id = event_id
        payload = UnsupportedQueryResponse(
            message=err.reason or UNSUPPORTED_MESSAGE,
            supported_query_types=[
                SupportedQueryType(**q) for q in supported_query_types_payload()
            ],
            event_id=event_id,
            query=request.query,
        ).model_dump(mode="json")
        await repo.save_event(event_id, request.query, payload)
        await repo.save_query(
            raw_query=request.query,
            parsed_parameters=spec.model_dump(mode="json"),
            query_type=spec.query_type.value,
            supported=False,
            rejection_reason=spec.rejection_reason,
            chart_type=None,
            total_records=0,
            latency_ms=(time.perf_counter() - started) * 1000,
            model=settings.classifier_model_list[0],
            trace_id=trace_id,
        )
        log.info("query.unsupported", event_id=event_id)
        raise

    # 3-5. Fetch -> aggregate -> visualize -> cite (path depends on query type).
    # The fetch goes through a read-through cache (services/search_cache.py), so the trial
    # cache is populated on a miss and re-hydrated on a hit.
    if spec.query_type == QueryType.COMPARISON:
        viz, citations, total, records = await _run_comparison(spec, client, repo)
    elif spec.query_type == QueryType.RELATIONSHIP:
        viz, citations, total, records = await _run_relationship(spec, client, repo)
    elif spec.query_type == QueryType.CORRELATION:
        viz, citations, total, records = await _run_scatter(spec, client, repo)
    else:
        viz, citations, total, records = await _run_chart(spec, client, repo)

    log.info("agent.fetched", records=len(records), total=total)

    # 6. Persist query history + citations (trials were cached during the fetch above).
    latency_ms = (time.perf_counter() - started) * 1000
    query_id = await repo.save_query(
        raw_query=request.query,
        parsed_parameters=spec.model_dump(mode="json"),
        query_type=spec.query_type.value,
        supported=spec.supported,
        rejection_reason=spec.rejection_reason,
        chart_type=viz.type.value,
        total_records=total,
        latency_ms=latency_ms,
        model=settings.classifier_model_list[0],
        trace_id=trace_id,
    )
    await repo.save_citations(query_id, citations)

    # Second agent: narrate the chart and cite sources. Non-fatal if it fails.
    summary = ""
    if summarize_fn is not None:
        try:
            summary = await summarize_fn(request.query, viz, citations)
        except Exception as exc:
            log.warning("agent.summarize_failed", error=str(exc))

    log.info("query.completed", query_id=query_id, total=total, latency_ms=round(latency_ms, 1))

    response = QueryResponse(
        event_id=event_id,
        query=request.query,
        interpretation=Interpretation(
            query_type=spec.query_type,
            parameters=_parameters(spec),
            reasoning=spec.reasoning,
            confidence=spec.confidence,
            alternatives=_alternatives(spec),
        ),
        visualization=viz,
        citations=citations,
        summary=summary,
        trace_id=trace_id or str(query_id),
    )
    await repo.save_event(event_id, request.query, response.model_dump(mode="json"))
    return response


async def _run_chart(
    spec: QuerySpec, client: ClinicalTrialsClient, repo: Repository
) -> PipelineResult:
    records, total = await cached_search(repo, client, spec)
    group_by = spec.effective_group_by()
    buckets = aggregate(records, group_by)
    if group_by == GroupBy.PHASE:
        # Phase is a fixed enum: enumerate every value so the distribution's bucket SET is
        # complete and exact, not limited to whichever phases happened to appear in the sample.
        present = {b.label for b in buckets}
        buckets += [Bucket(label=p, value=0, nct_ids=[]) for p in PHASE_ORDER if p not in present]
        buckets.sort(key=lambda b: PHASE_ORDER.index(b.label))
    await _apply_exact_counts(client, spec, group_by, buckets)
    if group_by == GroupBy.PHASE:
        buckets = [b for b in buckets if b.value > 0]  # drop phases with a true zero count
    viz = build_chart_visualization(spec, buckets, total, filters_summary(spec))
    viz.metadata.sampled = len(records)
    # The set is exhaustive for the fixed phase enum, or when every match was examined.
    viz.metadata.bucket_set_complete = group_by == GroupBy.PHASE or len(records) >= total
    trials_by_nct = _by_nct(records)
    # A bucket can have an exact value > 0 yet be absent from the capped sample (e.g. an enumerated
    # phase) — backfill citations so every shown datum stays traceable.
    if group_by is not None:
        unfilled = await _backfill_citations(
            client, [(b, spec, group_by, b.label) for b in buckets], trials_by_nct
        )
        if unfilled:
            viz.metadata.bucket_set_complete = False
    citations = build_citations(buckets, trials_by_nct, group_by)
    return viz, citations, total, records


async def _run_scatter(
    spec: QuerySpec, client: ClinicalTrialsClient, repo: Repository
) -> PipelineResult:
    records, total = await cached_search(repo, client, spec)
    points = build_scatter_points(records)
    viz = build_scatter_visualization(spec, points, total, filters_summary(spec))
    viz.metadata.sampled = len(records)
    # A scatter is one point per trial with no exact per-bucket counts, so it is inherently
    # sample-based whenever the fetch cap is hit — flag that the cloud is a subset of the
    # population, not all matching trials.
    if len(records) < total:
        viz.metadata.bucket_set_complete = False
        viz.metadata.data_caveat = _join_caveat(
            viz.metadata.data_caveat,
            f"Points are drawn from a capped sample of {len(records)} of {total} matching trials.",
        )
    # And be explicit when the plotted points are themselves a subsample of the eligible sample.
    plottable = plottable_count(records)
    if plottable > len(points):
        viz.metadata.data_caveat = _join_caveat(
            viz.metadata.data_caveat,
            f"Showing a representative random sample of {len(points)} of {plottable} sampled "
            "trials that report both enrollment and duration.",
        )
    citations = citations_from_points(points, _by_nct(records))
    return viz, citations, total, records


async def _bounded_gather(
    factories: list[Callable[[], Awaitable[Any]]], *, return_exceptions: bool = False
) -> list[Any]:
    """Run coroutine factories concurrently but capped at `upstream_concurrency`.

    Takes zero-arg factories (not coroutines) so nothing starts until a semaphore slot is free —
    bounding how many upstream ClinicalTrials.gov requests a single query fires at once.
    """
    sem = asyncio.Semaphore(settings.upstream_concurrency)

    async def run(factory: Callable[[], Awaitable[Any]]) -> Any:
        async with sem:
            return await factory()

    return await asyncio.gather(
        *(run(f) for f in factories), return_exceptions=return_exceptions
    )


def _join_caveat(existing: str | None, note: str) -> str:
    """Append a caveat sentence to metadata.data_caveat (reused as the single caveat channel)."""
    return f"{existing} {note}" if existing else note


# A backfill job: a bucket that may need citations, the spec it belongs to, and its dimension/label.
BackfillJob = tuple[Bucket, QuerySpec, GroupBy, str]


async def _backfill_citations(
    client: ClinicalTrialsClient,
    jobs: list[BackfillJob],
    trials_by_nct: dict[str, TrialRecord],
    limit: int = DEFAULT_LIMIT,
) -> bool:
    """Fetch a few NCT IDs for any non-zero bucket that has no sampled citations.

    The exact count can be > 0 for a bucket that didn't surface in the capped sample (so its
    `nct_ids` is empty) — a data point with no source trail. This fetches up to `limit` records for
    each such bucket so every shown datum stays citable. Returns True if any gap remains unfilled.
    """
    gaps = [
        (b, bucket_spec(s, gb, lbl)) for (b, s, gb, lbl) in jobs if b.value > 0 and not b.nct_ids
    ]
    fillable = [(b, s) for b, s in gaps if s is not None]
    if not fillable:
        return bool(gaps)  # nothing we can fetch, but gaps existed
    fetched = await _bounded_gather(
        [partial(client.fetch_sample, s, limit) for _, s in fillable],
        return_exceptions=True,
    )
    unfilled = len(gaps) - len(fillable)
    for (bucket, _spec), records in zip(fillable, fetched, strict=True):
        if isinstance(records, list) and records:
            bucket.nct_ids = [r.nct_id for r in records[:limit]]
            for r in records[:limit]:
                trials_by_nct.setdefault(r.nct_id, r)
        else:
            unfilled += 1
    return unfilled > 0


async def _apply_exact_counts(
    client: ClinicalTrialsClient,
    base_spec: QuerySpec,
    group_by: GroupBy | None,
    buckets: list[Bucket],
) -> None:
    """Replace each bucket's sampled count with the API's exact countTotal (bounded parallel)."""
    if not buckets or group_by is None:
        return
    results = await _bounded_gather(
        [partial(exact_count, client, base_spec, group_by, b.label) for b in buckets],
        return_exceptions=True,
    )
    for bucket, result in zip(buckets, results, strict=True):
        if isinstance(result, int):
            bucket.value = result
    # Top-N dimensions may reorder once counts are exact; keep year/phase in their order.
    if group_by in (GroupBy.COUNTRY, GroupBy.SPONSOR, GroupBy.STATUS):
        buckets.sort(key=lambda b: b.value, reverse=True)


async def _run_relationship(
    spec: QuerySpec, client: ClinicalTrialsClient, repo: Repository
) -> PipelineResult:
    records, total = await cached_search(repo, client, spec)
    network = build_network(records)
    viz = build_network_visualization(spec, network, total, filters_summary(spec))
    viz.metadata.sampled = len(records)
    # Edge weights are shared-trial counts over the fetched sample, not the full population —
    # when the fetch cap is hit, say so rather than implying the weights are exhaustive.
    if len(records) < total:
        viz.metadata.bucket_set_complete = False
        viz.metadata.data_caveat = _join_caveat(
            viz.metadata.data_caveat,
            f"Network reflects a capped sample of {len(records)} of {total} matching trials; "
            "edge weights are sample counts, not population totals.",
        )
    citations = citations_from_links(network["links"], _by_nct(records))
    return viz, citations, total, records


# Which QuerySpec field each comparison dimension varies per entity.
_COMPARISON_FIELDS = {"intervention", "country", "condition", "sponsor"}
# Breakdown axes a comparison can use for its shared x-axis (the grouped-bar categories).
_COMPARISON_BREAKDOWNS = (GroupBy.PHASE, GroupBy.YEAR, GroupBy.STATUS)
_MAX_COMPARISON_BUCKETS = 12


def _ordered_comparison_labels(
    per_entity: dict[str, dict[str, Bucket]], group_by: GroupBy
) -> list[str]:
    """Ordered union of breakdown labels across entities (phase order / chronological / by size)."""
    labels = {label for buckets in per_entity.values() for label in buckets}
    if group_by == GroupBy.PHASE:
        return [p for p in PHASE_ORDER if p in labels]
    if group_by == GroupBy.YEAR:
        years = sorted(labels, key=lambda x: int(x) if x.isdigit() else 0)
        return years[-_MAX_COMPARISON_BUCKETS:]  # most recent window if many
    # status (or other): order by combined sample frequency, keep the busiest.
    freq: dict[str, float] = {}
    for buckets in per_entity.values():
        for label, bucket in buckets.items():
            freq[label] = freq.get(label, 0) + bucket.value
    return sorted(labels, key=lambda label: freq[label], reverse=True)[:_MAX_COMPARISON_BUCKETS]


async def _comparison_population(
    client: ClinicalTrialsClient, base: QuerySpec, dim: str, entities: list[str]
) -> int:
    """Deduplicated total trials across the compared entities.

    Summing per-entity totals double-counts any trial that studies two of them (e.g. a
    head-to-head metformin-vs-semaglutide trial). Instead we OR the entities into a single
    Essie expression on the comparison dimension and count once — each entity parenthesized so
    multi-word terms (e.g. "breast cancer") stay grouped. Falls back to the summed per-entity
    totals (an upper bound) if the union query errors.
    """
    union_expr = " OR ".join(f"({e})" for e in entities)
    union_spec = base.model_copy(update={dim: union_expr})
    try:
        return await client.count(union_spec)
    except Exception:  # noqa: BLE001 - fall back to a summed upper bound on any upstream failure
        totals = await _bounded_gather(
            [partial(client.count, base.model_copy(update={dim: e})) for e in entities]
        )
        return sum(t for t in totals if isinstance(t, int))


async def _run_comparison(
    spec: QuerySpec, client: ClinicalTrialsClient, repo: Repository
) -> PipelineResult:
    entities = spec.comparison_entities or ([spec.intervention] if spec.intervention else [])
    if len(entities) < 2:
        # Not enough to compare -> emit a valid single-series distribution bar, and say so.
        fallback = spec.model_copy(update={"query_type": QueryType.DISTRIBUTION, "group_by": None})
        viz, citations, total, records = await _run_chart(fallback, client, repo)
        viz.metadata.data_caveat = _join_caveat(
            viz.metadata.data_caveat,
            "Only one entity was identified, so this shows a single-series distribution instead "
            "of a comparison.",
        )
        return viz, citations, total, records

    dim = (spec.comparison_dimension or "intervention").lower()
    if dim not in _COMPARISON_FIELDS:
        dim = "intervention"
    # The shared x-axis: phase by default, but honor an explicit year/status breakdown so
    # "compare A vs B per year" or "...by status" work too — not just phase distributions.
    group_by = spec.group_by if spec.group_by in _COMPARISON_BREAKDOWNS else GroupBy.PHASE
    # Clear the dimension's own filter so it doesn't restrict every entity's fetch.
    base = spec.model_copy(update={dim: None, "group_by": group_by})
    sub_specs = {e: base.model_copy(update={dim: e}) for e in entities}

    # Sample each entity (bucket discovery + citation NCT IDs).
    samples = await _bounded_gather(
        [partial(cached_search, repo, client, sub_specs[e]) for e in entities]
    )
    all_records: list[TrialRecord] = []
    per_entity: dict[str, dict[str, Bucket]] = {}
    for entity, (records, _) in zip(entities, samples, strict=True):
        all_records.extend(records)
        per_entity[entity] = {b.label: b for b in aggregate(records, group_by)}

    labels = _ordered_comparison_labels(per_entity, group_by)

    # Exact count per (entity, bucket) and per-entity total — bounded parallel.
    pairs = [(e, label) for e in entities for label in labels]
    bucket_counts = await _bounded_gather(
        [partial(exact_count, client, sub_specs[e], group_by, label) for e, label in pairs],
        return_exceptions=True,
    )
    # A failed exact_count falls back to the entity's SAMPLE count (a real lower bound) rather than
    # a misleading 0; track which pairs are approximate so we can flag them.
    exact: dict[tuple[str, str], int] = {}
    approx: list[tuple[str, str]] = []
    for (entity, label), c in zip(pairs, bucket_counts, strict=True):
        if isinstance(c, int):
            exact[(entity, label)] = c
        else:
            sample = per_entity[entity].get(label)
            exact[(entity, label)] = int(sample.value) if sample else 0
            approx.append((entity, label))
    total = await _comparison_population(client, base, dim, entities)

    series: list[dict[str, Any]] = []
    comp_buckets: list[Bucket] = []
    jobs: list[BackfillJob] = []
    for label in labels:
        row: dict[str, Any] = {"bucket": label}
        for entity in entities:
            row[entity] = exact[(entity, label)]
            sample_bucket = per_entity[entity].get(label)
            bucket = Bucket(
                label=f"{entity} · {label}",
                value=exact[(entity, label)],
                nct_ids=sample_bucket.nct_ids if sample_bucket else [],
            )
            comp_buckets.append(bucket)
            jobs.append((bucket, sub_specs[entity], group_by, label))
        series.append(row)

    viz = build_comparison_visualization(spec, series, total, filters_summary(base), group_by)
    viz.metadata.sampled = len(all_records)
    trials_by_nct = _by_nct(all_records)
    unfilled = await _backfill_citations(client, jobs, trials_by_nct)
    if unfilled:
        viz.metadata.bucket_set_complete = False
    if approx:
        affected = ", ".join(sorted({label for _, label in approx}))
        viz.metadata.bucket_set_complete = False
        viz.metadata.data_caveat = _join_caveat(
            viz.metadata.data_caveat,
            f"Some counts couldn't be fetched and fall back to sampled (approximate) values: "
            f"{affected}.",
        )
    citations = build_citations(comp_buckets, trials_by_nct, group_by)
    return viz, citations, total, all_records


def _alternatives(spec: QuerySpec) -> list[AlternativeViz]:
    """Map the LLM's plausible alternative query types to selectable chart options."""
    seen: set[QueryType] = set()
    out: list[AlternativeViz] = []
    for qt in spec.alternative_query_types or []:
        if qt in (QueryType.UNSUPPORTED, spec.query_type) or qt in seen:
            continue
        chart = QUERY_TYPE_TO_CHART.get(qt)
        if chart is None:
            continue
        seen.add(qt)
        out.append(AlternativeViz(query_type=qt, chart=chart))
    return out


def _by_nct(records: list[TrialRecord]) -> dict[str, TrialRecord]:
    return {r.nct_id: r for r in records}


def _parameters(spec: QuerySpec) -> dict[str, Any]:
    group_by = spec.effective_group_by()
    return {
        "condition": spec.condition,
        "intervention": spec.intervention,
        "intervention_type": spec.intervention_type,
        "study_type": spec.study_type.value if spec.study_type else None,
        "sponsor": spec.sponsor,
        "country": spec.country,
        "status": spec.status,
        "start_year": spec.start_year,
        "end_year": spec.end_year,
        "group_by": group_by.value if group_by else None,
        "comparison_entities": spec.comparison_entities,
        "comparison_dimension": spec.comparison_dimension,
    }
