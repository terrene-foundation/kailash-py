# Reference extraction — kailash-rs Delegate spine (for #1035 Python OSS mirror)

**Date:** 2026-05-21
**Cross-repo authorization:** `journal/0001-cross-repo-authorization-kailash-rs-check.md`
**Scope:** read-only. No edits, no commits, no PRs against `terrene-foundation/kailash-rs` (remote: `esperie-enterprise/kailash-rs`).
**Sources cited verbatim with absolute paths under `/Users/esperie/repos/loom/kailash-rs/`.**

---

## Top-line LOC inventory

The six lib.rs files are crate-root re-export shells (~692 LOC total); the load-bearing implementation lives in submodules. Real per-crate LOC:

| Crate                          | Total LOC (src/) | Lib.rs | Submodules                                                                                                                                    |
| ------------------------------ | ---------------- | ------ | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `kailash-delegate-types`       | 1,446            | 322    | composition (204) · envelope (330) · role (202) · identity (126) · directory (62) · intent (66) · memory (48) · message (54) · lifecycle (32) |
| `kailash-delegate-runtime`     | 6,473            | 145    | delegate (1,748) · composition (1,065) · posture (978) · memory (787) · lifecycle (684) · intent_role (612) · message (454)                   |
| `kailash-delegate-trust`       | 1,664            | 58     | grant (742) · cascade (530) · envelope (178) · error (81) · access (75)                                                                       |
| `kailash-delegate-dispatch`    | 1,276            | 83     | connector (267) · dispatch (265) · auth (264) · revocation (138) · receipt (135) · token (124)                                                |
| `kailash-delegate-audit`       | 1,238            | 34     | anchor (718) · chain (486)                                                                                                                    |
| `kailash-delegate-conformance` | 1,099            | 50     | vectors/mod (575) · receipt (349) · vectors/catalog (125)                                                                                     |
| **TOTAL**                      | **13,196**       |        |                                                                                                                                               |

The Rust delegate spine is feature-complete through M8-02 (E2E regression). Most mature: `kailash-delegate-runtime` and `kailash-delegate-trust` — every other crate exists in service of these two.

---

## Per-crate report

### 1. `kailash-delegate-types` — substrate-composition wrappers + identity/role/lifecycle

`<rs>/crates/kailash-delegate-types/src/lib.rs:1-29` declares the §249 "compose, do not re-derive" constraint. **The dependency edge on `eatp` + `kailash-governance` IS the structural composition gate**: every substrate primitive is held verbatim inside a wrapper, never re-skinned as a parallel serde-only type.

#### Public surface (re-exports at `lib.rs:41-58`)

```
pub use composition::{AuditChainRecord, GenesisRecord, PostureState, Principal};
pub use directory::PrincipalDirectory;
pub use eatp::types::PostureLevel;  // D1: re-export of frozen substrate enum
pub use envelope::{DelegateConstraintEnvelope, DelegateConstraintEnvelopeWire};
pub use identity::{DelegateId, DelegateIdentity, DelegateIdentityMetadata};
pub use intent::{InboundIntentEnvelope, IntentSource};
pub use lifecycle::LifecycleState;
pub use memory::{MemoryScope, MemoryStoreHandle};
pub use message::DelegateMessage;
pub use role::{CapabilitySet, Role, RoleBinding, RoleId, RoleLifecycleState, RoleScope, VoiceAttrs};
```

#### Composition wrappers (`composition.rs`)

All four "compose, don't re-derive" anchors live here. Every wrapper holds the substrate value in a `pub` field (or accessor) — deleting it is a compile error, surfacing substrate drift loudly:

- **`GenesisRecord`** (`composition.rs:51-88`) wraps `eatp::chain::GenesisBlock` + adds `spec_version: String` + `capabilities: Vec<String>`. `#[non_exhaustive]`. Signing remains the substrate's responsibility (`CareChain::sign()`).
- **`PostureState`** (`composition.rs:105-135`) composes BOTH `PostureLevel` (frozen enum) AND `eatp::posture::PostureSystem` (transition state machine). Deliberately not `Clone`/`Serialize` because `PostureSystem` owns boxed transition hooks; exposed by reference.
- **`AuditChainRecord`** (`composition.rs:147-171`) wraps `eatp::ledger::LedgerEntry` verbatim — the substrate's `prev_entry_hash`/`entry_hash` chain linkage is held as-is.
- **`Principal`** (`composition.rs:187-204`) wraps `eatp::types::AgentId`. Explicit "composes, does not re-skin" doc constraint.

#### F5 type-state — `DelegateConstraintEnvelope` (`envelope.rs:54-145`)

**This is the load-bearing type-state pattern Python must mirror.** The Rust encoding closes four widening hatches that type-state alone is insufficient to close:

```rust
#[derive(Debug, Serialize, Deserialize)]
#[serde(try_from = "DelegateConstraintEnvelopeWire")]
pub struct DelegateConstraintEnvelope {
    /// PRIVATE — closes the `Clone`+field-reconstruct hatch.
    inner: ConstraintEnvelope,
}
```

The four closed hatches (`envelope.rs:1-46`):

1. **`Clone` + field-reconstruct** — closed by NOT deriving `Clone` and keeping `inner` private.
2. **`serde::Deserialize`** — closed by `#[serde(try_from = ...)]`. Every deserialize routes through `DelegateConstraintEnvelopeWire { parent, child }` (`envelope.rs:130-145`), whose `TryFrom` runs the PUBLIC `kailash_governance::validate_tightening` check (parent → child). A wire payload that widens its declared parent fails to deserialize.
3. **`Default`** — closed by NOT deriving `Default`.
4. **`From` / builder** — closed by having NO public `From` impl and NO builder. The ONLY widening constructor is `DelegateConstraintEnvelope::genesis_seed(genesis: &GenesisRecord, envelope: ConstraintEnvelope) -> Self` (`envelope.rs:71-93`) — gated behind a `GenesisRecord`.

`tighten(self, child) -> Result<Self, MonotonicTighteningError>` (`envelope.rs:109-112`) **consumes `self`** — a rejected widening consumes the parent envelope and returns the typed error; the caller cannot recover the parent to retry a widening. There is deliberately no `widen` counterpart.

`proptest! prop_tighten_is_monotone_nonwidening` (`envelope.rs:289-328`) is the regression backstop: for any descending sequence of financial limits, every successive `tighten` succeeds; every reverse step is always rejected.

#### Identity (`identity.rs`)

- **`DelegateId`** (`identity.rs:25-49`) is a `pub struct DelegateId(pub Uuid)`. Opaque UUID newtype. **Deliberately NOT a `(organization_id, role_id, spec_version)` tuple** (A1): keying identity on that triple would re-root the Genesis chain every time any of those moves.
- **`DelegateIdentityMetadata`** (`identity.rs:56-83`) carries the triple as INDEXED metadata, never identity key.
- **`DelegateIdentity`** (`identity.rs:91-126`) carries `sovereign_ref: String` as an **EAGER REQUIRED** field (never `Option`). No `tier` field — tier is a runtime property (portability I1).

#### Role (`role.rs`) — clusters B1/B2/B3/B4

