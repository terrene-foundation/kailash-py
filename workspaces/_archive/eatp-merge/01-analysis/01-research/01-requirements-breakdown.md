# EATP + Trust-Plane Merge: Requirements Breakdown

**Date**: 2026-03-21
**Decision**: D001 (approved)
**Source Brief**: `briefs/01-eatp-merge-brief.md`

---

## 1. Namespace Mapping

### 1.1 EATP Package (`packages/eatp/src/eatp/`) -> `src/kailash/trust/`

The EATP package contains 116 modules organized into a root-level set and 14 subpackages. Every module moves into `kailash.trust.*`, preserving the internal subpackage structure under a new root.

#### Root Modules (28 files)

| Source (`eatp.*`)         | Target (`kailash.trust.*`) | Purpose                                                                            |
| ------------------------- | -------------------------- | ---------------------------------------------------------------------------------- |
| `__init__.py`             | `__init__.py`              | Public API surface (all re-exports)                                                |
| `chain.py`                | `chain.py`                 | Core types: GenesisRecord, DelegationRecord, TrustLineageChain, VerificationResult |
| `crypto.py`               | `crypto.py`                | Ed25519 signing, dual signatures, HMAC                                             |
| `authority.py`            | `authority.py`             | OrganizationalAuthority, AuthorityPermission                                       |
| `postures.py`             | `postures.py`              | TrustPosture, PostureStateMachine, PostureEvidence                                 |
| `reasoning.py`            | `reasoning.py`             | ReasoningTrace, ConfidentialityLevel, EvidenceReference                            |
| `exceptions.py`           | `exceptions.py`            | TrustError hierarchy (14 exception classes)                                        |
| `hooks.py`                | `hooks.py`                 | EATPHook, HookRegistry, HookContext                                                |
| `roles.py`                | `roles.py`                 | TrustRole, ROLE_PERMISSIONS, check_permission                                      |
| `vocabulary.py`           | `vocabulary.py`            | CONSTRAINT_VOCABULARY, POSTURE_VOCABULARY                                          |
| `scoring.py`              | `scoring.py`               | Behavioral trust scoring                                                           |
| `key_manager.py`          | `key_manager.py`           | AWSKMSKeyManager, InMemoryKeyManager                                               |
| `constraint_validator.py` | `constraint_validator.py`  | ConstraintValidator, DelegationConstraintValidator                                 |
| `execution_context.py`    | `execution_context.py`     | ExecutionContext, HumanOrigin                                                      |
| `multi_sig.py`            | `multi_sig.py`             | MultiSigPolicy, MultiSigManager                                                    |
| `merkle.py`               | `merkle.py`                | MerkleTree, MerkleProof, verify_merkle_proof                                       |
| `circuit_breaker.py`      | `circuit_breaker.py`       | PostureCircuitBreaker, CircuitState                                                |
| `metrics.py`              | `metrics.py`               | TrustMetricsCollector, PostureMetrics                                              |
| `cache.py`                | `cache.py`                 | TrustChainCache, CacheStats                                                        |
| `rotation.py`             | `rotation.py`              | CredentialRotationManager                                                          |
| `security.py`             | `security.py`              | TrustSecurityValidator, SecureKeyStorage, TrustRateLimiter                         |
| `audit_service.py`        | `audit_service.py`         | AuditQueryService, ComplianceReport                                                |
| `audit_store.py`          | `audit_store.py`           | AppendOnlyAuditStore, PostgresAuditStore                                           |
| `graph_validator.py`      | `graph_validator.py`       | Delegation graph cycle detection                                                   |
| `crl.py`                  | `crl.py`                   | CertificateRevocationList, CRLEntry                                                |
| `timestamping.py`         | `timestamping.py`          | TimestampAnchorManager, RFC3161TimestampAuthority                                  |
| `trusted_agent.py`        | `trusted_agent.py`         | TrustedAgent, TrustedSupervisorAgent                                               |
| `pseudo_agent.py`         | `pseudo_agent.py`          | PseudoAgent, PseudoAgentFactory                                                    |
| `posture_agent.py`        | `posture_agent.py`         | PostureAwareAgent                                                                  |
| `posture_store.py`        | `posture_store.py`         | SQLitePostureStore                                                                 |

#### Subpackage: `eatp.operations` -> `kailash.trust.operations`

| Source                   | Target                   | Purpose                                             |
| ------------------------ | ------------------------ | --------------------------------------------------- |
| `operations/__init__.py` | `operations/__init__.py` | TrustOperations, TrustKeyManager, CapabilityRequest |

#### Subpackage: `eatp.store` -> `kailash.trust.eatp_store`

**Note**: EATP stores and trust-plane stores are DIFFERENT abstractions. EATP stores persist `TrustLineageChain` objects. Trust-plane stores persist project records (decisions, milestones, holds). They MUST NOT be merged into a single `store/` directory.

| Source                | Target                     | Purpose                                 |
| --------------------- | -------------------------- | --------------------------------------- |
| `store/__init__.py`   | `eatp_store/__init__.py`   | TrustStore ABC, TransactionContext      |
| `store/memory.py`     | `eatp_store/memory.py`     | InMemoryTrustStore                      |
| `store/filesystem.py` | `eatp_store/filesystem.py` | FilesystemStore, validate_id, file_lock |
| `store/sqlite.py`     | `eatp_store/sqlite.py`     | SqliteTrustStore                        |

#### Subpackage: `eatp.constraints` -> `kailash.trust.constraints`

| Source                          | Target                          | Purpose                       |
| ------------------------------- | ------------------------------- | ----------------------------- |
| `constraints/__init__.py`       | `constraints/__init__.py`       | Package init                  |
| `constraints/builtin.py`        | `constraints/builtin.py`        | Built-in constraint types     |
| `constraints/commerce.py`       | `constraints/commerce.py`       | Commerce constraints          |
| `constraints/dimension.py`      | `constraints/dimension.py`      | 5 constraint dimensions       |
| `constraints/evaluator.py`      | `constraints/evaluator.py`      | ConstraintEvaluator           |
| `constraints/spend_tracker.py`  | `constraints/spend_tracker.py`  | SpendTracker                  |
| `constraints/budget_tracker.py` | `constraints/budget_tracker.py` | BudgetTracker, BudgetSnapshot |
| `constraints/budget_store.py`   | `constraints/budget_store.py`   | SQLiteBudgetStore             |

#### Subpackage: `eatp.enforce` -> `kailash.trust.enforce`

