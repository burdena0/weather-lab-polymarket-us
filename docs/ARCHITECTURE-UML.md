# Weather Lab architecture UML

These diagrams describe the implemented `weather-methods-20260916-v2` architecture. V1 and original protocol branches remain supported. The containing Git revision identifies the exact implementation. Each arm uses the same runtime with a different strategy configuration. Component views show logical responsibilities; they do not imply separate processes or one Python class per box. Sequence views show call order and decision branches.

Open the [offline diagram gallery](architecture/index.html) locally, or open the SVG figures below. The Mermaid sequence diagrams also render directly on GitHub. All figures use monochrome, square components and system sans-serif text.

The new protocol applies to newly packaged real-data runs. Earlier configurations and synthetic demos retain the original protocol. Its v2 availability gate rejects decisions before September 16, 2026 at 17:30:00 UTC (v1 retains 17:07:01 UTC). Validation failures return a skip before inference or intent creation. See the [v2 hypotheses and separate setup steps](WEATHER-HYPOTHESES.md), and the [original method review](WEATHER-METHODS-REVIEW.md).

## 1. Deterministic control

![UML component diagram: deterministic control](architecture/01-control.svg)

**Package:** `01-wallet-control.zip`. Copy and arbitrage are mutually exclusive run configurations. Copying an account is an unhedged benchmark. The basket mode models a complete disjoint temperature partition with ordinary aggregate payout of $1; it assumes all legs fill together in the paper simulator.

```mermaid
sequenceDiagram
    autonumber
    participant E as engine.replay
    participant S as Strategy (wallet_control)
    participant D as protocol module
    participant Q as core quote and mapping checks
    participant A as Account (isolated paper ledger)
    participant J as Run journal
    E->>S: decide(markets, signals, account, now)
    opt New research protocol configured
        S->>D: require_available(now)
        break Decision predates protocol availability
            S-->>E: Skip without further decision work
        end
    end
    alt control_mode = copy
        S->>S: Deduplicate reference-wallet signals
        S->>S: Check start time and signal freshness
        opt New research protocol configured
            S->>D: Require explicit full weather-day interval
        end
        S->>S: Check exact US identity, reviewed mapping and rules
        S->>Q: Size within reserve and exposure limits
        Q-->>S: Quantity and stressed cost
        S->>S: Apply reference price tolerance
    else control_mode = arbitrage
        S->>S: Group by station-day and verify complete partition
        opt New research protocol configured
            S->>D: Require identical full weather-day intervals for all legs
        end
        S->>Q: Quote one YES share per bucket with synchronized books
        Q-->>S: Aggregate cost including modeled fees and slippage
        S->>S: Require discovery spread at least 0.03 and sufficient budget
    end
    S-->>E: Intent ready after 2 seconds, expires after 60 seconds, or skip
    E->>J: Record decision or skip
    opt Intent is ready in a later eligible frame
        E->>A: fill(legs, current books, limits)
        A->>Q: Recheck depth, identity, reserve and costs
        Note over A,Q: Basket fill requires every leg and remaining spread of at least 0.02
        A-->>E: Paper fill or rejection
        E->>J: Record result and account checkpoint
    end
    opt Final venue settlement becomes available
        E->>A: settle(verified binary outcome, now)
        E->>J: Record settlement
    end
```

No model calls. Wallet signals require an explicitly reviewed mapping from the international public wallet feed to the exact US contract. An unmatched signal is skipped.

## 2. Fixed LLM with point-in-time RAG

![UML component diagram: fixed LLM](architecture/02-fixed.svg)

**Package:** `02-fixed-llm.zip`. One configured medium-tier call with medium reasoning effort for each eligible decision. RAG is SQLite FTS5 plus numeric weather analogues; no embedding service or model fine-tuning is implemented.

