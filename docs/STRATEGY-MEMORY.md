# Strategy memory and the research library

RAG is useful for supplying relevant, inspectable knowledge without retraining the model. That does not turn a narrated winning trade into a reliable strategy. See the [original RAG paper](https://arxiv.org/abs/2005.11401) and [backtest-overfitting research](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf).

## Included knowledge

The initial library contains **50 station-specific cards**, ten topics for each of KLAX, KNYC, KSFO, KMIA and KMDW:

- GFS / IFS agreement, peak timing, weather-change proxies and recent persistence.
- Station-specific residual calibration and exact settlement rules.
- Forecast vintages and receipt times, bin-boundary sensitivity.
- Executable depth and full costs, abstention and negative results.

These are curated summaries of the existing implemented methods and research limitations. They are **not new observations, training labels, completed station-days or verified profitable strategies**. Forecasts, reviewed outcomes, contract rules and receipts remain separate record types. No private credentials or account details belong in this library.

## Retrieval and efficiency

New forecasting packages enable `strategy_memory: true`; omit or set it to false for a matched memory-off comparison. The deterministic control cannot enable it. The original demo and weather-rule ablation preserve their earlier design by disabling it. Each replay creates a new experiment directory and journal database.

Cards share the existing SQLite evidence ledger. There is no new service, embedding call, subscription or fine-tuning. Selection uses the latest known revision per method for the exact station, then expiry, retirement, source and synthetic filters. It never resurrects an older favorable revision. Future evaluations remain unavailable to earlier decisions.

At most four cards totaling 8 KB enter each context. Selection prioritizes applicable topics, then uses deterministic station-day rotation to avoid always returning the same subset; it does not rank by reported P&L. The corpus is limited to 200 method identities per station at retrieval; larger sets return no cards with an audit notice. Query latency and token cost should still be measured on real workloads; no efficiency improvement has yet been benchmarked.

Full paper evaluations remain in the ledger. Probability prompts receive methodology, limitations, sample sizes and report references, with monetary results withheld to reduce anchoring. Card IDs and original payload hashes appear in retrieval journals and citations. The model treats card text as untrusted evidence; existing deterministic execution rules retain authority. Missing weather history still causes abstention.

## Enable and update

1. Install the updated runtime and four ZIPs. Existing frozen runs retain their configuration.
2. Seed once, using a new receipt filename:

   ```powershell
   python -m weatherlab seed-strategies --out data/research/strategy-library-v1.jsonl
   ```

   This creates 50 cards with actual local creation/availability times and a 90-day expiry. Reimporting the saved file is idempotent. Re-running seed with new timestamps and the same revision IDs intentionally fails rather than changing history.
3. To import the saved file into a new evidence database, or add reviewed revisions:

   ```powershell
   python -m weatherlab ingest --jsonl data/research/strategy-library-v1.jsonl --db data/evidence.sqlite
   ```

   The existing **Index evidence JSONL** dashboard control also accepts cards. Revisions require a new `evidence_id`, increasing integer `revision`, actual receipt/availability and new expiry. `status: retired` suppresses that method at and after its availability. No automatic refresh or renewal of claims is implemented.
4. Run matched, predeclared new experiments with memory on and off against the same causal input and RAG database. Use separate output directories and record model/config/code versions. Evaluate forecast scores, coverage, abstention, tokens, latency and after-cost simulated outcomes. Fixture results verify integration only.

## Recording reported paper performance

Supported statuses are `hypothesis`, `methodology`, `paper_evaluated` and `retired`. `profitability_established` must remain false. A `paper_evaluated` card requires an `evaluation` object with:

- `verification: reported_not_independently_verified`.
- `training_end`, `config_frozen_at`, `test_start`, `test_end`, in chronological order, with evaluation end no later than card availability.
- SHA-256 `dataset_hash`, `config_hash`, `report_hash` and an HTTPS `report_url`.
- Positive integer `station_days`, `trades`, `variants_tested`.
- `gross_pnl`, `fees`, `slippage`, `model_cost`, `overhead`, `net_pnl`, `max_drawdown`, and `limitations`.

The importer checks chronology, finite values and cost arithmetic. It does **not** fetch the report, verify its hash against a remote artifact, validate fills, prove independence or certify reported returns. Negative results use the same schema and selection policy as positive ones. Zero-trade/incomplete experiments remain methodology or hypothesis records with limitations, not performance evaluations. Any stronger claim requires a separately reviewed, reproducible, held-out evaluation and uncertainty analysis.

## Not added

No claimed channel win rates, automatically inferred profit labels, hindsight weather reconstructions, unlimited transcripts, private account history, self-modifying strategy code or automatic deployment. RAG records cannot change model budgets, cash reserves, position limits or settlement rules.
