# Trust-Plane Authority — Claude Code Instructions

**Package**: `trust-plane` v0.2.0
**Location**: `src/kailash/trust/plane/`
**Tests**: 1238 passing, 2 skipped

## Quick Context

TrustPlane is the EATP reference implementation — a trust environment for human-AI collaborative work. It provides cryptographic attestation for decisions, milestones, and verification in collaborative projects.

## What You Must Know

1. **SQLite is the default backend** — not filesystem. Users are researchers managing many projects.
2. **Store protocol** (`kailash.trust.plane.store.TrustPlaneStore`) — all persistence goes through this `typing.Protocol`. Three backends: SQLite (default), Filesystem, PostgreSQL.
3. **Security patterns are frozen** — 11 hardened patterns documented in `src/kailash/trust/plane/CLAUDE.md`. Do not simplify or remove any of them without running `/redteam`.
4. **Ed25519 is the default signing algorithm** — AWS KMS uses ECDSA P-256 (documented mismatch).
5. **Monotonic escalation only** — trust states can only go AUTO_APPROVED -> FLAGGED -> HELD -> BLOCKED, never backwards.

## Entry Points

- **CLI**: `attest` command (Click) — `kailash.trust.plane.cli:main`
- **MCP Server**: `trustplane-mcp` — `kailash.trust.plane.mcp_server:main`
- **Python API**: `from kailash.trust.plane.project import TrustProject`

## Configuration

Per-project config in `.trustplane.toml`. Precedence: CLI flags > env vars (`TRUSTPLANE_STORE`, `TRUSTPLANE_MODE`) > `.trustplane.toml` > defaults.

## Key Files

| File                  | Purpose                                                              |
| --------------------- | -------------------------------------------------------------------- |
| `project.py`          | `TrustProject` — main API class (create, load, check, verify)        |
| `store/__init__.py`   | `TrustPlaneStore` protocol definition                                |
| `store/sqlite.py`     | SQLite backend (default) with WAL mode, schema versioning            |
| `store/filesystem.py` | Filesystem backend with atomic writes, symlink protection            |
| `store/postgres.py`   | PostgreSQL backend with connection pooling                           |
| `models.py`           | All dataclasses (DecisionRecord, MilestoneRecord, constraints, etc.) |
| `delegation.py`       | Delegation chains, cascade revocation                                |
| `holds.py`            | Hold workflow (HELD actions require human resolution)                |
| `crypto_utils.py`     | AES-256-GCM encryption at rest                                       |
| `rbac.py`             | Role-Based Access Control (admin, auditor, delegate, observer)       |
| `key_manager.py`      | `TrustPlaneKeyManager` protocol + `LocalFileKeyManager` (Ed25519)    |
| `key_managers/`       | Cloud key managers (AWS KMS, Azure Key Vault, HashiCorp Vault)       |
| `identity.py`         | OIDC identity verification (Okta, Azure AD, Google)                  |
| `compliance.py`       | SOC2/ISO 27001 evidence mapping and GRC export                       |
| `siem.py`             | CEF/OCSF formatters for Splunk, Sentinel, QRadar                     |
| `shadow.py`           | Shadow mode observer (zero-config AI activity recording)             |
| `dashboard.py`        | Web-based trust status dashboard (stdlib http.server)                |
| `migrate.py`          | Schema migrations (filesystem -> SQLite, version upgrades)           |
| `conformance/`        | Backend conformance test suite                                       |
| `cli.py`              | Click CLI (`attest` command)                                         |
| `mcp_server.py`       | FastMCP server for AI agent integration                              |

## Installation

The base install includes the full trust-plane: SQLite, PostgreSQL, encryption, OIDC/SSO, RBAC, and all core features.

```bash
pip install kailash                      # Everything included
```

Vendor-specific secret backends are optional extras:

```bash
pip install kailash[aws-secrets]         # AWS KMS key management
pip install kailash[azure-secrets]       # Azure Key Vault
pip install kailash[vault]               # HashiCorp Vault Transit
pip install kailash[trust-windows]       # Windows file permissions (pywin32)
```
