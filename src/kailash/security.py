"""
Comprehensive Security Framework for the Kailash SDK.

This module provides an extensive security framework designed to protect against
common vulnerabilities and ensure safe execution of workflows, particularly in
cyclic patterns where long-running processes may be exposed to additional risks.
It implements defense-in-depth strategies with configurable policies.

Design Philosophy:
    Implements a comprehensive security-first approach with fail-safe defaults,
    defense-in-depth strategies, and extensive monitoring. Designed to protect
    against both common web vulnerabilities and workflow-specific attack vectors
    while maintaining usability and performance.

Key Security Features:
    - **Path Security**: Comprehensive path traversal prevention
    - **Input Validation**: Multi-layer input sanitization and validation
    - **Execution Security**: Safe code execution with sandboxing
    - **Resource Limits**: Memory, CPU, and execution time constraints
    - **Injection Protection**: Command and code injection prevention
    - **Audit Logging**: Comprehensive security event logging

Cycle Security Enhancements (v0.2.0):
    Enhanced security specifically for cyclic workflows including:
    - Long-running process monitoring and limits
    - Iteration-based resource accumulation detection
    - Parameter injection attack prevention in cycles
    - State corruption detection and prevention
    - Convergence manipulation attack detection

Security Layers:
    1. **Input Layer**: Validation and sanitization of all inputs
    2. **Execution Layer**: Sandboxed execution with resource limits
    3. **File System Layer**: Controlled file access with path validation
    4. **Network Layer**: Controlled external communication
    5. **Monitoring Layer**: Real-time security event detection

Vulnerability Protection:
    - **Path Traversal**: Comprehensive path validation and canonicalization
    - **Command Injection**: Input sanitization and safe command execution
    - **Code Injection**: AST validation and safe code execution
    - **Resource Exhaustion**: Memory, CPU, and time limits
    - **Information Disclosure**: Controlled error messages and logging
    - **Privilege Escalation**: Sandboxed execution environments

Core Components:
    - SecurityConfig: Centralized security policy configuration
    - ValidationFramework: Multi-layer input validation system
    - ExecutionSandbox: Safe code execution environment
    - ResourceMonitor: Real-time resource usage monitoring
    - AuditLogger: Comprehensive security event logging

Upstream Dependencies:
    - Operating system security features for sandboxing
    - Python security libraries for validation and monitoring
    - Workflow execution framework for integration points

Downstream Consumers:
    - All workflow execution components requiring security
    - Node implementations with external resource access
    - Runtime engines executing user-provided code
    - API endpoints handling external workflow requests

Examples:
    Basic security configuration:

    >>> from kailash.security import SecurityConfig, validate_node_parameters
    >>> # Configure security policy
    >>> config = SecurityConfig(
    ...     max_execution_time=300,
    ...     max_memory_mb=1024,
    ...     allowed_paths=["/safe/directory"]
    ... )
    >>> # Validate node parameters
    >>> validate_node_parameters(parameters, config)

    Secure file operations:

    >>> from kailash.security import safe_file_operation, validate_path
    >>> # Validate and access file safely
    >>> safe_path = validate_path("/user/input/path", base_dir="/safe/root")
    >>> with safe_file_operation(safe_path, "r") as f:
    ...     content = f.read()

    Execution timeout protection:

    >>> from kailash.security import execution_timeout
    >>> @execution_timeout(seconds=30)
    ... def potentially_long_running_function():
    ...     # Function will be terminated if it runs longer than 30 seconds
    ...     return process_data()

    Comprehensive monitoring:

    >>> from kailash.security import SecurityMonitor
    >>> monitor = SecurityMonitor()
    >>> with monitor.track_execution("workflow_execution"):
    ...     # All security events will be monitored and logged
    ...     runtime.execute(workflow)

Security Policies:
    Configurable security policies allow adaptation to different environments:
    - **Development**: Relaxed policies for debugging and testing
    - **Staging**: Moderate policies balancing security and functionality
    - **Production**: Strict policies prioritizing security
    - **High-Security**: Maximum security for sensitive environments

See Also:
    - :mod:`kailash.nodes.code.python` for secure code execution
    - :mod:`kailash.workflow.safety` for workflow-specific safety measures
    - :doc:`/guides/security` for comprehensive security best practices
"""

import importlib.util
import logging
import os
import re
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Any

try:
    import resource  # Unix-only module
except ImportError:  # pragma: no cover - Windows
    resource = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class SecurityError(Exception):
    """Raised when a security policy violation is detected."""


class PathTraversalError(SecurityError):
    """Raised when path traversal attempt is detected."""


class CommandInjectionError(SecurityError):
    """Raised when command injection attempt is detected."""


class ExecutionTimeoutError(SecurityError):
    """Raised when execution exceeds allowed time limit."""


class MemoryLimitError(SecurityError):
    """Raised when memory usage exceeds allowed limit."""


