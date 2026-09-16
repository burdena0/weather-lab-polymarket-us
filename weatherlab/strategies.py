"""Four strategies. Identical risk and fill engine; no direct network authority."""
import math
import statistics
from .core import MAX_POSITION, MAX_EVENT, RESERVE, context, event, identity, levels, quote, complete_partition, number, validate_market
from .models import PERSONAS, validate_prediction
from .protocol import VERSION, LATEST_VERSION, require_available, diagnostics, settlement_window
from .hypotheses import selected

STRATEGIES = {"wallet_control": "Wallet control", "fixed_llm": "Fixed model", "adaptive_llm": "Adaptive model", "polyswarm": "PolySwarm"}
RISK_PROFILES = {
    "reliable": {"edge": .06, "min_confidence": .7, "max_width": .25, "kelly": .1, "event_cap": 2, "bound_weight": 1.0},
    "balanced": {"edge": .03, "min_confidence": .5, "max_width": .4, "kelly": .25, "event_cap": 5, "bound_weight": 1.0},
    "risky": {"edge": .01, "min_confidence": .3, "max_width": .65, "kelly": .5, "event_cap": 5, "bound_weight": .5},
}


def leg(m, side, action, qty, limit):
    return {"slug": m["slug"], "market_id": m["id"], "rules_hash": m["rules_hash"], "side": side, "action": action, "qty": qty, "limit": limit}


def size(m, side, budget, now):
    # Monotone search in hundredths, capped to avoid large low-price notional bets.
    lo, hi, best = max(1, math.ceil(number(m["minimum_qty"])*100)), 500, None
    while lo <= hi:
        mid = (lo+hi)//2
        try:
            cash, _ = quote(m, side, "BUY", mid/100, now)
            if cash <= budget:
                best = (mid/100, cash)
                lo = mid+1
            else:
                hi = mid-1
        except ValueError:
            hi = mid-1
    return best


def remaining_budget(account, m):
    exposure = sum(p["cost"] for p in account.positions.values() if tuple(p["event"]) == event(m))
    return max(0, min(MAX_POSITION, MAX_EVENT-exposure, account.cash-RESERVE))


def route(ctx):
    """Versioned deterministic effort estimator; never trained on the test window."""
    f = ctx["forecast"]
    n = len(ctx["history"])
    residuals = [r["actual_high_f"]-r["forecast_high_f"] for r in ctx["history"]]
    spread = statistics.pstdev(residuals)
    distance = min([abs(f["high_f"]-b) for b in (ctx["contract"]["lower_f"], ctx["contract"]["upper_f"]) if b is not None] or [100])
    score = int(n < 30)+int(spread > 3)+int(distance < 2)+int(abs(f.get("revision_f", 0)) > 2)
    research = ctx.get('research_diagnostics')
    if research:
        # Frozen heuristic thresholds, not fitted performance estimates.
        score += int(research['half_degree_probability_span'] > .15)
        score += int(research['largest_hourly_change_f'] > 3)
        weather = research.get('weather_hypotheses')
        if weather:
            score += int(weather['model_high_spread_f'] > 3 or weather['peak_window_distance_hours'] > 3)
            score += int(weather['regime_change'])
    tier, effort = ("large", "high") if score >= 3 else ("medium", "medium") if score >= 1 else ("small", "low")
    return tier, effort, {"complexity_score": score, "history_days": n, "residual_std_f": spread, "distance_to_boundary_f": distance,
                         "research_protocol": research['version'] if research else None}


