# Delivery verification — 2026-09-15

## Verified

- 45 unit/integration tests passed with Python 3.10.11. They cover accounting, reserve and event caps, delayed fills, changed contract rules, stale/crossed quotes, duplicate depth, source chronology, immutable retrieval, invalid model responses, disabled/zero budgets, mocked provider usage, failed-call reservations, ZIP traversal, journal tampering, risk profiles and background start/stop.
- All four standalone bot ZIPs were extracted separately and their demo commands completed with accepted ledger/journal receipts. These were fixture runs, not cloud calls. `package-verification/latest.json` outside the distributable contains the smoke-test evidence.
- Browser interaction verified ZIP upload, replay, risk selection and persistence, unchanged prior results, four background workers, graceful stopping, and public-session operation. No browser console warnings or errors were observed in the final pass.
- A real public session discovered 60 supported US contracts and selected four using its fixed bounded rule. All four workers processed more than 29 newly captured frames. Quotes/forecast gaps were reported; no cloud calls or paper entries were falsely reported as successful.
- Desktop verification used 1504 x 1045; mobile used 390 x 844. Mobile page width was 375 CSS pixels (the viewport minus its scrollbar), with no page-level horizontal overflow. All strategies become stacked cards and retain their risk buttons.

## Visual review

The final design follows the user's NERV-terminal request. The previous light concept was superseded. The generated NERV concept and final desktop/mobile renders were opened and visually compared.

| Comparison | Evidence and resolution |
|---|---|
| Copy | Removed the original slogan. Main heading is WEATHER / CONTROL. Kept operational labels and real data only; excluded the concept's fictional location, date and system metadata. |
| Layout | Preserved numbered left rails, horizontal budget strip, operations band, four-row strategy array and paired event/configuration panels. All four rows fit in the desktop working area. |
| Typography | Condensed uppercase system headings; monospace values and controls. Installed fonts only; no font download or new dependency. |
| Palette | Near-black panels, amber text, red-orange dividers, lime active-state labels. No white cards or rounded pills. |
| Controls | Rectangular buttons; amber-filled selected risk preset. Clicked Reliable and restored Balanced; active session config stayed frozen. |
| Mobile | 390 x 844 viewport, 375-pixel document width. Four stacked strategy cards; all nine risk buttons present. No page overflow. |
| Assets/motion | No flashing effects. CSS structural motifs; the reference image is not substituted for interactive UI. |

Final visual evidence: docs/nerv-concept.png, docs/nerv-desktop.png, docs/nerv-mobile.png. PNGs remain in the source workspace and are excluded from compact ZIPs.

## Limits that remain

Real API access and paid inference were not exercised. The real station-history corpus, public reference wallet, exact reference-to-US mapping and current provider tariffs must be configured by the researcher. Intraday complete-day forecasting and automatic final venue settlement collection are not implemented. The current public source sample had incomplete same-day forecasts and one-sided books, so the correct outcome was to abstain.

Software tests and synthetic profitability do not establish forecast skill or executable returns. Follow `RESEARCH-DESIGN.md` before drawing scientific conclusions. The old local Python/OpenSSL installation is a separately reported dependency-maintenance issue; this delivery did not upgrade or install system packages.

## Reproduce

Run `python -m unittest discover -s tests -v`, then `python build_packages.py`. Extract each bot ZIP into its own fresh folder and run `python -m weatherlab demo`. Start the dashboard with `python -m weatherlab serve --port 8766`, upload all four packages, and use **Start sample**. Confirm four active workers and increasing frame counts, then stop and inspect the per-worker acceptance receipts under `data/sessions`. Public mode requires the documented evidence and model setup to make model-driven entries.
