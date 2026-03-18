# TrustPlane Package Instructions

**Last Updated**: 2026-03-18
**Do Not Edit Without Review**: Changes to this file affect the security posture of every session that touches trust-plane. Run `/redteam` after any modification.

## Overview

TrustPlane is the EATP reference implementation — a trust environment through which AI-assisted work happens. It sits between human authority and AI execution, providing cryptographic attestation for decisions, milestones, and verification in collaborative projects.

**Status**: 1499 tests passing. 16 rounds of red teaming — converged at zero findings (R16). 61+ hardening todos completed. v0.2.1 released. Store abstraction complete with SQLite default, filesystem, and PostgreSQL backends. Enterprise features (RBAC, OIDC, SIEM, dashboard, archive, shadow mode) fully implemented. Exception hierarchy fully unified (22 classes with `.details` param, all trace to TrustPlaneError). Budget enforcement wired (posture-budget tracking, NaN-hardened).

## What NOT to Change — Security Patterns

These 11 patterns were hardened through 12 rounds of red teaming. Each represents a real vulnerability that was discovered and fixed. DO NOT simplify, remove, or "clean up" any of these patterns without running `/redteam` first.

### Pattern 1: `validate_id()` for path traversal prevention

```python
# DO:
from trustplane._locking import validate_id
validate_id(record_id)  # Raises ValueError on "../", "/", etc.
path = store_dir / f"{record_id}.json"

# DO NOT:
path = store_dir / f"{user_input}.json"  # Path traversal: "../../../etc/passwd"
```

**Why**: Any externally-sourced record ID used in a filesystem path or SQL query MUST be validated first. The regex `^[a-zA-Z0-9_-]+$` prevents directory traversal and SQL injection via IDs.

### Pattern 2: `O_NOFOLLOW` via `safe_read_json()` / `safe_open()`

```python
# DO:
data = safe_read_json(path)  # Opens with O_NOFOLLOW, prevents symlink following

# DO NOT:
with open(path) as f:  # Follows symlinks — attacker redirects to arbitrary file
    data = json.load(f)
```

**Why**: Symlink attacks redirect file reads/writes to attacker-controlled locations. `O_NOFOLLOW` raises `ELOOP` if the path is a symlink. On Windows, `O_NOFOLLOW` is unavailable — this is a documented security degradation.

### Pattern 3: `atomic_write()` for ALL record writes

```python
# DO:
atomic_write(path, json.dumps(record.to_dict()))

# DO NOT:
with open(path, 'w') as f:  # Partial write on crash = corrupted record
    json.dump(record, f)
```

**Why**: Partial writes on crash produce corrupted records. `atomic_write()` uses temp file + `fsync` + `os.replace()` for crash safety. The `O_NOFOLLOW` flag also prevents symlink attacks during writes.

### Pattern 4: `safe_read_json()` for ALL JSON deserialization

```python
# DO:
data = safe_read_json(path)

# DO NOT:
data = json.loads(path.read_text())  # No symlink protection, no fd safety
```

**Why**: Combines `O_NOFOLLOW`, proper fd lifecycle management, and JSON parsing in one safe call. Using `path.read_text()` bypasses all protections.

### Pattern 5: `math.isfinite()` on all numeric constraint fields

```python
# DO (in __post_init__ or from_dict):
if self.max_cost_per_session is not None and not math.isfinite(self.max_cost_per_session):
    raise ValueError("max_cost_per_session must be finite")

# DO NOT:
if self.max_cost_per_session is not None and self.max_cost_per_session < 0:
    # Missing: NaN passes this check, Inf passes this check
```

**Why**: `NaN` and `Inf` bypass numeric comparisons (`NaN < 0` is `False`, `Inf < 0` is `False`). An attacker can set constraints to `NaN` to make all checks pass.

### Pattern 6: Bounded collections

```python
# DO:
call_log: deque = field(default_factory=lambda: deque(maxlen=10000))

# DO NOT:
call_log: list = field(default_factory=list)  # Grows without bound → OOM
```

**Why**: Unbounded collections in long-running processes (MCP proxy, delegation chains) lead to memory exhaustion. Trim oldest 10% when at capacity.

### Pattern 7: Monotonic escalation only

```python
# DO:
# AUTO_APPROVED → FLAGGED → HELD → BLOCKED (only forward)

# DO NOT:
if some_condition:
    verdict = Verdict.AUTO_APPROVED  # Downgrading from HELD is forbidden
```