def forecast(strategy, ctx, model, market_mid, swarm_count=5):
    if strategy == "fixed_llm":
        p, call = model.predict(ctx, "medium", "medium")
        return validate_prediction(p, ctx), {"route": "fixed", "calls": [call]}, call["latency_seconds"]
    if strategy == "adaptive_llm":
        tier, effort, routing = route(ctx)
        p, call = model.predict(ctx, tier, effort)
        calls = [call]
        # One bounded escalation for uncertainty; uncertainty remaining at largest => abstain.
        if (p["upper"]-p["lower"] > .3 or p["confidence"] < .5) and tier != "large":
            p, call = model.predict(ctx, "large", "high")
            calls.append(call)
            routing["escalated"] = True
        validate_prediction(p, ctx)
        if p["upper"]-p["lower"] > .4:
            p["abstain"] = True
        return p, {"route": routing, "calls": calls}, sum(c["latency_seconds"] for c in calls)
    if strategy != "polyswarm" or not 3 <= swarm_count <= 50:
        raise ValueError("Unsupported strategy or swarm size")
    predictions, calls = [], []
    # Sequential bounded inference is intentional: predictable spend, no subagent runtime.
    for i in range(swarm_count):
        persona = PERSONAS[i % len(PERSONAS)]+" Independent assessment "+str(i+1)
        p, call = model.predict(ctx, "medium", "medium", persona)
        validate_prediction(p, ctx)
        predictions.append(p)
        calls.append(call)
    if any(p["abstain"] for p in predictions):
        aggregate = dict(predictions[0], abstain=True, reason="At least one persona abstained; conservative swarm gate")
    else:
        weights = [max(.1, min(.8, p["confidence"])) for p in predictions]
        consensus = sum(w*p["probability_yes"] for w, p in zip(weights, predictions))/sum(weights)
        combined = .7*consensus+.3*market_mid
        aggregate = {"probability_yes": combined, "lower": min(combined, min(p["lower"] for p in predictions)),
                     "upper": max(combined, max(p["upper"] for p in predictions)), "confidence": sum(weights)/len(weights),
                     "abstain": statistics.pstdev(p["probability_yes"] for p in predictions) > .15,
                     "reason": "Confidence-capped persona consensus with fixed 30% market blend; weights are uncalibrated.",
                     "evidence_ids": sorted(set(e for p in predictions for e in p["evidence_ids"]))}
    return aggregate, {"route": "polyswarm-inspired", "calls": calls, "persona_predictions": predictions,
                       "implementation": "Five weather roles by default, conservative linear market blend; not a paper replication."}, sum(c["latency_seconds"] for c in calls)


