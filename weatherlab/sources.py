"""Bounded public GET-only collection. No exchange authentication or order paths."""
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, date
from pathlib import Path
from .core import digest, stamp, identity

HOSTS = {"gateway.polymarket.us", "api.weather.gov", "data-api.polymarket.com", "gamma-api.polymarket.com"}
STATIONS = {"KNYC", "KLAX", "KSFO", "KMIA", "KMDW"}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("Unexpected public-source redirect")


class PublicSource:
    def __init__(self, root, max_requests=100):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.count, self.max_requests = 0, max_requests
        self.opener = urllib.request.build_opener(NoRedirect())

    def get(self, url):
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in HOSTS or parsed.username or parsed.port:
            raise ValueError("Public source not allowlisted")
        self.count += 1
        if self.count > self.max_requests:
            raise ValueError("Public request budget exhausted")
        start = time.time()
        request = urllib.request.Request(url, headers={"User-Agent": "WeatherLab/1.0 public paper research", "Accept": "application/json"}, method="GET")
        with self.opener.open(request, timeout=7) as response:
            raw = response.read(4000001)
        if len(raw) > 4000000:
            raise ValueError("Oversized public payload")
        received = time.time()
        data = json.loads(raw)
        receipt = {"url": url, "request_started": start, "received_at": received, "sha256": hashlib.sha256(raw).hexdigest(), "data": data}
        path = self.root/(str(self.count).zfill(4)+".json")
        path.write_text(json.dumps(receipt, allow_nan=False), encoding="utf-8")
        return data, received, receipt["sha256"]

    def inventory(self):
        rows, complete = [], False
        for offset in (0, 100, 200):
            data, received, _ = self.get("https://gateway.polymarket.us/v1/markets?"+urllib.parse.urlencode({"categories": "climate", "active": "true", "closed": "false", "limit": 100, "offset": offset}))
            batch = data["markets"]
            rows.extend(batch)
            if len(batch) < 100:
                complete = True
                break
        if len({m["id"] for m in rows}) != len(rows):
            raise ValueError("Overlapping inventory pages")
        return rows, received, complete

    def book(self, m):
        raw, received, _ = self.get("https://gateway.polymarket.us/v1/markets/"+urllib.parse.quote(m["slug"], safe="")+"/book")
        b = raw["marketData"]
        def ls(name):
            if any(r["px"]["currency"] != "USD" for r in b[name]):
                raise ValueError("Non-USD book")
            return [[float(r["px"]["value"]), float(r["qty"])] for r in b[name]]
        return {"slug": b["marketSlug"], "state": "OPEN" if b["state"] == "MARKET_STATE_OPEN" else "CLOSED",
                "received": received, "source_at": stamp(b["transactTime"]), "bids": ls("bids"), "asks": ls("offers")}

    def forecast(self, m):
        station = m["station"]
        loc, _, _ = self.get("https://api.weather.gov/stations/"+station)
        if loc["properties"]["stationIdentifier"] != station:
            raise ValueError("NWS station mismatch")
        lon, lat = loc["geometry"]["coordinates"][:2]
        point, _, _ = self.get(f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}")
        raw, received, hashed = self.get(point["properties"]["forecastHourly"])
        periods = [p for p in raw["properties"]["periods"] if p["startTime"][:10] == m["date"]]
        # An intraday partial forecast cannot establish a full-day maximum without observed highs.
        if len(periods) < 23 or len({p["startTime"] for p in periods}) != len(periods):
            raise ValueError("Incomplete full-day hourly forecast; intraday observed-high adapter required")
        if any(p["temperatureUnit"] != "F" for p in periods):
            raise ValueError("Expected Fahrenheit forecast")
        return {"station": station, "date": m["date"], "high_f": max(p["temperature"] for p in periods),
                "issued_at": raw["properties"]["updateTime"], "received_at": received,
                "evidence_id": "nws-"+hashed[:24], "source_url": point["properties"]["forecastHourly"],
                "product": "NWS hourly grid forecast, not CLI", "revision_f": 0}