| Source                            | Target                            | Purpose                        |
| --------------------------------- | --------------------------------- | ------------------------------ |
| `enforce/__init__.py`             | `enforce/__init__.py`             | Package init                   |
| `enforce/challenge.py`            | `enforce/challenge.py`            | Challenge-response enforcement |
| `enforce/decorators.py`           | `enforce/decorators.py`           | Enforcement decorators         |
| `enforce/proximity.py`            | `enforce/proximity.py`            | Proximity scanner              |
| `enforce/selective_disclosure.py` | `enforce/selective_disclosure.py` | SD-JWT selective disclosure    |
| `enforce/shadow.py`               | `enforce/shadow.py`               | Shadow enforcement mode        |
| `enforce/strict.py`               | `enforce/strict.py`               | Strict enforcement mode        |

#### Subpackage: `eatp.a2a` -> `kailash.trust.a2a`

| Source              | Target              | Purpose                       |
| ------------------- | ------------------- | ----------------------------- |
| `a2a/__init__.py`   | `a2a/__init__.py`   | Package init                  |
| `a2a/agent_card.py` | `a2a/agent_card.py` | AgentCard, AgentCardGenerator |
| `a2a/auth.py`       | `a2a/auth.py`       | A2A authentication            |
| `a2a/exceptions.py` | `a2a/exceptions.py` | A2A exception hierarchy       |
| `a2a/jsonrpc.py`    | `a2a/jsonrpc.py`    | JSON-RPC handler              |
| `a2a/models.py`     | `a2a/models.py`     | Request/response models       |
| `a2a/service.py`    | `a2a/service.py`    | A2AService                    |

#### Subpackage: `eatp.esa` -> `kailash.trust.esa`

| Source              | Target              | Purpose                       |
| ------------------- | ------------------- | ----------------------------- |
| `esa/__init__.py`   | `esa/__init__.py`   | EnterpriseSystemAgent exports |
| `esa/api.py`        | `esa/api.py`        | ESA API integration           |
| `esa/base.py`       | `esa/base.py`       | Base ESA class                |
| `esa/database.py`   | `esa/database.py`   | ESA database integration      |
| `esa/discovery.py`  | `esa/discovery.py`  | ESA discovery protocol        |
| `esa/exceptions.py` | `esa/exceptions.py` | ESA exception hierarchy       |
| `esa/registry.py`   | `esa/registry.py`   | ESA registry                  |

#### Subpackage: `eatp.governance` -> `kailash.trust.governance`

| Source                         | Target                         | Purpose                  |
| ------------------------------ | ------------------------------ | ------------------------ |
| `governance/__init__.py`       | `governance/__init__.py`       | Package init             |
| `governance/models.py`         | `governance/models.py`         | Governance data models   |
| `governance/policy_models.py`  | `governance/policy_models.py`  | Policy model definitions |
| `governance/cost_estimator.py` | `governance/cost_estimator.py` | Action cost estimation   |
| `governance/policy_engine.py`  | `governance/policy_engine.py`  | Policy evaluation engine |
| `governance/rate_limiter.py`   | `governance/rate_limiter.py`   | Rate limiting            |

#### Subpackage: `eatp.registry` -> `kailash.trust.registry`

| Source                       | Target                       | Purpose                                        |
| ---------------------------- | ---------------------------- | ---------------------------------------------- |
| `registry/__init__.py`       | `registry/__init__.py`       | Package init                                   |
| `registry/exceptions.py`     | `registry/exceptions.py`     | Registry exceptions                            |
| `registry/agent_registry.py` | `registry/agent_registry.py` | AgentRegistry                                  |
| `registry/health.py`         | `registry/health.py`         | AgentHealthMonitor                             |
| `registry/models.py`         | `registry/models.py`         | AgentMetadata, RegistrationRequest             |
| `registry/store.py`          | `registry/store.py`          | AgentRegistryStore, PostgresAgentRegistryStore |

#### Subpackage: `eatp.revocation` -> `kailash.trust.revocation`

| Source                      | Target                      | Purpose                                              |
| --------------------------- | --------------------------- | ---------------------------------------------------- |
| `revocation/__init__.py`    | `revocation/__init__.py`    | Package init                                         |
| `revocation/broadcaster.py` | `revocation/broadcaster.py` | RevocationBroadcaster, InMemoryRevocationBroadcaster |
| `revocation/cascade.py`     | `revocation/cascade.py`     | CascadeRevocationManager                             |

#### Subpackage: `eatp.messaging` -> `kailash.trust.messaging`

| Source                           | Target                           | Purpose                  |
| -------------------------------- | -------------------------------- | ------------------------ |
| `messaging/__init__.py`          | `messaging/__init__.py`          | Package init             |
| `messaging/envelope.py`          | `messaging/envelope.py`          | SecureMessageEnvelope    |
| `messaging/channel.py`           | `messaging/channel.py`           | SecureChannel            |
| `messaging/exceptions.py`        | `messaging/exceptions.py`        | Messaging exceptions     |
| `messaging/replay_protection.py` | `messaging/replay_protection.py` | InMemoryReplayProtection |
| `messaging/signer.py`            | `messaging/signer.py`            | MessageSigner            |
| `messaging/verifier.py`          | `messaging/verifier.py`          | MessageVerifier          |

#### Subpackage: `eatp.knowledge` -> `kailash.trust.knowledge`

| Source                    | Target                    | Purpose                           |
| ------------------------- | ------------------------- | --------------------------------- |
| `knowledge/__init__.py`   | `knowledge/__init__.py`   | Package init                      |
| `knowledge/bridge.py`     | `knowledge/bridge.py`     | TrustKnowledgeBridge              |
| `knowledge/entry.py`      | `knowledge/entry.py`      | KnowledgeEntry                    |
| `knowledge/provenance.py` | `knowledge/provenance.py` | ProvenanceRecord, ProvenanceChain |

#### Subpackage: `eatp.interop` -> `kailash.trust.interop`

| Source                | Target                | Purpose                     |
| --------------------- | --------------------- | --------------------------- |
| `interop/__init__.py` | `interop/__init__.py` | Package init                |
| `interop/biscuit.py`  | `interop/biscuit.py`  | Biscuit token interop       |
| `interop/did.py`      | `interop/did.py`      | DID resolution              |
| `interop/jwt.py`      | `interop/jwt.py`      | JWT interop                 |
| `interop/sd_jwt.py`   | `interop/sd_jwt.py`   | SD-JWT selective disclosure |
| `interop/ucan.py`     | `interop/ucan.py`     | UCAN delegation             |
| `interop/w3c_vc.py`   | `interop/w3c_vc.py`   | W3C Verifiable Credentials  |

#### Subpackage: `eatp.orchestration` -> `kailash.trust.orchestration`

