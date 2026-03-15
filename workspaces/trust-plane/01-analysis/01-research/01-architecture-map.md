# TrustPlane Architecture Map

## Overview

TrustPlane is a 7,785 LOC Python package implementing the EATP reference — a trust environment sitting between human authority and AI execution. It provides cryptographic attestation for decisions, milestones, and verification in collaborative projects.

**Version**: 0.2.0 (Alpha)
**Tests**: 431 passing across 21 test files
**Red team**: 12 rounds, converged at zero findings (R12)

---

## Layered Architecture

### Layer 1: Security Primitives (`_locking.py` — 235 LOC)

| Primitive            | Purpose                                           |
| -------------------- | ------------------------------------------------- |
| `file_lock()`        | fcntl.flock cross-process exclusive locking       |
| `atomic_write()`     | crash-safe JSON persistence via temp+rename+fsync |
| `safe_read_json()`   | symlink-protected reads (O_NOFOLLOW)              |
| `_safe_read_text()`  | O_NOFOLLOW text read                              |
| `validate_id()`      | path traversal prevention                         |
| `compute_wal_hash()` | write-ahead log integrity (SHA-256)               |

### Layer 2: Domain Models (`models.py` — 850 LOC)

All dataclasses with `.to_dict()` / `.from_dict()` serialization.

**Constraint Dimensions (5 EATP):**

- `OperationalConstraints`: allowed/blocked actions
- `DataAccessConstraints`: path patterns, read/write scopes
- `FinancialConstraints`: cost limits, budget tracking
- `TemporalConstraints`: session hours, cooldown windows
- `CommunicationConstraints`: channel gates, review requirements
- `ConstraintEnvelope`: composite with monotonic tightening (`is_tighter_than()`)

**Records (Mirror Thesis):**

- `DecisionRecord`: decisions with reasoning trace
- `ExecutionRecord`: autonomous AI actions
- `EscalationRecord`: AI boundary reached
- `InterventionRecord`: human unprompted engagement
- `MilestoneRecord`: versioned checkpoints with file hashing

**Enums:**

- `DecisionType`: 13 types (SCOPE, ARGUMENT, EVIDENCE, etc.)
- `HumanCompetency`: 6 CARE Mirror categories
- `VerificationCategory`: AUTO_APPROVED, FLAGGED, HELD, BLOCKED
- `ReviewRequirement`: QUICK, STANDARD, FULL

### Layer 3: Core Orchestrator (`project.py` — 1,759 LOC)

**Class: `TrustProject`** — wraps full EATP lifecycle:

```
create() / load()           → Project lifecycle
check(action, context)      → Constraint gating → Verdict
record_decision/milestone() → Audit trail with signed anchors
record_execution/escalation/intervention() → Mirror Thesis
verify()                    → 4-level chain integrity validation
start_session() / end_session() → Audit context bracketing
switch_enforcement()        → strict ↔ shadow mode toggle
transition_posture()        → Trust state management
```

**EATP Integration:**

```python
from eatp import CapabilityRequest, TrustKeyManager, TrustOperations
from eatp.chain import ActionResult, AuthorityType, CapabilityType, VerificationResult
from eatp.crypto import generate_keypair
from eatp.enforce.strict import HeldBehavior, StrictEnforcer, Verdict
from eatp.enforce.shadow import ShadowEnforcer
from eatp.postures import PostureStateMachine, PostureTransitionRequest, TrustPosture
from eatp.reasoning import ConfidentialityLevel, ReasoningTrace
from eatp.store.filesystem import FilesystemStore
```

9 distinct eatp submodules imported.

### Layer 4: Domain Services

| Module           | LOC | Purpose                                                            |
| ---------------- | --- | ------------------------------------------------------------------ |
| `delegation.py`  | 576 | Multi-stakeholder delegation with cascade revocation, WAL recovery |
| `holds.py`       | 149 | Hold/Approve workflow for HELD verdicts                            |
| `session.py`     | 236 | Session tracking with file snapshots, Git HEAD correlation         |
| `mirror.py`      | 235 | CARE Mirror Thesis — `build_competency_map()`                      |
| `diagnostics.py` | 316 | Constraint quality scoring (0-100) with recommendations            |
| `reports.py`     | 169 | Markdown audit report generation                                   |
| `bundle.py`      | 391 | VerificationBundle export (JSON + HTML)                            |

