# COC Analysis: kailash-pact Integration

## Convention Drift Findings

### Error Hierarchy — NON-COMPLIANT

EATP rules require all errors to inherit from `TrustError` with `.details: Dict[str, Any]`. PACT errors inherit from bare `Exception`:

- `GovernanceBlockedError(Exception)`
- `GovernanceHeldError(Exception)`
- `CompilationError(Exception)`
- `ConfigurationError(Exception)`
- `EnvelopeAdapterError(Exception)`
- `MonotonicTighteningError(ValueError)`

**Decision needed**: Define `PactError` base class (parallel to `TrustError`) or bring under EATP hierarchy.

### Pydantic Usage — MIXED

Core governance types are dataclasses (compliant). `ConstraintEnvelopeConfig` and sub-configs are Pydantic (from standalone repo). `model_dump()` calls found in `context.py`, `engine.py`, `stores/sqlite.py`, `stores/backup.py` — all on the Pydantic config types.

## Security Blindness Findings

The `security-reviewer` agent has no knowledge of 6 governance-specific attack vectors:

1. **Clearance escalation via posture manipulation** — manipulating posture level raises clearance ceiling
2. **Envelope widening via intersection bypass** — bypassing monotonic tightening invariant
3. **Compartment bypass** — empty compartment set on SECRET/TOP_SECRET items
4. **Default-deny bypass via tool registration** — `register_tool()` accessible to agent
5. **Org compilation resource exhaustion** — deep/wide org definitions as DoS
6. **NaN/Inf on governance cost paths** — financial constraint checks in `verify_action()`

## Phase 05 Codification Plan

### New Agent

- `.claude/agents/frameworks/pact-specialist.md` — D/T/R addressing, envelopes, access enforcement, GovernanceEngine, governed agents

### New Skills Directory (`.claude/skills/XX-pact/`)

- `SKILL.md` — Index
- `pact-governance-engine.md` — Engine usage, initialization, SQLite backend
- `pact-dtr-addressing.md` — D/T/R grammar, accountability chain
- `pact-envelopes.md` — Three-layer model, monotonic tightening
- `pact-access-enforcement.md` — 5-step algorithm, KSPs, bridges
- `pact-governed-agents.md` — PactGovernedAgent, GovernanceContext, @governed_tool
- `pact-kaizen-integration.md` — Wrapping Kaizen agents with PACT governance

### New Rule

- `.claude/rules/pact-governance.md` — Frozen context, monotonic tightening, fail-closed, thread safety, compilation limits

### Updates

- `CLAUDE.md` — Add PACT to platform table, framework-first directive, agents section
- `.claude/agents/security-reviewer.md` — Governance-specific security checks
- `.claude/rules/agents.md` — Add pact-specialist to Rule 3

## Key Architectural Pattern: Anti-Self-Modification Defense

Agents receive `GovernanceContext(frozen=True)`, NEVER `GovernanceEngine`. The engine is private (`_engine`). This prevents agents from modifying their own governance constraints. Validated by `test_self_modification_defense.py` (18 tests).

This is a reusable pattern for any system where agents must be constrained from modifying their own permissions.
