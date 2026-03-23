"""
AgentDesigner: Translates subtasks into AgentSpec blueprints.

Given a Subtask (from the TaskDecomposer), the parent's constraint envelope,
and the list of available tools, the AgentDesigner produces an AgentSpec
with appropriate capabilities, tool selections, and a tightened child envelope.

Includes:
    - CapabilityMatcher: Finds existing AgentSpecs that match a set of capabilities.
    - SpawnPolicy: Decides whether a subtask warrants spawning a new agent vs
      handling it inline within the parent.
    - AgentDesigner: The main class that combines LLM judgment with the matcher
      and spawn policy to produce specs.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from kaizen_agents.llm import LLMClient
from kaizen_agents.orchestration.planner.decomposer import Subtask
from kaizen_agents.types import (
    AgentSpec,
    ConstraintEnvelope,
    MemoryConfig,
)


# ---------------------------------------------------------------------------
# CapabilityMatcher — finds existing specs matching required capabilities
# ---------------------------------------------------------------------------


@dataclass
class CapabilityMatch:
    """Result of matching an existing AgentSpec against required capabilities.

    Attributes:
        spec: The matching AgentSpec.
        matched_capabilities: Capabilities from the requirement that this spec covers.
        unmatched_capabilities: Capabilities from the requirement that this spec lacks.
        match_score: Fraction of required capabilities covered (0.0 to 1.0).
    """

    spec: AgentSpec
    matched_capabilities: list[str]
    unmatched_capabilities: list[str]
    match_score: float


class CapabilityMatcher:
    """Matches required capabilities against a registry of existing AgentSpecs.

    The matcher supports two modes:
        - Exact matching: capability strings must match exactly.
        - Semantic matching: uses an LLM to determine if two capability
          descriptions are semantically equivalent (e.g., "code-review"
          matches "static-analysis" if the LLM judges them equivalent).

    The registry is a simple in-memory list. In production this would be
    backed by the SDK's AgentRegistry / AgentInstanceRegistry.
    """

    def __init__(
        self,
        known_specs: list[AgentSpec] | None = None,
        llm_client: LLMClient | None = None,
    ) -> None:
        """Initialise the matcher.

        Args:
            known_specs: Pre-registered AgentSpecs to match against.
            llm_client: Optional LLM client for semantic matching. If not
                provided, only exact string matching is used.
        """
        self._specs: list[AgentSpec] = list(known_specs) if known_specs else []
        self._llm = llm_client

    def register(self, spec: AgentSpec) -> None:
        """Add a spec to the known registry.

        Args:
            spec: An AgentSpec to register for future capability matching.
        """
        self._specs.append(spec)

    def find_matches(
        self,
        required_capabilities: list[str],
        min_score: float = 0.5,
    ) -> list[CapabilityMatch]:
        """Find specs whose capabilities overlap with the requirements.

        Args:
            required_capabilities: Capabilities the subtask needs.
            min_score: Minimum match_score to include in results (0.0 to 1.0).

        Returns:
            List of CapabilityMatch objects sorted by match_score descending.
            Only matches with score >= min_score are returned.
        """
        if not required_capabilities or not self._specs:
            return []

        required_set = set(required_capabilities)
        matches: list[CapabilityMatch] = []

        for spec in self._specs:
            spec_caps = set(spec.capabilities)
            matched = required_set & spec_caps
            unmatched = required_set - spec_caps
            score = len(matched) / len(required_set) if required_set else 0.0

            if score >= min_score:
                matches.append(
                    CapabilityMatch(
                        spec=spec,
                        matched_capabilities=sorted(matched),
                        unmatched_capabilities=sorted(unmatched),
                        match_score=score,
                    )
                )

        matches.sort(key=lambda m: m.match_score, reverse=True)
        return matches

    def find_semantic_matches(
        self,
        required_capabilities: list[str],
        min_score: float = 0.5,
    ) -> list[CapabilityMatch]:
        """Find specs using semantic similarity for capability matching.

        Falls back to exact matching if no LLM client is configured.

        Args:
            required_capabilities: Capabilities the subtask needs.
            min_score: Minimum match_score threshold.

        Returns:
            List of CapabilityMatch objects sorted by match_score descending.
        """
        if not self._llm or not required_capabilities or not self._specs:
            return self.find_matches(required_capabilities, min_score)

        matches: list[CapabilityMatch] = []

        for spec in self._specs:
            if not spec.capabilities:
                continue

            matched, unmatched = self._semantic_compare(required_capabilities, spec.capabilities)
            score = len(matched) / len(required_capabilities) if required_capabilities else 0.0

            if score >= min_score:
                matches.append(
                    CapabilityMatch(
                        spec=spec,
                        matched_capabilities=matched,
                        unmatched_capabilities=unmatched,
                        match_score=score,
                    )
                )

        matches.sort(key=lambda m: m.match_score, reverse=True)
        return matches

    def _semantic_compare(
        self,
        required: list[str],
        available: list[str],
    ) -> tuple[list[str], list[str]]:
        """Use the LLM to determine which required capabilities are covered.

        Args:
            required: Required capability names.
            available: Available capability names from a spec.

        Returns:
            Tuple of (matched_capabilities, unmatched_capabilities).
        """
        if not self._llm:
            required_set = set(required)
            available_set = set(available)
            matched = sorted(required_set & available_set)
            unmatched = sorted(required_set - available_set)
            return matched, unmatched

        schema: dict[str, Any] = {
            "type": "object",
            "properties": {
                "matches": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "required_capability": {"type": "string"},
                            "is_covered": {"type": "boolean"},
                            "matched_by": {"type": "string"},
                        },
                        "required": ["required_capability", "is_covered", "matched_by"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["matches"],
            "additionalProperties": False,
        }

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a capability matching engine. Given a list of required "
                    "capabilities and a list of available capabilities, determine which "
                    "required capabilities are semantically covered by the available ones. "
                    "Two capabilities match if they are semantically equivalent or if the "
                    "available capability is a superset of the required one."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Required capabilities: {required}\n"
                    f"Available capabilities: {available}\n\n"
                    "For each required capability, indicate whether it is covered by any "
                    "available capability, and if so, which one."
                ),
            },
        ]

        result = self._llm.complete_structured(
            messages=messages,
            schema=schema,
            schema_name="capability_match",
        )

        matched: list[str] = []
        unmatched: list[str] = []

        for item in result.get("matches", []):
            cap = item.get("required_capability", "")
            if item.get("is_covered", False):
                matched.append(cap)
            else:
                unmatched.append(cap)

        return matched, unmatched


# ---------------------------------------------------------------------------
# SpawnPolicy — decides spawn vs inline
# ---------------------------------------------------------------------------


class SpawnDecision:
    """The result of a spawn-vs-inline policy evaluation."""

    SPAWN = "spawn"
    INLINE = "inline"

    def __init__(self, decision: str, reason: str) -> None:
        """Create a spawn decision.

        Args:
            decision: Either SpawnDecision.SPAWN or SpawnDecision.INLINE.
            reason: Human-readable explanation of why this decision was made.
        """
        self.decision = decision
        self.reason = reason

    @property
    def should_spawn(self) -> bool:
        """Whether a new agent should be spawned for this subtask."""
        return self.decision == self.SPAWN

    def __repr__(self) -> str:
        return f"SpawnDecision(decision={self.decision!r}, reason={self.reason!r})"


class SpawnPolicy:
    """Decides whether a subtask warrants spawning a new agent or handling inline.

    The decision is based on:
        - Subtask complexity (higher complexity favours spawning)
        - Number of required tools (more tools favours spawning for isolation)
        - Whether an existing spec covers the capabilities (reuse favours spawning)
        - Envelope constraints (tight budgets favour inline to avoid spawn overhead)

    Thresholds are configurable. The defaults are tuned for a balance between
    parallelism (spawn more) and overhead reduction (inline more).
    """

    def __init__(
        self,
        complexity_threshold: int = 3,
        tool_count_threshold: int = 2,
        budget_threshold: float = 1.0,
    ) -> None:
        """Initialise the policy with thresholds.

        Args:
            complexity_threshold: Subtasks at or above this complexity get spawned.
            tool_count_threshold: Subtasks needing this many tools or more get spawned.
            budget_threshold: If the envelope's financial limit is below this value,
                prefer inline to avoid spawn overhead costs.
        """
        self._complexity_threshold = complexity_threshold
        self._tool_count_threshold = tool_count_threshold
        self._budget_threshold = budget_threshold

    def evaluate(
        self,
        subtask: Subtask,
        parent_envelope: ConstraintEnvelope,
        has_matching_spec: bool = False,
    ) -> SpawnDecision:
        """Evaluate whether to spawn a new agent or handle inline.

        Args:
            subtask: The subtask to evaluate.
            parent_envelope: The parent's constraint envelope.
            has_matching_spec: Whether an existing spec covers this subtask's capabilities.

        Returns:
            A SpawnDecision indicating spawn or inline with justification.
        """
        financial_limit = parent_envelope.financial.get("limit", float("inf"))

        # If budget is very tight, prefer inline to avoid spawn overhead
        if financial_limit < self._budget_threshold:
            return SpawnDecision(
                SpawnDecision.INLINE,
                f"Financial budget (${financial_limit}) is below spawn threshold "
                f"(${self._budget_threshold}); handling inline to conserve budget.",
            )

        # High complexity strongly favours spawning for isolation and focus
        if subtask.estimated_complexity >= self._complexity_threshold:
            return SpawnDecision(
                SpawnDecision.SPAWN,
                f"Complexity {subtask.estimated_complexity} meets/exceeds threshold "
                f"{self._complexity_threshold}; spawning for focused execution.",
            )

        # Many tools suggest the subtask benefits from a dedicated agent
        if len(subtask.suggested_tools) >= self._tool_count_threshold:
            return SpawnDecision(
                SpawnDecision.SPAWN,
                f"Subtask needs {len(subtask.suggested_tools)} tools "
                f"(threshold: {self._tool_count_threshold}); spawning for tool isolation.",
            )

        # If there is already a matching spec, spawning is cheap (reuse)
        if has_matching_spec:
            return SpawnDecision(
                SpawnDecision.SPAWN,
                "Existing spec matches required capabilities; spawning for reuse.",
            )

        # Default: simple subtasks are handled inline
        return SpawnDecision(
            SpawnDecision.INLINE,
            f"Complexity {subtask.estimated_complexity} is below threshold "
            f"{self._complexity_threshold} with {len(subtask.suggested_tools)} tools; "
            "handling inline.",
        )


# ---------------------------------------------------------------------------
# AgentDesigner — produces AgentSpec from subtask + envelope + tools
# ---------------------------------------------------------------------------


# JSON schema for LLM-driven spec generation
AGENT_DESIGN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "Human-readable agent name (e.g., 'Code Reviewer').",
        },
        "description": {
            "type": "string",
            "description": "What this agent does, for capability matching.",
        },
        "capabilities": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Capabilities this agent provides.",
        },
        "selected_tools": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Tool IDs selected from the available tools list.",
        },
        "financial_ratio": {
            "type": "number",
            "description": ("Fraction of the parent's financial budget to allocate (0.0-1.0)."),
        },
        "needs_shared_memory": {
            "type": "boolean",
            "description": "Whether this agent needs shared memory with siblings.",
        },
        "needs_persistent_memory": {
            "type": "boolean",
            "description": "Whether this agent needs persistent memory across sessions.",
        },
        "produced_context_keys": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Context keys this agent will produce for downstream consumers.",
        },
    },
    "required": [
        "name",
        "description",
        "capabilities",
        "selected_tools",
        "financial_ratio",
        "needs_shared_memory",
        "needs_persistent_memory",
        "produced_context_keys",
    ],
    "additionalProperties": False,
}


def _build_design_system_prompt() -> str:
    """Build the system prompt for agent design."""
    return """You are an agent design engine for a PACT-governed autonomous agent system.

