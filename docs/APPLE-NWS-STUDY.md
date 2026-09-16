# Apple Weather, NWS and contract depth

## What arbitrage already does

Choose **Configuration → Control mode → Strict basket arbitrage**, save, then start a new paper session. Copy mode follows mapped wallet trades; it is not arbitrage.

The arbitrage control groups contracts for the same station, date and NWS CLI settlement source. Every integer Fahrenheit outcome must belong to exactly one bin, including both tails. It proposes buying one YES share in every bin only when their total stressed cost is at most $0.97. One ordinary, non-void resolution then pays $1 across the basket. Example: three exhaustive bins costing $0.25, $0.35 and $0.30 all-in cost $0.90 and pay $1 collectively.

It checks visible depth, minimum sizes, fresh metadata/books, source timestamps within two seconds, fees, slippage and the $40 reserve. The paper engine waits at least two seconds and checks the next observed books again. Its all-legs-fill assumption is idealized: simultaneous fills and a $1 payout under unusual cancellation/void rules are not guaranteed in a real market. The ordinary public session captures a bounded subset that may omit some bins; an incomplete basket correctly produces no entry.

## What the new tracker measures

The separate **Apple Weather / NWS** panel records:

- Apple's daily high and the temperature bin it maps to.
- The NWS full-day hourly-grid forecast maximum, when complete coverage exists.
- The latest quality-checked NWS station observation, with its observation time. This is a current temperature, **not** the final daily maximum or the venue payout.
- Every supported open contract for the chosen station/date, up to 12, including both tails when listed. Coverage and truncation are explicit.
- YES best bid/ask, total visible ask shares, shares within two cents of the ask, level counts, and a minimum-size quote including the existing fee/slippage stress model.
- The probability needed to break even at that stressed quote. A $0.432 all-in share requires a probability above 43.2% under a $1/zero payout assumption. A temperature point forecast alone does not establish that probability.

The public feed exposes price/quantity levels. **Shares and price levels are not counts of individual orders or executed trades.** Depth is not a forecast probability; visible size can disappear. The raw receipts and comparison times are preserved.

Apple/NWS disagreement is a hypothesis about forecast-driven mispricing. This tracker does not submit paper entries or alter the four existing strategies. No Apple residual calibration, profitable rule, continuous fill coverage or NWS-versus-Apple advantage has been established. This is the data-collection stage needed to test that hypothesis.

## Automatic Apple WeatherKit setup

Apple forecasts are retrieved only through WeatherKit. There is no phone entry, manual upload, or alternate Apple source. The dashboard refuses to start the tracker until credentials are configured. Existing archives remain unchanged.

The connector is implemented and locally tested, but an authenticated Apple response has not been validated for this project. WeatherKit requires your own Apple Developer Program access. No account was opened, membership purchased, or paid service enabled by this change.

