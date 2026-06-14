# Cluster B — §4.2 Clearance Gate + §4.3 Shard-to-Holder Binding

Conformance-gap analysis for EATP-12 v1.0 Trust Vault Key-Binding (kailash-py).
Security-critical: vault KEK authorization. Read-only — no source edited.

**Headline finding:** The entire vault binding is a **gated scaffold**.
`back_up_vault_key` (`src/kailash/trust/vault/backup.py:58-119`) raises
`NotImplementedError` (issue #606 / mint ISS-37); `restore_vault_key` **does
not exist anywhere** (grep `def restore_vault_key` → empty). Therefore EVERY
CL-/SH- requirement below is **ABSENT at the vault layer**. What IS present is
the reusable _substrate_ (CapabilitySet, RoleScope, the DispatchSurface
Invariant-3 capability gate, TenantScopedCascade, HMAC/canonical-JSON audit
primitives, the SLIP-0039 wrapper) that the binding must compose. The brief's
`delegate/*` substrate citations are **accurate** (the early "paths are wrong"
warning was over-cautious — `src/kailash/delegate/` exists and matches the
brief); the line numbers are off by a few and corrected below.

## Requirement table

| Normative ID   | Requirement (1-line)                                                                                                                | Current state                                 | Evidence (file:line)                                                                                                                                                                                                                | Net-new work                                                                     |
| -------------- | ----------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| **N12-CL-01**  | `back_up_vault_key` verifies `vault:backup` in bound role's `RoleScope.capabilities` before key resolution                          | **ABSENT**                                    | `trust/vault/backup.py:114-119` raises `NotImplementedError`; no clearance arg on signature (`:58-61` takes only `vault_key, ritual`)                                                                                               | Add `ClearanceContext` param; token-membership check mirroring Invariant 3       |
| **N12-CL-02**  | `restore_vault_key` verifies `vault:restore`; clearance/quorum/commitment/generation gates independent                              | **ABSENT**                                    | `def restore_vault_key` grep → EMPTY (function does not exist)                                                                                                                                                                      | Author entire `restore_vault_key` surface + 4 independent gates                  |
| **N12-CL-02a** | Binding-owned tenant + domain scoping, fail-closed (tenant→domain→token)                                                            | **ABSENT (substrate domain-blind by design)** | capability gate reads only token membership, domain-blind (`dispatch.py:1441-1442`); `RoleScope` has `domain` but **no tenant** (`types.py:579-580`); tenant lives on cascade (`trust.py:480`)                                      | Binding-added tenant check (cascade.tenant vs vault tenant) + domain cover check |
| **N12-CL-03**  | Governance-approver HELD action (Complete-level, OPTIONAL); `vault:approve`, approver≠requester, in signed payload                  | **ABSENT**                                    | no vault code; HELD/verification-gradient + `content_signing_bytes` primitive exists (`delegate/audit.py:79`)                                                                                                                       | Wire approver token into `event_payload` pre-image                               |
| **N12-CL-04**  | Cooling-off capability suspension during D6 7-day window; trust-anchored clock; fail-closed                                         | **ABSENT**                                    | posture axis exists (`TrustPosture.SUPERVISED`, `postures.py:38`); `SQLitePostureStore` (`posture_store.py:221`) stores posture, **NOT** capability suspension; **no `effective_posture` fn** (grep empty); no trust-anchored clock | Binding-local suspension layer keyed off D6 window + trust-anchored time         |
| **N12-CL-05**  | Complete-level backup-ceremony witness (`vault:witness`, ≠requester/≠approver, in signed payload)                                   | **ABSENT**                                    | no backup body; `content_signing_bytes` payload-signing available (`audit.py:79`)                                                                                                                                                   | Witness token into `vault_key_backup` `event_payload`                            |
| **N12-SH-01**  | Every shard bound to holder from deployment registry; reject unregistered (`unregistered-holder`)                                   | **ABSENT**                                    | no holder-registry surface (grep `holder_registry`/`unregistered.holder` → EMPTY); `back_up_vault_key` returns bare `List[List[str]]` with no holder attribution (`backup.py:60`)                                                   | Net-new registry + attribution-into-audit                                        |
| **N12-SH-02**  | Optional per-holder wrapping; Complete-level revocation; for-cause SHOULD wrap + MUST advance generation                            | **ABSENT (wrapping primitive exists)**        | HMAC primitives present (`delegate/audit.py:45` `import hmac`, `verify_seam` `:673`); no per-holder wrap code                                                                                                                       | Per-holder wrap/unwrap + `revoked-holder` path                                   |
| **N12-SH-03**  | Revocation MUST NOT drop effective reconstruction set below `k`; require rotation + surface to operator                             | **ABSENT**                                    | `rotate_holders` exists (`shamir.py:464`) but enforces no k-floor against a _registry_; no revocation accounting                                                                                                                    | k-floor guard on registry-aware revocation                                       |
| **N12-SH-04**  | For-cause revocation → generation-advancing KEK rotation; single `vault_kek_rotation` anchor w/ `for_cause=true` + new distribution | **ABSENT**                                    | `rotate_holders` re-shards but does **not** advance a generation (KeyMetadata has no generation int, `key_manager.py:114-118`); no `vault_kek_rotation` anchor emission                                                             | Generation counter (F-SUBSTRATE-1) + audited rotation anchor                     |

## Reusable substrate (REAL file:line — corrects brief's line offsets)

- **`CapabilitySet`** — `src/kailash/delegate/types.py:508`; `capabilities: tuple[str, ...]` (`:529`); `intersect(other)` at `:535-553`. Brief cites `types.py:535` for `intersect` — **accurate**.
- **`CapabilitySet.intersect` has ZERO authorization call sites** — confirms **F-AUTHZ-10**. Grep of `.intersect(` in non-test src hits only `delegate/envelope.py:163` (ConstraintEnvelope, a different `intersect`) and `trust/envelope.py:1376`. The capability gate does NOT use `intersect`; CL-01/02 gate the _bound single role_ per Invariant 3, and `intersect` is the forward-path multi-role _composition_ primitive only.
- **`RoleScope`** — `types.py:557`; fields `domain: str` + `capabilities: CapabilitySet` (`:579-580`). **No `tenant` field** — confirms **F-AUTHZ-11**. Brief cites `types.py:579` — **accurate**.
- **DispatchSurface Invariant 3 (capability gate)** — `dispatch.py:1435-1467` (brief cites `:1441`; the read is `role_caps = frozenset(role.scope.capabilities.capabilities)` at **`:1441`**, `missing = connector.requires_capabilities - role_caps` at `:1442`, raise at `:1456-1463`). The gate is **domain-blind** — it computes a pure set-difference over capability strings, no tenant/domain cascade. This is the exact mirror N12-CL-01 cites.
- **`TenantScopedCascade`** — `trust.py:396`; **`tenant: TenantScope`** attribute at `trust.py:480`. The runtime cross-check `cascade_tenant = self._cascade.tenant` lives at `runtime.py:1540`. This is the tenant anchor N12-CL-02a(a) must read from `ClearanceContext`, **never** from `RoleScope`.
- **HMAC / canonical-JSON audit primitives** — `delegate/audit.py`: `import hmac` (`:45`), `content_signing_bytes(event_type, event_payload, signer_delegate_id)` (`:79-130`) over `canonical_json_dumps` (`kailash.trust._json`, imported `:57`), `verify_seam` using `hmac.compare_digest` (`:673-682`). The pre-image is exactly `{event_type, event_payload, signer_delegate_id}` — confirms F-AUDIT-8 / the approver/witness-token-in-`event_payload` design.
- **SLIP-0039 wrapper** — `trust/vault/shamir.py`: `generate` (`:222`), `reconstruct` (`:317`), `serialize_shard`/`deserialize_shard` (`:402`/`:437`), `rotate_holders` (`:464`), `ShamirRitual` (`:145`). This is the only _working_ vault-layer code today.

## Net-new surfaces (must be built — none exist)

1. **`ClearanceContext`** — grep EMPTY. Carries bound `RoleScope`/`CapabilitySet`, the cascade's bound tenant, and the vault's `(tenant, domain)`. Threading point for CL-01/02/02a.
2. **`vault:backup` / `vault:restore` / `vault:approve` / `vault:witness` / `vault:rotate` / `vault:retire-alg` tokens** — grep `vault:backup`/`vault:restore` EMPTY. No vault capability vocabulary exists; tokens are plain strings the binding inserts into a `CapabilitySet`.
3. **Holder registry + `unregistered-holder` error** — grep EMPTY. Deployment-controlled attestable-principal registry; SH-01.
4. **Tenant/domain binding check** — the substrate gate is domain-blind (`dispatch.py:1441`), so CL-02a(a)+(b) are entirely binding-OWNED additions.
5. **Cooling-off suspension** — no `effective_posture`; `SQLitePostureStore` stores posture not capability suspension. CL-04 needs a binding-local 7-day window suspension keyed off the EATP-10 §14 trust-anchored clock (also net-new).
6. **`back_up_vault_key` body + entire `restore_vault_key` function** — backup stubbed (`:114`), restore non-existent.
7. **Generation counter / `vault_kek_rotation` anchor** — `KeyMetadata` (`key_manager.py:114-118`) carries `rotated_from`/`is_revoked`/`is_hardware_backed` but **no generation integer and no KEK-class tag** — confirms **F-SUBSTRATE-1**. SH-04's generation-advancing rotation has no substrate to advance.

## Conformant vs Complete split (drives sharding)

**Conformant-level MUST (must ship for any conformance):**

- N12-CL-01 (`vault:backup` gate), N12-CL-02 (`vault:restore` gate + independent gates), N12-CL-02a (tenant/domain fail-closed binding control), N12-SH-01 (holder registry, physical-custody attribution), N12-SH-03 (k-floor on revocation), N12-SH-04 (for-cause generation-advancing rotation).
- Multi-role `intersect` resolution is a REQUIRED forward-path surface (#1035) but **NOT** a Conformant resolution step (per F-AUTHZ-10) — gate on the _bound_ role only.

**Complete-level OPTIONAL (MUST NOT be mandatory for Conformant):**

- N12-CL-03 (governance-approver HELD action — mandatory only on the named high-risk paths: raw-bytes restore N12-IN-03, forced-stale N12-SG-03, cooling-off restore N12-CL-04).
- N12-CL-05 (backup-ceremony witness).
- N12-SH-02 (per-holder cryptographic wrapping; `MAY` at Conformant, Complete-level revocation).
- N12-CL-04 cooling-off suspension is a **binding-local consequence of D6** that fires regardless of level (it escalates to the CL-03 HELD action _or_ `missing-clearance` even at Conformant).

**Sharding implication:** the Conformant clearance gate (CL-01/02/02a) + holder-registry attribution (SH-01) form one coherent invariant cluster (token membership + tenant + domain + registry = ~4-5 invariants) that should shard separately from the Complete-level witness/approver/wrapping work and separately again from the generation-counter substrate extension (SH-04 + F-SUBSTRATE-1), which is blocked on mint ISS-37 / `kailash-py#630`.

## Key risks / pitfalls (§9 F-AUTHZ findings)

- **F-AUTHZ-1 (critical):** gate the **`CapabilitySet`** axis, NOT `DelegateConstraintEnvelope` (which carries only `inner` + `genesis_id`, no capability field). Verified: `envelope.py` has no capability field; CL-01/02 must read `role.scope.capabilities`.
- **F-AUTHZ-2 + F-AUTHZ-11 (critical/medium):** a `vault:*` token is **not** scope-free. The substrate gate is domain-blind and `RoleScope` has no tenant field — so CL-02a tenant+domain enforcement is **binding-owned**, reading tenant from `ClearanceContext`/cascade (`trust.py:480`), never off `RoleScope`. A flat token would let a dev-vault grant authorize a cross-tenant production-KEK recovery.
- **F-AUTHZ-4 (high):** D5/posture and capability are **orthogonal axes** — posture downgrade (SUPERVISED) does NOT remove a `vault:*` token from a `CapabilitySet`. CL-04 must enforce suspension at the capability layer explicitly; there is no `effective_posture→CapabilitySet` path (confirmed: no such fn).
- **F-AUTHZ-5 (high):** at Conformant (physical custody) a revoked current-generation paper shard is cryptographically indistinguishable from a legit one — neither identifier nor attribution can catch it. Generation-supersession (SH-04) is the **only** honest defense; do NOT over-claim a "commitment/identifier check" rejects it.
- **F-AUTHZ-6 (high):** caller-arbitrary holder IDs = sanctioned exfiltration channel. SH-01's registry (`unregistered-holder`) closes it; this is why SH-01 is Conformant-mandatory.
- **F-AUTHZ-7 (high):** the approver token MUST live **inside** the signed `event_payload` (covered by `content_signing_bytes` pre-image), approver≠requester, distinct `vault:approve` token, fail-closed — else a missing/forged approval is not cryptographically detectable.
- **F-AUTHZ-10/11 (medium, Ruling 2):** these are the substrate-accuracy corrections above — `intersect` is composition not resolution; tenant cascade is binding-owned. Both are already reflected truthfully in the spec; the binding must NOT re-introduce the false "substrate performs the cascade" claim.
- **F-AUTHZ-12 (medium):** backup _generation_ is the max-KEK-exposure moment; CL-05 witness is the Complete-level defense (the SH-01 registry limits WHO holds shards, not that generation is single-actor).

## Open questions for architecture

1. **ISS-37 / #606 dependency:** `back_up_vault_key` is explicitly gated on mint ISS-37 ("NOT YET STABLE"). Can the clearance gate (CL-01) + holder registry (SH-01) land **ahead** of ISS-37 against the frozen `back_up_vault_key` signature, or must the whole binding wait? The signature today (`vault_key: bytes, ritual: ShamirRitual`) carries **no** `ClearanceContext` — adding it changes the public signature the stub froze.
2. **`restore_vault_key` is wholly net-new** — does it live in `trust/vault/backup.py` (alongside backup) or a new `trust/vault/restore.py`? The spec's signature (`restore_vault_key(..., clearance: ClearanceContext, *, force_stale, passphrase_ref) -> RestoreReceipt`) has no scaffold to thread through.
3. **Generation counter ownership (F-SUBSTRATE-1):** SH-04 needs a monotonic `kek_generation` int + KEK-class tag on `KeyMetadata`, which is tracked under `kailash-py#630` as REQUIRED net-new. Is that extension in-scope for this workstream or a hard upstream blocker?
4. **Trust-anchored clock (CL-04 / F-TEMP-2):** the EATP-10 §14 trust-anchored-time discipline has no kailash-py surface found. Is there a trust-anchored time source to bind cooling-off determination to, or is that itself net-new (fail-closed when unavailable)?
5. **`AuditDispatcher.dispatch(anchor, tier="recovery")` (F-SUBSTRATE-2):** the shipped `dispatch()` (`trust/pact/audit.py:520`) keys on `VerificationLevel`, has no `tier` param / `recovery` tier. The clearance-denial anchors (N12-AU-01) need a dispatcher adapter — does the binding adapter map onto the gradient-keyed surface, or wait for the named-tier dispatcher (also `kailash-py#630`)?

**File written:** `workspaces/eatp-12-vault-binding-py/01-analysis/04-clearance-and-holder.md`
