"""The long-running ``BackgroundMoverService`` and its startup/shutdown lifecycle.

``run`` acquires the singleton lock, opens the durable SQLite state, reconciles
interrupted jobs (:class:`~file_mover.recovery.manager.RecoveryManager`), binds the
control socket, and then runs two responsibilities concurrently: the control server
(``health``/``status``/``list``/``stats``/``submit``) and a transfer-scheduler thread
that drives runnable jobs through the coordinator. SQLite is the durable queue between
submission and the scheduler.

The signal handlers only set a thread-safe stop event; the drain happens on the main
thread. Tests drive the service on a worker thread with ``install_signal_handlers=False``
and stop it via :meth:`request_stop`.
"""

from __future__ import annotations

import logging
import signal
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from file_mover import __version__
from file_mover.claiming import FileClaimManager
from file_mover.configuration import ApplicationConfig
from file_mover.constants import PROTOCOL_VERSION
from file_mover.control.dispatcher import CommandDispatcher
from file_mover.control.lock import ProcessLock
from file_mover.control.server import ControlSocketServer
from file_mover.jobs.models import (
    ACTIVE_JOB_STATES,
    ExistingDestinationPolicy,
    JobRecord,
    JobState,
    JobStatistics,
)
from file_mover.jobs.repository import JobRepository
from file_mover.jobs.sqlite_repository import SQLiteJobRepository
from file_mover.manifests import ManifestWriter
from file_mover.recovery.manager import RecoveryManager
from file_mover.submission import (
    JobSubmissionService,
    SubmissionResult,
    build_submission_request,
)
from file_mover.transfer.coordinator import TransferCoordinator
from file_mover.transfer.copy_engine import BufferedFileCopyEngine
from file_mover.transfer.integrity import IntegrityVerifier
from file_mover.transfer.retry import ErrorClassifier
from file_mover.transfer.scheduler import TransferScheduler
from file_mover.validation import SourceValidator

_LOCK_FILENAME = "service.lock"