class SecurityConfig:
    """Configuration for security policies and limits."""

    def __init__(
        self,
        allowed_directories: list[str] | None = None,
        max_file_size: int = 100 * 1024 * 1024,  # 100MB
        execution_timeout: float = 300.0,  # 5 minutes
        memory_limit: int = 512 * 1024 * 1024,  # 512MB
        allowed_file_extensions: list[str] | None = None,
        enable_audit_logging: bool = True,
        enable_path_validation: bool = True,
        enable_command_validation: bool = True,
    ):
        """
        Initialize security configuration.

        Args:
            allowed_directories: List of directories where file operations are permitted
            max_file_size: Maximum file size in bytes
            execution_timeout: Maximum execution time in seconds
            memory_limit: Maximum memory usage in bytes
            allowed_file_extensions: List of allowed file extensions
            enable_audit_logging: Whether to log security events
            enable_path_validation: Whether to validate file paths
            enable_command_validation: Whether to validate command strings
        """
        default_dirs = [
            os.path.expanduser("~/.kailash"),
            tempfile.gettempdir(),  # Allow all temp directories
            os.getcwd(),
            "/tmp",  # Unix temp directory
            "/var/tmp",  # Unix temp directory
        ]

        # Check for additional allowed directories from environment
        env_dirs = os.environ.get("KAILASH_ALLOWED_DIRS", "")
        if env_dirs:
            for dir_path in env_dirs.split(":"):
                if dir_path and os.path.isdir(dir_path):
                    default_dirs.append(os.path.abspath(dir_path))

        self.allowed_directories = allowed_directories or default_dirs
        self.max_file_size = max_file_size
        self.execution_timeout = execution_timeout
        self.memory_limit = memory_limit
        self.allowed_file_extensions = allowed_file_extensions or [
            ".txt",
            ".csv",
            ".tsv",
            ".json",
            ".yaml",
            ".yml",
            ".py",
            ".md",
            ".xml",
            ".log",
            ".dat",
            ".conf",
            ".cfg",
            ".ini",
            ".properties",
            ".html",
            ".htm",
            ".xhtml",
            ".jsonl",
            ".ndjson",
        ]
        self.enable_audit_logging = enable_audit_logging
        self.enable_path_validation = enable_path_validation
        self.enable_command_validation = enable_command_validation


# Global security configuration
_security_config = SecurityConfig()


def get_security_config() -> SecurityConfig:
    """Get the current security configuration."""
    return _security_config


def set_security_config(config: SecurityConfig) -> None:
    """Set the global security configuration."""
    global _security_config
    _security_config = config


def validate_file_path(
    file_path: str | Path,
    config: SecurityConfig | None = None,
    operation: str = "access",
) -> Path:
    """
    Validate and sanitize file paths to prevent traversal attacks.

    Args:
        file_path: The file path to validate
        config: Security configuration (uses global if None)
        operation: Description of the operation for logging

    Returns:
        Validated and normalized Path object

    Raises:
        PathTraversalError: If path traversal attempt is detected
        SecurityError: If path is outside allowed directories

    Examples:
        >>> # Safe paths
        >>> validate_file_path("data/file.txt")
        PosixPath('data/file.txt')

        >>> # Blocked paths
        >>> validate_file_path("../../../etc/passwd")
        Traceback (most recent call last):
        PathTraversalError: Path traversal attempt detected
    """
    if config is None:
        config = get_security_config()

    if not config.enable_path_validation:
        return Path(file_path)

    try:
        # Convert to Path and resolve to absolute path
        path = Path(file_path).resolve()

        # Check for path traversal indicators
        path_str = str(path)
        if ".." in str(file_path):
            if config.enable_audit_logging:
                logger.warning(
                    f"Path traversal attempt detected: {file_path} -> {path}"
                )
            raise PathTraversalError(f"Path traversal attempt detected: {file_path}")

        # Check for access to sensitive system directories
        sensitive_dirs = ["/etc", "/var", "/usr", "/root", "/boot", "/sys", "/proc"]
        if any(path_str.startswith(sensitive) for sensitive in sensitive_dirs):
            if config.enable_audit_logging:
                logger.warning(
                    f"Path traversal attempt detected: {file_path} -> {path}"
                )
            raise PathTraversalError(f"Path traversal attempt detected: {file_path}")

        # Validate file extension
        if path.suffix and path.suffix.lower() not in config.allowed_file_extensions:
            if config.enable_audit_logging:
                logger.warning(f"File extension not allowed: {path.suffix} in {path}")
            raise SecurityError(f"File extension not allowed: {path.suffix}")

        # Check if path is within allowed directories
        path_in_allowed_dir = False
        for allowed_dir in config.allowed_directories:
            try:
                allowed_path = Path(allowed_dir).resolve()
                # Use more robust relative path checking
                try:
                    path.relative_to(allowed_path)
                    path_in_allowed_dir = True
                    break
                except ValueError:
                    # Try alternative method for compatibility
                    if str(path).startswith(str(allowed_path)):
                        path_in_allowed_dir = True
                        break
            except (ValueError, OSError):
                # Handle cases where path resolution fails
                if str(path).startswith(str(allowed_dir)):
                    path_in_allowed_dir = True
                    break

        if not path_in_allowed_dir:
            if config.enable_audit_logging:
                logger.warning(f"Path outside allowed directories: {path}")
            raise SecurityError(f"Path outside allowed directories: {path}")

        if config.enable_audit_logging:
            logger.info(f"File path validated for {operation}: {path}")

        return path

    except (OSError, ValueError) as e:
        if config.enable_audit_logging:
            logger.error(f"Path validation error: {e}")
        raise SecurityError(f"Invalid file path: {file_path}")


def safe_open(
    file_path: str | Path,
    mode: str = "r",
    config: SecurityConfig | None = None,
    **kwargs,
):
    """
    Safely open a file with security validation.

    Args:
        file_path: Path to the file
        mode: File open mode
        config: Security configuration
        **kwargs: Additional arguments for open()

    Returns:
        File handle

    Raises:
        SecurityError: If security validation fails

    Examples:
        >>> with safe_open("data/file.txt", "r") as f:
        ...     content = f.read()
    """
    if config is None:
        config = get_security_config()

    # Validate the file path
    validated_path = validate_file_path(file_path, config, f"open({mode})")

    # Check file size for read operations
    if "r" in mode and validated_path.exists():
        file_size = validated_path.stat().st_size
        if file_size > config.max_file_size:
            raise SecurityError(
                f"File too large: {file_size} bytes > {config.max_file_size}"
            )

    # Create directory if writing and it doesn't exist
    if "w" in mode or "a" in mode:
        validated_path.parent.mkdir(parents=True, exist_ok=True)

    if config.enable_audit_logging:
        logger.info(f"Opening file: {validated_path} (mode: {mode})")

    return open(validated_path, mode, **kwargs)