### Layer 5: Integration Surfaces

| Module          | LOC | Purpose                                                            |
| --------------- | --- | ------------------------------------------------------------------ |
| `cli.py`        | 560 | Click CLI — 12 subcommands (init, decide, milestone, verify, etc.) |
| `mcp_server.py` | 242 | FastMCP — 5 trust tools for AI assistants                          |
| `proxy.py`      | 393 | MCP proxy — Tier 3 transport-level enforcement                     |

### Layer 6: Templates & Conformance

| Module                    | LOC   | Purpose                                                           |
| ------------------------- | ----- | ----------------------------------------------------------------- |
| `templates/__init__.py`   | 201   | 3 pre-built constraint envelopes (governance, software, research) |
| `conformance/__init__.py` | 1,232 | EATP conformance suite (RFC 2119 levels)                          |
| `migrate.py`              | 193   | Pre-v0.2.1 to FilesystemStore migration                           |

---

## Constraint Checking Algorithm (`.check()`)

```
1. Load ConstraintEnvelope from manifest
2. If no constraints → AUTO_APPROVED

Operational:
  If action in blocked_actions → BLOCKED
  If allowed_actions set AND action not in it → BLOCKED

Data access (if resource path given):
  If matches blocked_paths/patterns → BLOCKED
  If read/write_paths set AND not matching → FLAG

Financial/Temporal/Communication:
  Check at boundary → FLAG if near limit

If flagged → HELD (awaiting human resolution)
Else → AUTO_APPROVED

Create EATP audit anchor with reasoning trace
Return Verdict enum
```

---

## Enforcement Tiers

| Tier | Mechanism                              | Bypass Risk                   | Location                   |
| ---- | -------------------------------------- | ----------------------------- | -------------------------- |
| 1    | Rule file (contextual guidance)        | HIGH — AI can ignore          | `integration/claude_code/` |
| 2    | Pre-tool-use hook (process validation) | MEDIUM — runs in AI process   | `integration/claude_code/` |
| 3    | MCP proxy (transport enforcement)      | LOW — infrastructure-enforced | `proxy.py`                 |

Tier 3 is the strongest differentiator — fail-closed design means AI physically cannot reach tools without constraint checking.

---

## File Layout (trust-plane directory)

```
trust-plane/
├── manifest.json              # ProjectManifest
├── genesis.json               # EATP genesis record
├── keys/
│   ├── private.key            # Ed25519 (mode 0o600)
│   └── public.key
├── chains/                    # FilesystemStore
├── decisions/dec-*.json
├── milestones/ms-*.json
├── anchors/anchor-*.json
├── holds/hold-*.json
├── delegation/
├── sessions/session-*.json
└── .lock                      # fcntl lock file
```

---

## Security Pattern Inventory

| Pattern                              | Location        | Purpose                              |
| ------------------------------------ | --------------- | ------------------------------------ |
| `safe_read_json()` (O_NOFOLLOW)      | `_locking.py`   | Symlink attack prevention            |
| `atomic_write()` (temp+fsync+rename) | `_locking.py`   | Crash safety                         |
| `validate_id()`                      | `_locking.py`   | Path traversal prevention            |
| `_filter_arguments()`                | `proxy.py`      | Argument injection prevention        |
| `math.isfinite()`                    | `models.py`     | NaN/Inf constraint bypass prevention |
| `deque(maxlen=)`                     | `proxy.py`      | Bounded call log                     |
| `_MAX_SNAPSHOT_FILES`                | `session.py`    | Bounded file traversal               |
| mtime cache invalidation             | `mcp_server.py` | Stale constraint prevention          |
| `fcntl.flock`                        | `_locking.py`   | Cross-process locking                |
| `0o600` key creation                 | `project.py`    | Private key protection               |
| WAL with SHA-256 content hash        | `delegation.py` | Crash recovery integrity             |
