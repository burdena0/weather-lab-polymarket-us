"""Explicitly synthetic examples; no market-performance evidence."""
import copy
from datetime import datetime, timezone, timedelta
from .core import digest, identity

WALLET = "0x"+"1"*40


def sample():
    start = datetime(2026, 9, 15, 12, tzinfo=timezone.utc).timestamp()
    histories = []
    for i in range(35):
        d = datetime(2026, 8, 1, tzinfo=timezone.utc)+timedelta(days=i)
        at = d.timestamp()
        histories.append({"evidence_id": f"fixture-history-{i}", "kind": "history", "station": "KNYC", "date": d.date().isoformat(),
                          "source": "NWS_CLI", "forecast_high_f": 75+(i%3), "actual_high_f": 76+(i%3),
                          "forecast_issued": at-7200, "forecast_received": at-3600, "day_start": at, "day_end": at+86400,
                          "outcome_received": at+90000, "published_at": at+89900, "received_at": at+90000,
                          "available_at": at+90000, "synthetic": True,
                          "text": "Synthetic KNYC NWS CLI temperature forecast residual example; not observed data."})
    m = {"venue": "polymarket_us", "id": "fixture-nyc-01", "slug": "fixture-nyc-high", "station": "KNYC", "date": "2026-09-16",
         "lower_f": 75, "upper_f": 77, "source": "NWS_CLI", "rules_hash": digest("fixture daily CLI rules"),
         "metadata_received": start, "active": True, "close_at": start+86400, "minimum_qty": .01, "tick": .01, "fee_coefficient": .06,
         "forecast": {"station": "KNYC", "date": "2026-09-16", "high_f": 75, "issued_at": start-60, "received_at": start-30,
                      "revision_f": .1, "evidence_id": "fixture-forecast", "product": "SYNTHETIC hourly grid maximum"},
         "history": histories}
    frames = []
    for i in range(5):
        now = start+i*20
        market = copy.deepcopy(m)
        market["metadata_received"] = now
        market["book"] = {"slug": m["slug"], "state": "OPEN", "received": now, "source_at": now, "bids": [[.34, 50]], "asks": [[.36, 50]]}
        frame = {"at": now, "markets": [market], "signals": [], "settlements": []}
        if i == 0:
            frame["signals"] = [{"id": "fixture-buy", "wallet": WALLET, "slug": m["slug"], "trade_at": now, "received_at": now,
                                 "price": .38, "side": "YES", "action": "BUY", "contract_identity": identity(m),
                                 "mapping_verified": True, "us_rules_hash": m["rules_hash"], "us_market_id": m["id"]}]
        frames.append(frame)
    settled = start+90000
    frames.append({"at": settled, "markets": [], "signals": [], "settlements": [
        {"slug": m["slug"], "market_id": m["id"], "rules_hash": m["rules_hash"], "venue": "polymarket_us", "final": True,
         "yes_payout": 1, "received_at": settled, "evidence_id": "fixture-settlement"}]})
    return {"schema_version": 1, "venue": "polymarket_us", "synthetic": True, "frames": frames,
            "coverage": {"description": "Synthetic plumbing demonstration, no cloud model or real market performance."}}, histories


def config(strategy):
    return {"strategy": strategy, "venue": "polymarket_us", "mode": "paper", "initial_capital": 50,
            "reserve": 40, "monthly_subscription": 200, "reference_wallet": "", "control_mode": "copy", "swarm_count": 5, "risk_profile": "balanced"}
