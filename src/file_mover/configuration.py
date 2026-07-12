"""Configuration loading, validation, and the immutable ``ApplicationConfig`` model.

Configuration is a single INI file read with the standard-library
:mod:`configparser`. The :class:`ConfigurationLoader` runs a deterministic pipeline —
parse -> reject unknown sections/options -> convert to typed values -> validate ranges
and cross-field constraints -> build a frozen :class:`ApplicationConfig`. A single
``OptionSpec``-driven schema (:data:`SECTION_SCHEMAS`) is the one source of truth shared
by validation, unknown-option detection, default values, and generated documentation
(:func:`describe_schema`), satisfying L2-CFG-001..011.

All issues are collected and reported together (L2-CFG-008) via a
:class:`ConfigurationValidationError` carrying structured :class:`ConfigurationIssue`
records; the loader never falls back to reduced validation and never uses ``assert`` for
data-safety checks (L2-ARC-004/005).

Path options are modelled as :class:`~pathlib.PurePosixPath`: the production target is
Linux, and pure POSIX paths validate identically regardless of the host the loader runs
on (so tests behave the same on Windows and Linux).
"""

from __future__ import annotations

import configparser
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast

from file_mover.constants import MINIMUM_COPY_BUFFER_SIZE_BYTES
from file_mover.exceptions import ConfigurationError
from file_mover.jobs.models import HashAlgorithm, IntegrityMode

# Structured issues and the validation error


@dataclass(frozen=True)
class ConfigurationIssue:
    """One problem found while validating configuration.

    Attributes:
        section: The INI section the issue was found in (``"?"`` for parse errors).
        option: The offending option name, or ``None`` for section-level issues.
        value: The offending raw value, or ``None`` when absent.
        message: A human-readable description of the problem.
    """

    section: str
    option: str | None
    value: str | None
    message: str


class ConfigurationValidationError(ConfigurationError):
    """Raised when configuration content is invalid; carries every issue found."""

    def __init__(self, issues: Sequence[ConfigurationIssue]) -> None:
        """Initialise with the collected issues.

        Args:
            issues: All issues found during validation (at least one).
        """
        self.issues: tuple[ConfigurationIssue, ...] = tuple(issues)
        count = len(self.issues)
        noun = "issue" if count == 1 else "issues"
        super().__init__(f"configuration is invalid: {count} {noun}")


# Immutable configuration model


@dataclass(frozen=True)
class ServiceConfig:
    """Durable-state and lifecycle configuration (``[service]``)."""

    state_directory: PurePosixPath
    database_path: PurePosixPath
    manifest_directory: PurePosixPath
    socket_path: PurePosixPath
    shutdown_timeout_seconds: int
    poll_interval_seconds: float


@dataclass(frozen=True)
class ControlConfig:
    """Control-socket server configuration (``[control]``)."""

    socket_mode: int
    max_concurrent_requests: int
    request_timeout_seconds: int
    maximum_message_bytes: int


@dataclass(frozen=True)
class PathPolicyConfig:
    """Permitted source/destination roots and staging markers (``[paths]``)."""

    allowed_source_roots: tuple[PurePosixPath, ...]
    allowed_destination_roots: tuple[PurePosixPath, ...]
    claim_directory_name: str
    temporary_file_prefix: str
    reject_symbolic_links: bool


@dataclass(frozen=True)
class TransferConfig:
    """Transfer concurrency, buffering, and retry configuration (``[transfer]``)."""

    max_concurrent_jobs: int
    max_concurrent_files: int
    copy_buffer_size_bytes: int
    max_bytes_per_second: int
    retry_limit: int
    retry_initial_delay_seconds: float
    retry_max_delay_seconds: float
    use_kernel_copy: bool
    resume_partial_files: bool


@dataclass(frozen=True)
class IntegrityConfig:
    """Integrity-verification configuration (``[integrity]``)."""

    enabled: bool
    mode: IntegrityMode
    algorithm: HashAlgorithm


