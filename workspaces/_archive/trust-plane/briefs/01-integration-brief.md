# TrustPlane Integration Brief — kailash-py Monorepo

## What This Is

TrustPlane is the EATP reference implementation — a trust environment through which AI-assisted work happens. It has been copied from `terrene/packages/trust-plane/` into this monorepo as `packages/trust-plane/`.

**Status**: Production-ready. 431 tests passing. 12 rounds of red teaming — converged at zero findings (R12).

## What Needs to Happen

### 1. Monorepo Integration

TrustPlane depends on `eatp>=0.1.0` which lives at `packages/eatp/` in this same monorepo. The integration work:

- **pyproject.toml**: Update `trust-plane`'s dependency from `eatp>=0.1.0` (PyPI) to a path dependency pointing to `../eatp/` for development, while keeping the PyPI dependency for published releases
- **CI**: Add trust-plane to the monorepo CI pipeline (pytest, linting)
- **Imports**: Verify all `from eatp.*` imports resolve against the local EATP SDK package
- **Entry points**: Verify `attest` CLI and `trustplane-mcp` MCP server entry points work in monorepo context
- **Test isolation**: Ensure trust-plane tests run independently and don't interfere with other package tests

### 2. Cross-Package Testing

TrustPlane uses these EATP SDK modules extensively:
- `eatp.chain` — AuditAnchor, ActionResult, ChainVerifier
- `eatp.crypto` — generate_keypair, sign, verify
- `eatp.enforce.strict` — StrictEnforcer, Verdict
- `eatp.enforce.shadow` — ShadowEnforcer
- `eatp.store.filesystem` — FilesystemStore
- `eatp.reasoning` — ReasoningTrace, ConfidentialityLevel
- `eatp.posture` — PostureStateMachine, TrustPosture

Run trust-plane tests against the local EATP SDK (not a published version) to catch any API drift.

### 3. Shared Dependency Alignment

Check for version conflicts between trust-plane and other packages:
- `mcp>=1.0.0` — used by trust-plane's MCP server
- `click` — used by trust-plane's CLI
- Both may also be used by kailash-nexus or kailash-kaizen

## What NOT to Change

The trust-plane code is hardened through 12 rounds of red teaming. Do NOT:

- Replace `safe_read_json()` or O_NOFOLLOW patterns with bare `open()` calls
- Remove `math.isfinite()` validation from constraint fields
- Remove `_filter_arguments()` from the proxy
- Change `atomic_write()` fd ownership pattern (`fd = -1` inside `with os.fdopen()`)
- Remove `_MAX_SNAPSHOT_FILES` cap from session snapshots
- Use `deque` without `maxlen` for the proxy call log

If you need to modify security patterns, run `/redteam` first.

## Package Structure

```
packages/trust-plane/
├── pyproject.toml          # Package config (hatchling build, Apache-2.0)
├── README.md               # Package documentation
├── src/trustplane/         # Source code
│   ├── __init__.py
│   ├── _locking.py         # File locking, atomic writes, safe reads, ID validation
│   ├── models.py           # Data models (ConstraintEnvelope, DecisionRecord, etc.)
│   ├── project.py          # TrustProject — main class
│   ├── cli.py              # Click CLI (`attest` command)
│   ├── mcp_server.py       # MCP server (5 trust tools)
│   ├── proxy.py            # MCP proxy (Tier 3 transport enforcement)
│   ├── delegation.py       # Multi-stakeholder delegation with cascade revocation
│   ├── holds.py            # Hold/approve workflow
│   ├── session.py          # Session tracking with file snapshots
│   ├── mirror.py           # CARE Mirror Thesis records
│   ├── bundle.py           # VerificationBundle export (JSON/HTML)
│   ├── reports.py          # Audit report generation
│   ├── diagnostics.py      # Constraint quality scoring
│   ├── migrate.py          # Migration utilities
│   ├── templates/          # Pre-built constraint envelope templates
│   ├── conformance/        # EATP conformance test suite
│   └── integration/        # Integration modules (Claude Code)
└── tests/                  # 431 tests across 21 files
```

## Security Patterns (MUST preserve)

| Pattern | Location | Purpose |
|---------|----------|---------|
| `safe_read_json()` | `_locking.py` | O_NOFOLLOW atomic JSON read |
| `_safe_read_text()` | `_locking.py` | O_NOFOLLOW text read |
| `atomic_write()` | `_locking.py` | temp+fsync+rename for crash safety |
| `_safe_write_text()` | `_locking.py` | O_NOFOLLOW text write via atomic pattern |
| `validate_id()` | `_locking.py` | Path traversal prevention |
| `_safe_hash_file()` | `project.py` | O_NOFOLLOW binary file hashing |
| `_filter_arguments()` | `proxy.py` | Argument injection prevention |
| `math.isfinite()` | `models.py` | NaN/Inf constraint bypass prevention |
| `deque(maxlen=)` | `proxy.py` | Bounded call log |
| `_MAX_SNAPSHOT_FILES` | `session.py` | Bounded file traversal |
| mtime cache invalidation | `mcp_server.py` | Stale constraint prevention |

## Red Team History

12 rounds completed. Reports in `workspaces/trust-plane/04-validate/`:

| Round | Focus | Key Fixes |
|-------|-------|-----------|
| R3 | Initial hardening | Constraint tightening rewrite, path traversal prevention |
| R4 | Concurrency | deque BFS, WAL recovery, lock timeout |
| R5 | Accepted risk elimination | All 7 previously-accepted risks closed |
| R7 | Symlink protection | O_NOFOLLOW, ELOOP handling, WAL content hash |
| R8 | Bare open() elimination | All file operations hardened across all modules |
| R9 | Residual gaps | Public key protection, CLI output writes, dead code |
| R10 | Deep hardening | Input validation, proxy security, MCP cache, NaN |
| R11 | Convergence | NaN bypass, double-close fd, dead imports |
| R12 | CONVERGED | Zero findings from both deep-analyst and security-reviewer |

## Entry Points

- **CLI**: `attest` → `trustplane.cli:main` (Click)
- **MCP Server**: `trustplane-mcp` → `trustplane.mcp_server:main` (FastMCP)
- **Python API**: `from trustplane.project import TrustProject`

## Next Steps After Integration

1. Run `python -m pytest packages/trust-plane/tests/ -x -q` from monorepo root
2. Verify EATP imports resolve against local `packages/eatp/`
3. Add trust-plane to monorepo CI
4. Consider cross-package integration tests (trust-plane + eatp together)
