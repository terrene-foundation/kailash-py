# ADR-010: CO Five Layers → Agent Runtime Mapping

**Status**: ACCEPTED (2026-04-07)
**Scope**: Cross-cutting — applies to all Kaizen agent primitives, wrappers, and engines
**Deciders**: Platform Architecture Convergence workspace, user specification 2026-04-07

## Context

The CO (Cognitive Orchestration) Five Layers define the universal control surface for all agents. The convergence work (ADRs 001-009) defines the primitive/wrapper/engine architecture. This ADR maps the five layers onto that architecture, establishing **which component owns which layer** and **how enforcement semantics change across the tool↔autonomous spectrum**.

### The Five Layers

| CO Layer         | What it governs                            | Operational Controls                                                                                                                                                       |
| ---------------- | ------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Intent**       | What the agent is trying to achieve        | Objective/task from the invoker. Not PM-configured — comes from the work request.                                                                                          |
| **Context**      | What the agent knows about its environment | Data sources, knowledge (filtered by categories + classification), application state, execution history                                                                    |
| **Guardrails**   | What the agent must not do                 | **Hard**: Operating envelope, content freeze, never-delegated actions, verification gradient. **Soft**: Content review (held, not blocked), posture ceiling, budget limits |
| **Instructions** | What the agent should do                   | Output schema, procedures, expertise, PM-tuned prompts                                                                                                                     |
| **Learning**     | What the agent has learned                 | Agent versioning, posture evidence (success rate, incidents), execution metrics, codified patterns                                                                         |

### The Spectrum

The same five layers apply to both tool agents (L1-L2) and autonomous agents (L4-L5). What changes is **enforcement semantics based on posture**:

