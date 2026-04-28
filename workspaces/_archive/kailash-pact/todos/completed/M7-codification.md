# Milestone 7: Codification (Phase 05)

Dependencies: Milestone 4 (package working, CI green)
Can run in parallel with Milestone 6

---

## TODO-23: Create pact-specialist agent

**Priority**: MEDIUM
**Files**: Create `.claude/agents/frameworks/pact-specialist.md`

### Agent definition
- **Role**: PACT governance framework specialist
- **Scope**: D/T/R addressing, organization compilation, envelope model, access enforcement, GovernanceEngine usage, governed agent patterns, SQLite store implementation, REST API, YAML org loading
- **Relationship**: Peer to kaizen-specialist (agent execution) and eatp-expert (trust protocol)
- **Tools**: Read, Write, Edit, Bash, Grep, Glob, Task

### Acceptance criteria
- Agent definition follows existing framework specialist format
- Available as `pact-specialist` subagent type

---

## TODO-24: Create pact skills directory

**Priority**: MEDIUM
**Files**: Create `.claude/skills/XX-pact/` directory with skill files

### Skill files
1. `SKILL.md` — Index and quick reference
2. `pact-governance-engine.md` — Engine usage, initialization, decision API, SQLite backend
3. `pact-dtr-addressing.md` — D/T/R grammar rules, Address parsing, accountability chain
4. `pact-envelopes.md` — Three-layer model, monotonic tightening, intersection, defaults
5. `pact-access-enforcement.md` — 5-step algorithm, KSPs, bridges, clearance, compartments
6. `pact-governed-agents.md` — PactGovernedAgent, GovernanceContext (frozen), @governed_tool, middleware
7. `pact-kaizen-integration.md` — Wrapping Kaizen agents with PACT governance

### Acceptance criteria
- Skills loadable via `/pact` or skill trigger words
- Each skill contains accurate code examples from the integrated package

---

## TODO-25: Create pact-governance rule

**Priority**: HIGH (security-critical patterns)
**Files**: Create `.claude/rules/pact-governance.md`

### Rule scope
`packages/kailash-pact/**`

### MUST Rules
1. **Frozen GovernanceContext** — Agents receive `GovernanceContext(frozen=True)`, NEVER `GovernanceEngine`
2. **Monotonic Tightening** — Child envelopes MUST be equal to or more restrictive than parent envelopes
3. **D/T/R Grammar** — Every Department/Team MUST be immediately followed by exactly one Role
4. **Fail-Closed** — All `verify_action()` and `check_access()` error paths MUST return BLOCKED/DENY
5. **Default-Deny Tools** — Tools MUST be explicitly registered before execution
6. **NaN/Inf on Financial Fields** — All numeric constraint fields validated with `math.isfinite()`
7. **Compilation Limits** — Enforce MAX_COMPILATION_DEPTH, MAX_CHILDREN_PER_NODE, MAX_TOTAL_NODES
8. **Thread Safety** — All GovernanceEngine and store methods MUST acquire `self._lock`

### MUST NOT Rules
1. MUST NOT expose GovernanceEngine to agent code
2. MUST NOT bypass monotonic tightening
3. MUST NOT use bare `Exception` for governance errors

### Acceptance criteria
- Rule file follows existing rule format
- Scoped to `packages/kailash-pact/**`

---

## TODO-26: Update CLAUDE.md

**Priority**: MEDIUM
**Files**: `CLAUDE.md` (root)

### Changes
1. Add PACT to Kailash Platform table:
   ```
   | **PACT**     | Organizational governance (D/T/R)  | `pip install kailash-pact`   |
   ```
2. Add to Framework-First directive:
   - "Instead of custom governance/access control → check with **pact-specialist**"
3. Add pact-specialist to Agents section (Framework Specialists)
4. Add pact skills to Skills Navigation
5. Add `pact-governance.md` to Rules Index

### Acceptance criteria
- CLAUDE.md references pact-specialist, pact skills, and pact rules

---

## TODO-27: Update security-reviewer agent

**Priority**: HIGH (governance-specific attack vectors)
**Files**: `.claude/agents/security-reviewer.md`

### Add governance security checks
1. **Anti-self-modification**: Verify agents receive GovernanceContext, never GovernanceEngine
2. **Monotonic tightening**: Verify envelope intersection only tightens, never widens
3. **Fail-closed decisions**: Verify every try/except in GovernanceEngine returns BLOCKED/DENY
4. **Posture ceiling enforcement**: Verify effective_clearance() caps at POSTURE_CEILING[posture]
5. **Default-deny tools**: Verify no path allows tool execution without registration
6. **NaN/Inf on governance paths**: Financial constraint checks in verify_action()
7. **Compilation resource limits**: Verify MAX_COMPILATION_DEPTH, MAX_CHILDREN_PER_NODE, MAX_TOTAL_NODES

### Acceptance criteria
- Security reviewer knows to check governance-specific attack vectors
- Scope includes `packages/kailash-pact/**`

---

## TODO-28: Update agents.md rule

**Priority**: LOW
**Files**: `.claude/rules/agents.md`

### Changes
Add to Rule 3 (Framework Specialist for Framework Work):
```
- **pact-specialist**: For any organizational governance work
```

### Acceptance criteria
- Rule 3 includes pact-specialist routing