@dataclass(frozen=True)
class StabilityConfig:
    """Source-file stability-check configuration (``[stability]``)."""

    enabled: bool
    poll_count: int
    poll_interval_seconds: float


@dataclass(frozen=True)
class LoggingConfig:
    """Logging configuration (``[logging]``).

    Only the verbosity ``level`` is configurable: the service writes its event stream to
    stdout/stderr and lets the environment route it (twelve-factor), so log destinations
    are not application config.
    """

    level: str


@dataclass(frozen=True)
class ApplicationConfig:
    """The complete validated, immutable runtime configuration."""

    service: ServiceConfig
    control: ControlConfig
    paths: PathPolicyConfig
    transfer: TransferConfig
    integrity: IntegrityConfig
    stability: StabilityConfig
    logging: LoggingConfig


# Option schema — the single source of truth (L2-CFG-011)


@dataclass(frozen=True)
class OptionSpec:
    """Declarative definition of one configuration option.

    Drives value conversion, unknown/missing detection, default application, and
    documentation generation from a single definition.

    Attributes:
        name: The option key as it appears in the INI file.
        converter: Parses a raw string into a typed value; raises :class:`ValueError`
            with an operator-facing message on invalid input.
        required: Whether the option must be present (no compiled default).
        default: The compiled default raw string used when the option is absent and
            not required (validated through ``converter`` like any other value).
        description: Human-readable description for generated documentation.
    """

    name: str
    converter: Callable[[str], object]
    required: bool = False
    default: str = ""
    description: str = ""


_TRUE_TOKENS = frozenset({"true", "yes", "on", "1"})
_FALSE_TOKENS = frozenset({"false", "no", "off", "0"})
_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "OFF")


def _to_bool(raw: str) -> bool:
    """Parse an INI boolean (true/false/yes/no/on/off/1/0)."""
    token = raw.strip().lower()
    if token in _TRUE_TOKENS:
        return True
    if token in _FALSE_TOKENS:
        return False
    raise ValueError(f"expected a boolean (true/false), got {raw.strip()!r}")


def _int_converter(*, minimum: int | None = None) -> Callable[[str], int]:
    """Build an integer converter enforcing an optional inclusive lower bound."""

    def convert(raw: str) -> int:
        try:
            value = int(raw.strip())
        except ValueError:
            raise ValueError(f"expected an integer, got {raw.strip()!r}") from None
        if minimum is not None and value < minimum:
            raise ValueError(f"must be >= {minimum}, got {value}")
        return value

    return convert


def _float_converter(
    *, minimum: float | None = None, exclusive_minimum: bool = False
) -> Callable[[str], float]:
    """Build a float converter enforcing an optional lower bound."""

    def convert(raw: str) -> float:
        try:
            value = float(raw.strip())
        except ValueError:
            raise ValueError(f"expected a number, got {raw.strip()!r}") from None
        if minimum is not None:
            if exclusive_minimum and value <= minimum:
                raise ValueError(f"must be > {minimum}, got {value}")
            if not exclusive_minimum and value < minimum:
                raise ValueError(f"must be >= {minimum}, got {value}")
        return value

    return convert


def _octal_converter(raw: str) -> int:
    """Parse an octal permission mode such as ``0660``."""
    text = raw.strip()
    try:
        return int(text, 8)
    except ValueError:
        raise ValueError(f"expected an octal mode (e.g. 0660), got {text!r}") from None


def _enum_converter(enum_cls: type[IntegrityMode] | type[HashAlgorithm]) -> Callable[[str], object]:
    """Build a converter that maps a string to one of ``enum_cls``'s values."""

    def convert(raw: str) -> object:
        text = raw.strip()
        try:
            return enum_cls(text)
        except ValueError:
            valid = ", ".join(member.value for member in enum_cls)
            raise ValueError(f"expected one of [{valid}], got {text!r}") from None

    return convert


