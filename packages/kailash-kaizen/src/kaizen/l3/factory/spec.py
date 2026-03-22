# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""AgentSpec — frozen dataclass blueprint for agent instantiation.

A value type (AD-L3-15) that can be reused to spawn multiple instances.
Contains everything needed to instantiate an agent at runtime except
the LLM connection.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

__all__ = ["AgentSpec"]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentSpec:
    """Blueprint for agent instantiation.

    Frozen dataclass per AD-L3-15. Immutable after creation.
    Reusable: the same spec can spawn multiple AgentInstance objects.

    Fields:
        spec_id: Unique identifier for this spec (non-empty).
        name: Human-readable name for this agent type.
        description: Description of what this agent does.
        capabilities: Capabilities this agent provides (for discovery).
        tool_ids: Tool identifiers this agent has access to (no duplicates).
        envelope: Constraint envelope dict for this agent.
        memory_config: Configuration for memory backends.
        max_lifetime: Maximum wall-clock lifetime in seconds (None = no limit).
        max_children: Maximum direct children (None = no limit).
        max_depth: Maximum delegation depth below this agent (None = unlimited).
        required_context_keys: Context keys required from parent at spawn time.
        produced_context_keys: Context keys this agent will produce.
        metadata: Arbitrary key-value pairs for orchestration layer use.
    """

    spec_id: str
    name: str
    description: str
    capabilities: list[str] = field(default_factory=list)
    tool_ids: list[str] = field(default_factory=list)
    envelope: dict[str, Any] = field(default_factory=dict)
    memory_config: dict[str, Any] = field(default_factory=dict)
    max_lifetime: float | None = None
    max_children: int | None = None
    max_depth: int | None = None
    required_context_keys: list[str] = field(default_factory=list)
    produced_context_keys: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate spec_id is non-empty and tool_ids has no duplicates."""
        if not self.spec_id or not self.spec_id.strip():
            raise ValueError(
                f"spec_id must be a non-empty string, got {self.spec_id!r}"
            )
        if len(self.tool_ids) != len(set(self.tool_ids)):
            seen: set[str] = set()
            duplicates: list[str] = []
            for tid in self.tool_ids:
                if tid in seen:
                    duplicates.append(tid)
                seen.add(tid)
            raise ValueError(
                f"tool_ids must not contain duplicates, found: {duplicates}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "spec_id": self.spec_id,
            "name": self.name,
            "description": self.description,
            "capabilities": list(self.capabilities),
            "tool_ids": list(self.tool_ids),
            "envelope": dict(self.envelope),
            "memory_config": dict(self.memory_config),
            "max_lifetime": self.max_lifetime,
            "max_children": self.max_children,
            "max_depth": self.max_depth,
            "required_context_keys": list(self.required_context_keys),
            "produced_context_keys": list(self.produced_context_keys),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentSpec:
        """Deserialize from dict."""
        return cls(
            spec_id=data["spec_id"],
            name=data["name"],
            description=data["description"],
            capabilities=list(data.get("capabilities", [])),
            tool_ids=list(data.get("tool_ids", [])),
            envelope=dict(data.get("envelope", {})),
            memory_config=dict(data.get("memory_config", {})),
            max_lifetime=data.get("max_lifetime"),
            max_children=data.get("max_children"),
            max_depth=data.get("max_depth"),
            required_context_keys=list(data.get("required_context_keys", [])),
            produced_context_keys=list(data.get("produced_context_keys", [])),
            metadata=dict(data.get("metadata", {})),
        )
