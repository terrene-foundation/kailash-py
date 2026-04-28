# Cross-Repo Deconfliction: kaizen-agents / kailash-py / kailash-rs

**Date**: 2026-03-23
**Purpose**: Define clear ownership boundaries and remove unauthorized work

---

## The Problem

Three repos have overlapping kaizen-agents/kz-cli work:

| Repo                          | What Exists                                                                                | Should It?              |
| ----------------------------- | ------------------------------------------------------------------------------------------ | ----------------------- |
| **kaizen-agents** (this repo) | Orchestration layer + kz CLI (13.5K LOC)                                                   | YES — this is the owner |
| **kailash-py**                | `workspaces/kaizen-cli/` (75KB analysis) + `workspaces/kaizen-l3/` (L3 orchestration plan) | PARTIALLY — see below   |
| **kailash-rs**                | `workspaces/kaizen-l3/` (kaizen-agents plan, 10 phases, 8 ADRs)                            | PARTIALLY — see below   |

---

## Ownership Rules

### This Repo (kaizen-agents) OWNS:

1. **kaizen_agents package** — the LLM-driven orchestration layer
2. **kz package** — the CLI binary
3. **Behavioral specification** — how orchestration works (this is the reference)
4. **Integration tests** — proving orchestration works against real SDK
5. **L3 primitive specs** — authored HERE, delivered to SDK repos as specs

### kailash-py OWNS:

1. **L3 SDK primitives** (kaizen.l3) — deterministic, no LLM. Already done (v2.1.0)
2. **Phase 0 SDK prerequisites** — making primitives consumable by orchestration layer
3. **Their own orchestration integration** — `kaizen/orchestration/l3/` as THEIR bridge to the SDK (if they want one)

### kailash-rs OWNS:

1. **L3 SDK primitives** (Rust) — already done
2. **Their own kaizen-agents** (Rust) — using THIS repo as behavioral reference
3. **kz-rs binary** (Rust) — their CLI implementation

---

## What Must Be Removed

### From kailash-py:

**`workspaces/kaizen-cli/`** — This entire workspace must be removed or archived.

Why it shouldn't exist:

- kaizen-cli is a CONSUMER of kailash-py, not part of it
- Its specs belong in THIS repo, not in the SDK
- It was created against the agreement (specs only to SDK repos)

**Action**: Archive to `workspaces/kaizen-cli/archive/` or delete. The analysis docs have value as reference but they're in the wrong repo.

### From kailash-py `workspaces/kaizen-l3/`:

The L3 workspace is legitimate — it's the SDK's own work. But it contains orchestration layer plans that belong HERE:

**Keep**:

- All L3 primitive specs (01-05)
- L3 SDK implementation milestones (M0-M6)
- L3 red team results
- Phase 0 SDK prerequisite planning

**Remove or transfer**:

- Orchestration layer architecture plans → belong in THIS repo
- Module path decisions for `kaizen/orchestration/l3/` → that's kailash-py's internal decision, fine to keep
- But the orchestration layer BEHAVIORAL SPEC should come from THIS repo

### From kailash-rs `workspaces/kaizen-l3/`:

**Keep**:

- L3 primitive implementation (already done, 3 red team rounds converged)
- kailash-rs-specific ADRs for their Rust kaizen-agents (ADR-001 through ADR-008)
- Their kaizen-agents plan (10 phases) — this is THEIR implementation plan
- Their kz-cli flows — this is THEIR CLI plan

**Align**:

- Their plan references "Python reference (690 tests)" as behavioral spec
- That reference is currently hollow (zero SDK integration)
- They MUST wait for this repo to be properly wired before using it as reference
- OR they proceed independently using the SPEC (not the code) as reference

---

## The Phase 0 Decision

kailash-py found three SDK limitations (The Hard Truth). Two paths forward:

### Path A: Wait for kailash-py Phase 0

kailash-py fixes the SDK first:

- Async PlanExecutor (or async adapter)
- HELD as resolvable state
- Structured output from Signatures

Then this repo wires to the fixed SDK.

**Pro**: Clean integration. Orchestration layer uses SDK as designed.
**Con**: Blocked on kailash-py. Calendar time.