def _posix_path(raw: str) -> PurePosixPath:
    """Parse a single absolute POSIX path."""
    text = raw.strip()
    if not text:
        raise ValueError("path must not be empty")
    if "\x00" in text:
        raise ValueError("path must not contain a NUL byte")
    path = PurePosixPath(text)
    if not path.is_absolute():
        raise ValueError(f"path must be absolute, got {text!r}")
    return path


def _posix_path_list(raw: str) -> tuple[PurePosixPath, ...]:
    """Parse a newline- or comma-separated list of absolute POSIX paths."""
    parts = [part.strip() for line in raw.splitlines() for part in line.split(",")]
    parts = [part for part in parts if part]
    if not parts:
        raise ValueError("expected at least one absolute path")
    result: list[PurePosixPath] = []
    for part in parts:
        if "\x00" in part:
            raise ValueError("path must not contain a NUL byte")
        path = PurePosixPath(part)
        if not path.is_absolute():
            raise ValueError(f"path must be absolute, got {part!r}")
        result.append(path)
    return tuple(result)


def _single_component_name(raw: str) -> str:
    """Parse a single filename component (no separators, not ``.`` or ``..``)."""
    text = raw.strip()
    if not text:
        raise ValueError("must not be empty")
    if "/" in text or "\\" in text or text in {".", ".."}:
        raise ValueError(f"must be a single path component, got {text!r}")
    return text


def _nonempty_prefix(raw: str) -> str:
    """Parse a non-empty prefix that contains no path separators."""
    text = raw.strip()
    if not text:
        raise ValueError("must not be empty")
    if "/" in text or "\\" in text:
        raise ValueError(f"must not contain path separators, got {text!r}")
    return text


def _log_level(raw: str) -> str:
    """Parse a logging level name."""
    text = raw.strip().upper()
    if text not in _LOG_LEVELS:
        raise ValueError(f"expected one of {list(_LOG_LEVELS)}, got {raw.strip()!r}")
    return text


