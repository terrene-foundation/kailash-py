"""Hook system for autonomous agents."""

import importlib
from typing import TYPE_CHECKING

from kaizen.core.autonomy.hooks.builtin import (
    AuditHook,
    CostTrackingHook,
    PerformanceProfilerHook,
)
from kaizen.core.autonomy.hooks.manager import HookManager
from kaizen.core.autonomy.hooks.protocol import BaseHook, HookHandler
from kaizen.core.autonomy.hooks.types import (
    HookContext,
    HookEvent,
    HookPriority,
    HookResult,
)

if TYPE_CHECKING:
    # LoggingHook/MetricsHook/TracingHook require the optional `observability`
    # extra; they are lazy-loaded from the builtin package via __getattr__ so
    # importing the hook system (e.g. for HookManager) stays slim-core clean.
    from kaizen.core.autonomy.hooks.builtin import LoggingHook, MetricsHook, TracingHook

# Re-exported from the builtin package but lazy-loaded there (optional extra);
# delegate name resolution to builtin.__getattr__.
_OPTIONAL_HOOKS = ("LoggingHook", "MetricsHook", "TracingHook")


def __getattr__(name):
    if name in _OPTIONAL_HOOKS:
        builtin = importlib.import_module("kaizen.core.autonomy.hooks.builtin")
        return getattr(builtin, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "HookEvent",
    "HookContext",
    "HookResult",
    "HookPriority",
    "BaseHook",
    "HookHandler",
    "HookManager",
    "LoggingHook",
    "MetricsHook",
    "CostTrackingHook",
    "PerformanceProfilerHook",
    "AuditHook",
    "TracingHook",
]


def __dir__():
    return sorted(__all__)