- **`RoleId`** (`role.rs:20-44`): `pub struct RoleId(pub Uuid)`.
- **`RoleLifecycleState`** (`role.rs:50-61`): `Draft | Active | Suspended | Retired`. `#[non_exhaustive]`.
- **`CapabilitySet`** (`role.rs:69-96`): wraps `Vec<eatp::types::Capability>`. **`intersect()` is the INTERSECTION; deliberately no `union()`** — accumulating roles must never widen capability (B1).
- **`RoleScope`** (`role.rs:105-123`): `{ domain: kailash_governance::Address, capabilities: CapabilitySet }`. STRUCT with BOTH axes (B4). Composes the grammar-validated PACT D/T/R `Address` rather than a re-skinned string.
- **`Role`** (`role.rs:126-154`), **`VoiceAttrs`** (`role.rs:160-177`), **`RoleBinding`** (`role.rs:187-201`).

#### Lifecycle (`lifecycle.rs`)

The D3 single linear chain — pure data, no logic here:

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[non_exhaustive]
pub enum LifecycleState {
    Proposed, Instantiated, PostureGraded, Active, Retired, Archived,
}
```

The guard logic lives in `kailash-delegate-runtime/src/lifecycle.rs::LifecycleTransition`.

#### Memory / Message / Intent / Directory (small files)

- **`MemoryScope`** (`memory.rs:18-25`): `Delegate | Role | Task`. `#[non_exhaustive]`.
- **`MemoryStoreHandle`** (`memory.rs:36-48`): `{ role_ref: RoleId, scope: MemoryScope }`. **The store is owned by the role and lives OUTSIDE the Delegate; the Delegate holds only this handle** (C2).
- **`DelegateMessage`** (`message.rs:22-54`): `{ from: Principal, to: Principal, payload: serde_json::Value, envelope_ref: String, audit_ref: String }`. Minimal attested envelope; routing is the sibling Mesh spec.
- **`InboundIntentEnvelope`** (`intent.rs:38-66`): `{ originator: String, source: IntentSource, payload: Value, received_at: DateTime<Utc> }`. Net-new — no substrate equivalent. `IntentSource = Human | Agent | System`.
- **`PrincipalDirectory`** (`directory.rs:21-62`): `BTreeMap<String, DelegateId>` (deterministic for audit-stable iteration). `register()` / `lookup()` / `len()` / `is_empty()`.

---

### 2. `kailash-delegate-trust` — envelope + cascade + grant moments

`<rs>/crates/kailash-delegate-trust/src/lib.rs:1-58` is the trust-gate composition layer. The crate composes substrate from `eatp` and **`kailash-governance` (NOT `kailash-pact`)** — the M1-02 cargo-deny fence enforces this lighter dep.

#### Public surface (`lib.rs:46-58`)

```
pub use access::check_pact_access;
pub use cascade::{CascadeCacheKey, TenantScope, TenantScopedCascade};
pub use envelope::effective_multi_role_envelope;
pub use error::TrustGateError;
pub use grant::{
    GrantAuthorityEnvelope, GrantMoment, GrantMomentBroker, GrantSigner, GrantedAuthority,
};
```

#### TenantScope (`cascade.rs:100-149`) — RATIFIED Option A

Typed 2-variant enum, **NOT** `Option<String>` — "global / unscoped" is the EXPLICIT `Global` variant so a tenant-scoped deployment cannot accidentally seed unscoped:

```rust
pub enum TenantScope { Tenant(String), #[default] Global }
```

#### CascadeCacheKey (`cascade.rs:158-185`)

`{ delegation_id: Uuid, tenant: TenantScope }`. Two cascades sharing a delegation id but differing in tenant scope are distinct keys — this is the structural realization of Option A.

#### TenantScopedCascade (`cascade.rs:196-335`) — the load-bearing cascade primitive

```rust
pub struct TenantScopedCascade {
    chain: DelegationChain,       // composed substrate (private, accessor only)
    tenant: TenantScope,
}
```

**`cascade_child()`** (`cascade.rs:276-313`) is the gold-standard cascade check — fixed fail-closed order across 3 layers:

```rust
pub fn cascade_child(
    &self,
    parent: &DelegationScope,
    child: &DelegationScope,
    parent_env: &ConstraintEnvelope,
    child_env: &ConstraintEnvelope,
    child_tenant: &TenantScope,
) -> Result<(), TrustGateError> {
    // (1) RATIFIED Option A: tenant boundary first, fail-closed.
    if child_tenant != &self.tenant { return Err(TenantIsolation { .. }); }
    // (2) F1 downward-only: substrate DelegationScope::is_subset_of (3 axes only).
    if !child.is_subset_of(parent) { return Err(CascadeWidening { .. }); }
    // (3) F5 envelope tightening across ALL 5 PACT dimensions:
    //     the PUBLIC kailash_governance::validate_tightening.
    kailash_governance::validate_tightening(parent_env, child_env)?;
    Ok(())
}
```

The envelope pair is REQUIRED (not optional) precisely so the F5 layer cannot be bypassed by passing `None`.

**`trace_to_genesis()`** (`cascade.rs:328-334`) — composes the substrate `DelegationChain::trace_to_genesis`. Well-defined because the cascade is a tree (F1: no lateral edges).

#### Grant Moments (`grant.rs:1-742` — 742 LOC, full H1 design)

- **`GrantSigner`** (`grant.rs:99-127`): typed enum: `Human(HumanOrigin) | DelegatedAuthority(GrantedAuthority)`. The `DelegatedAuthority` arm carries a **mandatory** (non-`Option`) back-reference to the granting authority's delegation-chain position.
- **`GrantedAuthority`** (`grant.rs:62-84`): `{ delegation_id: Uuid }` — mandatory by construction (private field, no constructor that omits it).
- **`GrantAuthorityEnvelope`** (`grant.rs:135-178`): bounds a compromised grant key — `{ max_posture: PostureLevel, capability_classes: Vec<Capability>, max_grants_per_period: u32 }`.
- **`GrantMoment`** (`grant.rs:186-198`): `{ grant_id, signer, capability, posture, issued_at }`. Only constructible through `GrantMoment::issue(…)` or `GrantMomentBroker::issue_grant(…)`, which already enforces the H1 amendments fail-closed (authority verified against the CURRENT delegation chain — a revoked authority fails CLOSED).

The crate composes `eatp::human::{HoldQueue, HumanOrigin, PseudoAgent}` verbatim.

---

### 3. `kailash-delegate-runtime` — lifecycle + composition surface + posture

The largest crate (6,473 LOC). Decomposed into ordered shards: R1 lifecycle (M6-01), R2 envelope+cascade (M6-02), R3 posture (M6-03), R4 memory+genesis+composition (M6-04a), M6-05 message-send.

#### Public surface (`lib.rs:122-145`)

```
pub use composition::{CascadeWithPostureError, R2CompositionEngine};
pub use delegate::{verify_genesis, Delegate, GenesisVerificationError, IntentRoleSeam, RehydrationProof};
pub use lifecycle::{is_legal_transition, legal_next, LifecycleError, LifecycleTransition, SpawnError, TransitionError};
pub use memory::{delegate_holds_handle_not_store, MemoryEntry, MemoryRegistry, MemoryResolveError, RepointError, RepointReceipt, RoleMemoryStore};
pub use message::{resolve_disagreement, ConflictResolution, DisagreementOutcome, EnvelopeWinner, MessageSendError, SpecUpgrade, SpecUpgradeError};
pub use posture::{enforce_posture_cap, DowngradeTrigger, PostureAdvanceError, PostureCapError, PostureRatchet, RestrictedProfile};
```

#### R1: Lifecycle state machine (`lifecycle.rs`)

