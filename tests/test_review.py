import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from effect_ledger import Ledger
from effect_ledger.ledger import LedgerError, ValidationError
from effect_ledger.review import review


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "ledger.sqlite"
        self.ledger = Ledger(self.db)

    def tearDown(self):
        self.temp.cleanup()

    def add(self, scope, op, state):
        if state == "succeeded":
            self.ledger.execute(scope, op, "tool", {"secret_argument": "private"}, lambda: {"receipt": "private"})
        else:
            with sqlite3.connect(self.db) as db:
                db.execute("INSERT INTO operations(scope,operation_id,tool,arguments_sha256,state) VALUES(?,?,?,'hash',?)", (scope, op, "tool", state))

    def test_missing_path_and_parent_are_not_created(self):
        missing = self.root / "absent.sqlite"
        with self.assertRaises(LedgerError): review(missing)
        self.assertFalse(missing.exists())
        parent_db = self.root / "absent-parent" / "db.sqlite"
        with self.assertRaises(LedgerError): review(parent_db)
        self.assertFalse(parent_db.parent.exists())

    def test_review_does_not_initialize_schema(self):
        blank = self.root / "blank.sqlite"
        sqlite3.connect(blank).close()
        with self.assertRaises(LedgerError): review(blank)
        with sqlite3.connect(blank) as db:
            self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(), [])

    def test_review_does_not_mutate_operation_rows(self):
        self.add("scope", "pending", "pending")
        before = sqlite3.connect(self.db).execute("SELECT * FROM operations").fetchall()
        review(self.db)
        after = sqlite3.connect(self.db).execute("SELECT * FROM operations").fetchall()
        self.assertEqual(before, after)

    def test_pending_and_uncertain_have_distinct_conservative_notes(self):
        self.add("s", "a", "pending")
        self.add("s", "b", "uncertain")
        got = review(self.db)["operations"]
        self.assertEqual([x["state"] for x in got], ["pending", "uncertain"])
        self.assertEqual(got[0]["blocking_reason"], "may_still_be_running_or_process_died")
        self.assertEqual(got[1]["blocking_reason"], "action_may_have_completed")
        self.assertTrue(all(x["next_step"] == "inspect_authoritative_outcome_no_auto_retry" for x in got))

    def test_age_fields_mark_old_unresolved_work_without_mutating_it(self):
        self.add("s", "old", "pending")
        self.add("s", "recent", "uncertain")
        now = datetime.now(timezone.utc).replace(microsecond=0)
        old = (now - timedelta(hours=73)).strftime("%Y-%m-%d %H:%M:%S")
        recent = (now - timedelta(hours=71)).strftime("%Y-%m-%d %H:%M:%S")
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE operations SET created_at=? WHERE operation_id='old'", (old,))
            db.execute("UPDATE operations SET created_at=? WHERE operation_id='recent'", (recent,))
        before = sqlite3.connect(self.db).execute("SELECT operation_id,created_at FROM operations ORDER BY operation_id").fetchall()
        rows = {row["operation_id"]: row for row in review(self.db)["operations"]}
        after = sqlite3.connect(self.db).execute("SELECT operation_id,created_at FROM operations ORDER BY operation_id").fetchall()
        self.assertEqual(before, after)
        self.assertEqual(rows["old"]["age_hours"], 73)
        self.assertTrue(rows["old"]["older_than_72_hours"])
        self.assertEqual(rows["recent"]["age_hours"], 71)
        self.assertFalse(rows["recent"]["older_than_72_hours"])
        self.assertEqual(rows["old"]["next_step"], "inspect_authoritative_outcome_no_auto_retry")

    def test_succeeded_excluded(self):
        self.add("s", "success", "succeeded")
        self.assertEqual(review(self.db)["operations"], [])

    def test_scope_filter(self):
        self.add("alpha", "x", "pending")
        self.add("beta", "y", "pending")
        self.assertEqual([r["scope"] for r in review(self.db, scope="beta")["operations"]], ["beta"])

    def test_pagination_and_order(self):
        for op in ("z", "b", "a"):
            self.add("scope", op, "pending")
        result = review(self.db, limit=2)
        self.assertEqual([r["operation_id"] for r in result["operations"]], ["a", "b"])
        self.assertTrue(result["truncated"])

    def test_limit_rejects_bool_zero_and_infinite_values(self):
        for limit in (True, False, 0, float("inf"), "2", 1001):
            with self.subTest(limit=limit), self.assertRaises(ValidationError): review(self.db, limit=limit)

    def test_malformed_database_safe_error(self):
        bad = self.root / "bad.sqlite"
        bad.write_bytes(b"not a database private sentinel")
        with self.assertRaises(LedgerError) as err: review(bad)
        self.assertNotIn("private sentinel", str(err.exception))

    def test_missing_operations_schema_safe_error(self):
        blank = self.root / "no-operations.sqlite"
        sqlite3.connect(blank).execute("CREATE TABLE other(x)").connection.close()
        with self.assertRaises(LedgerError): review(blank)

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'POSIX FIFO required')
    def test_named_pipe_rejected_before_sqlite_open(self):
        pipe = self.root / 'pipe.sqlite'
        os.mkfifo(pipe)
        with self.assertRaises(LedgerError): review(pipe)

    @unittest.skipUnless(hasattr(os, 'symlink'), 'symlink support required')
    def test_symlink_loop_fails_without_traceback(self):
        loop = self.root / 'loop.sqlite'
        loop.symlink_to(loop)
        with self.assertRaises(LedgerError): review(loop)

    def test_invalid_timestamps_are_not_reported_as_metadata(self):
        self.add('s', 'o', 'uncertain')
        for value in ('private timestamp payload', '2026-02-30 00:00:00', '2026-01-01\n00:00:00'):
            with sqlite3.connect(self.db) as db:
                db.execute('UPDATE operations SET updated_at=?', (value,))
            with self.subTest(value=value), self.assertRaises(LedgerError) as err:
                review(self.db)
            self.assertEqual(str(err.exception), 'unable to review ledger')

    def test_uri_encoded_path(self):
        odd = self.root / "space %?# name.sqlite"
        Ledger(odd).execute("s", "o", "t", {}, lambda: {})
        self.assertEqual(len(review(odd)["operations"]), 0)

    def test_uncheckpointed_wal_is_visible(self):
        waldb = self.root / "wal.sqlite"
        Ledger(waldb)
        with sqlite3.connect(waldb) as db:
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            db.execute("PRAGMA wal_autocheckpoint=0")
            db.execute("INSERT INTO operations(scope,operation_id,tool,arguments_sha256,state) VALUES('s','pending','t','hash','pending')")
        self.assertTrue(Path(str(waldb) + "-wal").exists())
        self.assertEqual([x["operation_id"] for x in review(waldb)["operations"]], ["pending"])

    def test_cli_redacts_payload_hash_and_private_errors(self):
        self.add("scope", "operation", "uncertain")
        self.add("scope", "done", "succeeded")
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE operations SET arguments_sha256=?", ("secret_hash",))
        env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
        p = subprocess.run([sys.executable, "-m", "effect_ledger", "review", "--db", str(self.db)], capture_output=True, text=True, env=env)
        self.assertEqual(p.returncode, 0)
        self.assertNotIn("secret_hash", p.stdout); self.assertNotIn("private_receipt", p.stdout); self.assertNotIn("private", p.stdout)
        bad = subprocess.run([sys.executable, "-m", "effect_ledger", "review", "--db", str(self.root / "missing")], capture_output=True, text=True, env=env)
        self.assertEqual(bad.returncode, 1); self.assertNotIn("Traceback", bad.stderr)

    def test_cli_invalid_arguments_exit_two(self):
        env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
        for args in (("--limit", "0"), ("--limit", "1001"), ("--scope", "bad scope")):
            p = subprocess.run([sys.executable, "-m", "effect_ledger", "review", "--db", str(self.db), *args], capture_output=True, text=True, env=env)
            self.assertEqual(p.returncode, 2)
            self.assertLess(len(p.stderr), 500)


if __name__ == "__main__": unittest.main()
