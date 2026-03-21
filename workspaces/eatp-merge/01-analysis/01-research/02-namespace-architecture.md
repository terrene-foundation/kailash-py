# Namespace Architecture: kailash.trust.\*

**Author**: deep-analyst
**Date**: 2026-03-21
**Status**: PROPOSED
**Complexity Score**: 27 (Complex)
**Input**: 95 source files across 2 packages (EATP: 63 files, trust-plane: 42 files)

---

## Executive Summary

The merge of `packages/eatp/` (63 files, 18 subpackages) and `packages/trust-plane/` (42 files, 6 subpackages) into `src/kailash/trust/` requires resolving four naming collisions (store, exceptions, crypto, ConstraintEnvelope), three conceptual boundary decisions (protocol vs platform, chain store vs record store, signing vs encryption), and one CLI entry point strategy. This document defines the definitive directory tree, collision resolution, public API surface, and backward-compatible import shim strategy.

The key architectural insight is the **protocol/plane split**: EATP is a _protocol implementation_ (chains, attestations, signing, verification) while trust-plane is a _platform layer_ (projects, sessions, decisions, enforcement). These map naturally to `kailash.trust.protocol` and `kailash.trust.plane` -- not to a flat list of six top-level packages as the brief proposed.

---

## 1. Design Principles

### 1.1 Two-Layer Architecture

Every module in the merged codebase belongs to exactly one of two layers:

| Layer        | Namespace                | What it contains                                                                                                                                                       | Analogy                        |
| ------------ | ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------ |
| **Protocol** | `kailash.trust.protocol` | EATP specification implementation: chains, attestations, signing, verification, constraints, postures, reasoning, delegation records, authority, roles, vocabulary     | TCP/IP spec implementation     |
| **Plane**    | `kailash.trust.plane`    | Trust-plane platform: projects, sessions, decisions, milestones, holds, enforcement, delegation workflows, dashboard, CLI, SIEM, RBAC, identity, shadow mode, archival | An HTTP server built on TCP/IP |

The protocol layer has zero imports from the plane layer. The plane layer imports from the protocol layer. This dependency direction is enforced and testable.

### 1.2 Disambiguation Strategy

Where both packages have a concept with the same name but different semantics:

| Collision            | Protocol meaning                                                                     | Plane meaning                                                                                                   | Resolution                                                                                                                                                                         |
| -------------------- | ------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `store/`             | Chain storage (TrustStore ABC: store/get/update/delete chains)                       | Record storage (TrustPlaneStore Protocol: decisions, milestones, holds, delegates)                              | `protocol.chain_store` vs `plane.record_store`                                                                                                                                     |
| `exceptions`         | TrustError hierarchy (chain/signature/authority errors)                              | TrustPlaneError hierarchy (store/key/budget/RBAC errors)                                                        | Unified in `kailash.trust.exceptions` with single root                                                                                                                             |
| `crypto`             | Ed25519 signing, HMAC, chain hashing (PyNaCl)                                        | AES-256-GCM encryption-at-rest (cryptography lib)                                                               | `protocol.signing` vs `plane.encryption`                                                                                                                                           |
| `ConstraintEnvelope` | Protocol-level: generic constraint types (ConstraintType enum, Constraint dataclass) | Platform-level: five-dimension frozen dataclasses (Operational, DataAccess, Financial, Temporal, Communication) | Both preserved. Protocol's lives in `protocol.chain`. Plane's lives in `plane.models`. No rename needed -- different classes, different modules, full qualification disambiguates. |
| `key_manager`        | EATP KeyManagerInterface (InMemory, AWS KMS -- async, base64 key refs)               | TrustPlaneKeyManager Protocol (LocalFile, AWS, Azure, Vault -- sync, raw bytes)                                 | `protocol.key_management` vs `plane.key_management`                                                                                                                                |
| `templates`          | EATP constraint templates (dict-based, agent archetypes)                             | Trust-plane constraint templates (ConstraintEnvelope factories, project domains)                                | `protocol.templates` vs `plane.templates`                                                                                                                                          |

### 1.3 Depth Rules

- Maximum namespace depth: 4 levels (`kailash.trust.protocol.signing`)
- No single-file subpackages. If a directory would contain only `__init__.py`, the module stays as a file in the parent.
- Subpackages are created only when a concept has 3+ files.

---

## 2. Complete Directory Tree

