# Set up the models

Use [GETTING-STARTED.md](GETTING-STARTED.md) for the step-by-step setup checklist, separate from [historical replay instructions](HISTORICAL-REPLAY.md).

## Model choices

| Bot | Default API model | Effort | Paid calls per eligible market decision |
| --- | --- | --- | --- |
| Wallet control | None | Deterministic code | 0 |
| Fixed LLM | `gpt-5.6-terra` | `medium` | 1 |
| Adaptive LLM | `gpt-5.6-luna`, `gpt-5.6-terra`, `gpt-5.6-sol` | `low`, `medium`, `high` | 1, at most 2 after escalation |
| PolySwarm-inspired | `gpt-5.6-terra` | `medium` | 5 by default, sequential |

These choices are experiment defaults, not demonstrated weather winners. All three cloud bots can use one OpenAI project/key. The adaptive route scores historical sample support, residual dispersion, forecast revision size and proximity to a temperature boundary. Its decision is deterministic and recorded; it is not a trained routing policy. One uncertain answer can escalate to Sol. Missing data is not solved by buying more model effort.

The persona roles are meteorologist, historical calibration analyst, settlement auditor, skeptical forecaster and regime analyst. Five roles are used initially. The `swarm_count` configuration accepts 3–50, repeating role archetypes with separate assessment labels above five; 50 calls are not 50 independent models. Shared-model correlation remains an experimental limitation. A four-minute run deadline can stop a large sequential swarm. No claim of reproducing the paper's 50-persona system is made.

Official model pages checked for this design: [Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna), [Terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra), [Sol](https://developers.openai.com/api/docs/models/gpt-5.6-sol). Access to these IDs has not been tested on your account. Use immutable snapshot IDs when offered by your project; otherwise record alias, date, response ID and returned model for every run. All IDs are overrideable without editing engine code.

## Local setup

1. Open your OpenAI API project settings and obtain an API key with access to the intended models. Do not paste the key into chat or a bot ZIP. ChatGPT/Codex subscription cost and API token billing are separate accounting items.
2. In the extracted dashboard directory, copy `settings.env.example` to `.env`. Fill `OPENAI_API_KEY` locally. The application reads only its own working-directory `.env`; it does not copy the parent trading project's secrets.
3. Keep `WEATHERLAB_ENABLE_CLOUD=0` while validating imports and test-model replays.
4. Open [current model pricing](https://developers.openai.com/api/docs/models/compare). Set `WEATHERLAB_PRICE_SMALL`, `WEATHERLAB_PRICE_MEDIUM`, and `WEATHERLAB_PRICE_LARGE` to `input_USD_per_million,output_USD_per_million`. No stale prices are silently treated as actual billing. Cached input is charged at the full configured input price for conservative comparison.
5. Choose an explicit `WEATHERLAB_DAILY_API_BUDGET_USD`. It defaults to `0`; accepted positive ceilings are at most $20/day. Setting a ceiling is your local authorization for those future API calls. No paid calls were needed to validate the delivered fixtures.
6. Index real historical records using the next guide. A usable model context needs at least ten eligible same-station forecast/outcome pairs; this is a software minimum, not an adequate research sample.
7. Set `WEATHERLAB_ENABLE_CLOUD=1`, then restart the dashboard. Choose **Recorded data · cloud models**. Upload the common real dataset and run one short window first. Missing access, invalid schema, token exhaustion, incomplete output or missing citations produces a skip/failure record, not a fallback invented forecast.

```powershell
Copy-Item settings.env.example .env
# Edit .env locally with your editor. Never print or commit it.
python -m weatherlab ingest --jsonl my-data/history-and-rules.jsonl --db data/evidence.sqlite
python -m weatherlab replay --config configs/fixed_llm.json --dataset my-data/window.json --rag data/evidence.sqlite --out runs/fixed-validation-001 --cloud
python -m weatherlab.harness runs/fixed-validation-001
```

For each other arm change only `--config` to `configs/adaptive_llm.json` or `configs/polyswarm.json`, and give it a new output directory. Run the control with `configs/wallet_control.json`, without `--cloud`, and provide `--wallet 0x...`. `--control-mode arbitrage` starts a separate pure-arbitrage run. Do not pool it with wallet-copy returns.

All bots started from the dashboard share `data/model-budget.sqlite`. CLI runs from the same directory share it too. Separately extracted bot directories have separate local budgets; use a single dashboard or a central account-level spend limit for global cost control across hosts. A timed-out request retains its reserved cost because provider billing may have occurred. No retry is automatic. Actual token cost is a tariff-based estimate; reconcile invoices separately.

## Provider contract

The implementation sends a bounded Responses request with `store:false`, a strict JSON output schema, explicit reasoning effort and a 2,048 output-token ceiling. The full structured response must complete and cite supplied evidence IDs. The code validates finite probabilities and ordered uncertainty bounds before sizing. Probabilities and model self-confidence are uncalibrated until held-out validation shows otherwise. [Structured Outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs).

Price and wallet information are withheld during forecasting to reduce anchoring. After inference, common deterministic rules compare conservative model probability bounds with executable depth and cost. This deliberately separates probability estimation from risk authorization. Models cannot alter reserves, enable live trading or invoke tools.

## Before treating a cloud run as validated

Check `model-calls.json` for the actual model ID, response ID, token usage, latency, evidence IDs and output; inspect `journal.sqlite` and `acceptance.json`. A missing cloud key must never be described as a successful model test. Record all refused and truncated responses as part of reliability reporting. Increasing output tokens, changing the prompt/model, or changing pricing requires a new frozen configuration/code hash and new results.
