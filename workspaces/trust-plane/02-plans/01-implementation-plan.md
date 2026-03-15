# TrustPlane Implementation Plan

## Scope

Two parallel tracks:

1. **Monorepo Integration** — get trust-plane working in kailash-py
2. **Product Hardening** — resolve ALL gaps for day-1 completeness

**Design principle**: SQLite is the default storage backend (not filesystem). Users are heavy researchers generating high volumes of records. Filesystem remains available as an option for inspectability.

---

## Phase 1: Monorepo Integration + Cross-Platform Foundation

### 1.1 Python Version Alignment

- Fix `requires-python` in trust-plane pyproject.toml: `>=3.10` → `>=3.11`
- Reason: eatp requires >=3.11 for `tomllib`; trust-plane depends on eatp

### 1.2 Cross-Platform Support

- Replace `fcntl` with `filelock>=3.0` in both packages:
  - `packages/trust-plane/src/trustplane/_locking.py` — replace `fcntl.flock()` calls
  - `packages/eatp/src/eatp/store/filesystem.py` — replace `fcntl.flock()` calls
- Fix `os.rename()` → `os.replace()` in `_locking.py` (Windows atomic rename)
- Fix `posixpath` → `os.path` in `project.py` (cross-platform path normalization)
- Add `filelock>=3.0` to both `pyproject.toml` files
- Note: `filelock` doesn't support shared locks, but reads are already safe (atomic write-then-rename pattern)

### 1.3 Path Dependency for Development

- Add path dependency to pyproject.toml for local development:
  ```toml
  [tool.hatch.envs.default]
  dependencies = ["eatp @ file:///{root}/../eatp"]
  ```
- Keep `eatp>=0.1.0,<1.0.0` as the published dependency

### 1.4 Import Verification

- Run trust-plane tests against local eatp to catch API drift from gap-closure fixes
- Verify all 15+ eatp imports resolve correctly
- Special attention to modules we modified: `scoring.py`, `key_manager.py`, `hooks.py`, `broadcaster.py`, `execution_context.py`, `store/memory.py`

### 1.5 Entry Point Verification

- Test `attest` CLI entry point in monorepo context
- Test `trustplane-mcp` MCP server entry point
- Verify Python path resolution with editable installs

### 1.6 CI Integration

- Add trust-plane to monorepo test pipeline
- Ensure test isolation (separate conftest.py)
- Cross-package integration tests: trust-plane + eatp together
- Add Windows CI runner (`windows-latest` in GitHub Actions)

### 1.7 Security Hygiene

- Verify `.env` in trust-plane is either template-only or in .gitignore
- Apply Rust red team cross-reference fixes (F2, F4, P-H1, P-H2 — already done)
- Strengthen `from_dict()` validation across trust-plane models

---

## Phase 2: Store Abstraction + SQLite Default

### 2.1 EATP SqliteTrustStore

- Implement `SqliteTrustStore` in `packages/eatp/src/eatp/store/sqlite.py`
- Schema: `trust_chains` table with `agent_id TEXT PRIMARY KEY`, `chain_data TEXT (JSON)`, `active BOOLEAN`, timestamps, `authority_id TEXT`
- Implement all 7+1 `TrustStore` ABC methods
- Use stdlib `sqlite3` with `asyncio.to_thread()` wrapper (zero new dependencies, matches `FilesystemStore` precedent of sync I/O in async methods)
- WAL mode for concurrent read support
- Comprehensive tests mirroring `InMemoryTrustStore` test coverage

### 2.2 TrustPlane Store Protocol

- Define `TrustPlaneStore` protocol with methods for each record type:
  - Decisions: `store_decision()`, `get_decision()`, `list_decisions()`
  - Milestones: `store_milestone()`, `get_milestone()`, `list_milestones()`
  - Anchors: `store_anchor()`, `get_anchor()`, `list_anchors()`
  - Holds: `store_hold()`, `get_hold()`, `list_holds()`, `update_hold()`
  - Delegates: `store_delegate()`, `get_delegate()`, `list_delegates()`, `update_delegate()`
  - Manifest: `store_manifest()`, `get_manifest()`
  - Query: `count()`, `list_by_time_range()`, pagination support
- Extract current filesystem logic into `FileSystemTrustPlaneStore`
- Update 10 importing modules to use the abstraction

### 2.3 TrustPlane SQLite Backend

- Implement `SqliteTrustPlaneStore` with appropriate schema
- SQLite as the **default** backend for new `attest init` projects
- Filesystem available via `attest init --store filesystem` for inspectability
- Migration path: `attest migrate --to sqlite` for existing filesystem projects
- Single-file `.trust-plane/trust.db` — still portable and git-ignorable

### 2.4 Cross-Package Testing

- Run trust-plane conformance suite against both store backends
- Verify enforcement behavior matches expectations with SQLite
- Test constraint tightening with fixed `ExecutionContext.with_delegation()` (F-02)
- Edge cases from EATP fixes: bounded broadcaster, immutable scoring, input validation

---

## Phase 3: Developer Experience

### 3.1 Shadow Mode First Onboarding

- Add `attest shadow` command for zero-config observation
- Automatically instruments MCP server in observation-only mode
- Produces structured report of AI activity
- **This is the single highest-impact feature for adoption**

### 3.2 GitHub Action

- Create `trustplane/verify-action@v1`
- Runs `attest verify` in CI, posts verification status
- Immediate value for any adopter

### 3.3 Quickstart Experience

- Add `attest quickstart` that creates sensible defaults
- Templates for common domains (web app, data pipeline, research)
- "Why should I care?" section in README

### 3.4 Pre-commit Hook

- `attest verify` as pre-commit hook
- Reject commits that violate constraint envelope

---

## Phase 4: Enterprise Readiness

### 4.1 SIEM Integration

- Export trust events in CEF/OCSF format (leverage eatp SIEM module)
- Syslog exporter for enterprise security stacks

### 4.2 SSO/RBAC

- Integrate with organizational identity providers
- Role-based access control for delegation management

### 4.3 Dashboard

- Web-based trust status viewer
- Build on verification bundle HTML export
- Real-time constraint utilization display

### 4.4 SOC2 Evidence Mapping

- Map audit report outputs to SOC2 control categories
- Export formats compatible with GRC tools

### 4.5 HSM/KMS Key Management

- Integrate with AWS KMS, Azure Key Vault, HashiCorp Vault
- Leverage EATP's existing `AwsKmsKeyManager` as foundation

### 4.6 PostgreSQL Backend

- Implement `PostgresTrustPlaneStore` for enterprise multi-user deployments
- Support concurrent multi-process access beyond SQLite's limits
- Multi-tenancy support

---

## Dependencies

| Phase | Depends On                  | Risk                             |
| ----- | --------------------------- | -------------------------------- |
| 1     | eatp-gaps fixes complete    | LOW — we just completed them     |
| 2     | Phase 1 integration working | LOW — EATP TrustStore ABC exists |
| 3     | Phase 2 passing             | LOW                              |
| 4     | Phase 3 validated           | MEDIUM — enterprise features     |

---

## Decision Points (Resolved)

1. **Separate PyPI package or eatp submodule?**
   - **Decision**: Separate package. Trust-plane has distinct user persona.

2. **Windows support priority?**
   - **Decision**: Day 1. Use `filelock` library (cross-platform, 90M+ monthly downloads).

3. **Store abstraction timing?**
   - **Decision**: Phase 2 (day 1). SQLite is the default backend. Users are heavy researchers.

4. **Multi-user strategy?**
   - **Decision**: SQLite handles concurrent readers natively (WAL mode). PostgreSQL for multi-machine in Phase 4.
