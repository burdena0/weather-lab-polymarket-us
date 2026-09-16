# Reviewed weather-strategy source

Source: [Trade the Outcome weather guide](https://www.tradetheoutcome.com/polymarket-weather-strategy/), reviewed September 16, 2026. It is a secondary strategy article, not audited performance evidence. Its international examples do not establish eligibility on Polymarket US.

## Incorporated as testable hypotheses

The library now contains five additional methods: joint bin probabilities, partial temperature ladders, update timing, forecast-source weighting and seasonal evaluation. Each is marked unproven and timestamped at local review. Five station-specific copies yield 25 records. The existing four-card/8-KB retrieval budget still applies; cards are eligible references, not instructions to execute every method on each decision.

```powershell
python -m weatherlab seed-strategies --collection outcome-guide --out data/research/outcome-guide-v1.jsonl
```

The output is append-only. Re-ingest an existing generated JSONL with `ingest` to retain the same receipt; do not regenerate the same revision with a new timestamp. These records cannot enter decisions before their actual review time. They do not change old forecasts or rewrite previous experiments.

## Corrections used in implementation

For disjoint bins with one YES share each, let `P` be total probability covered and `C` the all-in basket cost. Expected profit is `P-C`; payoff outside the selected bins is zero, so the loss is `C`. A 45-cent partial ladder with only 30% coverage loses 15 cents in expectation. Cheap cost alone proves nothing. `weatherlab.strategy_sources.ladder_scenario` implements this analytical check; it has no order-book or trading authority.

An exhaustive basket needs verified complete rules coverage and executable costs; a forecast-price disagreement is a risky directional forecast. Quote-update lag must be measured rather than assumed. Recent Brier weights need earlier calibration and account for correlated errors. No season, article win-rate claim or suggested position-sizing fraction authorizes increased stakes.

Fee accounting follows the [Polymarket US schedule](https://docs.polymarket.us/fees), not a generic percentage from the article. The September 6-15 experiment retains its dated 0.06 coefficient. Future periods must use their effective schedule. [US market APIs](https://docs.polymarket.us/api-reference/market/overview) provide market information; current books cannot reconstruct historical quantities. [NWS probabilistic guidance](https://www.weather.gov/mlb/probabilistic) is a potential additional input; its location and accumulation window require alignment with the exact CLI settlement contract before use.

## Current implementation boundary

These additions supply reviewed RAG hypotheses and a ladder mathematics utility. They do not add a new HRRR/NBM feed, low-latency trading, maker-fill assumptions, or cross-venue execution. Those require separate data and validation. The [policy comparison](PROFITABILITY-IMPROVEMENTS.md) tests explicit net-entry thresholds, execution-time cancellation, local probability blending and a cheap pre-call gate on already committed forecasts. It does not claim to test these new cards or the [private-model interface](EXTERNAL-MODELS.md).
