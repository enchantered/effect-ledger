import argparse
import json
import sqlite3
import sys
from contextlib import closing

from .ledger import EffectFailed, IDENTIFIER, Ledger, LedgerError, OperationBlocked
from .review import DEFAULT_LIMIT, MAX_LIMIT, review

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_BLOCKED = 2

def _limit_argument(value: str) -> int:
    try:
        limit = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("limit must be an integer from 1 to 1000") from None
    if not 1 <= limit <= MAX_LIMIT:
        raise argparse.ArgumentTypeError("limit must be an integer from 1 to 1000")
    return limit

def _scope_argument(value: str) -> str:
    if not IDENTIFIER.fullmatch(value):
        raise argparse.ArgumentTypeError("invalid scope")
    return value

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
    r = subs.add_parser("review", help="read-only review of pending and uncertain operations")
    r.add_argument("--db", required=True)
    r.add_argument("--limit", type=_limit_argument, default=DEFAULT_LIMIT,
                   help="maximum rows, 1–1000 (default: 100)")
    r.add_argument("--scope", type=_scope_argument)
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            return demo(args.db, args.crash_after_effect)
        if args.command == "review":
            print(json.dumps(review(args.db, args.limit, args.scope), sort_keys=True))
            return EXIT_OK
        print(json.dumps(Ledger(args.db).inspect(), sort_keys=True))
        return EXIT_OK
    except LedgerError:
        print("ledger command failed safely", file=sys.stderr)
        return EXIT_ERROR

if __name__ == "__main__":
    raise SystemExit(main())
