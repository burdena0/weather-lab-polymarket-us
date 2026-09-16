# August 2026 historical test

## Setup prerequisites — separate from the experiment instructions

1. Open the Weather Lab folder and check Python works.
2. **Baseline only:** no API key, paid service, or linked account is required.
3. **Cloud models:** first complete sections 2, 3 and 6 of [GETTING-STARTED.md](GETTING-STARTED.md): your local API key, accessible model IDs, current prices, your chosen daily cap, and cloud enable switch. No paid test has been run for you.
4. Understand the archive limitation: the downloaded MOS data provides model runtime, not an independently verified first-receipt timestamp. Strict mode refuses it. Exploratory testing requires the explicit flag below; this does not make availability verified.

## Experiment protocol

- Station: KLAX (Los Angeles International Airport).
- Held-out test: August 1–31, 2026.
- Calibration examples: July 2026, fixed before testing. July outcomes not published before a test decision are excluded.
- Input: prior-day 12Z GFS MOS run, with an assumed six-hour dissemination delay. The maximum of eight three-hour forecast temperatures over the 08Z–08Z day is a forecast proxy, not the true daily forecast maximum and not the live NWS hourly-grid product.
- Labels: daily NWS CLI highs parsed by the Iowa Environmental Mesonet (IEM), with product identifiers. Raw CLI product review remains required for publication.
- Threshold: a fixed 80F daily-high threshold. This is a weather calibration benchmark; it is not a reconstruction of historical Polymarket contracts.

Sources: [IEM NWS MOS archive](https://mesonet.agron.iastate.edu/mos/), [IEM API and CLI services](https://mesonet.agron.iastate.edu/api/). The archive JSON is downloaded now; its receipt is never represented as an old live receipt.

The bundled normalized corpus is `examples/historical-klax-2026-08`. You can use it immediately without downloading again. Raw receipts remain local; the download command reconstructs a new source snapshot.

This is an exploratory development pilot: initial aggregate diagnostics were inspected while building the harness. Use a different untouched period for confirmatory paper claims.

## 1. Download the month and calibration examples

```powershell
python -m weatherlab.historical download --out data/historical/klax-2026-08-v1
```

This bounded job requests 62 daily forecasts and the CLI year table, writes individual hashed receipts, and separates `training.jsonl`, `cases.jsonl`, and `labels.jsonl`. Missing days are reported rather than filled. Do not overwrite an existing corpus; reuse it or give a new versioned directory.

## 2. Run the free fast baseline

```powershell
python -m weatherlab.historical run --corpus examples/historical-klax-2026-08 --out data/historical/baseline-001 --allow-assumed-availability
```

Without the final flag, strict mode intentionally rejects unverified historical availability. This exploratory baseline uses July forecast residuals to estimate the probability of exceeding the declared threshold. It is a statistical forecast, not a simulated LLM call.

## 3. Run the actual models after setup

```powershell
python -m weatherlab.historical run --corpus examples/historical-klax-2026-08 --out data/historical/cloud-001 --mode cloud --allow-assumed-availability
```

This requests fixed-model and adaptive-model forecasts plus a five-persona weather-only PolySwarm ablation. The ablation omits PolySwarm's market-price blend because no historical market prices are supplied. It must not be reported as the complete trading strategy. Wallet following and arbitrage also require real historical signals and synchronized books and are not fabricated here.

Calls are sequential, stateless and bounded by the existing shared budget. Approximately seven calls per complete day, plus possible adaptive escalations, may be attempted; budgeting can stop later attempts. A monthly run is not accelerated through provider latency. The simulated calendar advances without sleep, and already-computed outputs are streamed to disk. Use a new output directory for each run.

## 4. Review results

- `inputs.jsonl`: the exact allowed model payload for each day.
- `predictions.jsonl`: predictions, response audits and hash chain, written before scoring.
- `scores.jsonl`: outcomes joined only after every prediction is complete.
- `summary.json`: Brier scores, scored/skipped counts, elapsed seconds, and traced Python peak memory.

Lower Brier score is better. Report coverage and uncertainty; one station-month is a small, correlated sample. Do not select models, thresholds or prompts using August and then call August an untouched test set.

## Preventing future information in application inputs

The model context is built from an explicit field allowlist. August outcomes and later test days never enter it. Calibration is frozen to July and filtered by publication time. Station/date/source URLs and raw product text are removed from the model prompt. There is no conversation history, agent tool access, or growing cross-day memory. Tests confirm changing held-out labels does not change predictions and future-dated forecasts are rejected.

This does **not** prove a pretrained LLM never learned an old weather event. Redaction is a mitigation, not an exclusion proof. Archive corrections and unverified first-seen times are additional limitations. A prospective held-out experiment remains the stronger test.

## Memory and trading limits

The benchmark holds at most 31 calibration days and 31 labels, streams case/prediction files, clears saved model-call buffers, and measures Python allocations. This is bounded memory by design, not proof that every runtime/library is leak-free. The dashboard journal is capped at 200 display entries; full events remain on disk and consumed-depth cache expires only after its quotes are no longer executable.

There is no historical order-book dataset in this corpus. No trades, fills, profit, or strategy-success verdict are manufactured. To test trading returns, collect/import original timestamped US contract metadata, executable books, reference signals where applicable, and final settlement receipts. Then use the existing paper replay engine with its causal timestamps and delayed-fill rules. Weather-only accuracy is one necessary component of that larger test.