class BackgroundMoverService:
    """Owns the control server, durable state, the singleton lock, and shutdown."""

    def __init__(
        self,
        config: ApplicationConfig,
        *,
        repository: JobRepository | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialise the service.

        Args:
            config: The validated application configuration.
            repository: Durable job repository; created from the configured database path
                when omitted (and then owned/closed by the service).
            logger: Optional logger; defaults to ``file_mover.service``.
        """
        self._config = config
        self._logger = logger or logging.getLogger("file_mover.service")
        self._repository = repository
        self._owns_repository = repository is None
        self._submission: JobSubmissionService | None = None
        self._scheduler: TransferScheduler | None = None
        self._server: ControlSocketServer | None = None
        self._stopping = threading.Event()
        self._ready = threading.Event()

    def run(self, *, install_signal_handlers: bool = True) -> int:
        """Acquire the lock, open state, bind the socket, and serve until stopped.

        Args:
            install_signal_handlers: Install SIGTERM/SIGINT handlers (only possible on
                the main thread; disable when driving the service from a worker thread).

        Returns:
            ``0`` on a clean shutdown.
        """
        lock = ProcessLock(str(self._config.service.state_directory / _LOCK_FILENAME))
        lock.acquire()
        scheduler_thread: threading.Thread | None = None
        try:
            if self._repository is None:
                self._repository = SQLiteJobRepository(str(self._config.service.database_path))
            self._repository.initialize()
            self._submission = self._build_submission_service(self._repository)
            self._scheduler = self._build_scheduler(self._repository)
            self._reconcile(self._repository)
            server = ControlSocketServer(
                str(self._config.service.socket_path),
                self._build_dispatcher(),
                maximum_message_bytes=self._config.control.maximum_message_bytes,
                socket_mode=self._config.control.socket_mode,
                max_workers=self._config.control.max_concurrent_requests,
                logger=self._logger,
            )
            server.bind()
            self._server = server
            if install_signal_handlers:
                self._install_signal_handlers()
            scheduler_thread = threading.Thread(
                target=self._scheduler_loop, name="swit-scheduler", daemon=True
            )
            scheduler_thread.start()
            self._ready.set()
            self._logger.info("control service ready at %s", self._config.service.socket_path)
            server.serve_forever()
        finally:
            self._stopping.set()
            if scheduler_thread is not None:
                scheduler_thread.join(timeout=self._config.service.shutdown_timeout_seconds)
            if self._server is not None:
                self._server.close()
                self._server = None
            if self._owns_repository and self._repository is not None:
                self._repository.close()
                self._repository = None
            self._ready.clear()
            lock.release()
        return 0

    def wait_ready(self, timeout: float | None = None) -> bool:
        """Block until the service is serving (or ``timeout`` elapses)."""
        return self._ready.wait(timeout)

    def request_stop(self) -> None:
        """Signal the service to stop accepting connections and drain."""
        self._stopping.set()
        if self._server is not None:
            self._server.stop()

    def _build_dispatcher(self) -> CommandDispatcher:
        """Build the control-command dispatcher for this service."""
        return CommandDispatcher(
            {
                "health": self._handle_health,
                "status": self._handle_status,
                "list": self._handle_list,
                "stats": self._handle_stats,
                "submit": self._handle_submit,
            }
        )

    def _build_submission_service(self, repository: JobRepository) -> JobSubmissionService:
        """Construct the submission service from configuration."""
        paths = self._config.paths
        return JobSubmissionService(
            validator=SourceValidator(
                claim_directory_name=paths.claim_directory_name,
                reject_symbolic_links=paths.reject_symbolic_links,
            ),
            claim_manager=FileClaimManager(claim_directory_name=paths.claim_directory_name),
            manifest_writer=ManifestWriter(Path(str(self._config.service.manifest_directory))),
            repository=repository,
            allowed_source_roots=[Path(str(root)) for root in paths.allowed_source_roots],
            allowed_destination_roots=[Path(str(root)) for root in paths.allowed_destination_roots],
            stability=self._config.stability,
        )

    def _build_scheduler(self, repository: JobRepository) -> TransferScheduler:
        """Construct the transfer coordinator and scheduler from configuration."""
        integrity = self._config.integrity
        transfer = self._config.transfer
        paths = self._config.paths
        coordinator = TransferCoordinator(
            repository=repository,
            copy_engine=BufferedFileCopyEngine(
                buffer_size_bytes=transfer.copy_buffer_size_bytes,
                temporary_file_prefix=paths.temporary_file_prefix,
            ),
            integrity_verifier=IntegrityVerifier(
                algorithm=integrity.algorithm,
                buffer_size_bytes=transfer.copy_buffer_size_bytes,
            ),
            error_classifier=ErrorClassifier(),
            claim_directory_name=paths.claim_directory_name,
            integrity_enabled=integrity.enabled,
            integrity_mode=integrity.mode,
            destination_policy=ExistingDestinationPolicy.FAIL,
            retry_initial_delay_seconds=transfer.retry_initial_delay_seconds,
            retry_max_delay_seconds=transfer.retry_max_delay_seconds,
        )
        return TransferScheduler(
            repository=repository,
            coordinator=coordinator,
            max_concurrent_jobs=transfer.max_concurrent_jobs,
        )

    def _reconcile(self, repository: JobRepository) -> None:
        """Reconcile interrupted jobs against the filesystem before serving."""
        report = RecoveryManager(
            repository=repository,
            temporary_file_prefix=self._config.paths.temporary_file_prefix,
            logger=self._logger,
        ).reconcile()
        self._logger.info(
            "recovery reconciled %d job(s); removed %d stale temporary file(s)",
            report.requeued_jobs,
            report.removed_temporary_files,
        )

    def _scheduler_loop(self) -> None:
        """Run scheduler ticks until shutdown; a failing tick never stops the loop."""
        while not self._stopping.is_set():
            try:
                if self._scheduler is not None:
                    self._scheduler.run_once()
            except Exception:  # pylint: disable=broad-exception-caught
                self._logger.exception("transfer scheduler tick failed")
            self._stopping.wait(self._config.service.poll_interval_seconds)

    def _require_repository(self) -> JobRepository:
        """Return the repository, or raise if the service is not running."""
        if self._repository is None:
            raise RuntimeError("service repository is not open")
        return self._repository

    def _require_submission(self) -> JobSubmissionService:
        """Return the submission service, or raise if the service is not running."""
        if self._submission is None:
            raise RuntimeError("submission service is not open")
        return self._submission

    def _handle_health(self, _arguments: Mapping[str, Any]) -> dict[str, Any]:
        """Return the service health snapshot."""
        return {
            "service_state": "stopping" if self._stopping.is_set() else "running",
            "protocol_version": PROTOCOL_VERSION,
            "app_version": __version__,
            "socket_path": str(self._config.service.socket_path),
        }

    def _handle_status(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """Return one job's status, or ``found: false`` when absent."""
        job_id = arguments.get("job_id")
        if not isinstance(job_id, str):
            return {"found": False, "job": None}
        job = self._require_repository().get_job(job_id)
        return {"found": job is not None, "job": _job_to_dict(job) if job else None}

    def _handle_list(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """Return jobs filtered by the requested state group or name."""
        selector = arguments.get("state", "active")
        states = _resolve_state_selector(selector if isinstance(selector, str) else "active")
        jobs = self._require_repository().list_jobs(states)
        return {"jobs": [_job_to_dict(job) for job in jobs]}

    def _handle_stats(self, _arguments: Mapping[str, Any]) -> dict[str, Any]:
        """Return aggregate durable statistics."""
        return _statistics_to_dict(self._require_repository().statistics())

    def _handle_submit(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """Validate, claim, and durably record a submitted recording set."""
        request_id = arguments.get("request_id")
        destination = arguments.get("destination")
        source = arguments.get("source")
        file_list = arguments.get("file_list")
        if not isinstance(request_id, str) or not isinstance(destination, str):
            return _submission_error("BAD_REQUEST", "request_id and destination are required")
        if source is None and not file_list:
            return _submission_error("BAD_REQUEST", "a source directory or file list is required")
        scenario_id = arguments.get("scenario_id")
        files = [str(item) for item in file_list] if isinstance(file_list, list) else None
        try:
            request = build_submission_request(
                request_id=request_id,
                scenario_id=scenario_id if isinstance(scenario_id, str) else None,
                destination=destination,
                source=source if isinstance(source, str) else None,
                file_list=files,
            )
        except ValueError as error:
            return _submission_error("BAD_REQUEST", str(error))
        return _submission_result_to_dict(self._require_submission().submit(request))

    def _install_signal_handlers(self) -> None:
        """Install SIGTERM/SIGINT handlers that only set the stop event."""

        def _handle(signum: int, _frame: object) -> None:
            self._logger.info("received signal %s; shutting down", signum)
            self.request_stop()

        signal.signal(signal.SIGTERM, _handle)
        signal.signal(signal.SIGINT, _handle)


def _resolve_state_selector(selector: str) -> frozenset[JobState] | None:
    """Map a ``list`` state selector to a set of states (``None`` means all).

    Raises:
        ValueError: If ``selector`` is neither ``active``/``all`` nor a known state name.
    """
    lowered = selector.strip().lower()
    if lowered in {"all", ""}:
        return None
    if lowered == "active":
        return ACTIVE_JOB_STATES
    try:
        return frozenset({JobState(lowered)})
    except ValueError as error:
        raise ValueError(f"unknown job state selector {selector!r}") from error


def _job_to_dict(job: JobRecord) -> dict[str, Any]:
    """Serialise a :class:`JobRecord` for a control response."""
    return {
        "job_id": job.job_id,
        "state": job.state.value,
        "scenario_id": job.scenario_id,
        "source_root": job.source_root,
        "destination_root": job.destination_root,
        "file_count": job.file_count,
        "total_bytes": job.total_bytes,
        "bytes_copied": job.bytes_copied,
        "attempt_count": job.attempt_count,
        "last_error": job.last_error,
    }


def _statistics_to_dict(stats: JobStatistics) -> dict[str, Any]:
    """Serialise :class:`JobStatistics` for a control response."""
    return {
        "total_jobs": stats.total_jobs,
        "total_bytes": stats.total_bytes,
        "bytes_copied": stats.bytes_copied,
        "jobs_by_state": {state.value: count for state, count in stats.jobs_by_state.items()},
    }


def _submission_result_to_dict(result: SubmissionResult) -> dict[str, Any]:
    """Serialise a :class:`SubmissionResult` for a control response."""
    return {
        "accepted": result.accepted,
        "job_id": result.job_id,
        "state": result.state.value,
        "claimed_file_count": result.claimed_file_count,
        "claimed_bytes": result.claimed_bytes,
        "error_code": result.error_code,
        "error_message": result.error_message,
    }


def _submission_error(code: str, message: str) -> dict[str, Any]:
    """Build a rejected submission response for a malformed request."""
    return {
        "accepted": False,
        "job_id": None,
        "state": JobState.FAILED_RETAINED.value,
        "claimed_file_count": 0,
        "claimed_bytes": 0,
        "error_code": code,
        "error_message": message,
    }