**Why**: Trust state can only escalate, never relax. A HELD action cannot become AUTO_APPROVED — it must be explicitly resolved through the hold workflow.

### Pattern 8: `hmac.compare_digest()` for hash/signature comparison

```python
# DO:
import hmac as hmac_mod
if not hmac_mod.compare_digest(stored_hash, computed_hash):
    raise TamperDetectedError(...)

# DO NOT:
if stored_hash != computed_hash:  # Timing side-channel for byte-by-byte forgery
```

**Why**: String equality (`==`) leaks timing information. An attacker can measure comparison time to determine how many bytes match, enabling incremental hash forgery.

### Pattern 9: Key material zeroization

```python
# DO:
key_mgr.register_key(key_id, private_key)
del private_key  # Remove reference immediately after use

# On revocation:
self._keys[key_id] = ""  # Clear key material, keep tombstone

# DO NOT:
key_mgr.register_key(key_id, private_key)
# private_key persists in scope — visible to memory dumps
```

**Why**: Private key material in memory is vulnerable to debugger inspection and memory dumps. Python strings are immutable so true zeroing requires `ctypes`, but `del` removes the reference and clearing to empty string is the minimum defense.

### Pattern 10: `MultiSigPolicy` is `frozen=True`

```python
# DO:
@dataclass(frozen=True)
class MultiSigPolicy:
    required_signatures: int
    total_signers: int
    ...

# DO NOT:
@dataclass  # Mutable — fields can be changed after __post_init__ validation
class MultiSigPolicy:
```

**Why**: Without `frozen=True`, an attacker with object reference can bypass `__post_init__` validation by directly setting fields (e.g., `policy.required_signatures = 0`).

### Pattern 11: `from_dict()` validates all fields

```python
# DO:
@classmethod
def from_dict(cls, data: Dict[str, Any]) -> "Self":
    if "required_field" not in data:
        raise ValueError("missing required_field")
    return cls(required_field=data["required_field"])

# DO NOT:
@classmethod
def from_dict(cls, data: Dict[str, Any]) -> "Self":
    return cls(required_field=data.get("required_field", ""))  # Silent default
```

**Why**: Silent defaults in `from_dict()` accept malformed/tampered JSON without raising errors. A corrupted or attacker-modified record should fail loudly, not silently produce an object with default values.

### Pattern 12: `math.isfinite()` on ALL runtime cost values

```python
# DO (in check() and record_action()):
import math
action_cost = float(ctx.get("cost", 0.0))
if not math.isfinite(action_cost) or action_cost < 0:
    return Verdict.BLOCKED  # Fail-closed

# DO NOT:
action_cost = float(ctx.get("cost", 0.0))
if action_cost > limit:  # NaN > limit is False — bypass!
    return Verdict.BLOCKED
```

**Why**: `NaN` bypasses ALL numeric comparisons (`NaN > X` is always `False`). If `NaN` enters `session_cost` via `+=`, it permanently poisons the accumulator — all future budget checks pass. Pattern 5 covers constraint fields at construction; Pattern 12 covers runtime cost values from context dicts and deserialized sessions.

---

## Store Security Contract

All `TrustPlaneStore` backends MUST satisfy this contract. Failure to satisfy any requirement is a security defect, not a feature gap.

1. **ATOMIC_WRITES**: Every record write is all-or-nothing. A crash during write MUST NOT produce a partial or corrupted record. (Filesystem: `atomic_write()`. SQLite: transaction. PostgreSQL: transaction.)

2. **INPUT_VALIDATION**: Every method that accepts a record ID or query parameter MUST validate that ID before using it in a filesystem path or SQL statement. Malformed IDs MUST raise `ValueError`. Use `validate_id()` or equivalent.

3. **BOUNDED_RESULTS**: Every list method (`list_decisions()`, `list_holds()`, etc.) MUST accept a `limit` parameter and MUST NOT return more than `limit` records. Default limit MUST be <= 1000. Unbounded queries are forbidden.

4. **PERMISSION_ISOLATION**: The store backend MUST enforce that the calling process only accesses records belonging to the current project. Records from other projects MUST NOT be visible. (Filesystem: directory scoping. SQLite: `WHERE project_id = ?`. PostgreSQL: RLS.)

