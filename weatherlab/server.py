"""Loopback-only dashboard with declarative ZIP registration and isolated runs."""
import io
import copy
import json
import os
import re
import secrets
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from .engine import replay
from .fixtures import sample, WALLET
from .packages import inspect_package
from .rag import EvidenceStore
from .sources import capture
from .strategies import STRATEGIES, RISK_PROFILES
from .session import Session
from .accounts import AccountLink
from .readiness import readiness, check_models
from .research import collect_evidence
from .historical import run_month
from .disagreement import DisagreementStudy

ROOT = Path(__file__).resolve().parents[1]


class Lab:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        self.registry = self.read("registry.json", {})
        self.settings = self.read("settings.json", {"wallet": "", "control_mode": "copy"})
        self.latest = self.read("latest.json", {})
        self.session = None
        self.account = AccountLink(self.root)
        self.rag = EvidenceStore(self.root/"evidence.sqlite")
        self.readiness = readiness(self.root, self.rag, self.read('dataset.json',None), self.settings)
        self.model_access = None
        self.historical = self.read('historical/latest.json',None)
        self.disagreement = DisagreementStudy(self.root/'disagreement')

    def read(self, filename, default):
        p = self.root/filename
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default

    def save(self, filename, data):
        target = self.root/filename
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, allow_nan=False), encoding="utf-8")
        tmp.replace(target)

    def state(self):
        with self.rag.connect() as db:
            count = db.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
        dataset = self.read("dataset.json", None)
        return {"csrf": self.token, "bots": self.registry, "latest": self.latest, "settings": self.settings,
                "account": self.account.state(),
                "readiness": self.readiness, "model_access": self.model_access,
                "historical": self.historical,
                "disagreement": self.disagreement.state(),
                "session": self.session.state() if self.session else None,
                "evidence_count": count, "cloud_enabled": os.getenv("WEATHERLAB_ENABLE_CLOUD") == "1",
                "dataset": None if dataset is None else {"frames": len(dataset["frames"]), "synthetic": dataset.get("synthetic"), "coverage": dataset.get("coverage"), "errors": dataset.get("errors", [])[-10:]}}

    def mutate(self, path, raw):
        if path == "/api/upload":
            checked = inspect_package(raw, ROOT)
            ident = checked["manifest"]["bot_id"]
            self.registry[ident] = checked
            self.save("registry.json", self.registry)
            return {"message": STRATEGIES[ident]+" loaded; package verified."}
        if path == "/api/dataset":
            data = json.loads(raw)
            if data.get("schema_version") != 1 or data.get("venue") != "polymarket_us" or not isinstance(data.get("frames"), list) or not data["frames"]:
                raise ValueError("Expected a nonempty Weather Lab dataset.json")
            self.save("dataset.json", data)
            return {"message": "Dataset loaded. Its timestamps will govern replay eligibility."}
        if path == "/api/evidence":
            rows = [json.loads(line) for line in raw.decode("utf-8-sig").splitlines() if line.strip()]
            count = self.rag.ingest(rows)
            return {"message": f"Indexed {count} new immutable evidence records."}
        body = json.loads(raw or b"{}")
        if path == '/api/shortcuts/configure':
            if self.disagreement.state()['running']: raise ValueError('Stop the tracker before changing its source folder')
            self.disagreement.shortcuts.configure(body.get('folder',''))
            return {'message':'Synced forecast folder connected. Start the tracker after the iPhone has exported its first file.'}
        if path == '/api/disagreement/start':
            self.disagreement.start(body)
            return {'message':'Forecast/book tracker started. This collects observations; it does not place paper or real orders.'}
        if path == '/api/disagreement/stop':
            self.disagreement.stop.set()
            return {'message':'Tracker stop requested. The bounded in-flight snapshot will finish.'}
        if path == '/api/historical/baseline':
            self.historical = run_month(ROOT/'examples/historical-klax-2026-08',self.root/'historical'/str(uuid.uuid4()),allow_assumed=True)
            self.save('historical/latest.json',self.historical)
            return {'message':'August baseline completed. Exploratory weather accuracy only; archive availability unverified; no trades or cloud calls.'}
        if path == '/api/readiness':
            self.readiness = readiness(self.root,self.rag,self.read('dataset.json',None),self.settings)
            return {'message':'Readiness refreshed. No paid inference was requested.'}
        if path == '/api/models/check':
            self.model_access = check_models()
            return {'message':self.model_access.get('reason',self.model_access.get('note','Model access checked.'))}
        if path == '/api/research/collect':
            report=collect_evidence(self.root/'research'/str(uuid.uuid4()),self.rag)
            self.readiness=readiness(self.root,self.rag,self.read('dataset.json',None),self.settings)
            return {'message':f"Indexed {report['indexed']} public records; {report['history_pairs_created']} completed history pairs. "+report.get('next_step','Inspect collection receipts for source errors.')}
        if path in ('/api/account/connect', '/api/account/refresh'):
            account = self.account.refresh()
            if account['status'] != 'connected':
                raise ValueError(account['error'])
            return {'message': 'Polymarket US account verified. Read-only balances and positions; paper capital is unchanged.'}
        if path == '/api/account/disconnect':
            self.account.disconnect()
            return {'message': 'Dashboard account link removed. Your saved credentials remain unchanged.'}
        if path == '/api/session/stop':
            if self.session:
                self.session.stop.set()
            return {'message':'Stop requested. In-flight calls finish within their timeout; pending paper entries will be cancelled.'}
        if path == '/api/session/start':
            if self.session and (self.session.thread.is_alive() or any(t.is_alive() for t in self.session.workers.values())):
                raise ValueError('A session is already running or stopping')
            if set(self.registry) != set(STRATEGIES):
                raise ValueError('Upload all four bot packages before starting a comparison session')
            configs = {key:copy.deepcopy(row['manifest']['config']) for key,row in self.registry.items()}
            for key, config in configs.items():
                config['reference_wallet'] = self.settings['wallet']
                config['control_mode'] = self.settings['control_mode']
                if key != 'wallet_control':
                    config['risk_profile'] = self.settings.get('risk_profiles',{}).get(key,config.get('risk_profile','balanced'))
            self.session = Session(self.root/'sessions',configs,body.get('mode','demo'),self.rag,
                                   self.root/'model-budget.sqlite',wallet=self.settings['wallet'],
                                   mappings=self.read('reference-mappings.json',[]),duration=int(body.get('duration',3600)))
            self.session.start()
            return {'message':'Four paper strategies started. '+('SYNTHETIC DEMO: accelerated fixtures and test models.' if self.session.mode=='demo' else 'Public data: missing evidence or cloud configuration produces waiting/skip records.')}
        if path == "/api/risk":
            key, profile = body.get("strategy"), body.get("profile")
            if key not in STRATEGIES or key == "wallet_control" or profile not in RISK_PROFILES:
                raise ValueError("Select a valid LLM strategy and risk profile")
            self.settings.setdefault("risk_profiles", {})[key] = profile
            self.save("settings.json", self.settings)
            return {"message": f"{STRATEGIES[key]}: {profile.title()} saved for the next run. Existing results are unchanged."}
        if path == "/api/settings":
            wallet = body.get("wallet", "").strip()
            if wallet and not re.fullmatch(r"0x[0-9a-fA-F]{40}", wallet):
                raise ValueError("Wallet must be a 0x public address with 40 hex characters")
            mode = body.get("control_mode", "copy")
            if mode not in ("copy", "arbitrage"):
                raise ValueError("Unknown control mode")
            self.settings.update({"wallet": wallet.lower(), "control_mode": mode})
            self.save("settings.json", self.settings)
            return {"message": "Settings saved for the next new run."}
        if path == "/api/capture":
            if self.session and self.session.thread.is_alive():
                raise ValueError('Stop the active session before a separate capture')
            ident = "capture-"+str(uuid.uuid4())[:8]
            result = capture(self.root/"captures"/ident, seconds=45, max_markets=4, wallet=self.settings["wallet"], mappings=self.read("reference-mappings.json", []))
            if result["frames"]:
                self.save("dataset.json", result)
            return {"message": f"Captured {len(result['frames'])} frames; {len(result['errors'])} source/coverage notices. Inspect coverage below.", "coverage": result["coverage"]}
        if path == "/api/run":
            if self.session and self.session.thread.is_alive():
                raise ValueError('Stop the active session before a separate replay')
            if not self.registry:
                raise ValueError("Upload at least one bot ZIP first")
            source = body.get("source", "sample")
            if source not in ("sample", "recorded", "cloud"):
                raise ValueError("Unknown inference/data mode")
            if source == "sample":
                dataset, history = sample()
                store = EvidenceStore(self.root/"sample-evidence.sqlite")
                store.ingest(history)
            else:
                dataset = self.read("dataset.json", None)
                if not dataset or not dataset.get("frames"):
                    raise ValueError("Upload or capture a dataset first")
                store = self.rag
            ident = str(uuid.uuid4())[:12]
            results = {}
            for key in STRATEGIES:
                if key not in self.registry:
                    continue
                config = dict(self.registry[key]["manifest"]["config"])
                config["reference_wallet"] = WALLET if source == "sample" else self.settings["wallet"]
                config["control_mode"] = self.settings["control_mode"]
                if key != "wallet_control":
                    config["risk_profile"] = self.settings.get("risk_profiles", {}).get(key, config.get("risk_profile", "balanced"))
                result = replay(config, dataset, self.root/"runs"/ident/key, cloud=source == "cloud" and key != "wallet_control", rag=store,
                                budget_path=self.root/"model-budget.sqlite")
                result["run_id"] = ident
                results[key] = result
            self.latest = results
            self.save("latest.json", results)
            return {"message": "Replay completed. "+("SYNTHETIC TEST DATA — no cloud inference or performance evidence." if source == "sample" else "Inspect coverage, inference labels and skipped decisions.")}
        raise ValueError("Unknown operation")


