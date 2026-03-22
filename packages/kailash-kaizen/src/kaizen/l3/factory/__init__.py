# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Agent factory and instance registry for L3 runtime agent instantiation.

Public API:
    AgentSpec — Frozen blueprint for agent instantiation (AD-L3-15).
    AgentInstance — Mutable entity with lifecycle state machine.
    AgentInstanceRegistry — Thread-safe registry with asyncio.Lock.
    AgentFactory — Spawn/terminate with PACT invariant validation.
    Error types — Structured errors with .details dicts.
"""

from __future__ import annotations

from kaizen.l3.factory.errors import (
    EnvelopeNotTighter,
    FactoryError,
    InsufficientBudget,
    InstanceNotFound,
    MaxChildrenExceeded,
    MaxDepthExceeded,
    RegistryError,
    RequiredContextMissing,
    ToolNotInParent,
)
from kaizen.l3.factory.factory import AgentFactory
from kaizen.l3.factory.instance import (
    AgentInstance,
    AgentLifecycleState,
    InvalidStateTransitionError,
    TerminationReason,
    WaitReason,
)
from kaizen.l3.factory.registry import AgentInstanceRegistry
from kaizen.l3.factory.spec import AgentSpec

__all__ = [
    "AgentFactory",
    "AgentInstance",
    "AgentInstanceRegistry",
    "AgentLifecycleState",
    "AgentSpec",
    "EnvelopeNotTighter",
    "FactoryError",
    "InsufficientBudget",
    "InstanceNotFound",
    "InvalidStateTransitionError",
    "MaxChildrenExceeded",
    "MaxDepthExceeded",
    "RegistryError",
    "RequiredContextMissing",
    "TerminationReason",
    "ToolNotInParent",
    "WaitReason",
]