def validate_command_string(command: str, config: SecurityConfig | None = None) -> str:
    """
    Validate command strings to prevent injection attacks.

    Args:
        command: Command string to validate
        config: Security configuration

    Returns:
        Validated command string

    Raises:
        CommandInjectionError: If command injection attempt is detected
    """
    if config is None:
        config = get_security_config()

    if not config.enable_command_validation:
        return command

    # Check for common injection patterns
    dangerous_patterns = [
        r";",  # Command chaining
        r"&&",  # Logical AND command chaining
        r"\|\|",  # Logical OR command chaining
        r"\|",  # Pipe operations
        r"\$\(",  # Command substitution
        r"`.*`",  # Backtick command substitution
        r">\s*/dev/",  # Redirect to devices
        r"<.*>",  # Input/output redirection
        r"\beval\b",  # eval command
        r"\bexec\b",  # exec command
        r"rm\s+.*(\/|\*)",  # rm with dangerous paths
        r"cat\s+\/etc\/",  # reading system files
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, command, re.IGNORECASE):
            if config.enable_audit_logging:
                logger.warning(f"Command injection attempt detected: {command}")
            raise CommandInjectionError(f"Potentially dangerous command: {command}")

    if config.enable_audit_logging:
        logger.info(
            f"Command validated: {command[:100]}{'...' if len(command) > 100 else ''}"
        )

    return command


# P0D-002 / #2000: Presence-keyed, lazily-resolved cache for the allow-list that
# sanitize_input() applies when the caller passes allowed_types=None.
#
# WHY sys.modules INSTEAD OF import
# ---------------------------------
# The allow-list is consumed by exactly one operation: ``isinstance(value, t)``.
# A value can only BE an instance of ``torch.Tensor`` if the module defining that
# class has already executed in this process -- that is, if ``torch`` is already
# in ``sys.modules``. So consulting ``sys.modules`` instead of *importing* the
# framework is VERDICT-PRESERVING: every value the eager implementation would
# have accepted is still accepted, because holding such a value requires the
# framework to have been loaded first.
#
# The previous implementation imported every installed optional framework
# (torch, sklearn, scipy, pandas, xgboost, lightgbm, plotly, PIL, networkx, ...)
# the first time any node validated a parameter. On a machine with torch and
# sklearn installed that cost 7-9s on the FIRST PythonCodeNode execution of a
# process (kailash-py#2000), and it made node execution fail outright on a broken
# or partially-installed ML stack.
#
# SECURITY DIRECTION -- and the TWO places the verdict genuinely changed
# ----------------------------------------------------------------------
# For the optional-framework groups below the substitution is verdict-preserving:
# a value can only be an instance of a framework's type if that framework is
# loaded, so keying on sys.modules admits exactly what importing admitted.
# Resolution failures are logged at WARNING and fail closed -- the group's types
# are absent, so such values are rejected rather than silently admitted.
#
# Two verdicts DID change, and the blanket claim "this can only ever be narrower"
# that an earlier revision of this comment made was FALSE. Recorded explicitly so
# the next reader does not have to rediscover them:
#
#   1. sklearn under coverage (WIDER than before). The old sklearn branch was
#      wrapped in `if "coverage" not in sys.modules`, so a process running under
#      coverage REJECTED BaseEstimator/TransformerMixin values that every normal
#      process accepted. That guard existed to dodge the import cost/instrument-
#      ation conflict, not to express a security policy, and nothing imports
#      sklearn here any more -- so it is gone and coverage runs now agree with
#      production. This is a deliberate widening, limited to processes running
#      under coverage, and it makes the security surface stop depending on
#      whether the code is being measured.
#   2. The pandas name-based branch in sanitize_input() -- see the comment at
#      that block, which preserves its old verdict exactly via find_spec.
_BASE_ALLOWED_TYPES: tuple[type, ...] = (
    str,
    int,
    float,
    bool,
    list,
    dict,
    tuple,
    set,
    type(None),
)


def _resolve_pandas_types() -> list[type]:
    import pandas as pd

    return [
        pd.DataFrame,
        pd.Series,
        pd.Index,
        pd.MultiIndex,
        pd.Categorical,
        pd.Timestamp,
        pd.Timedelta,
        pd.Period,
        pd.DatetimeIndex,
        pd.TimedeltaIndex,
        pd.PeriodIndex,
    ]


def _resolve_numpy_types() -> list[type]:
    import numpy as np

    numpy_types: list[type] = [
        np.ndarray,
        np.ma.MaskedArray,
        np.int8,
        np.int16,
        np.int32,
        np.int64,
        np.uint8,
        np.uint16,
        np.uint32,
        np.uint64,
        np.float16,
        np.float32,
        np.float64,
        np.complex64,
        np.complex128,
        np.bool_,
        np.object_,
        np.datetime64,
        np.timedelta64,
    ]

    if hasattr(np, "matrix"):
        numpy_types.append(np.matrix)
    if hasattr(np, "string_"):
        numpy_types.append(getattr(np, "string_"))
    elif hasattr(np, "bytes_"):
        numpy_types.append(np.bytes_)
    if hasattr(np, "unicode_"):
        numpy_types.append(getattr(np, "unicode_"))
    elif hasattr(np, "str_"):
        numpy_types.append(np.str_)
    if hasattr(np, "float128"):
        numpy_types.append(np.float128)
    if hasattr(np, "complex256"):
        numpy_types.append(np.complex256)
    if hasattr(np, "generic"):
        numpy_types.append(np.generic)

    return numpy_types