```
src/kailash/trust/
    __init__.py                          # Public API surface (Section 4)
    exceptions.py                        # UNIFIED exception hierarchy (Section 5)
    _compat.py                           # Internal: version detection, shim helpers

    protocol/                            # EATP specification implementation
        __init__.py                      # Re-exports core protocol types
        chain.py                         # <- eatp/chain.py (GenesisRecord, DelegationRecord, TrustLineageChain, etc.)
        authority.py                     # <- eatp/authority.py (OrganizationalAuthority, AuthorityPermission)
        operations.py                    # <- eatp/operations/__init__.py (TrustOperations, TrustKeyManager, CapabilityRequest)
        roles.py                         # <- eatp/roles.py (TrustRole, ROLE_PERMISSIONS)
        vocabulary.py                    # <- eatp/vocabulary.py (EATP vocabulary mapping)
        hooks.py                         # <- eatp/hooks.py (EATPHook, HookRegistry, HookType)
        execution_context.py             # <- eatp/execution_context.py (HumanOrigin, ExecutionContext)
        scoring.py                       # <- eatp/scoring.py (behavioral scoring)
        metrics.py                       # <- eatp/metrics.py (trust metrics)
        security.py                      # <- eatp/security.py (security utilities)
        cache.py                         # <- eatp/cache.py (trust cache)
        circuit_breaker.py               # <- eatp/circuit_breaker.py
        graph_validator.py               # <- eatp/graph_validator.py (delegation graph validation)
        constraint_validator.py          # <- eatp/constraint_validator.py
        audit_service.py                 # <- eatp/audit_service.py
        audit_store.py                   # <- eatp/audit_store.py

        signing/                         # Ed25519 + HMAC cryptographic signing
            __init__.py                  # Re-exports: generate_keypair, sign, verify_signature, etc.
            crypto.py                    # <- eatp/crypto.py (Ed25519 sign/verify, HMAC, DualSignature, chain hashing)
            multi_sig.py                 # <- eatp/multi_sig.py (MultiSigPolicy, multi-signature support)
            merkle.py                    # <- eatp/merkle.py (Merkle tree proofs)
            timestamping.py              # <- eatp/timestamping.py (trusted timestamps)
            rotation.py                  # <- eatp/rotation.py (key rotation)
            crl.py                       # <- eatp/crl.py (certificate revocation lists)

        posture/                         # Trust posture state machine
            __init__.py                  # Re-exports: TrustPosture, PostureStateMachine, etc.
            postures.py                  # <- eatp/postures.py (TrustPosture, PostureStateMachine, PostureEvidence)
            posture_store.py             # <- eatp/posture_store.py (SQLitePostureStore)
            posture_agent.py             # <- eatp/posture_agent.py (PostureAwareAgent)

        reasoning/                       # Reasoning trace extension
            __init__.py                  # Re-exports: ReasoningTrace, ConfidentialityLevel, etc.
            traces.py                    # <- eatp/reasoning.py (ReasoningTrace, EvidenceReference)

        constraints/                     # Extensible constraint system
            __init__.py                  # <- eatp/constraints/__init__.py (re-exports)
            dimension.py                 # <- eatp/constraints/dimension.py (ConstraintDimension ABC)
            builtin.py                   # <- eatp/constraints/builtin.py (CostLimit, Time, Resource, etc.)
            evaluator.py                 # <- eatp/constraints/evaluator.py (MultiDimensionEvaluator)
            commerce.py                  # <- eatp/constraints/commerce.py
            spend_tracker.py             # <- eatp/constraints/spend_tracker.py
            budget_tracker.py            # <- eatp/constraints/budget_tracker.py (BudgetTracker)
            budget_store.py              # <- eatp/constraints/budget_store.py (SQLiteBudgetStore)

        chain_store/                     # Trust chain persistence (TrustStore ABC)
            __init__.py                  # <- eatp/store/__init__.py (TrustStore ABC, TransactionContext)
            memory.py                    # <- eatp/store/memory.py (InMemoryTrustStore)
            filesystem.py               # <- eatp/store/filesystem.py (FilesystemStore + file_lock + validate_id)
            sqlite.py                    # <- eatp/store/sqlite.py (SqliteTrustStore)

        enforce/                         # Enforcement modes (strict, shadow, challenge)
            __init__.py                  # <- eatp/enforce/__init__.py (re-exports)
            strict.py                    # <- eatp/enforce/strict.py (StrictEnforcer, Verdict)
            shadow.py                    # <- eatp/enforce/shadow.py (ShadowEnforcer)
            challenge.py                 # <- eatp/enforce/challenge.py (ChallengeProtocol)
            decorators.py                # <- eatp/enforce/decorators.py (@verified, @audited, @shadow)
            proximity.py                 # <- eatp/enforce/proximity.py (ProximityScanner)
            selective_disclosure.py      # <- eatp/enforce/selective_disclosure.py

        key_management/                  # Protocol-level key management (async, base64 refs)
            __init__.py                  # Re-exports: KeyManagerInterface, InMemoryKeyManager
            manager.py                   # <- eatp/key_manager.py (KeyManagerInterface ABC, InMemoryKeyManager, AWSKMSKeyManager)

        revocation/                      # Trust chain revocation
            __init__.py                  # <- eatp/revocation/__init__.py
            broadcaster.py               # <- eatp/revocation/broadcaster.py
            cascade.py                   # <- eatp/revocation/cascade.py

        interop/                         # Standards interoperability
            __init__.py                  # <- eatp/interop/__init__.py
            w3c_vc.py                    # <- eatp/interop/w3c_vc.py (W3C Verifiable Credentials)
            did.py                       # <- eatp/interop/did.py (Decentralized Identifiers)
            ucan.py                      # <- eatp/interop/ucan.py (UCAN tokens)
            sd_jwt.py                    # <- eatp/interop/sd_jwt.py (Selective Disclosure JWT)
            biscuit.py                   # <- eatp/interop/biscuit.py (Biscuit tokens)

        a2a/                             # Agent-to-Agent protocol
            __init__.py                  # <- eatp/a2a/__init__.py
            models.py                    # <- eatp/a2a/models.py
            agent_card.py                # <- eatp/a2a/agent_card.py
            auth.py                      # <- eatp/a2a/auth.py
            exceptions.py               # <- eatp/a2a/exceptions.py
            jsonrpc.py                   # <- eatp/a2a/jsonrpc.py
            service.py                   # <- eatp/a2a/service.py

        messaging/                       # Secure messaging
            __init__.py                  # <- eatp/messaging/__init__.py
            envelope.py                  # <- eatp/messaging/envelope.py
            channel.py                   # <- eatp/messaging/channel.py
            signer.py                    # <- eatp/messaging/signer.py
            verifier.py                  # <- eatp/messaging/verifier.py
            replay_protection.py         # <- eatp/messaging/replay_protection.py
            exceptions.py               # <- eatp/messaging/exceptions.py

        governance/                      # Protocol-level governance models
            __init__.py                  # <- eatp/governance/__init__.py
            models.py                    # <- eatp/governance/models.py
            policy_models.py             # <- eatp/governance/policy_models.py
            policy_engine.py             # <- eatp/governance/policy_engine.py
            cost_estimator.py            # <- eatp/governance/cost_estimator.py
            rate_limiter.py              # <- eatp/governance/rate_limiter.py

        registry/                        # Agent registry
            __init__.py                  # <- eatp/registry/__init__.py
            exceptions.py               # <- eatp/registry/exceptions.py

        orchestration/                   # Trust-aware orchestration
            __init__.py                  # <- eatp/orchestration/__init__.py
            execution_context.py         # <- eatp/orchestration/execution_context.py
            policy.py                    # <- eatp/orchestration/policy.py
            runtime.py                   # <- eatp/orchestration/runtime.py
            exceptions.py               # <- eatp/orchestration/exceptions.py
            integration/                 # Orchestration integrations
                __init__.py              # <- eatp/orchestration/integration/__init__.py
                registry_aware.py        # <- eatp/orchestration/integration/registry_aware.py
                secure_channel.py        # <- eatp/orchestration/integration/secure_channel.py

        esa/                             # Enterprise Service Architecture
            __init__.py                  # <- eatp/esa/__init__.py
            base.py                      # <- eatp/esa/base.py
            api.py                       # <- eatp/esa/api.py
            database.py                  # <- eatp/esa/database.py
            discovery.py                 # <- eatp/esa/discovery.py
            registry.py                  # <- eatp/esa/registry.py
            exceptions.py               # <- eatp/esa/exceptions.py

        knowledge/                       # Knowledge provenance
            __init__.py                  # <- eatp/knowledge/__init__.py
            bridge.py                    # <- eatp/knowledge/bridge.py
            entry.py                     # <- eatp/knowledge/entry.py
            provenance.py               # <- eatp/knowledge/provenance.py

        export/                          # Protocol-level export (SIEM format, compliance)
            __init__.py                  # <- eatp/export/__init__.py
            compliance.py                # <- eatp/export/compliance.py
            siem.py                      # <- eatp/export/siem.py

        agents/                          # Trust-enhanced agent wrappers
            __init__.py                  # Re-exports: TrustedAgent, PseudoAgent
            trusted_agent.py             # <- eatp/trusted_agent.py (TrustedAgent, TrustedSupervisorAgent)
            pseudo_agent.py              # <- eatp/pseudo_agent.py (PseudoAgent, human facade)

        templates/                       # Protocol constraint templates
            __init__.py                  # <- eatp/templates/__init__.py

        migrations/                      # EATP schema migrations
            __init__.py                  # <- eatp/migrations/__init__.py
            eatp_human_origin.py         # <- eatp/migrations/eatp_human_origin.py

        mcp/                             # EATP MCP server
            __init__.py                  # <- eatp/mcp/__init__.py
            server.py                    # <- eatp/mcp/server.py

        cli/                             # EATP CLI (eatp command)
            __init__.py                  # <- eatp/cli/__init__.py
            commands.py                  # <- eatp/cli/commands.py
            quickstart.py               # <- eatp/cli/quickstart.py

    plane/                               # Trust-plane platform layer
        __init__.py                      # Re-exports: TrustProject, TrustPlaneStore, etc.
        project.py                       # <- trustplane/project.py (TrustProject)
        session.py                       # <- trustplane/session.py (AuditSession)
        models.py                        # <- trustplane/models.py (DecisionRecord, MilestoneRecord, ConstraintEnvelope [5-dim], etc.)
        config.py                        # <- trustplane/config.py (TrustPlaneConfig)
        holds.py                         # <- trustplane/holds.py (HoldRecord, hold/approve workflow)
        delegation.py                    # <- trustplane/delegation.py (Delegate, ReviewResolution, cascade revocation)
        compliance.py                    # <- trustplane/compliance.py
        reports.py                       # <- trustplane/reports.py
        diagnostics.py                   # <- trustplane/diagnostics.py
        shadow.py                        # <- trustplane/shadow.py (ShadowMode)
        shadow_store.py                  # <- trustplane/shadow_store.py (ShadowStore)
        mirror.py                        # <- trustplane/mirror.py (Mirror Thesis competency map)
        proxy.py                         # <- trustplane/proxy.py
        identity.py                      # <- trustplane/identity.py (OIDC, IdentityConfig, JWKSProvider)
        rbac.py                          # <- trustplane/rbac.py (RBAC roles, permissions)
        archive.py                       # <- trustplane/archive.py (record archival)
        bundle.py                        # <- trustplane/bundle.py
        siem.py                          # <- trustplane/siem.py (CEF/OCSF formatting, TLS syslog)
        dashboard.py                     # <- trustplane/dashboard.py (web dashboard)
        migrate.py                       # <- trustplane/migrate.py (store migration)
        pathutils.py                     # <- trustplane/pathutils.py (normalize_resource_path)

        _locking.py                      # <- trustplane/_locking.py (file_lock, validate_id, safe_read_json, atomic_write)

        encryption/                      # AES-256-GCM encryption-at-rest
            __init__.py                  # Re-exports: encrypt_record, decrypt_record, derive_encryption_key
            crypto_utils.py              # <- trustplane/crypto_utils.py

        key_management/                  # Platform-level key managers (sync, raw bytes)
            __init__.py                  # Re-exports: TrustPlaneKeyManager, LocalFileKeyManager
            manager.py                   # <- trustplane/key_manager.py (TrustPlaneKeyManager Protocol, LocalFileKeyManager)
            aws_kms.py                   # <- trustplane/key_managers/aws_kms.py
            azure_keyvault.py            # <- trustplane/key_managers/azure_keyvault.py
            vault.py                     # <- trustplane/key_managers/vault.py

        record_store/                    # Trust-plane record persistence (TrustPlaneStore Protocol)
            __init__.py                  # <- trustplane/store/__init__.py (TrustPlaneStore Protocol)
            filesystem.py               # <- trustplane/store/filesystem.py (FileSystemTrustPlaneStore)
            sqlite.py                    # <- trustplane/store/sqlite.py (SqliteTrustPlaneStore)
            postgres.py                  # <- trustplane/store/postgres.py (PostgresTrustPlaneStore)

        conformance/                     # EATP conformance suite
            __init__.py                  # <- trustplane/conformance/__init__.py

        integration/                     # IDE/tool integrations
            __init__.py                  # <- trustplane/integration/__init__.py
            claude_code/                 # Claude Code integration
                __init__.py              # <- trustplane/integration/claude_code/__init__.py
            cursor/                      # Cursor IDE integration
                __init__.py              # <- trustplane/integration/cursor/__init__.py
                hook.py                  # <- trustplane/integration/cursor/hook.py

        templates/                       # Platform constraint templates (ConstraintEnvelope factories)
            __init__.py                  # <- trustplane/templates/__init__.py

        dashboard_templates/             # Dashboard HTML templates
            __init__.py                  # <- trustplane/dashboard_templates/__init__.py

        cli/                             # Trust-plane CLI (attest command)
            __init__.py
            commands.py                  # <- trustplane/cli.py (Click-based CLI entry point)
```