1. If you do not have membership, open [Apple Developer enrollment](https://developer.apple.com/programs/enroll/). Sign in with your Apple Account with two-factor authentication, choose individual enrollment if appropriate, and complete Apple's identity, agreement and payment steps yourself. Apple lists **US$99 per year**; WeatherKit includes up to **500,000 calls per month** with membership ([WeatherKit requirements](https://developer.apple.com/weatherkit/)). Wait until membership is active.
   - In [Certificates, Identifiers & Profiles](https://developer.apple.com/account/resources/identifiers/list), create or select your App ID. Enable WeatherKit in both **App Services** and **Capabilities**, then save. [Apple instructions](https://developer.apple.com/help/account/services/weatherkit)
   - Register the Service ID used by the REST API. Choose a unique reverse-domain identifier, such as `com.yourname.weatherlab`, and record the exact value. Follow [Apple's REST authentication instructions](https://developer.apple.com/documentation/weatherkitrestapi/request-authentication-for-weatherkit-rest-api).
   - In **Keys → +**, name the key `Weather Lab`, enable WeatherKit, register it and download the `.p8` file. Record the Key ID. Apple only allows that private-key download once. [Key instructions](https://developer.apple.com/help/account/keys/create-a-private-key)
   - Find your ten-character Team ID in your developer membership details. You now need four values locally: Team ID, Key ID, Service ID and the key file path.
2. Save the downloaded `.p8` private key **outside this repository**. On this computer, the prepared folder is `C:\Users\gamev\.weatherlab\weatherkit\`. Keep the original private; do not paste it into chat or an online JWT tool.
3. Ensure Node.js is installed. The signer uses only Node's built-in cryptography; no npm or pip dependencies are needed.
4. Add the following to your local `.env`, replacing the placeholders. Keep `WEATHERLAB_WEATHERKIT_TOKEN` blank when using automatic signing:

   ```dotenv
   WEATHERLAB_WEATHERKIT_TOKEN=
   WEATHERLAB_WEATHERKIT_TEAM_ID=YOUR_TEAM_ID
   WEATHERLAB_WEATHERKIT_KEY_ID=YOUR_KEY_ID
   WEATHERLAB_WEATHERKIT_SERVICE_ID=your.registered.service.id
   WEATHERLAB_WEATHERKIT_KEY_PATH=C:\private\AuthKey_YOUR_KEY_ID.p8
   ```

5. Restart the dashboard server to read the local settings. Select the station, contract date and **One snapshot**, then **Start tracker**.
6. Verify a returned Apple high and inspect **Source coverage and audit**. Configured credentials alone do not prove access. Authentication, attribution, coordinates, metric units, freshness and exact returned weather-day boundaries must pass. An expired token, unavailable API, or interval mismatch produces a notice and no Apple comparison.
7. Once one authenticated snapshot succeeds, use a bounded tracking period. The server signs a new 20-minute ES256 token locally for each snapshot. An existing developer JWT can alternatively be placed in `WEATHERLAB_WEATHERKIT_TOKEN`; that override is not automatically renewed.

WeatherKit is queried at NWS station coordinates with fixed local standard-time daily rollups, then checked against the actual venue interval. This aligns the research target with CLI-style days but may differ from the daily high displayed for a city on an iPhone. The API forecast must not be represented as a byte-for-byte observation of that app screen. Apple attribution is displayed when the API responds successfully.

## Compare forecasts with the final NWS high afterwards

Keep this separate from live collection so the final label cannot enter a prospective decision.

1. After the target day, locate its exact NWS **CLI** product. Check station, date and the daily **MAXIMUM** row, including any corrections. An instantaneous observation is not sufficient.
2. Archive that reviewed product with the existing command (replace every placeholder):

   ```powershell
   python -m weatherlab record-outcome --url "https://api.weather.gov/products/PRODUCT-ID" --station KLAX --date YYYY-MM-DD --high INTEGER_F --review-note "Verified station, date, MAXIMUM and corrections" --out data/cli-reviewed.jsonl
   ```

3. Find a pre-close `snapshot.json` path under **Source coverage and audit**, or under `data/disagreement/RUN/SEQUENCE/`.
4. Score it into a **new** result file:

   ```powershell
   python -m weatherlab.disagreement score --snapshot data/disagreement/RUN/0001/snapshot.json --outcome data/cli-reviewed.jsonl --out data/cli-score-new.json
   ```

This reports signed Apple and NWS errors in Fahrenheit. It verifies station/date, review metadata, product text hash and chronology, and preserves hashes of both inputs. It never modifies the snapshot, simulates a historical trade, or substitutes CLI weather verification for the venue's actual settlement receipt. Review of the CLI labels remains a human responsibility.

## Research controls and limits

- Snapshots are prospective. They contain actual download times; there is no historical Apple reconstruction or backdating. Outcomes are read only by the separate scoring command.
- Continuous forecast values map to integer bins using `floor(F + 0.5)`, an explicit research convention. Calibration must account for display rounding and source/settlement measurement differences.
- Quote checks reject stale, crossed, insufficient or invalid books. Depth has separate source and receipt timestamps. Each row is checked on collection, then displayed as an archived snapshot after ten seconds.
- The sampler keeps one result in memory, writes each snapshot and receipt to disk, and caps a run at one hour / 60 snapshots / 12 contracts / 24 public reads per snapshot. Calls are sequential, responses capped at 4 MB and timed out after seven seconds. There is no automatic restart, catch-up loop, or unbounded in-memory history. Disk archives accumulate across explicit runs.
- Before any trading experiment: collect independent station-days, freeze a training/test split, estimate source-specific forecast residuals, test calibration and costs, and predeclare how disagreement and depth affect entry. Market prices alone must not determine the forecast probability. Missing data and skipped entries are part of the result.
- The original four accounts, immutable experiments, $50 capital, $40 reserve and $200 monthly expense remain separate. No new dependency, LLM call or order endpoint was added.

## Verified in this change

Unit tests cover chronology, expired inputs, station and day mismatch, unit conversion, share/level semantics, quote refusal, missing sources, isolated post-day scoring, bounded sampler behavior, and secret-free status/error output. A real public KLAX / 2026-09-17 snapshot returned six exhaustive contracts, an NWS forecast and a quality-checked observation; stale book rows were rejected. Apple remained missing because WeatherKit credentials had not been provided. That check is not a profit test.

Sources: [Apple daily forecast fields](https://developer.apple.com/documentation/weatherkitrestapi/dayweatherconditions), [Apple request parameters](https://developer.apple.com/documentation/weatherkitrestapi/get-api-v1-weather-_language_-_latitude_-_longitude_), [Polymarket US market book](https://docs.polymarket.us/api-reference/markets/get-market-book), [NWS API](https://www.weather.gov/documentation/services-web-api).
