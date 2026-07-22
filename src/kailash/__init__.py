# pyright: reportUnsupportedDunderAll=false
"""Kailash Python SDK - A framework for building workflow-based applications.

The Kailash SDK provides a comprehensive framework for creating nodes and workflows
that align with container-node architecture while allowing rapid prototyping.

Note: ``__all__`` lists names resolved via ``__getattr__`` (lazy imports for
optional server extras). Pyright's ``reportUnsupportedDunderAll`` check is
disabled because it does not follow ``__getattr__`` fallbacks.
"""

import warnings

from kailash.events import DomainEvent, EventBus, Subscription, TenantScopedEventBus
from kailash.nodes.base import Node, NodeMetadata, NodeParameter
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# Import key components for easier access
from kailash.workflow.graph import Connection, NodeInstance, Workflow

# isort: split
# Eagerly register the EventBus workflow node. MUST be imported AFTER the
# runtime chain above so kailash.runtime.async_local -> kailash.nodes.base_async
# is fully loaded first. Otherwise:
#   EventPublishNode -> AsyncNode -> kailash.runtime.template_resolver
#   -> kailash.runtime.__init__ -> async_local -> AsyncNode
# triggers a partially-initialized-module ImportError on plain `import kailash`.
# The `# isort: split` directive above is load-bearing: it tells isort to treat
# this import as a separate sort block so the alphabetical-order pass does
# NOT reorder it back before `runtime.local` (which would re-introduce the
# circular import). Verified by `import kailash` + pre-commit Tier-1
# collection (issue #1054).
from kailash.nodes.events import EventPublishNode  # noqa: E402,F401


def __getattr__(name):
    """Lazy imports for optional dependencies and deprecation warnings."""
    if name == "WorkflowVisualizer":
        from kailash.workflow.visualization import WorkflowVisualizer

        return WorkflowVisualizer
    # governance_required posture — direct LLM egress (#1779, EATP D6 parity).
    # Lazy so plain `import kailash` does not eagerly load the PACT trust
    # package; the posture module itself is pure-stdlib but importing it via
    # kailash.trust.pact triggers that package's __init__.
    if name in ("is_governance_required", "set_governance_required"):
        from kailash.trust.pact.governance_posture import (
            is_governance_required,
            set_governance_required,
        )

        return {
            "is_governance_required": is_governance_required,
            "set_governance_required": set_governance_required,
        }[name]
    if name == "UngovernedEgressRefused":
        from kailash.trust.pact.exceptions import UngovernedEgressRefused

        return UngovernedEgressRefused
    if name == "WorkflowGraph":
        warnings.warn(
            "WorkflowGraph is deprecated and will be removed in v3.0.0. "
            "Use Workflow instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return Workflow
    if name in (
        "AgentUIMiddleware",
        "APIGateway",
        "RealtimeMiddleware",
    ):
        warnings.warn(
            f"{name} is no longer exported from kailash top-level. "
            f"Import from kailash.middleware instead: from kailash.middleware import {name}",
            DeprecationWarning,
            stacklevel=2,
        )
        from kailash import middleware

        return getattr(middleware, name)
    # Lazy server imports (require server extras)
    _server_names = {
        "WorkflowServer",
        "DurableWorkflowServer",
        "EnterpriseWorkflowServer",
        "create_gateway",
        "create_enterprise_gateway",
        "create_durable_gateway",
        "create_basic_gateway",
    }
    if name in _server_names:
        try:
            if name in (
                "WorkflowServer",
                "DurableWorkflowServer",
                "EnterpriseWorkflowServer",
            ):
                from kailash import servers

                return getattr(servers, name)
            else:
                from kailash.servers import gateway

                return getattr(gateway, name)
        except ImportError as exc:
            raise ImportError(
                f"{name} requires server dependencies (fastapi, uvicorn, "
                f"aiohttp, httpx, aiofiles). Install with: "
                f"pip install 'kailash[server]'"
            ) from exc
    raise AttributeError(f"module 'kailash' has no attribute {name!r}")


__version__ = "2.61.0"

__all__ = [
    # Core workflow components
    "Workflow",
    "NodeInstance",
    "Connection",
    "WorkflowBuilder",
    "WorkflowVisualizer",
    "Node",
    "NodeParameter",
    "NodeMetadata",
    "LocalRuntime",
    # Domain-event primitive (issue #1054)
    "EventBus",
    "Subscription",
    "DomainEvent",
    # Tenant-scoped event bus (issue #1338)
    "TenantScopedEventBus",
    # Server classes (lazy, require kailash[server])
    "WorkflowServer",
    "DurableWorkflowServer",
    "EnterpriseWorkflowServer",
    "create_gateway",
    "create_enterprise_gateway",
    "create_durable_gateway",
    "create_basic_gateway",
    # from_brief() family — Sg-Bootstrap surface (issue #1125 AC 4 + AC 9)
    "bootstrap",
    "BootstrapConfig",
    # governance_required posture — direct LLM egress (#1779, EATP D6 parity)
    "is_governance_required",
    "set_governance_required",
    "UngovernedEgressRefused",
]

# Eager bind of the bootstrap callable + BootstrapConfig (issue #1125 AC 4 + AC 9).
# `kailash.bootstrap` is BOTH a submodule name AND the callable name within it; if
# either symbol resolved through PEP 562 `__getattr__`, the lazy resolver's own
# `from kailash.bootstrap import bootstrap` import would auto-register the
# SUBMODULE as `kailash.bootstrap`, shadowing the callable on subsequent access.
# Eagerly binding here makes `kailash.bootstrap` the CALLABLE (the explicit
# attribute assignment wins over the submodule's auto-set). The supported
# import paths are therefore `kailash.bootstrap(...)` (the callable) and
# `from kailash.bootstrap import bootstrap` (resolves the submodule via
# sys.modules). The dotted-attribute form `kailash.bootstrap.bootstrap` is
# NOT reachable — `kailash.bootstrap` is the function after this bind, so
# attribute access raises AttributeError.
#
# Safety check: the bootstrap module's top-level imports are pure-Python
# (dataclasses, typing, logging, os) — NO kaizen at module-import time. Kaizen
# imports are deferred to call-time inside `_build_agent` and `bootstrap()`.
# Importing `kailash.bootstrap` here does NOT trigger the kaizen circular-load
# fence the workflow.from_brief module needs.
from kailash.bootstrap import BootstrapConfig, bootstrap  # noqa: E402, F401