Total: **105 files** in the target tree (95 source + 10 new `__init__.py` files for structural packages).

---

## 3. Rationale for Every Organizational Choice

### 3.1 Why `protocol/` and `plane/`, not flat

The brief proposed six top-level packages (`eatp`, `store`, `signing`, `verification`, `posture`, `reasoning`). This fails because:

1. **It cannot accommodate 63 EATP files.** The EATP package has 18 subpackages. Flattening them into six buckets loses the internal structure that developers already understand.
2. **It creates false equivalence.** `signing` and `verification` are not parallel to `store` -- they are sub-concerns of the protocol, while `store` is an overloaded name spanning both layers.
3. **It cannot represent the dependency direction.** The protocol layer must be importable without the platform layer. A flat structure has no mechanism to enforce this.

The two-layer split preserves the full internal structure of both packages while resolving every collision at the top level.

### 3.2 Why `chain_store/` and `record_store/`, not `store/`

The two `store/` directories implement fundamentally different abstractions:

|                    | EATP `TrustStore`                           | Trust-plane `TrustPlaneStore`                                                   |
| ------------------ | ------------------------------------------- | ------------------------------------------------------------------------------- |
| **What it stores** | TrustLineageChain objects                   | DecisionRecord, MilestoneRecord, HoldRecord, Delegate, ProjectManifest, anchors |
| **API style**      | Async (store_chain, get_chain, list_chains) | Sync (store_decision, get_decision, list_decisions)                             |
| **Backends**       | InMemory, Filesystem, SQLite                | Filesystem, SQLite, PostgreSQL                                                  |
| **Concern**        | Protocol-level chain persistence            | Platform-level project record persistence                                       |

Naming them `chain_store` and `record_store` makes the distinction self-documenting. A developer looking for "where do trust chains go" finds `chain_store`. A developer looking for "where do project decisions go" finds `record_store`.

### 3.3 Why `signing/` and `encryption/`, not `crypto/`

Both packages have crypto modules, but they do completely different things:

|             | EATP `crypto.py`                                              | Trust-plane `crypto_utils.py`                                   |
| ----------- | ------------------------------------------------------------- | --------------------------------------------------------------- |
| **Purpose** | Ed25519 signing, HMAC, chain hashing, key derivation (PBKDF2) | AES-256-GCM encryption/decryption at rest (HKDF key derivation) |
| **Library** | PyNaCl                                                        | cryptography (hazmat)                                           |
| **Output**  | Signatures, hashes                                            | Ciphertext blobs                                                |

`signing/` and `encryption/` are precise names. A developer knows exactly which one to import. The name `crypto/` would perpetuate the collision.

### 3.4 Why `protocol.key_management/` and `plane.key_management/`, not merged

The two key management systems are not compatible:

|                     | EATP `key_manager.py`                          | Trust-plane `key_manager.py`                                                    |
| ------------------- | ---------------------------------------------- | ------------------------------------------------------------------------------- |
| **Interface**       | ABC (abstract class, async)                    | Protocol (structural typing, sync)                                              |
| **Key format**      | Base64-encoded strings                         | Raw bytes                                                                       |
| **Operations**      | generate_keypair, sign, verify, rotate, revoke | sign, get_public_key, key_id, algorithm                                         |
| **Implementations** | InMemoryKeyManager, AWSKMSKeyManager           | LocalFileKeyManager, AwsKmsKeyManager, AzureKeyVaultKeyManager, VaultKeyManager |

Merging them would require breaking one interface or the other. They serve different purposes at different abstraction levels. Both are preserved in their respective layers.

### 3.5 Why `protocol.agents/` for trusted_agent, pseudo_agent, posture_agent