class Strategy:
    def __init__(self, config, model, started):
        self.config, self.model, self.started = config, model, started
        self.seen = set()
        self.last_decision = {}

    def decide(self, markets, signals, account, now):
        version = self.config.get('research_protocol')
        enabled = version in (VERSION, LATEST_VERSION)
        if enabled:
            try:
                require_available(now, version)
            except ValueError as exc:
                return [{'skip': str(exc), 'research_protocol': version}]
        result = self._decide(markets, signals, account, now)
        if enabled:
            for decision in result:
                decision['research_protocol'] = version
        return result

    def _decide(self, markets, signals, account, now):
        out = []
        kind = self.config["strategy"]
        profile_name = self.config.get("risk_profile", "balanced")
        profile = RISK_PROFILES[profile_name]
        if kind == "wallet_control":
            if self.config.get("control_mode", "copy") == "arbitrage":
                groups = {}
                for m in markets.values():
                    groups.setdefault(event(m), []).append(m)
                for group in groups.values():
                    key = str(event(group[0]))
                    if key in self.seen or not complete_partition(group):
                        continue
                    try:
                        if self.config.get('research_protocol') in (VERSION, LATEST_VERSION) and len({settlement_window(m) for m in group}) != 1:
                            raise ValueError('Basket contracts have different settlement intervals')
                        if max(m["book"]["source_at"] for m in group)-min(m["book"]["source_at"] for m in group) > 2:
                            raise ValueError("Basket book timestamps are not synchronized")
                        # A complete 1-share YES basket pays exactly $1 on ordinary resolution.
                        legs, cost = [], 0.0
                        for m in group:
                            cash, _ = quote(m, "YES", "BUY", 1, now)
                            cost += cash
                            legs.append(leg(m, "YES", "BUY", 1, cash+.005))
                        if 1-cost >= .03 and cost <= remaining_budget(account, group[0]):
                            out.append({"legs": legs, "ready_at": now+2, "expires_at": now+60, "minimum_payout": 1,
                                        "reason": "Exhaustive disjoint temperature basket below payout after stress costs; ideal all-legs-fill scenario"})
                            self.seen.add(key)
                    except (ValueError, KeyError) as exc:
                        out.append({"skip": str(exc), "slug": group[0]["slug"]})
                return out or [{"skip": "No eligible complete basket with positive net edge"}]
            wallet = self.config.get("reference_wallet", "").lower()
            for s in signals:
                sid = s["id"]
                if sid in self.seen:
                    continue
                self.seen.add(sid)
                try:
                    if not wallet or s["wallet"].lower() != wallet:
                        raise ValueError("Reference wallet not configured or mismatched")
                    if not self.started <= s["trade_at"] <= s["received_at"] <= now or now-s["trade_at"] > 120:
                        raise ValueError("Pre-start/stale/future wallet signal")
                    m = markets[s["slug"]]
                    if self.config.get('research_protocol') in (VERSION, LATEST_VERSION):
                        settlement_window(m)
                    if tuple(s["contract_identity"]) != identity(m) or s.get("mapping_verified") is not True:
                        raise ValueError("No exact verified US settlement mapping")
                    if s.get("us_rules_hash") != m["rules_hash"] or s.get("us_market_id") != m["id"]:
                        raise ValueError("Reference mapping changed")
                    action, side = s["action"], s["side"]
                    if action == "BUY":
                        sized = size(m, side, remaining_budget(account, m), now)
                        if not sized:
                            raise ValueError("No reserve-safe minimum-size entry")
                        qty, cash = sized
                    else:
                        qty = min(5, math.floor(account.available(m["slug"], side)*100)/100)
                        cash, _ = quote(m, side, "SELL", qty, now)
                    ref = number(s["price"])
                    if not 0 < ref < 1:
                        raise ValueError("Invalid reference price")
                    limit = ref+.02 if action == "BUY" else max(0, ref-.02)
                    out.append({"legs": [leg(m, side, action, qty, limit)], "ready_at": now+2, "expires_at": now+60,
                                "reason": "Deterministic wallet copy; not risk-free arbitrage", "signal_id": sid})
                except (ValueError, KeyError) as exc:
                    out.append({"skip": str(exc), "signal_id": sid})
            return out or [{"skip": "No new verified reference trade"}]
        for m in markets.values():
            try:
                validate_market(m, now)
                if now-self.last_decision.get(m["slug"], -math.inf) < 300:
                    continue
                bid, ask = levels(m, "YES", "SELL", now), levels(m, "YES", "BUY", now)
                if not bid or not ask:
                    raise ValueError("Two-sided book required for model comparison")
                mid = (bid[0][0]+ask[0][0])/2
                if not self.config.get("strategy_memory", False):
                    m = dict(m, retrieved_documents=[d for d in m.get("retrieved_documents", []) if d.get("kind") != "strategy_card"])
                if not self.config.get("external_predictions", False):
                    m = dict(m, retrieved_documents=[d for d in m.get("retrieved_documents", []) if d.get("kind") != "external_prediction"])
                ctx = context(m, now)
                if self.config.get('research_protocol') != LATEST_VERSION:
                    ctx['forecast'] = {k:v for k,v in ctx['forecast'].items() if k not in ('comparison_models','comparison_error','station_coordinates')}
                if self.config.get('research_protocol') in (VERSION, LATEST_VERSION):
                    ctx['research_diagnostics'] = diagnostics(m, ctx, now, self.config['research_protocol'], selected(self.config))
                self.last_decision[m["slug"]] = now
                prediction, audit, latency = forecast(kind, ctx, self.model, mid, self.config.get("swarm_count", 5))
                audit.update({"probability_yes": prediction["probability_yes"], "slug": m["slug"], "market_mid": mid,
                              "risk_profile": profile_name, "risk_parameters": dict(profile),
                              "market_id": m["id"], "rules_hash": m["rules_hash"],
                              "baseline_probability": ctx["baseline_probability"], "at": now, "reason": prediction["reason"]})
                if 'research_diagnostics' in ctx:
                    audit['research_diagnostics'] = ctx['research_diagnostics']
                if prediction["abstain"] or prediction["confidence"] < profile["min_confidence"] or prediction["upper"]-prediction["lower"] > profile["max_width"]:
                    out.append({"skip": "Model abstained or risk-profile uncertainty gate failed", "audit": audit})
                    continue
                # Exit is also modeled later, at a bid, without shorting.
                exit_legs = []
                for side in ("YES", "NO"):
                    held = math.floor(account.available(m["slug"], side)*100)/100
                    if held <= 0:
                        continue
                    fair = prediction["probability_yes"] if side == "YES" else 1-prediction["probability_yes"]
                    proceeds, _ = quote(m, side, "SELL", held, now)
                    if proceeds/held > fair+.03:
                        exit_legs.append(leg(m, side, "SELL", held, max(0, proceeds/held-.02)))
                if exit_legs:
                    out.append({"legs": exit_legs, "ready_at": now+max(2, latency), "expires_at": now+120, "reason": "Model exit", "audit": audit})
                    continue
                policy = ctx.get('research_diagnostics', {}).get('weather_hypotheses', {}).get('entry_policy', {})
                if policy.get('blocks'):
                    out.append({'skip': '; '.join(policy['blocks']), 'audit': audit})
                    continue
                required_edge = profile['edge']+policy.get('extra_edge', 0)
                choices = []
                for side in ("YES", "NO"):
                    if side not in policy.get('allowed_sides', ['YES', 'NO']):
                        continue
                    conservative = prediction["lower"] if side == "YES" else 1-prediction["upper"]
                    point = prediction["probability_yes"] if side == "YES" else 1-prediction["probability_yes"]
                    conservative = profile["bound_weight"]*conservative+(1-profile["bound_weight"])*point
                    exposure = sum(p["cost"] for p in account.positions.values() if tuple(p["event"]) == event(m))
                    budget = min(remaining_budget(account, m), max(0, profile["event_cap"]-exposure))
                    # Common capped fractional Kelly proposal across all forecasting arms.
                    unit = quote(m, side, "BUY", max(1, number(m["minimum_qty"])), now)[0]/max(1, number(m["minimum_qty"]))
                    kelly = max(0, (conservative-unit)/max(.001, 1-unit))*profile["kelly"]
                    budget = min(budget, 50*kelly)
                    sized = size(m, side, budget, now)
                    if sized and policy.get('size_factor', 1) < 1:
                        reduced = math.floor(sized[0]*policy['size_factor']*100)/100
                        sized = (reduced, quote(m, side, 'BUY', reduced, now)[0]) if reduced >= number(m['minimum_qty']) else None
                    if sized:
                        qty, cash = sized
                        edge = conservative-cash/qty
                        if edge >= required_edge:
                            choices.append((edge, leg(m, side, "BUY", qty, conservative-required_edge)))
                if choices:
                    chosen = max(choices, key=lambda x: x[0])[1]
                    out.append({"legs": [chosen], "ready_at": now+max(2, latency), "expires_at": now+120, "reason": prediction["reason"], "audit": audit, "risk_event_cap": profile["event_cap"]})
                else:
                    out.append({"skip": "No positive conservative edge after fees, uncertainty and caps", "audit": audit})
            except (ValueError, KeyError) as exc:
                out.append({"skip": str(exc), "slug": m.get("slug")})
        return out