5. **CONCURRENT_SAFETY**: The backend MUST handle concurrent reads and writes from multiple processes without data loss or corruption. (Filesystem: `filelock`. SQLite: WAL mode + `BEGIN IMMEDIATE`. PostgreSQL: MVCC.)

6. **NO_SILENT_FAILURES**: Every method MUST raise a specific, named exception (subclass of `TrustPlaneStoreError`) on failure. Methods MUST NOT return `None` or `False` to signal errors.

See `packages/trust-plane/src/trustplane/store/__init__.py` for the protocol definition (created in TODO-09).

---

## Red Team Convergence Evidence

| Fix    | Description                                        | Status    | Validated                        | Date       |
| ------ | -------------------------------------------------- | --------- | -------------------------------- | ---------- |
| R3-R12 | 12 rounds of progressive hardening                 | CONVERGED | deep-analyst + security-reviewer | 2026-03-14 |
| R13    | 38+ todos: enterprise hardening, RBAC, OIDC, SIEM  | CONVERGED | full test suite (1400+ tests)    | 2026-03-15 |
| F2/M-1 | MultiSigPolicy frozen=True                         | APPLIED   | manual verification              | 2026-03-15 |
| F4     | Key material zeroized on revocation                | APPLIED   | manual verification + unit test  | 2026-03-15 |
| P-H1   | hmac.compare_digest() in delegation.py, project.py | APPLIED   | manual verification              | 2026-03-15 |
| P-H2   | del private_key after register_key()               | APPLIED   | manual verification              | 2026-03-15 |
| T-44   | PostgreSQL exception wrapping (\_safe_connection)  | APPLIED   | 6 tests in test_postgres_store   | 2026-03-15 |
| T-45   | TLS syslog transport (RFC 5425)                    | APPLIED   | 4 tests in test_siem             | 2026-03-15 |
| T-53   | Dashboard bearer token auth (hmac.compare_digest)  | APPLIED   | 8 tests in test_dashboard        | 2026-03-15 |
| T-59   | MCP server thread-safe project access              | APPLIED   | threading.Lock on \_get_project  | 2026-03-15 |
| R14    | 16 code + 3 doc fixes (19 total across 3 rounds)   | CONVERGED | 4 agents, 1473 tests, 0 HIGH     | 2026-03-15 |
| R15-C1 | NaN bypass in check() budget gate (isfinite)       | APPLIED   | 4 regression tests               | 2026-03-18 |
| R15-C2 | NaN poisoning in session.record_action()           | APPLIED   | ValueError on NaN/Inf/negative   | 2026-03-18 |
| R15-H2 | session_cost deserialization NaN check             | APPLIED   | from_dict() validates isfinite   | 2026-03-18 |
| R15-H3 | Postgres migration error sanitization              | APPLIED   | \_sanitize_conninfo() on reason  | 2026-03-18 |
| R15-M4 | SQLite WAL/SHM file permissions to 0o600           | APPLIED   | chmod loop in initialize()       | 2026-03-18 |
| R15    | Integration hardening (budget, exceptions, E2E)    | CONVERGED | 3 agents, 1494 tests, 0 HIGH     | 2026-03-18 |

**Do not re-apply these fixes — they are already in place.**

---

## Cross-References

- `.claude/rules/trust-plane-security.md` — Scoped enforcement rules for trust-plane and EATP store code
- `.claude/rules/security.md` — Global security rules (secrets, injection, input validation)
- `.claude/rules/eatp.md` — EATP SDK conventions (dataclasses, error hierarchy, cryptography)
- `workspaces/trust-plane/briefs/01-integration-brief.md` — Full integration context and "What NOT to Change" list

## Store Architecture

TrustPlane uses a pluggable store architecture. All record persistence goes through the `TrustPlaneStore` protocol (`trustplane.store`).

### Available Backends

| Backend        | Class                       | Default | Use Case                                           |
| -------------- | --------------------------- | ------- | -------------------------------------------------- |
| **SQLite**     | `SqliteTrustPlaneStore`     | Yes     | Single-file, fast, handles high write volume       |
| **Filesystem** | `FileSystemTrustPlaneStore` | No      | Git-committed audit trails, file inspectability    |
| **PostgreSQL** | `PostgresTrustPlaneStore`   | No      | Multi-user production deployments, connection pool |

