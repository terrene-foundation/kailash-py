# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.1] - 2026-03-18

### Added

- Financial budget enforcement: `DecisionRecord.cost` field, `AuditSession.session_cost` tracking, `TrustProject.check()` budget gate, `budget_status` property
- `BudgetExhaustedError` exception (subclass of `ConstraintViolationError`) with structured attributes (session_cost, budget_limit, action_cost)
- 26 new E2E tests: lifecycle chain integrity, budget depletion, NaN bypass regression, frozen constraint mutation, mode switching, store conformance
- `.details: dict[str, Any]` parameter on all 23 exception classes (EATP convention)

### Changed

- Exception hierarchy consolidated: all 23 classes centralized in `trustplane.exceptions` (previously 6 were scattered across modules)
- All 5 constraint sub-dataclasses (`OperationalConstraints`, `DataAccessConstraints`, `FinancialConstraints`, `TemporalConstraints`, `CommunicationConstraints`) are now `frozen=True`
- Store backends raise `RecordNotFoundError` instead of `KeyError` (backward-compatible: `RecordNotFoundError` inherits from `KeyError`)
- `from __future__ import annotations` added to models.py, session.py, project.py
- `__all__` exports added to models.py, session.py, project.py

### Security

- R15-C1: NaN bypass in `check()` budget gate — `math.isfinite()` validation on context cost (Pattern 12)
- R15-C2: NaN poisoning in `session.record_action()` — ValueError on NaN/Inf/negative cost
- R15-H2: Session cost deserialization NaN check in `from_dict()`
- R15-H3: PostgreSQL migration error sanitization via `_sanitize_conninfo()`
- R15-M4: SQLite WAL/SHM file permissions set to 0o600
- R16-M3: Frozen constraint sub-dataclasses prevent post-init mutation bypass
- R16: `except KeyError` narrowed to `except RecordNotFoundError` in delegation cascade and manifest reload
- R16: `DecisionRecord.from_dict()` cost field pre-validation (defense-in-depth)
- 16 rounds of red teaming converged at zero findings across all severity levels

## [0.2.0] - 2026-03-15

### Added

- SQLite storage backend (default for new projects)
- Store abstraction layer (`TrustPlaneStore` protocol) for pluggable backends
- PostgreSQL storage backend (optional: `pip install trust-plane[postgres]`)
- `attest migrate --to sqlite` migration command for filesystem-to-SQLite conversion
- Schema versioning with forward-compatible migration runner
- Shadow mode (`attest shadow`) for zero-config AI activity observation
- Shadow reports in Markdown and JSON formats
- Quickstart wizard (`attest quickstart`) for guided project setup
- Domain templates: governance, software, research, data-pipeline, minimal
- Template commands: `attest template list`, `attest template apply`, `attest template describe`
- SIEM integration: CEF, OCSF, and syslog export formats
- SOC2 and ISO 27001 compliance evidence export (`attest export --format soc2`)
- Encryption at rest (AES-256-GCM, opt-in via `--encrypt`)
- HSM/KMS key management: AWS KMS, Azure Key Vault, HashiCorp Vault
- SSO/RBAC: OIDC identity verification and role-based access control
- Web dashboard (`attest dashboard`) for trust status visualization
- Multi-tenancy support with per-tenant isolation
- Cursor IDE integration (`attest integration setup cursor`)
- GitHub Action for CI verification (`actions/verify-action`)
- Pre-commit hook for trust chain verification
- Cross-platform support (Windows via filelock)
- `.trustplane.toml` configuration file with env var overrides
- Comprehensive tutorial and conceptual documentation
- Codified store backend implementation skill

### Changed

- Default storage backend changed from filesystem to SQLite
- Python minimum version raised from 3.10 to 3.11 (aligns with eatp)
- `os.rename` replaced with `os.replace` for atomic rename on Windows

### Fixed

- POSIX-only file locking replaced with cross-platform filelock library
- posixpath usage replaced with os.path for Windows compatibility
- Missing `validate_id()` in `store_review()` (R13 finding H1)
- Non-atomic migration fixed with raw SQL inserts (R13 finding H2)
- Negative limit bypass in list queries (R13 finding M2)
- Database file permissions set to 0o600 on POSIX (R13 finding M1)

### Security

- F2: MultiSigPolicy frozen=True (immutable after construction)
- F4: Key material zeroized on revocation
- F4: TLS socket leak prevention on syslog handshake failure
- F6: RBAC mtime-based cache invalidation for cross-process consistency
- F10: CEF header newline/CR injection prevention
- P-H1: hmac.compare_digest for all hash/token/signature comparisons
- P-H2: Private key deleted from memory after registration
- H-1: safe_read_text for dashboard token loading
- H-2: Explicit limit=100_000 on SIEM list calls
- H-3: math.isfinite on OIDC max_age_hours
- H-4: HTTPS validation on OIDC issuer_url
- H-5: Algorithm-first JWKS key resolution for key rotation
- C-2: hmac.compare_digest for archive hash verification
- R13: Store abstraction security gate — 4 findings fixed, 0 remaining
- R14: 16 code + 3 doc fixes across 3 rounds — converged at zero CRITICAL/HIGH
- 14 rounds of red teaming converged at zero findings

## [0.1.0] - 2026-02-15

### Added

- Initial release with filesystem-backed trust environment
- EATP integration (trust chains, delegation, verification)
- CLI (`attest`) with init, decide, milestone, verify, status, export commands
- MCP server for AI assistant integration
- Hold workflow for human-in-the-loop decisions
- Multi-stakeholder delegation with cascade revocation
- Constraint envelopes with 5 dimensions (operational, data access, financial, temporal, communication)
- 4-level verification (manifest, decisions, milestones, anchors)
- Verification bundle export (JSON, HTML)
