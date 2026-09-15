"""Shared validation, fee stress model, causal retrieval and paper ledger."""
import copy
import hashlib
import json
import math
import re
from datetime import datetime, date

INITIAL = 50.0
RESERVE = 40.0
MONTHLY = 200.0
MAX_POSITION = 5.0
MAX_EVENT = 5.0
SLIPPAGE = .002


def number(x):
    if isinstance(x, bool):
        raise ValueError("Boolean is not a number")
    n = float(x)
    if not math.isfinite(n):
        raise ValueError("Nonfinite number")
    return n


def stamp(x):
    if isinstance(x, (float, int)):
        return number(x)
    x = re.sub(r'(\.\d{6})\d+(?=Z|[+-]\d{2}:\d{2}$)', r'\1', x)
    d = datetime.fromisoformat(x.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("Timestamp must include timezone")
    return d.timestamp()


def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, allow_nan=False).encode()).hexdigest()


def identity(m):
    return tuple(m[k] for k in ("station", "date", "lower_f", "upper_f", "source"))


def event(m):
    return (m["station"], m["date"], m["source"])


def validate_market(m, now, require_open=True):
    if m.get("venue") != "polymarket_us" or m.get("source") != "NWS_CLI":
        raise ValueError("Only explicit Polymarket US / NWS CLI contracts supported")
    date.fromisoformat(m["date"])
    if not m.get("rules_hash") or not m.get("id") or not m.get("slug"):
        raise ValueError("Missing contract identity")
    if not 0 <= now - number(m["metadata_received"]) <= 300:
        raise ValueError("Stale contract metadata")
    lo, hi = m["lower_f"], m["upper_f"]
    if any(x is not None and (type(x) is not int or not -150 <= x <= 160) for x in (lo, hi)):
        raise ValueError("Invalid integer Fahrenheit bounds")
    if lo is not None and hi is not None and lo > hi:
        raise ValueError("Inverted interval")
    if require_open and (m.get("active") is not True or now >= stamp(m["close_at"])):
        raise ValueError("Market closed")
    if not 0 < number(m["minimum_qty"]) <= 100 or not 0 < number(m["tick"]) < 1:
        raise ValueError("Invalid market increments")


def levels(m, side, action, now):
    validate_market(m, now)
    b = m["book"]
    if b["slug"] != m["slug"] or b["state"] != "OPEN":
        raise ValueError("Wrong or closed book")
    if not 0 <= now - number(b["received"]) <= 10:
        raise ValueError("Stale book receipt")
    if not 0 <= now - number(b["source_at"]) <= 120:
        raise ValueError("Old/future book source; conservative snapshot policy")
    bids, asks = b["bids"], b["asks"]
    for ls in (bids, asks):
        if len(ls) > 1000 or len({number(p) for p, q in ls}) != len(ls):
            raise ValueError("Duplicate or oversized depth")
        for p, q in ls:
            if not 0 < number(p) < 1 or number(q) <= 0:
                raise ValueError("Invalid depth")
            if abs(number(p) / number(m["tick"]) - round(number(p) / number(m["tick"]))) > 1e-6:
                raise ValueError("Off-tick depth")
    if bids and asks and max(number(p) for p, _ in bids) >= min(number(p) for p, _ in asks):
        raise ValueError("Crossed book")
    if side == "NO":
        bids, asks = [[1-number(p), number(q)] for p, q in asks], [[1-number(p), number(q)] for p, q in bids]
    elif side != "YES":
        raise ValueError("Invalid outcome")
    if action not in ("BUY", "SELL"):
        raise ValueError("Invalid action")
    return sorted([[number(p), number(q)] for p, q in (asks if action == "BUY" else bids)], reverse=action == "SELL")


def quote(m, side, action, quantity, now):
    q = number(quantity)
    if q < number(m["minimum_qty"]) - 1e-9 or q <= 0 or abs(q*100-round(q*100)) > 1e-6:
        raise ValueError("Quantity below minimum or unsupported precision")
    remaining, cash, fee = q, 0.0, 0.0
    # Deliberate stress bound, not a claim of verified actual venue fees.
    theta = max(.07, number(m.get("fee_coefficient", .07)))
    if theta > 1:
        raise ValueError("Invalid fee coefficient")
    for p, depth in levels(m, side, action, now):
        take = min(depth, remaining)
        f = math.ceil((theta*take*p*(1-p)-1e-12)*100)/100
        fee += f
        cash += take*(p+SLIPPAGE if action == "BUY" else max(0, p-SLIPPAGE)) + (f if action == "BUY" else -f)
        remaining -= take
        if remaining < 1e-8:
            return round(max(cash, 0), 8), round(fee, 8)
    raise ValueError("Insufficient visible depth")


