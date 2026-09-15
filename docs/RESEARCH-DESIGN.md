# Research design and source use

## Research question

For Polymarket US daily-temperature contracts, does fixed, adaptive or persona-aggregated cloud inference add forecasting value or economic value beyond deterministic controls after retrieval, costs and execution delay?

This is a research harness and an explicit set of hypotheses. Software correctness, probability calibration, execution realism and profitability are separate claims requiring separate evidence.

## Source attribution

1. [Barot and Borkhatariya, PolySwarm, arXiv:2604.03888v1](https://arxiv.org/html/2604.03888v1). The paper motivates persona aggregation, market-prior combination, constrained sizing, proper scoring and cost/latency measurement. Here we implement five weather roles by default, capped confidence weights, a fixed linear blend and a disagreement/abstention gate. These are explicit adaptations, not a reproduction of its 50-persona experiment. The accessed evaluation section describes metrics and methodology; it does not supply a reproducible Polymarket US weather result establishing an edge for this implementation. Its crypto latency module is not transferred to weather.
2. [Unravelling the Probabilistic Forest: Arbitrage in Prediction Markets, arXiv:2508.03474v1](https://arxiv.org/html/2508.03474v1). We use payoff consistency and complete outcome coverage as the motivation for deterministic basket checks, and retain the distinction between opportunity detection and execution risk. Its international on-chain historical findings are not evidence of executable profit in US weather contracts. Our supported construction buys a complete disjoint integer-Fahrenheit YES partition below its ordinary $1 aggregate payout after modeled costs. Cross-venue shorting, token splitting/merging, and semantic arbitrage are excluded.
3. [LunarResearcher, Harness Engineering](https://x.com/LunarResearcher/status/2096570562625655088). The original X page failed direct access; its article text was read through the FxTwitter mirror. This is engineering commentary, not peer-reviewed financial evidence. It motivates the explicit contract, policy boundary, persistent journal, bounded calls and verifiable receipt described in `HARNESS.md`. Promotional instructions in source text are not incorporated.

No source's claimed profit is used as a training label or expected return. No full source text is redistributed with the ZIPs.

## Four arms and controls

| Arm | Decision rule | Main hypothesis |
| --- | --- | --- |
| 1A Wallet copy | New verified reference trades, exact US mapping, price-loss limit; zero model calls | Useful deterministic behavior benchmark |
| 1B Strict arbitrage | Buy an exhaustive nonoverlapping temperature basket with positive modeled payoff spread | Structural mispricing exists after practical gates |
| 2 Fixed | One Terra probability estimate from causal RAG, fixed medium effort | Retrieved evidence adds forecast skill |
| 3 Adaptive | Same evidence and risk policy; fixed complexity features select Luna/Terra/Sol and effort | Routing reduces cost without unacceptable error increase |
| 4 PolySwarm-inspired | Independent persona inputs with prices withheld, capped-confidence average, 30% market blend | Aggregation adds value after correlated errors and additional latency/cost |

1A and 1B are separate configurations in one control package. They are never merged into one return series. Unhedged copying is not pure arbitrage. Also report a cash benchmark and the statistical residual and market-probability forecasts recorded for every eligible model decision.

All arms receive the same input dataset, use separate $50 paper accounts, protect $40 cash, cap a position and station-day at $5, cap size at five shares and use the same fee/slippage rules. The control has no weather probability model. The principal ablation is arm 2 versus arm 3: only routing should change. Arm 4 changes aggregation and model-call count; that is a different hypothesis.

## Exact implemented policies

- Historical context: at least ten eligible same-station prior-day records; at most 30 retrieved analogues by default. Residual probability uses half-count smoothing. This is an unvalidated statistical baseline.
- Forecasts: six-hour issuance freshness and fifteen-minute receipt freshness. Books: ten-second receipt freshness, two-minute source-age ceiling, finite levels, correct slug/open state, no duplicate/crossed/off-tick prices.
- Entry (Balanced default; see `RISK-PROFILES.md` for Reliable/Risky): lower model probability bound (or one minus the upper YES bound for NO) minus modeled all-in cost must exceed three cents/share. Quarter-Kelly sizing uses this conservative bound and the common hard caps. Confidence intervals are model reports, not calibrated statistical intervals.
- Exit: sell owned inventory only when net bid exceeds the point-estimated fair value by three cents/share. Final supplied venue settlements release cash and recognize P&L once.
- Fill: decide at frame t, wait at least two seconds and the measured/synthetic inference delay, then evaluate the next eligible observed book. Intent expires after 60 seconds for copy/baskets or 120 seconds for model decisions. A five-minute observation gap cancels pending actions. No final-frame invented fill.
- Depth is consumed within an account and tracked across unchanged timestamp/depth snapshots; new observed book changes provide a new liquidity snapshot. No queue-priority or maker-fill claims.
- Fee stress: per consumed price level, ceil to cents of `theta * contracts * p * (1-p)`, with theta at least 0.07 or the larger captured market coefficient, plus $0.002 adverse cash adjustment/share. This deliberately conservative model is not the exact venue match fee. No rebates. See [US fee documentation](https://docs.polymarket.us/fees); captured metadata can differ and actual billing requires later reconciliation.
- Basket fills require every leg to pass the delayed checks in one paper transaction. This is an ideal all-legs-fill scenario, not proof of venue atomic execution. Source book times must be within two seconds at discovery and fill. Stress one-leg failures separately before publishing economic results. No claim of guaranteed realized profit is made.
- Current model calls are sequential and share a daily API budget. That adds latency to the swarm. Disclose it; do not compare a serial prototype's latency with a hypothetical parallel implementation.
- $200/month is accrued as $200 / 30 days on each alternative's experiment duration and shown outside protected trading cash. API charges are additional. Alternative accounts are not summed as one portfolio.

## Evaluation plan

Freeze market selection, station universe, decision cadence, model IDs, prompt, retrieval rule, risk limits, fill assumptions, split dates and analysis plan before collecting test outcomes. The public capture defaults to a fixed lexicographic bounded subset; it is a connectivity diagnostic, not an unbiased market-wide sample.

Use time-ordered training, development and untouched prospective test periods. Group all related buckets and simultaneous station-days by calendar date when estimating uncertainty. Retrospective LLM evaluation is contaminated if model pretraining includes the outcomes; a point-in-time evidence store cannot prove the absence of parametric leakage.

Report:

- Brier score and log loss on first forecasts, market/statistical baseline differences, calibration curves and coverage/abstention.
- Realized P&L, open liquidation value (unknown if missing depth), fees, model tokens/cost, subscription overhead and net economic P&L.
- Delay distributions, fill rejection reasons, data gaps, unexpected source/schema failures and model response failure rate.
- Unique markets, station-days and calendar dates. Multiple correlated temperature buckets are not independent trials.
- Results for all frozen configurations and all selected markets, including no-trade days. Do not select a winner on the test set and report its same-period score as out of sample.

`python -m weatherlab.evaluate LEFT/summary.json RIGHT/summary.json --out paired.json` matches contracts only if dataset hashes agree, reports missing-prediction counts, averages differences within calendar-date clusters and computes a seeded bootstrap interval with at least ten dates. The interval is descriptive, not automatic significance or a power guarantee. Synthetic/non-cloud results are refused unless explicitly allowed for testing.

Recommended ablations (predeclare; not all are implemented as toggles): statistical-only baseline; fixed without historical retrieval; numeric retrieval versus lexical-plus-numeric retrieval; adaptive without escalation; equal versus confidence-capped persona weights; no market blend; latency-matched and dollar-budget-matched model comparisons; fee/depth/one-leg-failure stress. New toggles require new package versions and tests; do not silently edit a completed experiment.

## Publication readiness

The delivery is ready for software experiments and corpus construction. It is not yet an empirical paper result. Before publication, validate actual API calls, build an audited real corpus, preregister a prospective window, validate the provided background public session under a preregistered collection protocol if making prospective claims, collect verified final venue outcomes, run the locked analysis and disclose all exclusions. The existing seven-session schedule is unchanged; this project installs no schedule or endless loop.
