"""Shared SQLite primitives for the small per-profile / board stores.

The projects and kanban stores open WAL SQLite files with the same two
primitives — an idempotent column-add migration and an IMMEDIATE write
transaction. One definition here keeps the two stores from drifting.
"""

from __future__ import annotations

import contextlib
import sqlite3
from pathlib import Path


def add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> bool:
    """``ALTER TABLE <table> ADD COLUMN <ddl>``, idempotent across races.

    Returns ``True`` when this call added the column. Swallows the
    ``duplicate column name`` error a concurrent migrator may have run first
    (issue #21708). ``column`` is the human-readable name for the call site;
    ``ddl`` carries the actual definition.
    """
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")
        return True
    except sqlite3.OperationalError as exc:
        if "duplicate column name" in str(exc).lower():
            return False
        raise


def is_zeroed_sqlite_file(
    path: Path, *, probe_bytes: int = 100, force: bool = False
) -> bool:
    """True when *path* looks like the #68474 zeroed-state.db signature.

    Signature: size > 0, first *probe_bytes* are all NUL (no ``SQLite format 3``
    header). Used at SessionDB open and for snapshot diagnostics so a silent
    all-zero file becomes a guided recovery instead of a generic failure.
    (Moved from ``sparkii_cli/backup.py`` during the Block 4 split.)
    """
    try:
        size = path.stat().st_size
    except OSError:
        return False
    if size <= 0:
        return False
    from core.sqlite_safe_read import read_header_bytes_preopen

    head = read_header_bytes_preopen(
        path, length=max(16, probe_bytes), force=force
    )
    if not head:
        return False
    if head.startswith(b"SQLite format 3"):
        return False
    return all(byte == 0 for byte in head)


@contextlib.contextmanager
def write_txn(conn: sqlite3.Connection):
    """An IMMEDIATE write transaction: at most one concurrent writer wins.

    The explicit ROLLBACK is guarded so a SQLite auto-rollback (no active
    transaction left under EIO / lock contention / corruption) cannot shadow
    the original exception with a spurious rollback error.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.OperationalError:
            pass
        raise
    else:
        conn.execute("COMMIT")
