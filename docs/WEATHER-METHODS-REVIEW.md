# Weather methods review

Protocol: `weather-methods-20260916-v1`. First available to decisions: **September 16, 2026, 17:07:01 UTC**. This is a research implementation, with no demonstrated performance advantage.

**Version note:** this page records the original v1 review. New packages now use [v2 weather hypotheses](WEATHER-HYPOTHESES.md), which adds GFS/IFS collection and explicit entry rules. Statements below about unconnected comparison feeds describe v1.

## Coverage and evidence quality

Reviewed all 13 videos listed on [Polymarket Hack's channel](https://www.youtube.com/@polymarkethack/videos) on September 16. Auto-generated English captions were exported and reviewed. The local research archive contains the complete captions, source URLs, receipt times, segment counts and SHA-256 hashes. The public packages contain original analysis and code, not full captions. Channel coverage is a snapshot; future uploads are not included.

Captions contain truncated sentences, ambiguous provider names and numerical inconsistencies. Video descriptions, titles and claimed wins are not independent verification. In particular, the political video titled “Trump Prediction 2026” discusses Hungary. No return, hit rate or probability estimate from these examples is treated as a verified result. Promotional referrals and claims of insider information are excluded.

| Video | Reviewed passage | Treatment in this weather experiment |
|---|---|---|
| [Weather Trading Explained](https://www.youtube.com/watch?v=NkK6Pp81qMk) | 0:39–1:15, 2:13–3:30, 4:26–6:10 | Exact contract/source, weather features and liquidity. Reject a universal afternoon settlement window and unsupported consensus-to-accuracy conversion. |
| [How To Trade Weather Markets](https://www.youtube.com/watch?v=P-oOJs_cMKc) | 0:50–2:15, 4:22–8:00 | Station, units, model disagreement and depth. Multiple websites do not establish independent models. |
| [How To Read a Weather Forecast](https://www.youtube.com/watch?v=iSWPeN35Uk4) | 2:00–7:00 | Disagreement and missing evidence must increase scrutiny, not confidence. No automatic 50% probability for model disagreement. |
| [Weather Prediction Markets Explained](https://www.youtube.com/watch?v=rKS1HKUA-O0) | 0:00–1:50, 5:00–6:50 | Hourly weather context and exact location. Claimed 80–100% accuracy from agreement is not used. |
| [Weather Prediction](https://www.youtube.com/watch?v=MhhopiLhuvI) | 0:45–3:30, 5:40–8:35 | Integrate forecast residuals over the contract's bin. Complete partition baskets retain executable depth/fee checks. Sea-breeze causality needs additional data. |
| [How To Predict Weather Markets](https://www.youtube.com/watch?v=JpHM_BJ-DVM) | 0:00–2:00, 4:40–7:40 | Explicit native units, rounding boundaries and threshold sensitivity. No invented decimal precision or forced probability from rounding. |
| [How To Predict Weather](https://www.youtube.com/watch?v=4228yFx_f04) | 0:00–2:45, 4:24–10:30 | Exact station and liquidity checks transfer. Daily-minimum contracts and retrospectively displayed forecasts are outside this daily-high implementation. |
| [Trump Prediction 2026](https://www.youtube.com/watch?v=se8O5QDTqQs) | 0:50–1:50, 5:00–7:50 | Distinguish event occurrence from official settlement. Cross-asset political signals are out of scope. Later market moves cannot prove an earlier actionable signal. |
| [Crypto Trading Strategy](https://www.youtube.com/watch?v=bNOkV4YRFZg) | 1:00–3:00, 6:00–8:10 | Prefer the exact official measurement over a related metric. Threshold coherence motivates contract checks; no crypto connector is added. |
| [Iran War Prediction Markets](https://www.youtube.com/watch?v=iYU_V6Q7xoU) | 1:00–3:00, 5:00–6:10 | Source corroboration and exact resolution wording transfer. Oil/news signals and cross-venue price differences are not weather arbitrage proof. |
| [This Weather Prediction Made Me Money](https://www.youtube.com/watch?v=3OcdEINkGSk) | 0:00–4:50 | Retain the complete hourly path and all peak timestamps. A daily maximum can occur outside typical afternoon hours. |
| [How To PREDICT Weather Markets](https://www.youtube.com/watch?v=XNFoxxX9FnY) | 0:00–3:00, 3:00–6:50 | Inspect abrupt forecast changes instead of assuming seasonal persistence. Later weather and off-station temperatures cannot validate an earlier trade. |
| [How To Predict Weather Markets Successfully](https://www.youtube.com/watch?v=cPQSG4J4lA8) | 0:00–4:30, 5:35–7:15 | Treat consumer-app forecasts as forecasts, require station matching, record missing independent models. Claimed tail-market accuracy and profits remain unverified. |

## What changed in each strategy

| Strategy | Implemented behavior |
|---|---|
| Wallet control | Remains zero-LLM. Requires an explicit full weather-day interval for a copied contract. Complete-basket mode additionally requires identical intervals across every leg. Existing exact mapping, depth, fee stress, synchronized books and delayed-fill checks remain mandatory. Copy trading and an ideal complete-basket simulation are separate control modes. |
| Fixed LLM | Receives validated full-day hourly temperatures, available wind/condition descriptions, all peak timestamps, forecast horizon, largest hourly change and residual-bin sensitivity. The fixed model and effort remain fixed. |
| Adaptive LLM | Receives the same evidence. Adds one complexity point for a half-degree sensitivity span above 0.15 and one for an hourly change above 3 F. These frozen thresholds are uncalibrated research choices. Existing model-budget caps and one-escalation maximum remain. |
| PolySwarm | Every existing persona receives the same diagnostics and explicit limits on source independence, rounding and confidence. Multiple LLM opinions do not count as independent meteorological forecasts. Existing abstention/disagreement gates and aggregation weights remain. |

All decisions are tagged with the protocol version. Forecasting audits include the diagnostics. The forecast collector now preserves the hourly records it already fetches; this introduces no new provider, request or paid service.

The half-degree stress calculation shifts each projected temperature by -0.5, 0 and +0.5 F before the existing integer-bin transform. It reports three smoothed empirical probabilities and their range. This is a sensitivity scenario, **not a calibrated error interval, observed measurement precision or settlement rule**. Final payouts still require actual final venue settlement evidence.

No live GFS/ECMWF comparison is connected. The diagnostics explicitly report one NWS grid product and unavailable independent-model agreement. Cloud fraction, soil moisture, radar trajectories and verified front arrival are not inferred from missing data. Dividing distance by surface wind speed is not an implemented forecast model.

## Separate setup steps for the new protocol

1. Use the updated dashboard runtime and upload the four updated ZIPs from `dist`. The package manifests enable this protocol for new real-data runs. Uploaded code is checked against the installed runtime.
2. Capture fresh public data. Older captures lack the required 23–25 hourly periods and will produce a skip before any paid model call. Full-day NWS coverage is required; intraday observation/forecast stitching is not implemented.
3. Continue collecting forecast receipts and reviewed final station outcomes. At least 10 causal forecast/outcome station-days are still required per forecast. Methodology notes do not count toward that minimum.
4. Complete the existing local cloud-key, model-access, tariff and budget setup in `LLM-SETUP.md`. These changes do not configure credentials or validate paid inference. A configured public wallet and exact US mappings are still required for copy mode.
5. Start a **new** public paper session or replay into a new output directory. Check `config.research_protocol` in the run manifest and `research_diagnostics` in model decision audits. No previous experiment, journal or balance is overwritten.
6. Compare new-protocol runs with separately frozen baseline runs using matched prospective station-days, model spending, calibrated probability scores and execution assumptions. Do not select thresholds using held-out results.

The existing sample demo explicitly uses the original protocol and synthetic fixture model; its manifest records that choice. It is a plumbing demonstration. The August benchmark also remains the earlier weather-only benchmark. Applying this September review retrospectively to August would be a new, contaminated exploratory analysis, not a causal verification: the new protocol refuses pre-review decisions.

## Local RAG records and schedule

Five station-specific original methodology notes are stored as `research_note`, with their actual September review/receipt availability. They contain limitations and source references, not target outcomes. They cannot become historical forecast/outcome pairs or appear in pre-review retrieval. Full captions remain outside the public repository and ZIPs.

Daily public evidence collection is scheduled separately at 09:00 America/New_York using Sol with low reasoning. The previous task-based heartbeat is paused. This schedule gathers the existing bounded public weather/contract evidence; it does not run model trades or continuously collect channel videos. Collection still needs the local host and network available.