### Store Protocol

```python
from trustplane.store import TrustPlaneStore
from trustplane.store.sqlite import SqliteTrustPlaneStore
from trustplane.store.filesystem import FileSystemTrustPlaneStore
from trustplane.store.postgres import PostgresTrustPlaneStore

# SQLite (default for new projects)
store = SqliteTrustPlaneStore(".trust-plane/trust.db")
store.initialize()

# Filesystem (opt-in)
store = FileSystemTrustPlaneStore(Path(".trust-plane"))
store.initialize()

# PostgreSQL (production)
store = PostgresTrustPlaneStore("postgresql://user:pass@host/db")
store.initialize()

# TrustProject accepts any store
project = await TrustProject.create(trust_dir, name, author, tp_store=store)
```

### PostgreSQL Backend

The PostgreSQL backend (`trustplane.store.postgres`) uses `psycopg` v3 with connection pooling:

- All connections go through `_safe_connection()` context manager
- Provider exceptions (`psycopg.OperationalError`, `psycopg.Error`) are caught and wrapped as `StoreConnectionError` / `StoreQueryError`
- Connection strings are sanitized — `_sanitize_conninfo()` strips passwords from error messages
- Store errors are never double-wrapped (existing `StoreConnectionError`/`StoreQueryError` are re-raised as-is)

### Schema Versioning (SQLite)

The SQLite backend includes automatic schema versioning:

- `meta` table stores `schema_version`
- On open: checks version, runs migrations if needed
- `SchemaTooNewError` raised if database is from a newer trust-plane version
- `SchemaMigrationError` raised if migration fails (rolled back)

### Configuration

Per-project settings in `.trustplane.toml`:

```toml
[store]
backend = "sqlite"  # or "filesystem"
sqlite_path = ".trust-plane/trust.db"

[enforcement]
mode = "strict"  # or "shadow"
```

Load with `TrustPlaneConfig.load(project_dir)`. CLI flags override config file; env vars (`TRUSTPLANE_STORE`, `TRUSTPLANE_MODE`) override both.

## Execution Patterns

```python
# TrustProject lifecycle
project = await TrustProject.create(path, name, author)  # or
project = await TrustProject.load(path)

# Constraint checking (includes budget enforcement)
verdict = project.check(action="write_file", context={"resource": "/src/main.py"})
# Returns: Verdict.AUTO_APPROVED | FLAGGED | HELD | BLOCKED

# Recording decisions with cost tracking
decision = DecisionRecord(
    decision_type=DecisionType.TECHNICAL,
    decision="Use modular architecture",
    rationale="Separation of concerns",
    cost=5.50,  # Optional: tracked when budget_tracking=True
)
await project.record_decision(decision)

# Budget status (within a session)
status = project.budget_status
# {"budget_tracking": True, "session_cost": 25.0, "remaining": 75.0, ...}

# Verification
result = await project.verify()  # 4-level chain integrity check
```

## Platform File Permission Notes

- **POSIX**: Private key files created with `0o600` (owner read/write only). Database files (`.db`, `-wal`, `-shm`) also `0o600`.
- **Windows**: `os.chmod()` only controls the read-only attribute — it does NOT restrict access. The `set_private_file_permissions()` function in `project.py` uses `pywin32` to set a DACL restricting access to the current user's SID.
- **Windows degradation**: If `pywin32` is not installed, a warning is logged but the file is still written. Install via `pip install trust-plane[windows]`.

## Path Normalization Convention

Constraint patterns and resource paths stored in trust-plane records MUST use forward slashes, regardless of platform. Use `normalize_resource_path()` from `trustplane.pathutils` before storing or comparing paths.

- Do NOT use `posixpath.normpath`, `os.path.normpath`, or `Path.as_posix()` directly for constraint patterns.
- Normalization happens on ingress: `DataAccessConstraints.__post_init__()`, `from_dict()`, and CLI path arguments.
- At comparison time, both sides should already be normalized.

## Codified Skills

- **Store Backend Implementation**: `.claude/skills/project/store-backend-implementation.md` — step-by-step guide for adding new TrustPlaneStore backends, including the 6-requirement security contract checklist, common pitfalls, and conformance test setup.

## Exception Hierarchy

