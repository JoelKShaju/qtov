# ClinicalTrials.gov Query-to-Visualization Agent

Ask a natural-language question about clinical trials and get back a **structured, cited
visualization specification**. The backend is a traced, multi-step agent: it uses an LLM (via
[Pydantic AI](https://ai.pydantic.dev)) to interpret the question into a **closed set of supported
query types**, queries the [ClinicalTrials.gov v2 API](https://clinicaltrials.gov/data-api/api),
aggregates the results deterministically, and returns a chart spec where **every data point is
traceable back to the trials (NCT IDs) that produced it, with a supporting text excerpt**.

```
NL query ─▶ interpret + classify (Pydantic AI)  ─▶ capability gate (reject unsupported → 422)
        ─▶ fetch ClinicalTrials.gov (read-through cache) ─▶ aggregate + cite ─▶ visualization spec
        ─▶ narrate (2nd agent) ─▶ JSON response  ─▶ UI (React + ECharts)
```

A small React UI (the optional "demo" deliverable) renders the spec and lets you click any data
point to open its source trail. The agent's output is **frontend-agnostic** — the contract is
documented under [API](#api) and [Data models](#data-models).

- **Inputs / outputs** → [API](#api) · full schema reference → [Data models](#data-models)
- **How to run** → [Quick start](#quick-start)
- **Example queries with real JSON outputs** → [`examples/`](examples/)
- **Design decisions & trade-offs** → [Design decisions](#design-decisions--trade-offs)
- **AI tools / validation / integrity** → [Integrity note](#integrity-note-ai-tool-use)

---

## Quick start

Requires Docker. You need an **OpenAI API key** for live query interpretation (this project's key
has access to `gpt-4o-mini`, the configured default — see [Models](#models)).

```bash
make up                       # first run: auto-creates .env, then STOPS until you add a key
```

On the **first run**, `make up` copies `.env.example → .env` for you and then **fails fast** with a
message if `OPENAI_API_KEY` is unset — so the stack never boots silently without a key. Add your key
and re-run:

```bash
#  → open .env and set OPENAI_API_KEY=sk-...
make up                       # build + run the full stack; `make down` stops it all
```

`make up` runs the whole stack together — backend, frontend, Postgres, **and** the Langfuse
observability overlay — and `make down` stops it all. (`.env` is created only if absent — an existing
one is never overwritten; the check lives in the `ensure-env` Make target, a prerequisite of `up`.)

> In **Claude Code**, the [`start-stack`](.claude/skills/start-stack/SKILL.md) skill does all of this
> for you — ask it to "start the stack" and it builds + runs everything, waits for health, prints the
> URLs below, and tails the logs.

- Frontend (UI): http://localhost:5173
- API docs (Swagger): http://localhost:8000/docs
- Health: http://localhost:8000/api/health
- Langfuse (traces): http://localhost:3001

Try it:
```bash
curl -s localhost:8000/api/query -H 'content-type: application/json' \
  -d '{"query":"How are diabetes trials distributed across phases?"}' | jq .
```

### Local development (host, fastest iteration)

```bash
make install   # uv sync (backend) + npm install (frontend)
make db        # start only Postgres
make dev       # backend (:8000) + frontend (:5173) together; Ctrl-C stops both
```

Other targets: `make test`, `make lint`, `make seed` (warm the cache with demo queries),
`make evals` (classification + data-faithfulness eval). Run `make help` for the full list.

### Configuration

All config is environment-driven (`backend/app/config.py`); copy `.env.example` → `.env`.

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | — | **Required** for live interpretation/summarization. |
| `OPENAI_MODEL` | `gpt-4o-mini` | Single-model default for **both** agents. |
| `CLASSIFIER_MODELS` | _(unset → `OPENAI_MODEL`)_ | Optional ordered fallback chain for the classifier only. |
| `SUMMARIZER_MODELS` | _(unset → `OPENAI_MODEL`)_ | Optional ordered fallback chain for the summarizer only. |
| `DATABASE_URL` | `postgresql+asyncpg://…/qtov` | Postgres connection. |
| `MAX_RECORDS` | `1000` | Per-query cap on records fetched for discovery/citations. |
| `PAGE_SIZE` | `200` | ClinicalTrials.gov page size. |
| `UPSTREAM_CONCURRENCY` | `8` | Max concurrent upstream requests in a query's count fan-out (top-N / comparison). |
| `UPSTREAM_MAX_RETRIES` | `3` | Retries for transient upstream failures (429/5xx/timeouts). |
| `UPSTREAM_BACKOFF_BASE` / `UPSTREAM_BACKOFF_CAP` | `0.5` / `8.0` | Exponential-backoff seconds (honors `Retry-After`). |
| `CACHE_TTL_SECONDS` | `86400` | Freshness window for the read-through cache. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` / `LOGFIRE_TOKEN` | — | Optional LLM tracing export (see [Observability](#observability)). |

---

## API

### `POST /api/query`

**Request.** Only `query` is required. Every other field is an **optional structured filter** that,
when supplied, is authoritative and overrides whatever the LLM infers from the prose.

```jsonc
{ "query": "How are diabetes trials distributed across phases?",
  "condition": "diabetes",            // all fields below are optional
  "drug_name": "metformin",           // alias for `intervention`
  "intervention_type": "Drug",        // Drug | Biological | Device | Procedure ...
  "study_type": "Interventional",     // Interventional | Observational
  "sponsor": "Mayo Clinic",
  "country": "United States",
  "trial_phase": "Phase 3",           // alias for `phase`
  "status": ["RECRUITING"],           // overall-status enums
  "start_year": 2015, "end_year": 2024,
  "date_range": { "from": "2015", "to": "2024" }  // alternative to start_year/end_year
}
```

**Response (HTTP 200).** A structured visualization plus the agent's interpretation, citations, and
a short narration. Truncated:

```jsonc
{
  "event_id": "4f80…",                  // shareable id; permalink is /<event_id> in the UI
  "query": "How are diabetes trials distributed across phases?",
  "interpretation": {
    "query_type": "distribution",
    "parameters": { "condition": "diabetes", "group_by": "phase", "...": null },
    "reasoning": "Counts trials per phase.",
    "confidence": 1.0,
    "alternatives": []                   // one-click alternate readings: [{query_type, chart}]
  },
  "visualization": {
    "type": "bar",
    "title": "Diabetes trials by phase",
    "data": [ { "x": "Phase 3", "y": 83 }, ... ],
    "encoding": { "x": {"field":"x","type":"ordinal"}, "y": {"field":"y","type":"quantitative"} },
    "metadata": {
      "total_records": 24004, "sampled": 1000, "bucket_set_complete": true,
      "data_caveat": null, "filters_applied": "condition=diabetes",
      "source": "ClinicalTrials.gov", "timestamp": "...",
      "chart_config": { "x_label": "Phase", "y_label": "Number of trials", "x_axis_rotation": 0 }
    }
  },
  "citations": [
    { "bucket": "Phase 3", "value": 83, "nct_ids": ["NCT01234567", ...],
      "trials": [ { "nct_id": "NCT01234567", "title": "...",
                    "url": "https://clinicaltrials.gov/study/NCT01234567",
                    "excerpt": "Phase: Phase 3" } ] }    // ← excerpt = the field/value backing the datum
  ],
  "summary": "Phase 3 dominates with 83 trials (NCT…). ...",
  "trace_id": "019f…"
}
```

**Error (HTTP 422) — unsupported query.** Rejected *before* any external fetch (the capability gate):

```jsonc
{ "error": "unsupported_query",
  "message": "I can't answer that...",
  "supported_query_types": [ { "type": "time_trend", "example": "..." }, ... ],
  "event_id": "..." }
```

Upstream/agent failures surface as `502 {error:"upstream_error"}` and `503 {error:"agent_error"}`.

**Other endpoints:** `GET /api/health`, `GET /api/queries?limit=N` (history),
`GET /api/queries/{id}`, `GET /api/events/{event_id}` (full saved result for a permalink).

A ready-to-import **Postman/Insomnia collection** (v2.1) lives at
[`scripts/qtov.postman_collection.json`](scripts/qtov.postman_collection.json).

---

## Supported query types & visualization coverage

The agent answers exactly these (a **closed taxonomy**); anything else returns a friendly 422 listing
what it *can* do. The `query_type → chart` mapping is fixed in code — the LLM only classifies and
extracts filters; it never picks a chart type or invents data.

| Query type     | Chart        | Example |
|----------------|--------------|---------|
| `time_trend`   | line         | *How has the number of trials for pembrolizumab changed per year since 2015?* |
| `distribution` | bar          | *How are diabetes trials distributed across phases?* |
| `comparison`   | grouped bar  | *Compare phases for metformin vs semaglutide.* — breakdown axis can be **phase, year, or status** |
| `geographic`   | bar          | *Which countries have the most recruiting trials for breast cancer?* |
| `relationship` | network      | *Show a network of sponsors and drugs for Alzheimer's trials.* |
| `correlation`  | scatter      | *Is there a relationship between enrollment size and trial duration for diabetes trials?* |

This spans the visualization breadth the assignment calls for — **bar, line/time-series, scatter,
and network** — plus grouped bar for comparisons. Adding a type = one enum value + one aggregation.

---

## Deep citations (bonus: source traceability)

Every data point — each bar, line vertex, grouped column, scatter point, and network node/edge —
carries the exact list of NCT IDs that produced it, **plus a dimension-aware `excerpt`**: the
specific field/value from each trial's API record that supports the datum.

| Data point     | Example `excerpt` |
|----------------|-------------------|
| Phase bucket   | `Phase: Phase 3` |
| Year bucket    | `Start date: 2019-04` |
| Country bucket | `Locations: United States` |
| Sponsor bucket | `Lead sponsor: Mayo Clinic` |
| Network edge   | `Sponsor: Pfizer · interventions: Metformin` |
| Scatter point  | `Enrollment: 420; 2019-01 → 2021-06 (29 months)` |

In the UI, click any data point to open the **source trail** drawer (links to ClinicalTrials.gov,
each with its excerpt). Citations are also returned inline and persisted to `query_citations`.

---

## Example queries and outputs

[`examples/`](examples/) contains **real `POST /api/query` responses** — one per query type — produced
by running the full pipeline against the live ClinicalTrials.gov API. Each file is a complete
`QueryResponse` (interpretation + visualization spec + citations with excerpts + narration).
Regenerate with `cd backend && MAX_RECORDS=500 uv run python ../scripts/generate_examples.py`.

> Counts are live and will drift as ClinicalTrials.gov updates. Each shown bucket's value is an exact
> `countTotal` (see [Design decisions](#design-decisions--trade-offs)).

---

## Architecture

Three application containers, wired by `docker compose` (plus a Langfuse observability overlay that
`make up` starts alongside them):

| Service    | Stack                                            | Role |
|------------|--------------------------------------------------|------|
| `backend`  | Python · FastAPI · Pydantic AI · SQLAlchemy      | Agent pipeline + REST API |
| `frontend` | React · Vite · TypeScript · Tailwind · ECharts   | Query UI + charts + citations drawer |
| `db`       | Postgres                                         | Trial + search-result cache · query history · citations |

The agent pipeline (`backend/app/agent/orchestrator.py`) runs as discrete, traced steps:

1. **Interpret & classify** — Pydantic AI returns a schema-validated `QuerySpec`
   (`app/agent/interpreter.py`). Deterministic keyword detectors complement the model for ambiguous
   intents and comparison breakdown axes.
2. **Capability gate** — queries outside the taxonomy are rejected with **HTTP 422** *before* any
   external fetch or DB write (`app/validation.py`).
3. **Fetch (read-through cache)** — `app/clients/clinicaltrials.py` maps the spec to v2 params,
   paginates, normalizes each study; wrapped by `app/services/search_cache.py` (see [Caching](#caching)).
4. **Aggregate + cite** — deterministic group-by (`app/services/aggregate.py`, `scatter.py`,
   `network.py`) keeping contributing NCT IDs + excerpts per point (`app/services/citations.py`).
5. **Visualize** — assemble the chart spec, encoding, and config (`app/services/visualize.py`).
6. **Narrate** — a second agent writes a short, source-cited analysis (`app/agent/summarize.py`); a
   post-hoc sanitizer strips any NCT ID it didn't actually receive.
7. **Persist** — query history + citations + a shareable result snapshot (`app/db/`).

### Models

Both agents default to **`gpt-4o-mini`** (the model this project's key can access); it classifies and
summarizes reliably with the structured-output prompts here. **`OPENAI_MODEL` is the one knob** that
sets the model for both — e.g. `OPENAI_MODEL=gpt-4o` switches both agents (once your key has access).
The LLM layer (`app/agent/llm.py`) is model-agnostic: `run_structured` / `run_text` accept an **ordered
list of models** and fall back on failure (with a per-model retry). To override just one agent with a
fallback chain, set `CLASSIFIER_MODELS` / `SUMMARIZER_MODELS` (CSV, first = primary); whichever is left
unset follows `OPENAI_MODEL`. Any `provider:model` string works, so another provider drops in with no
code change.

---

## Data models

Full request/response contract (Pydantic in `backend/app/schemas/`, mirrored in TypeScript at
`frontend/src/lib/types.ts`), so a frontend engineer can implement a renderer without reading the
backend.

### Enumerations

| Enum         | Values |
|--------------|--------|
| `QueryType`  | `time_trend`, `distribution`, `comparison`, `geographic`, `relationship`, `correlation`, `unsupported` |
| `ChartType`  | `line`, `bar`, `grouped_bar`, `network`, `scatter` |
| `GroupBy`    | `year`, `phase`, `country`, `sponsor`, `status` |
| `StudyType`  | `Interventional`, `Observational` |

`query_type → chart` is fixed: `time_trend→line`, `distribution→bar`, `comparison→grouped_bar`,
`geographic→bar`, `relationship→network`, `correlation→scatter`.

### Request — `QueryRequest`

| Field | Type | Notes |
|---|---|---|
| `query` | string (3–500) | **Required** natural-language question. |
| `condition` | string? | Disease/condition filter. |
| `intervention` | string? | Drug/intervention filter. Alias: **`drug_name`**. |
| `intervention_type` | string? | `Drug` \| `Biological` \| `Device` \| `Procedure` … |
| `study_type` | `StudyType`? | |
| `sponsor` | string? | Sponsor/organization. |
| `country` | string? | |
| `phase` | string? | e.g. `Phase 3`. Alias: **`trial_phase`**. |
| `status` | string[]? | Overall-status enums, e.g. `["RECRUITING"]`. |
| `start_year` / `end_year` | int? | Start-year bounds. |
| `date_range` | `{from, to}`? | ISO date/year bounds; alternative to `start_year`/`end_year`. |
| `force_query_type` | `QueryType`? | Pin a type (used when the user picks an alternative chart). |

### Interpretation — `QuerySpec` (LLM structured output)

The agent's validated reading of the query, surfaced to clients as `interpretation`: `query_type`,
`confidence` (0–1), `alternative_query_types[]`, `supported`, `rejection_reason?`, the extracted
filters (the `QueryRequest` fields above), `group_by?`, `comparison_entities[]?`,
`comparison_dimension?`, `title`, `reasoning`.

### Response — `QueryResponse`

| Field | Type | |
|---|---|---|
| `event_id` | string | Shareable id; permalink `/<event_id>`. |
| `query` | string | Echo of the request. |
| `interpretation` | `Interpretation` | `{ query_type, parameters, reasoning, confidence, alternatives[] }` |
| `visualization` | `Visualization` | See below. |
| `citations` | `Citation[]` | Source trail per data point. |
| `summary` | string | Short, source-cited narration. |
| `trace_id` | string? | Links to the LLM/agent trace. |

**`Visualization`** = `{ type: ChartType, title, data, encoding, metadata }`, where `encoding` is
`{ x?, y?, color? }` (each axis `{ field, type }`, `type ∈ temporal|ordinal|nominal|quantitative`).

**`VizMetadata`**: `total_records` (true total), `sampled` (records fetched, ≤ `MAX_RECORDS`),
`bucket_set_complete` (is the displayed bucket *set* exhaustive), `data_caveat` (e.g. a time trend's
in-progress/projected-year note), `filters_applied`, `source`, `timestamp`,
`chart_config { x_label, y_label, x_axis_rotation, time_format? }`.

**`data` shape by chart type:**

| `type` | `data` shape |
|---|---|
| `line` / `bar` | `[{ "x": string\|number, "y": number, "partial"?, "projected"? }]` |
| `grouped_bar` | `[{ "bucket": string, "<entity>": number, … }]` (one numeric column per compared entity) |
| `scatter` | `[{ "nct_id", "title", "phase", "x": enrollment, "y": duration_months }]` |
| `network` | `{ "nodes":[{id,name,category,value,nct_ids[]}], "links":[{source,target,value,nct_ids[]}], "categories":[{name}] }` |

**`Citation` / `TrialRef`**: `{ bucket, value, nct_ids[], trials: [{ nct_id, title, url, excerpt }] }`.
`bucket` matches the clicked chart label (`grouped_bar` → `"<entity> · <bucket>"`; `scatter` → the
`nct_id`; `network` → `"<source> → <target>"`). `trials` is capped (default 25/bucket) while
`nct_ids` lists every contributor.

---

## Design decisions & trade-offs

- **Pydantic AI for structured output** — type-safe, auto-validating, auto-retrying, and testable
  without a live LLM (`TestModel`). Far less brittle than hand-parsing tool-call JSON.
- **Closed taxonomy + capability gate** — predictable behavior and graceful failure. The LLM
  classifies; a fixed map picks the chart, so it can't hallucinate an unsupported chart type.
- **Deterministic pipeline after interpretation** — fetch / aggregate / visualize are pure Python,
  which makes results reproducible, fast, and exactly citable (no LLM in the data path).
- **Exact counts, bounded fetch, honest coverage.** A sample fetch (≤ `MAX_RECORDS`) discovers which
  buckets to show and supplies citation NCT IDs; each bucket's value is then replaced by an exact
  `countTotal` query (one tiny `pageSize=1` request per bucket, fanned out in parallel but bounded by
  `UPSTREAM_CONCURRENCY` so a wide query can't hammer or get throttled by CT.gov). Phase distributions
  enumerate the **full phase enum** (complete *and* exact). For open-ended top-N (country/sponsor) the
  bucket *set* still comes from the sample, so `metadata.bucket_set_complete=false` is set — each shown
  count is exact, but the long tail may be unrepresented. (The CT.gov v2 API has no query-scoped
  faceting, so exact top-N for free-text fields isn't available upstream.) **Every datum stays
  citable:** a bucket whose exact count is `>0` but that didn't surface in the capped sample (so it has
  no sampled NCT IDs) gets its citations **backfilled** with a small per-bucket fetch — no empty source
  trails.
- **Honest fallbacks, not silent ones.** When a comparison has only one entity it's rendered as a
  single-series distribution, and when an exact-count call fails upstream the cell falls back to the
  entity's **sample count** (a real lower bound) rather than a misleading `0`. Both are surfaced in
  `metadata.data_caveat` (and flip `bucket_set_complete` to `false`) instead of happening invisibly.
- **Resilient upstream client.** ClinicalTrials.gov calls retry transient failures (429/5xx/timeouts)
  with bounded exponential backoff (honoring `Retry-After`), fail fast on 4xx, and turn a malformed
  non-JSON body into a clean `UpstreamError` — all via one shared request helper used by every call.
- **Representative scatter sampling.** A scatter has one point *per trial* (no exact per-bucket
  count to fall back on), so it's inherently sample-bounded at `MAX_POINTS`. When more trials are
  plottable than the cap, points are drawn by a **deterministic uniform random subsample** (fixed
  seed) rather than top-N by enrollment — so the visible enrollment-vs-duration cloud stays unbiased
  instead of skewing toward mega-trials.
- **Generalized comparisons.** A comparison's grouped-bar x-axis is the *breakdown* dimension —
  phase by default, but `year` ("…per year") or `status` ("…by status") when asked — independent of
  the `comparison_dimension` (what the entities *are*).
- **Time-trend recency honesty.** Trials carry anticipated start dates, so the current/future year
  buckets are incomplete. They're flagged (`partial`/`projected` on the points + a `data_caveat`), the
  chart dims/annotates them, and the summarizer is told not to read them as a decline.
- **Read-through cache** (not a write-only log) — see [Caching](#caching).
- **API response is the source of truth — no entity normalization.** ClinicalTrials.gov intervention
  names are free text (no controlled vocabulary), so the same drug can appear under variant spellings.
  We keep them **verbatim** as distinct network nodes rather than guess they're the same — preserving
  fidelity. The network's only filtering is by relevance (`DRUG`/`BIOLOGICAL` types, drop placebo/sham).
- **Lean persistence.** Five small tables; nothing enabled that isn't used (an earlier `pgvector`
  scaffold was removed once it wasn't wired up). Schema: [`backend/app/db/README.md`](backend/app/db/README.md).

### Caching

The trial store is a real **read-through cache** (`app/services/search_cache.py`). Each search is keyed
by a hash of its exact API params: a **miss** calls ClinicalTrials.gov, normalizes, and records both the
trials and the result set; a fresh **hit** (within `CACHE_TTL_SECONDS`) re-hydrates the trial records
from Postgres and skips the API entirely. Exact per-bucket counts are intentionally **not** cached, so
chart values stay live even on a hit. A per-request lock serializes the async DB session (the comparison
path fans out fetches concurrently).

---

## Observability

- **Structured logging** — `structlog` JSON logs with a per-request `x-request-id` and per-step
  timings/events (`agent.interpreted`, `agent.fetched`, `cache.hit/miss`, `query.completed`, …).
- **LLM/agent tracing** — Pydantic AI's OpenTelemetry instrumentation captures each agent step
  (prompts, tokens, latency). `make up` runs a **self-hosted Langfuse** overlay alongside the app, so
  tracing works out of the box. Open Langfuse at http://localhost:3001 and log in with the seeded dev
  account **`admin@example.com` / `changeme123`** → *Tracing*; each request shows `classifier` +
  `summarizer` spans. The org, project, and API keys are auto-seeded on first boot
  (`LANGFUSE_INIT_*` in `docker-compose.observability.yml`) and the backend authenticates with them
  automatically — nothing to register or configure. `make down` stops it together with the app (add
  `ARGS=-v` to wipe trace data). To use managed Langfuse/Logfire/Datadog instead, set `LOGFIRE_TOKEN`
  or point `OTEL_EXPORTER_OTLP_ENDPOINT` at them.

  > These Langfuse credentials/keys (plus the hardcoded `SALT` / `NEXTAUTH_SECRET` / `ENCRYPTION_KEY`)
  > are **dev-only** — for any shared deployment, swap in real secrets via a manager (see
  > [Secrets & config](#secrets--config)).

  > Langfuse is heavy (web/worker + Postgres + ClickHouse + Redis + MinIO). To run just the app
  > without it: `docker compose up --build` (and `docker compose down`) — the base compose file only.

---

## Production readiness & future work

This is a take-home; below is what I'd add to run it as a real service. Focused on the **backend and
database**, roughly in priority order. Deliberately out of scope here so nothing is advertised that isn't
actually wired up.

### API & backend

- **Horizontal autoscaling on request load.** The FastAPI app is stateless, so it scales out behind a
  load balancer. Each request is I/O-bound (LLM + ClinicalTrials.gov calls), so autoscale on **in-flight
  requests / RPS and p95 latency** rather than CPU (K8s HPA on a custom RPS metric, or ECS service
  auto-scaling). Pair with a bounded request queue + max-concurrency so traffic bursts shed load
  gracefully instead of timing out.
- **Rate limiting, backpressure & an upstream circuit breaker.** Bounded retry/backoff on the CT.gov
  client is already in place; what remains for scale is per-client token-bucket limits to protect the
  service and a **global** limiter + circuit breaker around ClinicalTrials.gov (today
  `UPSTREAM_CONCURRENCY` bounds fan-out *per request*, not across concurrent requests), plus backoff
  jitter.
- **Auth & multi-tenancy.** API keys / OAuth2 / JWT, per-tenant quotas and isolation, tighter CORS
  (currently `*`), request-size limits, and per-route timeouts.
- **Async job path for heavy queries.** Wide comparisons / large network builds can be slow; move them
  to a worker (Arq / Celery / RQ) with a job-status endpoint or streamed responses, keeping API nodes
  responsive.
- **LLM cost & resilience.** Cache classifications (identical query → skip the LLM), enforce per-tenant
  token budgets, and alert on token/cost (Langfuse already reports cost per trace). The model fallback
  chain is in place; add provider-level failover.

### Database & data

- **Indexing.** Add btree indexes on the columns we filter/sort — `query_citations(query_id)` (FK),
  `queries(created_at)`, `events(created_at)`, `trials(start_year)`, `trials(lead_sponsor)`,
  `search_cache(fetched_at)` (TTL sweeps) — and **GIN** indexes on the JSONB columns we query
  (`trials.conditions`, `trials.interventions`). `create_all` builds none of these today.
- **Versioned migrations.** Replace `Base.metadata.create_all` with **Alembic** so schema changes are
  reviewed, ordered, and reversible (no destructive recreate).
- **Scheduled ingestion instead of lazy-on-query.** Bulk-load ClinicalTrials.gov (full export +
  incremental updates) into `trials` on a schedule. This is the biggest correctness win: with all
  matching data local we can compute **exact server-side aggregations** and drop the open-ended top-N
  sampling caveat (`bucket_set_complete=false`) entirely, and precompute **materialized-view rollups**
  for hot aggregations (counts by phase / year / country) refreshed on ingest.
- **Partitioning & retention.** Partition `trials` by `start_year` and the time-series tables
  (`queries`, `events`) by `created_at`; add retention/TTL jobs to prune old events and expire
  `search_cache`. Route read-heavy history/aggregation queries to **read replicas**.
- **Connection pooling.** Tune the asyncpg pool and front it with **PgBouncer** at scale. The current
  per-request `asyncio.Lock` around the session is a correctness stopgap for the concurrent comparison
  fan-out; pooled connection-per-task (or moving cache reads off the session — see Redis) removes it.
- **Managed Postgres.** RDS / Cloud SQL with automated backups, point-in-time recovery, and HA failover.
- **Domain enrichment.** Drug-name normalization (e.g. RxNorm) to merge free-text intervention spelling
  variants, and semantic search / RAG (re-enable `pgvector`, embed condition/intervention text) for
  fuzzy matching and "related trials".

### Caching → Redis

Move the read-through search cache (and optionally full `QueryResponse`s keyed by query hash) from the
Postgres `search_cache` table to **Redis**: native TTL, sub-millisecond reads, shared across all app
instances, and no DB-session contention — which also retires the per-request lock above. Postgres stays
the durable trial store + query history; Redis becomes the hot cache. Exact per-bucket counts could live
there too under a short TTL while keeping chart values fresh.

### Secrets & config

Get secrets out of `.env` and images. Use **[Infisical](https://infisical.com)** or a cloud-native
manager (**AWS Secrets Manager / GCP Secret Manager / HashiCorp Vault**) to inject `OPENAI_API_KEY`, DB
credentials, and Langfuse keys at runtime, with **rotation** and per-environment scoping — nothing
secret in the repo, compose files, or built images.

### Observability & ops

OTel tracing is already wired (Langfuse). Add **Prometheus metrics** (RPS, latency histograms,
cache hit-ratio, upstream error rate, LLM token/cost), **SLO-based alerting**, ship structured logs to a
sink (Loki / Datadog), and harden the deployment: distinct liveness vs. readiness probes (readiness gates
on DB + secret availability), graceful-shutdown draining of in-flight requests, non-root slim images,
image/dependency scanning, and an SBOM in CI.

---

## Testing & validation

```bash
make test     # backend pytest — no DB / LLM / network needed (externals mocked)
make lint     # ruff + mypy (backend) + tsc (frontend)
```

The suite (93 tests) covers normalization (incl. enrollment/duration), param mapping (incl. phase
filters + injection-safe sanitization), every aggregation, all visualization specs (incl. scatter
subsampling, generalized comparison, and time-trend recency flags), citations **and their excerpts**
**+ backfill of unsampled buckets**, the read-through cache (hit / stale / evicted), the upstream
client's **retry/backoff + malformed-JSON + pagination-cap** behavior, the bounded count fan-out, the
**single-entity downgrade and sample-count fallback caveats**, comparison-breakdown inference,
**model-config precedence** (`OPENAI_MODEL` vs the per-agent chains), **time-trend count reconciliation**,
the two-layer validation gate, and a full `POST /api/query` integration test (LLM mocked via Pydantic
AI's `TestModel`, the upstream API via `respx`, the DB via an in-memory repository).

Beyond unit tests, every supported query type was **validated end-to-end against the live API** — see
[`examples/`](examples/) for the captured outputs.

### Evals (measured, not asserted)

`make evals` runs two layers, writing a snapshot to [`evals/eval_report.md`](backend/evals/eval_report.md):

1. **Classification** — the interpreter over a labeled **golden set**
   ([`evals/golden_set.py`](backend/evals/golden_set.py) — 36 queries, paraphrases + tricky cases like
   medical advice and free-text summaries), reporting accuracy, per-query-type precision/recall/F1, and
   a confusion matrix. This is a small curated regression/smoke set measuring **query-type
   classification only** — not visualization correctness, citation coverage, or count reconciliation
   (those are layer 2). Needs `OPENAI_API_KEY` (skips loudly without it).
2. **Data faithfulness** — deterministic (no LLM/network): runs the real orchestrator over fixtures
   ([`evals/faithfulness.py`](backend/evals/faithfulness.py)) and gates on **citation coverage** (every
   `value>0` datum is cited; default 100%) and **count reconciliation** for `time_trend` (per-year exact
   counts sum to the total). Reconciliation is intentionally *not* asserted for phase/geographic, where
   a trial belongs to multiple buckets so the sum legitimately exceeds the total.

Latest classification snapshot (query-type classification only, 36-example curated set):

| | |
|---|---|
| Model | `gpt-4o-mini` |
| Accuracy | **100%** (36/36) · Macro-F1 1.00 |
| Per-class | precision/recall/F1 = 1.00 across all 7 query types (incl. `unsupported`) |

Both eval layers are unit-tested ([`tests/test_evals_metrics.py`](backend/tests/test_evals_metrics.py),
[`tests/test_faithfulness.py`](backend/tests/test_faithfulness.py)) and gate CI: faithfulness always
(exit non-zero below `EVAL_MIN_COVERAGE`, default 1.0, or on a reconciliation failure), and
classification below `EVAL_MIN_ACCURACY` (default 0.85) when a key is present.

---

## Project tooling (optional)

Three Claude Code skills assist development:
[`start-stack`](.claude/skills/start-stack/SKILL.md) brings the whole stack up, waits for health, and
tails the logs; [`query-to-image`](.claude/skills/query-to-image/SKILL.md) renders a query's chart to a
PNG (all five chart types); and [`debug-traces`](.claude/skills/debug-traces/SKILL.md) walks logs +
Langfuse traces to root-cause a failing/surprising query.

> The `.claude/skills/` format is Claude Code-specific, but each skill is a thin wrapper over plain
> `make` targets / `scripts/` — so it's straightforward to make these provider-agnostic: keep the logic
> in those runnable artifacts (plus an `AGENTS.md`), and point other tools' rule files
> (`.cursor/rules/`, `.github/copilot-instructions.md`, …) at the same commands.

---

## Integrity note (AI tool use)

Per the assignment's integrity note:

- **Tools used.** Built with the assistance of AI coding tools (Claude Code). Key dependencies:
  FastAPI, Pydantic AI, SQLAlchemy, httpx, structlog (backend); React, Vite, Apache ECharts, Tailwind
  (frontend). Data: ClinicalTrials.gov API v2.
- **How correctness was validated.** Field paths verified against the live API; a 93-test pytest suite
  (mocked LLM/API/DB) plus `ruff`/`mypy`/`tsc` in CI; a two-layer eval ([`evals/eval_report.md`](backend/evals/eval_report.md)):
  **classification** — a small, curated 36-example golden set measuring query-type classification *only*
  (accuracy/precision/recall + a confusion matrix; it does **not** measure visualization correctness),
  and **data faithfulness** — deterministic citation-coverage plus, for time trends, count
  reconciliation (the per-bucket exact counts sum to the reported total), asserted by
  `tests/test_faithfulness.py` and `tests/test_api.py::test_time_trend_counts_reconcile_with_total`;
  and end-to-end validation of every supported query type against the live ClinicalTrials.gov API
  (outputs in [`examples/`](examples/)).
- **Designed deliberately vs. generated.** The architecture and engineering decisions were designed
  deliberately: the closed-taxonomy + capability-gate model, the deterministic-after-interpretation
  pipeline, the exact-count strategy and `bucket_set_complete` honesty, the citation/excerpt model, the
  read-through cache, and the time-trend recency handling. AI assistance was used to generate and adapt
  implementation details (boilerplate, schema/test scaffolding, rendering code) against those decisions,
  which were then reviewed and validated.
```
