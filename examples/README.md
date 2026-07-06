# Example outputs

Real `POST /api/query` responses, one per supported query type, produced by running the
**full pipeline against the live ClinicalTrials.gov API** with the `gpt-4o-mini` classifier.
Regenerate with:

```bash
cd backend
set -a && . ../.env && set +a            # OPENAI_API_KEY
MAX_RECORDS=500 uv run python ../scripts/generate_examples.py
```

> Counts are live and will drift as ClinicalTrials.gov updates. `MAX_RECORDS=500` bounds the
> citation sample (and file size); the production default is 1000. Each shown bucket's value is
> an exact `countTotal`, independent of the sample (see `metadata.bucket_set_complete`).

| Query type        | Chart         | File |
|-------------------|---------------|------|
| `time_trend`      | line          | [`how-has-the-number-of-trials-for-pembrolizumab-changed-per-y.json`](how-has-the-number-of-trials-for-pembrolizumab-changed-per-y.json) |
| `distribution`    | bar           | [`how-are-diabetes-trials-distributed-across-phases.json`](how-are-diabetes-trials-distributed-across-phases.json) |
| `comparison`      | grouped bar   | [`compare-phases-for-trials-involving-metformin-vs-semaglutide.json`](compare-phases-for-trials-involving-metformin-vs-semaglutide.json) |
| `comparison` (year breakdown) | grouped bar | [`compare-the-number-of-metformin-vs-semaglutide-trials-per-ye.json`](compare-the-number-of-metformin-vs-semaglutide-trials-per-ye.json) |
| `geographic`      | bar           | [`which-countries-have-the-most-recruiting-trials-for-breast-c.json`](which-countries-have-the-most-recruiting-trials-for-breast-c.json) |
| `relationship`    | network       | [`show-a-network-of-sponsors-and-drugs-for-alzheimer-s-trials.json`](show-a-network-of-sponsors-and-drugs-for-alzheimer-s-trials.json) |
| `correlation`     | scatter       | [`is-there-a-relationship-between-enrollment-size-and-trial-du.json`](is-there-a-relationship-between-enrollment-size-and-trial-du.json) |

Each file is a complete `QueryResponse`: the agent's `interpretation`, the `visualization`
spec (type, `data`, `encoding`, `metadata`), the `citations` (every data point traced to its
NCT IDs, each with a supporting **excerpt**), and the narrated `summary`.
