import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from effect_ledger import (ConflictError, EffectFailed, Ledger, LedgerError, OperationBlocked, ValidationError)

class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.temp.name) / "ledger.sqlite")
        self.ledger = Ledger(self.db)
    def tearDown(self): self.temp.cleanup()
    def runop(self, **kw):
        args = dict(scope="scope", operation_id="op", tool="tool", arguments={"x": 1}, callback=lambda: {"ok": True})
        args.update(kw)
        return self.ledger.execute(**args)

    def test_initial_exec_and_cache(self):
        calls=[]
        a=self.runop(callback=lambda: calls.append(1) or {"ok":True})
        b=self.runop(callback=lambda: calls.append(2) or {"bad":True})
        self.assertEqual((a.receipt,a.cached), ({"ok":True},False)); self.assertEqual((b.receipt,b.cached), ({"ok":True},True)); self.assertEqual(len(calls),1)
    def test_canonical_key_order_reuses_cache(self):
        calls=[]
        self.ledger.execute("s","p","t",{"a":1,"b":{"x":2,"y":3}},lambda:calls.append(1) or {"ok":True})
        result=self.ledger.execute("s","p","t",{"b":{"y":3,"x":2},"a":1},lambda:calls.append(2))
        self.assertTrue(result.cached); self.assertEqual(calls,[1])
    def test_cache_after_new_ledger(self):
        self.runop(); other=Ledger(self.db); r=other.execute("scope","op","tool",{"x":1},lambda:self.fail())
        self.assertTrue(r.cached)
    def test_changed_arguments_conflict(self):
        self.runop()
        with self.assertRaises(ConflictError): self.runop(arguments={"x":2})
    def test_changed_tool_conflict(self):
        self.runop()
        with self.assertRaises(ConflictError): self.runop(tool="other")
    def test_same_args_distinct_ids_execute(self):
        calls=[]
        for op in ("a","b"): self.runop(operation_id=op,callback=lambda:calls.append(1) or {})
        self.assertEqual(len(calls),2)
    def test_scope_is_identity_namespace(self):
        self.runop(); r=self.runop(scope="other",callback=lambda:{"new":1}); self.assertFalse(r.cached)
    def test_pending_blocks_replay(self):
        def die(): raise RuntimeError("secret payload must not escape")
        with self.assertRaises(EffectFailed): self.runop(callback=die)
        self.assertEqual(self.ledger.inspect()[0]["state"],"uncertain")
        with self.assertRaises(OperationBlocked): self.runop(callback=lambda:self.fail())
    def test_pending_different_arguments_conflict(self):
        with self.assertRaises(EffectFailed): self.ledger.execute("s","p","t",{"x":1},lambda: (_ for _ in ()).throw(RuntimeError("private")))
        with self.assertRaises(ConflictError): self.ledger.execute("s","p","t",{"x":2},lambda:self.fail())
    def test_timeout_is_uncertain_and_safe(self):
        with self.assertRaises(EffectFailed) as e: self.runop(callback=lambda: (_ for _ in ()).throw(TimeoutError("private")))
        self.assertNotIn("private",str(e.exception))
        with self.assertRaises(OperationBlocked): self.runop()
    def test_nonfinite_rejected_before_effect(self):
        called=[]
        with self.assertRaises(ValidationError): self.runop(arguments={"x":float("nan")},callback=lambda:called.append(1))
        self.assertFalse(called)
    def test_nonstring_dict_key_rejected_before_effect(self):
        called=[]
        with self.assertRaises(ValidationError): self.runop(arguments={1:"one"},callback=lambda:called.append(1))
        self.assertFalse(called)
    def test_tuple_rejected_before_effect(self):
        with self.assertRaises(ValidationError): self.runop(arguments={"x":(1,2)})
    def test_deep_json_rejected(self):
        value=0
        for _ in range(66): value=[value]
        with self.assertRaises(ValidationError): self.runop(arguments=value)
    def test_invalid_identifier(self):
        for value in ("", "x y", "-bad", "a"*129, None):
            with self.subTest(value=value), self.assertRaises(ValidationError): self.runop(scope=value)
    def test_callback_required(self):
        with self.assertRaises(ValidationError): self.runop(callback=None)
    def test_invalid_receipt_uncertain(self):
        with self.assertRaises(EffectFailed): self.runop(callback=lambda: object())
        self.assertEqual(self.ledger.inspect()[0]["state"],"uncertain")
    def test_oversize_receipt_uncertain(self):
        with self.assertRaises(EffectFailed): self.runop(callback=lambda:"x"*65000)
        self.assertEqual(self.ledger.inspect()[0]["state"],"uncertain")
    def test_inspect_metadata_only(self):
        self.ledger.execute("s","p","t",{"SECRET_ARGUMENT":"abc"},lambda:{"SECRET_RECEIPT":"xyz"})
        rendered=json.dumps(self.ledger.inspect())
        self.assertNotIn("SECRET",rendered); self.assertNotIn("xyz",rendered); self.assertNotIn("abc",rendered)
    def test_memory_and_uri_databases_rejected(self):
        for path in (":memory:", "file::memory:?cache=shared", "file:db?mode=memory", ""):
            with self.subTest(path=path), self.assertRaises(ValidationError): Ledger(path)
    def test_database_parent_not_created(self):
        with self.assertRaises(ValidationError): Ledger(Path(self.temp.name)/"missing"/"db.sqlite")
    def test_corrupt_database_safe_errors(self):
        p=Path(self.temp.name)/"corrupt.sqlite"; p.write_bytes(b"not a sqlite database")
        err=subprocess.run([sys.executable,"-m","effect_ledger","inspect","--db",str(p)],capture_output=True,text=True,env={**os.environ,"PYTHONPATH":str(Path(__file__).resolve().parents[1])})
        self.assertEqual(err.returncode,1); self.assertNotIn("Traceback",err.stderr); self.assertNotIn("not a sqlite",err.stderr)
        with self.assertRaises(LedgerError): Ledger(p)
    def test_concurrent_claim_single_callback(self):
        other=Ledger(self.db); started=threading.Event(); release=threading.Event(); second_started=threading.Event(); loser_done=threading.Event(); results=[]; errors=[]
        def cb():
            started.set()
            if not release.wait(5): raise RuntimeError("test timeout")
            return {"done":True}
        def first():
            try: results.append(self.ledger.execute("s","same","tool",{"x":1},cb))
            except Exception as e: errors.append(e)
        def second():
            second_started.set()
            try: other.execute("s","same","tool",{"x":1},cb)
            except OperationBlocked: pass
            except Exception as e: errors.append(e)
            finally: loser_done.set()
        t1=threading.Thread(target=first); t1.start(); self.assertTrue(started.wait(3))
        t2=threading.Thread(target=second); t2.start(); self.assertTrue(second_started.wait(3))
        self.assertTrue(loser_done.wait(3)); self.assertTrue(t1.is_alive())
        release.set(); t1.join(5); t2.join(5)
        self.assertFalse(t1.is_alive() or t2.is_alive()); self.assertFalse(errors)
        cached=other.execute("s","same","tool",{"x":1},cb)
        self.assertEqual(len(results),1); self.assertFalse(results[0].cached); self.assertTrue(cached.cached)
    def test_cli_exception_window_blocks_retry_and_has_one_effect(self):
        env={**os.environ,"PYTHONPATH":str(Path(__file__).resolve().parents[1])}
        p=subprocess.run([sys.executable,"-m","effect_ledger","demo","--db",self.db,"--crash-after-effect"],capture_output=True,text=True,env=env)
        self.assertEqual(p.returncode,2); self.assertNotIn("synthetic local effect",p.stdout+p.stderr)
        self.assertEqual(self.ledger.inspect()[0]["state"],"uncertain")
        with sqlite3_connect(self.db) as db: self.assertEqual(db.execute("SELECT COUNT(*) FROM demo_outbox").fetchone()[0],1)
        retry=subprocess.run([sys.executable,"-m","effect_ledger","demo","--db",self.db],capture_output=True,text=True,env=env)
        self.assertEqual(retry.returncode,2); self.assertEqual(self.outbox_count(),1)
    def test_actual_subprocess_exit_after_nonidempotent_effect(self):
        env={**os.environ,"PYTHONPATH":str(Path(__file__).resolve().parents[1])}
        code='''import os,sqlite3\nfrom effect_ledger import Ledger\np=os.environ["LEDGER_DB"]\nwith sqlite3.connect(p) as d: d.execute("CREATE TABLE IF NOT EXISTS demo_outbox(id INTEGER PRIMARY KEY, operation_id TEXT NOT NULL, message TEXT NOT NULL)")\ndef effect():\n with sqlite3.connect(p) as d: d.execute("INSERT INTO demo_outbox(operation_id,message) VALUES(?,?)",("op","effect"))\n os._exit(73)\nLedger(p).execute("s","op","t",{"x":1},effect)\n'''
        env["LEDGER_DB"]=self.db
        p=subprocess.run([sys.executable,"-c",code],env=env,capture_output=True)
        self.assertEqual(p.returncode,73)
        self.assertEqual(self.outbox_count(),1)
        self.assertEqual(self.ledger.inspect()[0]["state"],"pending")
        with self.assertRaises(ConflictError): self.ledger.execute("s","op","t",{"x":2},lambda:self.fail())
        with self.assertRaises(OperationBlocked): self.ledger.execute("s","op","t",{"x":1},lambda:self.fail())
        self.assertEqual(self.outbox_count(),1)
    def test_independent_process_persistence(self):
        self.runop()
        env={**os.environ,"PYTHONPATH":str(Path(__file__).resolve().parents[1])}
        code='from effect_ledger import Ledger; print(Ledger(%r).execute("scope","op","tool",{"x":1},lambda: (_ for _ in ()).throw(RuntimeError())).cached)'%self.db
        p=subprocess.run([sys.executable,"-c",code],capture_output=True,text=True,env=env)
        self.assertEqual(p.returncode,0,p.stderr); self.assertEqual(p.stdout.strip(),"True")
    def test_cli_normal_demo_cache(self):
        p=subprocess.run([sys.executable,"-m","effect_ledger","demo","--db",self.db],capture_output=True,text=True,env={**os.environ,"PYTHONPATH":str(Path(__file__).resolve().parents[1])})
        self.assertEqual(p.returncode,0,p.stderr); self.assertTrue(json.loads(p.stdout)["second_cached"]); self.assertEqual(json.loads(p.stdout)["outbox_rows"],1)
    def test_cli_inspect_payload_safe(self):
        self.ledger.execute("s","p","t",{"secret":"arg"},lambda:{"secret":"receipt"})
        p=subprocess.run([sys.executable,"-m","effect_ledger","inspect","--db",self.db],capture_output=True,text=True,env={**os.environ,"PYTHONPATH":str(Path(__file__).resolve().parents[1])})
        self.assertEqual(p.returncode,0); self.assertNotIn("receipt",p.stdout); self.assertNotIn("arg",p.stdout)
    def outbox_count(self):
        with sqlite3_connect(self.db) as db: return db.execute("SELECT COUNT(*) FROM demo_outbox").fetchone()[0]

def sqlite3_connect(path):
    import sqlite3
    return sqlite3.connect(path)

if __name__ == "__main__": unittest.main()
