# Weather hypotheses: collection, entry rules and comparison runs

Protocol `weather-methods-20260916-v2` is available from **2026-09-16 17:30:00 UTC**. It preserves v1 and original configurations. New real-data packages enable v2; the three LLM arms enable all four hypotheses. The deterministic control keeps copy/basket logic and no model calls. Sample demos explicitly retain the original protocol.

## Implemented entry rules

These are frozen research hypotheses, not calibrated probabilities or proven sources of profit.

| Switch | Rule | Effect |
|---|---|---|
| `model_consensus` | GFS and IFS daily highs differ by at most 3 F, and their rounded point forecasts imply the same YES/NO side for the exact bin | Permit entries only on that side. Otherwise block new entry. Agreement does not increase probability or confidence. |
| `peak_timing` | Define each model's peak window as all hourly values within 0.5 F of its high. Compute the greatest distance from either window to the closest hour in the other window | Block entry when this symmetric distance exceeds 3 hours. Full contract-day coverage remains mandatory. |
| `regime_change` | In either model, a three-hour temperature change reaches 6 F, or a three-hour cloud-cover change reaches 40 percentage points together with a wind turn of at least 60 degrees. The wind test requires at least 5 mph at both endpoints | Require 2 cents more estimated edge per share and halve the proposed quantity, rounded down to hundredths. Skip if below minimum size. This is a weather-change proxy, not a verified front or sea-breeze detector. |
| `recent_trend_break` | Compare the NWS high with the mean of seven consecutive prior observed daily highs, whose final date is 1–3 days before the target. If the difference reaches 5 F, require both GFS and IFS to point in the same direction from that reference | Block entry on conflicting direction or missing recent history. The reference is recent persistence, not a long-term climate normal. |

Existing risk-profile uncertainty gates apply first. Existing owned-inventory exit logic runs before the new entry filters. The filters cannot authorize an otherwise rejected trade, increase position limits, bypass fees/depth checks, or change final settlement. Forecast/data validation is still needed before any decision, including an exit.

Fixed LLM keeps its fixed tier and effort. Adaptive adds one complexity point for model spread above 3 F **or** peak-window distance above 3 hours, and one for a detected regime change. Together with the four original and two v1 features, the maximum score is eight; routing remains 0=small, 1–2=medium, 3+=large, with at most one escalation. These routing features remain available in the v2 entry-rule ablations. PolySwarm keeps the existing persona loop and aggregator, applying the same entry filters afterward.

## Actual data integration