```
TrustPlaneError                          # Base for all trust-plane errors
  TrustPlaneStoreError                   # Base for store errors
    RecordNotFoundError(+KeyError)       # Record does not exist (also KeyError for backward compat)
    SchemaTooNewError                    # DB from newer trust-plane version
    SchemaMigrationError                 # Migration failed (rolled back)
    StoreConnectionError                 # Cannot connect to database
    StoreQueryError                      # Query/constraint failure
    StoreTransactionError                # Transaction commit/rollback failure
  TrustDecryptionError                   # Decryption failure (wrong key, tampered)
  KeyManagerError                        # Base for key manager errors
    KeyNotFoundError                     # Key does not exist in provider
    KeyExpiredError                      # Key expired or disabled
    SigningError                         # Signing operation failed
    VerificationError                    # Signature verification failed
  IdentityError                          # OIDC-specific errors
    TokenVerificationError               # JWT verification failure
    JWKSError                            # JWKS discovery/key retrieval failure
  RBACError                              # RBAC operation errors
  ConstraintViolationError                # Constraint check failure
    BudgetExhaustedError                 # Financial budget exceeded (session or per-action)
  ArchiveError                           # Archive operation errors
  TLSSyslogError                         # TLS syslog transport errors
  LockTimeoutError(TrustPlaneError, TimeoutError)  # File lock acquisition timeout (dual hierarchy)
```

Key manager implementations (AWS KMS, Azure Key Vault, HashiCorp Vault) MUST catch provider-specific exceptions and wrap them as `KeyManagerError` subclasses. The `provider` and `key_id` attributes help identify the source.

PostgreSQL store wraps `psycopg` exceptions: `OperationalError` -> `StoreConnectionError`, `Error` -> `StoreQueryError`. Connection info is sanitized to strip passwords.

---

## CLI Command Reference

Entry point: `attest` (Click-based CLI).

### Core Commands

| Command             | Description                       |
| ------------------- | --------------------------------- |
| `attest init`       | Initialize a new trust project    |
| `attest quickstart` | Interactive setup wizard          |
| `attest decide`     | Record a decision                 |
| `attest milestone`  | Record a milestone                |
| `attest verify`     | Verify chain integrity (4-level)  |
| `attest status`     | Show project status summary       |
| `attest decisions`  | List recorded decisions           |
| `attest export`     | Export project data               |
| `attest migrate`    | Migrate between store backends    |
| `attest dashboard`  | Launch the web dashboard          |
| `attest shadow`     | Shadow mode observation           |
| `attest enforce`    | Switch enforcement mode           |
| `attest audit`      | Generate audit report             |
| `attest mirror`     | Show Mirror Thesis competency map |
| `attest diagnose`   | Constraint quality analysis       |

### Command Groups

| Group                          | Subcommands                         |
| ------------------------------ | ----------------------------------- |
| `attest delegate ...`          | `add`, `list`, `revoke`             |
| `attest hold ...`              | `list`, `approve`, `deny`           |
| `attest template ...`          | `list`, `apply`, `describe`         |
| `attest tenants ...`           | `create`, `list`                    |
| `attest shadow-manage ...`     | `cleanup`, `stats`                  |
| `attest integration setup ...` | `cursor`                            |
| `attest identity ...`          | `setup`, `status`, `verify`         |
| `attest rbac ...`              | `assign`, `revoke`, `list`, `check` |
| `attest siem ...`              | `test`                              |
| `attest archive ...`           | `create`, `list`, `restore`         |

### Identity Commands (OIDC)

```bash
# Configure an OIDC provider
attest identity setup --issuer https://dev-123.okta.com --client-id abc123 --provider okta

# Check current configuration
attest identity status

# Verify a JWT token (uses JWKS auto-discovery)
attest identity verify eyJhbGciOiJSUzI1NiI...
```

Supported providers: `okta`, `azure_ad`, `google`, `generic_oidc`.

### RBAC Commands

```bash
# Assign a role (admin, auditor, delegate, observer)
attest rbac assign alice admin

# Check if a user can perform an operation
attest rbac check alice decide    # ALLOWED / DENIED

# List all role assignments
attest rbac list

# Revoke a user's role
attest rbac revoke alice
```

### SIEM Commands

```bash
# Send a test event (dry-run by default)
attest siem test --format cef
attest siem test --format ocsf

# Send via TLS syslog (RFC 5425)
attest siem test --format cef --host siem.example.com --port 6514 --tls \
  --ca-cert ca.pem --client-cert client.pem --client-key client-key.pem
```

