# Cluster A — §3.4 Substrate + §4.1 Input Shape

Conformance-gap analysis for EATP-12 v1.0 Trust Vault Key-Binding (kailash-py).
Read-only audit; every current-state claim is grep/read-verified against
`src/kailash/trust/**` at the commit checked out on `main` 2026-06-14.

Spec source: `workspaces/eatp-12-vault-binding-py/briefs/eatp-12-v1.0-spec.md`
(§3.4 lines 130-138, §4.1 lines 144-175, §9 red-team lines 558-694).

**Headline:** the binding's input-shape and net-new substrate are almost
entirely ABSENT. The shipped surface is a single gate-documented stub
(`back_up_vault_key(vault_key: bytes, ritual)`) raising `NotImplementedError`,
plus an Ed25519 **signing**-only key manager with no encryption hierarchy. Every
N12-IN requirement and every §3.4 substrate bullet is net-new. The spec itself
already discloses this honestly (§3.4 + F-SUBSTRATE-1/-2 under Ruling 2), so
this cluster is a build-from-near-zero, not a fix-the-drift.

## Requirement table

| Normative ID                                                         | Requirement (1-line)                                                                                                                                                                                                                                                         | Current state                      | Evidence (file:line)                                                                                                                                                                                                                                                                                                                                                                                                                                        | Net-new work                                                                                                                                                                                                                                                                                                                                                                                           |
| -------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **§3.4 bullet 1** — `key_class ∈ {KEK, DATA}` metadata tag           | `KeyMetadata` MUST expose a key-class field                                                                                                                                                                                                                                  | **ABSENT**                         | `trust/key_manager.py:110-118` — fields are `key_id, algorithm, created_at, expires_at, is_hardware_backed, hsm_slot, is_revoked, revoked_at, rotated_from`; **no** `key_class`. `grep -rn 'key_class' src/kailash/` → **0 hits**.                                                                                                                                                                                                                          | Add `key_class` field to `KeyMetadata` (or a vault-binding-owned metadata extension); the N12-IN-02 type check reads it.                                                                                                                                                                                                                                                                               |
| **§3.4 bullet 2** — `kek_generation: int` monotonic counter          | authoritative metadata MUST carry a generation integer advanced only by an audited rotation event (N12-RT-06)                                                                                                                                                                | **ABSENT**                         | `trust/key_manager.py:118` carries `rotated_from` (a key-ID lineage **string**), not a generation integer. `grep -rn 'kek_generation' src/kailash/` → **0 hits**.                                                                                                                                                                                                                                                                                           | Add `kek_generation: int`; wire its advance to the audited `vault_kek_rotation` anchor (out-of-cluster: §6/§4.5).                                                                                                                                                                                                                                                                                      |
| **§3.4 bullet 3** — KEK / data-key wrapping hierarchy                | KEK MUST protect data keys transitively; KEK-vs-data-key distinction MUST exist                                                                                                                                                                                              | **ABSENT**                         | No KEK/data-key distinction anywhere in key management. `TrustPlaneKeyManager` protocol is sign/get_public_key/key_id/algorithm only (`trust/plane/key_managers/manager.py:48-91`); `LocalFileKeyManager` is a single Ed25519 **signing** key (`:100-221`, `_load_private_key → Ed25519PrivateKey`); cloud backends (AWS-KMS / Azure / Vault) are all P-256 **signing** (`plane/key_managers/__init__.py:6-9`). `grep -rn 'KEK' src/kailash/` → **0 hits**. | New encryption/wrapping hierarchy; KEK as encryption key (not a signing key); data-key wrap/unwrap surface.                                                                                                                                                                                                                                                                                            |
| **N12-IN-01** — handle-based primary input                           | public `back_up_vault_key` / `restore_vault_key` MUST take a key **handle/ID**, resolve KEK internally; raw bytes MUST NOT cross the public boundary by default                                                                                                              | **ABSENT** (anti-conforming today) | `trust/vault/backup.py:58-61` — `back_up_vault_key(vault_key: bytes, ritual)` takes **raw bytes** as the primary arg (the exact non-conforming shape N12-IN-01 names). `restore_vault_key` does not exist: `grep -rn 'restore_vault_key' src/kailash/` → **0 hits**.                                                                                                                                                                                        | Re-shape `back_up_vault_key` to `(key_handle, ritual, clearance, holders)`; create `restore_vault_key(shards, target_handle, clearance, *, force_stale, passphrase_ref)`; add internal handle→KEK resolution inside the trusted process. The stub docstring already sanctions this signature evolution ("signature evolution is in scope for ISS-37", `backup.py:75-76`; spec N12-IN-03 final bullet). |
| **N12-IN-02** — KEK-only, type-enforced, never data keys             | handle resolution MUST verify resolved object is **KEK-class** and reject data-key / wrapped-blob / non-KEK with typed `not-a-kek` **before any sharding**                                                                                                                   | **ABSENT**                         | No handle-resolution path exists; no `key_class` tag to read (depends on §3.4 bullet 1); no `not-a-kek` error. The shipped stub never resolves a handle at all (`backup.py:91-95` raises immediately).                                                                                                                                                                                                                                                      | KEK-class check at resolution; `not-a-kek` typed error; ordering guarantee (check precedes shard). Per F-CRYPTO-5, this is the falsifiable enforcement the first draft lacked.                                                                                                                                                                                                                         |
| **N12-IN-03** — raw-bytes escape hatch, disabled by default          | MAY retain `secret: bytes` form, but MUST be **disabled by default** behind a build/deploy flag; absent flag → `escape-hatch-disabled`; when enabled, subject to clearance+holder+commitment+audit+stale gates + mandatory HELD approver + `vault_key_restore_raw` dual-emit | **ABSENT**                         | Current `vault_key: bytes` is the DEFAULT (and only) shape, not a disabled-by-default escape hatch (`backup.py:58-61`). No build flag, no `escape-hatch-disabled` error, no gating.                                                                                                                                                                                                                                                                         | Invert: handle-based becomes default; raw-bytes becomes flag-gated escape hatch with the full gate stack. Per F-CRYPTO-7 the disabled-by-default is a **MUST** (upgraded from SHOULD).                                                                                                                                                                                                                 |
| **N12-IN-04** — key-identity capture at backup                       | `back_up_vault_key` MUST record the resolved KEK's stable key-ID and bind it into the KEK-identity commitment (§4.4, N12-CB-01)                                                                                                                                              | **ABSENT**                         | No identity capture; the stub never resolves a key, so there is no key-ID to record (`backup.py:91-95`). `KeyMetadata.key_id` exists (`key_manager.py:110`) as a substrate building-block, but nothing in the vault path reads it.                                                                                                                                                                                                                          | Capture resolved KEK key-ID at backup; feed it to the §4.4 commitment (out-of-cluster CB-01, but the **capture** is this cluster's IN-04). The anchor that lets restore reject cross-vault re-install (`key-identity-mismatch`).                                                                                                                                                                       |
| **N12-IN-05** — no plaintext crosses the boundary; consume-and-`del` | reconstructed KEK MUST NOT return in plaintext; re-establish inside trusted module, return opaque handle; consume + `del` master-secret bytes in a `finally`; run in memory-locked, swap-disabled region; plaintext in no return/log/receipt/audit                           | **ABSENT**                         | No restore path exists (no `restore_vault_key`), so no consume-and-`del`, no memory-locked region, no opaque-handle return. The §8 memory-lock requirement has no implementation surface today.                                                                                                                                                                                                                                                             | Build the restore re-establishment path; `del` in `finally`; mlock/swap-disable region (§8); opaque-handle return type. Per F-BND-9 this is the enforcement the first draft asserted but never backed.                                                                                                                                                                                                 |