```mermaid
sequenceDiagram
    autonumber
    participant E as engine.replay
    participant R as EvidenceStore
    participant S as Strategy and core.context
    participant D as protocol module
    participant M as CloudModel
    participant L as Shared budget ledger
    participant P as Configured cloud model
    participant A as Account
    E->>R: retrieve(market, decision time, strategy_memory flag)
    R-->>E: Prior days, rules, notes and audit IDs, v2 retains seven latest days
    E->>S: decide with retrieved evidence and current books
    opt New research protocol configured
        S->>D: require_available(now)
        break Decision predates protocol availability
            S-->>E: Skip without a model call
        end
    end
    S->>S: Validate forecast, book and at least 10 causal history days
    opt New research protocol configured
        S->>D: diagnostics(market, context, now)
        D->>D: Validate full 23-25 hour path and contract interval
        opt V2 configured
            D->>D: Validate GFS and IFS location, receipts and hourly paths
            D->>D: Derive consensus, peak, regime and recent-trend entry policy
        end
        D-->>S: Weather diagnostics and versioned entry policy
    end
    Note over S,P: Forecast context excludes market prices, no model tool access
    S->>M: predict(context, medium tier, medium effort)
    M->>L: Reserve estimated cost under shared daily cap
    M->>P: Structured probability request with protocol guidance when enabled
    P-->>M: Probability, bounds, confidence, abstain and evidence IDs
    M->>L: Reconcile known token usage
    M->>M: Validate schema, probability bounds and supplied citations
    M-->>S: Validated prediction, latency and call audit
    S->>S: Apply selected uncertainty gate and existing owned-inventory exit logic
    opt Considering a new entry under v2
        S->>S: Check hypothesis blocks and permitted side
        S->>S: Apply extra edge and quantity factor, then shared fill limits
    end
    S-->>E: Intent or abstention with audit
    opt Intent ready in a later observed frame
        E->>A: Recheck and simulate fill after max(2 seconds, model latency)
        A-->>E: Fill or rejection
    end
    Note over E,A: Engine journals retrieval, decisions, fills and later settlements
```

Budget/configuration failures stop a model call. Unknown billed usage retains its reservation; the adapter does not automatically retry. Fixture mode substitutes `FixtureModel` and makes no cloud call.

## 3. Adaptive model routing with point-in-time RAG

![UML component diagram: adaptive LLM](architecture/03-adaptive.svg)

**Package:** `03-adaptive-llm.zip`. Same evidence, risk policy and fill engine as architecture 2. A deterministic router selects the initial tier; the LLM does not choose its own budget or execution authority.

```mermaid
sequenceDiagram
    autonumber
    participant E as engine.replay
    participant R as EvidenceStore
    participant S as Strategy
    participant D as protocol module
    participant T as route(context)
    participant M as CloudModel and budget gate
    participant P as Configured cloud model
    participant A as Account
    E->>R: Retrieve eligible evidence as of decision time
    R-->>E: History, documents, optional strategy cards and audit hashes
    E->>S: decide(current frame)
    opt New research protocol configured
        S->>D: require_available(now)
        break Decision predates protocol availability
            S-->>E: Skip without a model call
        end
    end
    S->>S: core.context validates forecast and at least 10 causal history days
    opt New research protocol configured
        S->>D: diagnostics(market, context, now)
        D->>D: Validate full 23-25 hour path and contract interval
        opt V2 configured
            D->>D: Validate GFS and IFS location, receipts and hourly paths
            D->>D: Derive consensus, peak, regime and recent-trend entry policy
        end
        D-->>S: Weather diagnostics and versioned entry policy
    end
    S->>T: Estimate computational effort
    T->>T: Sum four baseline, two v1 and two v2 features when enabled
    T-->>S: Small/low, medium/medium or large/high
    S->>M: predict(context, selected tier, effort)
    M->>P: Budget-reserved structured request
    P-->>M: Prediction and usage
    M-->>S: Validated prediction and audit
    opt Width above 0.30 OR confidence below 0.50, and initial tier is not large
        S->>M: One escalation to large tier, high effort
        M->>P: Second budget-reserved request with the same context
        P-->>M: Replacement prediction
        M-->>S: Validated prediction and second call audit
    end
    S->>S: Force abstention if final width exceeds 0.40
    S->>S: Apply risk profile and existing owned-inventory exit logic
    opt Considering a new entry under v2
        S->>S: Check hypothesis blocks, permitted side, extra edge and quantity factor
    end
    S-->>E: Intent or skip, include route features and all call audits
    opt Intent ready in a later observed frame
        E->>A: Recheck and fill after max(2 seconds, summed call latency)
        A-->>E: Paper fill or rejection
    end
```