| Source                                        | Target                                        | Purpose                        |
| --------------------------------------------- | --------------------------------------------- | ------------------------------ |
| `orchestration/__init__.py`                   | `orchestration/__init__.py`                   | Package init                   |
| `orchestration/exceptions.py`                 | `orchestration/exceptions.py`                 | Orchestration exceptions       |
| `orchestration/execution_context.py`          | `orchestration/execution_context.py`          | TrustExecutionContext          |
| `orchestration/policy.py`                     | `orchestration/policy.py`                     | TrustPolicy, TrustPolicyEngine |
| `orchestration/runtime.py`                    | `orchestration/runtime.py`                    | TrustAwareOrchestrationRuntime |
| `orchestration/integration/__init__.py`       | `orchestration/integration/__init__.py`       | Package init                   |
| `orchestration/integration/registry_aware.py` | `orchestration/integration/registry_aware.py` | Registry-aware orchestration   |
| `orchestration/integration/secure_channel.py` | `orchestration/integration/secure_channel.py` | Secure channel integration     |

#### Remaining: `eatp.cli`, `eatp.mcp`, `eatp.export`, `eatp.migrations`, `eatp.templates`

| Source                            | Target                            | Purpose                       |
| --------------------------------- | --------------------------------- | ----------------------------- |
| `cli/__init__.py`                 | `cli/__init__.py`                 | Package init                  |
| `cli/commands.py`                 | `cli/commands.py`                 | CLI command implementations   |
| `cli/quickstart.py`               | `cli/quickstart.py`               | Interactive quickstart wizard |
| `mcp/__init__.py`                 | `mcp/__init__.py`                 | Package init                  |
| `mcp/server.py`                   | `mcp/server.py`                   | EATP MCP server               |
| `export/__init__.py`              | `export/__init__.py`              | Package init                  |
| `export/compliance.py`            | `export/compliance.py`            | Compliance export             |
| `export/siem.py`                  | `export/siem.py`                  | SIEM export                   |
| `migrations/__init__.py`          | `migrations/__init__.py`          | Package init                  |
| `migrations/eatp_human_origin.py` | `migrations/eatp_human_origin.py` | Human origin migration        |
| `templates/__init__.py`           | `templates/__init__.py`           | Constraint templates          |

### 1.2 Trust-Plane Package (`packages/trust-plane/src/trustplane/`) -> `src/kailash/trust/plane/`

Trust-plane is a higher-level application built on top of EATP. It moves into `kailash.trust.plane/` to preserve the layering: EATP is the protocol layer, trust-plane is the application layer.

#### Root Modules

| Source (`trustplane.*`) | Target (`kailash.trust.plane.*`) | Purpose                                                            |
| ----------------------- | -------------------------------- | ------------------------------------------------------------------ |
| `__init__.py`           | `__init__.py`                    | Public API surface                                                 |
| `project.py`            | `project.py`                     | TrustProject (1929 LOC -- the main orchestrator)                   |
| `cli.py`                | `cli.py`                         | `attest` CLI (2282 LOC, Click-based)                               |
| `models.py`             | `models.py`                      | DecisionRecord, MilestoneRecord, ConstraintEnvelope (5 dimensions) |
| `exceptions.py`         | `exceptions.py`                  | TrustPlaneError hierarchy (22 exception classes)                   |
| `compliance.py`         | `compliance.py`                  | Compliance reporting (1314 LOC)                                    |
| `config.py`             | `config.py`                      | TrustPlaneConfig (.trustplane.toml)                                |
| `session.py`            | `session.py`                     | Session management                                                 |
| `delegation.py`         | `delegation.py`                  | Delegate, ReviewResolution                                         |
| `holds.py`              | `holds.py`                       | HoldRecord                                                         |
| `_locking.py`           | `_locking.py`                    | validate_id, safe_read_json, safe_open, atomic_write               |
| `crypto_utils.py`       | `crypto_utils.py`                | Encryption utilities                                               |
| `key_manager.py`        | `key_manager.py`                 | Abstract key manager interface                                     |
| `pathutils.py`          | `pathutils.py`                   | normalize_resource_path                                            |
| `shadow.py`             | `shadow.py`                      | Shadow mode enforcement                                            |
| `shadow_store.py`       | `shadow_store.py`                | Shadow observation store                                           |
| `dashboard.py`          | `dashboard.py`                   | Web dashboard with bearer token auth                               |
| `siem.py`               | `siem.py`                        | CEF/OCSF SIEM integration                                          |
| `identity.py`           | `identity.py`                    | OIDC/JWT identity verification                                     |
| `rbac.py`               | `rbac.py`                        | Role-based access control                                          |
| `archive.py`            | `archive.py`                     | Record archival to ZIP bundles                                     |
| `bundle.py`             | `bundle.py`                      | Archive bundle management                                          |
| `mirror.py`             | `mirror.py`                      | Mirror Thesis competency map                                       |
| `diagnostics.py`        | `diagnostics.py`                 | Constraint quality analysis                                        |
| `proxy.py`              | `proxy.py`                       | Trust proxy                                                        |
| `reports.py`            | `reports.py`                     | Report generation                                                  |
| `migrate.py`            | `migrate.py`                     | Store migration utilities                                          |
| `mcp_server.py`         | `mcp_server.py`                  | FastMCP trust-plane server                                         |

#### Store Subpackage

| Source                | Target                | Purpose                   |
| --------------------- | --------------------- | ------------------------- |
| `store/__init__.py`   | `store/__init__.py`   | TrustPlaneStore protocol  |
| `store/filesystem.py` | `store/filesystem.py` | FileSystemTrustPlaneStore |
| `store/sqlite.py`     | `store/sqlite.py`     | SqliteTrustPlaneStore     |
| `store/postgres.py`   | `store/postgres.py`   | PostgresTrustPlaneStore   |

#### Enterprise Key Managers

| Source                           | Target                           | Purpose                       |
| -------------------------------- | -------------------------------- | ----------------------------- |
| `key_managers/__init__.py`       | `key_managers/__init__.py`       | Package init                  |
| `key_managers/aws_kms.py`        | `key_managers/aws_kms.py`        | AWS KMS (ECDSA P-256)         |
| `key_managers/azure_keyvault.py` | `key_managers/azure_keyvault.py` | Azure Key Vault (ECDSA P-256) |
| `key_managers/vault.py`          | `key_managers/vault.py`          | HashiCorp Vault (Transit)     |

#### Integration Subpackage

| Source                                | Target                                | Purpose                    |
| ------------------------------------- | ------------------------------------- | -------------------------- |
| `integration/__init__.py`             | `integration/__init__.py`             | Package init               |
| `integration/cursor/__init__.py`      | `integration/cursor/__init__.py`      | Cursor IDE integration     |
| `integration/cursor/hook.py`          | `integration/cursor/hook.py`          | Cursor hook implementation |
| `integration/claude_code/__init__.py` | `integration/claude_code/__init__.py` | Claude Code integration    |