def _resolve_torch_types() -> list[type]:
    import torch

    torch_types: list[type] = [
        torch.Tensor,
        torch.nn.Module,
        torch.nn.Parameter,
    ]
    for cuda_type_name in ("FloatTensor", "DoubleTensor", "IntTensor", "LongTensor"):
        cuda_type = getattr(torch.cuda, cuda_type_name, None)
        if cuda_type is not None:
            torch_types.append(cuda_type)
    return torch_types


def _resolve_tensorflow_types() -> list[type]:
    import importlib

    tf = importlib.import_module("tensorflow")
    return [
        tf.Tensor,
        tf.Variable,
        tf.constant,
        tf.keras.Model,
        tf.keras.layers.Layer,
        tf.data.Dataset,
    ]


def _resolve_scipy_sparse_types() -> list[type]:
    import scipy.sparse

    return [
        scipy.sparse.csr_matrix,
        scipy.sparse.csc_matrix,
        scipy.sparse.coo_matrix,
        scipy.sparse.dia_matrix,
        scipy.sparse.dok_matrix,
        scipy.sparse.lil_matrix,
    ]


def _resolve_sklearn_types() -> list[type]:
    from sklearn.base import BaseEstimator, TransformerMixin

    return [BaseEstimator, TransformerMixin]


def _resolve_xgboost_types() -> list[type]:
    import importlib

    xgb = importlib.import_module("xgboost")
    return [xgb.DMatrix, xgb.Booster]


def _resolve_lightgbm_types() -> list[type]:
    import importlib

    lgb = importlib.import_module("lightgbm")
    return [lgb.Dataset, lgb.Booster]


def _resolve_matplotlib_types() -> list[type]:
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

    return [Figure, Axes]


def _resolve_plotly_types() -> list[type]:
    import plotly.graph_objects as go

    return [go.Figure]


def _resolve_statsmodels_types() -> list[type]:
    import importlib

    sm = importlib.import_module("statsmodels.api")
    return [sm.OLS, sm.GLM, sm.GLS, sm.WLS]


def _resolve_pillow_types() -> list[type]:
    from PIL import Image

    return [Image.Image]


def _resolve_spacy_types() -> list[type]:
    import importlib

    spacy_tokens = importlib.import_module("spacy.tokens")
    return [spacy_tokens.Doc, spacy_tokens.Span, spacy_tokens.Token]


def _resolve_networkx_types() -> list[type]:
    import networkx as nx

    return [nx.Graph, nx.DiGraph, nx.MultiGraph, nx.MultiDiGraph]


def _resolve_prophet_types() -> list[type]:
    import importlib

    prophet_mod = importlib.import_module("prophet")
    prophet_forecaster = importlib.import_module("prophet.forecaster")
    return [prophet_mod.Prophet, prophet_forecaster.Prophet]


# Each entry is (probe module names, resolver). The group contributes its types
# only when at least one probe module is already in sys.modules. A probe is the
# module in which the group's types are DEFINED (or the package whose __init__
# unconditionally executes that module), which is precisely the module that must
# have run for an instance of those types to exist.
#
# `cv2` had an entry in the eager implementation that imported OpenCV and added
# ZERO types to the allow-list; it is intentionally not carried over, because it
# only ever cost import time.
_OPTIONAL_TYPE_GROUPS: tuple[tuple[tuple[str, ...], Callable[[], list[type]]], ...] = (
    (("pandas",), _resolve_pandas_types),
    (("numpy",), _resolve_numpy_types),
    (("torch",), _resolve_torch_types),
    (("tensorflow",), _resolve_tensorflow_types),
    (("scipy.sparse",), _resolve_scipy_sparse_types),
    (("sklearn.base",), _resolve_sklearn_types),
    (("xgboost",), _resolve_xgboost_types),
    (("lightgbm",), _resolve_lightgbm_types),
    (("matplotlib.figure", "matplotlib.axes"), _resolve_matplotlib_types),
    (("plotly.graph_objects",), _resolve_plotly_types),
    (("statsmodels.api",), _resolve_statsmodels_types),
    (("PIL.Image",), _resolve_pillow_types),
    (("spacy.tokens",), _resolve_spacy_types),
    (("networkx",), _resolve_networkx_types),
    (("prophet",), _resolve_prophet_types),
)

_OPTIONAL_PROBE_NAMES: tuple[str, ...] = tuple(
    dict.fromkeys(name for probes, _ in _OPTIONAL_TYPE_GROUPS for name in probes)
)

# Single-entry cache holding (loaded-framework signature, frozen allow-list).
# Stored as ONE tuple so a concurrent reader always observes a consistent pair:
# a torn read of two separate globals could otherwise pair a stale (narrower)
# allow-list with a fresh signature and cache it indefinitely.
_ALLOWED_TYPES_CACHE: tuple[tuple[str, ...], tuple[type, ...]] | None = None

# Back-compat mirror of the most recently computed allow-list. Nothing in the
# SDK reads it; it is asserted by
# tests/tier2_integration/runtime/test_phase0d_optimizations.py as the
# module-level P0D-002 cache symbol, so it is kept and kept accurate.
_CACHED_ALLOWED_TYPES: tuple[type, ...] | None = None


_MODULE_INSTALLED_CACHE: dict[str, bool] = {}


