"""
TaskDecomposer: Breaks a high-level objective into structured subtasks.

This is the first stage of the planning pipeline. Given a natural-language
objective, contextual information, and a constraint envelope, the decomposer
uses an LLM to produce a list of subtasks with complexity estimates,
required capabilities, and suggested tools.

The decomposer is part of the orchestration layer (kaizen-agents) because
it requires LLM judgment. The Plan DAG (SDK primitive) handles validation
and execution of whatever the decomposer produces.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from kaizen_agents.llm import LLMClient
from kaizen_agents.types import ConstraintEnvelope, _default_envelope


@dataclass
class Subtask:
    """A decomposed unit of work produced by the TaskDecomposer.

    Attributes:
        description: Natural-language description of what this subtask accomplishes.
        estimated_complexity: Relative complexity on a 1-5 scale
            (1 = trivial, 5 = requires deep expertise or extended time).
        required_capabilities: Capabilities an agent needs to handle this subtask
            (e.g., "code-review", "web-search", "data-analysis").
        suggested_tools: Tool identifiers that would be useful for this subtask
            (e.g., "code_search", "file_write", "web_browser").
        depends_on: Indices of other subtasks in the same decomposition that must
            complete before this one can start. Empty list means no dependencies.
        output_keys: Keys this subtask will produce as output, available to
            downstream subtasks via input mapping.
    """

    description: str
    estimated_complexity: int
    required_capabilities: list[str] = field(default_factory=list)
    suggested_tools: list[str] = field(default_factory=list)
    depends_on: list[int] = field(default_factory=list)
    output_keys: list[str] = field(default_factory=list)


# JSON schema for the LLM structured output
DECOMPOSITION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "subtasks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "What this subtask accomplishes.",
                    },
                    "estimated_complexity": {
                        "type": "integer",
                        "description": "Complexity 1-5 (1=trivial, 5=expert-level).",
                    },
                    "required_capabilities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Capabilities an agent needs for this subtask.",
                    },
                    "suggested_tools": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tool identifiers useful for this subtask.",
                    },
                    "depends_on": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": ("Zero-based indices of subtasks that must complete first."),
                    },
                    "output_keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Keys this subtask produces as output.",
                    },
                },
                "required": [
                    "description",
                    "estimated_complexity",
                    "required_capabilities",
                    "suggested_tools",
                    "depends_on",
                    "output_keys",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["subtasks"],
    "additionalProperties": False,
}


def _build_system_prompt(envelope: ConstraintEnvelope) -> str:
    """Build the system prompt for the decomposer, incorporating envelope constraints."""
    budget_info = ""
    if envelope.financial is not None:
        budget_info += f"\n- Financial budget limit: ${envelope.financial.max_spend_usd}"

    blocked_ops = envelope.operational.blocked_actions
    if blocked_ops:
        budget_info += f"\n- Blocked operations: {', '.join(blocked_ops)}"

    allowed_ops = envelope.operational.allowed_actions
    if allowed_ops:
        budget_info += f"\n- Allowed operations: {', '.join(allowed_ops)}"

    confidentiality = envelope.confidentiality_clearance
    if confidentiality is not None:
        budget_info += f"\n- Data access clearance: {confidentiality.value}"

    constraint_section = ""
    if budget_info:
        constraint_section = f"""
## Constraints

The following envelope constraints apply to the overall task:{budget_info}

Subtasks must be feasible within these constraints. Do not suggest subtasks
that would violate blocked operations or exceed the data access ceiling.
"""

    return f"""You are a task decomposition engine for an autonomous agent system.

Your job is to break a high-level objective into concrete, actionable subtasks
that can each be assigned to a single agent. Each subtask should be self-contained
enough that an agent with the right capabilities and tools can complete it
independently (modulo data dependencies on other subtasks).

## Rules

1. Each subtask must have a clear, specific description of what it accomplishes.
2. Estimate complexity on a 1-5 scale:
   - 1: Trivial (simple lookup, formatting, single API call)
   - 2: Simple (straightforward logic, basic tool use)
   - 3: Moderate (requires reasoning, multiple steps)
   - 4: Complex (requires expertise, multi-tool coordination)
   - 5: Expert (deep domain knowledge, extended analysis)
3. List the capabilities an agent would need (e.g., "code-review", "web-search").
4. Suggest specific tools that would help (e.g., "file_read", "code_search").
5. Identify dependencies: which subtasks must complete before this one starts.
   Use zero-based indices referring to the position in the subtasks array.
6. List the output keys each subtask will produce for downstream consumers.
7. Prefer more, smaller subtasks over fewer, larger ones. Aim for complexity 1-3 per subtask.
8. Do NOT create circular dependencies. The dependency graph must be a DAG.
9. Ensure at least one subtask has no dependencies (a root task that can start immediately).
{constraint_section}"""


def _build_user_prompt(objective: str, context: dict[str, Any]) -> str:
    """Build the user prompt with the objective and any contextual information."""
    context_section = ""
    if context:
        context_lines = []
        for key, value in context.items():
            if isinstance(value, str):
                context_lines.append(f"- **{key}**: {value}")
            else:
                context_lines.append(f"- **{key}**: {value!r}")
        context_section = "\n\n## Context\n\n" + "\n".join(context_lines)

    return f"""## Objective

{objective}{context_section}

