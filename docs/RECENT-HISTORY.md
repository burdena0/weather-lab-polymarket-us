# Recent weather benchmark

## Completed collection and results

On September 16, 2026, the local collector downloaded September 6–15 forecasts and final daily highs for KLAX, KMDW, KMIA, KNYC and KSFO: **50 test station-days**, plus **155 earlier calibration station-days** (August 6–September 5). All five final station manifests report zero collection errors. A station-day is one station on one date.

This is an exploratory weather accuracy benchmark. It does not establish trading profitability or reproduce the full four-strategy trading comparison.

| Station | Test days | Days at least 80°F | Baseline mean Brier score |
| --- | ---: | ---: | ---: |
| KLAX — Los Angeles | 10 | 8 | 0.163237 |
| KMDW — Chicago Midway | 10 | 6 | 0.123494 |
| KMIA — Miami | 10 | 10 | 0.000246 |
| KNYC — Central Park | 10 | 3 | 0.079738 |
| KSFO — San Francisco | 10 | 4 | 0.179152 |

Brier score measures squared probability error; lower is better. Miami's ten outcomes are all YES at the fixed 80°F threshold, so its low score is not evidence that this station or strategy is superior. Ten days per station is too small for a profitability or generalization claim. No threshold was optimized on this test set.

## Sources and timing

- [IEM GFS MOS archive API](https://mesonet.agron.iastate.edu/api/1/mos.json): prior-day 12Z GFS MOS, using eight three-hour temperature samples over each station's local-standard CLI day. This sampled maximum is a different product from the live NWS hourly-grid forecast and may miss the true forecast peak.
- [IEM NWS CLI archive](https://mesonet.agron.iastate.edu/json/cli.py?station=KLAX&year=2026): final daily highs. Every included outcome was cross-checked against archived raw NWS CLI text for station, product, target date, Fahrenheit units and observed maximum. The collector accepts the `R` record-temperature marker.
- Each receipt retains its source URL, actual download time and content hash. Forecast availability uses an **assumed six-hour dissemination lag**, not a verified historical first-seen timestamp. Strict historical replay therefore remains blocked; exploratory runs require `--allow-assumed-availability`.

Earlier calibration outcomes are admitted only if their publication precedes that case's decision time. Test labels remain in a separate file and are opened for scoring only after all predictions have been written. Prompts redact station and date, but this cannot rule out pretrained model knowledge. Harness development used historical diagnostics; a fresh held-out period is necessary for confirmatory research.

These archive records are **not added to live RAG as causal history** and do not unlock its ten-day readiness requirement. Today's download timestamp cannot prove that a forecast was available to a live agent ten days ago. The benchmark excludes present-day strategy cards, unavailable historical books and wallet signals. The control cannot be scored without those market inputs. PolySwarm cloud mode is a weather-persona ablation, without its market-price blend or the full trading pipeline.

## Cloud status and remaining setup

Cloud inference is enabled locally with the existing $20/day application cap. The attempted KLAX cloud benchmark produced **zero validated model responses**. The provider returned **HTTP 429 / `credit_balance_exhausted`**. Thirty benchmark requests and one diagnostic request were attempted before the billing cause was identified. The updated runner stops further benchmark requests after the first billing, authentication, rate-limit, budget or deadline block.

The benchmark ledger retained $1.0486652 in conservative reservations; the diagnostic has a separate reservation. **Reservations are not confirmed charges.** They remain because failed requests provide no reliable usage reconciliation.

The user must fund the API account associated with the configured key before a cloud rerun can succeed. No credits were purchased, no account was created, and no real orders were submitted. Model-list access alone does not validate inference. After funding, rerun into a new output directory; do not overwrite previous evidence. Historical contract books, public-wallet signals and reviewed exact US contract rules are still needed for a trading backtest.

## Local evidence

The ignored local archive root is `data/historical/2026-09-06_2026-09-15-v2/`. Each station directory contains `protocol.json`, `manifest.json`, `training.jsonl`, `cases.jsonl`, `labels.jsonl` and original receipts. Baseline results are in `baseline-KLAX/` through `baseline-KSFO/`; the failed cloud run is preserved in `cloud-KLAX/`. Aggregate files are `collection-summary.json`, `baseline-summary.json` and `report.json`. The dashboard reads `data/historical/latest-recent.json`.

Raw downloaded data and local budget/account state are excluded from the public repository and ZIPs. Earlier unsuccessful collection attempts remain separate and immutable.

## Reproduce or extend

From the Weather Lab deployment folder, choose new output directories for every run:

```powershell
python -m weatherlab.historical_window --station KLAX --start 2026-09-06 --end 2026-09-15 --out data/historical/new-klax-corpus
python -m weatherlab.historical run --corpus data/historical/new-klax-corpus --out data/historical/new-klax-baseline --mode baseline --allow-assumed-availability
```

After resolving API credits, a bounded cloud run uses the same existing shared daily budget:

```powershell
python -m weatherlab.historical run --corpus data/historical/2026-09-06_2026-09-15-v2/KLAX --out data/historical/new-klax-cloud --mode cloud --allow-assumed-availability --max-seconds 900
```

Supported station IDs: `KLAX`, `KMDW`, `KMIA`, `KNYC`, `KSFO`. Collection accepts 1–31 completed test dates with 31 preceding calibration dates. Reads, row counts, memory buffers and inference runtime are bounded; replay does not sleep to simulate elapsed historical time. Reported Python peak memory does not measure all native-process memory.