def _module_is_installed(module_name: str) -> bool:
    """Is ``module_name`` importable here, without importing it?

    ``find_spec`` locates a module without executing it, so this answers
    "installed?" at no import cost. Memoised because the answer cannot change
    within a process without a path-hook change, and the callers sit on the
    node-execution hot path. The cache is keyed by name and bounded by the small
    fixed set of names the SDK ever asks about.
    """
    cached = _MODULE_INSTALLED_CACHE.get(module_name)
    if cached is not None:
        return cached
    if module_name in sys.modules:
        installed = True
    else:
        try:
            installed = importlib.util.find_spec(module_name) is not None
        except (ImportError, AttributeError, ValueError):
            installed = False
    _MODULE_INSTALLED_CACHE[module_name] = installed
    return installed


def _loaded_optional_signature() -> tuple[str, ...]:
    """Return the probe modules currently present in sys.modules.

    This is the cache key. It is recomputed on every call (a handful of dict
    lookups, ~1us) so that a framework imported AFTER the first call is picked
    up -- without it, presence-keyed resolution would permanently miss any
    framework loaded later and wrongly reject its values.
    """
    modules = sys.modules
    return tuple(name for name in _OPTIONAL_PROBE_NAMES if name in modules)


def _get_cached_allowed_types() -> list[type]:
    """Return the allow-list for sanitize_input(), resolved from loaded modules.

    Builtin types are always present. An optional framework's types are added
    only when that framework is already imported in this process, which is a
    necessary condition for any value of those types to exist. No heavy import
    is ever performed here (#2000).
    """
    global _ALLOWED_TYPES_CACHE, _CACHED_ALLOWED_TYPES

    signature = _loaded_optional_signature()

    entry = _ALLOWED_TYPES_CACHE  # single atomic read of the (key, value) pair
    if entry is not None and entry[0] == signature:
        # Return a mutable copy so callers can safely extend if needed
        return list(entry[1])

    allowed_types: list[type] = list(_BASE_ALLOWED_TYPES)
    loaded = frozenset(signature)
    resolution_failed = False
    for probes, resolve in _OPTIONAL_TYPE_GROUPS:
        if loaded.isdisjoint(probes):
            continue
        try:
            allowed_types.extend(resolve())
        except (ImportError, AttributeError, OSError) as exc:
            resolution_failed = True
            # Fail closed and loudly: the framework is loaded but its types could
            # not be resolved, so values of those types will now be REJECTED by
            # sanitize_input(). Never silently pretend the group was resolved.
            logger.warning(
                "Optional type group %s is loaded but its allow-list types could "
                "not be resolved (%s: %s); values of those types will be rejected "
                "by input sanitization.",
                "/".join(probes),
                type(exc).__name__,
                exc,
            )

    frozen = tuple(allowed_types)
    _CACHED_ALLOWED_TYPES = frozen
    if not resolution_failed:
        _ALLOWED_TYPES_CACHE = (signature, frozen)
    else:
        # Do NOT cache a partial result. A framework can be mid-initialisation
        # (its parent package in sys.modules before its submodules finish), and
        # caching that transient failure would reject its values for the whole
        # process life with no way back. Retrying costs an attribute access --
        # the framework is already imported, so no import is repeated.
        _ALLOWED_TYPES_CACHE = None
    return list(frozen)


@contextmanager
def execution_timeout(
    timeout: float | None = None, config: SecurityConfig | None = None
):
    """
    Context manager to enforce execution timeouts.

    Args:
        timeout: Timeout in seconds (uses config default if None)
        config: Security configuration

    Raises:
        ExecutionTimeoutError: If execution exceeds timeout

    Examples:
        >>> with execution_timeout(30.0):
        ...     # Code that should complete within 30 seconds
        ...     time.sleep(5)
    """
    if config is None:
        config = get_security_config()

    if timeout is None:
        timeout = config.execution_timeout

    start_time = time.time()

    try:
        yield
    finally:
        elapsed_time = time.time() - start_time
        if elapsed_time > timeout:
            if config.enable_audit_logging:
                logger.warning(f"Execution timeout: {elapsed_time:.2f}s > {timeout}s")
            raise ExecutionTimeoutError(
                f"Execution timeout: {elapsed_time:.2f}s > {timeout}s"
            )


# --- Address-space (memory) limiting -----------------------------------------
#
# RLIMIT_AS is a PROCESS-WIDE limit. Lowering it to an absolute value from
# inside a library permanently cripples the embedding process: every later
# mmap in that process fails, including the 8 MB stack pthread_create needs,
# which surfaces as `RuntimeError: can't start new thread` and as
# `sqlite3.OperationalError: disk I/O error` in code that has nothing to do
# with the node that set the limit (issue #2078).
#
# The guard below is therefore bounded in BOTH directions:
#   * in VALUE  - the ceiling is (current address-space usage + limit), so the
#     limit bounds what the guarded block may ADD, never the footprint the
#     process already legitimately has;
#   * in TIME   - the previous soft limit is restored on exit, and only the
#     SOFT limit is ever touched so the change stays reversible (lowering the
#     HARD limit is a one-way door for an unprivileged process).
#
# Concurrent guarded blocks keep a list of every requested ceiling and the
# TIGHTEST one is what is applied. First-writer-wins would let a concurrent
# block with a loose limit host a payload that was configured with a strict
# one — a silent sandbox bypass, since nodes in a parallel group may each carry
# their own SecurityConfig. The lock is held only for that bookkeeping, never
# across the guarded block, so parallel node execution is not serialized.
#
# SCOPE OF THE GUARANTEE — read before treating this as a sandbox:
#   * It bounds ONE block's ADDITIONAL address space. It does NOT bound the
#     total footprint of a run: values a payload leaves alive (node outputs,
#     workflow context) raise `current`, so the next block's ceiling is
#     computed from a larger base. N sequential nodes can therefore retain
#     N x limit in aggregate.
#   * It is process-wide while in force, so a payload that consumes its whole
#     headroom starves unrelated threads in the same process for the duration.
#   * `execution_timeout` measures elapsed time AFTER the block returns; it does
#     not interrupt, so a spinning payload holds that state until it finishes.
# In-process execution of genuinely untrusted code is NOT made safe by this
# control. Run it in a subprocess with its own absolute rlimits — which is
# exactly what kaizen's IsolatedHookExecutor does, and why an absolute,
# irreversible cap is correct THERE and wrong here.
_ADDRESS_SPACE_LOCK = threading.Lock()
# Ceilings requested by currently-active guards. The tightest is applied.
_address_space_requests: list[int] = []
# The (soft, hard) pair in force before the first active guard touched it.
_address_space_saved: tuple[int, int] | None = None
# The ceiling currently applied to the process, or None if we applied nothing.
_address_space_applied: int | None = None
_address_space_unsupported_logged = False


