# Codebase Inventory — EATP + Trust-Plane Merge

## 1. Current Dependency Graph

```
kailash (core SDK v1.0.0)
├── kailash-dataflow v1.1.0    [kailash only]
├── kailash-nexus v1.4.2       [kailash only]
└── kailash-kaizen v1.3.0      [kailash + eatp]
        │
        └── eatp v0.2.0        [standalone — no kailash dependency]
                │
                └── trust-plane v0.2.1  [eatp only — no kailash dependency]
```

**Key observations:**

- EATP and trust-plane are **fully independent** of kailash core
- Only kaizen bridges the split (depends on both kailash and eatp)
- DataFlow and Nexus are EATP-agnostic
- No circular dependencies exist
- No `kailash.trust` namespace exists yet — clean merge target
- No `kailash-pact` package exists yet

## 2. Package Inventory

### 2.1 EATP (`packages/eatp/`)

| Metric         | Value      |
| -------------- | ---------- |
| Version        | 0.2.0      |
| Python modules | 116        |
| Source LOC     | ~55,600    |
| Test files     | 72         |
| Test LOC       | ~47,200    |
| Subpackages    | 18         |
| Entry points   | `eatp` CLI |

**Dependencies (required):**

- `pynacl>=1.5` — Ed25519 cryptography (C extension)
- `pydantic>=2.6` — Data validation
- `jsonschema>=4.21` — Schema validation
- `click>=8.0` — CLI framework
- `filelock>=3.0` — Cross-process locking

**Optional dependencies:**

- `postgres`: asyncpg, sqlalchemy[asyncio]
- `aws-kms`: boto3
- `observability`: opentelemetry-api

**Subpackage map:**

| Subpackage     | Files | LOC   | Purpose                                 |
| -------------- | ----- | ----- | --------------------------------------- |
| a2a/           | 7     | 1,997 | Agent-to-agent communication            |
| cli/           | 3     | 1,836 | Command-line interface                  |
| constraints/   | 8     | 3,614 | Constraint dimensions + budget tracking |
| enforce/       | 7     | 2,203 | Strict/shadow enforcement modes         |
| esa/           | 7     | 4,422 | Enterprise Service Architecture         |
| export/        | 3     | 898   | Compliance + SIEM export                |
| governance/    | 6     | 2,330 | Policy engine, cost estimation          |
| interop/       | 7     | 3,915 | JWT, W3C VC, DID, UCAN, SD-JWT, Biscuit |
| knowledge/     | 4     | 1,397 | Knowledge graph + provenance            |
| mcp/           | 2     | 1,604 | MCP server integration                  |
| messaging/     | 7     | 1,859 | Signed envelopes + replay protection    |
| migrations/    | 2     | 501   | Schema migrations                       |
| operations/    | 1     | 1,986 | Core trust operations                   |
| orchestration/ | 8     | 3,152 | Workflow orchestration                  |
| registry/      | 6     | 2,262 | Agent discovery + registration          |
| revocation/    | 3     | 1,090 | Trust revocation + cascade              |
| store/         | 4     | 1,727 | Trust chain persistence                 |
| templates/     | 1     | —     | Template system                         |

**Core root modules:**

- `chain.py` — TrustLineageChain, GenesisRecord, DelegationRecord, AuditAnchor, VerificationResult
- `crypto.py` — sign, verify_signature, dual_sign, generate_keypair
- `authority.py` — OrganizationalAuthority, AuthorityPermission
- `postures.py` — TrustPosture, PostureStateMachine
- `reasoning.py` — ReasoningTrace, ConfidentialityLevel
- `exceptions.py` — TrustError hierarchy
- `execution_context.py` — Execution context
- `hooks.py` — EATPHook, HookRegistry
- `roles.py` — TrustRole, ROLE_PERMISSIONS
- `vocabulary.py` — POSTURE_VOCABULARY, CONSTRAINT_VOCABULARY

### 2.2 Trust-Plane (`packages/trust-plane/`)

| Metric         | Value                                     |
| -------------- | ----------------------------------------- |
| Version        | 0.2.1                                     |
| Python modules | 30+                                       |
| Source LOC     | ~20,000                                   |
| Test files     | 59                                        |
| Test LOC       | ~21,500                                   |
| Total tests    | ~1,500                                    |
| Entry points   | `attest` CLI, `trustplane-mcp` MCP server |

**Dependencies (required):**

- `eatp>=0.1.0,<1.0.0` — EATP SDK
- `click>=8.0` — CLI framework
- `filelock>=3.0` — File locking
- `mcp>=1.0.0` — MCP server

**Optional dependencies:**

- `postgres`: psycopg[binary], psycopg_pool
- `aws`: boto3
- `azure`: azure-keyvault-keys, azure-identity
- `vault`: hvac
- `encryption`: cryptography
- `sso`: PyJWT, cryptography

