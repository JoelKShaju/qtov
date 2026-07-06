# Deploying to Render

The repo ships a [`render.yaml`](render.yaml) blueprint that provisions the whole stack —
managed Postgres, the FastAPI backend (Docker), and the React frontend (static site) — in one
step. Budget ~10 minutes.

## Prerequisites

- A [Render](https://render.com) account (free tier is enough to start).
- An **OpenAI API key** with a spending cap set (see [step 4](#4-cap-the-openai-spend)).

## 1. Create the Blueprint

1. Push this repo to your own GitHub (already at `github.com/JoelKShaju/qtov`).
2. Render dashboard → **New → Blueprint** → connect the repo.
3. Render reads `render.yaml` and shows three resources: **qtov-db**, **qtov-api**, **qtov-web**.
   Approve to create them.

## 2. Set the OpenAI key

`OPENAI_API_KEY` is intentionally **not** in `render.yaml` (it's a secret). On the **qtov-api**
service → **Environment** → set `OPENAI_API_KEY` to your key → save. This triggers a redeploy.

## 3. Reconcile the URLs (if needed)

Render subdomains are globally unique, so `qtov-api` / `qtov-web` may already be taken and get a
suffix. After the first deploy, check the real URLs, then — only if they differ from the guesses
in `render.yaml` — update two values and redeploy:

| Service | Env var | Set to |
|---|---|---|
| qtov-api | `CORS_ORIGINS` | the **frontend** URL, e.g. `https://qtov-web-xyz.onrender.com` |
| qtov-web | `VITE_API_BASE` | the **backend** URL + `/api`, e.g. `https://qtov-api-xyz.onrender.com/api` |

`VITE_API_BASE` is baked in at build time, so changing it requires a **Clear cache & redeploy**
of qtov-web.

## 4. Cap the OpenAI spend

Every query runs two LLM calls, so a public URL is a spend risk. Two layers protect you:

- **Hard cap (do this):** OpenAI dashboard → **Billing → Limits** → set a low monthly hard limit
  (e.g. $5–10) on the key. This is the real safety net.
- **Rate limiting (already on):** `render.yaml` sets `RATE_LIMIT_ENABLED=true` and
  `RATE_LIMIT_PER_MINUTE=8` — a per-IP cap on `POST /api/query` (see `app/ratelimit.py`). Tune it
  in the qtov-api environment.

**Zero-cost alternative:** if you'd rather not expose your key at all, add a "bring your own key"
field to the UI and pass it through per request — the demo then costs you nothing.

## Free-tier caveats

- **Cold starts:** free web services sleep after ~15 min idle; the first request then takes ~30s.
  Fine for a portfolio link; upgrade qtov-api to a paid instance for always-on.
- **Database expiry:** Render's **free Postgres expires ~30 days** after creation. The app needs a
  live DB to serve queries (it persists each result), so upgrade the DB to keep the demo alive
  past a month, or recreate it.

## After it's live

Lead your resume's Projects entry with the URL, keeping the repo as secondary:

> **ClinicalTrials.gov Query-to-Visualization Agent** — `qtov-web.onrender.com` · `github.com/JoelKShaju/qtov`
