# Milestone 4: Version Bump & Configuration

kailash 2.0.0 with trust namespace, dependencies, entry points, and documentation.

## TODO-35: Update kailash pyproject.toml — version and dependencies

Update root `pyproject.toml`:

```toml
[project]
version = "2.0.0"

[project.dependencies]
jsonschema = ">=4.24.0"    # unchanged
networkx = ">=2.7"          # unchanged
pydantic = ">=1.9"          # unchanged (NOT raised — pydantic was phantom dep)
pyyaml = ">=6.0"            # unchanged
filelock = ">=3.0"          # NEW — moved from eatp/trust-plane
```

**Acceptance**: `pip install -e .` installs filelock. Version reads 2.0.0.

---

## TODO-36: Update kailash pyproject.toml — trust optional extra

Add `kailash[trust]` optional extra:

```toml
[project.optional-dependencies]
trust = ["pynacl>=1.5"]
```

**Acceptance**: `pip install -e ".[trust]"` installs pynacl. `from kailash.trust.signing.crypto import generate_keypair` works.

---

## TODO-37: Update kailash pyproject.toml — CLI entry points

Add trust CLI entry points:

```toml
[project.scripts]
kailash = "kailash.cli:main"
eatp = "kailash.trust.cli:main"
attest = "kailash.trust.plane.cli.commands:main"
trustplane-mcp = "kailash.trust.plane.mcp_server:main"
```

**Acceptance**: `eatp --help`, `attest --help`, `trustplane-mcp --help` all work.

---

## TODO-38: Update kailash pyproject.toml — trust-plane extras absorption

Add trust-plane provider extras to existing kailash extras where they don't already exist:

```toml
[project.optional-dependencies]
# Existing extras that may need additions:
postgres = ["asyncpg>=0.29", "psycopg[binary]>=3.0", "psycopg_pool>=3.0"]  # Add psycopg if not present
trust-encryption = ["cryptography>=41.0"]  # NEW
trust-sso = ["PyJWT>=2.8", "cryptography>=41.0"]  # NEW
```

Check existing `aws-secrets`, `azure-secrets`, `vault` extras — verify they already cover trust-plane's boto3, azure-keyvault-keys, hvac requirements.

**Acceptance**: All trust-plane optional features installable via kailash extras.

---

## TODO-39: Update kailash pyproject.toml — pytest markers

Add trust-specific pytest markers:

```toml
[tool.pytest.ini_options]
markers = [
    # ... existing markers
    "trust: Trust subsystem tests",
    "trust_security: Trust security regression tests",
    "trust_benchmark: Trust performance benchmarks",
]
```

**Acceptance**: `pytest -m trust` selects only trust tests.

---

## TODO-40: Update kailash __init__.py version

Update `src/kailash/__init__.py`:
```python
__version__ = "2.0.0"
```

**Acceptance**: `python -c "import kailash; print(kailash.__version__)"` prints `2.0.0`.

---

## TODO-41: Update CHANGELOG.md

Add kailash 2.0.0 entry:

```markdown
## [2.0.0] - 2026-XX-XX

### Added
- `kailash.trust` namespace — EATP protocol implementation merged into core
- `kailash.trust.plane` namespace — Trust-plane platform merged into core
- `kailash[trust]` optional extra for Ed25519 cryptography (pynacl)
- CLI entry points: `eatp`, `attest`, `trustplane-mcp`
- `filelock>=3.0` added to core dependencies

### Changed
- kailash-kaizen 2.0.0 drops standalone `eatp` dependency (uses kailash.trust)
- kailash-dataflow and kailash-nexus accept kailash 2.x

### Deprecated
- `eatp` package — use `from kailash.trust import ...` instead
- `trust-plane` package — use `from kailash.trust.plane import ...` instead
- Both packages continue to work as shims with DeprecationWarning
```

**Acceptance**: CHANGELOG.md has 2.0.0 entry with all sections.

---

## TODO-42: Update CLAUDE.md platform table

Add `kailash.trust` to the platform table in `CLAUDE.md`:

```markdown
| Framework      | Purpose                                | Install                          |
| -------------- | -------------------------------------- | -------------------------------- |
| **Core SDK**   | Workflow orchestration, 140+ nodes     | `pip install kailash`            |
| **Trust**      | EATP protocol + trust-plane governance | `pip install kailash[trust]`     |
| **DataFlow**   | Zero-config database operations        | `pip install kailash-dataflow`   |
| **Nexus**      | Multi-channel deployment (API+CLI+MCP) | `pip install kailash-nexus`      |
| **Kaizen**     | AI agent framework                     | `pip install kailash-kaizen`     |
```

**Acceptance**: CLAUDE.md reflects the new trust framework.

---

## TODO-43: Update .claude/rules/eatp.md scope

Change scope from `packages/eatp/**` to `src/kailash/trust/**` (excluding `plane/`).

**Acceptance**: Rules apply to the new location.

---

## TODO-44: Update .claude/rules/trust-plane-security.md scope

Change scope from `packages/trust-plane/**` to `src/kailash/trust/plane/**` and `src/kailash/trust/_locking.py`.

**Acceptance**: Security rules apply to the new location.

---

## TODO-45: Update .claude/rules/dataflow-pool.md if needed

Check if pool rules reference eatp or trust-plane. Update if necessary.

**Acceptance**: No stale references to old package paths in any rule file.

---

## TODO-46: Scan all .claude/ rules for stale references

Grep all `.claude/` files for references to `packages/eatp`, `packages/trust-plane`, `from eatp`, `from trustplane`. Update all occurrences.

**Acceptance**: Zero stale references in `.claude/` directory.
