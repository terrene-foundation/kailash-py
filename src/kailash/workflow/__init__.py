"""Workflow system for the Kailash SDK."""

from typing import TYPE_CHECKING, Any

from kailash.workflow.async_builder import AsyncWorkflowBuilder, ErrorHandler
from kailash.workflow.async_builder import RetryPolicy as AsyncRetryPolicy
from kailash.workflow.async_patterns import AsyncPatterns
from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow.cycle_analyzer import CycleAnalyzer
from kailash.workflow.cycle_builder import CycleBuilder
from kailash.workflow.cycle_config import CycleConfig, CycleTemplates
from kailash.workflow.cycle_debugger import (
    CycleDebugger,
    CycleExecutionTrace,
    CycleIteration,
)
from kailash.workflow.cycle_profiler import CycleProfiler, PerformanceMetrics
from kailash.workflow.dlq import DLQItem, PersistentDLQ

# workflow_from_brief is pure-Python at import time (all kaizen + _from_brief
# imports are deferred to call-time inside the function). WorkflowPlan and
# WorkflowPlanSignature are LAZY via from_brief.__getattr__ — see that
# module's docstring for the kaizen-import circular-load fence rationale.
from kailash.workflow.from_brief import workflow_from_brief
from kailash.workflow.graph import Connection, NodeInstance, Workflow
from kailash.workflow.mermaid_visualizer import MermaidVisualizer
from kailash.workflow.resilience import (
    CircuitBreakerConfig,
    RetryPolicy,
    RetryStrategy,
    WorkflowResilience,
    apply_resilience_to_workflow,
)
from kailash.workflow.templates import BusinessWorkflowTemplates
from kailash.workflow.templates import CycleTemplates as WorkflowCycleTemplates
from kailash.workflow.visualization import WorkflowVisualizer

if TYPE_CHECKING:
    # Surface the lazy ``WorkflowPlan`` / ``WorkflowPlanSignature`` exports to
    # static analyzers (CodeQL ``py/undefined-export``, pyright, mypy --strict,
    # Sphinx autodoc) per ``rules/orphan-detection.md`` § 6b. Both symbols are
    # resolved at runtime via ``__getattr__`` below (their bodies live behind
    # ``from_brief.py``'s own lazy factories — the kaizen-import circular-load
    # fence). Without this analyzer-only import, CodeQL flags both ``__all__``
    # entries as "exported but not defined" because the lazy ``__getattr__``
    # binding is invisible to module-scope static analysis.
    from kailash.workflow.from_brief import (  # noqa: F401
        WorkflowPlan,
        WorkflowPlanSignature,
    )

__all__ = [
    "Workflow",
    "NodeInstance",
    "Connection",
    "WorkflowVisualizer",
    "MermaidVisualizer",
    "WorkflowBuilder",
    "AsyncWorkflowBuilder",
    "AsyncPatterns",
    "RetryPolicy",
    "AsyncRetryPolicy",
    "ErrorHandler",
    "CycleBuilder",
    "CycleConfig",
    "CycleTemplates",
    "CycleDebugger",
    "CycleExecutionTrace",
    "CycleIteration",
    "CycleProfiler",
    "PerformanceMetrics",
    "CycleAnalyzer",
    "RetryStrategy",
    "RetryPolicy",
    "CircuitBreakerConfig",
    "WorkflowResilience",
    "apply_resilience_to_workflow",
    "PersistentDLQ",
    "DLQItem",
    "WorkflowCycleTemplates",
    "BusinessWorkflowTemplates",
    # from_brief() surface — issue #1125 AC 1 + AC 6
    "WorkflowPlan",
    "WorkflowPlanSignature",
    "workflow_from_brief",
]


def __getattr__(name: str) -> Any:
    """PEP 562 lazy attribute resolver for ``WorkflowPlan`` and
    ``WorkflowPlanSignature``.

    Both classes are exposed via the lazy resolvers in
    :mod:`kailash.workflow.from_brief` (see that module's docstring
    for the import-time circularity rationale — kaizen + S1 imports
    trigger a circular load with ``kailash.trust.posture``). The
    classes therefore cannot be imported eagerly here; this hook
    resolves them at call time.
    """
    if name == "WorkflowPlanSignature":
        from kailash.workflow.from_brief import _signature_cls

        return _signature_cls()
    if name == "WorkflowPlan":
        from kailash.workflow.from_brief import _workflow_plan_cls

        return _workflow_plan_cls()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# Bind from_brief() as a classmethod onto Workflow per issue #1125 AC 1.
# Classmethod binding (not a separate top-level function) so users invoke
# the documented form `Workflow.from_brief(brief)` and get a WorkflowBuilder
# whose `.build().execute()` runs end-to-end. Per the brief: "today the
# call raises AttributeError; this converts the documented contract from
# 'aspirational' to 'executable'."
#
# The classmethod intentionally ignores `cls` — Workflow.from_brief()
# returns a WorkflowBuilder (which builds a Workflow), not a Workflow
# instance directly. This matches the canonical Kailash pattern of
# `WorkflowBuilder().build()` per `rules/patterns.md` § Runtime Execution.
def _workflow_from_brief_classmethod(cls, brief, **kwargs):
    """Realize a natural-language brief into a :class:`WorkflowBuilder`.

    See :func:`kailash.workflow.from_brief.workflow_from_brief` for the
    full contract, accepted keyword arguments, and raised exceptions.

    The classmethod returns a :class:`WorkflowBuilder` (not a
    :class:`Workflow` instance) so the caller can compose further
    with the standard builder API before calling ``.build()``::

        wf = Workflow.from_brief("a workflow that reads CSV and counts rows")
        runtime = LocalRuntime()
        results, run_id = runtime.execute(wf.build())
    """
    return workflow_from_brief(brief, **kwargs)


Workflow.from_brief = classmethod(_workflow_from_brief_classmethod)  # type: ignore[attr-defined]
