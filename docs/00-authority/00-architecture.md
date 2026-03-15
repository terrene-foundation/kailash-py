# Trust-Plane Architecture

## System Overview

TrustPlane sits between human authority and AI execution. It provides a cryptographic record of every decision, delegation, and verification in an AI-assisted project.

```
Human Authority
    |
    v
TrustPlane (attestation layer)
    |--- Decisions (what was decided, why, by whom)
    |--- Milestones (what was produced, verified against what)
    |--- Delegations (who can act, with what constraints)
    |--- Holds (what was paused for human review)
    |--- Constraints (what limits apply: temporal, financial, data, comms)
    |
    v
AI Execution (constrained by trust plane)
```

## Module Map

### Core Domain

```
trustplane/
├── project.py          # TrustProject — lifecycle: create, load, check, verify
├── models.py           # Dataclasses: DecisionRecord, MilestoneRecord, constraints
├── delegation.py       # Delegation chains, cascade revocation, WAL recovery
├── holds.py            # Hold workflow: PENDING -> APPROVED/DENIED/OVERRIDE
├── exceptions.py       # Exception hierarchy (TrustPlaneError base)
├── config.py           # .trustplane.toml configuration with env var override
├── pathutils.py        # Cross-platform path normalization (always forward slashes)
└── _locking.py         # validate_id(), atomic_write(), safe_read_json(), O_NOFOLLOW
```

### Storage

```
trustplane/store/
├── __init__.py         # TrustPlaneStore protocol (typing.Protocol)
├── sqlite.py           # SQLite backend — WAL mode, schema versioning, migrations
├── filesystem.py       # Filesystem backend — atomic JSON files, filelock
└── postgres.py         # PostgreSQL backend — psycopg3, connection pooling, RLS
```

### Security & Identity

```
trustplane/
├── crypto_utils.py     # AES-256-GCM encryption at rest (HKDF key derivation)
├── rbac.py             # RBAC: 4 roles x 12 operations
├── identity.py         # OIDC provider config + JWT verification (PyJWT)
├── key_manager.py      # TrustPlaneKeyManager protocol + LocalFileKeyManager (Ed25519)
└── key_managers/
    ├── aws_kms.py      # AWS KMS (ECDSA P-256, boto3)
    ├── azure_keyvault.py  # Azure Key Vault (EC P-256)
    └── vault.py        # HashiCorp Vault Transit
```

### Enterprise

```
trustplane/
├── compliance.py       # SOC2/ISO 27001 evidence mapping, GRC CSV/JSON export
├── siem.py             # CEF v0 + OCSF 1.1 formatters, syslog handler
├── dashboard.py        # Web dashboard (stdlib http.server, localhost only)
├── dashboard_templates/ # HTML templates for dashboard
├── shadow.py           # Shadow mode observer (zero-config activity recording)
├── shadow_store.py     # Shadow data SQLite store
├── reports.py          # Trust summary reports
├── session.py          # Session management
├── mirror.py           # Trust chain mirroring
├── bundle.py           # Trust bundle export/import
├── diagnostics.py      # Trust chain diagnostics
└── migrate.py          # Schema migration (filesystem->SQLite, version upgrades)
```

### Integrations

```
trustplane/
├── proxy.py            # MCP proxy for constraint enforcement
├── mcp_server.py       # FastMCP server (trustplane-mcp entry point)
├── cli.py              # Click CLI (attest entry point)
├── conformance/        # Backend conformance test suite
├── integration/
│   ├── claude_code/    # Claude Code hook integration
│   └── cursor/         # Cursor IDE hook integration
└── templates/          # Project templates (quickstart)
```

## Data Flow

### Project Initialization

```
attest init --name "Project" --author "User"
    |
    v
TrustProject.create()
    |--- Creates .trust-plane/ directory
    |--- Generates Ed25519 keypair
    |--- Creates genesis attestation (EATP chain root)
    |--- Initializes store (SQLite by default)
    |--- Writes .trustplane.toml config
    v
Ready for decisions/milestones/delegations
```

### Constraint Checking

```
project.check(action="write_file", resource="/src/main.py")
    |
    v
Load constraints from manifest
    |--- Check temporal bounds (start/end dates)
    |--- Check data access patterns (allowed/denied paths)
    |--- Check financial limits (cost tracking)
    |--- Check communication constraints
    v
Verdict: AUTO_APPROVED | FLAGGED | HELD | BLOCKED
    |
    (if HELD) -> HoldManager creates HoldRecord -> await human resolution
    (if BLOCKED) -> action denied, recorded
    (if AUTO_APPROVED/FLAGGED) -> action permitted, recorded
```

### Verification Chain

```
project.verify()
    |
    v
Level 1: Anchor integrity (hash chain continuity)
Level 2: Signature validity (Ed25519/ECDSA verification)
Level 3: Decision-milestone linkage (referential integrity)
Level 4: Delegation authority (capability chain validation)
    v
VerificationResult with per-level pass/fail
```

## Store Protocol

All persistence goes through `TrustPlaneStore` (`typing.Protocol`). Backends are interchangeable at project creation time.

| Method Group | Operations |
|-------------|------------|
| Decisions | `store_decision`, `get_decision`, `list_decisions` |
| Milestones | `store_milestone`, `get_milestone`, `list_milestones` |
| Holds | `store_hold`, `get_hold`, `list_holds`, `update_hold` |
| Delegates | `store_delegate`, `get_delegate`, `list_delegates`, `update_delegate` |
| Reviews | `store_review`, `list_reviews` |
| Manifest | `store_manifest`, `get_manifest` |
| Anchors | `store_anchor`, `get_anchor`, `list_anchors` |
| WAL | `store_wal`, `get_wal`, `delete_wal` |
| Lifecycle | `initialize`, `close` |

All list methods accept `limit` parameter (default 1000, max enforced). All ID parameters validated before use.