**Module map (by function):**

| Module            | LOC   | Purpose                                                   |
| ----------------- | ----- | --------------------------------------------------------- |
| project.py        | 1,929 | TrustProject lifecycle + EATP integration                 |
| cli.py            | 2,282 | Click CLI entry point                                     |
| compliance.py     | 1,314 | Constraint compliance + budget checking                   |
| conformance/      | 1,233 | Conformance test framework                                |
| models.py         | 940   | Data models (5 constraint classes, decisions, milestones) |
| dashboard.py      | 792   | Web dashboard (FastAPI)                                   |
| store/postgres.py | 773   | PostgreSQL backend                                        |
| store/sqlite.py   | 727   | SQLite backend (default)                                  |
| siem.py           | 738   | SIEM event export (CEF/OCSF)                              |
| identity.py       | 650   | OIDC JWT verification                                     |
| shadow.py         | 602   | Shadow mode enforcement                                   |
| delegation.py     | 590   | Delegation + human review                                 |
| shadow_store.py   | 479   | Shadow audit log                                          |
| archive.py        | 444   | Long-term record archival                                 |
| bundle.py         | ~400  | Archive bundle management                                 |
| config.py         | ~300  | Project configuration (TOML)                              |
| session.py        | ~270  | Audit session context                                     |
| mcp_server.py     | ~280  | FastMCP server                                            |
| migrate.py        | ~450  | Store backend migration                                   |
| proxy.py          | ~400  | MCP proxy for enforcement                                 |
| rbac.py           | ~340  | Role-based access control                                 |
| exceptions.py     | ~280  | 22-class exception hierarchy                              |
| key_manager.py    | ~230  | Key management protocol                                   |
| diagnostics.py    | ~300  | Constraint quality analysis                               |
| mirror.py         | ~240  | Competency mapping (Mirror Thesis)                        |
| holds.py          | ~160  | On-hold decision workflow                                 |
| reports.py        | ~180  | Report generation                                         |
| crypto_utils.py   | ~120  | Cryptographic utilities                                   |
| \_locking.py      | ~250  | File I/O security (O_NOFOLLOW, atomic_write)              |
| pathutils.py      | ~60   | Path normalization                                        |

**Store backends (TrustPlaneStore protocol):**

- SQLite (default) — WAL mode, schema versioning
- PostgreSQL — psycopg3, connection pooling
- Filesystem — JSON files, git-compatible

**Security patterns (12 hardened):**

1. `validate_id()` — path traversal prevention
2. `O_NOFOLLOW` via `safe_read_json()` — symlink attack prevention
3. `atomic_write()` — crash-safe writes
4. `safe_read_json()` — symlink-safe deserialization
5. `math.isfinite()` — NaN/Inf protection
6. Bounded collections (maxlen) — OOM prevention
7. Monotonic escalation — trust ratcheting
8. `hmac.compare_digest()` — timing side-channel protection
9. Key material zeroization — memory safety
10. `frozen=True` dataclasses — immutable constraint objects
11. `from_dict()` validation — JSON tampering detection
12. `isfinite()` on runtime costs — budget bypass prevention

### 2.3 Kailash Core (`src/kailash/`)

| Metric          | Value          |
| --------------- | -------------- |
| Version         | 1.0.0          |
| Subdirectories  | 29             |
| Trust namespace | Does NOT exist |

**Core dependencies:**

- `jsonschema>=4.24.0`
- `networkx>=2.7`
- `pydantic>=1.9`
- `pyyaml>=6.0`

**Existing optional extras (relevant):**

- `[mcp]` — mcp
- `[database]` — sqlalchemy, aiosqlite
- `[postgres]` — asyncpg
- `[auth]` — bcrypt, PyJWT

### 2.4 Kailash Kaizen (`packages/kailash-kaizen/`)

| Metric          | Value                                      |
| --------------- | ------------------------------------------ |
| Version         | 1.3.0                                      |
| EATP dependency | `eatp>=0.1.0` (declared, active via shims) |

**EATP integration:**

- `kaizen/trust/` directory contains ~20 shim modules
- Each shim re-exports from `eatp.*` (e.g., `from eatp.crypto import ...`)
- `kaizen/__init__.py` re-exports 200+ symbols including EATP types
- `kaizen/trust/audit_store.py` is the ONLY integration point where EATP + kailash frameworks intersect (uses DataFlow + AsyncLocalRuntime)

## 3. Design Collision Points

### 3.1 Store Abstraction Collision

|          | EATP `store/`                                        | Trust-Plane `store/`                              |
| -------- | ---------------------------------------------------- | ------------------------------------------------- |
| Protocol | `TrustStore` (ABC)                                   | `TrustPlaneStore` (Protocol)                      |
| Purpose  | Chain persistence (genesis, delegation, attestation) | Record persistence (decisions, milestones, holds) |
| Backends | Memory, SQLite, Filesystem                           | SQLite, PostgreSQL, Filesystem                    |
| Methods  | get/store chain records                              | get/store decisions, milestones, holds, delegates |

