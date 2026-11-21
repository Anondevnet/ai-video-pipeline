#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from aiinf import pipeline, state as st, smoke


def main():
    p = argparse.ArgumentParser(prog="ai-influencer-run")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    plan = sub.add_parser("plan"); plan.add_argument("--lane", default="both")
    run = sub.add_parser("run")
    run.add_argument("--mock", action="store_true")
    run.add_argument("--live", action="store_true")
    run.add_argument("--lane", default="both")
    run.add_argument("--concept-limit", type=int, default=None,
                     help="process at most N concepts; live mode defaults to 1")
    smoke_cmd = sub.add_parser(
        "live-smoke-test",
        help="inspect/validate config and preview the request; with --confirm-live, "
             "make EXACTLY ONE paid Kling create request, download and validate it")
    smoke_cmd.add_argument("--confirm-live", action="store_true",
                           help="actually issue the single paid request")
    args = p.parse_args()

    if args.cmd == "status":
        s = st.load_state()
        print(f"last_stage={s['last_stage']} updated={s['updated_at']}")
        for cid, rec in s["concepts"].items():
            print(f"  {cid}: {rec['last_stage']} errors={len(rec.get('errors', []))}")
    elif args.cmd == "plan":
        from aiinf.planner import plan_concepts
        for c in plan_concepts(lane=args.lane):
            print(f"{c.id} [{c.lane}] {c.title} errors={c.validate()}")
    elif args.cmd == "run":
        res = pipeline.run_pipeline(lane=args.lane, mock=args.mock, live=args.live,
                                    concept_limit=args.concept_limit)
        for r in res["results"]:
            print(r)
        failed = [r for r in res["results"] if r.get("status") not in ("ok", "validation_failed")]
        if failed:
            return 1
    elif args.cmd == "live-smoke-test":
        from aiinf import kling as kling_mod
        if args.confirm_live:
            print(smoke.CONFIRMATION, flush=True)
            print(f"   endpoint: {kling_mod.CREATE_ENDPOINT}", flush=True)
        try:
            report = smoke.run_smoke_test(confirm=args.confirm_live)
        except kling_mod.KlingError as exc:
            print(f"SMOKE TEST FAILED: {exc}")
            return 1
        for key in ("mode", "concept_id", "character", "create_url", "max_create_requests", "config", "character_reference"):
            if key in report:
                print(f"{key}: {report[key]}")
        if report.get("note"):
            print(f"note: {report['note']}")
        if str(report.get("mode", "")).startswith("dry-run"):
            print("\nrequest body that WOULD be sent:")
            print(json.dumps(report["request_body"], indent=2))
            print("\nNo Kling request was made. Re-run with --confirm-live to issue one.")
            return 0
        print(f"task_id: {report.get('task_id')}")
        print(f"create_requests: {report.get('create_requests')}")
        print(f"artifact: {report.get('artifact')} ({report.get('bytes')} bytes)")
        print(f"validation_findings: {report.get('validation_findings')}")
        print("\nSmoke test complete. Stopping without rendering or exporting.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