Router score adds one point for each: fewer than 30 history days; residual standard deviation above 3°F; forecast within 2°F of a bucket boundary; absolute forecast revision above 2°F. V1 adds one point for a half-degree probability span above 0.15 and one for a largest hourly temperature change above 3°F. V2 adds one point for model spread above 3°F or peak-window distance above 3 hours, and one for a detected regime change. Score 0 selects small/low; 1–2 medium/medium; any score at least 3 selects large/high (maximum 4 originally, 6 in v1 and 8 in v2). This is a fixed heuristic, not a trained router. Maximum two calls per eligible decision.

## 4. PolySwarm-inspired persona ensemble

![UML component diagram: PolySwarm-inspired ensemble](architecture/04-polyswarm.svg)

**Package:** `04-polyswarm.zip`. Five roles by default: meteorologist, historical calibration analyst, settlement auditor, skeptic and weather-regime analyst. These are sequential stateless model requests within one strategy worker, not autonomous spawned agents. The implementation is inspired by the research and is not a full paper replication.

```mermaid
sequenceDiagram
    autonumber
    participant E as engine.replay
    participant R as EvidenceStore
    participant S as Strategy (polyswarm)
    participant D as protocol module
    participant M as CloudModel and budget gate
    participant P as Medium-tier cloud model
    participant G as Consensus aggregation
    participant A as Account
    E->>R: Retrieve eligible evidence at decision time
    R-->>E: History, documents, optional strategy cards and audit hashes
    E->>S: decide(current frame)
    opt New research protocol configured
        S->>D: require_available(now)
        break Decision predates protocol availability
            S-->>E: Skip without a model call
        end
    end
    S->>S: core.context validates forecast and at least 10 causal history days
    opt New research protocol configured
        S->>D: diagnostics(market, context, now)
        D->>D: Validate full 23-25 hour path and contract interval
        opt V2 configured
            D->>D: Validate GFS and IFS location, receipts and hourly paths
            D->>D: Derive consensus, peak, regime and recent-trend entry policy
        end
        D-->>S: Weather diagnostics and versioned entry policy
    end
    loop Each configured persona, sequentially, default count 5
        S->>M: predict(same context, medium tier/effort, persona)
        M->>P: Budget-reserved request with protocol guidance when enabled
        Note over M,P: No prices or other persona outputs
        P-->>M: Persona prediction and token usage
        M-->>S: Validated prediction and audit
    end
    S->>G: Aggregate persona predictions and external market midpoint
    alt Any persona abstains
        G-->>S: Abstain
    else All personas return forecasts
        G->>G: Weight each probability by confidence clipped to 0.10–0.80
        G->>G: Blend 70% consensus with 30% market midpoint
        G->>G: Envelope bounds and union evidence IDs
        G->>G: Abstain if persona probability standard deviation exceeds 0.15
        G-->>S: Aggregate probability, bounds and confidence
    end
    S->>S: Apply risk profile and existing owned-inventory exit logic
    opt Considering a new entry under v2
        S->>S: Enforce shared hypothesis entry rules and sizing
    end
    S-->>E: Intent or abstention, all persona audits and total latency
    opt Intent ready in a later observed frame
        E->>A: Recheck and fill after max(2 seconds, summed call latency)
        A-->>E: Paper fill or rejection
    end
```

Persona count is configurable from 3 to 50, with the five role prompts cycling. Confidence weights are uncalibrated, and model errors may be correlated. A request failure prevents completion of the decision; partial ensembles are not silently substituted.

## Shared runtime and boundaries