### Path B: Adapt to SDK As-Is

This repo adapts to the current SDK reality:

- PlanMonitor runs its own async execution loop, uses PlanValidator + Plan types from SDK
- Recovery treats HELD as event-driven (listen for "held" events, nodes stay FAILED)
- PlanComposer uses `complete_structured()` with JSON Schema, not Signatures

**Pro**: Unblocked. Can proceed immediately.
**Con**: More orchestration-layer code that might become redundant when SDK evolves.

### Recommendation: Path B

The orchestration layer's job is to add intelligence on top of SDK primitives. If the SDK's PlanExecutor is sync, the orchestration layer adds async execution. If HELD is phantom, the orchestration layer manages hold state. If Signatures are strings, the orchestration layer parses them.

This is the correct layer boundary: SDK provides deterministic primitives, orchestration adds LLM-driven behavior. Waiting for the SDK to become async doesn't make sense — the LLM boundary IS inherently async.

kailash-py Phase 0 work is still valuable (it improves the SDK for all consumers), but it shouldn't block THIS repo.

---

## kailash-rs Alignment

### The 8 ADR Decisions

kailash-rs has 8 pending architecture decisions for their kaizen-agents. This repo should provide input:

| ADR                        | Decision                                      | This Repo's Input                                   |
| -------------------------- | --------------------------------------------- | --------------------------------------------------- |
| 001: Crate boundary        | Module in kailash-kaizen + separate kz binary | Aligned — matches our package split                 |
| 002: LLM structured output | `complete_structured<T>()` with schemars      | Aligned — our `complete_structured()` does the same |
| 003: Tool registry         | Dynamic + permission overlay                  | Aligned — our permission system works the same way  |
| 004: Config format         | TOML, 3-level merge                           | Aligned — matches our TOML config                   |
| 005: Agent loop            | Async stream-based, model-driven              | Aligned — our loop.py does native function calling  |
| 006: Display               | crossterm + termimad (no TUI framework)       | Aligned — our display.py is line-oriented           |
| 007: Session format        | JSON in .kz/sessions/                         | Aligned — our session manager uses JSON             |
| 008: Hook system           | Subprocess, JSON protocol, exit codes         | Aligned — our hook manager matches                  |

**Recommendation**: Approve all 8 ADRs. They align with this repo's patterns. Let kailash-rs proceed to build kz-rs. Once THIS repo is properly wired to kailash-py SDK, kailash-rs uses the behavioral test suite (not the Python code) as their conformance target.

---

## Handoff Protocol

### This Repo → kailash-py

- **Delivers**: L3 primitive specs (already done — briefs 00-05)
- **Delivers**: Bug reports if SDK primitives don't work as specified
- **Does NOT deliver**: Orchestration layer code, CLI code, or workspace analysis

### This Repo → kailash-rs

- **Delivers**: Behavioral test suite (once properly wired to SDK)
- **Delivers**: Orchestration spec (what the kaizen-agents layer DOES, not how)
- **Does NOT deliver**: Python code for porting (Rust idioms differ)

### kailash-py → This Repo

- **Delivers**: SDK L3 primitives via PyPI (`kaizen.l3` imports)
- **Delivers**: Phase 0 SDK improvements when ready (async PlanExecutor, etc.)
- **Does NOT deliver**: Orchestration layer (that's OUR job)

### kailash-rs → This Repo

- **Delivers**: Reference kz-rs implementation for cross-language alignment
- **Delivers**: Red team findings on behavioral divergence
- **Does NOT deliver**: Code to port (Rust is independent implementation)

---

## Action Items

### Immediate (this session)

1. Proceed with Path B (adapt to SDK as-is)
2. Write revised implementation plan for this repo
3. Begin /todos phase

### Next Session (kailash-py)

1. Archive `workspaces/kaizen-cli/` (wrong repo)
2. Continue Phase 0 SDK prerequisites independently
3. Publish SDK improvements as they're ready (this repo picks them up via PyPI)

### Next Session (kailash-rs)

1. Approve 8 ADRs
2. Proceed to /todos and /implement for their kaizen-agents
3. Use behavioral spec (not Python code) as reference
