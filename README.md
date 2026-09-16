# Weather Lab — Polymarket US paper research

Four independently packaged strategies and a new local dashboard. Python 3.10+ with SQLite FTS5; no pip install or Node build is required. This directory is independent of the old dashboard and its experiment databases. No live order adapter, automatic schedule, or paid calls are enabled. Optional read-only account linking uses local credentials and Node.js built-in cryptography (no npm dependencies); see docs/ACCOUNT-LINK.md. Background sessions start only when explicitly requested in the dashboard.

## Start here

[Setup checklist](docs/GETTING-STARTED.md) · [August historical test](docs/HISTORICAL-REPLAY.md) · [Prospective data collection](docs/DATA-COLLECTION.md)

[Apple Weather / NWS tracker and arbitrage explanation](docs/APPLE-NWS-STUDY.md): prospective forecast, observation and contract-depth collection; manual iPhone input or optional authenticated WeatherKit. Separate post-day CLI scoring. This study does not execute trades.


```powershell

git clone https://github.com/burdena0/weather-lab-polymarket-us.git
cd weather-lab-polymarket-us

python -m weatherlab serve --port 8767

```

Open http://127.0.0.1:8767. Upload the four bot ZIPs from `dist`, then click **Start sample** for an animated background paper session, or **Replay sample** for one completed fixture run. Each sample uses an independent $50 account and a deterministic test double; the dashboard explicitly labels those results synthetic. Start the server from the extracted dashboard ZIP the same way on another computer.

| ZIP | Role |

| --- | --- |

| `01-wallet-control.zip` | Deterministic account following; separately selectable exhaustive-temperature-basket arbitrage |

| `02-fixed-llm.zip` | Fixed Terra inference with retrieved evidence |

| `03-adaptive-llm.zip` | Deterministic effort estimation, Luna/Terra/Sol routing, one bounded escalation |

| `04-polyswarm.zip` | Five weather personas, confidence-capped consensus, market blend and disagreement gate |

| `weather-lab-dashboard.zip` | New dashboard, shared runtime, documentation, fixtures and tests |

Every bot ZIP is standalone: extract it and run `python -m weatherlab demo`. Each contains `manifest.json`, runtime source, fixtures, documentation and tests. Upload registration is declarative: the dashboard checks hashes and dispatches its own reviewed runtime. It never imports arbitrary uploaded Python. Config changes create fresh runs; previous results are retained.

## What works now

- Monochrome dashboard with system sans-serif typography, setup checks, public evidence collection and historical replay.
- Bundled July calibration and August 2026 KLAX weather examples; fast bounded-memory baseline and optional stateless cloud forecast benchmark.
- Verified binary settlement retrieval and separate post-run paper-ledger reconciliation.


- Public Polymarket US inventory/book capture and bounded NWS hourly forecast retrieval.

- RAG index creation from JSONL; station/time filters, numeric analogues and SQLite FTS5 lexical search.

- Four paper replay strategies, delayed observed-depth fills, fee/slippage stress, exposure/reserve limits, exits, and supplied final-settlement accounting.

- Structured OpenAI Responses adapter, provider-side model selection, bounded cost reservation and no automatic retry after uncertain billing.

- Local uploads, sample/recorded/cloud replay, background sample/public sessions, evidence ingestion, decision audits and result export.

- Independent Reliable / Balanced / Risky buttons for each LLM strategy, with frozen per-run settings.

- Immutable run folders, independent SQLite journals, hash chains, checkpoints, acceptance receipts, Brier/log-loss scoring and paired date-cluster evaluation.

## What the delivery does not establish

The supplied fixtures are synthetic. No paid cloud request, real forecast edge, real fill, profitable strategy, comprehensive historical corpus or continuous prospective trading run is established. The application supports bounded background sessions (15 minutes, one hour, or four hours), concurrent strategy workers and continuous public capture within a session. Public sessions preserve accounts across capture windows, and completed runs can use a separate settlement-only reconciliation command. Intraday observed highs remain unimplemented; new captures select future venue-days with complete hourly forecast coverage. Checkpoints support inspection, not automatic crash resume. A later publication experiment needs a predeclared prospective collection protocol, settlement reconciliation, a complete real evidence corpus, and account-authorized model validation. Do not describe retrospective replay as prospective execution.

The native US API does not supply the international public-wallet feed. Copy mode requires a configured international wallet plus reviewed exact mapping to US contracts. Hourly station observations or Weather Underground rules are not assumed equivalent to NWS CLI settlement. No matching evidence means no copied trade. Arbitrage mode needs complete disjoint temperature coverage and sufficient synchronized depth; bounded captures may not contain the full basket.

Cloud calls require your own API access, verified current token prices and an explicit local budget. The default budget is zero. Model IDs may be changed locally; preserve exact IDs and the returned model/usage audit in the paper.

## Guides

- [Read-only account linking](docs/ACCOUNT-LINK.md)

- [LLM setup and commands](docs/LLM-SETUP.md)

- [RAG corpus, training data and schemas](docs/DATA-AND-RAG.md)

- [Research design, source references and limitations](docs/RESEARCH-DESIGN.md)

- [Harness contracts and verification](docs/HARNESS.md)

- [Risk profile settings](docs/RISK-PROFILES.md)

- [Background sessions and operation](docs/SESSIONS.md)

- [Delivery validation](docs/VALIDATION.md)

## Commands

```powershell

python -m unittest discover -s tests -v

python build_packages.py

python -m weatherlab demo --strategy adaptive_llm

python -m weatherlab ingest --jsonl examples/history.synthetic.jsonl

python -m weatherlab capture --out captures/window-001 --seconds 45 --max-markets 4

python -m weatherlab replay --config configs/fixed_llm.json --dataset examples/dataset.synthetic.json --rag data/evidence.sqlite --out runs/example-001

python -m weatherlab.harness runs/example-001

```

Keep synthetic and real evidence indexes separate. `--out` must be new; immutable results are never overwritten. Public capture is an unscheduled, bounded read-only diagnostic and does not extend the existing seven-session experiment. No old supervisors are started or changed.

For a new design/version, freeze a new configuration and new run directory. Preserve `$50 initial capital / $40 reserve / $200 monthly overhead`. Fees use a deliberately conservative assumption documented in the research guide, not verified venue match receipts.

