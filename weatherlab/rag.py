"""Point-in-time retrieval: SQLite FTS5 + station-specific weather analogues.

No embedding service, vector DB subscription, or generated facts are required.
The persisted index is reproducible from JSONL; immutable document revisions only.
"""
import json
import math
import re
import sqlite3
from pathlib import Path
from .core import digest, stamp, number


class EvidenceStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS evidence (
              id TEXT PRIMARY KEY, kind TEXT, station TEXT, event_date TEXT,
              published REAL, received REAL, available REAL, hash TEXT, payload TEXT);
            CREATE INDEX IF NOT EXISTS evidence_asof ON evidence(station,available,event_date);
            CREATE VIRTUAL TABLE IF NOT EXISTS evidence_fts USING fts5(id UNINDEXED, text);
            """)

    def connect(self):
        return sqlite3.connect(self.path, timeout=5)

    def ingest(self, rows):
        count = 0
        with self.connect() as db:
            for row in rows:
                ident = row["evidence_id"]
                if not isinstance(ident, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,180}", ident):
                    raise ValueError("Invalid evidence identifier")
                if row["kind"] not in ("history", "rules", "forecast", "observation", "research_note"):
                    raise ValueError("Unsupported evidence type")
                published, received, available = [stamp(row[k]) for k in ("published_at", "received_at", "available_at")]
                if not published <= received <= available:
                    raise ValueError("Evidence chronology violated")
                if row.get("synthetic") is not True and not str(row.get("source_url", "")).startswith("https://"):
                    raise ValueError("Real evidence needs source URL")
                if len(json.dumps(row)) > 50000:
                    raise ValueError("Chunk exceeds 50 KB; split with immutable revision IDs")
                hashed = digest(row)
                old = db.execute("SELECT hash FROM evidence WHERE id=?", (ident,)).fetchone()
                if old:
                    if old[0] != hashed:
                        raise ValueError("Evidence revision is immutable: "+ident)
                    continue
                if row["kind"] == "history":
                    for key in ("forecast_high_f", "actual_high_f", "forecast_received", "forecast_issued", "outcome_received", "day_start", "day_end", "source"):
                        if key not in row:
                            raise ValueError("Incomplete forecast/outcome pair: "+key)
                    if stamp(row["forecast_received"]) >= stamp(row["day_start"]):
                        raise ValueError("Historical forecast was not received before target day")
                    if stamp(row["outcome_received"]) > available:
                        raise ValueError("Historical outcome not available at recorded time")
                    if stamp(row["outcome_received"]) < stamp(row["day_end"]) or stamp(row["forecast_issued"]) > stamp(row["forecast_received"]):
                        raise ValueError("Outcome/forecast chronology violated")
                db.execute("INSERT INTO evidence VALUES(?,?,?,?,?,?,?,?,?)", (ident, row["kind"], row["station"], row["date"], published, received, available, hashed, json.dumps(row)))
                db.execute("INSERT INTO evidence_fts VALUES(?,?)", (ident, row.get("text", "")))
                count += 1
        return count

    def retrieve(self, market, now, limit=30, allow_synthetic=False):
        if not 10 <= limit <= 90:
            raise ValueError("Historical retrieval requires 10-90 records")
        query = " OR ".join(re.findall(r"[A-Za-z0-9]+", market["station"]+" temperature forecast maximum CLI")[:12])
        with self.connect() as db:
            rows = db.execute("SELECT payload FROM evidence WHERE station=? AND available<=? AND published<=? AND received<=? AND event_date<? AND kind='history'",
                              (market["station"], now, now, now, market["date"])).fetchall()
            notes = db.execute("SELECT e.payload,bm25(evidence_fts) FROM evidence_fts JOIN evidence e ON e.id=evidence_fts.id WHERE evidence_fts MATCH ? AND e.station=? AND e.available<=? AND e.published<=? AND e.received<=? AND e.event_date<=? AND e.kind IN ('rules','research_note') ORDER BY bm25(evidence_fts),e.id LIMIT 8",
                               (query, market["station"], now, now, now, market["date"])).fetchall()
        rows = [json.loads(r[0]) for r in rows]
        rows = [r for r in rows if r.get("source") == market["source"] and (allow_synthetic or not r.get("synthetic"))]
        target = number(market["forecast"]["high_f"])
        # Numeric analogues are intentionally separate from lexical relevance.
        # Similar forecast level plus seasonal distance; scores are heuristics, not probabilities.
        from datetime import date
        day = date.fromisoformat(market["date"]).timetuple().tm_yday
        def distance(r):
            seasonal = abs(date.fromisoformat(r["date"]).timetuple().tm_yday-day)
            seasonal = min(seasonal, 366-seasonal)
            return abs(number(r["forecast_high_f"])-target)/5 + seasonal/90
        # Keep one latest eligible revision per station-day, never double count revisions.
        latest = {}
        for r in rows:
            if r["date"] not in latest or stamp(r["available_at"]) > stamp(latest[r["date"]]["available_at"]):
                latest[r["date"]] = r
        selected = sorted(latest.values(), key=lambda r: (distance(r), r["date"], r["evidence_id"]))[:limit]
        docs = [json.loads(r[0]) for r in notes]
        docs = [r for r in docs if allow_synthetic or not r.get("synthetic")]
        return {"history": selected, "documents": docs,
                "audit": {"method": "station/time filters + numeric weather analogues + SQLite FTS5 BM25",
                          "as_of": now, "candidates": len(latest), "selected_ids": [r["evidence_id"] for r in selected],
                          "document_ids": [r["evidence_id"] for r in docs], "index_path": self.path.name,
                          "scores": {r["evidence_id"]: distance(r) for r in selected}}}
