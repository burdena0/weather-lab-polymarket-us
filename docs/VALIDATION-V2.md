# Revision verification — September 15, 2026

## Verified locally

- 67 tests pass: existing accounting/session safeguards plus forecast interval coverage, future-day selection, setup redaction, settlement identity/finality, unchanged original reconciliation journals, reviewed history pairing, held-out-label independence, strict availability refusal, corpus hashing and bounded row reads.
- Collected 60 current US contract rules and five distinct future station-day NWS forecast snapshots without reported source errors. They are indexed as rules/forecasts, not completed historical pairs.
- A 30-second future-day public capture produced 14 frames without forecast-coverage errors. This is feed verification, not fill evidence.
- Verified one archived contract's binary USD settlement by matching resolved metadata, unchanged rules and book settlement fields. No account or order endpoint was used.
- Downloaded 31 July calibration examples and all 31 August 2026 KLAX forecast/outcome examples. There were no missing-day errors. Normalized examples are bundled; hashed raw receipts remain local and the downloader can produce a new version.
- Exploratory August statistical baseline: 31 scored days, 16 YES and 15 NO outcomes at the fixed 80F threshold, mean Brier 0.1183369. CLI run completed in approximately 0.053 seconds, with 108,510 bytes of traced peak Python allocations. Browser-triggered run also completed. These are observed runs, not runtime guarantees or proof against every possible memory leak.
- Browser verified the historical replay button and displayed result. The monochrome desktop interface rendered without console warnings/errors. Mobile width 390 yielded 375 CSS-pixel viewport and 375 scroll width, with no page-level horizontal overflow.

## Scope of those results

The monthly corpus uses archived GFS MOS three-hour forecast samples, distinct from the prospective hourly NWS grid product. Historical first-seen availability is unverified; the six-hour dissemination delay is an explicit assumption. Strict mode blocks those records. Initial test aggregates informed harness development, so this month is an exploratory pilot, not a pristine confirmatory holdout.

The application isolates held-out labels, rejects future-dated inputs, freezes calibration, blinds station/date and uses stateless model calls. Those controls cannot establish that a pretrained model never saw the event during training. No actual paid LLM request was made in this revision.

No historical market books, signals or executable fills are invented. The baseline score does not establish profitability. The monthly PolySwarm cloud option is a weather-only persona ablation without market blending, not a full trading-strategy replication. Intraday observed-high adaptation and a reviewed prospective history corpus remain unfinished research work.

## Runtime and data boundaries

The updated local dashboard is on port 8767. The earlier session on 8766 was stopped before starting a fresh session with the remaining time. Original run folders and old SupahTrade supervisors remain untouched. User credentials, account snapshots, live captures, local runtime logs and run databases are excluded from Git and ZIPs. The `.env` template preserves disabled cloud inference and a zero spending cap.
