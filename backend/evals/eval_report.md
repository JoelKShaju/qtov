# Classification eval report

- Model: `gpt-4o-mini`
- Cases: 36
- **Accuracy: 100.0%**  ·  Macro-F1: 1.00

## Per-query-type metrics

| query_type | precision | recall | f1 | support |
|---|---|---|---|---|
| `time_trend` | 1.00 | 1.00 | 1.00 | 5 |
| `distribution` | 1.00 | 1.00 | 1.00 | 5 |
| `comparison` | 1.00 | 1.00 | 1.00 | 5 |
| `geographic` | 1.00 | 1.00 | 1.00 | 5 |
| `relationship` | 1.00 | 1.00 | 1.00 | 5 |
| `correlation` | 1.00 | 1.00 | 1.00 | 5 |
| `unsupported` | 1.00 | 1.00 | 1.00 | 6 |

## Confusion matrix (rows = gold, cols = predicted)

```
      gold/pred |  TT  DI CMP GEO REL COR UNS
---------------------------------------------
 TT time_trend  |   5   0   0   0   0   0   0
 DI distributio |   0   5   0   0   0   0   0
CMP comparison  |   0   0   5   0   0   0   0
GEO geographic  |   0   0   0   5   0   0   0
REL relationshi |   0   0   0   0   5   0   0
COR correlation |   0   0   0   0   0   5   0
UNS unsupported |   0   0   0   0   0   0   6

Legend: TT=time_trend  DI=distribution  CMP=comparison  GEO=geographic  REL=relationship  COR=correlation  UNS=unsupported
```


## Data faithfulness (deterministic — no LLM/network)

- **Citation coverage: 100%** (7/7 value>0 data points cited; gate ≥ 100%)
- **Count reconciliation (time_trend): 1/1** (per-year exact counts sum to the reported total)
- Result: **PASS**