```mermaid
classDiagram
    class Lab {
        +state()
        +mutate(path, raw)
    }
    class Session {
        +start()
        +state()
        +queues
        +workers
    }
    class ReplayEngine {
        <<module>>
        +replay(config, dataset, output)
    }
    class Strategy {
        +decide(markets, signals, account, now)
    }
    class WeatherProtocol {
        <<module>>
        +require_available(now)
        +settlement_window(market)
        +diagnostics(market, context, now)
    }
    class WeatherHypotheses {
        <<module>>
        +compare(market, context, now, flags)
    }
    class ModelForecasts {
        <<module>>
        +collect(source, market, latitude, longitude)
        +decode(response, market, receipt)
    }
    class PublicSource {
        +forecast(market, with_comparison)
    }
    class EvidenceStore {
        +ingest(rows)
        +retrieve(market, now, include_strategies)
    }
    class Account {
        +fill(legs, markets, now)
        +settle(outcome, now)
        +summary(markets, now, elapsed)
    }
    class CloudModel {
        +predict(context, tier, effort, persona)
    }
    class FixtureModel {
        +predict(context, tier, effort, persona)
    }
    Lab *-- EvidenceStore
    Lab o-- Session : active session
    Session ..> ReplayEngine : one worker per strategy
    ReplayEngine ..> Strategy : creates per run
    ReplayEngine ..> Account : creates per run
    ReplayEngine ..> EvidenceStore : optional causal retrieval
    EvidenceStore ..> StrategyMemory : bounded as-of method cards
    class StrategyMemory {
        +validate(card)
        +retrieve(db, market, now)
        +inventory(db)
    }
    Strategy ..> WeatherProtocol : versioned real-data decision checks
    CloudModel ..> WeatherProtocol : versioned forecasting guidance
    WeatherProtocol ..> WeatherHypotheses : v2 diagnostics and entry policy
    PublicSource ..> ModelForecasts : optional named GFS and IFS collection
    CloudModel ..> WeatherHypotheses : v2 model guidance
    Strategy ..> CloudModel : configured cloud mode
    Strategy ..> FixtureModel : test mode alternative
```

- **Control plane:** browser → loopback HTTP/CSRF checks → `Lab` → validated ZIP configuration → `Session` or offline `replay`. ZIP uploads register declarative configurations; uploaded Python is not executed.
- **Data plane:** public capture or recorded frames → chronological replay → strategy → delayed intent → observed-depth paper fill → settlement → immutable run artifacts. Four session workers have independent accounts and size-one input queues; a slow worker can drop frames. Public frames are stamped no earlier than processing time. Common publication therefore does not guarantee identical consumed frames; compare logged receipts and dropped-frame counts in research results.
- **Risk:** $50 starting capital; $40 protected cash; $5 common position/station-day ceilings; five-share proposal cap. LLM Reliable/Balanced/Risky settings affect next-run confidence, uncertainty, edge and fractional-Kelly rules. Reliable uses a tighter $2 event cap. All fills recheck hard limits. $200/month overhead is reported separately for each alternative; model cost is additional.
- **Causality:** RAG filters publication, receipt and availability timestamps at the decision time and uses prior-day completed history. Settlements cannot enter a prediction before availability. These controls constrain supplied data; they cannot prove that an LLM's pretrained weights lack historical outcome knowledge.
- **Protocol:** new real-data package configurations freeze the research version. The control validates full-day settlement intervals without a forecast or LLM. LLM arms require a complete hourly path, add bounded diagnostics to context and audits, and receive versioned model guidance. V2 validates named GFS/IFS forecasts, exposes cloud/wind and peak diagnostics, and enforces switchable entry rules after existing exit logic. The two model families are not assumed statistically independent. Sample/demo entry points explicitly remove this protocol and record the original configuration.
- **Persistence:** evidence SQLite index, shared model-budget SQLite ledger, independent hash-chained run journals, input/config/code hashes, checkpoints and acceptance receipts. Checkpoints support inspection; automatic crash resume is not implemented.
- **Deployment:** all orchestration and paper accounting run on the PC. Only configured inference requests go to the cloud API. Small/medium/large are configuration tiers; exact provider model IDs and returned IDs belong in the run audit. Diagrams do not assert API availability or successful paid inference.

## Recurring evidence collection