def normalize_market(m, received):
    text = m.get("description", "")
    stations = set(re.findall(r"\bK[A-Z]{3}\b", text)) & STATIONS
    day = re.search(r"for (\d{4}-\d{2}-\d{2})", text)
    if len(stations) != 1 or not day or "highest temperature" not in text.lower():
        raise ValueError("Unsupported or ambiguous weather station/date")
    if "National Weather Service" not in text or "Climatological Report" not in text:
        raise ValueError("Unverified NWS CLI settlement source")
    date.fromisoformat(day[1])
    between = re.search(r"between (-?\d+)F and (-?\d+)F", text)
    below = re.search(r"(?:below|less than) (-?\d+)F", text)
    atmost = re.search(r"less than or equal to (-?\d+)F", text)
    above = re.search(r"(?:at least|greater than or equal to) (-?\d+)F", text)
    if between:
        lower, upper = map(int, between.groups())
    elif atmost:
        lower, upper = None, int(atmost[1])
    elif below:
        lower, upper = None, int(below[1])-1
    elif above:
        lower, upper = int(above[1]), None
    else:
        raise ValueError("Unsupported range wording; requires explicit parser extension")
    return {"venue": "polymarket_us", "id": str(m["id"]), "slug": m["slug"], "station": stations.pop(), "date": day[1],
            "lower_f": lower, "upper_f": upper, "source": "NWS_CLI", "rules_hash": hashlib.sha256(text.encode()).hexdigest(),
            "metadata_received": received, "active": m.get("active") is True and m.get("closed") is False,
            "close_at": m["endDate"], "minimum_qty": float(m["minimumTradeQty"]), "tick": float(m["orderPriceMinTickSize"]),
            "fee_coefficient": float(m.get("feeCoefficient", .07)), "forecast": None, "history": []}


def wallet_signals(source, wallet, mappings, markets, started, seen):
    if not re.fullmatch(r"0x[0-9a-fA-F]{40}", wallet):
        raise ValueError("Valid public reference wallet required")
    raw, received, _ = source.get("https://data-api.polymarket.com/activity?"+urllib.parse.urlencode({"user": wallet, "type": "TRADE", "limit": 100, "sortBy": "TIMESTAMP", "sortDirection": "DESC"}))
    if not isinstance(raw, list) or len(raw) >= 100:
        raise ValueError("Wallet coverage incomplete; refuse truncated window")
    signals, rejects = [], []
    for r in raw:
        sid = digest({k: r.get(k) for k in ("transactionHash", "asset", "side", "price", "size", "timestamp")})
        if sid in seen or r["timestamp"] < started:
            continue
        seen.add(sid)
        try:
            if r.get("proxyWallet", "").lower() != wallet.lower() or r.get("type") != "TRADE":
                raise ValueError("Wallet identity/type mismatch")
            mapping = next((x for x in mappings if x["condition_id"] == r["conditionId"] and x["token"] == r["asset"]), None)
            if not mapping:
                raise ValueError("No reviewed international-to-US rules mapping")
            us = markets[mapping["us_slug"]]
            data, _, _ = source.get("https://gamma-api.polymarket.com/markets?"+urllib.parse.urlencode({"condition_ids": r["conditionId"]}))
            exact = [x for x in data if x["conditionId"] == r["conditionId"]]
            if len(exact) != 1:
                raise ValueError("Ambiguous reference condition")
            ref = exact[0]
            text = ref["description"]
            if hashlib.sha256(text.encode()).hexdigest() != mapping["reference_rules_hash"]:
                raise ValueError("Reference rules changed")
            if "Climatological Report" not in text or "National Weather Service" not in text or "Show Hourly Data" in text:
                raise ValueError("Reference source is not equivalent to US daily CLI")
            tokens, outcomes = json.loads(ref["clobTokenIds"]), json.loads(ref["outcomes"])
            if r["asset"] not in tokens or outcomes[tokens.index(r["asset"])].upper() != r["outcome"].upper():
                raise ValueError("Reference token/outcome mismatch")
            if tuple(mapping["contract_identity"]) != identity(us) or mapping["us_rules_hash"] != us["rules_hash"]:
                raise ValueError("Mapping identity mismatch")
            if mapping.get("reviewed") is not True or not mapping.get("review_note"):
                raise ValueError("Human review of exact settlement equivalence required")
            signals.append({"id": sid, "wallet": wallet.lower(), "slug": us["slug"], "trade_at": r["timestamp"], "received_at": received,
                            "price": r["price"], "side": r["outcome"].upper(), "action": r["side"], "contract_identity": identity(us),
                            "mapping_verified": True, "us_market_id": us["id"], "us_rules_hash": us["rules_hash"]})
        except (ValueError, KeyError) as exc:
            rejects.append({"signal_id": sid, "reason": str(exc)})
    return signals, rejects


