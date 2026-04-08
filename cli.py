# TheSNMC RustDB command-line interface
from __future__ import annotations

import argparse
import json
import sqlite3

from decaydb.engine import DecayEngine
from decaydb.models import bootstrap


def get_engine(db_path: str) -> DecayEngine:
    conn = sqlite3.connect(db_path)
    bootstrap(conn)
    return DecayEngine(conn)


def main() -> None:
    parser = argparse.ArgumentParser(description="TheSNMC RustDB CLI")
    parser.add_argument("--db", default="decay.db", help="SQLite db path")
    parser.add_argument("--tenant", default="default", help="Tenant id")
    sub = parser.add_subparsers(dest="cmd", required=True)

    seed = sub.add_parser("seed")
    seed.add_argument("--policy-name", default="cli_log")
    seed.add_argument("--payload", default="cli seeded detailed payload with many words to summarize later")

    tick = sub.add_parser("tick")
    tick.add_argument("--shadow-mode", action="store_true")

    state = sub.add_parser("state")
    state.add_argument("--id", type=int, required=True)

    sub.add_parser("metrics")
    sub.add_parser("list")

    ctrl = sub.add_parser("control")
    ctrl.add_argument("--id", type=int, required=True)
    ctrl.add_argument("--legal-hold", choices=["0", "1"])
    ctrl.add_argument("--do-not-decay", choices=["0", "1"])

    restore = sub.add_parser("restore")
    restore.add_argument("--id", type=int, required=True)

    args = parser.parse_args()
    engine = get_engine(args.db)

    if args.cmd == "seed":
        pid = engine.upsert_policy(
            args.tenant,
            args.policy_name,
            {
                "record_type": "log",
                "stage_one_after_sec": 10,
                "stage_two_after_sec": 20,
                "delete_after_sec": 30,
            },
        )
        oid = engine.create_object(args.tenant, "log", args.payload, pid)
        print(json.dumps({"policy_id": pid, "object_id": oid}))
        return

    if args.cmd == "tick":
        changed = engine.decay_tick(args.tenant, shadow_mode=args.shadow_mode)
        print(json.dumps({"changed": changed, "shadow_mode": args.shadow_mode}))
        return

    if args.cmd == "state":
        print(json.dumps(engine.get_state(args.tenant, args.id), indent=2))
        return

    if args.cmd == "metrics":
        print(json.dumps(engine.metrics_summary(args.tenant), indent=2))
        return

    if args.cmd == "list":
        rows = engine.list_objects(args.tenant)
        print(
            json.dumps(
                [
                    {
                        "id": int(r["id"]),
                        "record_type": r["record_type"],
                        "deleted": bool(r["deleted"]),
                        "stage": int(r["current_stage"]),
                    }
                    for r in rows
                ],
                indent=2,
            )
        )
        return

    if args.cmd == "control":
        legal_hold = None if args.legal_hold is None else args.legal_hold == "1"
        do_not_decay = None if args.do_not_decay is None else args.do_not_decay == "1"
        ok = engine.set_object_controls(args.tenant, args.id, legal_hold=legal_hold, do_not_decay=do_not_decay)
        print(json.dumps({"updated": ok}))
        return

    if args.cmd == "restore":
        ok = engine.restore_object(args.tenant, args.id)
        print(json.dumps({"restored": ok}))
        return


if __name__ == "__main__":
    main()

