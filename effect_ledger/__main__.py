import argparse
import json
import sqlite3
import sys
from contextlib import closing

from .ledger import EffectFailed, Ledger, LedgerError, OperationBlocked

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_BLOCKED = 2

def demo(dbpath: str, crash_after_effect: bool) -> int:
    """Run local demo; --crash-after-effect simulates an exception window, not process death."""
    ledger = Ledger(dbpath)
    with closing(sqlite3.connect(dbpath)) as db:
        db.execute("CREATE TABLE IF NOT EXISTS demo_outbox (id INTEGER PRIMARY KEY, operation_id TEXT NOT NULL, message TEXT NOT NULL)")
    def fake_effect():
        with closing(sqlite3.connect(dbpath)) as db:
            db.execute("INSERT INTO demo_outbox(operation_id,message) VALUES(?,?)", ("demo-operation", "synthetic local effect"))
            db.commit()
        if crash_after_effect:
            raise RuntimeError("simulated exception window")
        return {"status": "inserted", "operation_id": "demo-operation"}
    try:
        first = ledger.execute("demo", "demo-operation", "synthetic.outbox", {"message": "synthetic local effect"}, fake_effect)
        second = ledger.execute("demo", "demo-operation", "synthetic.outbox", {"message": "synthetic local effect"}, fake_effect)
        print(json.dumps({"first_cached": first.cached, "second_cached": second.cached, "outbox_rows": _outbox_count(dbpath)}, sort_keys=True))
        return EXIT_OK
    except OperationBlocked:
        print("operation blocked; no automatic replay", file=sys.stderr)
        return EXIT_BLOCKED
    except EffectFailed:
        print("operation uncertain; no automatic replay", file=sys.stderr)
        return EXIT_BLOCKED
    except LedgerError:
        print("ledger operation failed safely", file=sys.stderr)
        return EXIT_ERROR

def _outbox_count(path: str) -> int:
    with closing(sqlite3.connect(path)) as db:
        return db.execute("SELECT COUNT(*) FROM demo_outbox").fetchone()[0]

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="effect_ledger")
    subs = parser.add_subparsers(dest="command", required=True)
    d = subs.add_parser("demo", help="run synthetic local outbox demonstration")
    d.add_argument("--db", required=True)
    d.add_argument("--crash-after-effect", action="store_true", help="simulate exception after effect (not process death)")
    i = subs.add_parser("inspect", help="print operation metadata without payloads")
    i.add_argument("--db", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            return demo(args.db, args.crash_after_effect)
        print(json.dumps(Ledger(args.db).inspect(), sort_keys=True))
        return EXIT_OK
    except LedgerError:
        print("ledger command failed safely", file=sys.stderr)
        return EXIT_ERROR

if __name__ == "__main__":
    raise SystemExit(main())
