# Automatic Apple Weather feed without Developer membership

The dashboard now defaults to **Apple Shortcuts exports**, replacing its WeatherKit credential requirement. Apple's Shortcuts app supplies **Get Weather Forecast**. Your phone retrieves the data, writes a small JSON file to iCloud Drive, and this PC reads the synced file during each tracker snapshot. No typing or copying temperatures is involved after setup.

This is not a remote reader of the Weather app's screen. It uses Apple's weather action on your iPhone. Exact location, day boundaries, caching and background execution must be checked on your device. The application labels these as device-reported forecasts, not authenticated WeatherKit receipts.

**Current verification:** PC ingestion, freshness checks, matching, persistence and UI are tested. The Shortcut has not been created or run on your iPhone, and iCloud delivery has not been verified. There is no installed Shortcut or fabricated iCloud sharing link in this package.

## 1. Connect iCloud Drive on Windows

1. Install **iCloud for Windows** from the Microsoft Store using [Apple's setup instructions](https://support.apple.com/guide/icloud-windows/set-up-icloud-drive-icw0144825a5/icloud).
2. Sign in to the same Apple Account used on your iPhone. Complete two-factor authentication yourself.
3. Turn on **iCloud Drive**. You do not need to enable Photos, Passwords or other services for this feed.
4. In File Explorer, open iCloud Drive and create `Shortcuts\WeatherLab` if it does not exist. On your iPhone, confirm that folder appears in **Files → iCloud Drive → Shortcuts → WeatherLab**.
5. Keep that folder downloaded on Windows using its **Always keep on this device** option if available. Sync must remain enabled.
6. Copy the folder's full Windows path. It is commonly `C:\Users\gamev\iCloud Drive\Shortcuts\WeatherLab`, but use the actual path shown on your PC.
7. Open the dashboard at `http://127.0.0.1:8767/`. Under **Apple Weather / NWS**, paste the path in **Synced forecast folder** and click **Connect forecast folder**. The directory must already exist. This requires no server restart.

## 2. Build the iPhone Shortcut once

Use the built-in **Shortcuts** app. Action names/options may vary by iOS version. This recipe is for the KLAX experiment; use the station's actual forecast location, not Current Location.

1. Create a shortcut named **Weather Lab — KLAX**.
2. Add **Get Weather Forecast**. Choose **Daily**, and set a fixed location of **Los Angeles International Airport**. Keep the resulting Weather Conditions list.
3. Add **Current Date**, then **Format Date** using **ISO 8601** (include the timezone offset). Set Variable `FetchedAt` to this formatted result. Place this after the weather request so it represents completion of the retrieval, not shortcut start.
4. Add **Repeat with Each** over the Weather Conditions list. Within the repeat:
   - Use **Get Details of Weather Conditions → Date** on **Repeat Item**.
   - Format that date as **ISO 8601** into variable `ForecastTime`.
   - Format the same date using custom format `yyyy-MM-dd` into variable `ForecastDate`. Use the same timezone for both formats; do not format one in UTC and the other in local time.
   - Use **Get Details of Weather Conditions → High** on **Repeat Item**. Depending on iOS, the field may be named **High Temperature**. Do not select Temperature, Feels Like or Low.
   - Use **Convert Measurement** to Fahrenheit, then **Get Numbers from Input** and **Get Item from List → First Item**. This must produce one number, without a degree sign or unit suffix. Verify negative values retain their sign when applicable.
   - Create a **Dictionary** with `date` (Text = ForecastDate), `forecast_time` (Text = ForecastTime), and `high` (Number = converted high).
   - **Add to Variable** named `ForecastRows`. Each repeat adds one dictionary.
5. After the repeat, create a Dictionary with these fields:

   | Key | Type | Value |
   | --- | --- | --- |
   | `schema_version` | Number | `1` |
   | `source` | Text | `apple_shortcuts` |
   | `station` | Text | `KLAX` |
   | `location` | Text | `Los Angeles International Airport` |
   | `period` | Text | `daily` |
   | `unit` | Text | `F` |
   | `fetched_at` | Text | FetchedAt variable |
   | `forecasts` | Array | ForecastRows variable (dictionaries, not a quoted JSON string) |

6. Convert that Dictionary to JSON text with **Get Text from Input**. Use **Quick Look** on the first run to confirm the output is a JSON object, not a description of the dictionary or a quoted string. Remove Quick Look once verified, so later automation needs no screen interaction.
7. Use **Set Name** to name the text `KLAX.json`, then **Save File** in **iCloud Drive → Shortcuts → WeatherLab**. Turn **Ask Where to Save** off and **Overwrite If File Exists** on. Always overwrite that one station file.
8. Run the shortcut once and allow its weather/location and folder permissions. Confirm the high matches the daily forecast for the fixed airport location. Check the same `KLAX.json` appears on Windows.

The file should have this structure; the illustrative numbers and dates below are **not live data** and must be generated by the actions above:

```json
{
  "schema_version": 1,
  "source": "apple_shortcuts",
  "station": "KLAX",
  "location": "Los Angeles International Airport",
  "period": "daily",
  "unit": "F",
  "fetched_at": "2026-09-16T09:00:00-07:00",
  "forecasts": [
    {"date": "2026-09-17", "forecast_time": "2026-09-17T00:00:00-07:00", "high": 77}
  ]
}
```

If the target date is wrong because your phone formats a different timezone from the forecast location, fix the shortcut's date formatting before using the comparison. Do not relabel a different day's forecast. The research panel keeps station/civil-day alignment explicitly unverified; it is not admitted as a verified CLI historical pair.

## 3. Make retrieval automatic

1. In **Shortcuts → Automation**, add a **Time of Day** automation.
2. Choose a time during your experiment, repeat Daily, select **Run Immediately** (or disable **Ask Before Running**, depending on iOS), and run **Weather Lab — KLAX**.
3. Add additional scheduled times for the collection window. Exports must arrive less than 30 minutes old to remain eligible; schedule comfortably inside that window, for example at 20-minute intervals during a short experiment.
4. Test while the phone is locked, then verify that the file's `fetched_at` value advances and that Windows receives it. Permission prompts, battery state, network loss or iCloud delays can interrupt automation. A repeating Wait loop is not a reliable background scheduler.
5. In the dashboard, choose KLAX and a contract date included in the export. Start with **One snapshot**. Confirm **Apple daily high** is populated and read **Source coverage and audit**. Then choose a bounded tracker period.

The PC samples every five minutes. It reads the most recently synced forecast; it cannot force the iPhone to run a shortcut. If the file stops updating, the Apple feed expires and the tracker reports that gap. This is scheduled sampling, not a guaranteed real-time stream. No paid developer membership is needed for this approach; ordinary iCloud account/storage availability and the phone remain prerequisites.

## More stations

Duplicate the shortcut, change its fixed weather location, `station` and filename together:

| Station | Required location | Filename |
| --- | --- | --- |
| KLAX | Los Angeles International Airport | `KLAX.json` |
| KSFO | San Francisco International Airport | `KSFO.json` |
| KNYC | Central Park weather station, New York | `KNYC.json` |
| KMIA | Miami International Airport | `KMIA.json` |
| KMDW | Chicago Midway Airport | `KMDW.json` |

If Shortcuts cannot identify the exact station location, retain the mismatch as a research limitation. A city label alone is not verification of a station coordinate.

## Data handling

- Only five allowlisted station filenames are read, from the configured local folder. No local network listener or public dashboard exposure is added.
- Each file is limited to 64 KB and 14 daily forecasts. Malformed, partial, future-dated, stale, duplicate-date, missing-date, mismatched-station and invalid-unit exports are rejected.
- The PC records first receipt time and the original payload hash in `data/disagreement/shortcuts/receipts.sqlite`. Reading the same file again does not refresh its receipt or expiration time. File modification timestamps are not used as historical availability.
- Forecast retrieval time comes from the phone and is not an authenticated provider publication timestamp. Cached data may still exist upstream. Exact app-screen equality is not established.
- Existing WeatherKit credentials and older experiment archives remain untouched. The optional direct API is still available with `python -m weatherlab.disagreement snapshot --apple-mode weatherkit ...`.
- Final NWS CLI outcomes remain in the separate [post-day scoring workflow](APPLE-NWS-STUDY.md#compare-forecasts-with-the-final-nws-high-afterwards). They never enter the prospective feed.

Sources: [Apple's Shortcuts app and Weather actions](https://apps.apple.com/us/app/shortcuts/id915249334), [Apple's automation guide](https://support.apple.com/guide/shortcuts/welcome/ios), [iCloud Drive on Windows](https://support.apple.com/guide/icloud-windows/set-up-icloud-drive-icw0144825a5/icloud).
