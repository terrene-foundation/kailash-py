# Milestone 1: Directory Structure & Code Move

All EATP and trust-plane source files moved into `src/kailash/trust/`. No import rewrites yet.

## TODO-01: Create target directory tree

Create the complete `src/kailash/trust/` directory structure with all subdirectories.

**Directories to create:**
```
src/kailash/trust/
src/kailash/trust/chain_store/
src/kailash/trust/constraints/
src/kailash/trust/enforce/
src/kailash/trust/a2a/
src/kailash/trust/messaging/
src/kailash/trust/interop/
src/kailash/trust/governance/
src/kailash/trust/registry/
src/kailash/trust/orchestration/
src/kailash/trust/orchestration/integration/
src/kailash/trust/esa/
src/kailash/trust/knowledge/
src/kailash/trust/export/
src/kailash/trust/signing/
src/kailash/trust/posture/
src/kailash/trust/reasoning/
src/kailash/trust/agents/
src/kailash/trust/revocation/
src/kailash/trust/mcp/
src/kailash/trust/cli/
src/kailash/trust/migrations/
src/kailash/trust/templates/
src/kailash/trust/plane/
src/kailash/trust/plane/store/
src/kailash/trust/plane/key_managers/
src/kailash/trust/plane/conformance/
src/kailash/trust/plane/integration/
src/kailash/trust/plane/integration/cursor/
src/kailash/trust/plane/integration/claude_code/
src/kailash/trust/plane/encryption/
src/kailash/trust/plane/templates/
src/kailash/trust/plane/dashboard_templates/
src/kailash/trust/plane/cli/
```

**Acceptance**: All directories exist. Each has a placeholder `__init__.py`.

---

## TODO-02: Move EATP root modules

Copy EATP root-level Python files from `packages/eatp/src/eatp/` to `src/kailash/trust/`.

**Direct moves** (same filename):
- `chain.py`, `authority.py`, `exceptions.py`, `hooks.py`, `roles.py`, `vocabulary.py`
- `scoring.py`, `key_manager.py`, `constraint_validator.py`, `execution_context.py`
- `multi_sig.py` → NO (goes to `signing/`)
- `security.py`, `audit_service.py`, `audit_store.py`, `graph_validator.py`
- `circuit_breaker.py`, `metrics.py`, `cache.py`
- `trusted_agent.py` → NO (goes to `agents/`)
- `pseudo_agent.py` → NO (goes to `agents/`)
- `postures.py` → NO (goes to `posture/`)
- `posture_store.py` → NO (goes to `posture/`)
- `posture_agent.py` → NO (goes to `agents/`)
- `reasoning.py` → NO (goes to `reasoning/`)
- `crypto.py` → NO (goes to `signing/`)

**Renamed moves** (see TODO-03, TODO-04, TODO-05):
Handled in subsequent todos.

**Acceptance**: All direct-move root modules exist at `src/kailash/trust/`. File content identical to source.

---

## TODO-03: Move EATP modules with renames (signing/)

Move crypto-related modules into `src/kailash/trust/signing/`:

| Source | Target |
|--------|--------|
| `eatp/crypto.py` | `trust/signing/crypto.py` |
| `eatp/multi_sig.py` | `trust/signing/multi_sig.py` |
| `eatp/merkle.py` | `trust/signing/merkle.py` |
| `eatp/timestamping.py` | `trust/signing/timestamping.py` |
| `eatp/rotation.py` | `trust/signing/rotation.py` |
| `eatp/crl.py` | `trust/signing/crl.py` |

Create `signing/__init__.py` that re-exports the most-used symbols: `generate_keypair`, `sign`, `verify_signature`, `dual_sign`, `dual_verify`, `DualSignature`.

**Acceptance**: All 6 files in `signing/`. `__init__.py` re-exports work.

---

## TODO-04: Move EATP modules with renames (posture/, reasoning/, agents/)

| Source | Target |
|--------|--------|
| `eatp/postures.py` | `trust/posture/postures.py` |
| `eatp/posture_store.py` | `trust/posture/posture_store.py` |
| `eatp/posture_agent.py` | `trust/agents/posture_agent.py` |
| `eatp/reasoning.py` | `trust/reasoning/traces.py` |
| `eatp/trusted_agent.py` | `trust/agents/trusted_agent.py` |
| `eatp/pseudo_agent.py` | `trust/agents/pseudo_agent.py` |

Create `__init__.py` files for each subpackage with appropriate re-exports:
- `posture/__init__.py`: TrustPosture, PostureStateMachine, PostureEvidence
- `reasoning/__init__.py`: ReasoningTrace, ConfidentialityLevel, EvidenceReference
- `agents/__init__.py`: TrustedAgent, PseudoAgent, PostureAwareAgent

**Acceptance**: All files moved. `__init__.py` re-exports verified.

---

## TODO-05: Move EATP subpackages (direct)

Copy these EATP subpackages directly (same internal structure):