The collector requests explicitly named `gfs_global` and `ecmwf_ifs025` products through [Open-Meteo's forecast API](https://open-meteo.com/en/docs), using coordinates retrieved from the exact NWS station metadata. It requests temperature, cloud cover, wind speed and wind direction, Fahrenheit/mph, UTC Unix timestamps, and only the calendar dates needed to cover the contract interval. The decoder requires both named products, valid units, a contiguous full venue day, and a returned provider grid point within 50 km of the requested coordinates. This distance bound detects gross mismatches; it does not establish station-level forecast accuracy.

The returned coordinate is provider-response metadata, not separate native-cell metadata for both models. Exact native grid-cell equivalence is unverified. Both are gridded forecasts. Provider interpolation, terrain adjustment and shared observations can correlate their errors. The API's latest stitched forecasts do not expose a trustworthy initialization timestamp in this response: `issued_at` remains null. Availability is the actual local receipt, never an invented model issue time. A composite forecast becomes available only after its last component receipt; each comparison forecast also retains its own timestamp. Decisions require receipts no older than 15 minutes and received before the target weather day; source-run freshness remains a limitation. See the [GFS documentation](https://open-meteo.com/en/docs/gfs-api), [ECMWF documentation](https://open-meteo.com/en/docs/ecmwf-api), and [single-run timing explanation](https://open-meteo.com/en/docs/single-runs-api).

Data attribution: **Open-Meteo, NOAA GFS and ECMWF IFS**, [CC BY 4.0](https://open-meteo.com/en/licence). This implementation uses the free API for this non-commercial research project under its [usage terms](https://open-meteo.com/en/terms). No paid subscription or additional credential is configured.

`collect-evidence` stores the NWS receipt plus two separate comparison forecast records for each of up to five station-days. It stays within 24 bounded requests and creates no completed outcomes automatically. `capture` embeds the comparison forecasts in decision frames. If comparison collection fails, the NWS record is preserved, the failure is reported, and v2 decisions skip rather than silently falling back to one family. V1 excludes the supplementary model fields from its forecast context.

V2 RAG retrieval reserves space for the seven latest eligible completed station-days, then fills the remaining slots with weather analogues, within the existing 30-record default. All date/source/availability filters still apply. Reviewed outcome pairing retains compact model forecast metadata for future model-specific error analysis; NWS residuals are **not** treated as calibrated GFS/IFS errors.

## New setup and test steps

1. Update the dashboard runtime and import all four newly built ZIPs. Check that their manifests use `weather-methods-20260916-v2`.
2. Collect prospective evidence into a new folder:

   ```powershell
   python -m weatherlab collect-evidence --out data/research/models-day-001
   ```

   Inspect `report.json`: a complete five-station run should report five NWS forecasts and ten comparison forecasts. Any feed errors must be investigated. The existing daily Sol/low collection uses the same updated collector.
3. Review final NWS CLI outcomes and pair them using [DATA-COLLECTION.md](DATA-COLLECTION.md). At least ten causal history days remain necessary; the trend rule additionally needs seven consecutive recent days. Forecast records and methodology notes do not satisfy these gates.
4. Capture fresh synchronized decision inputs and books:

   ```powershell
   python -m weatherlab capture --out data/research/models-window-001 --seconds 45 --max-markets 4
   ```

5. Test switches by copying a configuration to a **new** filename and changing its `weather_hypotheses` list. Valid names are the four table entries. An empty list disables the entry filters while retaining v2 evidence, diagnostics and routing. Do not modify an existing run's saved configuration.
6. Run the automated comparison, using a new output directory:

   ```powershell
   python -m weatherlab ablate-weather --dataset data/research/models-window-001/dataset.json --config configs/fixed_llm.json --rag data/evidence.sqlite --out data/ablations/fixed-001
   ```

   This performs seven sequential, isolated replays: v1 baseline, v2 evidence-only, all v2 entry rules, and four leave-one-rule-out variants. The same immutable dataset is used throughout. It writes a frozen plan, per-run manifests/journals and `comparison.json`. Repeat with `adaptive_llm.json` and `polyswarm.json` and different output directories.
7. The command above uses the **fixture model**, so it tests wiring and rule behavior only. Actual LLM comparisons require the existing [cloud setup](LLM-SETUP.md) and explicit `--cloud`. Seven cloud replays can incur seven runs of model costs under the shared daily cap. Model latency can change fill eligibility, and model output is not guaranteed reproducible.

## Research limits

No current profitability claim is supported. The first verified v2 collection archived five NWS station-days and ten GFS/IFS series with 24 hours each; it produced zero completed historical pairs. The existing August weather-only benchmark has no contemporaneously collected v2 inputs, so it is not evidence for these entry rules.

Evaluate on predeclared, unseen prospective station-days. Report abstention and coverage rates, matched forecast scores, latency, spend, after-cost simulated outcomes, and dependence between bins/strategies. Do not select the most profitable threshold on the held-out evaluation set. A narrated winning trade, source title, or claimed channel accuracy is not a training label. Crypto, political and conflict-specific signals remain outside this weather-only experiment.

## Verification and bundled example

110 unit tests pass, including causal receipt checks, missing-model rejection, peak-window disagreement, circular wind directions, position reduction, exit preservation and recent-day RAG retention. All seven variants completed for each of the three forecasting arms in a synthetic smoke test (21 isolated runs). No paid inference or real strategy performance was tested.

A fully invented v2 dataset is included for checking package wiring without setup:

```powershell
python -m weatherlab ablate-weather --dataset examples/dataset.weather-hypotheses.synthetic.json --config configs/fixed_llm.json --out data/ablations/synthetic-fixed-001
```

Do not pass the real RAG database to this fixture command. It uses the synthetic history embedded in the example.