SECTION_SCHEMAS: dict[str, tuple[OptionSpec, ...]] = {
    "service": (
        OptionSpec(
            "state_directory",
            _posix_path,
            default="/var/lib/file-mover",
            description="Durable state root.",
        ),
        OptionSpec(
            "database_path",
            _posix_path,
            default="/var/lib/file-mover/jobs.db",
            description="Authoritative SQLite job/file state database.",
        ),
        OptionSpec(
            "manifest_directory",
            _posix_path,
            default="/var/lib/file-mover/manifests",
            description="Human-readable per-job manifests.",
        ),
        OptionSpec(
            "socket_path",
            _posix_path,
            default="/run/file-mover/control.sock",
            description="Unix control socket path.",
        ),
        OptionSpec(
            "shutdown_timeout_seconds",
            _int_converter(minimum=1),
            default="60",
            description="Grace period for in-flight work to checkpoint.",
        ),
        OptionSpec(
            "poll_interval_seconds",
            _float_converter(minimum=0.0, exclusive_minimum=True),
            default="2",
            description="Transfer scheduler poll interval, in seconds.",
        ),
    ),
    "control": (
        OptionSpec(
            "socket_mode",
            _octal_converter,
            default="0660",
            description="Control-socket permission bits (octal).",
        ),
        OptionSpec(
            "max_concurrent_requests",
            _int_converter(minimum=1),
            default="8",
            description="Control thread-pool size.",
        ),
        OptionSpec(
            "request_timeout_seconds",
            _int_converter(minimum=1),
            default="30",
            description="Per-request timeout.",
        ),
        OptionSpec(
            "maximum_message_bytes",
            _int_converter(minimum=1),
            default="1048576",
            description="Maximum accepted control-message size.",
        ),
    ),
    "paths": (
        OptionSpec(
            "allowed_source_roots",
            _posix_path_list,
            required=True,
            description="Absolute source roots submissions may draw from.",
        ),
        OptionSpec(
            "allowed_destination_roots",
            _posix_path_list,
            required=True,
            description="Absolute destination roots (different filesystem than sources).",
        ),
        OptionSpec(
            "claim_directory_name",
            _single_component_name,
            default=".swit-moving",
            description="Per-source staging directory name.",
        ),
        OptionSpec(
            "temporary_file_prefix",
            _nonempty_prefix,
            default=".swit-partial-",
            description="Prefix for in-progress destination files.",
        ),
        OptionSpec(
            "reject_symbolic_links",
            _to_bool,
            default="true",
            description="Reject symbolic links during inventory/claim.",
        ),
    ),
    "transfer": (
        OptionSpec(
            "max_concurrent_jobs",
            _int_converter(minimum=1),
            default="1",
            description="Number of active jobs.",
        ),
        OptionSpec(
            "max_concurrent_files",
            _int_converter(minimum=1),
            default="2",
            description="Files copied concurrently within a job.",
        ),
        OptionSpec(
            "copy_buffer_size_bytes",
            _int_converter(minimum=MINIMUM_COPY_BUFFER_SIZE_BYTES),
            default="8388608",
            description="Bounded copy buffer size (64 KiB floor).",
        ),
        OptionSpec(
            "max_bytes_per_second",
            _int_converter(minimum=0),
            default="0",
            description="Aggregate copy throughput ceiling in bytes/sec (0 = unlimited); "
            "adjustable at runtime with `file-mover throttle`.",
        ),
        OptionSpec(
            "retry_limit",
            _int_converter(minimum=0),
            default="10",
            description="Maximum automatic retry attempts (0 disables).",
        ),
        OptionSpec(
            "retry_initial_delay_seconds",
            _float_converter(minimum=0.0, exclusive_minimum=True),
            default="10",
            description="Backoff floor delay.",
        ),
        OptionSpec(
            "retry_max_delay_seconds",
            _float_converter(minimum=0.0),
            default="900",
            description="Backoff ceiling (>= initial delay).",
        ),
        OptionSpec(
            "use_kernel_copy",
            _to_bool,
            default="true",
            description="Attempt kernel-assisted copy (copy_file_range) with buffered fallback.",
        ),
        OptionSpec(
            "resume_partial_files",
            _to_bool,
            default="true",
            description="Resume an interrupted copy from its fsynced partial instead of "
            "restarting the file from byte zero.",
        ),
    ),
    "integrity": (
        OptionSpec(
            "enabled",
            _to_bool,
            default="true",
            description="Master switch for integrity verification.",
        ),
        OptionSpec(
            "mode",
            _enum_converter(IntegrityMode),
            default="source-and-destination-hash",
            description="metadata | source-hash | source-and-destination-hash.",
        ),
        OptionSpec(
            "algorithm",
            _enum_converter(HashAlgorithm),
            default="sha256",
            description="sha256 | sha512 | blake2b.",
        ),
    ),
    "stability": (
        OptionSpec(
            "enabled",
            _to_bool,
            default="true",
            description="Enable the source-stability defensive check.",
        ),
        OptionSpec(
            "poll_count",
            _int_converter(minimum=2),
            default="2",
            description="Number of metadata observations (>= 2).",
        ),
        OptionSpec(
            "poll_interval_seconds",
            _float_converter(minimum=0.0, exclusive_minimum=True),
            default="5",
            description="Seconds between observations.",
        ),
    ),
    "logging": (
        OptionSpec(
            "level",
            _log_level,
            default="INFO",
            description="DEBUG | INFO | WARNING | ERROR | OFF (OFF disables all logging).",
        ),
    ),
}

_REQUIRED_SECTIONS = frozenset(
    section for section, specs in SECTION_SCHEMAS.items() if any(spec.required for spec in specs)
)


# Loader


