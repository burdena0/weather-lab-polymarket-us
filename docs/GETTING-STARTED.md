# Setup checklist

This is the setup you need to complete. The separate [historical test guide](HISTORICAL-REPLAY.md) covers running August's experiment after setup.

## 1. Open the project

Use the existing Weather Lab folder on this computer. On another computer:

```powershell
git clone https://github.com/burdena0/weather-lab-polymarket-us.git
cd weather-lab-polymarket-us
python --version
node --version
```

Python 3.10+ with SQLite FTS5 runs the paper core. Node is only needed for account linking. No pip/npm packages are required. GitHub stores the source and ZIPs; the server runs on your computer.

## 2. Enter your API key locally

1. Open the [OpenAI API dashboard](https://platform.openai.com/) and select your billing project. Set up API billing yourself if required.
2. Create a project API key with permission to list models and create Responses. A ChatGPT/Codex subscription does not configure this application's API access.
3. This computer already has a blank local `.env`. For a fresh checkout only:

```powershell
if (-not (Test-Path .env)) { Copy-Item settings.env.example .env }
notepad .env
```

4. Paste your key after `OPENAI_API_KEY=`. Save locally. Never put the key in chat, GitHub, or ZIP files.
5. Keep `WEATHERLAB_ENABLE_CLOUD=0` and the daily budget at zero while checking access:

```powershell
python -m weatherlab doctor --check-models
```

Expected: `api_key_present: true` and `listed: true` for all three configured IDs. This performs a model-list GET, not paid inference. HTTP 401 means authentication needs attention. Missing models require accessible replacements, recorded as a new experiment configuration. Listing access does not prove a Responses request will succeed.

## 3. Check prices and choose your own cap

The template contains these prices verified September 15, 2026, in USD per million input/output tokens:

| Setting | Model | Input,output |
| --- | --- | --- |
| WEATHERLAB_PRICE_SMALL | gpt-5.6-luna | 0.20,1.20 |
| WEATHERLAB_PRICE_MEDIUM | gpt-5.6-terra | 2,12 |
| WEATHERLAB_PRICE_LARGE | gpt-5.6-sol | 4,20 |

Recheck [official model prices](https://developers.openai.com/api/docs/models) before enabling calls. Set `WEATHERLAB_DAILY_API_BUDGET_USD` to the amount you personally authorize for a UTC day; accepted positive caps are at most $20. No amount has been chosen for you. All strategies in the same working directory share a ledger; separate copies have separate caps. Estimates require invoice reconciliation.

## 4. Start the dashboard

1. Stop an existing paper session with **Stop** and wait for its workers to finish. Stop the old server with Ctrl+C before starting another on the same port.
2. Run:

```powershell
python -m weatherlab serve --port 8767
```

3. Open [Weather Lab](http://127.0.0.1:8767/).
4. Import the four `dist/01-...` through `dist/04-...` ZIPs.
5. Click **Check setup** for missing configuration and data. Click **Check model access** after saving `.env` and restarting.
6. **Start sample** tests all four strategies with synthetic fixtures. It does not establish model quality or profitability.
7. Refresh the read-only Polymarket US account link if needed. It does not enable live trading or fill the reference-wallet field.

## 5. Choose which experiment to run

- **Historical weather accuracy:** follow [HISTORICAL-REPLAY.md](HISTORICAL-REPLAY.md). Baseline testing needs no key. Cloud testing needs your key, prices, chosen budget, and explicit acceptance of unverified archive availability. It does not establish trading returns.
- **Prospective public paper trading:** follow [DATA-COLLECTION.md](DATA-COLLECTION.md). Collect and review at least ten eligible prior forecast/CLI outcome days per station. This is a software minimum, not a research sample-size recommendation.
- **Wallet copy:** provide the public wallet and reviewed exact mappings to US contract rules. Your linked private US account is not the international public-wallet feed. Many contracts have no equivalent mapping; do not invent one.
- **Strict basket arbitrage:** select it in Control mode before a fresh run. It requires a complete exhaustive basket and synchronized depth. Four selected contracts may be insufficient. Keep its results separate from copy control.

## 6. Enable cloud inference when ready

1. Set `WEATHERLAB_ENABLE_CLOUD=1` only after configuring your key, accessible model IDs, current prices and your chosen cap.
2. Save `.env` and restart the server.
3. For prospective paper work, select risk profiles before starting a fresh 15-minute public session. Reliable is stricter, not a return guarantee.
4. Confirm **validated cloud calls** increases. Inspect response IDs, returned model, usage and evidence in `model-calls.json` and the decision audit. Running workers and a `cloud` label alone do not prove a model ran.
5. Treat history, quote, budget and schema errors as skips. Do not bypass them to manufacture trades.

Official references: [API quickstart](https://developers.openai.com/api/docs/quickstart), [model listing](https://developers.openai.com/api/reference/resources/models/methods/list).
