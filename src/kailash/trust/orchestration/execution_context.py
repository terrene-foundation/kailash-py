# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Trust Execution Context - Carries trust state through workflow execution.

The TrustExecutionContext tracks trust information as it flows through
a multi-agent workflow, including:
- Delegated capabilities from parent agents
- Inherited constraints that must be respected
- Complete delegation chain for audit trail
- Metadata for context tracking

Example:
    # Create initial context from supervisor
    context = TrustExecutionContext.create(
        parent_agent_id="supervisor-001",
        task_id="analyze-data-001",
        delegated_capabilities=["read_data", "analyze_data"],
        inherited_constraints={
            "time_window": TimeWindow(start, end),
            "resource_limit": 100,
        }
    )

    # Propagate to worker agent
    worker_context = context.propagate_to_child(
        child_agent_id="worker-001",
        task_id="subtask-001",
        capabilities=["read_data"],  # Subset of delegated
    )

    # Verify capabilities before action
    if worker_context.has_capability("read_data"):
        # Proceed with action
        pass
"""

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from kailash.trust.orchestration.exceptions import (
    ConstraintLooseningError,
    ContextPropagationError,
    DelegationChainError,
)


class ContextMergeStrategy(str, Enum):
    """Strategy for merging parallel execution contexts."""

    INTERSECTION = "intersection"  # Capabilities: intersection, Constraints: most restrictive
    UNION = "union"  # Capabilities: union (requires all sources), Constraints: most restrictive
    FIRST_WINS = "first_wins"  # Use first context's values


@dataclass
class DelegationEntry:
    """
    Single entry in the delegation chain.

    Records who delegated to whom, for what task, and when.
    """

    delegator_id: str
    delegatee_id: str
    task_id: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    capabilities: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "delegator_id": self.delegator_id,
            "delegatee_id": self.delegatee_id,
            "task_id": self.task_id,
            "timestamp": self.timestamp.isoformat(),
            "capabilities": self.capabilities,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DelegationEntry":
        """Deserialize from dictionary."""
        return cls(
            delegator_id=data["delegator_id"],
            delegatee_id=data["delegatee_id"],
            task_id=data["task_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            capabilities=data.get("capabilities", []),
            metadata=data.get("metadata", {}),
        )


@dataclass
class TrustExecutionContext:
    """
    Carries trust state through workflow execution.

    The context flows from parent to child agents, tracking:
    - What capabilities were delegated
    - What constraints must be respected
    - The complete delegation chain for audit

    Attributes:
        context_id: Unique identifier for this context
        parent_agent_id: Agent that created/delegated this context
        current_agent_id: Agent currently executing with this context
        task_id: Task/workflow being executed
        delegated_capabilities: Capabilities delegated to current agent
        inherited_constraints: Constraints from parent that must be respected
        delegation_chain: Complete chain of delegations
        created_at: When this context was created
        metadata: Additional context information
    """

    context_id: str
    parent_agent_id: str
    current_agent_id: str
    task_id: str
    delegated_capabilities: Set[str]
    inherited_constraints: Dict[str, Any]
    delegation_chain: List[DelegationEntry]
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        parent_agent_id: str,
        task_id: str,
        delegated_capabilities: List[str],
        inherited_constraints: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "TrustExecutionContext":
        """
        Create a new execution context.

        Args:
            parent_agent_id: Agent creating this context (e.g., supervisor)
            task_id: Task/workflow identifier
            delegated_capabilities: Capabilities being delegated
            inherited_constraints: Constraints to inherit
            metadata: Additional context information

        Returns:
            New TrustExecutionContext instance
        """
        context_id = str(uuid.uuid4())
        return cls(
            context_id=context_id,
            parent_agent_id=parent_agent_id,
            current_agent_id=parent_agent_id,  # Initially same as parent
            task_id=task_id,
            delegated_capabilities=set(delegated_capabilities),
            inherited_constraints=inherited_constraints or {},
            delegation_chain=[],  # Empty initially
            metadata=metadata or {},
        )

    def has_capability(self, capability: str) -> bool:
        """Check if context includes a capability."""
        return capability in self.delegated_capabilities

    def has_all_capabilities(self, capabilities: List[str]) -> bool:
        """Check if context includes all specified capabilities."""
        return all(self.has_capability(cap) for cap in capabilities)

    def get_constraint(self, constraint_type: str, default: Any = None) -> Any:
        """Get a constraint value."""
        return self.inherited_constraints.get(constraint_type, default)

    def propagate_to_child(
        self,
        child_agent_id: str,
        task_id: str,
        capabilities: Optional[List[str]] = None,
        additional_constraints: Optional[Dict[str, Any]] = None,
    ) -> "TrustExecutionContext":
        """
        Create child context with propagated trust.

        The child context can only have:
        - Subset of parent's capabilities (capabilities can only reduce)
        - Same or tighter constraints (constraints can only tighten)

        Args:
            child_agent_id: Agent receiving delegated context
            task_id: Child task identifier
            capabilities: Capabilities to delegate (must be subset of current)
            additional_constraints: Additional constraints for child

        Returns:
            New TrustExecutionContext for child agent

        Raises:
            ContextPropagationError: If propagation fails
            ConstraintLooseningError: If attempting to loosen constraints
        """
        # Determine capabilities to delegate
        if capabilities is None:
            child_capabilities = self.delegated_capabilities.copy()
        else:
            # Ensure child capabilities are subset of parent
            requested_caps = set(capabilities)
            invalid_caps = requested_caps - self.delegated_capabilities
            if invalid_caps:
                raise ContextPropagationError(
                    self.current_agent_id,
                    child_agent_id,
                    f"Cannot delegate capabilities not held: {invalid_caps}",
                )
            child_capabilities = requested_caps

        # Merge constraints (child can only tighten)
        child_constraints = self._merge_constraints(additional_constraints)

        # Create delegation entry
        delegation = DelegationEntry(
            delegator_id=self.current_agent_id,
            delegatee_id=child_agent_id,
            task_id=task_id,
            capabilities=list(child_capabilities),
        )

        # Create child context
        child_context = TrustExecutionContext(
            context_id=str(uuid.uuid4()),
            parent_agent_id=self.current_agent_id,
            current_agent_id=child_agent_id,
            task_id=task_id,
            delegated_capabilities=child_capabilities,
            inherited_constraints=child_constraints,
            delegation_chain=self.delegation_chain + [delegation],
            metadata=self.metadata.copy(),
        )

        return child_context

    def _merge_constraints(
        self,
        additional_constraints: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Merge constraints ensuring only tightening.

        Rules:
        - Numeric limits: take minimum
        - Time windows: take intersection
        - Action sets: take intersection
        - Boolean flags: AND (more restrictive)

        Raises:
            ConstraintLooseningError: If new constraint is less restrictive
        """
        if not additional_constraints:
            return self.inherited_constraints.copy()

        merged = self.inherited_constraints.copy()

        for key, new_value in additional_constraints.items():
            if key not in merged:
                # New constraint - just add it
                merged[key] = new_value
            else:
                # Existing constraint - must tighten or maintain
                existing_value = merged[key]
                merged[key] = self._tighten_constraint(key, existing_value, new_value)

        return merged

    def _tighten_constraint(
        self,
        constraint_type: str,
        existing: Any,
        new: Any,
    ) -> Any:
        """
        Apply constraint tightening logic.

        Returns the more restrictive value.
        """
        # Numeric limits - take minimum
        if isinstance(existing, (int, float)) and isinstance(new, (int, float)):
            if new > existing:
                raise ConstraintLooseningError(
                    constraint_type,
                    str(existing),
                    str(new),
                )
            return min(existing, new)

        # Sets/lists of allowed actions - take intersection
        if isinstance(existing, (list, set)) and isinstance(new, (list, set)):
            existing_set = set(existing)
            new_set = set(new)
            # New set must be subset or equal
            if not new_set.issubset(existing_set):
                extra = new_set - existing_set
                raise ConstraintLooseningError(
                    constraint_type,
                    str(existing),
                    f"attempted to add: {extra}",
                )
            return list(new_set.intersection(existing_set))

        # Boolean - AND (more restrictive)
        if isinstance(existing, bool) and isinstance(new, bool):
            if existing is False and new is True:
                raise ConstraintLooseningError(
                    constraint_type,
                    str(existing),
                    str(new),
                )
            return existing and new

        # Dictionary - recurse
        if isinstance(existing, dict) and isinstance(new, dict):
            result = existing.copy()
            for k, v in new.items():
                if k in result:
                    result[k] = self._tighten_constraint(f"{constraint_type}.{k}", result[k], v)
                else:
                    result[k] = v
            return result

        # Default - new value (no tightening check for unknown types)
        return new

    def get_delegation_path(self) -> List[str]:
        """
        Get the path of agent IDs in delegation chain.

        Returns:
            List of agent IDs from root to current
        """
        if not self.delegation_chain:
            return [self.parent_agent_id]

        path = [self.delegation_chain[0].delegator_id]
        for entry in self.delegation_chain:
            path.append(entry.delegatee_id)
        return path

    def find_root_delegator(self) -> str:
        """
        Find the original delegator (root of chain).

        Returns:
            Agent ID of root delegator
        """
        if not self.delegation_chain:
            return self.parent_agent_id
        return self.delegation_chain[0].delegator_id

    def get_chain_length(self) -> int:
        """Get the length of the delegation chain."""
        return len(self.delegation_chain)

    @staticmethod
    def merge_parallel_contexts(
        contexts: List["TrustExecutionContext"],
        strategy: ContextMergeStrategy = ContextMergeStrategy.INTERSECTION,
    ) -> "TrustExecutionContext":
        """
        Merge multiple contexts from parallel execution.

        Used when parallel branches complete and need to combine results.

        Args:
            contexts: List of contexts to merge
            strategy: Merge strategy to use

        Returns:
            Merged TrustExecutionContext

        Raises:
            DelegationChainError: If contexts cannot be merged
        """
        if not contexts:
            raise DelegationChainError("Cannot merge empty context list")

        if len(contexts) == 1:
            return contexts[0]

        base = contexts[0]

        if strategy == ContextMergeStrategy.FIRST_WINS:
            return base

        # Merge capabilities based on strategy
        if strategy == ContextMergeStrategy.INTERSECTION:
            merged_caps = base.delegated_capabilities.copy()
            for ctx in contexts[1:]:
                merged_caps &= ctx.delegated_capabilities
        else:  # UNION
            merged_caps = base.delegated_capabilities.copy()
            for ctx in contexts[1:]:
                merged_caps |= ctx.delegated_capabilities

        # Merge constraints - always take most restrictive
        merged_constraints = base.inherited_constraints.copy()
        for ctx in contexts[1:]:
            for key, value in ctx.inherited_constraints.items():
                if key in merged_constraints:
                    # Take more restrictive
                    existing = merged_constraints[key]
                    if isinstance(existing, (int, float)) and isinstance(value, (int, float)):
                        merged_constraints[key] = min(existing, value)
                    elif isinstance(existing, (list, set)) and isinstance(value, (list, set)):
                        merged_constraints[key] = list(set(existing) & set(value))
                    elif isinstance(existing, bool) and isinstance(value, bool):
                        merged_constraints[key] = existing and value
                    else:
                        merged_constraints[key] = value
                else:
                    merged_constraints[key] = value

        # Combine delegation chains (flattened)
        all_entries = []
        seen_ids = set()
        for ctx in contexts:
            for entry in ctx.delegation_chain:
                entry_id = f"{entry.delegator_id}-{entry.delegatee_id}-{entry.task_id}"
                if entry_id not in seen_ids:
                    all_entries.append(entry)
                    seen_ids.add(entry_id)

        return TrustExecutionContext(
            context_id=str(uuid.uuid4()),
            parent_agent_id=base.parent_agent_id,
            current_agent_id=base.current_agent_id,
            task_id=base.task_id,
            delegated_capabilities=merged_caps,
            inherited_constraints=merged_constraints,
            delegation_chain=all_entries,
            metadata={"merged_from": [ctx.context_id for ctx in contexts]},
        )

    def compute_hash(self) -> str:
        """
        Compute deterministic hash of context for verification.

        Returns:
            SHA-256 hash of context state
        """
        data = {
            "context_id": self.context_id,
            "parent_agent_id": self.parent_agent_id,
            "current_agent_id": self.current_agent_id,
            "task_id": self.task_id,
            "delegated_capabilities": sorted(self.delegated_capabilities),
            "inherited_constraints": self.inherited_constraints,
            "chain_length": len(self.delegation_chain),
        }
        serialized = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode()).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "context_id": self.context_id,
            "parent_agent_id": self.parent_agent_id,
            "current_agent_id": self.current_agent_id,
            "task_id": self.task_id,
            "delegated_capabilities": list(self.delegated_capabilities),
            "inherited_constraints": self.inherited_constraints,
            "delegation_chain": [e.to_dict() for e in self.delegation_chain],
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrustExecutionContext":
        """Deserialize from dictionary."""
        return cls(
            context_id=data["context_id"],
            parent_agent_id=data["parent_agent_id"],
            current_agent_id=data["current_agent_id"],
            task_id=data["task_id"],
            delegated_capabilities=set(data["delegated_capabilities"]),
            inherited_constraints=data.get("inherited_constraints", {}),
            delegation_chain=[DelegationEntry.from_dict(e) for e in data.get("delegation_chain", [])],
            created_at=datetime.fromisoformat(data["created_at"]),
            metadata=data.get("metadata", {}),
        )

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str: str) -> "TrustExecutionContext":
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(json_str))
