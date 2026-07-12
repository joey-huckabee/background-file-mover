"""``SQLiteJobRepository`` — authoritative durable job and file state.

SQLite is the durable work queue (L1-SYS-007). Each thread gets its own connection with
``foreign_keys=ON``, ``journal_mode=WAL``, ``synchronous=FULL``, and a ``busy_timeout``
(L3-PY-007, L3-JOB-001); the schema is created and migrated idempotently at startup via
``PRAGMA user_version``. Every SQLite error and every malformed stored value is
translated into a typed :class:`~file_mover.exceptions.RepositoryError` so a corrupt row
or a locked database can never crash the service (the no-panic contract).
"""

from __future__ import annotations

import contextlib
import sqlite3
import threading
import time
from collections.abc import Callable, Collection, Iterator

from file_mover.exceptions import RepositoryError
from file_mover.jobs.models import (
    FileRecord,
    FileState,
    JobRecord,
    JobState,
    JobStatistics,
    is_allowed_job_transition,
)

_SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE jobs (
    job_id            TEXT PRIMARY KEY,
    state             TEXT NOT NULL,
    source_root       TEXT NOT NULL,
    destination_root  TEXT NOT NULL,
    created_at        REAL NOT NULL,
    updated_at        REAL NOT NULL,
    scenario_id       TEXT,
    request_id        TEXT UNIQUE,
    file_count        INTEGER NOT NULL DEFAULT 0,
    total_bytes       INTEGER NOT NULL DEFAULT 0,
    bytes_copied      INTEGER NOT NULL DEFAULT 0,
    attempt_count     INTEGER NOT NULL DEFAULT 0,
    next_retry_time   REAL,
    last_error        TEXT
);
CREATE TABLE files (
    file_id           TEXT PRIMARY KEY,
    job_id            TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
    relative_path     TEXT NOT NULL,
    state             TEXT NOT NULL,
    size_bytes        INTEGER NOT NULL DEFAULT 0,
    bytes_copied      INTEGER NOT NULL DEFAULT 0,
    source_hash       TEXT,
    destination_hash  TEXT,
    attempt_count     INTEGER NOT NULL DEFAULT 0,
    last_error        TEXT
);
CREATE INDEX idx_jobs_state ON jobs(state);
CREATE INDEX idx_files_job ON files(job_id, relative_path);
"""


class SQLiteJobRepository:
    """A durable :class:`~file_mover.jobs.repository.JobRepository` backed by SQLite."""

    def __init__(self, database_path: str, *, time_source: Callable[[], float] = time.time) -> None:
        """Initialise the repository.

        Args:
            database_path: Path to the SQLite database file.
            time_source: Clock used for ``updated_at`` stamps; injectable for tests.
        """
        self._path = database_path
        self._now = time_source
        self._local = threading.local()
        self._connections: list[sqlite3.Connection] = []
        self._lock = threading.Lock()

    def _connection(self) -> sqlite3.Connection:
        """Return this thread's connection, creating and configuring it on first use."""
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is not None:
            return conn
        try:
            conn = sqlite3.connect(self._path, timeout=5.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = FULL")
            conn.execute("PRAGMA busy_timeout = 5000")
        except sqlite3.Error as error:
            raise RepositoryError(f"cannot open database {self._path}: {error}") from error
        self._local.conn = conn
        with self._lock:
            self._connections.append(conn)
        return conn

    @contextlib.contextmanager
    def _translate(self, operation: str) -> Iterator[None]:
        """Translate any SQLite error raised in the block into a RepositoryError."""
        try:
            yield
        except sqlite3.Error as error:
            raise RepositoryError(f"{operation} failed: {error}") from error

    def initialize(self) -> None:
        """Create the schema and apply migrations (idempotent)."""
        with self._translate("initialize"):
            conn = self._connection()
            with conn:
                version = int(conn.execute("PRAGMA user_version").fetchone()[0])
                if version < _SCHEMA_VERSION:
                    conn.executescript(_SCHEMA)
                    conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")

    def insert_job(self, job: JobRecord) -> None:
        """Insert a new job record."""
        with self._translate("insert_job"):
            conn = self._connection()
            with conn:
                conn.execute(
                    """
                    INSERT INTO jobs (
                        job_id, state, source_root, destination_root, created_at,
                        updated_at, scenario_id, request_id, file_count, total_bytes,
                        bytes_copied, attempt_count, next_retry_time, last_error
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job.job_id,
                        job.state.value,
                        job.source_root,
                        job.destination_root,
                        job.created_at,
                        job.updated_at,
                        job.scenario_id,
                        job.request_id,
                        job.file_count,
                        job.total_bytes,
                        job.bytes_copied,
                        job.attempt_count,
                        job.next_retry_time,
                        job.last_error,
                    ),
                )

    def get_job(self, job_id: str) -> JobRecord | None:
        """Return the job with ``job_id``, or ``None`` if absent."""
        with self._translate("get_job"):
            row = (
                self._connection()
                .execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
                .fetchone()
            )
        return _row_to_job(row) if row is not None else None

    def get_job_by_request_id(self, request_id: str) -> JobRecord | None:
        """Return the job with the given idempotency ``request_id``, or ``None``."""
        with self._translate("get_job_by_request_id"):
            row = (
                self._connection()
                .execute("SELECT * FROM jobs WHERE request_id = ?", (request_id,))
                .fetchone()
            )
        return _row_to_job(row) if row is not None else None

    def list_jobs(self, states: Collection[JobState] | None = None) -> list[JobRecord]:
        """Return jobs, optionally filtered to the given states, newest first."""
        with self._translate("list_jobs"):
            conn = self._connection()
            if states is None:
                rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
            elif not states:
                return []
            else:
                placeholders = ", ".join("?" for _ in states)
                # `placeholders` is only "?" marks; the state values are bound as
                # parameters below, so this is not an injection vector.
                query = (
                    f"SELECT * FROM jobs WHERE state IN ({placeholders}) "  # nosec B608
                    "ORDER BY created_at DESC"
                )
                rows = conn.execute(query, tuple(state.value for state in states)).fetchall()
        return [_row_to_job(row) for row in rows]

    def insert_files(self, files: Collection[FileRecord]) -> None:
        """Insert file records for a job."""
        with self._translate("insert_files"):
            conn = self._connection()
            with conn:
                conn.executemany(
                    """
                    INSERT INTO files (
                        file_id, job_id, relative_path, state, size_bytes, bytes_copied,
                        source_hash, destination_hash, attempt_count, last_error
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            record.file_id,
                            record.job_id,
                            record.relative_path,
                            record.state.value,
                            record.size_bytes,
                            record.bytes_copied,
                            record.source_hash,
                            record.destination_hash,
                            record.attempt_count,
                            record.last_error,
                        )
                        for record in files
                    ],
                )

    def update_file(
        self,
        file_id: str,
        *,
        state: FileState | None = None,
        source_hash: str | None = None,
        destination_hash: str | None = None,
        last_error: str | None = None,
    ) -> None:
        """Partially update a file record's state, hashes, or last error."""
        assignments: list[str] = []
        params: list[object] = []
        if state is not None:
            assignments.append("state = ?")
            params.append(state.value)
        if source_hash is not None:
            assignments.append("source_hash = ?")
            params.append(source_hash)
        if destination_hash is not None:
            assignments.append("destination_hash = ?")
            params.append(destination_hash)
        if last_error is not None:
            assignments.append("last_error = ?")
            params.append(last_error)
        if not assignments:
            return
        params.append(file_id)
        # `assignments` is a fixed list of "column = ?" fragments; all values are bound.
        query = f"UPDATE files SET {', '.join(assignments)} WHERE file_id = ?"  # nosec B608
        with self._translate("update_file"):
            conn = self._connection()
            with conn:
                conn.execute(query, tuple(params))

    def record_job_progress(self, job_id: str, bytes_copied: int) -> None:
        """Update a job's copied-bytes progress counter."""
        with self._translate("record_job_progress"):
            conn = self._connection()
            with conn:
                conn.execute(
                    "UPDATE jobs SET bytes_copied = ?, updated_at = ? WHERE job_id = ?",
                    (bytes_copied, self._now(), job_id),
                )

    def list_files(self, job_id: str) -> list[FileRecord]:
        """Return the files belonging to ``job_id`` in deterministic order."""
        with self._translate("list_files"):
            rows = (
                self._connection()
                .execute("SELECT * FROM files WHERE job_id = ? ORDER BY relative_path", (job_id,))
                .fetchall()
            )
        return [_row_to_file(row) for row in rows]

    def transition_job(self, job_id: str, to_state: JobState) -> None:
        """Transition a job to ``to_state``, enforcing the allowed-transition map."""
        with self._translate("transition_job"):
            conn = self._connection()
            with conn:
                row = conn.execute("SELECT state FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
                if row is None:
                    raise RepositoryError(f"cannot transition unknown job {job_id!r}")
                current = _parse_state(row["state"])
                if not is_allowed_job_transition(current, to_state):
                    raise RepositoryError(
                        f"illegal job transition {current.value} -> {to_state.value}"
                    )
                conn.execute(
                    "UPDATE jobs SET state = ?, updated_at = ? WHERE job_id = ?",
                    (to_state.value, self._now(), job_id),
                )

    def transition_job_if(
        self, job_id: str, from_states: Collection[JobState], to_state: JobState
    ) -> bool:
        """Compare-and-set a job's state; return whether the transition was applied."""
        expected = {state.value for state in from_states}
        with self._translate("transition_job_if"):
            conn = self._connection()
            with conn:
                row = conn.execute("SELECT state FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
                if row is None:
                    raise RepositoryError(f"cannot transition unknown job {job_id!r}")
                current = _parse_state(row["state"])
                if current.value not in expected:
                    return False
                if not is_allowed_job_transition(current, to_state):
                    raise RepositoryError(
                        f"illegal job transition {current.value} -> {to_state.value}"
                    )
                conn.execute(
                    "UPDATE jobs SET state = ?, updated_at = ? WHERE job_id = ?",
                    (to_state.value, self._now(), job_id),
                )
                return True

    def reset_job_state(self, job_id: str, to_state: JobState) -> None:
        """Set a job's state unconditionally (recovery use; bypasses the transition map)."""
        with self._translate("reset_job_state"):
            conn = self._connection()
            with conn:
                conn.execute(
                    "UPDATE jobs SET state = ?, updated_at = ? WHERE job_id = ?",
                    (to_state.value, self._now(), job_id),
                )

    def list_runnable_job_ids(self, now: float, *, limit: int) -> list[str]:
        """Return ids of runnable jobs (queued, or retry-wait whose retry time has passed)."""
        with self._translate("list_runnable_job_ids"):
            rows = (
                self._connection()
                .execute(
                    """
                SELECT job_id FROM jobs
                WHERE state = ?
                   OR (state = ? AND (next_retry_time IS NULL OR next_retry_time <= ?))
                ORDER BY created_at ASC
                LIMIT ?
                """,
                    (JobState.QUEUED.value, JobState.RETRY_WAIT.value, now, limit),
                )
                .fetchall()
            )
        return [row["job_id"] for row in rows]

    def record_job_error(
        self, job_id: str, message: str, *, next_retry_time: float | None = None
    ) -> None:
        """Record a failure on a job, incrementing its attempt count."""
        with self._translate("record_job_error"):
            conn = self._connection()
            with conn:
                conn.execute(
                    """
                    UPDATE jobs
                    SET last_error = ?, next_retry_time = ?,
                        attempt_count = attempt_count + 1, updated_at = ?
                    WHERE job_id = ?
                    """,
                    (message, next_retry_time, self._now(), job_id),
                )

    def statistics(self) -> JobStatistics:
        """Return aggregate job statistics."""
        with self._translate("statistics"):
            rows = (
                self._connection()
                .execute(
                    """
                SELECT state, COUNT(*) AS n,
                       COALESCE(SUM(total_bytes), 0) AS tb,
                       COALESCE(SUM(bytes_copied), 0) AS bc
                FROM jobs GROUP BY state
                """
                )
                .fetchall()
            )
        jobs_by_state: dict[JobState, int] = {}
        total_jobs = total_bytes = bytes_copied = 0
        for row in rows:
            jobs_by_state[_parse_state(row["state"])] = int(row["n"])
            total_jobs += int(row["n"])
            total_bytes += int(row["tb"])
            bytes_copied += int(row["bc"])
        return JobStatistics(
            total_jobs=total_jobs,
            total_bytes=total_bytes,
            bytes_copied=bytes_copied,
            jobs_by_state=jobs_by_state,
        )

    def close(self) -> None:
        """Close all open database connections."""
        with self._lock:
            connections = list(self._connections)
            self._connections.clear()
        for conn in connections:
            with contextlib.suppress(sqlite3.Error):
                conn.close()
        self._local = threading.local()


def _parse_state(value: object) -> JobState:
    """Map a stored state string to a :class:`JobState`, or raise RepositoryError."""
    try:
        return JobState(value)
    except ValueError as error:
        raise RepositoryError(f"corrupt job state in database: {value!r}") from error


def _parse_file_state(value: object) -> FileState:
    """Map a stored state string to a :class:`FileState`, or raise RepositoryError."""
    try:
        return FileState(value)
    except ValueError as error:
        raise RepositoryError(f"corrupt file state in database: {value!r}") from error


def _row_to_job(row: sqlite3.Row) -> JobRecord:
    """Map a ``jobs`` row to a :class:`JobRecord`."""
    return JobRecord(
        job_id=row["job_id"],
        state=_parse_state(row["state"]),
        source_root=row["source_root"],
        destination_root=row["destination_root"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        scenario_id=row["scenario_id"],
        request_id=row["request_id"],
        file_count=row["file_count"],
        total_bytes=row["total_bytes"],
        bytes_copied=row["bytes_copied"],
        attempt_count=row["attempt_count"],
        next_retry_time=row["next_retry_time"],
        last_error=row["last_error"],
    )


def _row_to_file(row: sqlite3.Row) -> FileRecord:
    """Map a ``files`` row to a :class:`FileRecord`."""
    return FileRecord(
        file_id=row["file_id"],
        job_id=row["job_id"],
        relative_path=row["relative_path"],
        state=_parse_file_state(row["state"]),
        size_bytes=row["size_bytes"],
        bytes_copied=row["bytes_copied"],
        source_hash=row["source_hash"],
        destination_hash=row["destination_hash"],
        attempt_count=row["attempt_count"],
        last_error=row["last_error"],
    )
