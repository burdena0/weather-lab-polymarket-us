# Running all four strategies





Upload the four ZIPs to the new dashboard. Choose a duration, then click **Start sample** or **Start public**. The session runs in the local Python server even if you close the browser tab; your computer and the server must remain running. Closing the server interrupts the session. No system service or schedule is installed, and sessions do not automatically resume after a restart.





## Sample mode





All four strategy workers process a shared stream of accelerated synthetic fixtures. It uses deterministic test models, not paid LLM inference. A synthetic day is shown every 18 seconds; fixture outcomes alternate to exercise wins and losses. Each account persists throughout the session, including across synthetic days. Subscription overhead follows simulated elapsed time, not the animation's wall-clock duration. None of these returns demonstrates an edge.





A Reliable setting may abstain throughout the fixture: its minimum model confidence is 0.70, while the test model reports 0.60. An active worker that declines to trade is still processing observations; inspect its decision reason.





## Public data mode





This launches prospective public book collection and four independent paper accounts. Each strategy receives a copy of newly observed data. Separate worker threads let model calls proceed independently. Within PolySwarm, persona calls remain sequential. At most the latest pending frame is queued for each worker; lagged observations are dropped and counted rather than traded late. Decisions use the actual processing time, and old quotes fail freshness checks. Each arm writes its own exact processed inputs; differing input-stream hashes cannot be claimed to be identical paired replays.





The collector refreshes its bounded inventory selection between windows. All source receipts remain under the new session folder. Three successive empty capture windows stop the session with a visible failure. A Stop request prevents further frames; an in-flight bounded HTTP/model request can finish before the workers finalize. Pending entries are cancelled, and existing paper positions remain in the final account report. Stopping does not pretend to liquidate them.





Public mode requires the real corpus and cloud setup from the other guides. Missing cloud access, forecast coverage, station history or a reviewed wallet mapping produces explicit skips. This release has no automatic final US settlement collector and no observed-high-plus-remaining-hours intraday forecast adapter. Unresolved paper inventory remains unresolved. Do not label missing configuration as successful cloud inference or treat public sessions as publication-ready results without these data checks.





## Evidence and control





Each worker preserves its frozen config, independent account, input JSONL, journal, checkpoints and final acceptance receipt. The dashboard shows worker liveness, processed-frame count, last-update age and latest decision reason. The session's final-state.json contains all four final results and capture notices. Session errors are distinct from normal no-trade decisions.





Risk selections apply to the next session. The old SupahTrade schedule and halted supervisors are untouched. Sessions last up to four hours, with one hour selected by default; start another explicitly when required. The shared API ledger still limits cumulative daily spend.





## Runtime audit boundary





The delivery was tested on local Python 3.10.11, whose installed libraries reported OpenSSL 1.1.1t and SQLite 3.40.1. This is an old runtime. No interpreter or system package was installed or upgraded. Use a maintained, separately reviewed Python installation for cloud research, and record its exact version. The Python paper core uses standard-library modules only; optional account linking also uses an existing Node.js runtime and its built-in crypto module; zero pip dependencies does not remove trust in the interpreter and bundled native libraries. ZIP hashes and journal chains establish consistency, not author identity or an operating-system sandbox.