#### Other

| Source                            | Target                            | Purpose                                                          |
| --------------------------------- | --------------------------------- | ---------------------------------------------------------------- |
| `templates/__init__.py`           | `templates/__init__.py`           | Trust-plane constraint templates (different from EATP templates) |
| `conformance/__init__.py`         | `conformance/__init__.py`         | Store conformance testing                                        |
| `dashboard_templates/__init__.py` | `dashboard_templates/__init__.py` | Dashboard HTML templates                                         |

### 1.3 Naming Decision: EATP Stores vs Trust-Plane Stores

These are fundamentally different abstractions and MUST remain separate:

| Store Type           | ABC / Protocol               | Records Stored                                   | Current Location   | Target Location             |
| -------------------- | ---------------------------- | ------------------------------------------------ | ------------------ | --------------------------- |
| **EATP TrustStore**  | `TrustStore` (ABC)           | `TrustLineageChain` objects                      | `eatp.store`       | `kailash.trust.eatp_store`  |
| **TrustPlane Store** | `TrustPlaneStore` (Protocol) | Decisions, milestones, holds, delegates, anchors | `trustplane.store` | `kailash.trust.plane.store` |

The name `kailash.trust.eatp_store` avoids collision with `kailash.trust.plane.store`. An alternative is `kailash.trust.chain_store` (since it stores trust chains).

---

## 2. Dependency Changes

### 2.1 Dependencies Moving into Kailash Core

| Dependency         | Current Owner      | Action                                         | Rationale                                                 |
| ------------------ | ------------------ | ---------------------------------------------- | --------------------------------------------------------- |
| `pynacl>=1.5`      | eatp               | Move to `kailash[trust]` optional extra        | Ed25519 crypto -- not needed for basic workflow execution |
| `pydantic>=2.6`    | eatp               | Already in kailash core (`pydantic>=1.9`)      | Version floor needs raising from 1.9 to 2.6               |
| `jsonschema>=4.21` | eatp               | Already in kailash core (`jsonschema>=4.24.0`) | Already satisfied                                         |
| `click>=8.0`       | eatp + trust-plane | Already in kailash `[cli]` optional extra      | Already satisfied                                         |
| `filelock>=3.0`    | eatp + trust-plane | Move to `kailash[trust]` optional extra        | Only needed for trust store locking                       |
| `mcp>=1.0.0`       | trust-plane        | Already in kailash `[mcp]` optional extra      | Already satisfied                                         |

### 2.2 New `kailash[trust]` Optional Extra

```toml
[project.optional-dependencies]
trust = [
    "pynacl>=1.5",
    "filelock>=3.0",
]
```

The `kailash[trust]` extra enables the core trust primitives (crypto, stores). Without it, `import kailash.trust` works for types/models but `generate_keypair()` and filesystem stores raise `ImportError` with clear install instructions.

### 2.3 Trust-Plane Specific Extras (absorbed into existing kailash extras)

| trust-plane Extra | kailash Extra (existing)          | Dependencies                                   |
| ----------------- | --------------------------------- | ---------------------------------------------- |
| `postgres`        | `kailash[postgres]` (exists)      | psycopg[binary]>=3.0, psycopg_pool>=3.0        |
| `aws`             | `kailash[aws-secrets]` (exists)   | boto3>=1.26 (already >=1.34)                   |
| `azure`           | `kailash[azure-secrets]` (exists) | azure-keyvault-keys>=4.8, azure-identity>=1.12 |
| `vault`           | `kailash[vault]` (exists)         | hvac>=2.0                                      |
| `encryption`      | new: `kailash[trust-encryption]`  | cryptography>=41.0                             |
| `sso`             | new: `kailash[trust-sso]`         | PyJWT>=2.8, cryptography>=41.0                 |
| `windows`         | new: `kailash[trust-windows]`     | pywin32 (win32 only)                           |

### 2.4 Kaizen Dependency Changes

**Before**:

```toml
dependencies = [
    "kailash>=1.0.0,<2.0.0",
    "eatp>=0.1.0",           # <-- REMOVE
    ...
]
```

**After**:

```toml
dependencies = [
    "kailash>=2.0.0,<3.0.0",  # trust primitives now in core
    ...
]
```

Kaizen's `eatp>=0.1.0` dependency is REMOVED. All trust types come from `kailash.trust.*`.

### 2.5 Pydantic Version Floor

Kailash core currently pins `pydantic>=1.9`. EATP requires `pydantic>=2.6`. The merge raises the kailash core floor to `pydantic>=2.6`. This is a **breaking change** for any consumer still on Pydantic v1.

---

## 3. Shim Package Design

### 3.1 EATP Shim Package (`packages/eatp/`)

After the merge, `packages/eatp/` becomes a thin redirect package:

**`packages/eatp/src/eatp/__init__.py`**:

```python
"""EATP compatibility shim -- all code has moved to kailash.trust.

Install kailash[trust] and import from kailash.trust instead.
This package emits DeprecationWarning on first import and will be
removed in a future release.
"""
import warnings
warnings.warn(
    "The 'eatp' package is deprecated. "
    "Use 'from kailash.trust import ...' instead. "
    "Install: pip install kailash[trust]",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export everything from kailash.trust for backward compatibility
from kailash.trust import *  # noqa: F401,F403
from kailash.trust import __all__  # noqa: F401
```

**Every submodule** follows the same pattern:

```python
# eatp/chain.py
import warnings
warnings.warn(
    "Import from 'kailash.trust.chain' instead of 'eatp.chain'.",
    DeprecationWarning,
    stacklevel=2,
)
from kailash.trust.chain import *  # noqa: F401,F403
```

**`packages/eatp/pyproject.toml`** changes:

```toml
[project]
name = "eatp"
version = "0.3.0"  # Bump to signal shim transition
description = "EATP compatibility shim — use kailash[trust] instead"
dependencies = [
    "kailash[trust]>=2.0.0",  # Depends on the new kailash
]
```

The shim package:

- Continues publishing to PyPI
- Every import path emits `DeprecationWarning` once
- Has zero code -- only re-export stubs
- Declares dependency on `kailash[trust]>=2.0.0`
- Version bumps to 0.3.0 to signal the transition

### 3.2 Trust-Plane Shim Package (`packages/trust-plane/`)

Same pattern:

**`packages/trust-plane/src/trustplane/__init__.py`**:

