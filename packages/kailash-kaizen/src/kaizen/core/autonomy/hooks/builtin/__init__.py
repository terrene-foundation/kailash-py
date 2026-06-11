"""
Built-in hook implementations.

Provides common hooks for logging, metrics, cost tracking, performance profiling, audit, and tracing.

``LoggingHook``, ``MetricsHook``, and ``TracingHook`` depend on the optional
``observability`` extra (structlog / prometheus-client / opentelemetry). They are
lazy-loaded via PEP 562 ``__getattr__`` so that merely importing the hook system
(e.g. for ``HookManager``) does not require the extra on a slim-core install.
Accessing one of these names without the extra installed raises a clear,
actionable ImportError.
"""

import importlib
from typing import TYPE_CHECKING

from .audit_hook import AuditHook
from .cost_tracking_hook import CostTrackingHook
from .performance_profiler_hook import PerformanceProfilerHook

if TYPE_CHECKING:
    # Analyzer-only imports (PEP 562 lazy exports) — keep static analysis,
    # Sphinx autodoc, and `from pkg import *` resolution working while the
    # runtime import stays deferred behind __getattr__ (orphan-detection Rule 6b).
    from .logging_hook import LoggingHook
    from .metrics_hook import MetricsHook
    from .tracing_hook import TracingHook

__all__ = [
    "LoggingHook",
    "MetricsHook",
    "CostTrackingHook",
    "PerformanceProfilerHook",
    "AuditHook",
    "TracingHook",
]

# Public name -> submodule providing it. Each submodule pulls a dependency that
# ships only with the `observability` extra, so they are imported on demand.
_OPTIONAL_HOOKS = {
    "LoggingHook": "logging_hook",
    "MetricsHook": "metrics_hook",
    "TracingHook": "tracing_hook",
}


def __getattr__(name):
    module_name = _OPTIONAL_HOOKS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    try:
        module = importlib.import_module(f".{module_name}", __name__)
    except ImportError as exc:
        raise ImportError(
            f"{name} requires the optional 'observability' extra "
            "(structlog / prometheus-client / opentelemetry). Install it with: "
            "pip install 'kailash-kaizen[observability]'"
        ) from exc
    return getattr(module, name)


def __dir__():
    return sorted(__all__)
