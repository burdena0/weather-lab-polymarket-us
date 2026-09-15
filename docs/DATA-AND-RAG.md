# Evidence, RAG and training data

## Start with retrieval, not fine-tuning

RAG supplies external evidence to a model at inference time; it does not update model weights. This release implements a local SQLite corpus with FTS5 full-text search and numeric weather-analogue selection. It requires no embedding API or vector database. That makes the first research comparison auditable and inexpensive.

The retrieval pipeline is:

1. Check immutable record ID, publication time, receipt time, available time, station, date and source.
2. Select only information available by the replay decision time. Historical outcomes must precede the target day. Forecasts in historical pairs must have been recorded before their own observation day.
3. Keep one latest eligible revision per historical station-day.
4. Rank historical examples by forecast-temperature similarity and seasonal distance; retrieve at most 30 by default.
5. Retrieve up to eight same-station rules/research chunks through BM25 lexical ranking with the same timestamp boundary.
6. Build a bounded context with source IDs. Reject model output that invents IDs. Record retrieval candidates, selected IDs, scores and input hash.

The numeric ranking is a fixed heuristic. It has not been optimized against the evaluation set. Dense semantic retrieval can be a future ablation, but it is not implemented or claimed here. For precise numerical station records, verified metadata and analogue distance may be more useful than semantic similarity; measure this rather than assuming it.

## Data to provide

| Dataset | Required content | Purpose |
| --- | --- | --- |
| Contract rules | US market ID/slug, raw description/hash, station, local observation date, units, exact inclusive interval, settlement source, close time, tick/minimum quantity | Prevent contracts with similar titles from being treated as equivalent |
| Forecast vintages | Model/product, station/grid mapping, issue time, first receipt time, target date, hourly temperatures, revisions; ideally ensemble members | Forecast input and historical forecast-error model |
| Station observations | Timestamp, source/product, correction flag, full-day/partial-day status, daily high with timezone | Distinguish current observed high from final CLI target |
| Final venue outcomes | US market ID/rules hash, final YES payout, receipt time, original source receipt | Score forecasts and settle paper inventory |
| Market microstructure | Full bid/offer depth, source timestamp, receipt timestamp, state, tick, quantity minimum, fee metadata | Delayed execution, liquidity and cost analysis |
| Wallet evidence | Public address, transaction ID, condition/token/outcome, trade time, first receipt time, price/quantity, reviewed US mapping | Deterministic copy control only |
| Model traces | Exact model, effort, prompt/code/data hashes, output, evidence IDs, tokens, delay, routing/escalation | Reproducibility and cost/error attribution |

Suggested research target: a full seasonal cycle or more of station history, plus a locked prospective evaluation window spanning many independent dates and weather regimes. This is a collection objective, not a claim that the necessary data are available or that a particular sample size guarantees statistical power. Determine sample size using pilot effect sizes and date-cluster dependence. Ten rows merely unlocks the software; it is not a publication-quality validation set.

Start with supported KNYC, KLAX, KSFO, KMIA and KMDW markets. Every station must match the actual US contract text. Do not substitute a nearby city station, a gridded forecast maximum, or international settlement rules for the venue's CLI target.