**`legal_next()`** (`lifecycle.rs:91-103`) is the authoritative legal-edge table:

```rust
pub fn legal_next(state: LifecycleState) -> Option<LifecycleState> {
    match state {
        Proposed => Some(Instantiated),
        Instantiated => Some(PostureGraded),
        PostureGraded => Some(Active),
        Active => Some(Retired),
        Retired => Some(Archived),
        Archived => None,
        _ => None,  // non_exhaustive future-state: fail-closed
    }
}
```

**`LifecycleTransition<L: KnowledgeLedger>`** (`lifecycle.rs:207-401`):

- `new(delegate_id, audit: Arc<AuditChainEngine<L>>)` — seeds at `Proposed`.
- `async fn transition(&mut self, to) -> Result<AuditChainRecord, TransitionError>`:
  1. Legality check — illegal edges rejected BEFORE any audit event emitted.
  2. Audit-attest — `audit.record(LedgerContent::Evidence(json!({...})))` is `async`.
  3. Apply — only after audit succeeds. Audit failure leaves state unchanged.
- `async fn spawn_sub_delegate(&self, child_tenant) -> Result<(LifecycleTransition, TenantScopedCascade), SpawnError>` (`lifecycle.rs:359-400`):
  - Only legal when `state == Active` (otherwise `SpawnError::NotActive`).
  - Produces a **CASCADE** (D3): fresh child `DelegationChain` + fresh `TrustKeyPair` + fresh `AuditChainEngine` + fresh `DelegateId`.
  - **C3 ratified:** records ONE `delegate.subdelegate.spawned` evidence event on the **parent's** audit chain (opaque UUIDs only — no envelope/key/identity secret). Parent-chain append failure fails the spawn.

`TransitionError = Illegal(LifecycleError) | Audit(EatpError)`.
`SpawnError = NotActive { parent_state } | Audit(EatpError)`.
`LifecycleError { from, to, expected: Option<LifecycleState> }` — carries the single legal successor.

#### R2: Composition engine (`composition.rs`) — F5 surface

`R2CompositionEngine` (`composition.rs:149-387`) is the runtime composition surface. **Deliberately NO Clone/Default/From/builder** — inherits F5 hatches from `DelegateConstraintEnvelope`:

```rust
pub struct R2CompositionEngine {
    effective: DelegateConstraintEnvelope,  // PRIVATE — F5 type-state
    tenant: TenantScope,                     // Option A
}
```

**The only widening constructor:** `from_genesis(genesis: &GenesisRecord, baseline: ConstraintEnvelope, tenant: TenantScope) -> Self` (`composition.rs:175-184`).