def history_asof(rows, m, now):
    valid = []
    seen = set()
    for r in rows:
        if r.get("station") != m["station"] or r.get("source") != m["source"] or r.get("date", "9999") >= m["date"]:
            continue
        if max(stamp(r["available_at"]), stamp(r["forecast_received"]), stamp(r["outcome_received"])) > now:
            continue
        if stamp(r["forecast_issued"]) > stamp(r["forecast_received"]) or stamp(r["forecast_received"]) >= stamp(r["day_start"]):
            continue
        if stamp(r["outcome_received"]) < stamp(r["day_end"]) or stamp(r["available_at"]) < stamp(r["outcome_received"]):
            continue
        if r["date"] in seen:
            raise ValueError("Duplicate historical station-day")
        seen.add(r["date"])
        for k in ("forecast_high_f", "actual_high_f"):
            if not -150 <= number(r[k]) <= 160:
                raise ValueError("Invalid historical temperature")
        valid.append(r)
    return sorted(valid, key=lambda r: r["date"])[-90:]


def context(m, now):
    f = m.get("forecast")
    if not isinstance(f, dict):
        raise ValueError("Missing complete forecast; abstaining")
    if f["station"] != m["station"] or f["date"] != m["date"]:
        raise ValueError("Forecast station/day mismatch")
    if not 0 <= now-stamp(f["issued_at"]) <= 21600 or not 0 <= now-stamp(f["received_at"]) <= 900:
        raise ValueError("Stale/future forecast")
    if stamp(f["issued_at"]) > stamp(f["received_at"]):
        raise ValueError("Forecast received before issuance")
    h = history_asof(m.get("history", []), m, now)
    if len(h) < 10:
        raise ValueError("Need at least 10 causal station-day forecast/outcome records")
    forecast = number(f["high_f"])
    if not -150 <= forecast <= 160:
        raise ValueError("Invalid forecast temperature")
    # Empirical residual distribution, with half-count smoothing; an unvalidated baseline.
    projected = [forecast + number(r["actual_high_f"])-number(r["forecast_high_f"]) for r in h]
    def yes(t):
        rounded = math.floor(t+.5)
        return (m["lower_f"] is None or rounded >= m["lower_f"]) and (m["upper_f"] is None or rounded <= m["upper_f"])
    p = (sum(yes(t) for t in projected)+.5)/(len(h)+1)
    docs = [r for r in m.get("retrieved_documents", []) if r.get("station") == m["station"] and
            max(stamp(r["published_at"]), stamp(r["received_at"]), stamp(r["available_at"])) <= now]
    return {"as_of": now, "contract": {k: m[k] for k in ("id", "slug", "station", "date", "lower_f", "upper_f", "source", "rules_hash")},
            "forecast": f, "history": h, "baseline_probability": p,
            "retrieved_documents": docs,
            "evidence_ids": [f["evidence_id"]]+[r["evidence_id"] for r in h]+[r["evidence_id"] for r in docs],
            "limitations": "Residual model is uncalibrated; hourly grid maximum is not the CLI settlement observation."}


def complete_partition(markets):
    if len(markets) < 2 or len({event(m) for m in markets}) != 1:
        return False
    rows = sorted(markets, key=lambda m: -math.inf if m["lower_f"] is None else m["lower_f"])
    if rows[0]["lower_f"] is not None or rows[-1]["upper_f"] is not None:
        return False
    return all(a["upper_f"] is not None and b["lower_f"] is not None and a["upper_f"]+1 == b["lower_f"] for a, b in zip(rows, rows[1:]))


