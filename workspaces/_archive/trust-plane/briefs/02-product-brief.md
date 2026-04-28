# TrustPlane Product Brief

## Product

**TrustPlane** is the EATP reference implementation — the trust environment through which AI-assisted work happens. It sits between human authority and AI execution, providing cryptographic attestation for decisions, milestones, and verification in collaborative projects.

## Positioning

**"The `git init` of AI accountability"** — ubiquity through ease of adoption.

Every project that uses AI should be able to answer: who authorized what, why, and with what constraints? TrustPlane makes this as simple as `attest init`.

## What It Does

- **Genesis Record**: Establishes the root of trust for any project
- **Constraint Envelope**: All five EATP dimensions (Financial, Operational, Temporal, Data Access, Communication) with monotonic tightening
- **Decision Records**: Human-readable decisions with EATP Audit Anchor + Reasoning Trace
- **Milestone Records**: FULL-verification checkpoints with file hashing
- **Mirror Records**: ExecutionRecord/EscalationRecord/InterventionRecord (CARE Mirror Thesis)
- **Competency Map**: What AI handles autonomously vs. where humans contribute
- **Trust Postures**: PSEUDO_AGENT → SUPERVISED → SHARED_PLANNING → CONTINUOUS_INSIGHT → DELEGATED
- **Enforcement**: Strict (blocks/holds) and Shadow (logs only) modes with runtime switching
- **Hold/Approve Workflow**: Actions exceeding envelope are queued for human resolution
- **MCP Server**: 5 tools (trust_check, trust_record, trust_envelope, trust_status, trust_verify) for AI assistant integration
- **Verification Bundle**: Self-contained export (JSON/HTML) for independent verification
- **Audit Reports**: Markdown reports with timeline, constraints, competency map
- **Session Tracking**: File change tracking with SHA-256 snapshots and git HEAD correlation

## Tech Stack

- Python 3.12+
- EATP SDK (`eatp>=0.1.0`) — FilesystemStore, StrictEnforcer, ShadowEnforcer, PostureStateMachine, ReasoningTrace, ConfidentialityLevel
- MCP protocol (`mcp>=1.0.0`) — FastMCP server for AI tool integration
- Click — CLI framework
- JSON persistence — no database required

## Architecture

```
Human defines constraint envelope (Trust Plane)
│
▼
TrustPlane (EATP reference implementation)
├── VERIFY every action against constraint envelope
├── AUDIT every verification (signed Audit Anchor)
├── RECORD decisions with reasoning traces
├── MIRROR human engagement patterns
│
▼
Any Execution Tool (Claude Code, Cursor, Windsurf, custom)
├── Talks to TrustPlane via MCP tools
├── Follows contextual guidance (Tier 1 rules)
├── Pre-tool-use hooks validate actions (Tier 2)
│
▼
Immutable Audit Store (FilesystemStore)
├── Every action recorded with full trust lineage
├── Verification gradient determines audit depth
└── Anyone can verify with public key only
```

### Enforcement Tiers

| Tier | Mechanism | Status |
|------|-----------|--------|
| 1 | Rule file (contextual guidance for AI) | Implemented |
| 2 | Pre-tool-use hook (process validation) | Implemented |
| 3 | MCP proxy (transport-level enforcement) | Implemented |

## Users

- **AI-assisted teams**: Any team using AI tools for collaborative work
- **Enterprises**: Organizations needing AI accountability for compliance
- **Auditors**: Independent verification of AI decision trails
- **EATP implementers**: Reference implementation for building EATP-conformant systems

## Constraints

- **Foundation product**: Must use Foundation standards (EATP, CARE, CO)
- **License**: Apache 2.0 (Foundation-owned)
- **LLM-agnostic**: Works with any AI execution tool, not tied to any vendor
- **No database required**: FilesystemStore for zero-dependency adoption

## Authority Claim

TrustPlane is the EATP reference implementation with:
- Full five-dimension constraint envelopes
- Real EATP chain verification (not fake chains)
- Trust posture progression per EATP spec
- Mirror Thesis operationalization per CARE spec
- Enforcement modes matching EATP StrictEnforcer/ShadowEnforcer
- Independent verification via VerificationBundle

## Current State (v0.2.0)

- 431 tests passing (21 test files)
- Core modules: project, models, session, mirror, bundle, reports, holds, mcp_server, cli, proxy, templates, diagnostics, delegation, conformance, _locking
- CLI: attest init/decide/milestone/verify/status/decisions/mirror/export/audit/migrate/template/delegate/diagnose
- MCP: 5 trust tools for AI assistant integration
- MCP Proxy: Transport-level enforcement (Tier 3) with fail-closed behavior, symlink-safe config loading, atomic config writes
- Constraint Templates: 3 pre-built templates (governance, software, research)
- Constraint Diagnostics: Quality scoring (0-100) with actionable recommendations
- Delegation: Multi-stakeholder oversight with configurable depth, cascade revocation (deque-based BFS), WAL recovery with content hash
- Conformance Suite: EATP Complete conformance with behavioral verification (ungameable), REASONING_REQUIRED + dual-binding signing tests, all reads symlink-protected
- Cross-process concurrency: fcntl.flock-based locking with configurable timeout, atomic writes (write-to-temp-then-rename)
- In-process concurrency: asyncio.Lock on ALL state-mutating methods (including switch_enforcement, verify)
- WAL recovery: Write-ahead log with mandatory SHA-256 content hash (missing hash = rejection)
- Symlink protection: ALL file reads across ALL modules use O_NOFOLLOW (safe_read_json, _safe_read_text, _hash_file). Zero bare open() calls in production code.
- fd leak prevention: safe_read_json() closes fd on os.fdopen() failure
- ID collision prevention: Random nonce in ALL ID generation (projects, sessions, delegates, holds, decisions, milestones, executions, escalations, interventions)
- EATP v2.2 dual-binding: reasoning_trace_hash persisted in ALL anchor types (decision, execution, escalation, intervention)
- Repair verification: repair() re-verifies parent chain after fixes
- Iterative revocation: cascade revocation uses deque work queue (no stack overflow, O(1) popleft)
- Secure key creation: private keys created with 0o600 mode + O_NOFOLLOW atomically (no world-readable window, no symlink redirect)
- Migration safety: migrate.py uses safe_read_json() for reads and atomic_write() for writes
- Claude Code integration: rule file, hook script, anti-amnesia template

## Roadmap

- **M10-02**: Reference implementation documentation (deferred to monorepo migration)
- **M10-03**: Monorepo migration to kailash-py (cross-repo operation)