**`tighten_effective(self, child) -> Result<Self, MonotonicTighteningError>`** (`composition.rs:203-210`) — consumes `self` (inherits M2-02's no-recovery shape).

**`cascade_child(&self, cascade, parent_scope, child_scope, child_env, child_tenant) -> Result<(), TrustGateError>`** (`composition.rs:246-267`) routes verbatim through `TenantScopedCascade::cascade_child` — the runtime never re-implements the check.

**`cascade_child_with_posture(...)`** (`composition.rs:308-330`) adds R3's cross-Delegate posture cap as the final fail-closed step on the SAME edge.

**Option A tenant threading:**

- `cache_key(delegation_id: Uuid) -> CascadeCacheKey` (`composition.rs:343-345`)
- `audit_tenant_label() -> Option<&str>` (`composition.rs:355-357`)
- `metric_tenant_label() -> &str` — `"global"` for the explicit unscoped variant (`composition.rs:367-369`).

The proptest `prop_cascade_never_widens_any_of_the_5_pact_dimensions` (`composition.rs:947-1063`) fences ALL 5 PACT dimensions including the subtle empty-set operational widening case.

#### R3: Posture ratchet (`posture.rs`)

Three load-bearing invariants (`posture.rs:38-54`):

1. **advance-only-by-grant** — `PostureRatchet::advance_on_grant(&GrantMoment)` is the ONLY method that raises posture. No `set_posture`, no `raise_to`, no public mutable accessor.
2. **fail-closed-downgrade** — `downgrade_on_violation` drops posture to `Pseudo` floor on envelope-violation or audit-failure. If the audit append recording the downgrade itself fails, posture STILL drops.
3. **child ≤ parent** — `enforce_posture_cap(parent: PostureLevel, child: PostureLevel) -> Result<(), PostureCapError>` (`posture.rs:171-178`).

`DowngradeTrigger = EnvelopeViolation(MonotonicTighteningError) | AuditFailure(EatpError)`.
`PostureAdvanceError = NotAnAdvance { current, grant } | Audit(EatpError)`.

D2: posture is a per-Delegate SCALAR — never a `BTreeMap<CapabilityId, PostureLevel>`. D1: no sixth posture level; `RestrictedProfile` is a NAMED ENVELOPE TEMPLATE.

#### R4: Delegate composition surface (`delegate.rs` — 1,748 LOC)

**`Delegate`** is the 5-factor wire-up: `PrincipalDirectory × TenantScopedCascade × R2CompositionEngine × AuditChainEngine × DispatchEngine/Connector`. Instantiated ONLY from a verified `GenesisRecord`.

**`verify_genesis(genesis: &GenesisRecord, chain_owner: &TrustKeyPair) -> Result<RehydrationProof, GenesisVerificationError>`** (`delegate.rs:222-261`) — fixed fail-closed order:

1. **Unrooted check** — `public_key_hex` MUST decode to 32-byte Ed25519 key.
2. **Owner-key match** — declared owner key MUST equal supplied keypair's public key.
3. **Chain integrity** — `CareChain::new(chain_owner).genesis(block).sign()?.verify_chain()?`.

`GenesisVerificationError = Unrooted { detail } | OwnerKeyMismatch { declared, supplied } | ChainIntegrity(EatpError) | SpecVersionMismatch { proof, metadata }`.

`RehydrationProof { verified_genesis_owner: String, spec_version: String }` — the token `Delegate::instantiate` requires as proof genesis was verified. Mintable ONLY by `verify_genesis`; existence IS the proof.

Posture seeding (M6-04a, floor-only): every M6-04a-built Delegate seeds `PostureRatchet` at `PostureLevel::Pseudo` (L1, minimum autonomy). `Delegate::instantiate` never accepts a caller posture value — escalation at instantiation is structurally unrepresentable.

#### M6-05: Message send + disagreement resolution (`message.rs`)

- **`MessageSendError = EnvelopeExpired { expired_at, now } | Audit(EatpError)`** (`message.rs:81-104`).
- **`ConflictResolution`** (`message.rs:130-137`): ratified 2-variant `StricterEnvelopeWins | EscalateToHuman`. `#[non_exhaustive]` for future arbiter arm; NO arbiter / NO runtime-configurable in v0 (F3).
- **`EnvelopeWinner = First | Second | Equivalent`** (`message.rs:141-153`).
- **`DisagreementOutcome = StricterWins { winner: EnvelopeWinner } | Escalate`** (`message.rs:161-172`).
- **`resolve_disagreement(env_a, env_b)`** composes the PUBLIC `kailash_governance::validate_tightening` — "stricter envelope" is "the envelope that does not widen the other"; never a re-derived comparison.

Spec upgrade (I3): `Delegate::apply_spec_upgrade` composes the M4 audit layer's own `requires_reroot` classification + `reroot_for_major_upgrade`.

---

### 4. `kailash-delegate-dispatch` — Connector trait + idempotent dispatch

`<rs>/crates/kailash-delegate-dispatch/src/lib.rs:1-83` is the connector-facing binding contract. The crate **deliberately does NOT depend on `kaizen-agents` or `kailash-delegate-runtime`** — the M1-02 F3 resolved-graph CI fence enforces this. `-dispatch` stays connector-facing.

#### Public surface (`lib.rs:68-83`)

```
pub use auth::{assert_service_account_distinct, ConnectorAuth, ImpersonationByCloneError, ServiceAccountRef};
pub use connector::{Connector, ConnectorError, OptionalPrimitive};
pub use dispatch::{DispatchDisposition, DispatchEngine, DispatchError, DispatchOutcome, IdempotencyKey};
pub use kailash_delegate_types::Principal;
pub use receipt::{record_read_receipt, record_write_envelope, AttestationError, AttestedReadReceipt, SignedActionEnvelope};
pub use revocation::{RevocationChannel, DEFAULT_TOKEN_TTL};
pub use token::{issue_test_token, OidcClaims, OidcVerifier, TokenError};
```

#### The `Connector` trait — `connector.rs:115-237`

**This is the trait the issue body promises Python must mirror.** Actual signature (verbatim from `connector.rs:115-237`):

```rust
#[async_trait]
pub trait Connector: Send + Sync {
    // Inherent methods every implementor MUST provide:
    fn revocation(&self) -> &RevocationChannel;
    fn ledger(&self) -> &dyn KnowledgeLedger;
    fn verifier(&self) -> &OidcVerifier;

    // Required primitive 1 — SAML/OIDC auth (provided method; trait owns the sequencing):
    async fn authenticate(
        &self,
        bearer_token: &str,
        sovereign: &Principal,
    ) -> Result<Principal, ConnectorError> {
        let service_account = self.verifier().verify_to_principal(bearer_token)?;
        assert_service_account_distinct(&service_account, sovereign)?;  // G1(a) clone check
        Ok(service_account)
    }

    // Required primitive 2 — signed action envelope per write:
    async fn write<F, Fut>(
        &self,
        actor: &Principal,
        action: &str,
        perform_write: F,
    ) -> Result<SignedActionEnvelope, ConnectorError>
    where F: FnOnce() -> Fut + Send,
          Fut: Future<Output = Result<(), ConnectorError>> + Send,
    {
        if self.revocation().is_revoked(actor) { return Err(Revoked(...)); }
        perform_write().await?;
        let envelope = record_write_envelope(self.ledger(), actor, action).await?;
        Ok(envelope)
    }

    // Required primitive 3 — EATP-attested receipt per read:
    async fn read<T, F, Fut>(
        &self,
        reader: &Principal,
        resource: &str,
        perform_read: F,
    ) -> Result<(T, AttestedReadReceipt), ConnectorError>
    where T: Send,
          F: FnOnce() -> Fut + Send,
          Fut: Future<Output = Result<T, ConnectorError>> + Send,
    {
        if self.revocation().is_revoked(reader) { return Err(Revoked(...)); }
        let value = perform_read().await?;
        let receipt = record_read_receipt(self.ledger(), reader, resource).await?;
        Ok((value, receipt))
    }

    fn optional_primitives(&self) -> &[OptionalPrimitive] { &[] }
}
```

**Note the divergence from the #988 issue body's `pull / normalize / capabilities` sketch.** The shipped trait is `authenticate / write / read / revocation` — the §10 4-required-primitives outline (SAML/OIDC auth, signed action envelope per write, EATP-attested receipt per read, instant revocation channel). The original `pull / normalize / capabilities` proposal in #988 was the channel-data-fetch shape; what shipped is the trust/auth/audit shape. **Python's `Connector` ABC must mirror the shipped shape, not the issue-body sketch.**

#### `OptionalPrimitive` (`connector.rs:78-104`)

```rust
#[non_exhaustive]
pub enum OptionalPrimitive {
    NativeApiBinding, ChangeDataCapture, BulkEnvelope, BrowserFallback,
    // NO DirectDb variant — G2 compile-time guarantee
}
```

The test `assert_no_direct_db_variant` (`connector.rs:255-266`) is an exhaustive match with no `_ =>` arm — adding `DirectDb` upstream breaks compilation. Python should mirror this with a closed `Enum` + a comparable structural assertion (e.g. a unit test enumerating exactly the allowed members against `set(OptionalPrimitive)`).

#### `ConnectorAuth` (`auth.rs:87-117`) — G1 type-forbidden impersonation

```rust
#[non_exhaustive]
pub enum ConnectorAuth {
    ScopedDelegation { service_account_ref: ServiceAccountRef, role_ref: RoleId },
    #[cfg(feature = "substitution")]
    Substitution { delegate_account_ref: DelegateAccountRef },
    // NO Impersonation variant — G1 compile-time guarantee
}
```

Test `assert_no_impersonation_variant` (`auth.rs:218-230`) is the same exhaustive-match enforcement.

**`assert_service_account_distinct(service_account: &Principal, sovereign: &Principal) -> Result<(), ImpersonationByCloneError>`** (`auth.rs:166-176`) — G1 amendment (a) runtime check: even with `Impersonation` type-removed, a connector could provision the service account as a clone of the human's credentials. Runtime check rejects equality.

#### `OidcVerifier` (`token.rs:56-104`) — REAL bearer-token verification, no mock

HS256 in v0 via `jsonwebtoken` crate. `OidcClaims { sub, exp, iss }`. `issue_test_token` (`token.rs:117-124`) is provided so the required-primitive integration test mints a REAL token (signed with the real key) and verifies it through the real verifier — Tier-2 no-mocking contract.

#### `DispatchEngine<T>` (`dispatch.rs:79-148`) — net-new idempotent dispatch

NOT a wrap of a substrate primitive — `kaizen_agents::GovernedSupervisor` provides retry-with-cap recovery, NOT exactly-once. This engine adds the dedup layer on top.

```rust
pub struct DispatchEngine<T> { cache: Mutex<HashMap<IdempotencyKey, T>> }

impl<T: Clone> DispatchEngine<T> {
    pub fn dispatch<F>(&self, key: &IdempotencyKey, action: F)
        -> Result<DispatchOutcome<T>, DispatchError>
    where F: FnOnce() -> Result<T, DispatchError>;
}
```

- First dispatch: runs `action`, caches `Ok` value, returns `Executed`.
- Subsequent dispatch with same key: returns cached value WITHOUT calling `action`, with `ReplayedCached`.
- Failed action NOT cached — composes the supervisor's retry-with-cap.
- Lock-poison-safe: recovers via `PoisonError::into_inner` rather than panicking.

`DispatchDisposition = Executed | ReplayedCached`.
`DispatchOutcome<T> { value: T, disposition: DispatchDisposition }`.

#### Receipt (`receipt.rs:42-73`)

```rust
pub struct SignedActionEnvelope { actor: Principal, action: String, audit_entry: LedgerEntryId }
pub struct AttestedReadReceipt { reader: Principal, resource: String, audit_entry: LedgerEntryId }
```

Both record into `LedgerContent::Evidence(json!({"agent_id": ..., "kind": "connector_write"|"connector_read", "action"|"resource": ...}))`.

Residency posture (`receipt.rs:13-24`): identity/action recorded verbatim BY DESIGN — a redacted audit trail is not an audit trail. The audit ledger CONTENT is on-prem-resident by topology; only the M4 salted chain-head crosses the residency boundary.

#### Revocation (`revocation.rs`)

`RevocationChannel` + `DEFAULT_TOKEN_TTL`. Per-call introspection bounded by short token TTL (G1 amendment (b)).

---

### 5. `kailash-delegate-audit` — append-only hash chain over EATP ledger

`<rs>/crates/kailash-delegate-audit/src/lib.rs:1-34` — composes substrate `eatp::ledger::KnowledgeLedger`. Does NOT re-implement hash chaining, hash computation, or tamper detection — those stay in the substrate.

#### Public surface (`lib.rs:29-34`)

```
pub use anchor::{
    classify_constraint_error, classify_constraint_outcome, validate_cross_tier_mode,
    AuditVisibility, CrossAnchorError, CrossTierMode, DelegateEventKind, Salt, WitnessedCrossAnchor,
};
pub use chain::{AuditChainEngine, ChainId, ChainTier};
```

#### ChainTier + ChainId (`chain.rs:54-138`)

```rust
#[non_exhaustive]
pub enum ChainTier { OnPrem, Cloud, Named(String) }

#[non_exhaustive]
pub struct ChainId {
    pub spec_version: String,
    pub tier: ChainTier,
    pub succession_ref: Option<[u8; 32]>,  // I3 lineage link
}

impl ChainId {
    pub fn major(&self) -> &str;
    pub fn requires_reroot(&self, target_spec_version: &str) -> bool;  // major-component change
}
```

#### AuditChainEngine (`chain.rs:158-332`)

```rust
pub struct AuditChainEngine<L: KnowledgeLedger = InMemoryLedger> {
    chain_id: ChainId,
    ledger: Arc<L>,
}

impl<L: KnowledgeLedger> AuditChainEngine<L> {
    pub fn new(chain_id: ChainId) -> Self;  // InMemoryLedger default
    pub fn with_ledger(chain_id: ChainId, ledger: Arc<L>) -> Self;
    pub fn chain_id(&self) -> &ChainId;
    pub fn ledger(&self) -> &Arc<L>;

    pub async fn record(&self, content: LedgerContent) -> Result<AuditChainRecord, EatpError>;
    pub async fn verify_integrity(&self) -> Result<(), EatpError>;
    pub async fn head(&self) -> Result<Option<LedgerEntry>, EatpError>;
    pub fn hashes_equal(a: &[u8; 32], b: &[u8; 32]) -> bool;  // constant-time, substrate fn
    pub async fn reroot_for_major_upgrade(
        &self,
        target_spec_version: impl Into<String>,
    ) -> Result<AuditChainEngine<InMemoryLedger>, EatpError>;
}
```

**Emitted-chain wire format (what Python must produce in a form the Rust verifier can verify per #1035 acceptance criterion 7).** A `LedgerEntry` (from `eatp::ledger`) carries:

- `entry_id: LedgerEntryId` (UUID)
- `sequence: u64` (substrate-computed, gap-free)
- `prev_entry_hash: Option<[u8; 32]>` (first entry: `None`)
- `entry_hash: [u8; 32]` (SHA-256 over canonical-JSON input via `LedgerEntry::compute_hash`)
- `content: LedgerContent` (an enum: `Evidence(serde_json::Value)`, `PolicyDecision(...)`, etc.)
- `timestamp: DateTime<Utc>`

The `content` for a Delegate-emitted event is `LedgerContent::Evidence(serde_json::Value)`. Example payloads observed in the Rust source:

- Lifecycle transition (`lifecycle.rs:293-300`):
  ```json
  {
    "event": "delegate.lifecycle.transition",
    "delegate_id": "<uuid>",
    "from": "Proposed",
    "to": "Instantiated"
  }
  ```
- Sub-delegate spawn (`lifecycle.rs:391-396`):
  ```json
  {
    "event": "delegate.subdelegate.spawned",
    "parent_id": "<uuid>",
    "child_id": "<uuid>"
  }
  ```
- Connector write/read (`dispatch/receipt.rs:90-94, 121-125`):
  ```json
  {"agent_id": "<id>", "kind": "connector_write", "action": "<string>"}
  {"agent_id": "<id>", "kind": "connector_read", "resource": "<string>"}
  ```

**Cross-impl chain agreement** requires identical canonical-JSON shape for these payloads. Python must use the same field names, same value types, same key order semantics (substrate `LedgerEntry::compute_hash` uses canonical JSON — Python must use a canonical-JSON serializer compatible with the Rust substrate's hashing input).

#### Cross-anchor (`anchor.rs:1-120` + 598 LOC of impl) — M4-02

Net-new, no substrate primitive. Per-tier chains (default `CrossTierMode::PerTierWitnessed`) joined by a salted on-prem-head digest:

1. On-prem chain head computed via substrate.
2. Fresh 32-byte CSPRNG `Salt` (`ZeroizeOnDrop`).
3. Publish `anchor_digest = SHA-256(salt || onprem_head_entry_hash)` to cloud — salt never leaves on-prem.
4. Seam verification: cloud-side recomputes and constant-time-compares via `LedgerEntry::hashes_equal`.

`CrossTierMode = PerTierWitnessed | SingleContinuous`. `SingleContinuous` is opt-in for same-residency only.
`CrossAnchorError = SeamVerificationFailed | ContinuousAcrossResidencyBoundary { detail }`.

---

### 6. `kailash-delegate-conformance` — F1-fenced behavioural vectors + cross-impl receipts

`<rs>/crates/kailash-delegate-conformance/src/lib.rs:1-50` — the **OSS-bound** crate. Apache-2.0 / Terrene-pledged mirror; one over-specified vector that encodes a proprietary engine internal permanently forces the engine open.

**Structural defense:** `Cargo.toml` depends on NO `kailash-delegate-*` engine crate — an engine symbol cannot resolve. CI workflow `.github/workflows/rust.yml` "Delegate spine F1 fence" step asserts manifest stays engine-free AND greps `src/` for any `kailash_delegate_*` symbol.

#### Public surface (`lib.rs:46-50`)

```
pub use receipt::{receipts_agree, ConformanceReceipt, ReceiptError};
pub use vectors::{
    delegate_spec_vectors, validate_vector_set, BehaviouralOutcome, ConformanceVector, SchemaError, SpecAnchor,
};
```

#### Conformance vector format (`vectors/mod.rs`)

**Format: Rust data, declared via Rust function** (`vectors/catalog.rs::delegate_spec_vectors`), serialized as **JSON** for cross-impl sharing. NOT checked-in JSON files — vectors are generated by calling the Rust function; the in-session feedback loop is `validate_vector_set(&vectors)`.

The schema (`vectors/mod.rs:227-249`):

```rust
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(try_from = "ConformanceVectorWire")]
#[non_exhaustive]
pub struct ConformanceVector {
    pub id: String,              // e.g. "DV-5-001" — cross-impl receipt addresses by this id
    pub spec_anchor: SpecAnchor, // MANDATORY — F1 fence #1
    pub given: String,           // plain spec language; NEVER a serialized engine struct
    pub behaviour: String,       // plain spec language; the per-vector review reads this
    pub expected: BehaviouralOutcome,  // CLOSED enum — F1 fences #2 + #3
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[non_exhaustive]
pub enum BehaviouralOutcome { Accept, Reject, EscalateToHuman }

pub struct SpecAnchor { section: String /* private; dotted-decimal; validated */ }
```

`SpecAnchor` is constructible ONLY through `SpecAnchor::new(section)` or `TryFrom<String>` (`serde(try_from)`). It validates dotted-decimal ASCII digits with interior single dots (no leading/trailing/doubled dot). Display renders WITH `§` glyph; storage WITHOUT.

**Three structural fences** (`vectors/mod.rs:16-43`):

1. Mandatory spec-§ anchor + validating deserialization (every vector reconstructed from JSON routes through `ConformanceVector::new`).
2. Behavioural-only expected output (closed enum — cannot round-trip an engine struct).
3. Value-allowlist enforced by the type system (an asserted value outside the published taxonomy is unrepresentable, not gate-rejected).

`SchemaError = InvalidSpecAnchor { detail } | EmptyField { field, detail } | DuplicateId { id }`.

`validate_vector_set(&[ConformanceVector]) -> Result<(), SchemaError>` — every vector valid AND all ids unique.

**Authored vectors** (only 2 in M7-02 — `vectors/catalog.rs`):

- `DV-5-001` (`SpecAnchor("5")`, expected `Reject`) — monotonic-tightening: a Delegation widening the Financial dimension MUST be rejected.
- `DV-10-001` (`SpecAnchor("10")`, expected `Reject`) — G1 service-account / sovereign-principal separation: identical principal is impersonation; reject the binding.

**For Python:** mirror by exporting `delegate_spec_vectors() -> list[ConformanceVector]` and serializing to JSON byte-identically. The JSON form a vector serializes to (from `vectors/mod.rs:412-419` round-trip test): `SpecAnchor` serializes as its bare section string `"7.3"` (not a struct).

Example expected JSON for `DV-5-001`:

```json
{
  "id": "DV-5-001",
  "spec_anchor": "5",
  "given": "Genesis Record G authorizes a Delegate, and a Delegation D from that Delegate widens the Financial dimension of its constraint envelope relative to G",
  "behaviour": "the runtime MUST reject Delegation D -- a delegated constraint envelope may only tighten, never widen, a PACT dimension within a single lifecycle; widening requires a new Genesis Record",
  "expected": "Reject"
}
```

#### F4 cross-impl receipt protocol (`receipt.rs`)

**This is the cross-SDK agreement primitive #1035 acceptance criterion 7 hinges on.**

```rust
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(try_from = "ConformanceReceiptWire")]
#[non_exhaustive]
pub struct ConformanceReceipt {
    pub implementation: String,       // "kailash-rs", "kailash-py"
    pub vector_crate_version: String, // exact crate version pinned
    pub commit_sha: String,           // commit SHA of the vector-set revision
    pub vectors_total: usize,
    pub vectors_passed: usize,        // MUST be ≤ vectors_total
}

impl ConformanceReceipt {
    pub fn conforms(&self) -> bool {
        self.vectors_total > 0 && self.vectors_passed == self.vectors_total
    }
}

pub fn receipts_agree(a: &ConformanceReceipt, b: &ConformanceReceipt) -> bool {
    a.implementation != b.implementation
        && a.vector_crate_version == b.vector_crate_version
        && a.commit_sha == b.commit_sha
        && a.conforms()
        && b.conforms()
}
```

`ReceiptError = EmptyField { field, detail } | PassedExceedsTotal { passed, total }`.

**Critical for Python:** the agreement protocol is COUNTS-ONLY by F1 design — never field-by-field engine diff. Python emits a `ConformanceReceipt { implementation: "kailash-py", vector_crate_version, commit_sha, vectors_total, vectors_passed }` after running the same vector set; Rust + Python receipts cross-reference via `receipts_agree`. The receipt is `serde`-serializable so each implementation persists it durably (journal entry / `observations.jsonl`) per `verify-resource-existence.md` MUST-4.

---

## Open/closed gap map — Python mirror translation patterns

| Rust primitive                                                                                    | Encoding pattern                                                                          | Python OSS mirror translation                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| ------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| `DelegateConstraintEnvelope` type-state (no Clone/Default/From; private inner; `serde(try_from)`) | Type-state via private field + consuming `tighten(self) -> Self` + `try_from` deserialize | `@dataclass(frozen=True, slots=True)` with **private `_inner`**, **no `__init__` taking the underlying envelope** (only classmethod `genesis_seed(cls, genesis, envelope)`); `tighten(self, child) -> "DelegateConstraintEnvelope"` raises `MonotonicTighteningError` and **returns a NEW instance** (Python can't "consume" but the frozen-dataclass + private-field combination closes the reconstruct hatch); pydantic `model_validator(mode="before")` or a `__post_init__` running the tightening check on deserialize. The "Wire" pair `{ parent, child }` becomes a Pydantic model whose `model_validator(mode="after")` calls `validate_tightening`. |
| `LifecycleState` (`#[non_exhaustive]` enum)                                                       | Closed Rust enum + non_exhaustive future variants + wildcard fail-closed arm              | `class LifecycleState(StrEnum)` — `PROPOSED / INSTANTIATED / POSTURE_GRADED / ACTIVE / RETIRED / ARCHIVED`. Mirror `legal_next` as a module-level dict `\_LEGAL_NEXT: dict[LifecycleState, LifecycleState                                                                                                                                                                                                                                                                                                                                                                                                                                                    | None]`. Mirror the wildcard fail-closed default via a `.get(state)`(returns`None` for unknown variants, fail-closed).                                                                                                                                                                                                              |
| `LifecycleTransition` (async; audit-before-apply)                                                 | Stateful struct + `Arc<AuditChainEngine>`                                                 | `class LifecycleTransition` with `_state: LifecycleState`, `_audit: AuditChainEngine`; `async def transition(self, to) -> AuditChainRecord` — same fixed order: legality → audit-attest → apply. Audit failure leaves state unchanged.                                                                                                                                                                                                                                                                                                                                                                                                                       |
| `TenantScope = Tenant(String)                                                                     | Global`                                                                                   | Typed 2-variant enum with `#[default] Global`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                | `class TenantScope: ...` as a sealed dataclass union, or a `Literal["global"]                                                                                                                                                                                                                                                      | tuple[Literal["tenant"], str]`. Cleaner: dataclass hierarchy `TenantScope`→`TenantScopeTenant(tenant_id: str)`/`TenantScopeGlobal()`with`is_global()`/`tenant_id() -> str | None`accessors. **Must NOT use`Optional[str]`\*\* — typed structural distinction is the whole point (M-1 misconfig guard). |
| `TenantScopedCascade.cascade_child` (3-layer fixed order)                                         | Borrow-based 5-arg fn                                                                     | `def cascade_child(self, parent_scope, child_scope, parent_env, child_env, child_tenant) -> None` — raises `TrustGateError` (one of `TenantIsolation`, `CascadeWidening`, `Tightening`). Envelope pair REQUIRED (no default-None).                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `R2CompositionEngine` (only widening constructor is `from_genesis`)                               | Private field + no public constructor except `from_genesis`                               | `class R2CompositionEngine`: `__init__` raises `NotImplementedError` (or is decorated `@final` private); the only public constructor is `@classmethod from_genesis(cls, genesis, baseline, tenant)`. `tighten_effective(self, child) -> "R2CompositionEngine"` returns a new instance (Python equivalent of consuming-self).                                                                                                                                                                                                                                                                                                                                 |
| `PostureRatchet` (advance-only-by-grant; fail-closed downgrade)                                   | Stateful struct + scalar `PostureLevel` field                                             | `class PostureRatchet`: `_posture: PostureLevel`; **no `set_posture`, no `raise_to`**. The ONLY raising method is `async def advance_on_grant(self, grant: GrantMoment)`. `downgrade_on_violation(self, trigger)` drops to floor even on audit-record failure.                                                                                                                                                                                                                                                                                                                                                                                               |
| `Connector` trait (default methods own sequencing)                                                | `#[async_trait]` with provided methods                                                    | `class Connector(abc.ABC)`: `@abstractmethod` properties `revocation`, `ledger`, `verifier`. **Non-abstract** `async def authenticate / write / read` — the ABC owns the sequencing (revocation check, attestation) so subclass authors cannot forget. Python can't fully replicate the trait's "compile-time-can't-skip-the-check" but the non-abstract concrete methods + private hooks pattern (`async def _perform_write` abstract, `async def write` final concrete that calls it) is the closest equivalent.                                                                                                                                           |
| `OptionalPrimitive` (no `DirectDb` — compile-time guarantee)                                      | `#[non_exhaustive]` enum + exhaustive-match test                                          | `class OptionalPrimitive(Enum)`: `NATIVE_API_BINDING / CHANGE_DATA_CAPTURE / BULK_ENVELOPE / BROWSER_FALLBACK`. Mirror the compile-time guarantee with a unit test asserting `set(OptionalPrimitive) == {NATIVE_API_BINDING, CHANGE_DATA_CAPTURE, BULK_ENVELOPE, BROWSER_FALLBACK}` — adding `DIRECT_DB` fails the test. (Python loses the structural strength but gains the test-asserted invariant.)                                                                                                                                                                                                                                                       |
| `ConnectorAuth` (no `Impersonation`)                                                              | Same enum + exhaustive-match                                                              | Same pattern: `class ConnectorAuth: ...` sealed union; unit test enumerates the exact allowed variants.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `assert_service_account_distinct`                                                                 | Runtime `Principal != Principal` check                                                    | `def assert_service_account_distinct(service_account: Principal, sovereign: Principal) -> None` — raises `ImpersonationByCloneError(principal: str)`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| `OidcVerifier` (HS256, real `jsonwebtoken`)                                                       | `jsonwebtoken` crate                                                                      | `class OidcVerifier`: backed by `pyjwt` (or `python-jose`). `verify(token: str) -> OidcClaims`; `verify_to_principal(token: str) -> Principal`. Real verification, no mock — same Tier-2 contract as Rust.                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| `AuditChainEngine` (composes `KnowledgeLedger`)                                                   | Generic over `L: KnowledgeLedger`                                                         | `class AuditChainEngine[L: KnowledgeLedger]`: `async def record(content: LedgerContent) -> AuditChainRecord`; `async def verify_integrity() -> None`; `async def head() -> LedgerEntry                                                                                                                                                                                                                                                                                                                                                                                                                                                                       | None`; `async def reroot_for_major_upgrade(target_spec_version) -> AuditChainEngine[InMemoryLedger]`. **Canonical-JSON serialization MUST byte-match the Rust substrate's hashing input** — use `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False)` and verify against a Rust-generated reference vector. |
| `ConformanceVector` (validating constructor + `serde(try_from)`)                                  | Pydantic-like validating dataclass                                                        | `class ConformanceVector(BaseModel)` (pydantic v2): `model_validator(mode="after")` raises `SchemaError`. `SpecAnchor` as a custom Pydantic type with `field_validator` enforcing dotted-decimal. **Serialized form must match Rust byte-identically** (cross-impl JSON sharing).                                                                                                                                                                                                                                                                                                                                                                            |
| `ConformanceReceipt` + `receipts_agree`                                                           | Counts-only F4 protocol                                                                   | Identical pydantic model + standalone `def receipts_agree(a, b) -> bool` with the EXACT same predicate (distinct implementations + same version + same SHA + both conform). This is the cross-impl agreement primitive #1035 acceptance criterion 7 hinges on.                                                                                                                                                                                                                                                                                                                                                                                               |
| `delegate_spec_vectors() -> Vec<ConformanceVector>`                                               | Rust function building the vector list                                                    | `def delegate_spec_vectors() -> list[ConformanceVector]`. Build the SAME 2 vectors (DV-5-001, DV-10-001) with byte-identical `given`/`behaviour` prose. JSON-export must round-trip against the Rust JSON form.                                                                                                                                                                                                                                                                                                                                                                                                                                              |

---

## Rust shard ordering — what Python should mirror

`git log --oneline -30 -- crates/kailash-delegate-*/` (from `<rs>`):

```
9a612dd1 feat(delegate): -runtime R1 lifecycle state machine (#988 M6-01)
4efc3b85 fix(delegate): -runtime emit parent-chain sub-delegate-spawn audit event + align rustdoc (#988 M6-01, C3)
78de99f3 feat(delegate): -runtime R2 envelope+cascade tightening — F5 co-shipment (#988 M6-02)
4dccdef3 test(delegate): -runtime fence the operational PACT dimension in the F5 regression suite (#988 M6-02, MEDIUM-1)
ff80207a feat(delegate): -runtime R3 posture ratchet + cross-Delegate cap (#988 M6-03)
4b3a9491 docs(delegate): add `# Caller contract` security section to with_posture (#988 M6-03)
d0ad005a feat(delegate): -runtime R4 memory + genesis-verify + composition surface (#988 M6-04a)
ea4ba8a1 fix(delegate): close F5 posture-escalation + 4 gate findings (#988 M6-04a)
07dd183d docs(delegate): correct two stale posture-rehydration doc refs (#988 M6-04a)
d5e8ab80 fix(delegate): re-export RepointError at the crate root (#988 M6-04a)
93bd9e35 feat(delegate): -runtime intent->role LLM step + F3/F6 quarantine (#988 M6-04b)
92c3f17d fix(delegate): harden F3 fence against cargo-tree errors + doc candidate-ceiling (#988 M6-04b)
923dfe59 feat(delegate): -runtime M6-05 message send path + disagreement resolution + spec upgrade (#988)
f4a72a7a feat(delegate): -conformance M7-01 vector schema + F1 licensing fence (#988)
22aad3cb fix(delegate): M7-01 gate-review fixes — validating vector deserialization + broadened F1 fence (#988)
151fd6cb feat(delegate): -conformance M7-02 F4 cross-impl receipt protocol + first behavioural vectors (#988)
98df7f01 fix(delegate): M7-02 gate fix — receipts_agree requires distinct implementations (#988)
88cacd40 feat(delegate-spine): M8-02 add composed-Delegate E2E regression (#988)
ccf17055 docs(delegate-spine): M8-02 release-prep disposition journal + nightly fmt (#988)
```

Earlier merged-via-PR commits (visible via `git log --all`):

```
c5202094 feat(delegate): -dispatch Connector trait + G1/G2 auth model (#988 M5-01)
1a1e369a feat(delegate): -trust Grant Moments + GrantSigner (#988 M3-02)
bde686c2 fix(delegate): -audit zeroize cross-anchor Salt + narrow serialize surface (#988 M4 M-3)
fc12ab24 fix(delegate): -dispatch alg-confusion rejection tests + receipt residency doc (#988 M5 M-2/M-4)
65081e36 fix(delegate): -trust enforce 5-dim envelope tightening on cascade edges + tenant-misconfig guard (#988 M3 H-1)
730645c7 Merge pull request #1032 from esperie-enterprise/feat/delegate-spine-m3-trust
61a36249 Merge pull request #1033 from esperie-enterprise/feat/delegate-spine-m4-audit
```

**Shard ordering pattern Python should mirror:**

1. **M1** — workspace setup (Cargo manifest fences). For Python: pyproject.toml + package layout fences (the F1 conformance crate MUST NOT import any engine module).
2. **M2-01** types (composition wrappers, identity, role, lifecycle, message, memory, intent, directory) before M2-02 envelope (the F5 type-state).
3. **M3-01** trust cascade (`TenantScopedCascade::cascade_child` — tenant → scope → envelope) before **M3-02** grant moments.
4. **M4** audit chain (lib + cross-anchor) — independently shardable; only depends on `-types`.
5. **M5** dispatch — `Connector` trait + G1/G2 auth + idempotent dispatch; **independently shardable** (does not depend on `-runtime`).
6. **M6-01** runtime lifecycle (composes -types + -audit).
7. **M6-02** runtime R2 composition engine + F5 cascade (composes -trust + -types).
8. **M6-03** posture ratchet + cross-Delegate posture cap.
9. **M6-04a** memory + genesis-verify + composition surface (`Delegate::instantiate` + `verify_genesis`).
10. **M6-04b** intent→role LLM step — **F3/F6 quarantined** behind a default-off feature gate. Python equivalent: an optional install extra (`pip install kailash-delegate[intent-role]`) that pulls `kailash-kaizen`.
11. **M6-05** message send path + disagreement resolution + spec upgrade (composes M4 reroot primitive).
12. **M7-01** conformance schema + F1 licensing fence (NO vectors yet — schema first, hard sequencing).
13. **M7-02** first behavioural vectors + F4 cross-impl receipt protocol.
14. **M8-02** composed-Delegate E2E regression.

**Key shard discipline:** M7-01 ships the schema with ZERO vectors authored (the F1 fence lands before any vector can leak an engine internal). M7-02 then authors vectors against the frozen schema. Python MUST honor this two-step.

---

## Substrate dependencies — what Python needs to reproduce

The Rust spine composes (never re-derives):

- **`eatp`** — `chain::{CareChain, GenesisBlock}`, `keys::TrustKeyPair`, `delegation::{DelegationChain, DelegationScope, DelegationRecord}`, `constraints::ConstraintEnvelope`, `ledger::{KnowledgeLedger, InMemoryLedger, LedgerEntry, LedgerEntryId, LedgerContent}`, `human::{HoldQueue, HumanOrigin, PseudoAgent}`, `posture::PostureSystem`, `types::{AgentId, OrgId, Capability, ConstraintDimensions, TrustLevel, PostureLevel, Subject, SubjectType}`, `EatpError`.
- **`kailash-governance`** — `Address` (D/T/R), `validate_tightening`, `compute_effective_envelope`, `can_access`, `MonotonicTighteningError`.

**Python equivalents** must already exist in `kailash-py` (the EATP + governance substrate is shared across SDKs — this is the open-core/open-spec relationship the #988 issue body describes). The Python Delegate package should `from kailash.eatp import ...` / `from kailash.governance import ...` in the same composition pattern — and the F1 conformance package's `pyproject.toml` MUST NOT depend on any `kailash-delegate-*` module.

---

## 5-line summary

1. **Per-crate LOC** (full src/, not just lib.rs): -types 1,446 · -runtime 6,473 · -trust 1,664 · -dispatch 1,276 · -audit 1,238 · -conformance 1,099. Total 13,196 LOC. lib.rs files are re-export shells (692 LOC); load-bearing impl lives in submodules.
2. **Most mature**: `kailash-delegate-runtime` (the load-bearing composition surface) and `kailash-delegate-trust` (the cascade gate); every other crate exists in service of these two.
3. **Canonical-type list** (the Python ABC/dataclass mirror set): `DelegateId`, `RoleId`, `DelegateIdentity`, `DelegateIdentityMetadata`, `Role`, `RoleBinding`, `RoleScope`, `CapabilitySet`, `VoiceAttrs`, `RoleLifecycleState`, `LifecycleState`, `GenesisRecord`, `PostureState`, `PostureLevel`, `AuditChainRecord`, `Principal`, `PrincipalDirectory`, `DelegateConstraintEnvelope` (F5 type-state), `DelegateMessage`, `InboundIntentEnvelope`, `IntentSource`, `MemoryScope`, `MemoryStoreHandle`, `TenantScope`, `CascadeCacheKey`, `TenantScopedCascade`, `GrantSigner`, `GrantedAuthority`, `GrantAuthorityEnvelope`, `GrantMoment`, `Connector` (ABC), `ConnectorAuth`, `ServiceAccountRef`, `OptionalPrimitive`, `OidcVerifier`, `OidcClaims`, `SignedActionEnvelope`, `AttestedReadReceipt`, `RevocationChannel`, `DispatchEngine`, `IdempotencyKey`, `DispatchOutcome`, `DispatchDisposition`, `ChainId`, `ChainTier`, `AuditChainEngine`, `WitnessedCrossAnchor`, `Salt`, `CrossTierMode`, `R2CompositionEngine`, `LifecycleTransition`, `PostureRatchet`, `RestrictedProfile`, `Delegate`, `RehydrationProof`, `IntentRoleSeam`, `ConflictResolution`, `DisagreementOutcome`, `EnvelopeWinner`, `ConformanceVector`, `SpecAnchor`, `BehaviouralOutcome`, `ConformanceReceipt`. Plus error families: `TrustGateError`, `LifecycleError`, `TransitionError`, `SpawnError`, `GenesisVerificationError`, `MessageSendError`, `SpecUpgradeError`, `PostureAdvanceError`, `PostureCapError`, `DowngradeTrigger`, `CascadeWithPostureError`, `ConnectorError`, `ImpersonationByCloneError`, `TokenError`, `DispatchError`, `AttestationError`, `MonotonicTighteningError`, `SchemaError`, `ReceiptError`, `CrossAnchorError`.
4. **Conformance vector format**: Rust function `delegate_spec_vectors() -> Vec<ConformanceVector>` (in `-conformance/src/vectors/catalog.rs`), JSON-serializable via serde for cross-impl byte-identical sharing. Schema enforces: mandatory `SpecAnchor` (dotted-decimal), closed `BehaviouralOutcome` enum (`Accept|Reject|EscalateToHuman`), validating `try_from` deserialize. Currently 2 authored vectors: DV-5-001 (§5 monotonic tightening, Reject) + DV-10-001 (§10 G1 principal separation, Reject). Cross-impl agreement via `receipts_agree(rs_receipt, py_receipt) -> bool` — counts-only protocol that never inspects per-vector engine output (F1 design).
5. **Rust shard ordering Python should mirror**: M1 (workspace fences) → M2 (-types: composition wrappers first, then F5 envelope type-state) → M3 (-trust: cascade first, then grant moments) → M4 (-audit: chain + cross-anchor) → M5 (-dispatch: Connector trait + G1/G2 + idempotent dispatch) → M6-01..04a (-runtime: lifecycle → R2 composition → R3 posture → R4 composition surface) → M6-04b (intent→role behind default-off feature gate) → M6-05 (message send + disagreement + spec upgrade) → M7-01 (-conformance: schema + F1 fence, ZERO vectors) → M7-02 (first behavioural vectors + F4 cross-impl receipt protocol) → M8-02 (composed-Delegate E2E regression). Key discipline: F1 schema before any vector; -conformance package MUST have zero engine deps.