def serve(port=8766):
    lab = Lab(Path.cwd()/"data")
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def reply(self, status, data, content="application/json"):
            if not isinstance(data, bytes):
                data = json.dumps(data, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", content)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data: https://weatherkit.apple.com; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(data)

        def valid_host(self):
            return self.headers.get("Host") in (f"127.0.0.1:{port}", f"localhost:{port}")

        def do_GET(self):
            if not self.valid_host():
                self.reply(403, {"error": "Loopback host required"})
                return
            if self.path == "/api/state":
                self.reply(200, lab.state())
            elif self.path == "/api/export":
                self.reply(200, lab.session.state()['results'] if lab.session else lab.latest)
            elif self.path in ("/", "/app.js", "/style.css"):
                name = "index.html" if self.path == "/" else self.path[1:]
                ctype = {"index.html": "text/html; charset=utf-8", "app.js": "text/javascript; charset=utf-8", "style.css": "text/css; charset=utf-8"}[name]
                self.reply(200, (ROOT/"web"/name).read_bytes(), ctype)
            else:
                self.reply(404, {"error": "Not found"})

        def do_POST(self):
            if not self.valid_host() or self.headers.get("X-WeatherLab-CSRF") != lab.token:
                self.reply(403, {"error": "Invalid local session token"})
                return
            origin = self.headers.get("Origin")
            if origin and origin not in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
                self.reply(403, {"error": "Cross-origin request rejected"})
                return
            if not lab.lock.acquire(blocking=False):
                self.reply(409, {"error": "Another operation is running"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 8000000:
                    raise ValueError("Request must be 1 byte to 8 MB")
                self.connection.settimeout(20)
                raw = self.rfile.read(length)
                self.reply(200, lab.mutate(self.path, raw))
            except Exception as exc:
                self.reply(400, {"error": type(exc).__name__+": "+str(exc)[:300]})
            finally:
                lab.lock.release()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Weather Lab: http://127.0.0.1:{port} (paper only)", flush=True)
    server.serve_forever()