def _log_address_space_unsupported(reason: str) -> None:
    """Log once that the address-space limit could not be applied.

    Once, not per execution: where it fails it fails identically every time,
    and a per-execution warning would bury the log without adding information.
    """
    global _address_space_unsupported_logged
    if _address_space_unsupported_logged:
        return
    _address_space_unsupported_logged = True
    logger.warning(
        "Memory limit is NOT enforced for in-process code execution on this "
        "platform (%s). Code executed by PythonCodeNode may allocate without "
        "bound. Run untrusted code in a subprocess if the limit must hold.",
        reason,
    )


def _current_address_space_bytes() -> int | None:
    """Return this process's current virtual address-space size, or None.

    Reads ``/proc/self/statm`` (field 0, total program size in pages). Returns
    None where /proc is absent or unreadable, which is the signal that the
    ceiling cannot be computed and the limit must not be applied.

    There is deliberately no fallback. Every portable alternative reports
    RESIDENT memory (``getrusage`` gives ``ru_maxrss``), and RLIMIT_AS caps
    ADDRESS SPACE, which on Linux runs several times larger. Sizing an
    address-space ceiling from a resident-memory reading would put the cap
    below the process's own footprint — issue #2078 exactly. Enforcing nothing
    and saying so is the safe branch.

    Consequence, and it is a real reduction in coverage: POSIX hosts that
    enforce RLIMIT_AS but have no /proc (the BSDs, a Linux container with /proc
    unmounted or hidepid-restricted) get no enforcement, where the pre-#2078
    code did enforce. They get the one-time warning instead.
    """
    try:
        with open("/proc/self/statm", "rb") as handle:
            pages = int(handle.read().split()[0])
    except (OSError, ValueError, IndexError):
        return None
    return pages * os.sysconf("SC_PAGE_SIZE")


def _enter_address_space_guard(limit: int) -> int | None:
    """Register a ceiling and apply it if it is the tightest. Caller holds lock.

    Returns the registered ceiling (to be passed back to the exit helper), or
    None when nothing was registered and no ceiling is in force for this guard.
    """
    global _address_space_saved, _address_space_applied

    current = _current_address_space_bytes()
    if current is None:
        _log_address_space_unsupported("address-space usage is not readable")
        return None

    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    ceiling = current + limit
    if hard != resource.RLIM_INFINITY:
        ceiling = min(ceiling, hard)

    # Compare against the limit that was in force BEFORE we touched anything;
    # once we have applied a ceiling, `soft` is our own value, not the
    # environment's.
    baseline_soft = _address_space_saved[0] if _address_space_saved else soft
    if baseline_soft != resource.RLIM_INFINITY and baseline_soft <= ceiling:
        # The environment is already at least as tight as we would ask for.
        return None

    _address_space_requests.append(ceiling)
    target = min(_address_space_requests)
    if target != _address_space_applied:
        try:
            resource.setrlimit(resource.RLIMIT_AS, (target, hard))
        except Exception as exc:  # noqa: BLE001 - see below
            # Deliberately broad. A narrow (OSError, ValueError) lets
            # OverflowError through from an over-large configured limit, and an
            # exception escaping here would leave this guard registered and
            # every later guard believing a ceiling is in force — the sandbox
            # would be silently off for the life of the process.
            _address_space_requests.pop()
            _log_address_space_unsupported(f"setrlimit(RLIMIT_AS) rejected: {exc}")
            return None
        if _address_space_saved is None:
            _address_space_saved = (soft, hard)
        _address_space_applied = target
    return ceiling


def _exit_address_space_guard(ceiling: int) -> None:
    """Deregister a ceiling, restoring or loosening as needed. Caller holds lock."""
    global _address_space_saved, _address_space_applied

    try:
        _address_space_requests.remove(ceiling)
    except ValueError:  # pragma: no cover - defensive; entry returned it
        return

    if _address_space_requests:
        target = min(_address_space_requests)
        if target != _address_space_applied and _address_space_saved is not None:
            try:
                resource.setrlimit(
                    resource.RLIMIT_AS, (target, _address_space_saved[1])
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Could not loosen RLIMIT_AS to %s after a guarded block "
                    "exited; the process stays at %s: %s",
                    target,
                    _address_space_applied,
                    exc,
                )
            else:
                _address_space_applied = target
        return

    if _address_space_saved is None:
        return

    try:
        resource.setrlimit(resource.RLIMIT_AS, _address_space_saved)
    except Exception as exc:  # noqa: BLE001
        # NOT cleared on failure. Clearing first would throw away the only
        # record of the pre-guard value, leaving the process capped forever
        # with nothing able to restore it — the #2078 failure mode, minus any
        # path to recovery. Keeping it lets the next guard's exit retry.
        logger.error(
            "Could not restore RLIMIT_AS to %s after guarded execution; this "
            "process's address space stays capped: %s",
            _address_space_saved,
            exc,
        )
    else:
        _address_space_saved = None
        _address_space_applied = None


