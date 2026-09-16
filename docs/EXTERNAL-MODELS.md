# Connect a private forecast model

The local JSONL interface accepts binary-contract probabilities from an existing model. It does not require model code, proprietary features, or weights. No reinforcement model was supplied or trained here; nitrogen-related predictive skill is unverified. The dashboard reports **waiting for predictions** until actual outputs are imported.

## Steps for the model owner

1. Have the model export one JSON object per exact contract to a local `.jsonl` file, using the fields below. Generate a probability of the contract settling YES, not a price, action, temperature, or claimed return.
2. Use the exact Polymarket US market ID, rules SHA-256, NWS CLI station, target date and inclusive integer Fahrenheit bounds from the market record. `null` is allowed for one open-ended bound.
3. Identify the model by a stable name and SHA-256 of its frozen artifact. Export honest UTC timestamps for training cutoff, model freeze, latest available input, generation and expiry. Predictions expire within 24 hours. Changing the trained artifact requires a new hash.
4. Import the file locally:

   ```powershell
   python -m weatherlab import-predictions --jsonl C:\path\to\predictions.jsonl
   ```

5. Import the updated forecasting ZIPs. Their manifests enable optional `external_predictions` retrieval; the deterministic control excludes it. No predictions means no extra model input. The same setting can be disabled in a new configuration for an ablation. Existing runs are immutable.
6. Collect predictions prospectively, record settlements, and compare new isolated runs with and without this input. Historical files imported now cannot participate in past decisions. No historical-availability override is provided.

Use a temporary file followed by an atomic rename when exporting. Files are read once per import, not watched. This interface performs no model training, API inference, arbitrary code execution, or live orders. It uses the existing local evidence database; experiment journals stay isolated in new output directories.

## Exact schema

```json
{
  "schema_version": 1,
  "model_id": "private_rl",
  "model_version_sha256": "SHA256_OF_ACTUAL_MODEL_ARTIFACT",
  "training_end": "UTC_TIMESTAMP",
  "model_frozen_at": "UTC_TIMESTAMP",
  "input_available_through": "UTC_TIMESTAMP",
  "generated_at": "UTC_TIMESTAMP",
  "expires_at": "UTC_TIMESTAMP",
  "venue": "polymarket_us",
  "station": "KNYC",
  "date": "TARGET_LOCAL_DATE",
  "source": "NWS_CLI",
  "market_id": "EXACT_US_MARKET_ID",
  "rules_hash": "SHA256_OF_EXACT_RULES",
  "lower_f": 75,
  "upper_f": 77,
  "probability_yes": 0.6,
  "synthetic": false
}
```

This is a schema illustration, not an observed prediction. All fields are required; extra fields, nonfinite values and invalid timestamps are rejected. Export no confidential feature descriptions or secrets. Private files and the evidence database are excluded from Git and ZIPs.

## Validation and limits

The importer records the current local receipt time; the caller cannot set it through the file. Training/input timestamps are **user declarations**, not independently audited facts. Files are bounded to 2 MB, 1,000 rows and 4 KB per prediction. A batch is atomic. Identical reimports retain the first receipt. Generic evidence upload cannot introduce private predictions with fabricated receipt times.

Retrieval is opt-in, requires exact contract identity and as-of availability, and returns at most three models. The latest generated prediction for a model supersedes older outputs even when the replacement expires. Conflicting predictions for the same model and generation time cause abstention for that model. More than 200 matching revisions blocks retrieval until the archive is narrowed. Synthetic predictions are excluded from real-data retrieval.

Predictions enter bounded evidence context for the three LLM arms. They cannot bypass history minimums, freshness, source rules, uncertainty checks, budgets or deterministic execution. Context includes an explicit warning that probabilities, independence and calibration are unverified. Importing predictions is not proof that their features are useful. The current historical return reports use none of these private predictions.

The expanded package now allows up to 128 members (previously 100); the existing 8 MB compressed, 16 MB expanded, 2 MB/member limits and runtime hash checks remain in force.