```mermaid
sequenceDiagram
    participant T as Standalone scheduled task
    participant C as collect-evidence CLI
    participant U as Public US, NWS and Open-Meteo
    participant F as Immutable local receipts
    participant R as EvidenceStore
    participant L as Dashboard readiness
    Note over T,C: Daily 09:00 Eastern, Sol with low reasoning, old heartbeat paused
    T->>T: Inspect latest report and skip an already successful daily collection
    T->>C: Collect within five minutes into a new run directory
    C->>U: Bounded public GET requests
    U-->>C: Rules, up to five NWS station-days and ten GFS/IFS series
    C->>F: Archive original receipts and complete hourly forecast paths
    C->>R: Ingest rules, NWS and comparison forecasts with actual availability
    C-->>T: Report coverage, errors and next outcome-review step
    T->>L: Refresh through loopback API if dashboard is running
    Note over C,R: Completed history requires separately reviewed final CLI outcomes
    Note over T,L: No strategy inference, trading sessions or order submission
```

Reviewed methodology notes are a separate, timestamped `research_note` input. They never count as completed weather history. The scheduled task runs in the Weather Lab deployment and is separate from the older SupahTrade trading experiment.

## Offline hypothesis ablation

```mermaid
sequenceDiagram
    participant C as ablate-weather CLI
    participant B as ablation.run
    participant E as engine.replay
    participant F as Immutable output directories
    C->>B: Config, one dataset, new output root and optional cloud flag
    B->>F: Freeze dataset hash and seven-variant plan
    loop Sequential variants with separate accounts and journals
        B->>E: V1, v2 evidence-only, all rules or leave-one-rule-out config
        E-->>B: Run result, accounting and forecast scores
        B->>F: Write comparison summary after each completed variant
    end
    Note over B,E: Shared cloud budget when explicitly enabled, otherwise fixture model
    Note over B,F: Existing runs preserved, no parameter search or profitability assertion
```

Ablations retain v2 evidence/routing when an entry switch is disabled. They compare entry rules, not a full decomposition of each model's reasoning. A failed variant stops the sequence with partial results saved. See [WEATHER-HYPOTHESES.md](WEATHER-HYPOTHESES.md).

## Apple Weather study: separate implemented pipeline

```mermaid
sequenceDiagram
    participant I as iPhone Shortcut
    participant C as iCloud Drive
    participant F as ShortcutFeed
    participant D as DisagreementStudy
    participant U as Public US market and NWS sources
    participant V as Dashboard comparison
    I->>I: Retrieve fixed-location daily Apple forecast
    I->>C: Overwrite station JSON on configured schedule
    C-->>F: Sync file to configured Windows folder
    D->>U: Retrieve contracts, NWS forecast/observation and books
    D->>F: Read forecast for matching station and contract date
    F->>F: Validate size/schema/date/units and 30-minute freshness
    F->>F: Persist original first receipt and payload hash
    F-->>D: Device-reported daily high and provenance limitations
    D-->>V: Forecast-bin matches, prices, visible shares and audit gaps
    Note over D,V: No trading intents, automatic RAG admission or strategy input connection
```

The phone/iCloud path still requires user setup and end-to-end device verification. WeatherKit remains an optional CLI source. Station coordinates and weather-day equivalence are unverified for Shortcuts exports. This side pipeline must not be drawn as an active input to the four strategies until a reviewed integration exists. NWS final daily highs are scored separately after the day; a current observation is not that outcome.

## Strategy memory

New forecasting package configurations enable `strategy_memory: true`. Original configurations default to false; the control never consumes strategy cards. Synthetic demos and weather-hypothesis ablations explicitly disable memory. The evidence ledger stores immutable `strategy_card` revisions. Retrieval selects the latest revision available at decision time before applying retirement, expiry, station, source and synthetic filters. It adds at most four cards / 8 KB to the existing weather context, records their payload hashes, and excludes monetary evaluation results from probability prompts. Ranking uses applicability and deterministic station-day rotation, not returns. `CloudModel` adds guidance that cards are untrusted references and cannot authorize execution. No embedding service, executable strategy loading, automatic promotion or model training was added. Each changed run still uses a new journal database. See [STRATEGY-MEMORY.md](STRATEGY-MEMORY.md).

