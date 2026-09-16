"""Append-only replay results, delayed fills and matched forecast scoring."""
import copy
import json
import math
import sqlite3
import time
from collections import deque
from pathlib import Path
from .core import Account, digest, number, stamp
from .models import FixtureModel, CloudModel
from .strategies import Strategy, STRATEGIES, RISK_PROFILES
from .harness import code_hash, classify, verify_run
from .protocol import check_version, LATEST_VERSION


def validate_config(c):
    check_version(c.get('research_protocol'))
    if 'weather_hypotheses' in c or c.get('research_protocol') == LATEST_VERSION:
        from .hypotheses import selected
        selected(c)
        if c.get('research_protocol') != LATEST_VERSION:
            raise ValueError('Weather hypothesis switches require the v2 research protocol')
    if c.get("risk_profile", "balanced") not in RISK_PROFILES:
        raise ValueError("Risk profile must be reliable, balanced or risky")
    if c.get("strategy") not in STRATEGIES or c.get("venue") != "polymarket_us" or c.get("mode") != "paper":
        raise ValueError("Unsupported paper strategy/venue")
    if c.get("initial_capital") != 50 or c.get("reserve") != 40 or c.get("monthly_subscription") != 200:
        raise ValueError("Fixed experiment accounting must remain 50 / 40 / 200")
    if c.get("control_mode", "copy") not in ("copy", "arbitrage"):
        raise ValueError("Select copy OR arbitrage as a separate run")
    if type(c.get("swarm_count", 5)) is not int or not 3 <= c.get("swarm_count", 5) <= 50:
        raise ValueError("Swarm count must be 3-50")
    return c