class ConfigurationLoader:
    """Loads and validates configuration into an immutable :class:`ApplicationConfig`."""

    def load(self, path: PurePosixPath | str) -> ApplicationConfig:
        """Load and validate configuration from an INI file.

        Args:
            path: Filesystem path to the configuration file.

        Returns:
            The validated, immutable configuration.

        Raises:
            ConfigurationError: If the path is invalid or the file cannot be read.
            ConfigurationValidationError: If the content is invalid.
        """
        resolved = _resolve_config_path(path)
        try:
            text = resolved.read_text(encoding="utf-8")
        except OSError as error:
            raise ConfigurationError(
                f"cannot read configuration file {resolved}: {error}"
            ) from error
        return self.load_text(text, source=str(resolved))

    def load_text(self, text: str, *, source: str = "<string>") -> ApplicationConfig:
        """Load and validate configuration from INI text.

        Args:
            text: The full INI document.
            source: A label used in parse-error messages.

        Returns:
            The validated, immutable configuration.

        Raises:
            ConfigurationValidationError: If the content is invalid.
        """
        parser = _read_parser(text, source)
        typed, issues = _structural_and_conversion_issues(parser)
        issues.extend(_cross_field_issues(typed))
        if issues:
            raise ConfigurationValidationError(issues)
        return _build_config(typed)


def _resolve_config_path(path: PurePosixPath | str) -> Path:
    """Validate and normalise an operator-supplied configuration path before reading it.

    The path comes from untrusted-shaped input (the ``--config`` flag or the systemd
    unit), so it is normalised to an absolute, symlink-resolved real path and confirmed to
    be an existing *regular file* before any filesystem read. NUL bytes and non-file
    targets are rejected up front rather than reaching :meth:`~pathlib.Path.read_text`,
    closing the path-injection vector.

    Raises:
        ConfigurationError: If the path is malformed, does not exist, or is not a regular
            file.
    """
    raw = str(path)
    if "\x00" in raw:
        raise ConfigurationError("configuration path must not contain a NUL byte")
    try:
        resolved = Path(raw).expanduser().resolve(strict=True)
    except OSError as error:
        raise ConfigurationError(f"cannot read configuration file {path}: {error}") from error
    if not resolved.is_file():
        raise ConfigurationError(f"configuration path is not a regular file: {resolved}")
    return resolved


def _read_parser(text: str, source: str) -> configparser.ConfigParser:
    """Parse INI text strictly, converting parse failures into a validation error."""
    parser = configparser.ConfigParser(strict=True, interpolation=None, delimiters=("=",))
    try:
        parser.read_string(text, source=source)
    except configparser.Error as error:
        message = " ".join(str(error).split())
        raise ConfigurationValidationError(
            [ConfigurationIssue(section="?", option=None, value=None, message=message)]
        ) from error
    return parser


def _structural_and_conversion_issues(
    parser: configparser.ConfigParser,
) -> tuple[dict[str, dict[str, object]], list[ConfigurationIssue]]:
    """Detect unknown/missing sections and options and convert present values."""
    issues: list[ConfigurationIssue] = _section_level_issues(parser)
    typed: dict[str, dict[str, object]] = {}
    for section, specs in SECTION_SCHEMAS.items():
        raw_items = dict(parser.items(section)) if parser.has_section(section) else {}
        values, section_issues = _convert_section(section, specs, raw_items)
        issues.extend(section_issues)
        typed[section] = values
    return typed, issues


def _section_level_issues(parser: configparser.ConfigParser) -> list[ConfigurationIssue]:
    """Report unknown present sections and missing required sections."""
    issues: list[ConfigurationIssue] = []
    present_sections = set(parser.sections())
    known_sections = set(SECTION_SCHEMAS)
    for section in sorted(present_sections - known_sections):
        issues.append(
            ConfigurationIssue(
                section, None, None, f"unknown section; valid sections: {sorted(known_sections)}"
            )
        )
    for section in sorted(_REQUIRED_SECTIONS - present_sections):
        issues.append(ConfigurationIssue(section, None, None, "required section is missing"))
    return issues