## Recent archive benchmark: separate weather-only pipeline

```mermaid
sequenceDiagram
    participant C as historical_window CLI
    participant I as IEM MOS and NWS CLI archives
    participant F as Immutable corpus and receipts
    participant B as Historical benchmark
    participant M as CloudModel or statistical baseline
    participant D as Dashboard recent-history summary
    C->>F: Freeze station, test dates and earlier calibration dates
    C->>I: Bounded public reads for forecasts and raw CLI text
    I-->>C: Archived forecasts, daily highs and publication metadata
    C->>C: Verify station, date, sample coverage and raw observed maximum
    C->>F: Hash calibration, cases and separate labels; preserve receipt times
    Note over C,F: Assumed six-hour forecast availability; never backdate live RAG
    B->>F: Verify hashes and nonoverlapping calibration/test periods
    Note over F,B: Strict replay blocked unless historical availability is verified
    loop At most 31 test days; explicit exploratory override when needed
        B->>B: Filter calibration by outcome publication; redact station/date
        B->>M: Label-free context and bounded inference deadline
        alt Valid forecast
            M-->>B: Probability and call audit
        else Billing, auth, rate, budget or deadline failure
            M-->>B: Sanitized failure; retain uncertain budget reservation
            B->>B: Skip further cloud requests in this benchmark
        end
        B->>F: Append prediction or skip and hash-chain audit
    end
    B->>F: Only now open test labels and write Brier scores
    F-->>D: Local aggregate report with coverage, scores and cloud blocker
    Note over B,D: No historical books, wallet trades, full market blend or profit claim
```

The recent-window downloader is separate from the original August fixture downloader. Both use the bounded historical runner. Archives remain outside the live evidence index. The September 6–15 pilot contains five stations and keeps calibration in August 6–September 5. Its current cloud attempt is blocked by provider credits; the statistical baseline completed. See [RECENT-HISTORY.md](RECENT-HISTORY.md) for reproducible commands, evidence paths and limits.

## Source map

| Responsibility | Implementation |
| --- | --- |
| Dashboard, ZIP registration, session dispatch | `web/app.js`, `weatherlab/server.py`, `weatherlab/packages.py` |
| Public sources and frame publication | `weatherlab/sources.py`, `weatherlab/session.py` |
| Causal replay, journals, delayed intents | `weatherlab/engine.py` |
| Four decision policies, router, aggregation, profiles | `weatherlab/strategies.py` |
| Context validation, quotes, fills, paper account | `weatherlab/core.py` |
| Protocol availability, settlement intervals, hourly diagnostics and model guidance | `weatherlab/protocol.py` |
| Evidence collection and outcome pairing | `weatherlab/research.py`, `weatherlab/sources.py` |
| Named GFS/IFS collection and validation | `weatherlab/weather_models.py` |
| Weather features, switchable entry policies and ablations | `weatherlab/hypotheses.py`, `weatherlab/ablation.py` |
| RAG and immutable evidence | `weatherlab/rag.py` |
| Strategy reference validation, selection, seed library and inventory | `weatherlab/strategy_memory.py` |
| Model adapter, persona prompts, cost reservation | `weatherlab/models.py` |
| Recent archive download, raw CLI checks and weather-only benchmark | `weatherlab/historical_window.py`, `weatherlab/historical.py` |
| Apple/NWS side study | `weatherlab/shortcut_feed.py`, `weatherlab/disagreement.py` |

Figures are generated by `python docs/architecture/render.py`; this uses only the Python standard library. SVGs and the HTML gallery work offline. Mermaid source is embedded above for editing on GitHub or in a compatible diagram editor.

## Maintenance rule

Architecture changes must update this document and `docs/architecture/render.py` in the same change. Regenerate the four SVGs and offline gallery, verify diagram rendering and call order against the implementation, and rebuild the distributable ZIPs. State whether a connection is implemented, optional, or still unconnected. Keep the original protocol and new protocol branches explicit.