@contextmanager
def memory_limit_guard(limit: int | None = None, config: SecurityConfig | None = None):
    """
    Context manager bounding how much address space the guarded block may add.

    Applies ``limit`` bytes of headroom above the process's CURRENT
    address-space usage for the duration of the block, then restores the
    previous soft limit. A ``MemoryError`` raised inside the block is
    translated to :class:`MemoryLimitError` — but only when this guard actually
    put a ceiling in force, so genuine host exhaustion is never misattributed.

    Concurrent guards apply the TIGHTEST requested ceiling, not the first one
    requested, so a block configured with a strict limit is never hosted under
    a laxer concurrent one.

    Where the platform cannot support the ceiling — no ``resource`` module or no
    ``RLIMIT_AS`` (Windows), no readable ``/proc`` (macOS, the BSDs), or a kernel
    that refuses ``setrlimit(RLIMIT_AS)`` — the block runs unguarded and a single
    warning is logged, on all three paths. That is a real gap, not a silent one:
    the limit is advertised as unenforced rather than pretended.

    This bounds ONE block's additional address space. It is not a sandbox for
    untrusted code, and it does not bound a run's total footprint; see the
    module comment above this function for the full scope of the guarantee.

    Args:
        limit: Additional address space the block may use, in bytes
            (uses ``config.memory_limit`` if None)
        config: Security configuration

    Raises:
        MemoryLimitError: If the guarded block exhausts the headroom

    Examples:
        >>> with memory_limit_guard(64 * 1024 * 1024):
        ...     data = [0] * 1000
    """
    if config is None:
        config = get_security_config()

    if limit is None:
        limit = config.memory_limit

    has_rlimit = resource is not None and hasattr(resource, "RLIMIT_AS")
    applicable = bool(limit) and has_rlimit

    # Warn HERE, not only from inside _enter_address_space_guard. That function
    # runs only when `applicable` is true, so on a platform with no RLIMIT_AS at
    # all (Windows: `resource` does not exist) the guard would otherwise apply no
    # ceiling AND emit no warning -- the silent failure this control exists to
    # avoid. `bool(limit)` is excluded deliberately: an unset limit is disabled
    # by configuration, not unenforceable by platform, and warning on it would
    # train readers to ignore the message.
    if limit and not has_rlimit:
        _log_address_space_unsupported(
            "the `resource` module is unavailable"
            if resource is None
            else "`resource.RLIMIT_AS` is not defined"
        )

    # Per-guard, never a module global: whether THIS guard put a ceiling in
    # force is what licenses relabelling a MemoryError as MemoryLimitError.
    registered: int | None = None
    if applicable:
        with _ADDRESS_SPACE_LOCK:
            registered = _enter_address_space_guard(limit)

    try:
        yield
    except MemoryError as exc:
        if registered is None:
            # Nothing was enforced, so this is genuine host exhaustion.
            # Relabelling it would name a cause that is not connected to
            # anything and send the reader to the wrong knob.
            raise
        raise MemoryLimitError(
            f"Memory limit exceeded: code execution requested more than "
            f"{limit} bytes of additional address space"
        ) from exc
    finally:
        if registered is not None:
            with _ADDRESS_SPACE_LOCK:
                _exit_address_space_guard(registered)