def replay(config, dataset, output, cloud=False, rag=None, budget_path=None, frame_stream=None, on_update=None, duration=240, stop_event=None):
    validate_config(config)
    if type(dataset.get("synthetic")) is not bool:
        raise ValueError("Dataset must explicitly declare synthetic true or false")
    if dataset.get("schema_version") != 1 or dataset.get("venue") != "polymarket_us":
        raise ValueError("Invalid dataset schema or venue")
    frames = dataset["frames"]
    if frame_stream is None and not 1 <= len(frames) <= 20000:
        raise ValueError("Require 1-20000 ordered frames")
    times = [number(f["at"]) for f in frames]
    if any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError("Frames must be strictly chronological")
    if cloud and dataset.get("synthetic"):
        raise ValueError("Cloud billing is disabled for synthetic datasets")
    root = Path(output)
    root.mkdir(parents=True, exist_ok=False)
    metadata = {"config": config, "config_hash": digest(config), "dataset_hash": digest(dataset), "synthetic": bool(dataset.get("synthetic")),
                "inference": "cloud" if cloud else "fixture_not_llm", "created_at": time.time(), "execution": "paper_only",
                "fill_model": "delayed observed-depth taker stress; baskets are ideal all-legs-fill scenarios", "code_version": "1.0.0", "code_hash": code_hash()}
    (root/"manifest.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    db = sqlite3.connect(root/"journal.sqlite")
    db.execute("CREATE TABLE events (seq INTEGER PRIMARY KEY, at REAL, kind TEXT, payload TEXT, prev_hash TEXT, event_hash TEXT)")
    tip, sequence = '0'*64, 0
    def record(at, kind, payload):
        nonlocal tip, sequence
        at = number(at)
        sequence += 1
        hashed = digest({'seq':sequence,'at':at,'kind':kind,'payload':payload,'previous':tip})
        db.execute("INSERT INTO events VALUES(?,?,?,?,?,?)", (sequence,at,kind,json.dumps(payload,allow_nan=False),tip,hashed))
        db.commit()
        tip = hashed
    model = CloudModel(budget_path or root.parent/"model-budget.sqlite") if cloud else FixtureModel()
    model.cancel_event = stop_event
    account = Account()
    started = times[0] if times else dataset['started_at']
    strategy = Strategy(config, model, started)
    pending, forecasts, journal = [], {}, deque(maxlen=200)
    scored = []
    last_markets = {}
    residual_depth = {}
    depth_times = {}
    status, error = "completed", None
    wall_start = time.monotonic()
    model.deadline = wall_start+duration
    now, previous_at, input_hash, index = started, None, '0'*64, -1
    def snapshot(phase):
        return {**metadata, 'status':phase, 'error':error, 'strategy':config['strategy'],
                **account.summary(last_markets, now, max(0, now-started)),
                'mean_brier':sum(s['brier'] for s in scored)/len(scored) if scored else None,
                'independent_station_days':len({s['station_day'] for s in scored}),
                'journal':copy.deepcopy(list(journal)), 'validated_model_calls':len(model.calls),
                'cloud_connection_validated':cloud and bool(model.calls), 'last_frame_at':now,
                'heartbeat_at':time.time(), 'frames_processed':index+1,
                'pending_count':len(pending), 'profitability_established':False}
    try:
        for index, source_frame in enumerate(frame_stream if frame_stream is not None else frames):
            if time.monotonic()-wall_start > duration:
                raise ValueError("Run time budget reached; split replay into a predeclared shorter experiment")
            f = copy.deepcopy(source_frame)
            now = number(f["at"])
            if previous_at is not None and now <= previous_at:
                raise ValueError('Stream frames must be strictly chronological')
            if frame_stream is not None:
                input_hash = digest({'previous':input_hash,'frame':f})
                with (root/'inputs.jsonl').open('a',encoding='utf-8') as stream_file:
                    stream_file.write(json.dumps(f,allow_nan=False)+'\n')
            rows = f.get("markets", [])
            if len(rows) > 100 or len({m["slug"] for m in rows}) != len(rows):
                raise ValueError("Duplicate or oversized market frame")
            markets = {m["slug"]: m for m in rows}
            # Quotes older than 120 seconds cannot execute; release their consumed-depth cache.
            for key in list(depth_times):
                if now-depth_times[key]>120:
                    depth_times.pop(key);residual_depth.pop(key,None)
            for m in markets.values():
                b = m["book"]
                key = digest([m["slug"], b["source_at"], b["bids"], b["asks"]])
                m["depth_key"] = key
                if key in residual_depth:
                    b["bids"], b["asks"] = copy.deepcopy(residual_depth[key])
            last_markets = markets
            if rag:
                for m in markets.values():
                    if m.get("forecast"):
                        retrieved = rag.retrieve(m, now, allow_synthetic=bool(dataset.get("synthetic")),
                                                 include_recent=config.get('research_protocol') == LATEST_VERSION and config['strategy'] != 'wallet_control')
                        m["history"] = retrieved["history"]
                        m["retrieved_documents"] = retrieved["documents"]
                        record(now, "retrieval", {"slug": m["slug"], **retrieved["audit"]})
            if previous_at is not None and now-previous_at > 300:
                for intent in pending:
                    record(now, "cancel", {"reason": "Observation gap > five minutes", "intent": intent})
                pending = []
            for s in f.get("settlements", []):
                pred = forecasts.get(s["slug"])
                if pred and (pred["market_id"] != s["market_id"] or pred["rules_hash"] != s["rules_hash"]):
                    raise ValueError("Forecast/settlement identity mismatch")
                account.settle(s, now)
                record(now, "settlement", s)
                if s["slug"] in forecasts:
                    prediction = forecasts.pop(s["slug"])
                    y, p = s["yes_payout"], prediction["probability_yes"]
                    clipped = min(1-1e-9, max(1e-9, p))
                    scored.append({"slug": s["slug"], "station_day": prediction["station_day"], "y": y,
                                   "p": p, "brier": (p-y)**2, "log_loss": -y*math.log(clipped)-(1-y)*math.log(1-clipped),
                                   "market_brier": (prediction["market_mid"]-y)**2,
                                   "statistical_baseline_brier": (prediction["baseline_probability"]-y)**2})
            retained = []
            for intent in pending:
                if now > intent["expires_at"] or any(l["slug"] in account.resolved for l in intent["legs"]):
                    record(now, "cancel", {"reason": "Intent expired or market resolved", "intent": intent})
                elif now >= intent["ready_at"]:
                    try:
                        detail = account.fill(intent["legs"], markets, now, minimum_payout=intent.get("minimum_payout"), event_cap=intent.get("risk_event_cap", 5))
                        record(now, "fill", {"legs": detail, "paper": True})
                        journal.append({"at": now, "kind": "fill", "reason": intent["reason"], "legs": detail})
                    except (ValueError, KeyError) as exc:
                        record(now, "reject_fill", {"reason": str(exc), "intent": intent})
                        journal.append({"at": now, "kind": "reject_fill", "reason": str(exc)})
                else:
                    retained.append(intent)
            pending = retained
            for decision in strategy.decide(markets, f.get("signals", []), account, now):
                kind = "skip" if "skip" in decision else "decision"
                record(now, kind, decision)
                journal.append({"at": now, "kind": kind, "reason": decision.get("skip", decision.get("reason")), "audit": decision.get("audit")})
                audit = decision.get("audit")
                if audit and audit["slug"] not in forecasts and audit["slug"] not in account.resolved:
                    m = markets[audit["slug"]]
                    forecasts[audit["slug"]] = {**audit, "station_day": m["station"]+"/"+m["date"]}
                if kind == "decision":
                    pending.append(decision)
            account.model_cost = model.cost
            for m in markets.values():
                if 0 <= now-number(m['book']['source_at']) <= 120:
                    residual_depth[m["depth_key"]] = copy.deepcopy((m["book"]["bids"], m["book"]["asks"]))
                    depth_times[m['depth_key']]=number(m['book']['source_at'])
            record(now, "account", account.__dict__)
            checkpoint = {"phase":"running", "last_frame":index, "account":account.__dict__, "pending":pending,
                          "seen_signals":sorted(strategy.seen), "journal_tip":tip, "last_decision":strategy.last_decision,
                          "resume_policy":"Inspection only; no automatic re-execution of uncertain cloud calls or old entry opportunities."}
            temp = root/'checkpoint.tmp'
            temp.write_text(json.dumps(checkpoint,allow_nan=False),encoding='utf-8');temp.replace(root/'checkpoint.json')
            previous_at = now
            if on_update:
                on_update(snapshot('running'))
    except Exception as exc:
        status, error = "failed", type(exc).__name__+": "+str(exc)[:300]
        record(now, "failure", {"error": error, **classify(error)})
    finally:
        account.model_cost = model.cost
        for intent in pending:
            record(now, "cancel", {"reason": "End of observed dataset; no invented fill", "intent": intent})
        if frame_stream is not None:
            metadata['dataset_hash'] = input_hash
            metadata['streamed_inputs'] = True
            (root/'manifest.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
        summary = {**metadata, "status": status, "error": error, "strategy": config["strategy"],
                   **account.summary(last_markets, now, max(0, now-started)), "forecast_scores": scored,
                   "scored_contracts": len(scored), "independent_station_days": len({s["station_day"] for s in scored}),
                   "mean_brier": sum(s["brier"] for s in scored)/len(scored) if scored else None,
                   "journal": list(journal), "next_job": "Collect prospective common inputs and verified history; run cloud only after explicit local budget configuration.",
                   "profitability_established": False, "journal_tip":tip,
                   "validated_model_calls":len(model.calls), "cloud_connection_validated":cloud and bool(model.calls),
                   "failure_classes":[classify(j['reason']) for j in journal if j['kind'] in ('skip','reject_fill')]}
        (root/'checkpoint.json').write_text(json.dumps({"phase":status,"account":account.__dict__,"pending":[],"journal_tip":tip,
                                                      "seen_signals":sorted(strategy.seen),"last_decision":strategy.last_decision}),encoding='utf-8')
        (root/"summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False), encoding="utf-8")
        (root/"model-calls.json").write_text(json.dumps(model.calls, indent=2), encoding="utf-8")
        db.close()
        receipt = verify_run(root)
        (root/'acceptance.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
        if on_update:
            on_update({**summary,'heartbeat_at':time.time(),'last_frame_at':now,'frames_processed':index+1,'pending_count':0})
    return summary
