# Prospective data and settlement workflow

## Archive rules and pre-day forecasts

Use **Collect public evidence** in the dashboard, or:

```powershell
python -m weatherlab collect-evidence --out data/research/day-001
python -m weatherlab doctor
```

Always choose a new output directory. The command stores hashed public receipts, indexes current rules, and archives up to five future station-day forecasts. It makes no LLM calls. It also archives explicitly named GFS and ECMWF hourly forecasts for each station-day. The separate daily 09:00 Eastern Sol/low task runs this collector on this host; other installations must configure their own schedule. See [WEATHER-HYPOTHESES.md](WEATHER-HYPOTHESES.md) for comparison-feed checks and test switches.

The first local collection saved 60 rule records and five pre-day forecasts, with no source errors. It created zero completed historical pairs: outcomes cannot be known before their target day ends.

The forecast must cover the full venue interval from `gameStartTime` to `endDate`, in contiguous hours. The interval is not inferred from a date substring or the computer's timezone. Check contract rules before treating that interval as the scientific target.

```powershell
python -m weatherlab capture --out data/research/window-001 --seconds 45 --max-markets 4
```

New public captures select future venue-days, sorted by date/station/slug. `--selection all_dates` is available for diagnostic capture. It does not solve missing intraday observations. Missing/stale/one-sided books remain gaps. Keep selection fixed within an experiment.

## Record and pair actual daily outcomes

1. After the target day, find the exact NWS Climatological Report (Daily) for the contract's station/date. Read its full text. Check the observed MAXIMUM row and correction status, not a record maximum, forecast, or nearby station.
2. Copy the product's `https://api.weather.gov/products/...` URL.
3. Replace every placeholder below with the reviewed values:

```powershell
python -m weatherlab record-outcome --url "https://api.weather.gov/products/REAL_PRODUCT_ID" --station KLAX --date YYYY-MM-DD --high ACTUAL_INTEGER_F --review-note "Checked station, date, observed MAXIMUM and corrections" --out data/research/outcome-001.jsonl
```

The command archives the CLI text, hash and real download time. It verifies product type; your review supplies the station/date/high label. It cannot prove that a human label is correct.

4. Join to the previously captured forecast:

```powershell
python -m weatherlab pair-history --archive data/research/day-001/forecast-archive.json --outcomes data/research/outcome-001.jsonl --out data/research/history-001.jsonl
python -m weatherlab doctor
```

This indexes the pair, preserves original forecast receipt time, and sets availability no earlier than review/ingestion now. It never backdates a downloaded archive into an old replay. One latest eligible revision per station-day is retrieved; multiple bins do not increase sample size. Use new files for later outcomes. Collect ten eligible days per station to satisfy the software gate, then determine the larger study sample independently.

Use [DATA-AND-RAG.md](DATA-AND-RAG.md) for importing an existing reviewed corpus. Keep the historical MOS benchmark separate: its forecast product and availability assumptions differ from this prospective NWS hourly-grid workflow.

## Reconcile completed paper positions

After a public session has fully stopped and its contracts have resolved:

```powershell
python -m weatherlab reconcile --run data/sessions/SESSION_ID/fixed_llm --out data/research/reconcile-fixed-001
```

Repeat for wallet_control, adaptive_llm and polyswarm, using separate output directories. The command verifies the original journal/checkpoint, retrieves open-position metadata and book settlement fields, and requires matching market ID, unchanged rules, resolved/closed status, binary USD payout, and a valid settlement timestamp.

It writes a separate `reconciliation.json` and receipts. It never modifies the original run, makes new entries, resumes inference, or submits orders. Unresolved and nonbinary/void payouts remain flagged. Cash and realized paper P&L are updated in the report; total-period overhead and forecast scores are not recomputed. Review corrections through a new report.

The dedicated settlement endpoint returned an HTTP error in this environment. The adapter instead cross-checks documented book `settlementPx`, observed `settlementSetTime`, and resolved metadata. This path was verified against one archived resolved contract. CLI temperature labels and venue payouts remain distinct evidence.

## Limits

No intraday observed-high adapter is implemented. The next-day workflow avoids missing earlier forecast hours; it does not establish that hourly observations equal the CLI maximum. Bounded snapshots do not recover intervening depth or real fills.

Sources: [NWS API](https://www.weather.gov/documentation/services-web-api), [Polymarket US market data](https://docs.polymarket.us/api-reference/market/overview), [market identity endpoint](https://docs.polymarket.us/api-reference/markets/get-market-by-slug).