## Reusable infrastructure

What the binding CAN build on (verified present):

- **SLIP-0039 wrapper — production-ready.** `trust/vault/shamir.py` exposes a
  frozen `ShamirRitual(threshold, total_shards)` with full validation
  (`shamir.py:145-219`: `threshold>=2` enforced, `total_shards<=16`,
  `threshold<=total_shards`, `threshold==1 & total>1` rejected) plus
  `generate` / `reconstruct` / `serialize_shard` / `deserialize_shard` /
  `rotate_holders` (`__all__` at `shamir.py:77`). The ritual surface is the
  threading point N12-IN-01's `back_up_vault_key(..., ritual: ShamirRitual)`
  already references. Cluster B (crypto/commitment) owns the deeper SLIP-0039
  pinning (`extendable`, `iteration_exponent`, F-XSDK-1/CRY-PIN).
- **`KeyMetadata.key_id`** (`key_manager.py:110`) — the stable key-ID field
  N12-IN-04 captures already exists as a substrate primitive; the binding reads
  it, it does not invent it.
- **Key-manager backends exist** (AWS-KMS, Azure-KV, HashiCorp-Vault,
  LocalFile — `plane/key_managers/`) — but **all signing-only** (P-256 /
  Ed25519). They are a structural template for the net-new encryption-key
  manager, NOT a reusable KEK surface.