Public sources implemented: [Polymarket US market API](https://docs.polymarket.us/api-reference/market/overview), `api.weather.gov` station/point/hourly endpoints, and public international activity/Gamma metadata only for reference-wallet mapping. The bounded collector can reject same-day forecasts whose earlier hours are missing; an observed-high plus remaining-hours adapter is needed before making intraday whole-day forecasts. The collector does not manufacture the missing past hours.

## Historical JSONL format

One JSON object per line. See `examples/history.synthetic.jsonl` for executable examples. The fields below are all required for `kind:history`:

```json
{
  "evidence_id": "KNYC-2026-08-01-cli-v1",
  "kind": "history",
  "station": "KNYC",
  "date": "2026-08-01",
  "source": "NWS_CLI",
  "source_url": "https://api.weather.gov/products/REPLACE_WITH_REAL_PRODUCT_ID",
  "forecast_high_f": 80,
  "actual_high_f": 81,
  "forecast_issued": "2026-07-31T20:00:00Z",
  "forecast_received": "2026-07-31T20:00:10Z",
  "day_start": "2026-08-01T04:00:00Z",
  "day_end": "2026-08-02T04:00:00Z",
  "outcome_received": "2026-08-02T12:00:10Z",
  "published_at": "2026-08-02T12:00:00Z",
  "received_at": "2026-08-02T12:00:10Z",
  "available_at": "2026-08-02T12:00:10Z",
  "synthetic": false,
  "text": "Replace this example with verified product and forecast provenance."
}
```

The numbers above illustrate schema only; they are not observed records. Record correct station-local day boundaries in UTC, including daylight saving changes. Publication/receipt/available timestamps must be honest: do not assign an old receipt time to an archive first downloaded today. Archived evidence needs independently verified historical availability before a historical replay can use it. Keep the actual archive download receipt separately. A historical model output may still contain pretraining knowledge of old outcomes; point-in-time RAG alone cannot remove that contamination.

For rules, use `kind:rules` and the common ID/station/date/published/received/available/source_url/text fields. Chunk by contract clause or meteorological fact, at most 50 KB per record. Preserve exact wording, units and negation. Do not ingest the social post as weather evidence. A changed document requires a new `evidence_id`; old IDs cannot be overwritten. Human-reviewed data must retain reviewer and provenance information in additional fields.

```powershell
python -m weatherlab ingest --jsonl my-data/history-and-rules.jsonl --db data/evidence.sqlite
```

Alternatively use **Index evidence JSONL** in the dashboard. Synthetic rows are excluded automatically from real-data retrieval. Use a separate index for demos.

## Replay dataset

`examples/dataset.synthetic.json` defines the executable schema: `schema_version:1`, `venue:polymarket_us`, explicit `synthetic`, and chronological `frames`. Each frame has `at`, normalized `markets`, newly observed `signals`, and final `settlements`. Do not sort or rewrite bad clocks silently; validation rejects duplicate/non-increasing frame times. The public capture command creates this structure with receipt files. Append later final settlement envelopes from audited US venue evidence; temperature observations alone are not exchange settlement confirmation.

Wallet mapping lives in dashboard `data/reference-mappings.json`. Use an array of records with `condition_id`, `token`, `us_slug`, `reference_rules_hash`, `us_rules_hash`, `contract_identity:[station,date,lower_f,upper_f,"NWS_CLI"]`, `reviewed:true`, and `review_note`. The collector rechecks reference rules and token outcomes. This is an explicit human-reviewed mapping, not a semantic guess. Typical international hourly/Wunderground contracts may have no eligible match.

## Fine-tuning and learned routing later

Keep train/development/test splits chronological and grouped by observation date across stations. All buckets for the same station-day belong to one split. Tune retrieval, calibration and routing only on train/development; lock them before test. Prefer supervised examples of evidence selection, abstention and properly sourced probability reporting. Do not use fabricated chain-of-thought or profitable-wallet trades as correct forecast labels. Wallet profitability is not a weather outcome label.

Before fine-tuning an LLM, compare the empirical residual baseline, a calibrated statistical forecaster, and a fixed model with RAG. If model calibration helps, fit calibration only on development predictions. If routing helps, construct offline examples containing context features and every candidate model's held-out error, latency and cost, then optimize a predeclared cost/accuracy objective. Current routing is deterministic; no trained router or calibrator is included. Fine-tuning support and price depend on the model and must be checked before selecting a training API.

Measure retrieval separately with hand-labeled required evidence, recall at k, citation precision, temporal violations, station mismatches and abstention behavior. A citation's existence does not prove that the cited text supports the model's claim; human entailment audits remain necessary.