class Account:
    def __init__(self):
        self.cash = INITIAL
        self.positions = {}
        self.realized = 0.0
        self.fees = 0.0
        self.fills = 0
        self.model_cost = 0.0
        self.resolved = {}

    def available(self, slug, side):
        return self.positions.get(slug+":"+side, {}).get("qty", 0.0)

    def fill(self, legs, markets, now, cap=MAX_POSITION, minimum_payout=None, event_cap=MAX_EVENT):
        event_cap = min(MAX_EVENT, number(event_cap))
        if minimum_payout is not None:
            times = [markets[leg["slug"]]["book"]["source_at"] for leg in legs]
            if max(times)-min(times) > 2:
                raise ValueError("Basket books lost synchronization before fill")
        draft = copy.deepcopy(self)
        working = copy.deepcopy(markets)
        total_cost = 0.0
        details = []
        for leg in legs:
            m = working[leg["slug"]]
            if m["rules_hash"] != leg["rules_hash"] or m["id"] != leg["market_id"]:
                raise ValueError("Contract changed since decision")
            key = m["slug"]+":"+leg["side"]
            qty = number(leg["qty"])
            cash, fee = quote(m, leg["side"], leg["action"], qty, now)
            unit = cash/qty
            if leg["action"] == "BUY" and unit > leg["limit"] + 1e-9:
                raise ValueError("Price moved beyond decision limit")
            if leg["action"] == "SELL" and unit < leg["limit"] - 1e-9:
                raise ValueError("Exit price moved beyond decision limit")
            pos = draft.positions.get(key, {"qty": 0, "cost": 0, "event": event(m), "rules_hash": m["rules_hash"], "market_id": m["id"]})
            if leg["action"] == "BUY":
                if draft.cash-cash < RESERVE-1e-8 or pos["cost"]+cash > MAX_POSITION+1e-8:
                    raise ValueError("Cash reserve or position cap")
                exposure = sum(p["cost"] for p in draft.positions.values() if tuple(p["event"]) == event(m))
                if exposure+cash > event_cap+1e-8:
                    raise ValueError("Station-day exposure cap")
                pos["qty"] += qty
                pos["cost"] += cash
                draft.cash -= cash
                total_cost += cash
            else:
                if qty > pos["qty"]+1e-8:
                    raise ValueError("No short selling or outside inventory")
                basis = pos["cost"]*qty/pos["qty"]
                pos["qty"] -= qty
                pos["cost"] -= basis
                draft.cash += cash
                draft.realized += cash-basis
            draft.positions[key] = pos
            draft.fees += fee
            draft.fills += 1
            details.append({**leg, "cash": cash, "fee": fee})
            source_side = "asks" if (leg["side"] == "YES") == (leg["action"] == "BUY") else "bids"
            remaining = qty
            ordered = sorted(m["book"][source_side], reverse=source_side == "bids")
            for level in ordered:
                take = min(remaining, level[1])
                level[1] -= take
                remaining -= take
            m["book"][source_side] = [ls for ls in ordered if ls[1] > 1e-8]
        if total_cost > cap+1e-8 or (minimum_payout is not None and minimum_payout-total_cost < .02):
            raise ValueError("Basket/budget edge disappeared after delay")
        self.__dict__.update(draft.__dict__)
        for l in legs:
            markets[l["slug"]]["book"] = working[l["slug"]]["book"]
        return details

    def settle(self, s, now):
        slug = s["slug"]
        if s.get("venue") != "polymarket_us" or s.get("final") is not True or number(s["yes_payout"]) not in (0, 1):
            raise ValueError("Require final venue binary settlement")
        if stamp(s["received_at"]) > now or not s.get("evidence_id"):
            raise ValueError("Future or missing settlement evidence")
        if slug in self.resolved:
            if self.resolved[slug] != s["yes_payout"]:
                raise ValueError("Conflicting settlement")
            return False
        for side in ("YES", "NO"):
            p = self.positions.get(slug+":"+side)
            if p and p["qty"] > 0 and (p["market_id"] != s["market_id"] or p["rules_hash"] != s["rules_hash"]):
                raise ValueError("Settlement contract mismatch")
        for side in ("YES", "NO"):
            key = slug+":"+side
            p = self.positions.get(key)
            if p and p["qty"] > 0:
                if p["market_id"] != s["market_id"] or p["rules_hash"] != s["rules_hash"]:
                    raise ValueError("Settlement contract mismatch")
                payout = p["qty"]*(s["yes_payout"] if side == "YES" else 1-s["yes_payout"])
                self.cash += payout
                self.realized += payout-p["cost"]
                p["qty"], p["cost"] = 0, 0
        self.resolved[slug] = s["yes_payout"]
        return True

    def summary(self, markets, now, elapsed):
        marked, unknown, open_cost = 0.0, 0, 0.0
        for key, p in self.positions.items():
            if p["qty"] <= 1e-8:
                continue
            slug, side = key.rsplit(":", 1)
            open_cost += p["cost"]
            try:
                marked += quote(markets[slug], side, "SELL", p["qty"], now)[0]
            except (ValueError, KeyError):
                unknown += 1
        overhead = MONTHLY*max(0, elapsed)/(30*86400)
        return {"cash": round(self.cash, 6), "open_value": None if unknown else round(marked, 6), "unmarked_positions": unknown,
                "open_cost": round(open_cost, 6), "realized_pnl": round(self.realized, 6), "fees": round(self.fees, 6),
                "model_cost": round(self.model_cost, 6), "subscription_accrued": round(overhead, 6),
                "net_after_costs": None if unknown else round(self.cash+marked-INITIAL-self.model_cost-overhead, 6),
                "fills": self.fills, "initial_capital": INITIAL, "reserve": RESERVE,
                "conservative_equity_floor": round(self.cash, 6)}