def capture(root, seconds=30, max_markets=4, wallet="", mappings=None, on_frame=None, stop_event=None):
    if not 5 <= seconds <= 120 or not 1 <= max_markets <= 12:
        raise ValueError("Capture bound: 5-120 seconds and 1-12 markets")
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    source = PublicSource(root/"receipts")
    started = time.time()
    dataset = {"schema_version": 1, "venue": "polymarket_us", "synthetic": False, "started_at": started, "frames": [], "coverage": {}, "errors": []}
    try:
        raw, received, complete = source.inventory()
        normalized = []
        for row in raw:
            try:
                normalized.append(normalize_market(row, received))
            except (ValueError, KeyError) as exc:
                dataset["errors"].append({"slug": row.get("slug"), "reason": str(exc)})
        # Predeclared lexicographic subset, never rank/select by observed profitability.
        selected = sorted(normalized, key=lambda m: (m["date"], m["station"], m["slug"]))[:max_markets]
        dataset["coverage"] = {"inventory_complete": complete, "inventory_count": len(raw), "supported": len(normalized), "selected": len(selected),
                               "selection": "date/station/slug ascending, bounded subset", "continuous": False, "settlements_collected": False}
        cache = {}
        for m in selected:
            try:
                k = (m["station"], m["date"])
                if k not in cache:
                    cache[k] = source.forecast(m)
                m["forecast"] = cache[k]
            except Exception as exc:
                dataset["errors"].append({"slug": m["slug"], "reason": "forecast: "+type(exc).__name__+": "+str(exc)[:180]})
        seen = set()
        # Wall limit includes inventory and forecast retrieval.
        while time.time()-started < seconds and source.count < 96 and not (stop_event and stop_event.is_set()):
            frame = {"markets": [], "signals": [], "settlements": []}
            for m in selected:
                try:
                    m["book"] = source.book(m)
                    frame["markets"].append(dict(m))
                except Exception as exc:
                    dataset["errors"].append({"slug": m["slug"], "reason": "book: "+type(exc).__name__+": "+str(exc)[:160]})
            if wallet:
                try:
                    frame["signals"], rejects = wallet_signals(source, wallet, mappings or [], {m["slug"]: m for m in selected}, started, seen)
                    dataset["errors"].extend(rejects)
                except Exception as exc:
                    dataset["errors"].append({"reason": "wallet: "+type(exc).__name__+": "+str(exc)[:180]})
            frame["at"] = time.time()
            dataset["frames"].append(frame)
            if on_frame:
                on_frame(frame)
            if stop_event:
                stop_event.wait(2)
            else:
                time.sleep(2)
    except Exception as exc:
        dataset["errors"].append({"reason": "capture: "+type(exc).__name__+": "+str(exc)[:180]})
    finally:
        dataset["finished_at"] = time.time()
        dataset["next_job"] = "Review receipts and coverage; supply causal historical pairs, exact wallet mapping and later venue settlement receipts."
        (root/"dataset.json").write_text(json.dumps(dataset, indent=2), encoding="utf-8")
    return dataset