**These are complementary, not competing.** EATP stores trust chains; trust-plane stores governance records. Both are needed.

### 3.2 Exception Hierarchy Collision

| EATP                      | Trust-Plane                         |
| ------------------------- | ----------------------------------- |
| `TrustError` (base)       | `TrustPlaneError` (base)            |
| `TrustChainNotFoundError` | `RecordNotFoundError`               |
| `InvalidSignatureError`   | `SigningError`, `VerificationError` |
| `HookError`               | `KeyManagerError`                   |
| `ProximityError`          | `ConstraintViolationError`          |

Trust-plane already has `RecordNotFoundError` inheriting from both `TrustPlaneStoreError` AND `KeyError`.

### 3.3 Crypto Module Collision

- EATP: `crypto.py` (Ed25519 sign/verify, generate_keypair, HMAC)
- Trust-Plane: `crypto_utils.py` (Ed25519 helpers, wraps EATP crypto)

### 3.4 CLI Entry Points

- EATP: `eatp` → `eatp.cli:main`
- Trust-Plane: `attest` → `trustplane.cli:main`
- Trust-Plane: `trustplane-mcp` → `trustplane.mcp_server:main`

## 4. Cross-Package Import Inventory

### 4.1 Trust-Plane imports from EATP (20+ entry points)

```python
from eatp import CapabilityRequest, TrustKeyManager, TrustOperations
from eatp.authority import AuthorityPermission, OrganizationalAuthority
from eatp.chain import ActionResult, AuthorityType, CapabilityType, VerificationResult
from eatp.crypto import generate_keypair
from eatp.enforce.shadow import ShadowEnforcer
from eatp.enforce.strict import HeldBehavior, StrictEnforcer, Verdict
from eatp.postures import PostureStateMachine, PostureTransitionRequest, TrustPosture
from eatp.reasoning import ConfidentialityLevel, ReasoningTrace
from eatp.store.filesystem import FilesystemStore
```

### 4.2 Kaizen imports from EATP (~20 shim modules)

All in `packages/kailash-kaizen/src/kaizen/trust/`:

- `constraint_validator.py` → `eatp.constraint_validator`
- `audit_service.py` → `eatp.audit_service`
- `audit_store.py` → `eatp.audit_store`
- `cache.py` → `eatp.cache`
- `crypto.py` → `eatp.crypto`
- `execution_context.py` → `eatp.execution_context`
- `exceptions.py` → `eatp.exceptions`
- `metrics.py` → `eatp.metrics`
- `postures.py` → `eatp.postures`
- `reasoning.py` → `eatp.reasoning`
- `rotation.py` → `eatp.rotation`
- `timestamping.py` → `eatp.timestamping`
- `messaging/envelope.py` → `eatp.messaging.envelope`
- `messaging/verifier.py` → `eatp.messaging.verifier`
- `messaging/signer.py` → `eatp.messaging.signer`
- `messaging/channel.py` → `eatp.messaging.channel`
- `messaging/replay_protection.py` → `eatp.messaging.replay_protection`
- `messaging/exceptions.py` → `eatp.messaging.exceptions`

### 4.3 No imports in the reverse direction

- EATP does NOT import from kailash, trust-plane, or kaizen
- Trust-plane does NOT import from kailash or kaizen
- DataFlow and Nexus do NOT import from EATP or trust-plane

## 5. Version and Publishing Status

| Package          | PyPI Name        | Current Version | Published?                  |
| ---------------- | ---------------- | --------------- | --------------------------- |
| kailash          | kailash          | 1.0.0           | Yes                         |
| eatp             | eatp             | 0.2.0           | Yes                         |
| trust-plane      | trust-plane      | 0.2.1           | Yes (dist/ has 0.2.0 wheel) |
| kailash-kaizen   | kailash-kaizen   | 1.3.0           | Yes                         |
| kailash-dataflow | kailash-dataflow | 1.1.0           | Yes                         |
| kailash-nexus    | kailash-nexus    | 1.4.2           | Yes                         |

## 6. Key Decision Points

1. **Version strategy**: kailash 2.0 (semver break) vs 1.x additive
2. **Dependency strategy**: pynacl always-installed vs behind `kailash[trust]` extra
3. **Namespace design**: flat `kailash.trust.*` vs nested `kailash.trust.protocol.*` + `kailash.trust.plane.*`
4. **Exception unification**: merge hierarchies or keep separate under one root?
5. **Store coexistence**: how do two `store/` directories with different protocols merge?
6. **CLI consolidation**: merge CLIs or keep separate entry points?
7. **Kaizen shim strategy**: update to `from kailash.trust...` or keep compatibility layer?