### Archive Commands

```bash
# Archive records older than 365 days
attest archive create --max-age-days 365

# List archived bundles
attest archive list

# Restore from an archive
attest archive restore archive-20260101-120000
```

### Shadow Store Management

```bash
# Cleanup old shadow sessions
attest shadow-manage cleanup --max-age-days 90 --max-sessions 10000

# View shadow store statistics
attest shadow-manage stats
```

---

## Enterprise Features

### SIEM Integration (`trustplane.siem`)

Formats trust-plane events for enterprise SIEM consumption:

- **CEF** (Common Event Format) — HP ArcSight, Splunk via CEF
- **OCSF** (Open Cybersecurity Schema Framework) — AWS Security Lake, modern SIEMs
- Syslog transport: UDP (RFC 3164), TCP, TLS (RFC 5425 with octet-framing)
- Mutual TLS support: `--ca-cert`, `--client-cert`, `--client-key`
- All 6 record types supported: `DecisionRecord`, `MilestoneRecord`, `HoldRecord`, `ExecutionRecord`, `EscalationRecord`, `InterventionRecord`

### OIDC Identity Verification (`trustplane.identity`)

JWT token verification with automatic key rotation:

- `IdentityConfig`: Persists OIDC provider config via `atomic_write()` / `safe_read_json()`
- `JWKSProvider`: JWKS auto-discovery via `.well-known/openid-configuration`
  - In-memory caching with configurable TTL (default: 1 hour)
  - Automatic cache invalidation on `kid` mismatch (key rotation)
- `OIDCVerifier`: Full JWT verification (signature, expiry, issuer, audience, token age)

### RBAC (`trustplane.rbac`)

Role-based access control with 4 roles:

| Role       | Permissions                                           |
| ---------- | ----------------------------------------------------- |
| `admin`    | All operations                                        |
| `auditor`  | Read-only: verify, status, decisions, export          |
| `delegate` | Operational: decide, milestone, check, delegate, hold |
| `observer` | View-only: status, decisions                          |

Persisted atomically to `rbac.json` in the trust directory.

### Dashboard (`trustplane.dashboard`)

Web-based project dashboard with bearer token authentication:

- Token auto-generated on first launch, stored in `.dashboard-token`
- All `/api/` endpoints require `Authorization: Bearer <token>` header
- HTML pages accessible without auth (status overview only)
- `--no-auth` flag disables authentication (development mode)
- Uses `hmac.compare_digest()` for constant-time token comparison
- Paginated API responses for bounded results

### Shadow Mode (`trustplane.shadow_store`)

Non-blocking observation mode for AI tool calls:

- Separate `shadow.db` — independent from main `trust.db`
- WAL journal mode for concurrent readers
- Retention policies via `cleanup()`: age-based, count-based, size-based
- `validate_id()` on all public methods
- CLI management: `attest shadow-manage cleanup`, `attest shadow-manage stats`

### Store Archival (`trustplane.archive`)

Long-term record archival to compressed bundles:

- Archives decisions, milestones, and resolved holds older than N days
- ZIP bundles with SHA-256 integrity hash in manifest
- Tamper detection on restore (hash verification)
- Supports both SQLite and filesystem backends
- CLI: `attest archive create`, `attest archive list`, `attest archive restore`

### Cloud Key Managers (`trustplane.key_managers`)

| Provider        | Module                        | Algorithm   | Notes                      |
| --------------- | ----------------------------- | ----------- | -------------------------- |
| AWS KMS         | `key_managers.aws_kms`        | ECDSA P-256 | Ed25519 unavailable in KMS |
| Azure Key Vault | `key_managers.azure_keyvault` | ECDSA P-256 | Ed25519 unavailable in AKV |
| HashiCorp Vault | `key_managers.vault`          | ECDSA P-256 | Via Transit engine         |

All providers wrap native exceptions into `KeyManagerError` subclasses.

---

## Entry Points

- **CLI**: `attest` -> `trustplane.cli:main` (Click)
- **MCP Server**: `trustplane-mcp` -> `trustplane.mcp_server:main` (FastMCP)
- **Dashboard**: `attest dashboard` -> `trustplane.dashboard:run_dashboard`
- **Python API**: `from trustplane.project import TrustProject`