Given a subtask description, the parent's constraint envelope, and a list of
available tools, your job is to design an AgentSpec that can accomplish the
subtask effectively.

## Rules

1. Choose a clear, descriptive name for the agent (e.g., "Code Reviewer", "Data Analyst").
2. Write a description that would help other agents understand what this one does.
3. List the capabilities this agent provides (matching or expanding on the subtask's requirements).
4. Select tools from the available tools list ONLY. Do not invent tools that are not available.
5. Allocate a financial_ratio (0.01 to 0.5) of the parent's budget. Complex subtasks need more.
   - Complexity 1-2: 0.01-0.05
   - Complexity 3: 0.05-0.15
   - Complexity 4: 0.10-0.25
   - Complexity 5: 0.20-0.50
6. Set needs_shared_memory to true if the agent needs to share state with sibling agents.
7. Set needs_persistent_memory to true if results should persist across sessions.
8. List the context keys this agent will produce for downstream consumers."""


def _build_design_user_prompt(
    subtask: Subtask,
    parent_envelope: ConstraintEnvelope,
    available_tools: list[str],
) -> str:
    """Build the user prompt for agent design."""
    budget_str = ""
    financial_limit = parent_envelope.financial.get("limit")
    if financial_limit is not None:
        budget_str = f"\n  Financial limit: ${financial_limit}"

    blocked = parent_envelope.operational.get("blocked", [])
    blocked_str = ""
    if blocked:
        blocked_str = f"\n  Blocked operations: {', '.join(blocked)}"

    tools_str = ", ".join(available_tools) if available_tools else "(none available)"

    deps_str = ""
    if subtask.depends_on:
        deps_str = f"\n  Depends on subtask indices: {subtask.depends_on}"

    output_str = ""
    if subtask.output_keys:
        output_str = f"\n  Expected output keys: {', '.join(subtask.output_keys)}"

    return f"""## Subtask

Description: {subtask.description}
Complexity: {subtask.estimated_complexity}/5
Required capabilities: {', '.join(subtask.required_capabilities) or '(none specified)'}
Suggested tools: {', '.join(subtask.suggested_tools) or '(none suggested)'}{deps_str}{output_str}

## Parent Envelope{budget_str}{blocked_str}

## Available Tools

{tools_str}

Design an AgentSpec for this subtask. Select tools only from the available list."""


class AgentDesigner:
    """Translates subtasks into fully-specified AgentSpec blueprints.

    Combines LLM-driven design with the CapabilityMatcher (for reuse of
    existing specs) and SpawnPolicy (for spawn-vs-inline decisions).

    Usage:
        designer = AgentDesigner(llm_client=my_client)
        spec, decision = designer.design(
            subtask=my_subtask,
            parent_envelope=my_envelope,
            available_tools=["file_read", "code_search", "web_browser"],
        )
        if decision.should_spawn:
            # spawn a new agent with `spec`
            ...
        else:
            # handle the subtask inline
            ...
    """

    def __init__(
        self,
        llm_client: LLMClient,
        capability_matcher: CapabilityMatcher | None = None,
        spawn_policy: SpawnPolicy | None = None,
    ) -> None:
        """Initialise the designer.

        Args:
            llm_client: LLM client for generating spec designs.
            capability_matcher: Optional matcher for reusing existing specs.
                If not provided, a new empty matcher is created.
            spawn_policy: Optional policy for spawn-vs-inline decisions.
                If not provided, default thresholds are used.
        """
        self._llm = llm_client
        self._matcher = capability_matcher or CapabilityMatcher()
        self._policy = spawn_policy or SpawnPolicy()

    @property
    def capability_matcher(self) -> CapabilityMatcher:
        """The capability matcher used by this designer."""
        return self._matcher

    @property
    def spawn_policy(self) -> SpawnPolicy:
        """The spawn policy used by this designer."""
        return self._policy

    def design(
        self,
        subtask: Subtask,
        parent_envelope: ConstraintEnvelope,
        available_tools: list[str],
    ) -> tuple[AgentSpec, SpawnDecision]:
        """Design an AgentSpec for a subtask.

        The design process:
        1. Check for existing specs that match the required capabilities.
        2. Evaluate the spawn policy.
        3. If an existing spec covers all capabilities, adapt it.
        4. Otherwise, use the LLM to generate a new spec.
        5. Tighten the envelope and validate tool selections.

        Args:
            subtask: The subtask to design an agent for.
            parent_envelope: The parent's constraint envelope (child must be tighter).
            available_tools: Tool IDs available in the parent's operational envelope.

        Returns:
            A tuple of (AgentSpec, SpawnDecision). The spec is ready to pass
            to the AgentFactory for instantiation.
        """
        # Step 1: Check for existing matching specs
        matches = self._matcher.find_matches(
            required_capabilities=subtask.required_capabilities,
            min_score=0.8,
        )

        has_match = len(matches) > 0
        best_match = matches[0] if has_match else None

        # Step 2: Evaluate spawn policy
        spawn_decision = self._policy.evaluate(
            subtask=subtask,
            parent_envelope=parent_envelope,
            has_matching_spec=has_match,
        )

        # Step 3: Generate or adapt spec
        if best_match and best_match.match_score >= 1.0:
            spec = self._adapt_existing_spec(
                base_spec=best_match.spec,
                subtask=subtask,
                parent_envelope=parent_envelope,
                available_tools=available_tools,
            )
        else:
            spec = self._generate_new_spec(
                subtask=subtask,
                parent_envelope=parent_envelope,
                available_tools=available_tools,
            )

        # Step 4: Validate and tighten
        spec = self._validate_and_tighten(spec, parent_envelope, available_tools)

        return spec, spawn_decision

    def _adapt_existing_spec(
        self,
        base_spec: AgentSpec,
        subtask: Subtask,
        parent_envelope: ConstraintEnvelope,
        available_tools: list[str],
    ) -> AgentSpec:
        """Adapt an existing spec for a new subtask.

        Reuses the base spec's structure but updates the envelope and tools
        to match the current parent's constraints and available tools.

        Args:
            base_spec: The existing spec to adapt.
            subtask: The target subtask.
            parent_envelope: The parent's envelope for tightening.
            available_tools: Currently available tools.

        Returns:
            An adapted AgentSpec.
        """
        available_set = set(available_tools)
        filtered_tools = [t for t in base_spec.tool_ids if t in available_set]

        # Add any suggested tools that are available but not in the base spec
        for tool in subtask.suggested_tools:
            if tool in available_set and tool not in filtered_tools:
                filtered_tools.append(tool)

        child_envelope = self._tighten_envelope(parent_envelope, subtask)

        return AgentSpec(
            spec_id=f"{base_spec.spec_id}-{uuid.uuid4().hex[:8]}",
            name=base_spec.name,
            description=base_spec.description,
            capabilities=list(base_spec.capabilities),
            tool_ids=filtered_tools,
            envelope=child_envelope,
            memory_config=MemoryConfig(
                session=base_spec.memory_config.session,
                shared=base_spec.memory_config.shared,
                persistent=base_spec.memory_config.persistent,
                shared_namespace=base_spec.memory_config.shared_namespace,
            ),
            required_context_keys=list(base_spec.required_context_keys),
            produced_context_keys=subtask.output_keys or list(base_spec.produced_context_keys),
            metadata={
                "adapted_from": base_spec.spec_id,
                "subtask_description": subtask.description,
                "subtask_complexity": subtask.estimated_complexity,
            },
        )

    def _generate_new_spec(
        self,
        subtask: Subtask,
        parent_envelope: ConstraintEnvelope,
        available_tools: list[str],
    ) -> AgentSpec:
        """Use the LLM to generate a new AgentSpec for the subtask.

        Args:
            subtask: The subtask to design for.
            parent_envelope: The parent's envelope for context.
            available_tools: Available tool IDs.

        Returns:
            A new AgentSpec generated by the LLM.
        """
        system_prompt = _build_design_system_prompt()
        user_prompt = _build_design_user_prompt(subtask, parent_envelope, available_tools)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        raw_result = self._llm.complete_structured(
            messages=messages,
            schema=AGENT_DESIGN_SCHEMA,
            schema_name="agent_design",
        )

        return self._parse_spec(raw_result, subtask, parent_envelope)

    def _parse_spec(
        self,
        raw: dict[str, Any],
        subtask: Subtask,
        parent_envelope: ConstraintEnvelope,
    ) -> AgentSpec:
        """Parse the LLM's structured output into an AgentSpec.

        Args:
            raw: The parsed JSON dict from the LLM.
            subtask: The original subtask for fallback values.
            parent_envelope: For envelope tightening.

        Returns:
            A constructed AgentSpec.
        """
        name = raw.get("name", "Unnamed Agent")
        description = raw.get("description", subtask.description)
        capabilities = raw.get("capabilities", subtask.required_capabilities)
        selected_tools = raw.get("selected_tools", [])
        financial_ratio = raw.get("financial_ratio", 0.1)
        needs_shared = raw.get("needs_shared_memory", False)
        needs_persistent = raw.get("needs_persistent_memory", False)
        produced_keys = raw.get("produced_context_keys", subtask.output_keys)

        # Clamp financial_ratio to valid range
        financial_ratio = max(0.01, min(0.5, float(financial_ratio)))

        child_envelope = self._tighten_envelope(parent_envelope, subtask, financial_ratio)

        return AgentSpec(
            spec_id=f"designed-{uuid.uuid4().hex[:8]}",
            name=str(name),
            description=str(description),
            capabilities=[str(c) for c in capabilities] if isinstance(capabilities, list) else [],
            tool_ids=[str(t) for t in selected_tools] if isinstance(selected_tools, list) else [],
            envelope=child_envelope,
            memory_config=MemoryConfig(
                session=True,
                shared=bool(needs_shared),
                persistent=bool(needs_persistent),
            ),
            required_context_keys=[],
            produced_context_keys=(
                [str(k) for k in produced_keys] if isinstance(produced_keys, list) else []
            ),
            metadata={
                "generated_by": "agent_designer",
                "subtask_description": subtask.description,
                "subtask_complexity": subtask.estimated_complexity,
                "financial_ratio": financial_ratio,
            },
        )

    def _tighten_envelope(
        self,
        parent: ConstraintEnvelope,
        subtask: Subtask,
        financial_ratio: float = 0.1,
    ) -> ConstraintEnvelope:
        """Create a tightened child envelope from the parent's envelope.

        Applies monotonic tightening per PACT spec:
        - Financial: child.limit <= parent.remaining (uses ratio)
        - Operational: inherits parent's constraints
        - Temporal: inherits parent's window
        - Data Access: inherits parent's ceiling and scopes
        - Communication: inherits parent's recipients and channels

        Args:
            parent: The parent's constraint envelope.
            subtask: The subtask (unused currently but available for future
                per-subtask tightening logic).
            financial_ratio: Fraction of parent's financial budget to allocate.

        Returns:
            A new ConstraintEnvelope that is strictly tighter than the parent's.
        """
        parent_limit = parent.financial.get("limit", 10.0)
        child_limit = parent_limit * financial_ratio

        return ConstraintEnvelope(
            financial={"limit": child_limit},
            operational={
                "allowed": list(parent.operational.get("allowed", [])),
                "blocked": list(parent.operational.get("blocked", [])),
            },
            temporal=dict(parent.temporal),
            data_access={
                "ceiling": parent.data_access.get("ceiling", "internal"),
                "scopes": list(parent.data_access.get("scopes", [])),
            },
            communication={
                "recipients": list(parent.communication.get("recipients", [])),
                "channels": list(parent.communication.get("channels", [])),
            },
        )

    def _validate_and_tighten(
        self,
        spec: AgentSpec,
        parent_envelope: ConstraintEnvelope,
        available_tools: list[str],
    ) -> AgentSpec:
        """Validate spec constraints and enforce tool subsetting.

        Ensures:
        - All tool_ids are in the available_tools set (I-05 from spec 04)
        - Child envelope's financial limit does not exceed parent's
        - Child inherits operational blocks from parent

        Args:
            spec: The spec to validate.
            parent_envelope: The parent's envelope.
            available_tools: Tool IDs available to the parent.

        Returns:
            The spec with any invalid tools removed and envelope constraints enforced.
        """
        available_set = set(available_tools)
        valid_tools = [t for t in spec.tool_ids if t in available_set]
        spec.tool_ids = valid_tools

        # Enforce financial tightening
        parent_limit = parent_envelope.financial.get("limit", float("inf"))
        child_limit = spec.envelope.financial.get("limit", parent_limit)
        if child_limit > parent_limit:
            spec.envelope.financial["limit"] = parent_limit

        # Ensure blocked operations are a superset of parent's
        parent_blocked = set(parent_envelope.operational.get("blocked", []))
        child_blocked = set(spec.envelope.operational.get("blocked", []))
        merged_blocked = parent_blocked | child_blocked
        spec.envelope.operational["blocked"] = sorted(merged_blocked)

        # Ensure allowed operations are a subset of parent's (if parent restricts)
        parent_allowed = parent_envelope.operational.get("allowed", [])
        if parent_allowed:
            parent_allowed_set = set(parent_allowed)
            child_allowed = spec.envelope.operational.get("allowed", [])
            filtered_allowed = [a for a in child_allowed if a in parent_allowed_set]
            spec.envelope.operational["allowed"] = filtered_allowed

        return spec
