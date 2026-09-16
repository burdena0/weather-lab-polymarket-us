# Profitability improvements: exploratory comparison

## Result

The development-selected fixed LLM with a 50% market-probability blend returned **+$1.48 after fees and model costs** on the later period at 2 cents extra entry cost. It returned **-$0.68 at 5 cents** and **-$37.69 after allocated overhead** at the primary assumption. These results do not establish profitability.

No variant covered all costs. A fixed LLM with a cheap pre-call gate had a better later-period result, but selecting it from those results would use evaluation hindsight. The development-selected variant remains the headline result.

## Frozen design and actual inputs

- 23 policies compared; see all results below and [machine-readable evidence](results/profit-policy-comparison.json).
- Development: September 6-9, 2026 (20 contracts). September 10 excluded because evaluation decisions must follow all development settlements. Evaluation: September 11-15 (25 contracts).
- Selection maximized the worst development P&L after model costs across 2-cent and 5-cent entry scenarios, with deterministic tie breaks. A no-trade benchmark was eligible.
- Baselines use earlier August weather calibration. Forecast outputs, fees and model call records are reused from the completed contract experiment. Prediction chains and raw archive hashes were verified again. No new cloud requests were made.
- These dates were already inspected in earlier work. The chronological split is a useful diagnostic, **not a fresh holdout**. The next validation must collect unseen dates before changing or selecting thresholds.
- New hypotheses test an 8-percentage-point net edge, cancellation when delayed execution loses its edge, a 50% blend with the decision-time market midpoint, and a pre-call baseline gate. The gate uses no LLM output, outcome or execution quote to decide whether a call is needed. Consulted failures retain their cost; skipped historical costs are hypothetical future savings, not refunded charges.
- Entry side is selected using decision-time evidence; delayed quotes can cancel but cannot reverse it. Each scenario rechecks its actual stressed entry, so different scenarios can have different trades. Higher entry costs can therefore sometimes avoid a losing trade; they are not expected to improve returns systematically.
- Each alternative keeps $50 initial cash, $40 reserve, $2 maximum entry, five-share maximum and the dated fee schedule. No larger positions were simulated. Model costs and overhead are reported outside trading cash. Evaluation overhead is $39.17 per alternative over the decision-to-settlement span; this is not the sum of simultaneously operated accounts.
- Full fills remain hypothetical: historical quantities, queue position and actual fills are unavailable. Archived forecast availability is assumed. These are historical scenarios, not a prediction of future dollar profit.
- No private reinforcement-model predictions exist yet. New RAG cards were not available at these historical decisions. Neither contributes to these numbers. The wallet/basket control still lacks the necessary depth and reference signals.

## All evaluation results

P&L columns include trading fees and model costs; overhead is separate. Asterisks identify the variant selected using development only. No variant is deployed automatically from this search.

| Variant | Trades at 2c | Modeled model cost | Net at 2c | Net at 5c | Net at 2c incl. overhead |
| --- | ---: | ---: | ---: | ---: | ---: |
| Statistical baseline / original | 15 | $0.0000 | $-1.43 | $-3.61 | $-40.60 |
| Statistical baseline / recheck entry | 15 | $0.0000 | $-1.43 | $-5.55 | $-40.60 |
| Statistical baseline / 8pp net edge | 12 | $0.0000 | $+1.98 | $-0.93 | $-37.19 |
| Statistical baseline / half market blend | 10 | $0.0000 | $+0.36 | $-2.27 | $-38.81 |
| Fixed LLM / original | 17 | $0.3638 | $-2.11 | $-3.99 | $-41.28 |
| Fixed LLM / recheck entry | 17 | $0.3638 | $-2.11 | $-1.86 | $-41.28 |
| Fixed LLM / 8pp net edge | 14 | $0.3638 | $+1.48 | $+0.67 | $-37.69 |
| Fixed LLM / half market blend * | 14 | $0.3638 | $+1.48 | $-0.68 | $-37.69 |
| Fixed LLM / cheap pre-call gate | 12 | $0.1671 | $+1.81 | $+0.38 | $-37.36 |
| Fixed LLM / combined | 6 | $0.1671 | $-0.99 | $+0.64 | $-40.16 |
| Adaptive LLM / original | 14 | $1.3455 | $-4.09 | $-6.13 | $-43.25 |
| Adaptive LLM / recheck entry | 14 | $1.3455 | $-4.09 | $-7.05 | $-43.25 |
| Adaptive LLM / 8pp net edge | 10 | $1.3455 | $-0.50 | $-1.82 | $-39.66 |
| Adaptive LLM / half market blend | 10 | $1.3455 | $-0.50 | $-4.10 | $-39.66 |
| Adaptive LLM / cheap pre-call gate | 10 | $0.6185 | $+0.23 | $-1.09 | $-38.94 |
| Adaptive LLM / combined | 4 | $0.6185 | $-1.17 | $+0.28 | $-40.34 |
| PolySwarm / original | 10 | $1.8167 | $-3.26 | $-4.16 | $-42.43 |
| PolySwarm / recheck entry | 10 | $1.8167 | $-3.26 | $-2.72 | $-42.43 |
| PolySwarm / 8pp net edge | 7 | $1.8167 | $-1.99 | $-3.21 | $-41.16 |
| PolySwarm / half market blend | 7 | $1.8167 | $-1.99 | $-0.92 | $-41.16 |
| PolySwarm / cheap pre-call gate | 7 | $0.8606 | $-1.03 | $-1.66 | $-40.20 |
| PolySwarm / combined | 2 | $0.8606 | $-1.06 | $-0.86 | $-40.23 |
| Market implied / original | 0 | $0.0000 | $+0.00 | $+0.00 | $-39.17 |

## Reproduce

```powershell
python -m weatherlab.profitability_research --prepared data/historical/contract-profitability-v1/prepared-v2 --out data/historical/profit-policy-comparison-NEW
```

The prepared input and archived receipts must exist locally. Each output directory must be new; `plan.json`, `selection.json` and `report.json` are exclusive-create artifacts. Public distributions include the result and code; they do not contain private local data or credentials.

## Decision

Keep the initial experiment immutable. The tested controls are research candidates, not a demonstrated profitable production policy. Before scaling capital: collect real depth and fresh first-seen forecasts, freeze one candidate, then measure net outcomes on unseen dates against the statistical and market baselines. Treat the $200 monthly overhead as a real hurdle unless the actual business cost changes. Additional stake multiplies trading losses as readily as gains and does not repair poor forecasts.

## Delivery status and research pause

Before the user paused further testing, 151 unit tests passed, and the original contract-return results were unchanged after the reporting refactor. The last previous-weeks feature has unit coverage; its live archive download and rendered UI have not been exercised. No private-model predictions, iPhone Shortcut execution, or iCloud delivery have been verified. No additional backtests or test runs were performed after the pause. The frontend is frozen after this update at the user's request.

For the continuing research objective, report monthly paper P&L after trading fees, execution costs, model costs and the retained subscription expense. A dollar threshold for significant profit has not been specified. The existing results do not meet an after-all-costs profitability objective.
