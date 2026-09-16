import argparse
import json
import uuid
from pathlib import Path
from .fixtures import sample, config, WALLET
from .engine import replay
from .models import load_env
from .rag import EvidenceStore
from .strategies import STRATEGIES


def main():
    p = argparse.ArgumentParser(description="Weather Lab: isolated Polymarket US paper research")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("serve").add_argument("--port", type=int, default=8766)
    doctor=sub.add_parser('doctor')
    doctor.add_argument('--check-models',action='store_true')
    collect=sub.add_parser('collect-evidence')
    collect.add_argument('--out',required=True)
    collect.add_argument('--db',default='data/evidence.sqlite')
    recon=sub.add_parser('reconcile')
    recon.add_argument('--run',required=True)
    recon.add_argument('--out',required=True)
    pairs=sub.add_parser('pair-history')
    pairs.add_argument('--archive',required=True)
    pairs.add_argument('--outcomes',required=True)
    pairs.add_argument('--out',required=True)
    pairs.add_argument('--db',default='data/evidence.sqlite')
    outcome=sub.add_parser('record-outcome')
    for field in ('url','station','date','review-note','out'): outcome.add_argument('--'+field,required=True)
    outcome.add_argument('--high',required=True,type=int)
    demo = sub.add_parser("demo")
    demo.add_argument("--strategy", choices=STRATEGIES)
    demo.add_argument("--out", default="runs")
    run = sub.add_parser("replay")
    run.add_argument("--dataset", required=True)
    run.add_argument("--config", default="manifest.json")
    run.add_argument("--out", required=True)
    run.add_argument("--rag", default="data/evidence.sqlite")
    run.add_argument("--cloud", action="store_true")
    run.add_argument("--control-mode", choices=("copy", "arbitrage"))
    run.add_argument("--wallet")
    ingest = sub.add_parser("ingest")
    ingest.add_argument("--jsonl", required=True)
    ingest.add_argument("--db", default="data/evidence.sqlite")
    cap = sub.add_parser("capture")
    cap.add_argument("--out", required=True)
    cap.add_argument("--seconds", type=int, default=30)
    cap.add_argument("--max-markets", type=int, default=4)
    cap.add_argument("--wallet", default="")
    cap.add_argument("--mappings")
    cap.add_argument('--selection',choices=('future_day','all_dates'),default='future_day')
    args = p.parse_args()
    load_env(Path.cwd()/".env")
    if args.cmd == 'doctor':
        from .readiness import readiness, check_models
        report=readiness(Path('data'),EvidenceStore('data/evidence.sqlite'))
        if args.check_models: report['model_access']=check_models()
        print(json.dumps(report,indent=2))
    elif args.cmd == 'collect-evidence':
        from .research import collect_evidence
        print(json.dumps(collect_evidence(args.out,EvidenceStore(args.db)),indent=2))
    elif args.cmd == 'record-outcome':
        from .research import record_outcome
        print(json.dumps(record_outcome(args.url,args.station,args.date,args.high,args.review_note,args.out),indent=2))
    elif args.cmd == 'pair-history':
        from .research import pair_history
        print(json.dumps(pair_history(args.archive,args.outcomes,args.out,EvidenceStore(args.db)),indent=2))
    elif args.cmd == 'reconcile':
        from .research import reconcile
        report=reconcile(args.run,args.out)
        print(json.dumps({k:v for k,v in report.items() if k!='account'},indent=2))
    elif args.cmd == "serve":
        from .server import serve
        serve(args.port)
    elif args.cmd == "demo":
        c = config(args.strategy) if args.strategy else json.loads(Path("manifest.json").read_text())["config"]
        c["reference_wallet"] = WALLET
        c.pop('research_protocol', None)
        dataset, _ = sample()
        result = replay(c, dataset, Path(args.out)/(c["strategy"]+"-"+str(uuid.uuid4())[:8]))
        print(json.dumps({k: result[k] for k in ("strategy", "status", "synthetic", "inference", "fills", "realized_pnl", "net_after_costs")}, indent=2))
    elif args.cmd == "replay":
        c = json.loads(Path(args.config).read_text())
        c = c.get("config", c)
        if args.control_mode:
            c["control_mode"] = args.control_mode
        if args.wallet:
            c["reference_wallet"] = args.wallet
        result = replay(c, json.loads(Path(args.dataset).read_text()), args.out, cloud=args.cloud,
                        rag=EvidenceStore(args.rag), budget_path=Path("data/model-budget.sqlite"))
        print(json.dumps({k: result[k] for k in ("strategy", "status", "error", "fills", "realized_pnl", "net_after_costs")}, indent=2))
        if result["status"] != "completed":
            raise SystemExit(1)
    elif args.cmd == "ingest":
        rows = [json.loads(line) for line in Path(args.jsonl).read_text(encoding="utf-8-sig").splitlines() if line.strip()]
        print(json.dumps({"ingested": EvidenceStore(args.db).ingest(rows)}))
    elif args.cmd == "capture":
        from .sources import capture
        mappings = json.loads(Path(args.mappings).read_text()) if args.mappings else []
        result = capture(args.out, args.seconds, args.max_markets, args.wallet, mappings, selection_policy=args.selection)
        print(json.dumps({"frames": len(result["frames"]), "coverage": result["coverage"], "errors": result["errors"]}, indent=2))


if __name__ == "__main__":
    main()