Break this objective into subtasks. Return the result as a JSON object with
a "subtasks" array. Each subtask needs: description, estimated_complexity (1-5),
required_capabilities, suggested_tools, depends_on (indices), and output_keys."""


class TaskDecomposer:
    """Breaks a high-level objective into structured subtasks using an LLM.

    The decomposer takes a natural-language objective, optional context, and
    a constraint envelope, then uses structured LLM output to produce a list
    of Subtask objects. These subtasks become the inputs to the AgentDesigner
    (which produces AgentSpecs) and eventually the PlanComposer (which
    assembles a Plan DAG).

    Usage:
        decomposer = TaskDecomposer(llm_client=my_client)
        subtasks = decomposer.decompose(
            objective="Implement user authentication for the web app",
            context={"stack": "Python/FastAPI", "auth_provider": "Auth0"},
            envelope=my_envelope,
        )
        for subtask in subtasks:
            print(subtask.description, subtask.estimated_complexity)
    """

    def __init__(self, llm_client: LLMClient) -> None:
        """Initialise the decomposer with an LLM client.

        Args:
            llm_client: A configured LLMClient instance for making completions.
        """
        self._llm = llm_client

    def decompose(
        self,
        objective: str,
        context: dict[str, Any] | None = None,
        envelope: ConstraintEnvelope | None = None,
    ) -> list[Subtask]:
        """Decompose an objective into a list of subtasks.

        Args:
            objective: Natural-language description of the goal to accomplish.
            context: Optional dict of contextual information (tech stack,
                existing state, user preferences, etc.).
            envelope: Constraint envelope bounding the task. Defaults to a
                permissive envelope if not provided.

        Returns:
            A list of Subtask objects ordered so that dependencies appear
            before their dependents (topologically sorted).

        Raises:
            ValueError: If the LLM returns an invalid decomposition structure.
        """
        effective_envelope = envelope or _default_envelope()
        effective_context = context or {}

        system_prompt = _build_system_prompt(effective_envelope)
        user_prompt = _build_user_prompt(objective, effective_context)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        raw_result = self._llm.complete_structured(
            messages=messages,
            schema=DECOMPOSITION_SCHEMA,
            schema_name="task_decomposition",
        )

        return self._parse_subtasks(raw_result)

    def _parse_subtasks(self, raw: dict[str, Any]) -> list[Subtask]:
        """Parse and validate the raw LLM response into Subtask objects.

        Args:
            raw: The parsed JSON dict from the LLM structured output.

        Returns:
            A validated list of Subtask objects.

        Raises:
            ValueError: If the structure is invalid or contains circular dependencies.
        """
        raw_subtasks = raw.get("subtasks")
        if not isinstance(raw_subtasks, list):
            raise ValueError(f"Expected 'subtasks' to be a list, got {type(raw_subtasks).__name__}")

        if len(raw_subtasks) == 0:
            raise ValueError("Decomposition produced zero subtasks")

        subtasks: list[Subtask] = []
        num_subtasks = len(raw_subtasks)

        for idx, item in enumerate(raw_subtasks):
            if not isinstance(item, dict):
                raise ValueError(f"Subtask at index {idx} is not a dict: {type(item).__name__}")

            description = item.get("description", "")
            if not description or not isinstance(description, str):
                raise ValueError(f"Subtask at index {idx} has invalid or empty description")

            complexity = item.get("estimated_complexity", 3)
            if not isinstance(complexity, int) or not (1 <= complexity <= 5):
                complexity = max(1, min(5, int(complexity)))

            depends_on = item.get("depends_on", [])
            if not isinstance(depends_on, list):
                depends_on = []

            # Validate dependency indices are in range and don't self-reference
            valid_deps = []
            for dep_idx in depends_on:
                if isinstance(dep_idx, int) and 0 <= dep_idx < num_subtasks and dep_idx != idx:
                    valid_deps.append(dep_idx)

            capabilities = item.get("required_capabilities", [])
            if not isinstance(capabilities, list):
                capabilities = []
            capabilities = [str(c) for c in capabilities if c]

            tools = item.get("suggested_tools", [])
            if not isinstance(tools, list):
                tools = []
            tools = [str(t) for t in tools if t]

            output_keys = item.get("output_keys", [])
            if not isinstance(output_keys, list):
                output_keys = []
            output_keys = [str(k) for k in output_keys if k]

            subtasks.append(
                Subtask(
                    description=description,
                    estimated_complexity=complexity,
                    required_capabilities=capabilities,
                    suggested_tools=tools,
                    depends_on=valid_deps,
                    output_keys=output_keys,
                )
            )

        self._validate_no_cycles(subtasks)
        self._validate_has_root(subtasks)

        return subtasks

    def _validate_no_cycles(self, subtasks: list[Subtask]) -> None:
        """Verify the dependency graph is acyclic using topological sort.

        Raises:
            ValueError: If a cycle is detected in the dependency graph.
        """
        num = len(subtasks)
        visited: list[int] = [0] * num  # 0=unvisited, 1=in-progress, 2=done

        def dfs(node: int) -> None:
            if visited[node] == 1:
                raise ValueError(
                    f"Circular dependency detected involving subtask {node}: "
                    f"'{subtasks[node].description[:60]}'"
                )
            if visited[node] == 2:
                return
            visited[node] = 1
            for dep in subtasks[node].depends_on:
                if 0 <= dep < num:
                    dfs(dep)
            visited[node] = 2

        for i in range(num):
            if visited[i] == 0:
                dfs(i)

    def _validate_has_root(self, subtasks: list[Subtask]) -> None:
        """Verify at least one subtask has no dependencies (can start immediately).

        Raises:
            ValueError: If every subtask depends on at least one other.
        """
        has_root = any(len(s.depends_on) == 0 for s in subtasks)
        if not has_root:
            raise ValueError(
                "No root subtask found: every subtask depends on at least one other. "
                "At least one subtask must have an empty depends_on list."
            )