def sanitize_input(
    value: Any,
    max_length: int = 10000,
    allowed_types: list[type] | None = None,
    config: SecurityConfig | None = None,
    context: str = "generic",
) -> Any:
    """
    Sanitize input values to prevent injection attacks.

    Args:
        value: Value to sanitize
        max_length: Maximum string length
        allowed_types: List of allowed types
        config: Security configuration
        context: Execution context for context-aware sanitization.
            - "generic": Default moderate sanitization (backward compatible)
            - "python_exec": Python code execution (preserves shell metacharacters)
            - "shell_exec": Shell command execution (removes all dangerous characters)

    Returns:
        Sanitized value

    Raises:
        SecurityError: If input fails validation

    Note:
        The context parameter allows for appropriate security measures based on
        how the data will be used. Python code execution via exec() does not
        need shell metacharacter sanitization since characters like $, ;, &, |
        are regular Python string characters and not executed by a shell.
    """
    if config is None:
        config = get_security_config()

    if allowed_types is None:
        # P0D-002: Use cached allowed_types to avoid 13+ lazy imports per call.
        # The cache is computed once on first access and reused for all subsequent calls.
        allowed_types = _get_cached_allowed_types()

    # Type validation - allow data science types
    # Filter out non-types to avoid isinstance errors
    valid_types = [t for t in allowed_types if isinstance(t, type)]
    type_allowed = any(isinstance(value, t) for t in valid_types)

    # Force allow pandas DataFrame - it should always be allowed regardless of mocking
    # This handles test interference where pandas might be mocked.
    #
    # #2000: this block no longer IMPORTS pandas, but its verdict is preserved
    # EXACTLY, which takes two different gates:
    #   * the name-based branch never needed pandas loaded -- it only reads the
    #     value's own class. It historically ran whenever pandas was INSTALLED
    #     (the `import pandas` above it succeeded), so it is gated on
    #     installed-ness, checked via find_spec, which locates without executing.
    #     Gating it on loaded-ness instead would REJECT a polars/spark frame that
    #     was previously accepted; gating it on nothing would ACCEPT one on a
    #     machine with no pandas at all, where it was previously rejected.
    #   * the isinstance branch needs the real class, and a value can only BE a
    #     pandas DataFrame if pandas is already loaded, so loaded-ness is the
    #     exact gate there and costs no import.
    if not type_allowed and _module_is_installed("pandas"):
        if hasattr(value, "__class__") and "DataFrame" in str(value.__class__):
            # Covers a real DataFrame and a mock standing in for one alike.
            type_allowed = True
        elif "pandas" in sys.modules:
            try:
                import pandas as pd

                if isinstance(value, pd.DataFrame):
                    type_allowed = True
            except ImportError:
                pass

    # Additional check for numpy scalar types
    # #2000: gated on sys.modules. A value can only BE a numpy scalar if numpy is
    # already loaded, so this gate is exact and imports nothing.
    if not type_allowed and "numpy" in sys.modules:
        try:
            import numpy as np

            # Check if it's any numpy type
            if isinstance(value, np.generic):
                type_allowed = True
        except ImportError:
            pass

    if not type_allowed:
        raise SecurityError(f"Input type not allowed: {type(value)}")

    # String sanitization
    if isinstance(value, str):
        if len(value) > max_length:
            raise SecurityError(f"Input too long: {len(value)} > {max_length}")

        # Context-aware sanitization
        if context == "python_exec":
            # Python execution context: Only remove XSS patterns, preserve shell metacharacters
            # Python exec() does not execute shell commands, so $, ;, &, |, `, (, ) are safe
            sanitized = re.sub(
                r"<script.*?</script>", "", value, flags=re.IGNORECASE | re.DOTALL
            )
            sanitized = re.sub(r"javascript:", "", sanitized, flags=re.IGNORECASE)
            # Remove only the most dangerous HTML tags for XSS prevention
            sanitized = re.sub(
                r"</?(?:script|iframe|object|embed).*?>",
                "",
                sanitized,
                flags=re.IGNORECASE,
            )
        elif context == "shell_exec":
            # Shell execution context: Remove all shell metacharacters
            sanitized = re.sub(r"[<>;&|`$()]", "", value)
            sanitized = re.sub(
                r"<script.*?</script>", "", sanitized, flags=re.IGNORECASE | re.DOTALL
            )
            sanitized = re.sub(r"javascript:", "", sanitized, flags=re.IGNORECASE)
        else:
            # Generic context: Moderate sanitization (backward compatible)
            # Remove only basic XSS patterns, preserve most characters
            sanitized = re.sub(
                r"<script.*?</script>", "", value, flags=re.IGNORECASE | re.DOTALL
            )
            sanitized = re.sub(r"javascript:", "", sanitized, flags=re.IGNORECASE)
            # Remove angle brackets for basic XSS protection
            sanitized = re.sub(r"[<>]", "", sanitized)

        if sanitized != value and config.enable_audit_logging:
            logger.warning(
                f"Input sanitized ({context}): {value[:50]}... -> {sanitized[:50]}..."
            )

        return sanitized

    # Dictionary sanitization (recursive)
    if isinstance(value, dict):
        return {
            sanitize_input(
                k, max_length, allowed_types, config, context
            ): sanitize_input(v, max_length, allowed_types, config, context)
            for k, v in value.items()
        }

    # List sanitization (recursive)
    if isinstance(value, list):
        return [
            sanitize_input(item, max_length, allowed_types, config, context)
            for item in value
        ]

    return value


def create_secure_temp_dir(
    prefix: str = "kailash_", config: SecurityConfig | None = None
) -> Path:
    """
    Create a secure temporary directory.

    Args:
        prefix: Prefix for the directory name
        config: Security configuration

    Returns:
        Path to the secure temporary directory
    """
    if config is None:
        config = get_security_config()

    # Create temp directory with secure permissions
    temp_dir = Path(tempfile.mkdtemp(prefix=prefix))

    # Set restrictive permissions (owner only)
    temp_dir.chmod(0o700)

    if config.enable_audit_logging:
        logger.info(f"Created secure temp directory: {temp_dir}")

    return temp_dir


def validate_node_parameters(
    parameters: dict[str, Any],
    config: SecurityConfig | None = None,
    context: str = "generic",
) -> dict[str, Any]:
    """
    Validate and sanitize node parameters.

    Args:
        parameters: Node parameters to validate
        config: Security configuration
        context: Execution context for context-aware sanitization
            - "generic": Default moderate sanitization
            - "python_exec": Python code execution (preserves shell metacharacters)
            - "shell_exec": Shell command execution (removes all dangerous characters)

    Returns:
        Validated and sanitized parameters

    Raises:
        SecurityError: If parameters fail validation
    """
    if config is None:
        config = get_security_config()

    validated_params = {}

    for key, value in parameters.items():
        # Sanitize parameter key
        clean_key = sanitize_input(key, config=config, context=context)

        # Special handling for file paths
        if "path" in key.lower() or "file" in key.lower():
            if isinstance(value, (str, Path)):
                validated_value = validate_file_path(value, config, f"parameter {key}")
            else:
                validated_value = sanitize_input(value, config=config, context=context)
        else:
            validated_value = sanitize_input(value, config=config, context=context)

        validated_params[clean_key] = validated_value

    if config.enable_audit_logging:
        logger.info(
            f"Node parameters validated ({context}): {list(validated_params.keys())}"
        )

    return validated_params
