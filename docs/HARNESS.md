# Harness contract

The model proposes probabilities and abstentions. Shared code owns eligibility, sizing, ledger updates and completion checks. Source text and model explanations have no authority to alter policy.

## Boundaries and evidence

| Layer | Contract | Deterministic evidence |
| --- | --- | --- |
| Package | Known paper strategy, fixed accounting, compatible runtime; no secrets | Full member hashes, trusted-runtime source comparison, ZIP path/size/symlink checks |
| Retrieval | Correct station/date/source; only available evidence; immutable revisions | SQLite revision IDs, time predicates, rank audit, context hash |
| Public inputs | Allowlisted HTTPS GET hosts, bounded requests/time/bytes; no exchange key | Raw receipt payload, source URL, request/receipt timestamps, SHA256 |
| Inference | Fixed endpoint, bounded prompt/output/time, explicit local budget, strict response shape | Response ID, model, effort, tokens, estimated cost, latency, cited IDs |
| Risk | $50 initial, $40 reserve, $5 position/station-day cap, no shorting | Account transitions, rejected decisions and fill gates |
| Execution model | Future observed depth, expiration, no gap replay, no invented final fills | Decision time, readiness time, later book and paper fill record |
| Accounting | Owned positions only, idempotent matching final settlement, unknown marks remain unknown | Cash/cost/realized reconciliation and final checkpoint |
| Completion | Testable checks pass; model's claim of success has no effect | `acceptance.json`, journal hash chain and artifact hashes |

## Run artifacts

- `manifest.json`: frozen configuration, code hash, dataset hash, model mode and fill assumptions.
- `journal.sqlite`: ordered events, previous-event hash and current-event hash. Chain verification detects inconsistent modification; this is not a cryptographic signature against an attacker who can rewrite every file.
- `checkpoint.json`: durable account, seen signals, pending intents while running, and last decision times. Final pending intents are cancelled.
- `model-calls.json`: successfully validated inference traces; no API keys. Failed/uncertain call cost reservation is retained in the shared `model-budget.sqlite`.
- `summary.json`: actual run status, accounting, scoring, source/model skips, next job and limits.
- `acceptance.json`: independently recomputed ledger/hash-chain checks and evidence classification.

`python -m weatherlab.harness RUN_DIRECTORY` verifies the artifact. An interrupted process can leave a checkpoint/journal without a final summary; treat it as interrupted, never completed. This version deliberately does not automatically resume uncertain external calls or reuse old entry opportunities. Inspection and a newly frozen run are explicit steps.

## Failure handling

Failures are classified as configuration, temporal validation, evidence gap, execution guard, model validation or unclassified. The next-job text targets the failure class. A stale source is refreshed by later data, not repaired by rewording a prompt. Bad mapping requires evidence review. A model schema failure leaves an audit entry and no trade. Uncertain billing retains a cost reservation and is not automatically retried.

Runtime model policy cannot authorize live exchange actions: there is no live trading implementation in this package. Local configuration can enable paid inference, but its default is off with zero budget. Dashboard mutations require a local-session token and loopback Host/Origin checks; uploads never execute their own code. This server is intended for one trusted local user, not public Internet exposure. A remote dashboard needs authentication, tenant isolation, resource quotas and deployment hardening as a separately reviewed change.

## Verification rubric

Reject the run on wrong venue/identity, future data, changed contract rules, invalid numerical output, missing citations, reserve violation, cash reconciliation error, ambiguous settlement or broken journal chain. Reject performance claims based on fixtures, unresolved missing marks, incomplete coverage, retrospective data called prospective, or an unvalidated cloud connection.

Tests exercise both successful flows and adversarial failures. Browser validation exercises upload, replay, visible audit state, errors, settings, evidence input and responsive layout. These are software acceptance checks. They do not replace provider validation, meteorological target review or statistical evidence from a real experiment.
