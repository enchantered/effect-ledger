"""Read-only uncertainty review; this is not automatic operation resolution."""
from __future__ import annotations

import re
import sqlite3
import stat
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .ledger import IDENTIFIER, LedgerError, ValidationError

DEFAULT_LIMIT = 100
MAX_LIMIT = 1000


def _path(value: Any) -> Path:
    raw = str(value) if isinstance(value, (str, Path)) else ""
    if (not raw or raw.strip() != raw or raw == ":memory:" or raw.startswith("file:")
            or "mode=memory" in raw):
        raise ValidationError("a persistent SQLite file path is required")
    return Path(raw)


def review(path: str | Path, limit: int = DEFAULT_LIMIT, scope: str | None = None) -> dict[str, Any]:
    """Return only unresolved operation metadata without creating or changing the DB.

    SQLite may use WAL coordination sidecars. This is logical read-only access,
    not byte-for-byte forensic access or a security sandbox against hostile filesystem actors.
    """
    db_path = _path(path)
    if type(limit) is not int or not 1 <= limit <= MAX_LIMIT:
        raise ValidationError("limit must be an integer from 1 to 1000")
    if scope is not None and (type(scope) is not str or not IDENTIFIER.fullmatch(scope)):
        raise ValidationError("invalid scope")
    try:
        if not stat.S_ISREG(db_path.stat().st_mode):
            raise LedgerError("unable to review ledger")
        # Resolve the local path to avoid SQLite interpreting user path text as a URI.
        uri = db_path.resolve(strict=False).as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=5, isolation_level=None)) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            sql = ("SELECT scope,operation_id,tool,state,created_at,updated_at "
                   "FROM operations WHERE state IN ('pending','uncertain')")
            params: list[Any] = []
            if scope is not None:
                sql += " AND scope=?"
                params.append(scope)
            sql += " ORDER BY scope,operation_id LIMIT ?"
            params.append(limit + 1)
            rows = db.execute(sql, params).fetchall()
            db.rollback()
        truncated = len(rows) > limit
        rows = rows[:limit]
        operations = []
        for row in rows:
            # Validate every interpolated/displayed value before returning it.
            for field, label in (("scope", "scope"), ("operation_id", "operation ID"), ("tool", "tool name")):
                value = row[field]
                if type(value) is not str or not IDENTIFIER.fullmatch(value):
                    raise LedgerError("unable to review ledger")
            state = row["state"]
            if type(state) is not str or state not in ("pending", "uncertain"):
                raise LedgerError("unable to review ledger")
            created, updated = row["created_at"], row["updated_at"]
            for timestamp in (created, updated):
                if type(timestamp) is not str or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}", timestamp):
                    raise LedgerError("unable to review ledger")
                datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
            created_at = datetime.strptime(created, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            age_seconds = (datetime.now(timezone.utc) - created_at).total_seconds()
            age_hours = max(0, int(age_seconds // 3600))
            operations.append({
                "scope": row["scope"], "operation_id": row["operation_id"],
                "tool": row["tool"], "state": state,
                "created_at": created, "updated_at": updated,
                "age_hours": age_hours,
                "older_than_72_hours": age_seconds >= 72 * 3600,
                "blocking_reason": ("may_still_be_running_or_process_died" if state == "pending"
                                    else "action_may_have_completed"),
                "next_step": "inspect_authoritative_outcome_no_auto_retry",
            })
        return {"operations": operations, "truncated": truncated, "read_only": True}
    except LedgerError:
        raise
    except (sqlite3.Error, OSError, ValueError, UnicodeError, RuntimeError):
        raise LedgerError("unable to review ledger") from None