|                  | Tool Agent (L1-L2) | Autonomous Agent (L4-L5)                 |
| ---------------- | ------------------ | ---------------------------------------- |
| **Intent**       | Given to it        | Derives from objective                   |
| **Context**      | Injected           | Discovers + selects                      |
| **Guardrails**   | Hard walls         | Same hard walls (envelopes don't soften) |
| **Instructions** | Commands           | Guidance (agent uses judgment)           |
| **Learning**     | Metrics recorded   | Drives posture progression               |

**Key principle**: Guardrails are invariant across the spectrum. An operating envelope doesn't get wider because an agent is more autonomous. A content freeze blocks L5 delegated agents just as much as L1 pseudo agents. This is PACT principle P1 (envelope is recursive) enforced through the verification gradient.

**Key insight**: Instructions shift from commands to guidance:

- **Tool Agent** (L1-L2): Output schema is a hard contract. Missing sections = rejected.
- **Autonomous Agent** (L4-L5): Output schema is a preference. Use judgment on what's relevant.

Same `output_schema` field on the Agent model. Same PM editing surface. **Different enforcement at runtime based on posture.**

## Decision

**Each CO layer maps to a specific component in the convergence architecture. The mapping is canonical — every implementation (Python, Rust, and any future SDK) MUST preserve this mapping.**

### Layer → Component Mapping

```
┌─────────────┬──────────────────────────────────────────────────────────────────────────┐
│  CO Layer   │  Component(s) that own this layer                                        │
├─────────────┼──────────────────────────────────────────────────────────────────────────┤
│ Intent      │ BaseAgent(signature=...) — InputField defines what the invoker asks,     │
│             │ OutputField defines what the agent delivers.                              │
│             │ For autonomous agents: Delegate decomposes objective into sub-intents.    │
├─────────────┼──────────────────────────────────────────────────────────────────────────┤
│ Context     │ BaseAgent._memory (execution history), BaseAgent._tools (data sources),  │
│             │ MCPClient (external knowledge via MCP resources),                         │
│             │ L3GovernedAgent filters context by clearance (classification ceiling).    │
│             │ Tool agents: context is injected. Autonomous agents: context is           │
│             │ discovered + selected via tool calls.                                     │
├─────────────┼──────────────────────────────────────────────────────────────────────────┤
│ Guardrails  │ L3GovernedAgent(envelope=...) — hard walls:                              │
│             │   ConstraintEnvelope (5D: financial, operational, temporal, data,         │
│             │   communication), never-delegated actions, content freeze.                │
│             │ MonitoredAgent(budget_usd=...) — soft walls:                              │
│             │   Budget limits, posture ceiling.                                         │
│             │ Verification gradient (AUTO_APPROVED → FLAGGED → HELD → BLOCKED)          │
│             │   evaluates every action against envelope. INVARIANT: does not soften     │
│             │   with higher autonomy.                                                   │
├─────────────┼──────────────────────────────────────────────────────────────────────────┤
│ Instructions│ BaseAgent(system_prompt=..., signature=...) +                             │
│             │ StructuredOutput.from_signature(sig).for_provider(provider) — output      │
│             │ schema, procedures, PM-tuned prompts.                                     │
│             │ ENFORCEMENT VARIES BY POSTURE:                                            │
│             │   L1-L2 (tool): schema is hard contract (strict validation, reject        │
│             │   on missing fields).                                                     │
│             │   L3-L5 (autonomous): schema is guidance (best-effort parsing,            │
│             │   graceful degradation, agent may produce additional context).             │
│             │ The same signature= parameter drives both. The enforcement level is       │
│             │ read from the agent's posture in the PACT envelope.                       │
├─────────────┼──────────────────────────────────────────────────────────────────────────┤
│ Learning    │ MonitoredAgent — execution metrics (cost, latency, token usage).          │
│             │ PostureStore — posture evidence (success rate, incidents, escalations).   │
│             │ TrustPlane DecisionRecord — codified decisions with reasoning traces.     │
│             │ ExperimentTracker — model performance over time.                          │
│             │ Tool agents: metrics recorded passively.                                  │
│             │ Autonomous agents: learning drives posture progression (L3→L4→L5).       │
└─────────────┴──────────────────────────────────────────────────────────────────────────┘
```

### Shared Capabilities (Both Tool and Autonomous Agents)

These are capabilities that exist at the BaseAgent level and are available to BOTH agent types:

1. **Read context** — knowledge, data sources, categories, app state (via `_memory`, `_tools`, MCP)
2. **Respect guardrails** — envelope, freeze, gradient, review (via `L3GovernedAgent` wrapper)
3. **Follow instructions** — output schema, procedures (via `signature`, `system_prompt`, `StructuredOutput`)
4. **Record learning** — metrics, evidence, version history (via `MonitoredAgent`, `PostureStore`)

### BaseAgent (Tool Agent) Adds

- **Deterministic invocation**: `run(**inputs) -> Dict[str, Any]` — message in, response out
- **Output schema hard enforcement**: Signature validation is strict. Missing fields in output = `SignatureValidationError`
- **Scoped context injection**: Only the data sources configured for this specific agent instance
- **Workflow composability**: `to_workflow()` for Core SDK integration (n8n-era requirement)

### Delegate/StreamingAgent (Autonomous Agent) Adds

- **Objective decomposition**: Breaks intent into sub-tasks (via TAOD loop)
- **Tool agent selection**: Chooses which tool agents to invoke based on context (via `ToolRegistry` + `ToolHydrator`)
- **Reasoning trace**: TAOD loop — Think, Act, Observe, Decide (via `AgentLoop`)
- **Posture-aware judgment**: Can deviate from instruction schema within envelope boundaries
- **Streaming events**: Per-token output + tool call events (via `StreamingAgent` wrapper)

### Posture-Aware Instruction Enforcement

This is the new concept that emerges from the CO Five Layers mapping. The `StructuredOutput` system needs to know the agent's posture to decide enforcement level:

```python
class StructuredOutput:
    """Handles Signature → JSON schema translation with posture-aware enforcement."""

    def __init__(self, signature: type[Signature], posture: AgentPosture = AgentPosture.TOOL):
        self._signature = signature
        self._posture = posture

    def validate_output(self, raw_output: str) -> ValidationResult:
        """Validate LLM output against the signature schema.

        Enforcement varies by posture:

        - TOOL (L1-L2): Strict validation. Missing required fields = error.
          Extra fields = stripped. Type mismatches = error. No retry — reject.

        - SUPERVISED (L3): Moderate validation. Missing required fields = warning +
          retry with correction prompt. Extra fields = kept (may be useful context).
          Type mismatches = attempt coercion, then retry.

        - AUTONOMOUS (L4-L5): Soft validation. Missing fields = accept partial result
          with metadata noting what's missing. Extra fields = kept. Type mismatches =
          best-effort coercion. The agent's judgment is trusted within envelope.
        """
        if self._posture == AgentPosture.TOOL:
            return self._strict_validate(raw_output)
        elif self._posture == AgentPosture.SUPERVISED:
            return self._moderate_validate(raw_output)
        else:  # AUTONOMOUS
            return self._soft_validate(raw_output)


class AgentPosture(Enum):
    """Agent posture levels (maps to PACT/EATP posture)."""
    PSEUDO = "pseudo"          # L1: Not a real agent — direct API call
    TOOL = "tool"              # L2: Deterministic invocation
    SUPERVISED = "supervised"  # L3: Agent with human oversight
    AUTONOMOUS = "autonomous"  # L4: Independent within envelope
    DELEGATING = "delegating"  # L5: Can delegate to other agents
```

### How This Maps to the Wrapper Stack

```python
# Tool Agent (L1-L2): Hard enforcement
agent = BaseAgent(
    config=BaseAgentConfig(model="...", posture=AgentPosture.TOOL),
    signature=ContentUpdateSchema,  # hard contract
    system_prompt="Your output MUST have Summary, New Features, Bug Fixes.",
)
result = agent.run(content="...")  # strict validation, reject on missing fields

# Autonomous Agent (L4-L5): Soft enforcement
delegate = Delegate(
    model="...",
    signature=FinancialReportSchema,  # guidance, not hard contract
    system_prompt="Financial reports typically have these sections. Use judgment.",
    budget_usd=10.0,
    envelope=cfo_envelope,  # PACT envelope for CFO role
)
# Internally:
#   BaseAgent(posture=AgentPosture.AUTONOMOUS, signature=...)
#     → MonitoredAgent(budget)
#       → L3GovernedAgent(envelope)
#         → StreamingAgent(TAOD loop)
#
# StructuredOutput reads posture from BaseAgent config.
# Validation is soft — missing sections are noted, not rejected.
# The same signature field, same PM editing surface, different enforcement.
```

## Rationale

1. **The CO Five Layers are the canonical control surface.** They predate the convergence and are defined in the CO spec (`skills/co-reference/`). This ADR makes the mapping explicit rather than implicit.

2. **"Same field, different enforcement based on posture" is the key insight.** It means we DON'T need separate `strict_signature` vs `soft_signature` parameters. One `signature=` parameter, one `system_prompt=`, one PM editing surface. The enforcement level comes from `posture`.

3. **Guardrails are invariant.** This is PACT principle P1. The wrapper stack enforces it: `L3GovernedAgent` and `MonitoredAgent` apply the SAME envelope regardless of posture. A content freeze blocks L5 agents just as hard as L1 agents. No softening.

4. **The wrapper stack naturally implements the layer ownership.** Each wrapper adds one CO layer's capabilities. The primitives (BaseAgent) own Intent + Instructions. The wrappers (L3GovernedAgent, MonitoredAgent) own Guardrails + Learning. Context flows through all of them via `_memory`, `_tools`, and MCP.

5. **This maps the tool agent ↔ autonomous agent spectrum onto the SAME primitive stack.** The convergence already decided (ADR-001 through ADR-007) that both agent types use the same `BaseAgent` + wrappers. This ADR shows WHY that works — because the CO layers are the same, only enforcement varies by posture.

## Consequences

### Changes to existing specs

1. **SPEC-03 (Composition wrappers)**: Add `posture: AgentPosture` parameter to `BaseAgent.__init__`. `StructuredOutput` reads this to determine validation strictness.

2. **SPEC-04 (BaseAgent slimming)**: `BaseAgentConfig` gains a `posture: AgentPosture = AgentPosture.TOOL` field. Default is TOOL (backward compat — existing code gets strict validation).

3. **SPEC-05 (Delegate facade)**: `Delegate` sets `posture=AgentPosture.AUTONOMOUS` by default (or reads from the PACT envelope if one is provided).

4. **ADR-003 (Streaming as wrapper)**: `StreamingAgent`'s TAOD loop produces `TurnComplete.structured` which respects the posture-aware validation — soft validation for autonomous, strict for tool.

5. **SPEC-07 (ConstraintEnvelope)**: Add `posture_ceiling: AgentPosture` to `ConstraintEnvelope` — the envelope can LOWER posture but never raise it. A supervisor can delegate a task to an agent at a LOWER posture than their own.

### Positive

- ✅ Unifies the tool agent and autonomous agent control surfaces
- ✅ PM editing surface is the same for both (signature, system_prompt)
- ✅ Posture-aware enforcement means no separate "strict" vs "soft" APIs
- ✅ Guardrail invariance is enforced by the wrapper stack (not by developer discipline)
- ✅ Maps directly to PACT posture levels (PSEUDO → TOOL → SUPERVISED → AUTONOMOUS → DELEGATING)
- ✅ Maps directly to EATP trust postures (same progression)
- ✅ Learning layer naturally drives posture progression (L3 → L4 → L5 based on evidence)

### Negative

- ❌ `posture` is a new parameter on `BaseAgentConfig` — all 188 subclasses default to TOOL (backward compat) but may need explicit posture setting
- ❌ `StructuredOutput` validation logic gets more complex (3 modes instead of 1)
- ❌ Test coverage must cover all 3 enforcement modes × all provider formats

## Implementation Notes

### BaseAgentConfig gains posture

```python
class BaseAgentConfig:
    model: str
    posture: AgentPosture = AgentPosture.TOOL  # NEW — default preserves backward compat
    # ... existing fields ...
```

### StructuredOutput reads posture

```python
class StructuredOutput:
    @classmethod
    def from_signature(
        cls,
        signature: type[Signature],
        *,
        posture: AgentPosture = AgentPosture.TOOL,
    ) -> StructuredOutput:
        return cls(signature=signature, posture=posture)

    def validate_output(self, raw_output: str) -> ValidationResult:
        match self._posture:
            case AgentPosture.PSEUDO | AgentPosture.TOOL:
                return self._strict_validate(raw_output)
            case AgentPosture.SUPERVISED:
                return self._moderate_validate(raw_output)
            case AgentPosture.AUTONOMOUS | AgentPosture.DELEGATING:
                return self._soft_validate(raw_output)
```

### Delegate auto-detects posture from envelope

```python
class Delegate:
    def __init__(self, model, *, signature=None, envelope=None, ...):
        # If envelope is provided, read posture from it
        if envelope and envelope.posture_ceiling:
            posture = envelope.posture_ceiling
        else:
            posture = AgentPosture.AUTONOMOUS  # default for Delegate

        config = BaseAgentConfig(model=model, posture=posture)
        inner = BaseAgent(config=config, signature=signature, ...)
        ...
```

### Cross-SDK parity

Rust's `AgentConfig` already has `execution_mode: ExecutionMode { Autonomous, SingleShot }`. This maps to:

- `SingleShot` → `AgentPosture::Tool`
- `Autonomous` → `AgentPosture::Autonomous`

Rust should expand `ExecutionMode` to match the full posture spectrum, or add a separate `posture` field on `AgentConfig`.

## This Needs to Float Up to Loom

Per user instruction, this ADR and the CO Five Layers mapping need to be codified into the loom-level COC artifacts:

1. **`loom/.claude/rules/agent-reasoning.md`** should reference the CO Five Layers mapping and the posture-aware enforcement model
2. **`loom/.claude/skills/co-reference/`** should include the layer → component mapping table
3. **`loom/.claude/skills/04-kaizen/`** should reference this ADR for how Kaizen primitives map to CO layers
4. **`loom/.claude/agents/frameworks/kaizen-specialist.md`** should know about posture-aware instruction enforcement

This codification happens during the `/codify` phase of this workspace.

## Related ADRs

- **ADR-001**: Composition over extension points (provides the wrapper stack that implements the layers)
- **ADR-002**: BaseAgent keeps Node inheritance (BaseAgent as Intent + Instructions owner)
- **ADR-003**: Streaming as wrapper (StreamingAgent implements the autonomous execution path)
- **ADR-006**: Single ConstraintEnvelope (the Guardrails layer's data type)
- **ADR-007**: Delegate as composition facade (the Autonomous Agent entry point)

## Related Specs

- **SPEC-03**: Composition wrappers (gains `posture` parameter)
- **SPEC-04**: BaseAgent slimming (gains `posture` in config)
- **SPEC-05**: Delegate facade (auto-detects posture from envelope)
- **SPEC-07**: ConstraintEnvelope (gains `posture_ceiling` field)

## Related CO/COC Documents

- `skills/co-reference/` — CO Five Layer architecture
- `rules/agent-reasoning.md` — LLM-first agent reasoning (the Instructions layer enforcement)
- `rules/pact-governance.md` — PACT principle P1 (envelope is recursive = Guardrails invariance)