```python
import warnings
warnings.warn(
    "The 'trust-plane' package is deprecated. "
    "Use 'from kailash.trust.plane import ...' instead. "
    "Install: pip install kailash[trust]",
    DeprecationWarning,
    stacklevel=2,
)
from kailash.trust.plane import *  # noqa: F401,F403
from kailash.trust.plane import __all__  # noqa: F401
```

**Every submodule** follows the same pattern (e.g., `trustplane.project` -> `kailash.trust.plane.project`).

**`packages/trust-plane/pyproject.toml`** changes:

```toml
[project]
name = "trust-plane"
version = "0.3.0"
description = "TrustPlane compatibility shim — use kailash[trust] instead"
dependencies = [
    "kailash[trust]>=2.0.0",
]
```

### 3.3 DeprecationWarning Strategy

- Each module emits the warning ONCE per process (Python's default `DeprecationWarning` filter)
- `stacklevel=2` so the warning points to the caller's import, not the shim file
- Message tells the user exactly what to change: old import -> new import, package to install
- Shim packages are maintained for at minimum 2 minor kailash releases (e.g., removed in kailash 2.2+)
- The `eatp` CLI entry point in the shim package continues to work (delegates to `kailash.trust.cli:main`)

### 3.4 Submodule Shim Inventory

Every submodule needs a shim redirect. The full list:

**EATP shims** (one file per original module, ~90 shim files):

- `eatp.chain` -> `kailash.trust.chain`
- `eatp.crypto` -> `kailash.trust.crypto`
- `eatp.store` -> `kailash.trust.eatp_store`
- `eatp.store.memory` -> `kailash.trust.eatp_store.memory`
- `eatp.store.filesystem` -> `kailash.trust.eatp_store.filesystem`
- `eatp.store.sqlite` -> `kailash.trust.eatp_store.sqlite`
- `eatp.constraints.budget_tracker` -> `kailash.trust.constraints.budget_tracker`
- ... (every leaf module gets a shim)

**Trust-plane shims** (one file per original module, ~45 shim files):

- `trustplane.project` -> `kailash.trust.plane.project`
- `trustplane.store` -> `kailash.trust.plane.store`
- `trustplane.store.sqlite` -> `kailash.trust.plane.store.sqlite`
- `trustplane._locking` -> `kailash.trust.plane._locking`
- ... (every leaf module gets a shim)

---

## 4. Consumer Migration Requirements

### 4.1 Kaizen (Internal Consumer, ~75 shim modules)

**Current state**: Kaizen's `kaizen/trust/` directory has ~75 modules. Of these:

- **~60 are pure re-export shims** (`from eatp.X import *`) -- these become shims pointing to `kailash.trust.X`
- **~5 have original Kaizen-specific code** that imports from eatp:
  - `kaizen/trust/store.py` -- PostgresTrustStore (DataFlow-backed, original code)
  - `kaizen/trust/authority.py` -- OrganizationalAuthorityRegistry (DataFlow-backed, original code)
  - `kaizen/trust/audit_store.py` -- PostgresAuditStore (DataFlow-backed, original code + re-exports)
  - `kaizen/trust/governance/approval_manager.py` -- original code (imports kailash.runtime)
  - `kaizen/trust/governance/budget_enforcer.py` -- original code (imports kailash.runtime, DataFlow)
  - `kaizen/trust/governance/budget_reset.py` -- original code (imports kailash.runtime, DataFlow)
  - `kaizen/trust/migrations/eatp_human_origin.py` -- original code (DataFlow migration)

**Migration steps**:

1. **Pure shim modules**: Change `from eatp.X import *` to `from kailash.trust.X import *` in all ~60 files
2. **Original code modules**: Change `from eatp.Y import Z` to `from kailash.trust.Y import Z` in the ~5 files with original code
3. **kaizen/trust/**init**.py**: Change all `from kaizen.trust.X import ...` import chains (the source is now `kailash.trust.X`)
4. **pyproject.toml**: Remove `eatp>=0.1.0` from dependencies, bump kailash dependency to `>=2.0.0`

**The `kaizen/trust/` directory continues to exist** as a convenience re-export layer. Kaizen users can import from either `kaizen.trust` or `kailash.trust` -- the kaizen layer just adds Kaizen-specific types (PostgresTrustStore, OrganizationalAuthorityRegistry, budget enforcer, approval manager).

### 4.2 External Users of `eatp` Package

**Migration path**:

1. `pip install kailash[trust]` (replaces `pip install eatp`)
2. Change imports:
   - `from eatp import TrustOperations` -> `from kailash.trust import TrustOperations`
   - `from eatp.chain import GenesisRecord` -> `from kailash.trust.chain import GenesisRecord`
   - `from eatp.crypto import generate_keypair` -> `from kailash.trust.crypto import generate_keypair`
   - `from eatp.store.memory import InMemoryTrustStore` -> `from kailash.trust.eatp_store.memory import InMemoryTrustStore`
3. During transition, `pip install eatp>=0.3.0` pulls in `kailash[trust]` and the old imports work with `DeprecationWarning`

### 4.3 External Users of `trust-plane` Package

**Migration path**:

1. `pip install kailash[trust]` (replaces `pip install trust-plane`)
2. Change imports:
   - `from trustplane import TrustProject` -> `from kailash.trust.plane import TrustProject`
   - `from trustplane.store.sqlite import SqliteTrustPlaneStore` -> `from kailash.trust.plane.store.sqlite import SqliteTrustPlaneStore`
   - `from trustplane.models import DecisionRecord` -> `from kailash.trust.plane.models import DecisionRecord`
3. During transition, `pip install trust-plane>=0.3.0` pulls in `kailash[trust]` and old imports work with `DeprecationWarning`

### 4.4 Other Internal Consumers

| Consumer                      | Current Dependency            | Change Required                                 |
| ----------------------------- | ----------------------------- | ----------------------------------------------- |
| kailash-dataflow              | None (EATP-agnostic)          | No change                                       |
| kailash-nexus                 | None (EATP-agnostic)          | No change                                       |
| kailash-pact (upcoming)       | Will depend on kailash only   | Design against `kailash.trust.*` from the start |
| astra, arbor (external repos) | May import eatp or trustplane | Update imports, or rely on shim packages        |

---

## 5. Test Migration Requirements

### 5.1 EATP Tests (`packages/eatp/tests/`)

**Current structure** (3 tiers, ~85 test files):

```
packages/eatp/tests/
    conftest.py                          -> tests/trust/conftest.py
    test_coverage_verification.py        -> tests/trust/test_coverage_verification.py
    unit/
        test_adversarial.py              -> tests/trust/unit/test_adversarial.py
        test_aws_kms_key_manager.py      -> tests/trust/unit/test_aws_kms_key_manager.py
        test_behavioral_scoring.py       -> tests/trust/unit/test_behavioral_scoring.py
        test_biscuit_interop.py          -> tests/trust/unit/test_biscuit_interop.py
        test_budget_tracker.py           -> tests/trust/unit/test_budget_tracker.py
        test_cascade_revoke.py           -> tests/trust/unit/test_cascade_revoke.py
        test_cascade_revoke_atomicity.py -> tests/trust/unit/test_cascade_revoke_atomicity.py
        test_challenge.py               -> tests/trust/unit/test_challenge.py
        test_circuit_breaker_bounded.py  -> tests/trust/unit/test_circuit_breaker_bounded.py
        test_circuit_breaker_registry.py -> tests/trust/unit/test_circuit_breaker_registry.py
        test_cli.py                      -> tests/trust/unit/test_cli.py
        test_cli_smoke.py               -> tests/trust/unit/test_cli_smoke.py
        test_compliance_export.py        -> tests/trust/unit/test_compliance_export.py
        test_constraints_postures.py     -> tests/trust/unit/test_constraints_postures.py
        test_conventions.py              -> tests/trust/unit/test_conventions.py
        test_coverage_gaps.py            -> tests/trust/unit/test_coverage_gaps.py
        test_deep_analyst_fixes.py       -> tests/trust/unit/test_deep_analyst_fixes.py
        test_did.py                      -> tests/trust/unit/test_did.py
        test_dimension_registry_alignment.py -> tests/trust/unit/test_dimension_registry_alignment.py
        test_dual_signature.py           -> tests/trust/unit/test_dual_signature.py
        test_enforce_reasoning.py        -> tests/trust/unit/test_enforce_reasoning.py
        test_enforcer_bounded_memory.py  -> tests/trust/unit/test_enforcer_bounded_memory.py
        test_enforcer_hooks.py           -> tests/trust/unit/test_enforcer_hooks.py
        test_exceptions.py              -> tests/trust/unit/test_exceptions.py
        test_execution_context_constraints.py -> tests/trust/unit/test_execution_context_constraints.py
        test_file_locking.py             -> tests/trust/unit/test_file_locking.py
        test_filesystem_store.py         -> tests/trust/unit/test_filesystem_store.py
        test_hooks.py                    -> tests/trust/unit/test_hooks.py
        test_input_validation.py         -> tests/trust/unit/test_input_validation.py
        test_jwt_interop.py              -> tests/trust/unit/test_jwt_interop.py
        test_key_manager_security.py     -> tests/trust/unit/test_key_manager_security.py
        test_kms_fail_closed.py          -> tests/trust/unit/test_kms_fail_closed.py
        test_knowledge_reasoning.py      -> tests/trust/unit/test_knowledge_reasoning.py
        test_mcp_reasoning.py            -> tests/trust/unit/test_mcp_reasoning.py
        test_memory_store_soft_delete.py -> tests/trust/unit/test_memory_store_soft_delete.py
        test_metrics_bounded.py          -> tests/trust/unit/test_metrics_bounded.py
        test_metrics_export.py           -> tests/trust/unit/test_metrics_export.py
        test_models_crypto.py            -> tests/trust/unit/test_models_crypto.py
        test_path_traversal_prevention.py -> tests/trust/unit/test_path_traversal_prevention.py
        test_posture_default.py          -> tests/trust/unit/test_posture_default.py
        test_posture_evidence.py         -> tests/trust/unit/test_posture_evidence.py
        test_property_based.py           -> tests/trust/unit/test_property_based.py
        test_proximity_scanner.py        -> tests/trust/unit/test_proximity_scanner.py
        test_public_api_exports.py       -> tests/trust/unit/test_public_api_exports.py
        test_quickstart.py               -> tests/trust/unit/test_quickstart.py
        test_reasoning.py                -> tests/trust/unit/test_reasoning.py
        test_reasoning_backward_compat.py -> tests/trust/unit/test_reasoning_backward_compat.py
        test_reasoning_crypto.py         -> tests/trust/unit/test_reasoning_crypto.py
        test_reasoning_enrichment.py     -> tests/trust/unit/test_reasoning_enrichment.py
        test_reasoning_integration.py    -> tests/trust/unit/test_reasoning_integration.py
        test_reasoning_store_audit_scoring.py -> tests/trust/unit/test_reasoning_store_audit_scoring.py
        test_reasoning_transplant_attack.py -> tests/trust/unit/test_reasoning_transplant_attack.py
        test_roles.py                    -> tests/trust/unit/test_roles.py
        test_scoring.py                  -> tests/trust/unit/test_scoring.py
        test_sd_jwt.py                   -> tests/trust/unit/test_sd_jwt.py
        test_sd_jwt_reasoning.py         -> tests/trust/unit/test_sd_jwt_reasoning.py
        test_sdk_conventions.py          -> tests/trust/unit/test_sdk_conventions.py
        test_serialization.py            -> tests/trust/unit/test_serialization.py
        test_siem_export.py              -> tests/trust/unit/test_siem_export.py
        test_sqlite_trust_store.py       -> tests/trust/unit/test_sqlite_trust_store.py
        test_ucan.py                     -> tests/trust/unit/test_ucan.py
        test_verify_reasoning.py         -> tests/trust/unit/test_verify_reasoning.py
        test_vocabulary.py               -> tests/trust/unit/test_vocabulary.py
        test_w3c_vc.py                   -> tests/trust/unit/test_w3c_vc.py
    integration/
        test_lifecycle.py                -> tests/trust/integration/test_lifecycle.py
        test_mcp_integration.py          -> tests/trust/integration/test_mcp_integration.py
        test_wire_format.py              -> tests/trust/integration/test_wire_format.py
        test_posture_store.py            -> tests/trust/integration/test_posture_store.py
        test_budget_store.py             -> tests/trust/integration/test_budget_store.py
    e2e/
        (empty currently)                -> tests/trust/e2e/
    benchmarks/
        test_benchmarks.py               -> tests/trust/benchmarks/test_benchmarks.py
        test_verification_gradient.py    -> tests/trust/benchmarks/test_verification_gradient.py
    fixtures/
        wire_format/
            generate_fixtures.py         -> tests/trust/fixtures/wire_format/generate_fixtures.py
```

### 5.2 Trust-Plane Tests (`packages/trust-plane/tests/`)

**Current structure** (3 tiers, ~55 test files):

```
packages/trust-plane/tests/
    conftest.py                                    -> tests/trust/plane/conftest.py
    unit/
        test_models.py                              -> tests/trust/plane/unit/test_models.py
        test_eatp_api_surface.py                    -> tests/trust/plane/unit/test_eatp_api_surface.py
        test_pathutils.py                           -> tests/trust/plane/unit/test_pathutils.py
        test_exceptions.py                          -> tests/trust/plane/unit/test_exceptions.py
        test_templates.py                           -> tests/trust/plane/unit/test_templates.py
        test_identity_jwks.py                       -> tests/trust/plane/unit/test_identity_jwks.py
        test_encryption.py                          -> tests/trust/plane/unit/test_encryption.py
        test_key_managers.py                        -> tests/trust/plane/unit/test_key_managers.py
    integration/
        test_project.py                             -> tests/trust/plane/integration/test_project.py
        test_cli.py                                 -> tests/trust/plane/integration/test_cli.py
        test_trustplane_store.py                    -> tests/trust/plane/integration/test_trustplane_store.py
        test_delegation.py                          -> tests/trust/plane/integration/test_delegation.py
        test_diagnostics.py                         -> tests/trust/plane/integration/test_diagnostics.py
        test_file_tracking.py                       -> tests/trust/plane/integration/test_file_tracking.py
        test_session.py                             -> tests/trust/plane/integration/test_session.py
        test_recovery.py                            -> tests/trust/plane/integration/test_recovery.py
        test_shadow_mode.py                         -> tests/trust/plane/integration/test_shadow_mode.py
        test_holds.py                               -> tests/trust/plane/integration/test_holds.py
        test_bundle.py                              -> tests/trust/plane/integration/test_bundle.py
        test_mirror_records.py                      -> tests/trust/plane/integration/test_mirror_records.py
        test_competency_map.py                      -> tests/trust/plane/integration/test_competency_map.py
        test_proxy.py                               -> tests/trust/plane/integration/test_proxy.py
        test_migrate.py                             -> tests/trust/plane/integration/test_migrate.py
        test_migrate_sqlite.py                      -> tests/trust/plane/integration/test_migrate_sqlite.py
        test_posture.py                             -> tests/trust/plane/integration/test_posture.py
        test_conformance.py                         -> tests/trust/plane/integration/test_conformance.py
        test_constraints.py                         -> tests/trust/plane/integration/test_constraints.py
        test_config.py                              -> tests/trust/plane/integration/test_config.py
        test_key_protection.py                      -> tests/trust/plane/integration/test_key_protection.py
        test_key_managers.py                        -> tests/trust/plane/integration/test_key_managers.py
        test_identity.py                            -> tests/trust/plane/integration/test_identity.py
        test_compliance_export.py                   -> tests/trust/plane/integration/test_compliance_export.py
        test_docs_examples.py                       -> tests/trust/plane/integration/test_docs_examples.py
        test_multitenancy.py                        -> tests/trust/plane/integration/test_multitenancy.py
        test_quickstart.py                          -> tests/trust/plane/integration/test_quickstart.py
        test_rbac.py                                -> tests/trust/plane/integration/test_rbac.py
        test_siem.py                                -> tests/trust/plane/integration/test_siem.py
        test_shadow.py                              -> tests/trust/plane/integration/test_shadow.py
        test_archive.py                             -> tests/trust/plane/integration/test_archive.py
        test_concurrency.py                         -> tests/trust/plane/integration/test_concurrency.py
        test_cursor_integration.py                  -> tests/trust/plane/integration/test_cursor_integration.py
        store/
            test_sqlite_trustplane_store.py         -> tests/trust/plane/integration/store/test_sqlite_trustplane_store.py
            test_sqlite_migrations.py               -> tests/trust/plane/integration/store/test_sqlite_migrations.py
            test_store_conformance.py               -> tests/trust/plane/integration/store/test_store_conformance.py
        security/
            conftest.py                             -> tests/trust/plane/integration/security/conftest.py
            test_static_checks.py                   -> tests/trust/plane/integration/security/test_static_checks.py
            test_security_patterns.py               -> tests/trust/plane/integration/security/test_security_patterns.py
    e2e/
        test_mcp_server.py                          -> tests/trust/plane/e2e/test_mcp_server.py
        test_cross_deliverable.py                   -> tests/trust/plane/e2e/test_cross_deliverable.py
        test_dashboard.py                           -> tests/trust/plane/e2e/test_dashboard.py
        store/
            test_postgres_store.py                  -> tests/trust/plane/e2e/store/test_postgres_store.py
```

### 5.3 conftest.py Changes

1. **Root `conftest.py`**: No changes needed -- it auto-loads `.env` for all tests
2. **New `tests/trust/conftest.py`**: Merge fixtures from both EATP and trust-plane conftest files
   - `tmp_store_dir` fixture from EATP conftest
   - asyncio_mode already set globally in root `pyproject.toml`
3. **New `tests/trust/plane/conftest.py`**: Trust-plane-specific fixtures
4. **All test imports must be updated**: `from eatp import X` -> `from kailash.trust import X`, `from trustplane import X` -> `from kailash.trust.plane import X`

### 5.4 Test Count Verification

The merge MUST result in zero test loss:

- EATP: ~85 test files
- Trust-plane: ~55 test files (1499 tests passing)
- Total: ~140 test files
- Every test that passes before the merge MUST pass after

### 5.5 pytest Configuration Changes

Add to root `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = [
    # existing markers...
    "trust: Trust subsystem tests",
    "trust_security: Trust security regression tests",
    "trust_benchmark: Trust performance benchmarks",
]
```

---

## 6. Entry Point Changes

### 6.1 CLI Entry Points

| CLI Command      | Current Entry Point          | Target Entry Point                    | Notes                    |
| ---------------- | ---------------------------- | ------------------------------------- | ------------------------ |
| `eatp`           | `eatp.cli:main`              | `kailash.trust.cli:main`              | EATP CLI commands        |
| `attest`         | `trustplane.cli:main`        | `kailash.trust.plane.cli:main`        | Trust-plane CLI commands |
| `trustplane-mcp` | `trustplane.mcp_server:main` | `kailash.trust.plane.mcp_server:main` | MCP server               |
| `kailash`        | `kailash.cli:main`           | `kailash.cli:main`                    | Unchanged                |

### 6.2 Kailash Core pyproject.toml Entry Points

Add to kailash core `pyproject.toml`:

```toml
[project.scripts]
kailash = "kailash.cli:main"
eatp = "kailash.trust.cli:main"
attest = "kailash.trust.plane.cli:main"
trustplane-mcp = "kailash.trust.plane.mcp_server:main"
```

### 6.3 Shim Package Entry Points

The shim packages ALSO declare entry points (for users who install the shim):

```toml
# packages/eatp/pyproject.toml
[project.scripts]
eatp = "kailash.trust.cli:main"  # Delegates to new location

# packages/trust-plane/pyproject.toml
[project.scripts]
attest = "kailash.trust.plane.cli:main"
trustplane-mcp = "kailash.trust.plane.mcp_server:main"
```

### 6.4 CLI Namespace Decision

The `eatp` and `attest` commands remain as separate entry points. They are NOT merged into `kailash trust ...` subcommands because:

- They have their own independent Click command trees
- External docs and scripts reference them by name
- A `kailash trust eatp ...` prefix adds typing overhead for no benefit

---

## 7. Success Criteria

Each criterion has a concrete acceptance test.

### SC-1: Core Import Works

```python
from kailash.trust import GenesisRecord, DelegationRecord, TrustOperations
from kailash.trust.chain import TrustLineageChain, VerificationResult
from kailash.trust.crypto import generate_keypair, sign, verify_signature
```

**Test**: `test_trust_core_imports.py` -- import all public names from `kailash.trust.__all__` and verify they are the correct classes.

### SC-2: pip install kailash Includes Trust Types

```bash
pip install kailash
python -c "from kailash.trust.chain import GenesisRecord; print('OK')"
```

**Test**: CI job that installs `kailash` (no extras) and verifies trust type imports work. Crypto operations (`generate_keypair`) should raise `ImportError` with install instructions when `pynacl` is missing.

### SC-3: Kaizen Depends on Kailash Only

```toml
# kailash-kaizen pyproject.toml
dependencies = ["kailash>=2.0.0,<3.0.0", ...]  # NO eatp
```

**Test**: `pip install kailash-kaizen` in a clean venv and verify `from kaizen.trust import TrustOperations` works without `eatp` installed separately.

### SC-4: All EATP Tests Pass Under New Paths

```bash
pytest tests/trust/ -v
```

**Test**: All ~85 EATP test files pass with updated imports. Test count matches pre-merge count.

### SC-5: All Trust-Plane Tests Pass Under New Paths

```bash
pytest tests/trust/plane/ -v
```

**Test**: All ~55 trust-plane test files pass (1499 tests). Test count matches pre-merge count.

### SC-6: Shim Package Backward Compatibility

```python
import warnings
with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter("always")
    from eatp import TrustOperations
    assert len(w) == 1
    assert issubclass(w[0].category, DeprecationWarning)
    assert "kailash.trust" in str(w[0].message)
```

**Test**: `test_eatp_shim_backward_compat.py` -- verify old imports work and emit DeprecationWarning.

### SC-7: Trust-Plane Shim Backward Compatibility

```python
import warnings
with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter("always")
    from trustplane import TrustProject
    assert len(w) == 1
    assert issubclass(w[0].category, DeprecationWarning)
    assert "kailash.trust.plane" in str(w[0].message)
```

**Test**: `test_trustplane_shim_backward_compat.py` -- verify old imports work and emit DeprecationWarning.

### SC-8: CLI Entry Points Work

```bash
eatp --help       # Must print EATP CLI help
attest --help     # Must print attest CLI help
trustplane-mcp    # Must start MCP server
```

**Test**: CLI smoke tests verifying help output and error-free startup.

### SC-9: Security Patterns Preserved

All 12 security patterns documented in `packages/trust-plane/CLAUDE.md` must continue to work:

- `validate_id()` path traversal prevention
- `O_NOFOLLOW` via `safe_read_json()` / `safe_open()`
- `atomic_write()` for record writes
- `math.isfinite()` on numeric constraints
- Bounded collections (`maxlen=10000`)
- Monotonic escalation
- `hmac.compare_digest()` for hash comparison
- Key material zeroization
- `frozen=True` on MultiSigPolicy
- `from_dict()` validates all fields
- `math.isfinite()` on runtime cost values

**Test**: The existing security regression tests (`tests/trust/plane/integration/security/`) continue to pass unchanged.

### SC-10: No Import Cycle

```python
import kailash  # Must not trigger circular import
from kailash.trust import TrustOperations  # No circular dependency
```

**Test**: Fresh Python interpreter, import kailash, verify no `ImportError` from circular imports.

---

## 8. Non-Requirements (Explicitly Out of Scope)

### 8.1 NOT Changing

1. **EATP specification** -- The CC BY 4.0 specification remains independent. Only the Python implementation moves.

2. **Rust SDK** -- `kailash-rs` implements EATP independently. This merge is Python-only and has no effect on the Rust implementation.

3. **kailash-dataflow** -- No dependency on EATP. Zero changes required.

4. **kailash-nexus** -- No dependency on EATP. Zero changes required.

5. **Core SDK behavior** -- Workflow execution (`runtime.execute(workflow.build())`), node types, WorkflowBuilder patterns, LocalRuntime, AsyncLocalRuntime -- all unchanged.

6. **Trust-plane security patterns** -- All 12 red-team-hardened security patterns are preserved exactly as-is. No simplification, no refactoring, no "cleanup."

7. **EATP SDK conventions** -- Dataclasses (not Pydantic for data types), `to_dict()`/`from_dict()` serialization, `TrustError` base exception, Ed25519 mandatory signing -- all preserved.

8. **Store implementations** -- SQLite, filesystem, PostgreSQL, in-memory stores are moved as-is. No refactoring of store internals.

9. **Kaizen's DataFlow-backed types** -- `PostgresTrustStore`, `OrganizationalAuthorityRegistry`, budget enforcer, approval manager stay in kaizen. They are Kaizen-specific (depend on DataFlow + kailash runtime) and do NOT move into core.

10. **Test infrastructure** -- conftest.py patterns, pytest markers, asyncio_mode settings remain functionally identical.

### 8.2 NOT Doing in This Merge

1. **Merging EATP and trust-plane exception hierarchies** -- `TrustError` (eatp) and `TrustPlaneError` (trust-plane) remain separate exception roots. Merging them would break every catch clause in consumer code.

2. **Merging EATP TrustStore and TrustPlane TrustPlaneStore** -- These are different abstractions (chain storage vs project record storage). They stay separate.

3. **Removing the `kaizen/trust/` re-export layer** -- Kaizen users may import from `kaizen.trust`. This layer stays as a convenience.

4. **Removing shim packages from PyPI** -- Both `eatp` and `trust-plane` continue to be published. Removal is a separate future decision.

5. **Adding new features to the trust subsystem** -- This is a pure move+shim operation. No new trust features, no new APIs, no new tests.

6. **Kailash major version bump decision** -- Whether this is kailash 2.0 or 1.x with additive exports is a separate versioning decision (see brief).

7. **Updating external documentation** -- Sphinx docs, README updates, and user migration guides are tracked separately (per deployment rules, these are mandatory during `/codify` and `/deploy`).

8. **Cross-SDK alignment** -- Filing kailash-rs issues for this merge is not required since it's a packaging change, not a semantic change.
