"""Durable idempotency guard for side-effect callbacks; it cannot make effects transactional."""
from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
MAX_ARGUMENT_BYTES = 1_000_000
MAX_RECEIPT_BYTES = 64_000

class LedgerError(Exception):
    """Base class for safe, payload-free ledger errors."""
class ValidationError(LedgerError): pass
class ConflictError(LedgerError): pass
class OperationBlocked(LedgerError): pass
class EffectFailed(LedgerError): pass

@dataclass(frozen=True)
class Execution:
    receipt: Any
    cached: bool


def _validate_json_tree(value: Any, depth: int = 0) -> None:
    if depth > 64:
        raise ValidationError("JSON value exceeds maximum nesting depth")
    if value is None or type(value) in (bool, str):
        return
    if type(value) is int:
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ValidationError("value must be valid finite JSON")
        return
    if type(value) is list:
        for item in value:
            _validate_json_tree(item, depth + 1)
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise ValidationError("JSON object keys must be strings")
            _validate_json_tree(item, depth + 1)
        return
    raise ValidationError("value must be a pure JSON tree")

def _canonical(value: Any, *, limit: int) -> tuple[str, bytes]:
    _validate_json_tree(value)
    try:
        text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        raw = text.encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise ValidationError("value must be valid finite JSON") from None
    if len(raw) > limit:
        raise ValidationError("JSON value exceeds size limit")
    return text, raw

def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValidationError(f"invalid {label}")
    return value

class Ledger:
    """SQLite ledger. Callback is called as callback() only after durable claim commit."""
    def __init__(self, path: str | Path):
        raw_path = str(path) if isinstance(path, (str, Path)) else ""
        if not raw_path or raw_path.strip() != raw_path or raw_path == ":memory:" or raw_path.startswith("file:") or "mode=memory" in raw_path:
            raise ValidationError("a persistent SQLite file path is required")
        self.path = raw_path
        if not Path(self.path).parent.exists():
            raise ValidationError("database parent directory must already exist")
        try:
            with closing(self._connect()) as db:
                db.execute("PRAGMA journal_mode=WAL")
                db.execute("""CREATE TABLE IF NOT EXISTS operations (
                    scope TEXT NOT NULL, operation_id TEXT NOT NULL, tool TEXT NOT NULL,
                    arguments_sha256 TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('pending','succeeded','uncertain')),
                    receipt_json TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(scope, operation_id),
                    CHECK ((state='succeeded' AND receipt_json IS NOT NULL) OR (state!='succeeded' AND receipt_json IS NULL))
                )""")
        except (sqlite3.Error, OSError):
            raise LedgerError("unable to initialize ledger database") from None

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        return db

    def execute(self, scope: str, operation_id: str, tool: str, arguments: Any,
                callback: Callable[[], Any]) -> Execution:
        scope = _identifier(scope, "scope")
        operation_id = _identifier(operation_id, "operation ID")
        tool = _identifier(tool, "tool name")
        if not callable(callback):
            raise ValidationError("callback must be callable")
        _, arg_bytes = _canonical(arguments, limit=MAX_ARGUMENT_BYTES)
        digest = hashlib.sha256(arg_bytes).hexdigest()
        try:
            with closing(self._connect()) as db:
                db.execute("BEGIN IMMEDIATE")
                try:
                    row = db.execute("SELECT tool,arguments_sha256,state,receipt_json FROM operations WHERE scope=? AND operation_id=?", (scope, operation_id)).fetchone()
                    if row is None:
                        db.execute("INSERT INTO operations(scope,operation_id,tool,arguments_sha256,state) VALUES(?,?,?,?,'pending')", (scope, operation_id, tool, digest))
                        db.commit()
                        prior = None
                    else:
                        if row["tool"] != tool or row["arguments_sha256"] != digest:
                            raise ConflictError("operation key is already bound to different input")
                        state, payload = row["state"], row["receipt_json"]
                        db.commit()
                        prior = (state, payload)
                except Exception:
                    db.rollback()
                    raise
        except (ConflictError, ValidationError, OperationBlocked):
            raise
        except (sqlite3.Error, OSError):
            raise LedgerError("unable to claim operation") from None
        if prior is not None:
            state, payload = prior
            if state == "succeeded":
                try:
                    return Execution(json.loads(payload), True)
                except (TypeError, ValueError, json.JSONDecodeError):
                    raise LedgerError("stored receipt is unreadable") from None
            raise OperationBlocked(f"operation is {state}; automatic replay is blocked")
        try:
            receipt = callback()
            encoded, _ = _canonical(receipt, limit=MAX_RECEIPT_BYTES)
        except Exception as exc:
            self._set_uncertain(scope, operation_id)
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            raise EffectFailed("effect failed or receipt was invalid; operation is uncertain") from None
        try:
            with closing(self._connect()) as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("UPDATE operations SET state='succeeded', receipt_json=?, updated_at=CURRENT_TIMESTAMP WHERE scope=? AND operation_id=? AND state='pending'", (encoded, scope, operation_id))
                if db.execute("SELECT changes()").fetchone()[0] != 1:
                    db.rollback()
                    raise LedgerError("unable to record receipt; operation remains blocked")
                db.commit()
        except LedgerError:
            raise
        except sqlite3.Error:
            raise LedgerError("effect completed but receipt could not be recorded; operation remains blocked") from None
        return Execution(json.loads(encoded), False)

    def _set_uncertain(self, scope: str, operation_id: str) -> None:
        try:
            with closing(self._connect()) as db:
                db.execute("UPDATE operations SET state='uncertain', updated_at=CURRENT_TIMESTAMP WHERE scope=? AND operation_id=? AND state='pending'", (scope, operation_id))
        except sqlite3.Error:
            pass

    def inspect(self) -> list[dict[str, str]]:
        """Return metadata only; intentionally excludes argument hashes and receipt payloads."""
        try:
            with closing(self._connect()) as db:
                rows = db.execute("SELECT scope,operation_id,tool,state,created_at,updated_at FROM operations ORDER BY scope,operation_id").fetchall()
                return [dict(row) for row in rows]
        except sqlite3.Error:
            raise LedgerError("unable to inspect ledger") from None
