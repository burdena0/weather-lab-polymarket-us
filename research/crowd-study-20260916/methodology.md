# Weather crowd calibration study

This is an independent reproduction of the descriptive analysis in [Ivan0x1's video, *I Tested 5,768 Polymarket Weather Bets*](https://www.youtube.com/watch?v=-qWlCNF57BE). The video's reported sample size, 40% accuracy and 0.069 Brier score are reference claims, not results imported into this study.

## Scope and sources

- Weather dates: September 16, 2025 through September 15, 2026, inclusive.
- International platform: closed Gamma events with weather tag 84, filtered to daily **highest temperature** titles. All cities are retained, including U.S. cities listed on the international platform.
- U.S. platform: closed climate contracts, grouped by city and weather date. The returned daily-temperature inventory starts April 22, 2026. This is less than a full year of available U.S. coverage, not an imputed year.
- Broad weather topics, daily minima, hurricanes and annual/global temperature questions are outside this video's daily-high analysis.
- Stable Gamma keyset pagination replaces the video's offset loop because the current offset endpoint has a pagination limit. The inventory exhausts the official result pages; it does not establish coverage of delisted or incorrectly tagged markets.
- International YES-token histories: [CLOB batch price-history endpoint](https://docs.polymarket.com/api-reference/markets/get-batch-prices-history), explicit historical timestamps and 30-minute fidelity. `interval=max` returned empty histories for old resolved markets in discovery; explicit ranges returned data. Requests are divided into at most seven-day windows.
- U.S. histories: [official price-history endpoint](https://docs.polymarket.us/api-reference/price-history/get-price-history), custom windows of at most 24 hours and fidelity 1. These return irregular stored quote records, including sub-minute timestamps, subsequently sampled onto the same 30-minute grid. Long/YES prices are book-derived display prices, generally asks, not trade prints or midpoint probabilities.
- U.S. outcomes come from identified terminal market books with binary USD `settlementPx` and a post-close settlement timestamp. Serialized `outcomes`/`outcomePrices` are not used because their ordering conflicted with market sides in a discovery receipt.
- International outcomes require a real condition ID, a mapped YES token, closed/resolved status and a binary final price. An event must have exactly one winner across all retained buckets. Missing or ambiguous outcomes are excluded and counted.
- Bucket labels must form a complete, non-overlapping integer-temperature partition, including both tails. This additional check excludes two incomplete international events and one incomplete U.S. event in the retrieved inventory. It prevents missing buckets from falsely improving price-sum consistency. Other unresolved/placeholder events are conservatively excluded in full rather than silently reducing their bucket count.

The acquisition tool uses only public market-data endpoints, never credentials, account data or order submission. Its sole POST is the documented **read-only** batch history query. Requests are capped at approximately 14 per second across 32 network workers, with bounded retries, response sizes and per-event lifetimes. Compressed receipts record URL, request body, retrieval timestamp, SHA-256 and response. Local research archives stay under ignored `data/`.

## Reproduction and timing

1. Preserve all raw returned observations. Sort timestamps; resolve same-timestamp duplicates by retaining the final returned observation. Collapse observations assigned to the same 30-minute endpoint to the latest observation at or before that endpoint.
2. Forward-fill from earlier observations only, never backward-fill. Start the common board only after every bucket has a price. A price at 12:01 cannot be used at 12:00. The grid uses UTC endpoints.
3. Sum all YES bucket prices at each common endpoint. The video calls this `prob_sum`; this study calls it **price sum** because venue quotes need not be calibrated probabilities.
4. Find the first six consecutive grid endpoints with sum in [0.90, 1.10]. Stop eligibility at the first common endpoint where any bucket is at least 0.95. Six endpoint checks span 150 minutes between the first and sixth reading; they represent six half-hour grid slots.
5. Record two distinct timestamps: the **retrospective run start**, which requires later observations to identify, and **causal confirmation at the sixth reading**. Main results use confirmation. Both sets of metrics are exported; the run start is not presented as an executable contemporaneous signal.
6. At each timestamp, select the highest-priced bucket. For exact ties, average the tied buckets' outcomes, equivalent to uniform random tie-breaking, without choosing the eventual winner. The random baseline is the event's actual 1 / bucket count, averaged over the same eligible events.
7. Calculate calibration by 10-percentage-point price bins. Plot each bin's mean quoted price against its eventual win frequency and report sample size. Brier score is mean squared error across binary buckets; report pooled bucket weighting and equal event weighting. Compare equal-event Brier against the corresponding uniform 1 / bucket count forecast, not an inappropriate 50% prediction for every bucket.
8. Repeat confirmation detection with no carried quote older than one hour. Unlimited forward-fill is retained for comparability with the video; the freshness restriction shows whether stale prices drive the results.

The 95% intervals resample whole weather dates, jointly retaining cities and buckets on each sampled date (500 replicates, fixed seed). Intervals are omitted below ten contributing dates, assessed separately for each calibration bin. They do not account for all serial dependence or every selection decision. Cities with small samples remain labeled by sample count.

First-observation opening-price sums combine each bucket's first retrieved observation, which may occur at different times. They are not simultaneous executable baskets. The archive is historical data retrieved today; it does not prove original publication latency or that today's rules were available unchanged at every historical timestamp.

## Interpretation

Price-sum convergence is a descriptive consistency filter. It cannot identify whether humans, bots or market makers set prices. A favorite win rate above a uniform random bucket baseline is predictive information, not proof of excess return. Calibration is not a Brier score; they are related but separate diagnostics. Book depth, spreads, commissions, adverse selection, capital lockup and model/operating costs are not simulated here. No P&L, live trading, model calls or resumed strategy backtests are part of this job.

## Local reproduction

Run from the deployment root:

```powershell
python tools/weather_crowd_study.py inventory
python tools/weather_crowd_study.py histories
python tools/graph_weather_crowd.py
```

Collection uses the standard library. Figure generation uses the existing local Matplotlib installation under `data/tools/plotting` (or an existing compatible environment with NumPy and Matplotlib). Nothing is installed automatically. Reruns reuse cached receipts and completed histories. Outputs are under `data/crowd-study-20250916-20260915/graphs/`: PDF, platform and city PNGs, example event timelines, an offline figure gallery, per-event CSV, compressed complete result records, and exclusion/summary JSON.

The scripts form an isolated research path; they do not change the frozen dashboard, RAG, strategy dispatch or paper accounts. See the [architecture view](https://github.com/burdena0/weather-lab-polymarket-us/blob/main/docs/ARCHITECTURE-UML.md#weather-crowd-calibration-study).

## Retrieved results

| Metric | International platform | U.S. platform |
|---|---:|---:|
| Inventory events | 10,088 | 674 |
| Inventory contracts | 106,714 | 4,043 |
| Cities | 55 | 5 |
| Distinct inventory weather dates | 365 | 135 |
| Clean events with aligned histories | 10,047 | 673 |
| Events passing six-check filter | 9,548 | 304 |
| Favorite win rate at retrospective start | 39.9% | 44.7% |
| Favorite win rate at sixth-check confirmation | 40.5% | 45.9% |
| Same-event uniform random baseline | 9.6% | 16.7% |
| Confirmation accuracy, date-bootstrap 95% interval | 39.2–41.6% | 39.9–50.8% |
| Pooled binary-bucket Brier at confirmation | 0.06623 | 0.10881 |
| Equal-event Brier at confirmation | 0.06690 | 0.10881 |
| Equal-event uniform-forecast Brier | 0.08630 | 0.13889 |
| Events passing one-hour freshness sensitivity | 8,995 | 302 |

The normalized histories for clean events contain 12,445,810 international price records and 19,055,214 U.S. quote records. These counts precede the common 30-minute grid; the U.S. source has much finer observations and the counts are not comparable liquidity measures.

International exclusions: 20 unresolved/placeholder events, 8 with empty histories, 11 without a common history window, and 2 incomplete partitions. U.S. exclusions: 1 incomplete partition. Another 499 clean international events and 369 clean U.S. events never pass the six-check filter before the 95-cent cutoff. All requested history jobs completed after recovery of transient acquisition errors; empty source histories remain empty.

The international inventory spans the full requested year. The U.S. inventory spans April 22–September 15, 2026 with 135 distinct dates; earlier dates and other missing dates are not filled. Confirmation results use 363 international weather dates and 79 U.S. weather dates.

These results reproduce the video's approximate 40% international favorite accuracy on a different trailing-year sample. They show predictive information relative to a uniformly random bucket, **not** excess trading returns. Different bucket counts, quote conventions, cities and date coverage prevent a simple platform ranking from either accuracy or raw Brier scores.

Public figures and exports: [research/crowd-study-20260916](index.html). The PDF contains platform and city figures; the gallery also includes one example timeline for each platform/city. Event-level CSV and JSON preserve individual scores and prices. Full transcripts and raw acquisition receipts are not included in the public research figures.
