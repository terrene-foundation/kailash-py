# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
kaizen.orchestration — multi-agent orchestration surface.

This module hosts:

- ``OrchestrationRuntime`` (cross-SDK parity with kailash-rs
  ``kaizen-agents::orchestration::runtime``) — strategy-driven multi-agent
  coordination with Sequential / Parallel / Hierarchical / Pipeline
  strategies. See ``kaizen.orchestration.runtime``.
- Re-exports + ``sys.modules`` aliases that point
  ``kaizen.orchestration.patterns.*`` at the real
  ``kaizen_agents.patterns.patterns.*`` modules so existing ``mock.patch``
  targets continue to resolve.

The proxy aliases predate the runtime module; they are preserved verbatim
so tests that patch ``kaizen.orchestration.patterns.blackboard.A2A_AVAILABLE``
keep working.
"""

import sys

# Optional proxy aliases — only installed when kaizen-agents is present.
# kaizen-agents is not a hard dependency of kailash-kaizen; the proxies exist
# solely so legacy ``mock.patch("kaizen.orchestration.patterns.blackboard.…")``
# call sites continue to resolve when both packages are co-installed. A clean
# kailash-kaizen install (without kaizen-agents) MUST still import successfully.
try:
    import kaizen_agents.patterns.patterns as _pp  # noqa: E402
    import kaizen_agents.patterns.patterns.blackboard as _bb  # noqa: E402
    import kaizen_agents.patterns.patterns.ensemble as _en  # noqa: E402
    import kaizen_agents.patterns.patterns.meta_controller as _mc  # noqa: E402
except ImportError:
    pass
else:
    sys.modules.setdefault("kaizen.orchestration.patterns", _pp)
    sys.modules.setdefault("kaizen.orchestration.patterns.blackboard", _bb)
    sys.modules.setdefault("kaizen.orchestration.patterns.ensemble", _en)
    sys.modules.setdefault("kaizen.orchestration.patterns.meta_controller", _mc)

# Public OrchestrationRuntime surface (issue #602 — cross-SDK parity with
# kailash-rs kaizen-agents::orchestration::runtime). Eager imports so the
# symbols satisfy `from kaizen.orchestration import *` and Sphinx autodoc per
# rules/orphan-detection.md §6.
from kaizen.orchestration.runtime import (  # noqa: E402
    AgentLike,
    Coordinator,
    OrchestrationConfig,
    OrchestrationError,
    OrchestrationResult,
    OrchestrationRuntime,
    OrchestrationStrategy,
    OrchestrationStrategyKind,
    PipelineInputSource,
    PipelineStep,
    SharedMemoryCoordinator,
)

__all__ = [
    "AgentLike",
    "Coordinator",
    "OrchestrationConfig",
    "OrchestrationError",
    "OrchestrationResult",
    "OrchestrationRuntime",
    "OrchestrationStrategy",
    "OrchestrationStrategyKind",
    "PipelineInputSource",
    "PipelineStep",
    "SharedMemoryCoordinator",
]