def _convert_section(
    section: str, specs: tuple[OptionSpec, ...], raw_items: dict[str, str]
) -> tuple[dict[str, object], list[ConfigurationIssue]]:
    """Convert one section's raw options, collecting unknown-option and conversion issues."""
    issues: list[ConfigurationIssue] = []
    spec_by_name = {spec.name: spec for spec in specs}
    for key in sorted(set(raw_items) - set(spec_by_name)):
        issues.append(
            ConfigurationIssue(
                section,
                key,
                raw_items[key],
                f"unknown option; valid options: {sorted(spec_by_name)}",
            )
        )
    values: dict[str, object] = {}
    for spec in specs:
        if spec.name in raw_items:
            raw = raw_items[spec.name]
        elif spec.required:
            issues.append(
                ConfigurationIssue(section, spec.name, None, "required option is missing")
            )
            continue
        else:
            raw = spec.default
        try:
            values[spec.name] = spec.converter(raw)
        except ValueError as error:
            issues.append(ConfigurationIssue(section, spec.name, raw, str(error)))
    return values, issues


def _cross_field_issues(typed: dict[str, dict[str, object]]) -> list[ConfigurationIssue]:
    """Validate constraints that span multiple options (guarded on presence)."""
    issues: list[ConfigurationIssue] = []
    issues.extend(_retry_delay_issues(typed))
    issues.extend(_root_overlap_issues(typed))
    issues.extend(_state_directory_issues(typed))
    return issues


def _retry_delay_issues(typed: dict[str, dict[str, object]]) -> list[ConfigurationIssue]:
    """Ensure the backoff ceiling is not below the backoff floor."""
    transfer = typed.get("transfer", {})
    initial = transfer.get("retry_initial_delay_seconds")
    maximum = transfer.get("retry_max_delay_seconds")
    if isinstance(initial, float) and isinstance(maximum, float) and maximum < initial:
        return [
            ConfigurationIssue(
                "transfer",
                "retry_max_delay_seconds",
                str(maximum),
                f"must be >= retry_initial_delay_seconds ({initial})",
            )
        ]
    return []


def _root_overlap_issues(typed: dict[str, dict[str, object]]) -> list[ConfigurationIssue]:
    """Reject any source root that overlaps a destination root (either nested in the other)."""
    paths = typed.get("paths", {})
    sources = paths.get("allowed_source_roots")
    destinations = paths.get("allowed_destination_roots")
    if not (isinstance(sources, tuple) and isinstance(destinations, tuple)):
        return []
    return [
        ConfigurationIssue(
            "paths",
            "allowed_destination_roots",
            str(destination),
            f"source and destination roots must not overlap ({source} vs {destination})",
        )
        for source in sources
        for destination in destinations
        if _overlaps(source, destination)
    ]


def _state_directory_issues(typed: dict[str, dict[str, object]]) -> list[ConfigurationIssue]:
    """Reject a state directory located inside (or equal to) an allowed source root.

    Directional: a source root nested under the state directory is fine; only the reverse
    is rejected.
    """
    state_directory = typed.get("service", {}).get("state_directory")
    sources = typed.get("paths", {}).get("allowed_source_roots")
    if not (isinstance(state_directory, PurePosixPath) and isinstance(sources, tuple)):
        return []
    return [
        ConfigurationIssue(
            "service",
            "state_directory",
            str(state_directory),
            f"state directory must not be inside an allowed source root ({source})",
        )
        for source in sources
        if state_directory == source or state_directory.is_relative_to(source)
    ]


def _overlaps(first: PurePosixPath, second: PurePosixPath) -> bool:
    """Return True if either path is equal to or nested within the other."""
    return first == second or first.is_relative_to(second) or second.is_relative_to(first)