These three modules are trust-enhanced agent wrappers that belong to the protocol layer (they implement EATP trust patterns), not the platform layer (they don't depend on TrustProject or TrustPlaneStore). `posture_agent` is co-located with `posture/` conceptually but it is an agent wrapper, so it groups with other agent wrappers under `protocol.agents/`. The `posture/` subpackage contains the posture state machine and persistence -- the agent wrapper uses it but is not part of it.

### 3.6 Why `plane/` preserves flat structure for most modules

Trust-plane modules are largely standalone files (project.py, session.py, holds.py, etc.). Creating subpackages for concepts with fewer than 3 files would increase depth without improving navigation. Only `record_store/` (3 backends + protocol), `key_management/` (4 implementations + protocol), `encryption/` (1 file, but needed to disambiguate from signing), and `integration/` (2 IDE integrations) justify subpackages.

### 3.7 Why EATP subpackages preserve their structure

EATP subpackages like `a2a/`, `messaging/`, `interop/`, `governance/`, `orchestration/`, `esa/`, `knowledge/` each contain 3-7 tightly coupled files. They are well-established internal groupings. Flattening them would create a 40+ file flat directory that is harder to navigate than the current structure.

---

## 4. Public API Surface: `kailash.trust.__init__.py`

The top-level `__init__.py` exposes the **most-used types** -- the ones that appear in quick-start examples and the 80% use case. Deep imports remain available for advanced usage.

```python
# kailash/trust/__init__.py

"""Kailash Trust — EATP protocol implementation and trust-plane platform.

Quick Start (Protocol):
    from kailash.trust import TrustOperations, TrustKeyManager, generate_keypair
    from kailash.trust.protocol.chain_store.memory import InMemoryTrustStore

Quick Start (Platform):
    from kailash.trust import TrustProject, DecisionRecord, DecisionType
    from kailash.trust.plane.record_store.sqlite import SqliteTrustPlaneStore
"""

# === Protocol-layer essentials ===

# Core operations (ESTABLISH, DELEGATE, VERIFY, AUDIT)
from kailash.trust.protocol.operations import (
    CapabilityRequest,
    TrustKeyManager,
    TrustOperations,
)

# Chain types
from kailash.trust.protocol.chain import (
    AuthorityType,
    CapabilityType,
    ConstraintType,
    DelegationRecord as ProtocolDelegationRecord,
    GenesisRecord,
    TrustLineageChain,
    VerificationLevel,
    VerificationResult,
)

# Authority
from kailash.trust.protocol.authority import (
    AuthorityPermission,
    OrganizationalAuthority,
)

# Signing
from kailash.trust.protocol.signing.crypto import (
    generate_keypair,
    sign,
    verify_signature,
)

# Chain store ABC
from kailash.trust.protocol.chain_store import TrustStore

# Postures
from kailash.trust.protocol.posture import (
    PostureStateMachine,
    TrustPosture,
)

# Reasoning
from kailash.trust.protocol.reasoning import (
    ConfidentialityLevel,
    ReasoningTrace,
)

# Enforcement
from kailash.trust.protocol.enforce import (
    StrictEnforcer,
    Verdict,
)

# === Platform-layer essentials ===

# Project (primary entry point)
from kailash.trust.plane.project import TrustProject

# Models
from kailash.trust.plane.models import (
    CommunicationConstraints,
    ConstraintEnvelope,
    DataAccessConstraints,
    DecisionRecord,
    DecisionType,
    FinancialConstraints,
    MilestoneRecord,
    OperationalConstraints,
    TemporalConstraints,
)

# Record store Protocol
from kailash.trust.plane.record_store import TrustPlaneStore

# === Unified exceptions ===
from kailash.trust.exceptions import (
    TrustError,
    TrustPlaneError,
)
```

**Design decision**: `DelegationRecord` from EATP chain is re-exported as `ProtocolDelegationRecord` to avoid collision with trust-plane's `Delegate` model. Advanced users import the full path: `from kailash.trust.protocol.chain import DelegationRecord`.

---

## 5. Exception Hierarchy Merge

### 5.1 The Problem

EATP has `TrustError` as its root (19 exception classes). Trust-plane has `TrustPlaneError` as its root (22 exception classes). Both have `.details` parameter. Both have `ConstraintViolationError`. They have independent hierarchies with no shared base.

### 5.2 The Solution: Unified Hierarchy with Bridge Base

```python
# kailash/trust/exceptions.py

class TrustError(Exception):
    """Root of ALL trust-related exceptions.

    EATP protocol errors and trust-plane platform errors all inherit from this.
    Catch TrustError to handle any trust-related failure.
    """
    def __init__(self, message: str = "", *, details: dict | None = None):
        self.details: dict = details or {}
        super().__init__(message)


# --- Protocol-layer exceptions (formerly under eatp.exceptions) ---

class ProtocolError(TrustError):
    """Base for EATP protocol errors."""
    pass

class AuthorityNotFoundError(ProtocolError): ...
class AuthorityInactiveError(ProtocolError): ...
class TrustChainNotFoundError(ProtocolError): ...
class InvalidTrustChainError(ProtocolError): ...
class CapabilityNotFoundError(ProtocolError): ...
class InvalidSignatureError(ProtocolError): ...
class VerificationFailedError(ProtocolError): ...
class AgentAlreadyEstablishedError(ProtocolError): ...
class TrustStoreError(ProtocolError): ...           # Chain store errors
class TrustChainInvalidError(TrustStoreError): ...
class TrustStoreDatabaseError(TrustStoreError): ...
class DelegationError(ProtocolError): ...
class DelegationCycleError(DelegationError): ...
class DelegationExpiredError(DelegationError): ...
class HookError(ProtocolError): ...
class HookTimeoutError(HookError): ...
class ProximityError(ProtocolError): ...
class BehavioralScoringError(ProtocolError): ...
class KMSConnectionError(ProtocolError): ...
class RevocationError(ProtocolError): ...
class PathTraversalError(ProtocolError): ...
class PostureStoreError(ProtocolError): ...

# Protocol-level constraint violation
class ProtocolConstraintViolationError(ProtocolError):
    """Raised when an action violates protocol-level trust constraints."""
    pass


# --- Platform-layer exceptions (formerly under trustplane.exceptions) ---

class TrustPlaneError(TrustError):
    """Base for trust-plane platform errors."""
    pass

class TrustPlaneStoreError(TrustPlaneError): ...
class RecordNotFoundError(TrustPlaneStoreError, KeyError): ...
class SchemaTooNewError(TrustPlaneStoreError): ...
class SchemaMigrationError(TrustPlaneStoreError): ...
class StoreConnectionError(TrustPlaneStoreError): ...
class StoreQueryError(TrustPlaneStoreError): ...
class StoreTransactionError(TrustPlaneStoreError): ...
class TrustDecryptionError(TrustPlaneError): ...
class KeyManagerError(TrustPlaneError): ...
class KeyNotFoundError(KeyManagerError): ...
class KeyExpiredError(KeyManagerError): ...
class SigningError(KeyManagerError): ...
class VerificationError(KeyManagerError): ...
class IdentityError(TrustPlaneError): ...
class TokenVerificationError(IdentityError): ...
class JWKSError(IdentityError): ...
class RBACError(TrustPlaneError): ...

# Platform-level constraint violation
class ConstraintViolationError(TrustPlaneError):
    """Raised when an action violates the constraint envelope."""
    pass

class BudgetExhaustedError(ConstraintViolationError): ...
class ArchiveError(TrustPlaneError): ...
class TLSSyslogError(TrustPlaneError): ...
class LockTimeoutError(TrustPlaneError, TimeoutError): ...
```

### 5.3 Collision Resolution: ConstraintViolationError

Both EATP and trust-plane define `ConstraintViolationError`. They have different signatures and different base classes. The solution:

- EATP's becomes `ProtocolConstraintViolationError` (under `ProtocolError`)
- Trust-plane's keeps the name `ConstraintViolationError` (under `TrustPlaneError`) because it is the user-facing one (used in `TrustProject.check()`, CLI, dashboard)

The shim layer maps old imports to the new names. See Section 7.

### 5.4 Key Property

`TrustError` is now the single root. Users can:

- `except TrustError` to catch everything
- `except ProtocolError` to catch only protocol-level failures
- `except TrustPlaneError` to catch only platform-level failures
- `except TrustStoreError` to catch chain store failures
- `except TrustPlaneStoreError` to catch record store failures

---

## 6. Store Coexistence Detail

### 6.1 Chain Store (protocol layer)

```
kailash.trust.protocol.chain_store
    __init__.py          # TrustStore ABC, TransactionContext, _chain_has_missing_reasoning
    memory.py            # InMemoryTrustStore
    filesystem.py        # FilesystemStore (JSON files, file_lock, validate_id)
    sqlite.py            # SqliteTrustStore
```

Accessed via:

```python
from kailash.trust.protocol.chain_store import TrustStore
from kailash.trust.protocol.chain_store.memory import InMemoryTrustStore
from kailash.trust.protocol.chain_store.sqlite import SqliteTrustStore
```

### 6.2 Record Store (platform layer)

```
kailash.trust.plane.record_store
    __init__.py          # TrustPlaneStore Protocol
    filesystem.py        # FileSystemTrustPlaneStore
    sqlite.py            # SqliteTrustPlaneStore
    postgres.py          # PostgresTrustPlaneStore
```

Accessed via:

```python
from kailash.trust.plane.record_store import TrustPlaneStore
from kailash.trust.plane.record_store.sqlite import SqliteTrustPlaneStore
from kailash.trust.plane.record_store.postgres import PostgresTrustPlaneStore
```

### 6.3 Why not merge them

- `TrustStore` is async; `TrustPlaneStore` is sync.
- `TrustStore` stores `TrustLineageChain` objects; `TrustPlaneStore` stores 7 different record types.
- `TrustStore` backends are {memory, filesystem, sqlite}; `TrustPlaneStore` backends are {filesystem, sqlite, postgres}.
- Merging would require either making `TrustPlaneStore` async (breaking all trust-plane code) or making `TrustStore` sync (breaking all EATP code). Neither is acceptable.

---

## 7. Backward-Compatible Import Shims

### 7.1 `packages/eatp/src/eatp/__init__.py` (shim)

```python
"""EATP compatibility shim — use kailash.trust.protocol instead."""
import warnings
warnings.warn(
    "Importing from 'eatp' is deprecated. Use 'kailash.trust.protocol' instead. "
    "The 'eatp' package will be removed in a future version.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export everything from the new location
from kailash.trust.protocol.chain import *
from kailash.trust.protocol.operations import *
from kailash.trust.protocol.signing.crypto import *
from kailash.trust.protocol.chain_store import TrustStore
from kailash.trust.protocol.chain_store.memory import InMemoryTrustStore
from kailash.trust.protocol.authority import *
from kailash.trust.protocol.posture.postures import *
from kailash.trust.protocol.reasoning.traces import *
from kailash.trust.protocol.constraints.budget_tracker import *
from kailash.trust.protocol.constraints.budget_store import *
from kailash.trust.protocol.hooks import *
from kailash.trust.protocol.roles import *
from kailash.trust.protocol.vocabulary import *
from kailash.trust.exceptions import (
    TrustError,
    TrustChainNotFoundError,
    ProtocolConstraintViolationError as ConstraintViolationError,
    # ... all other EATP exceptions
)

__version__ = "0.3.0"  # Shim version
```

Each EATP subpackage (`eatp.store`, `eatp.enforce`, etc.) gets its own shim `__init__.py` that re-exports from the new location.

### 7.2 `packages/trust-plane/src/trustplane/__init__.py` (shim)

```python
"""TrustPlane compatibility shim — use kailash.trust.plane instead."""
import warnings
warnings.warn(
    "Importing from 'trustplane' is deprecated. Use 'kailash.trust.plane' instead. "
    "The 'trustplane' package will be removed in a future version.",
    DeprecationWarning,
    stacklevel=2,
)

from kailash.trust.plane.project import TrustProject
from kailash.trust.plane.record_store import TrustPlaneStore
from kailash.trust.plane.record_store.filesystem import FileSystemTrustPlaneStore
from kailash.trust.plane.record_store.sqlite import SqliteTrustPlaneStore
from kailash.trust.plane.models import *
from kailash.trust.exceptions import (
    TrustPlaneError,
    TrustPlaneStoreError,
    # ... all trust-plane exceptions
)

__version__ = "0.3.0"  # Shim version
```

### 7.3 Shim Module Strategy

Every current submodule path must continue to work. This requires per-submodule shims:

| Old import                | Shim in                                               | Maps to                                              |
| ------------------------- | ----------------------------------------------------- | ---------------------------------------------------- |
| `eatp.chain`              | `packages/eatp/src/eatp/chain.py`                     | `kailash.trust.protocol.chain`                       |
| `eatp.crypto`             | `packages/eatp/src/eatp/crypto.py`                    | `kailash.trust.protocol.signing.crypto`              |
| `eatp.store.memory`       | `packages/eatp/src/eatp/store/memory.py`              | `kailash.trust.protocol.chain_store.memory`          |
| `eatp.enforce.strict`     | `packages/eatp/src/eatp/enforce/strict.py`            | `kailash.trust.protocol.enforce.strict`              |
| `eatp.postures`           | `packages/eatp/src/eatp/postures.py`                  | `kailash.trust.protocol.posture.postures`            |
| `eatp.reasoning`          | `packages/eatp/src/eatp/reasoning.py`                 | `kailash.trust.protocol.reasoning.traces`            |
| `trustplane.project`      | `packages/trust-plane/src/trustplane/project.py`      | `kailash.trust.plane.project`                        |
| `trustplane.store.sqlite` | `packages/trust-plane/src/trustplane/store/sqlite.py` | `kailash.trust.plane.record_store.sqlite`            |
| `trustplane.models`       | `packages/trust-plane/src/trustplane/models.py`       | `kailash.trust.plane.models`                         |
| `trustplane.exceptions`   | `packages/trust-plane/src/trustplane/exceptions.py`   | `kailash.trust.exceptions` (TrustPlaneError subtree) |

---

## 8. CLI Entry Points

### 8.1 Current Entry Points

| Package     | CLI command      | Entry point                            |
| ----------- | ---------------- | -------------------------------------- |
| EATP        | `eatp`           | `eatp.cli.commands:cli` (Click)        |
| Trust-plane | `attest`         | `trustplane.cli:main` (Click)          |
| Trust-plane | `trustplane-mcp` | `trustplane.mcp_server:main` (FastMCP) |

### 8.2 Target Entry Points

| CLI command      | Entry point                               | Notes                   |
| ---------------- | ----------------------------------------- | ----------------------- |
| `kailash-trust`  | `kailash.trust.plane.cli.commands:main`   | New unified CLI         |
| `attest`         | `kailash.trust.plane.cli.commands:main`   | Backward-compat alias   |
| `eatp`           | `kailash.trust.protocol.cli.commands:cli` | Backward-compat alias   |
| `trustplane-mcp` | `kailash.trust.protocol.mcp.server:main`  | MCP stays with protocol |

The `attest` command is preserved as an alias because it has real users. The `eatp` CLI is preserved for protocol-only operations (chain inspection, key generation). Both can eventually be unified under `kailash-trust` with subcommand groups.

---

## 9. Dependency Direction Enforcement

### 9.1 Import Rules

```
kailash.trust.protocol.**  MAY import from  kailash.trust.exceptions
kailash.trust.protocol.**  MUST NOT import from  kailash.trust.plane.**

kailash.trust.plane.**  MAY import from  kailash.trust.exceptions
kailash.trust.plane.**  MAY import from  kailash.trust.protocol.**
kailash.trust.plane.**  MUST NOT import from  kailash.trust.plane.cli.**  (CLI depends on plane, not reverse)
```

### 9.2 Enforcement Mechanism

A CI check (or a lint rule) scans imports:

```python
# tests/test_import_boundaries.py
def test_protocol_does_not_import_plane():
    """Protocol layer must not import from plane layer."""
    import ast, pathlib
    protocol_dir = pathlib.Path("src/kailash/trust/protocol")
    for py_file in protocol_dir.rglob("*.py"):
        tree = ast.parse(py_file.read_text())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = getattr(node, "module", "") or ""
                for alias in getattr(node, "names", []):
                    full = f"{module}.{alias.name}" if module else alias.name
                    assert "kailash.trust.plane" not in full, (
                        f"{py_file}: protocol layer imports plane layer ({full})"
                    )
```

---

## 10. Risk Register

| #   | Risk                                                                  | Likelihood | Impact      | Mitigation                                                                                                                                                                                                    |
| --- | --------------------------------------------------------------------- | ---------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| R1  | Circular import between protocol and plane during migration           | HIGH       | CRITICAL    | Enforce dependency direction from day 1 of migration. Test with `test_import_boundaries.py`.                                                                                                                  |
| R2  | Shim packages break when old submodule paths change                   | HIGH       | MAJOR       | Every submodule gets its own shim file. Test every old import path in a dedicated test file.                                                                                                                  |
| R3  | Trust-plane `project.py` imports from 8 different `eatp.*` paths      | HIGH       | MAJOR       | `project.py` is the largest single-file migration risk. Map all 8 import blocks before moving. Must rewrite to `kailash.trust.protocol.*` paths.                                                              |
| R4  | `ConstraintEnvelope` name collision confuses developers               | MEDIUM     | SIGNIFICANT | Protocol uses `ConstraintEnvelope` from `chain.py` (generic). Plane uses `ConstraintEnvelope` from `models.py` (5-dimension). Both are valid in their context. Document the distinction in module docstrings. |
| R5  | `ConstraintViolationError` name collision in exception hierarchy      | HIGH       | MAJOR       | Rename EATP's to `ProtocolConstraintViolationError`. Shim maps old name.                                                                                                                                      |
| R6  | Third-party consumers of `pip install eatp` break silently            | MEDIUM     | CRITICAL    | Shim package emits DeprecationWarning. PyPI page updated with migration guide. Shim version bumped to 0.3.0.                                                                                                  |
| R7  | `_locking.py` security patterns broken during move                    | LOW        | CRITICAL    | Security-reviewer audit required. All 12 security patterns from trust-plane CLAUDE.md must pass red team after move.                                                                                          |
| R8  | Two `key_manager` systems with same concept name confuse contributors | MEDIUM     | SIGNIFICANT | Different layer, different subpackage (`protocol.key_management` vs `plane.key_management`). Docstrings explain the distinction.                                                                              |
| R9  | Test migration misses test files with implicit relative imports       | HIGH       | MAJOR       | Grep all test files for `from eatp` and `from trustplane` before declaring migration complete.                                                                                                                |
| R10 | CLI entry points break in `pyproject.toml`                            | MEDIUM     | MAJOR       | Maintain backward-compatible entry points. Test both old and new CLI commands in CI.                                                                                                                          |

---

## 11. Decision Points Requiring Stakeholder Input

1. **Version strategy**: Is this kailash 2.0.0 (semver major) or 1.x additive? The namespace architecture supports both, but the migration approach differs. With 2.0.0, we can remove old paths immediately. With 1.x, we carry shims indefinitely.

2. **`pynacl` as core dependency vs extra**: Should `pip install kailash` include PyNaCl (adds ~2MB, C extension build), or should it be `pip install kailash[trust]`? If it is an extra, `from kailash.trust.protocol.signing import generate_keypair` would raise ImportError without the extra.

3. **EATP CLI preservation**: Should `eatp` CLI command be preserved as a separate entry point, or unified into `kailash-trust eatp <subcommand>`? The current `eatp` CLI has limited usage (quickstart, chain inspection).

4. **`trustplane.conformance` location**: The conformance suite tests whether an EATP _implementation_ is spec-compliant. It currently lives in trust-plane but tests protocol behavior. Should it move to `protocol.conformance/` or stay in `plane.conformance/`? Argument for plane: it uses `safe_read_json` from `_locking.py`. Argument for protocol: it validates protocol compliance.

5. **`TrustPlaneKeyManager` unification timeline**: The two key management interfaces could theoretically be unified in a future version. Should this architecture document establish a path toward unification, or explicitly declare them permanently separate?

---

## 12. Cross-Reference Audit

### Documents affected by this change

- `packages/eatp/pyproject.toml` -- entry points, dependencies
- `packages/trust-plane/pyproject.toml` -- entry points, dependencies
- `pyproject.toml` (root kailash) -- new `kailash.trust.*` namespace, new dependencies
- `.claude/rules/trust-plane-security.md` -- path references change
- `.claude/rules/eatp.md` -- import paths change
- `packages/trust-plane/CLAUDE.md` -- all import examples change
- `workspaces/eatp-merge/decisions.yml` -- update with implementation decisions
- `packages/kailash-kaizen/` -- drops `eatp` dependency, rewrites imports
- Any consumer of `from eatp import ...` or `from trustplane import ...`

### Inconsistencies found

- The brief proposed `kailash.trust.store` as a single namespace, but there are two fundamentally different store abstractions that cannot share a name.
- The brief proposed `kailash.trust.verification` but verification is a method on `TrustOperations`, not a standalone module. There is no `verification.py` in either package.
- The brief did not account for the 18 EATP subpackages (a2a, cli, constraints, enforce, esa, export, governance, interop, knowledge, mcp, messaging, migrations, operations, orchestration, registry, revocation, store, templates).
- The brief did not address the `ConstraintEnvelope` name collision (both packages define it with different semantics).

---

## 13. Migration Sequence (Implementation Order)

### Phase 1: Foundation (no code moves yet)

1. Create `src/kailash/trust/__init__.py` (empty)
2. Create `src/kailash/trust/exceptions.py` (unified hierarchy)
3. Create `src/kailash/trust/_compat.py`
4. Write `test_import_boundaries.py`

### Phase 2: Protocol layer (move EATP code)

1. Move `eatp/chain.py` to `protocol/chain.py` (zero dependencies on plane)
2. Move `eatp/crypto.py` to `protocol/signing/crypto.py`
3. Move `eatp/reasoning.py` to `protocol/reasoning/traces.py`
4. Move `eatp/postures.py` to `protocol/posture/postures.py`
5. Move remaining root modules (authority, operations, roles, etc.)
6. Move subpackages (constraints, enforce, store, etc.)
7. Update all internal imports within protocol layer
8. Create shim files in `packages/eatp/`
9. Run all EATP tests against new paths

### Phase 3: Platform layer (move trust-plane code)

1. Move `trustplane/exceptions.py` content into unified `exceptions.py` (already done in Phase 1)
2. Move `trustplane/_locking.py` to `plane/_locking.py`
3. Move `trustplane/models.py` to `plane/models.py`
4. Move `trustplane/project.py` to `plane/project.py` (rewrite all `from eatp` imports)
5. Move remaining modules
6. Move subpackages (store, key_managers, integration, etc.)
7. Update all internal imports within plane layer
8. Create shim files in `packages/trust-plane/`
9. Run all trust-plane tests against new paths

### Phase 4: Consumer updates

1. Update kailash-kaizen imports
2. Remove `eatp` from kailash-kaizen dependencies
3. Update any other consumers (astra, arbor)

### Phase 5: Red team

1. Re-run all 12 trust-plane security patterns
2. Verify all 1499 trust-plane tests pass
3. Verify all EATP tests pass
4. Verify shim imports work
5. Verify CLI entry points work

---

## Appendix A: Complete File Count

| Directory                                  | Files    | Source                                               |
| ------------------------------------------ | -------- | ---------------------------------------------------- |
| `kailash/trust/`                           | 3        | New (init, exceptions, compat)                       |
| `kailash/trust/protocol/`                  | 17       | EATP root modules                                    |
| `kailash/trust/protocol/signing/`          | 7        | EATP crypto + related                                |
| `kailash/trust/protocol/posture/`          | 4        | EATP postures                                        |
| `kailash/trust/protocol/reasoning/`        | 2        | EATP reasoning                                       |
| `kailash/trust/protocol/constraints/`      | 9        | EATP constraints                                     |
| `kailash/trust/protocol/chain_store/`      | 4        | EATP store                                           |
| `kailash/trust/protocol/enforce/`          | 7        | EATP enforce                                         |
| `kailash/trust/protocol/key_management/`   | 2        | EATP key_manager                                     |
| `kailash/trust/protocol/revocation/`       | 3        | EATP revocation                                      |
| `kailash/trust/protocol/interop/`          | 6        | EATP interop                                         |
| `kailash/trust/protocol/a2a/`              | 7        | EATP a2a                                             |
| `kailash/trust/protocol/messaging/`        | 7        | EATP messaging                                       |
| `kailash/trust/protocol/governance/`       | 6        | EATP governance                                      |
| `kailash/trust/protocol/registry/`         | 3        | EATP registry                                        |
| `kailash/trust/protocol/orchestration/`    | 7        | EATP orchestration                                   |
| `kailash/trust/protocol/esa/`              | 7        | EATP esa                                             |
| `kailash/trust/protocol/knowledge/`        | 4        | EATP knowledge                                       |
| `kailash/trust/protocol/export/`           | 3        | EATP export                                          |
| `kailash/trust/protocol/agents/`           | 4        | EATP agent wrappers                                  |
| `kailash/trust/protocol/templates/`        | 1        | EATP templates                                       |
| `kailash/trust/protocol/migrations/`       | 2        | EATP migrations                                      |
| `kailash/trust/protocol/mcp/`              | 2        | EATP MCP                                             |
| `kailash/trust/protocol/cli/`              | 3        | EATP CLI                                             |
| `kailash/trust/plane/`                     | 20       | Trust-plane root modules                             |
| `kailash/trust/plane/encryption/`          | 2        | Trust-plane crypto_utils                             |
| `kailash/trust/plane/key_management/`      | 5        | Trust-plane key_managers                             |
| `kailash/trust/plane/record_store/`        | 4        | Trust-plane store                                    |
| `kailash/trust/plane/conformance/`         | 1        | Trust-plane conformance                              |
| `kailash/trust/plane/integration/`         | 5        | Trust-plane integrations                             |
| `kailash/trust/plane/templates/`           | 1        | Trust-plane templates                                |
| `kailash/trust/plane/dashboard_templates/` | 1        | Trust-plane dashboard HTML                           |
| `kailash/trust/plane/cli/`                 | 2        | Trust-plane CLI                                      |
| **TOTAL**                                  | **~150** | 95 source + ~55 `__init__.py` / new structural files |

---

## Appendix B: Import Path Migration Table

This is the authoritative mapping for every importable path in both packages.

### EATP Root Modules

| Old path                    | New path                                           |
| --------------------------- | -------------------------------------------------- |
| `eatp`                      | `kailash.trust` (top-level re-exports)             |
| `eatp.chain`                | `kailash.trust.protocol.chain`                     |
| `eatp.authority`            | `kailash.trust.protocol.authority`                 |
| `eatp.operations`           | `kailash.trust.protocol.operations`                |
| `eatp.crypto`               | `kailash.trust.protocol.signing.crypto`            |
| `eatp.roles`                | `kailash.trust.protocol.roles`                     |
| `eatp.vocabulary`           | `kailash.trust.protocol.vocabulary`                |
| `eatp.hooks`                | `kailash.trust.protocol.hooks`                     |
| `eatp.execution_context`    | `kailash.trust.protocol.execution_context`         |
| `eatp.scoring`              | `kailash.trust.protocol.scoring`                   |
| `eatp.metrics`              | `kailash.trust.protocol.metrics`                   |
| `eatp.security`             | `kailash.trust.protocol.security`                  |
| `eatp.cache`                | `kailash.trust.protocol.cache`                     |
| `eatp.circuit_breaker`      | `kailash.trust.protocol.circuit_breaker`           |
| `eatp.graph_validator`      | `kailash.trust.protocol.graph_validator`           |
| `eatp.constraint_validator` | `kailash.trust.protocol.constraint_validator`      |
| `eatp.audit_service`        | `kailash.trust.protocol.audit_service`             |
| `eatp.audit_store`          | `kailash.trust.protocol.audit_store`               |
| `eatp.postures`             | `kailash.trust.protocol.posture.postures`          |
| `eatp.posture_store`        | `kailash.trust.protocol.posture.posture_store`     |
| `eatp.posture_agent`        | `kailash.trust.protocol.agents.posture_agent`      |
| `eatp.reasoning`            | `kailash.trust.protocol.reasoning.traces`          |
| `eatp.key_manager`          | `kailash.trust.protocol.key_management.manager`    |
| `eatp.trusted_agent`        | `kailash.trust.protocol.agents.trusted_agent`      |
| `eatp.pseudo_agent`         | `kailash.trust.protocol.agents.pseudo_agent`       |
| `eatp.multi_sig`            | `kailash.trust.protocol.signing.multi_sig`         |
| `eatp.merkle`               | `kailash.trust.protocol.signing.merkle`            |
| `eatp.timestamping`         | `kailash.trust.protocol.signing.timestamping`      |
| `eatp.rotation`             | `kailash.trust.protocol.signing.rotation`          |
| `eatp.crl`                  | `kailash.trust.protocol.signing.crl`               |
| `eatp.exceptions`           | `kailash.trust.exceptions` (ProtocolError subtree) |

### EATP Subpackages

| Old path                            | New path                                              |
| ----------------------------------- | ----------------------------------------------------- |
| `eatp.store`                        | `kailash.trust.protocol.chain_store`                  |
| `eatp.store.memory`                 | `kailash.trust.protocol.chain_store.memory`           |
| `eatp.store.filesystem`             | `kailash.trust.protocol.chain_store.filesystem`       |
| `eatp.store.sqlite`                 | `kailash.trust.protocol.chain_store.sqlite`           |
| `eatp.enforce`                      | `kailash.trust.protocol.enforce`                      |
| `eatp.enforce.strict`               | `kailash.trust.protocol.enforce.strict`               |
| `eatp.enforce.shadow`               | `kailash.trust.protocol.enforce.shadow`               |
| `eatp.enforce.challenge`            | `kailash.trust.protocol.enforce.challenge`            |
| `eatp.enforce.decorators`           | `kailash.trust.protocol.enforce.decorators`           |
| `eatp.enforce.proximity`            | `kailash.trust.protocol.enforce.proximity`            |
| `eatp.enforce.selective_disclosure` | `kailash.trust.protocol.enforce.selective_disclosure` |
| `eatp.constraints`                  | `kailash.trust.protocol.constraints`                  |
| `eatp.constraints.dimension`        | `kailash.trust.protocol.constraints.dimension`        |
| `eatp.constraints.builtin`          | `kailash.trust.protocol.constraints.builtin`          |
| `eatp.constraints.evaluator`        | `kailash.trust.protocol.constraints.evaluator`        |
| `eatp.constraints.commerce`         | `kailash.trust.protocol.constraints.commerce`         |
| `eatp.constraints.spend_tracker`    | `kailash.trust.protocol.constraints.spend_tracker`    |
| `eatp.constraints.budget_tracker`   | `kailash.trust.protocol.constraints.budget_tracker`   |
| `eatp.constraints.budget_store`     | `kailash.trust.protocol.constraints.budget_store`     |
| `eatp.interop`                      | `kailash.trust.protocol.interop`                      |
| `eatp.interop.w3c_vc`               | `kailash.trust.protocol.interop.w3c_vc`               |
| `eatp.interop.did`                  | `kailash.trust.protocol.interop.did`                  |
| `eatp.interop.ucan`                 | `kailash.trust.protocol.interop.ucan`                 |
| `eatp.interop.sd_jwt`               | `kailash.trust.protocol.interop.sd_jwt`               |
| `eatp.interop.biscuit`              | `kailash.trust.protocol.interop.biscuit`              |
| `eatp.a2a`                          | `kailash.trust.protocol.a2a`                          |
| `eatp.messaging`                    | `kailash.trust.protocol.messaging`                    |
| `eatp.governance`                   | `kailash.trust.protocol.governance`                   |
| `eatp.registry`                     | `kailash.trust.protocol.registry`                     |
| `eatp.orchestration`                | `kailash.trust.protocol.orchestration`                |
| `eatp.orchestration.integration`    | `kailash.trust.protocol.orchestration.integration`    |
| `eatp.esa`                          | `kailash.trust.protocol.esa`                          |
| `eatp.knowledge`                    | `kailash.trust.protocol.knowledge`                    |
| `eatp.export`                       | `kailash.trust.protocol.export`                       |
| `eatp.revocation`                   | `kailash.trust.protocol.revocation`                   |
| `eatp.templates`                    | `kailash.trust.protocol.templates`                    |
| `eatp.migrations`                   | `kailash.trust.protocol.migrations`                   |
| `eatp.mcp`                          | `kailash.trust.protocol.mcp`                          |
| `eatp.cli`                          | `kailash.trust.protocol.cli`                          |

### Trust-Plane Modules

| Old path                                 | New path                                             |
| ---------------------------------------- | ---------------------------------------------------- |
| `trustplane`                             | `kailash.trust.plane`                                |
| `trustplane.project`                     | `kailash.trust.plane.project`                        |
| `trustplane.session`                     | `kailash.trust.plane.session`                        |
| `trustplane.models`                      | `kailash.trust.plane.models`                         |
| `trustplane.config`                      | `kailash.trust.plane.config`                         |
| `trustplane.holds`                       | `kailash.trust.plane.holds`                          |
| `trustplane.delegation`                  | `kailash.trust.plane.delegation`                     |
| `trustplane.compliance`                  | `kailash.trust.plane.compliance`                     |
| `trustplane.reports`                     | `kailash.trust.plane.reports`                        |
| `trustplane.diagnostics`                 | `kailash.trust.plane.diagnostics`                    |
| `trustplane.shadow`                      | `kailash.trust.plane.shadow`                         |
| `trustplane.shadow_store`                | `kailash.trust.plane.shadow_store`                   |
| `trustplane.mirror`                      | `kailash.trust.plane.mirror`                         |
| `trustplane.proxy`                       | `kailash.trust.plane.proxy`                          |
| `trustplane.identity`                    | `kailash.trust.plane.identity`                       |
| `trustplane.rbac`                        | `kailash.trust.plane.rbac`                           |
| `trustplane.archive`                     | `kailash.trust.plane.archive`                        |
| `trustplane.bundle`                      | `kailash.trust.plane.bundle`                         |
| `trustplane.siem`                        | `kailash.trust.plane.siem`                           |
| `trustplane.dashboard`                   | `kailash.trust.plane.dashboard`                      |
| `trustplane.migrate`                     | `kailash.trust.plane.migrate`                        |
| `trustplane.pathutils`                   | `kailash.trust.plane.pathutils`                      |
| `trustplane._locking`                    | `kailash.trust.plane._locking`                       |
| `trustplane.crypto_utils`                | `kailash.trust.plane.encryption.crypto_utils`        |
| `trustplane.exceptions`                  | `kailash.trust.exceptions` (TrustPlaneError subtree) |
| `trustplane.key_manager`                 | `kailash.trust.plane.key_management.manager`         |
| `trustplane.key_managers.aws_kms`        | `kailash.trust.plane.key_management.aws_kms`         |
| `trustplane.key_managers.azure_keyvault` | `kailash.trust.plane.key_management.azure_keyvault`  |
| `trustplane.key_managers.vault`          | `kailash.trust.plane.key_management.vault`           |
| `trustplane.store`                       | `kailash.trust.plane.record_store`                   |
| `trustplane.store.filesystem`            | `kailash.trust.plane.record_store.filesystem`        |
| `trustplane.store.sqlite`                | `kailash.trust.plane.record_store.sqlite`            |
| `trustplane.store.postgres`              | `kailash.trust.plane.record_store.postgres`          |
| `trustplane.conformance`                 | `kailash.trust.plane.conformance`                    |
| `trustplane.integration`                 | `kailash.trust.plane.integration`                    |
| `trustplane.integration.claude_code`     | `kailash.trust.plane.integration.claude_code`        |
| `trustplane.integration.cursor`          | `kailash.trust.plane.integration.cursor`             |
| `trustplane.templates`                   | `kailash.trust.plane.templates`                      |
| `trustplane.dashboard_templates`         | `kailash.trust.plane.dashboard_templates`            |
| `trustplane.cli`                         | `kailash.trust.plane.cli.commands`                   |
| `trustplane.mcp_server`                  | `kailash.trust.protocol.mcp.server`                  |
