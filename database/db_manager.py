"""SQLite connection management with safe commits/rollbacks."""
from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Sequence

from config import BACKUP_DIR, BACKUP_KEEP, DB_PATH, DEFAULT_SETTINGS, ensure_directories
from database.schema import DEFAULT_CATEGORIES, SCHEMA_STATEMENTS, SCHEMA_VERSION

log = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Raised for any database failure, carrying a user-presentable message."""


class DatabaseManager:
    """Owns the single SQLite connection used by the whole application.

    The connection is shared across threads (needed for background exports)
    and every access is serialised through a re-entrant lock.
    """

    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = Path(db_path)
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------ #
    # Connection lifecycle
    # ------------------------------------------------------------------ #
    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            try:
                ensure_directories()
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
                conn = sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=15)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA foreign_keys = ON")
                conn.execute("PRAGMA journal_mode = WAL")
                conn.execute("PRAGMA synchronous = NORMAL")
                self._conn = conn
            except sqlite3.Error as exc:
                log.exception("Cannot open database")
                raise DatabaseError(f"Could not open the database: {exc}") from exc
        return self._conn

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.execute("PRAGMA optimize")
                    self._conn.close()
                finally:
                    self._conn = None

    # ------------------------------------------------------------------ #
    # Query helpers
    # ------------------------------------------------------------------ #
    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Run a block atomically: commit on success, roll back on any error."""
        with self._lock:
            conn = self.connect()
            try:
                yield conn
                conn.commit()
            except sqlite3.Error as exc:
                conn.rollback()
                log.exception("Database transaction failed")
                raise DatabaseError(f"Database operation failed: {exc}") from exc
            except Exception:
                conn.rollback()
                raise

    def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        """Execute a write statement and return ``lastrowid``."""
        with self.transaction() as conn:
            return conn.execute(sql, params).lastrowid or 0

    def executemany(self, sql: str, rows: Sequence[Sequence[Any]]) -> None:
        with self.transaction() as conn:
            conn.executemany(sql, rows)

    def query_all(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            try:
                return self.connect().execute(sql, params).fetchall()
            except sqlite3.Error as exc:
                log.exception("Query failed: %s", sql)
                raise DatabaseError(f"Database query failed: {exc}") from exc

    def query_one(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
        with self._lock:
            try:
                return self.connect().execute(sql, params).fetchone()
            except sqlite3.Error as exc:
                log.exception("Query failed: %s", sql)
                raise DatabaseError(f"Database query failed: {exc}") from exc

    def scalar(self, sql: str, params: Sequence[Any] = (), default: Any = 0) -> Any:
        row = self.query_one(sql, params)
        if row is None or row[0] is None:
            return default
        return row[0]

    # ------------------------------------------------------------------ #
    # Initialisation
    # ------------------------------------------------------------------ #
    def initialize(self) -> None:
        """Create tables, default settings and default categories (idempotent)."""
        with self.transaction() as conn:
            for statement in SCHEMA_STATEMENTS:
                conn.execute(statement)
            conn.execute(
                "INSERT OR IGNORE INTO app_settings (key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
            for key, value in DEFAULT_SETTINGS.items():
                conn.execute(
                    "INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)", (key, value)
                )
            seeded = conn.execute(
                "SELECT value FROM app_settings WHERE key = 'defaults_seeded'"
            ).fetchone()
            if seeded is None:
                conn.executemany(
                    "INSERT OR IGNORE INTO categories (name, type, color, icon, is_default) "
                    "VALUES (?, ?, ?, ?, 1)",
                    DEFAULT_CATEGORIES,
                )
                conn.execute(
                    "INSERT INTO app_settings (key, value) VALUES ('defaults_seeded', '1')"
                )

    # ------------------------------------------------------------------ #
    # Settings
    # ------------------------------------------------------------------ #
    def get_setting(self, key: str, default: str = "") -> str:
        row = self.query_one("SELECT value FROM app_settings WHERE key = ?", (key,))
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.execute(
            "INSERT INTO app_settings (key, value, updated_at) "
            "VALUES (?, ?, datetime('now', 'localtime')) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
            "updated_at = excluded.updated_at",
            (key, value),
        )

    # ------------------------------------------------------------------ #
    # Backup
    # ------------------------------------------------------------------ #
    def backup(self, destination_dir: Path = BACKUP_DIR, prefix: str = "finance_backup") -> Path:
        """Write a consistent snapshot of the live database and return its path."""
        destination_dir = Path(destination_dir)
        destination_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = destination_dir / f"{prefix}_{stamp}.db"
        with self._lock:
            source = self.connect()
            dest = sqlite3.connect(str(target))
            try:
                source.backup(dest)
            except sqlite3.Error as exc:
                log.exception("Backup failed")
                raise DatabaseError(f"Backup failed: {exc}") from exc
            finally:
                dest.close()
        return target

    def prune_backups(self, prefix: str = "auto_backup", keep: int = BACKUP_KEEP,
                      directory: Path = BACKUP_DIR) -> None:
        """Delete the oldest automatic backups, keeping the newest ``keep``."""
        files = sorted(Path(directory).glob(f"{prefix}_*.db"), key=lambda f: f.stat().st_mtime, reverse=True)
        for old in files[keep:]:
            try:
                old.unlink()
            except OSError:
                log.warning("Could not delete old backup %s", old)

    REQUIRED_TABLES = {"transactions", "categories", "budgets", "savings_goals",
                       "savings_contributions", "app_settings"}

    @classmethod
    def validate_backup(cls, path: Path) -> None:
        """Raise DatabaseError unless ``path`` is a healthy FinanceFlow database."""
        path = Path(path)
        if not path.is_file():
            raise DatabaseError("The selected backup file does not exist.")
        try:
            conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
            try:
                tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not cls.REQUIRED_TABLES <= tables:
                    raise DatabaseError("This file is not a ZaBir FinanceFlow backup.")
                if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise DatabaseError("The backup file is damaged (integrity check failed).")
            finally:
                conn.close()
        except sqlite3.Error as exc:
            raise DatabaseError(f"The selected file is not a valid database: {exc}") from exc

    def restore_from(self, source: Path) -> None:
        """Replace the live database with ``source`` (validated first)."""
        source = Path(source)
        self.validate_backup(source)
        with self._lock:
            self.close()
            try:
                src = sqlite3.connect(f"{source.resolve().as_uri()}?mode=ro", uri=True)
                dest = sqlite3.connect(str(self.db_path))
                try:
                    src.backup(dest)
                finally:
                    src.close()
                    dest.close()
            except sqlite3.Error as exc:
                log.exception("Restore failed")
                self.connect()
                raise DatabaseError(f"Restore failed: {exc}") from exc
            self.connect()
            self.initialize()

    def optimize(self) -> None:
        """Compact the file and refresh query-planner statistics."""
        with self._lock:
            try:
                conn = self.connect()
                conn.commit()
                conn.execute("VACUUM")
                conn.execute("PRAGMA optimize")
            except sqlite3.Error as exc:
                raise DatabaseError(f"Optimisation failed: {exc}") from exc