- **The stub is sanctioned to evolve.** `backup.py:5-44` + `:75-76`
  docstring + spec N12-IN-03 final bullet explicitly authorize the
  `vault_key: bytes` → handle-based signature change under this spec
  (the ONE permitted `NotImplementedError` per zero-tolerance Rule 2,
  issue #606 / mint ISS-37).

## Net-new surfaces required

New types/fields this cluster must originate (none exist today — all greps empty):

1. **`VaultKeyHandle`** — opaque vault key identifier type; the primary arg of
   both public entry points (`grep VaultKeyHandle` → 0 hits). Spec §4.1
   signatures (lines 165-172) use it directly.
2. **`BackupReceipt`** — return type of `back_up_vault_key`; carries shard set
   (or refs), audit-anchor ref, captured `kek_generation`, KEK-identity
   commitment + `kek_commitment_alg`, key-check-value, `shard_commitments`,
   `side_channel_hardened`, holder binding — **never** KEK bytes/passphrase
   (spec §4.1 line 175). 0 hits.
3. **`RestoreReceipt`** — return type of `restore_vault_key`; carries the
   re-established key handle + audit-anchor ref, **never** KEK bytes
   (§4.1 line 175). 0 hits.
4. **`ClearanceContext`** — carries the caller's bound `RoleScope`/`CapabilitySet`,
   the dispatch cascade's bound tenant, and the vault's `(tenant, domain)`
   (§4.1 line 175; gate semantics in §4.2, out-of-cluster). `grep 'class
ClearanceContext'` → 0 hits. **Net-new** (the clearance-gate cluster owns its
   semantics; this cluster only needs it on the input signature).
5. **`PassphraseRef`** — provenance handle for `passphrase_ref` (never raw
   passphrase bytes on the public path; §4.1 line 175, §4.4.1). Net-new
   (cross-references Cluster B / passphrase F-CRYPTO-4).
6. **`HolderId`** — element type of the `holders: list[HolderId]` backup arg
   (§4.1 line 167). Net-new (holder-registry cluster owns its semantics;
   this cluster needs the type on the signature).
7. **`key_class` field** on `KeyMetadata` (or vault-owned metadata extension)
   — §3.4 bullet 1.
8. **`kek_generation: int`** monotonic counter on authoritative metadata —
   §3.4 bullet 2.
9. **KEK/data-key wrapping hierarchy** — a net-new encryption-key abstraction
   distinct from the shipped signing-key managers — §3.4 bullet 3.

## Key risks / pitfalls (§9 red-team findings bearing on this cluster)

- **F-SUBSTRATE-1 (high, Ruling 2)** — `kek_generation`, KEK-class metadata,
  and the KEK/data-key hierarchy are specified against substrate present in
  **neither** shipped SDK (spec line 630). Resolution is **truthful re-word, not
  weakened**: §3.4 discloses them as REQUIRED net-new (tracked
  `kailash-py#630`/`#1304`); N12-IN-02 + N12-RT-06 are "binding-adds" framed.
  **Pitfall:** do NOT implement against an assumed-present `key_class`/generation
  field — they are this cluster's to create. The §6 stale-guard AND N12-IN-02
  both DEPEND on these landing first; sequence the metadata extension before the
  type check.
- **F-CRYPTO-5 (high)** — KEK/data-key boundary unenforced + handle/identity
  unbound in the first draft (spec line 568). N12-IN-02 (`not-a-kek` type check)
  - N12-IN-04 (`key-identity-mismatch` via captured key-ID) are the falsifiable
    enforcement. **Pitfall:** asserting "the handle resolves to a KEK" without the
    type check is exactly the gap F-CRYPTO-5 names — the check MUST run **before
    any sharding**, exercised by V8(b).
- **F-CRYPTO-7 (high)** — escape hatch re-installs arbitrary KEK with no binding
  (spec line 570). N12-IN-03 disables it by default (**MUST**, upgraded from
  SHOULD), behind a build flag + mandatory HELD approval, subject to the
  commitment check, dual-emitting `vault_key_restore_raw`. **Pitfall:** the
  shipped `vault_key: bytes` default IS the un-gated raw path F-CRYPTO-7 forbids;
  inverting default-vs-escape-hatch is the load-bearing change, not an additive
  one.
- **F-BND-9 (medium)** — no-plaintext-return was asserted but unbacked in the
  first draft (spec line 619). N12-IN-05 supplies the enforcement point
  (consume-and-`del` inside the trusted module + memory-locked region) AND the
  adversarial vector (V7(b)). **Pitfall:** returning the reconstructed KEK to the
  caller "just for the handle wrap" defeats N12-IN-05; the re-establishment MUST
  happen inside the trusted module and return only an opaque handle.

## Open questions for architecture

1. **Metadata extension placement.** Does `key_class` / `kek_generation` land as
   new fields on the shipped `KeyMetadata` dataclass
   (`key_manager.py:93-118`), or as a vault-binding-owned metadata wrapper?
   §3.4 says "the binding REQUIRES the key metadata to expose" — wrapper vs
   field is an architecture call. Field-on-`KeyMetadata` is the
   least-indirection path but touches the shared trust substrate; a wrapper
   isolates the vault concern. (Recommend confirming with the cross-spec /
   substrate cluster owner — `#630` tracks this.)
2. **KEK encryption-key abstraction.** The shipped key managers are all
   **signing** keys (Ed25519 / P-256). A KEK is an **encryption** key. Is the
   net-new hierarchy a new `EncryptionKeyManager` protocol sibling to
   `TrustPlaneKeyManager`, or an extension of the existing one? This is the
   largest net-new surface and likely spans Cluster A's §3.4 bullet 3 with the
   substrate cluster.
3. **`VaultKeyHandle` opacity contract.** What is the handle's concrete shape —
   a thin wrapper over `KeyMetadata.key_id` (str), or a richer opaque token
   carrying `(tenant, domain)` resolution hints? §4.1 says the handle resolves
   the vault's `(tenant, domain)` (line 175), implying it carries more than a
   bare key-ID.
4. **Memory-lock surface (N12-IN-05 + §8).** Does kailash-py have an existing
   mlock / swap-disable primitive, or is the memory-locked region itself
   net-new? `grep` for an existing primitive was out-of-scope for this cluster;
   the restore-path cluster should confirm before assuming N12-IN-05's
   memory-locked region is implementable.
5. **`ClearanceContext` ownership.** This cluster needs `ClearanceContext` on
   the input signature, but its `(tenant, domain)` resolution + `RoleScope`/
   `CapabilitySet` binding semantics belong to the clearance-gate cluster
   (§4.2, F-AUTHZ-1/10/11). Confirm the type's home so the input signature and
   the gate cluster agree on its shape.

---

**Verification note:** Every "ABSENT" / "0 hits" claim above was produced by a
live `grep -rn '<token>' src/kailash/` (excluding `__pycache__`) in this
session: `key_class`, `kek_generation`, `KEK`, `VaultKeyHandle`,
`BackupReceipt`, `RestoreReceipt`, `restore_vault_key`, `class
ClearanceContext` each returned 0. The stub signature, `KeyMetadata` field
list, key-manager protocol, and SLIP-0039 surface were read directly at the
cited line ranges.