- `eatp/operations/` → `trust/operations/`
- `eatp/constraints/` → `trust/constraints/`
- `eatp/enforce/` → `trust/enforce/`
- `eatp/a2a/` → `trust/a2a/`
- `eatp/messaging/` → `trust/messaging/`
- `eatp/interop/` → `trust/interop/`
- `eatp/governance/` → `trust/governance/`
- `eatp/registry/` → `trust/registry/`
- `eatp/revocation/` → `trust/revocation/` (broadcaster.py, cascade.py)
- `eatp/orchestration/` → `trust/orchestration/` (including `integration/` subdirectory)
- `eatp/esa/` → `trust/esa/`
- `eatp/knowledge/` → `trust/knowledge/`
- `eatp/export/` → `trust/export/`
- `eatp/mcp/` → `trust/mcp/`
- `eatp/cli/` → `trust/cli/`
- `eatp/migrations/` → `trust/migrations/`
- `eatp/templates/` → `trust/templates/`

**Acceptance**: File count matches source. `diff -rq` shows no content differences.

---

## TODO-06: Move EATP store/ → trust/chain_store/

Copy `packages/eatp/src/eatp/store/` to `src/kailash/trust/chain_store/`:

| Source | Target |
|--------|--------|
| `store/__init__.py` | `chain_store/__init__.py` |
| `store/memory.py` | `chain_store/memory.py` |
| `store/filesystem.py` | `chain_store/filesystem.py` |
| `store/sqlite.py` | `chain_store/sqlite.py` |

**Acceptance**: 4 files in `chain_store/`. TrustStore ABC, InMemoryTrustStore, FilesystemStore, SqliteTrustStore all present.

---

## TODO-07: Move _locking.py to trust root (shared)

Per reconciliation H-03, `_locking.py` moves to `src/kailash/trust/_locking.py` (not inside `plane/`). Both protocol and plane layers can import from it.

Copy from `packages/trust-plane/src/trustplane/_locking.py` to `src/kailash/trust/_locking.py`.

Also copy `packages/trust-plane/src/trustplane/pathutils.py` to `src/kailash/trust/pathutils.py` (shared utility).

**Acceptance**: Both files at trust root level. Content identical to source.

---

## TODO-08: Move trust-plane root modules

Copy trust-plane root modules from `packages/trust-plane/src/trustplane/` to `src/kailash/trust/plane/`:

**Direct moves:**
- `project.py`, `models.py`, `exceptions.py`, `compliance.py`, `config.py`
- `session.py`, `delegation.py`, `holds.py`, `shadow.py`, `shadow_store.py`
- `dashboard.py`, `siem.py`, `identity.py`, `rbac.py`, `archive.py`, `bundle.py`
- `mirror.py`, `diagnostics.py`, `proxy.py`, `reports.py`, `migrate.py`, `mcp_server.py`

**Renamed moves:**
- `crypto_utils.py` → `plane/encryption/crypto_utils.py`
- `key_manager.py` → `plane/key_managers/manager.py`
- `cli.py` → `plane/cli/commands.py`

**Acceptance**: All modules present under `plane/`. File content matches source.

---

## TODO-09: Move trust-plane subpackages

Copy trust-plane subpackages:

- `trustplane/store/` → `trust/plane/store/` (3 backends + protocol)
- `trustplane/key_managers/` → `trust/plane/key_managers/` (aws, azure, vault)
- `trustplane/conformance/` → `trust/plane/conformance/`
- `trustplane/integration/` → `trust/plane/integration/` (cursor/, claude_code/)
- `trustplane/templates/` → `trust/plane/templates/`
- `trustplane/dashboard_templates/` → `trust/plane/dashboard_templates/`

**Acceptance**: All subpackages present. File count matches source.

---

## TODO-10: Create kailash.trust.__init__.py (public API surface)

Write the top-level `src/kailash/trust/__init__.py` that re-exports the most-used types from both layers. Use lazy imports for pynacl-dependent types.

**Must export:**
- Protocol essentials: `TrustOperations`, `TrustKeyManager`, `CapabilityRequest`
- Chain types: `GenesisRecord`, `DelegationRecord`, `TrustLineageChain`, `VerificationResult`
- Signing (lazy): `generate_keypair`, `sign`, `verify_signature`
- Platform essentials: `TrustProject`, `DecisionRecord`, `DecisionType`
- Exceptions: `TrustError`, `TrustPlaneError`

**Must NOT import pynacl at module level.**

**Acceptance**: `python -c "from kailash.trust import GenesisRecord"` works without pynacl installed.

---

## TODO-11: Create kailash.trust.plane.__init__.py (plane API surface)

Write `src/kailash/trust/plane/__init__.py` re-exporting trust-plane's public API:
- `TrustProject`, `TrustPlaneStore`, `SqliteTrustPlaneStore`, `FileSystemTrustPlaneStore`
- `DecisionRecord`, `DecisionType`, `MilestoneRecord`, `ConstraintEnvelope`
- All 5 constraint classes
- Key exception classes

**Acceptance**: All trust-plane public names importable from `kailash.trust.plane`.

---

## TODO-12: Verify file counts

Run verification:
- Count Python files in `src/kailash/trust/` — expect ~105
- Compare against source packages
- Ensure no files were missed

**Acceptance**: File count verified. No modules missing.
