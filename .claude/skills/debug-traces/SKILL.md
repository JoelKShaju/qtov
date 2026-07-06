---
name: debug-traces
description: Debug a failing or surprising /api/query result in the ClinicalTrials.gov agent using structured logs and Langfuse traces. Use when a query errors (422/502/503), returns an empty or wrong chart, or the agent misclassifies — to find the root cause from logs + the LLM trace.
---

# Debug with logs + traces

Use when a query in this project misbehaves (error, empty/wrong chart, bad classification).

## 1. Identify the request
- Every `POST /api/query` response includes a `trace_id` (also stored in `queries.trace_id`) — the **Langfuse/OTel trace id** for that request.
- Recent queries (id, type, supported, records, trace_id):
  ```
  curl -s localhost:8000/api/queries?limit=10 | python3 -m json.tool
  ```

## 2. Structured logs (stdout — NOT persisted)
JSON logs via structlog go to container stdout (no file/Loki). Read them with:
- `docker compose logs backend --since 15m`
- Errors only: `docker compose logs backend | grep -iE 'warning|error|failed'`
- Key events to look for (each line has `request_id`, `path`, `event`, `level`, timings):
  `agent.interpreted`, `agent.fetched`, `query.completed`, `agent.interpret_failed`,
  `agent.summarize_failed`, `cache.hit`, `cache.miss`, `db.init_failed`, `tracing.*`.

## 3. Langfuse trace (the LLM steps)
Requires the observability overlay running (`docker-compose.observability.yml`).
- UI: http://localhost:3001 → **Tracing** → open the trace whose id == the response `trace_id`.
  You'll see the `qtov.query` parent with `classifier` + `summarizer` children: model, prompt,
  completion, token usage, cost, latency, and any error.
- API:
  ```
  curl -s -u pk-lf-qtov-public:sk-lf-qtov-secret \
    "http://localhost:3001/api/public/traces/<trace_id>" | python3 -m json.tool
  ```

## 4. Common failure modes
| Symptom | Likely cause | Where to look |
|---|---|---|
| `422 unsupported_query` | capability gate (outside taxonomy) | response body; classifier span `query_type=unsupported` |
| `422` validation | blank / too-long query | request schema |
| `502 upstream_error` | ClinicalTrials.gov call failed | logs `UpstreamError`; httpx span in trace |
| `503 agent_error` | LLM call failed — bad/missing key, rate limit, **model access (e.g. gpt-4o 403)** | logs `agent.interpret_failed`; classifier span error |
| empty / tiny chart | no matching trials, or filters too narrow | `total_records`; `parsed_parameters` |
| wrong chart / filters | misclassification or hallucinated filter | `queries.parsed_parameters`; classifier span input/output |

## 5. See exactly what the agent decided
```
curl -s localhost:8000/api/queries/<id> | python3 -c 'import sys,json;print(json.dumps(json.load(sys.stdin)["parsed_parameters"],indent=2))'
```
This is the full `QuerySpec`: `query_type`, filters, `comparison_dimension`, `confidence`, `alternative_query_types`.

## Tips
- Logs correlate by `request_id` (also the `x-request-id` response header); traces by `trace_id`. Match by time if needed.
- Reproduce:
  ```
  curl -s localhost:8000/api/query -H 'content-type: application/json' -d '{"query":"..."}' | python3 -m json.tool
  ```