def _build_config(typed: dict[str, dict[str, object]]) -> ApplicationConfig:
    """Assemble the frozen configuration from validated, typed values."""
    service = typed["service"]
    control = typed["control"]
    paths = typed["paths"]
    transfer = typed["transfer"]
    integrity = typed["integrity"]
    stability = typed["stability"]
    logging = typed["logging"]
    return ApplicationConfig(
        service=ServiceConfig(
            state_directory=cast(PurePosixPath, service["state_directory"]),
            database_path=cast(PurePosixPath, service["database_path"]),
            manifest_directory=cast(PurePosixPath, service["manifest_directory"]),
            socket_path=cast(PurePosixPath, service["socket_path"]),
            shutdown_timeout_seconds=cast(int, service["shutdown_timeout_seconds"]),
            poll_interval_seconds=cast(float, service["poll_interval_seconds"]),
        ),
        control=ControlConfig(
            socket_mode=cast(int, control["socket_mode"]),
            max_concurrent_requests=cast(int, control["max_concurrent_requests"]),
            request_timeout_seconds=cast(int, control["request_timeout_seconds"]),
            maximum_message_bytes=cast(int, control["maximum_message_bytes"]),
        ),
        paths=PathPolicyConfig(
            allowed_source_roots=cast("tuple[PurePosixPath, ...]", paths["allowed_source_roots"]),
            allowed_destination_roots=cast(
                "tuple[PurePosixPath, ...]", paths["allowed_destination_roots"]
            ),
            claim_directory_name=cast(str, paths["claim_directory_name"]),
            temporary_file_prefix=cast(str, paths["temporary_file_prefix"]),
            reject_symbolic_links=cast(bool, paths["reject_symbolic_links"]),
        ),
        transfer=TransferConfig(
            max_concurrent_jobs=cast(int, transfer["max_concurrent_jobs"]),
            max_concurrent_files=cast(int, transfer["max_concurrent_files"]),
            copy_buffer_size_bytes=cast(int, transfer["copy_buffer_size_bytes"]),
            max_bytes_per_second=cast(int, transfer["max_bytes_per_second"]),
            retry_limit=cast(int, transfer["retry_limit"]),
            retry_initial_delay_seconds=cast(float, transfer["retry_initial_delay_seconds"]),
            retry_max_delay_seconds=cast(float, transfer["retry_max_delay_seconds"]),
            use_kernel_copy=cast(bool, transfer["use_kernel_copy"]),
            resume_partial_files=cast(bool, transfer["resume_partial_files"]),
        ),
        integrity=IntegrityConfig(
            enabled=cast(bool, integrity["enabled"]),
            mode=cast(IntegrityMode, integrity["mode"]),
            algorithm=cast(HashAlgorithm, integrity["algorithm"]),
        ),
        stability=StabilityConfig(
            enabled=cast(bool, stability["enabled"]),
            poll_count=cast(int, stability["poll_count"]),
            poll_interval_seconds=cast(float, stability["poll_interval_seconds"]),
        ),
        logging=LoggingConfig(level=cast(str, logging["level"])),
    )


def configuration_advisories(config: ApplicationConfig) -> list[str]:
    """Return operator advisories for valid-but-consequential option combinations.

    These are **not** errors — the configuration is valid — but the combinations have
    non-obvious consequences (see ``docs/FEATURE-INTERACTIONS.md``). They are surfaced by
    ``file-mover doctor`` and logged once at service start, never raised.
    """
    notes: list[str] = []
    transfer = config.transfer
    if transfer.max_bytes_per_second > 0 and transfer.use_kernel_copy:
        notes.append(
            "a bandwidth limit is set with use_kernel_copy=true; kernel-assisted copy is "
            "bypassed while the limit is active (throttle 0 restores it)."
        )
    verifies_destination = (
        config.integrity.enabled
        and config.integrity.mode is IntegrityMode.SOURCE_AND_DESTINATION_HASH
    )
    if transfer.resume_partial_files and not verifies_destination:
        notes.append(
            "resume_partial_files=true without integrity.mode=source-and-destination-hash; "
            "a crash-interrupted resume may not detect a corrupted partial."
        )
    return notes


def describe_schema() -> str:
    """Render the option schema as human-readable reference text.

    Generated from the same :data:`SECTION_SCHEMAS` used for validation, so the two can
    never drift (L2-CFG-011).

    Returns:
        A multi-line description of every section and option.
    """
    lines: list[str] = []
    for section, specs in SECTION_SCHEMAS.items():
        lines.append(f"[{section}]")
        for spec in specs:
            requirement = "required" if spec.required else f"default: {spec.default!r}"
            lines.append(f"  {spec.name} ({requirement}) - {spec.description}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
