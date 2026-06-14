# Cluster C — §4.4 Commitment Binding + §4.4.1 Passphrase + §6 Stale-Guard

EATP-12 v1.0 Trust Vault Key-Binding — conformance-gap analysis for the
anti-injection cluster (KEK-identity commitment, passphrase provenance,
stale-generation guard). Read-only audit against shipped `kailash-py` at
`src/kailash/trust/**`. Every current-state claim is evidence-first
(file:line); where grep returned empty it is stated explicitly.

**Headline:** the entire cluster is **ABSENT** from shipped code. ZERO of the
nine normative IDs have any implementation surface. What exists is a usable set
of _substrate primitives_ (canonical-JSON encoders, the EATP-08 alg registry,
the SLIP-0039 wrapper) that the binding will compose — plus a single
issue-linked stub (`back_up_vault_key`). There is no `restore_vault_key`, no
commitment, no KCV, no generation counter, no denylist, no `shard_commitments`,
no `RecoveryRitualRecord`.

---

## Requirement table

| Normative ID     | Requirement (1-line)                                                                                                           | Current state | Evidence (file:line)                                                                                                                                                                        | Net-new work                                                                                                                             |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------ | ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| **N12-CB-01**    | KEK-identity commitment over canonical tuple `{domain_sep, vault_id, kek_generation, master_secret, pp}`, registered at backup | **ABSENT**    | grep `kek_identity_commitment` → 0 hits across `src/kailash/`; `back_up_vault_key` raises `NotImplementedError` (`vault/backup.py:96`)                                                      | New commitment helper; backup-path registration; canonical pre-image via `canonical_json_dumps` (see § pre-image)                        |
| **N12-CB-02**    | Restore verifies commitment + identity BEFORE re-establishing any key (steps 7/d)                                              | **ABSENT**    | grep `restore_vault_key` → 0 hits; no restore surface exists anywhere in `src/kailash/trust/vault/` (`backup.py`+`shamir.py` only)                                                          | New `restore_vault_key`; recompute-under-captured-generation; `kek-commitment-mismatch`/`key-identity-mismatch` codes                    |
| **N12-CB-03**    | Per-deployment foreign-shard check via `shard_commitments` (EATP-10 reuse), `unknown-shard` before reconstruction              | **ABSENT**    | grep `shard_commitments` → 0 hits; grep `RecoveryRitualRecord` → 0 hits; `reconstruct` does NO identity/commitment check (`shamir.py:317-394`)                                              | New `shard_commitments` array maintenance + check; sourcing from `vault_key_backup`/`vault_holder_rotation`/`vault_kek_rotation` anchors |
| **N12-CB-04(a)** | First-class `kek_commitment_alg` field (`"eatp-v1"`) in `BackupReceipt` + audit payload + `RecoveryRitualRecord`               | **ABSENT**    | grep `kek_commitment_alg` → 0 hits. Registry token `eatp-v1` (SHA-256) DOES exist (`algorithm_id.py:109-114`)                                                                               | New field on net-new `BackupReceipt`; reuse `algorithm_id.py` registry for token validation                                              |
| **N12-CB-04(b)** | Recompute-under-recorded-alg against per-(handle,gen) registry; `commitment-alg-mismatch` only when no row exists              | **ABSENT**    | No restore path → no recompute. `coerce_algorithm_id` exists for token coercion (`algorithm_id.py`, exported `signing/__init__.py:39`)                                                      | New per-(target_handle, generation) commitment registry keyed by alg; new `commitment-alg-mismatch` error                                |
| **N12-CB-04(c)** | Additive recommit registry (`vault_kek_recommit` anchor ADDS `C_Y`, keeps `C_X`); growth metric                                | **ABSENT**    | grep `vault_kek_recommit` → 0 hits                                                                                                                                                          | New anchor subtype + additive registry semantics + operator growth metric                                                                |
| **N12-CB-04(d)** | Mandatory key-free **KCV** = `truncate_8B(H_alg(canonical_json_dumps({domain_sep:"EATP-12/kcv/v1", ...})))`, 16 hex            | **ABSENT**    | grep `kcv` / `key_check_value` → 0 hits                                                                                                                                                     | New KCV helper (NIST SP 800-130); `kcv-mismatch` error; 8-byte/16-hex fixed constant                                                     |
| **N12-CB-04(e)** | Algorithm retirement (`vault_kek_retire` anchor → entry non-verifiable); `retired-commitment-alg` error                        | **ABSENT**    | grep `vault_kek_retire` → 0 hits                                                                                                                                                            | New retire anchor subtype; `vault:retire-alg` capability; re-commit-before-retire recoverability guard                                   |
| **N12-PP-01**    | Passphrase provenance defined + bound into commitment; printable-ASCII validation; `invalid-passphrase`                        | **ABSENT**    | grep `passphrase_provenance` → 0 hits. `reconstruct(passphrase=bytes)` accepts a passphrase but does NO printability validation and surfaces library `ValueError` raw (`shamir.py:317-392`) | New provenance tag + binding; pre-call printable-ASCII (32–126) check; `passphrase_ref` opaque handle on restore surface                 |
| **N12-SG-01**    | Generation tagged (monotonic int) AND bound into commitment; embedded in blob under fixed `kek_generation:int`                 | **ABSENT**    | grep `kek_generation` → 0 hits. `KeyMetadata` carries `is_revoked`/`rotated_from`/`is_hardware_backed` but **NO generation integer, NO key-class** (`key_manager.py:110-118`)               | Net-new key-manager surface (`kailash-py#630`, F-SUBSTRATE-1): generation counter + KEK-class tag                                        |
| **N12-SG-02**    | Stale restore refused by default; step-6 foreign-shard → step-7 commitment → step-8 ordinal `stale-generation`                 | **ABSENT**    | No restore path; grep `stale-generation` → 0 hits; no rotation chain sourcing the current generation                                                                                        | New 3-gate ordered pipeline (steps 6/7/8); current-generation sourced from audited `vault_kek_rotation` chain (N12-RT-06)                |
| **N12-SG-03**    | `force_stale` override: distinct `vault:restore-stale` capability + HELD approval; dual-emit `safety` tier                     | **ABSENT**    | grep `force_stale` → 0 hits                                                                                                                                                                 | New override flag (default `False`); higher capability gate; `vault_key_restore_forced_stale` anchor dual-emitted                        |
| **N12-SG-05**    | Compromised-generation denylist; `revoked-generation` even at current; derived from audited anchor chain                       | **ABSENT**    | grep `revoked-generation` → 0 hits. `KeyMetadata.is_revoked` is per-key, NOT per-generation (`key_manager.py:116`)                                                                          | New per-generation REVOKED state derived from rotation/denylist anchor chain (distinct from per-key `is_revoked`)                        |

**Summary:** 0 of 9 normative IDs (counting CB-04 a–e as one) PRESENT or PARTIAL. All ABSENT. The cluster is greenfield on top of three reusable substrate primitives.

---

## The canonical commitment pre-image (byte-exact transcription)

### N12-CB-01 — KEK-identity commitment pre-image (spec §4.4, lines 230-237)

```
kek_identity_commitment = H_alg( canonical_json_dumps({
    "domain_sep": "EATP-12/kek-identity-commitment/v1",
    "vault_id": <string>,
    "kek_generation": <int>,
    "master_secret": <lowercase-hex>,
    "passphrase_provenance": <string-tag, §4.4.1>
}) )
```

Pinned constants / shape rules (spec §4.4, lines 239-244):

- `domain_sep` is the **fixed ASCII constant** `"EATP-12/kek-identity-commitment/v1"` — reproduced byte-identically in the Appendix B golden fixture.
- **`vault_salt` is DELETED** — there is NO `vault_salt` field (F-CRYPTO-14 fix). Domain separation comes from `domain_sep`; the construction commits to `master_secret` directly.
- The single canonical input tuple is EXACTLY `{domain_sep, vault_id, kek_generation, master_secret, passphrase_provenance}` and MUST be enumerated identically across N12-CB-01, N12-CB-02(b)/(c), §8, and Appendix B.
- `kek_generation` is the **captured** generation (the value the backup tagged), per N12-SG-01 / second-cycle fix [1]/[14].
- `master_secret` is **lowercase-hex** encoded.
- `H_alg` is the hash resolved from the recorded `kek_commitment_alg` (N12-CB-04); for `"eatp-v1"` the Hash column resolves to SHA-256.
- A keyed `HMAC-H(K=HKDF-Extract(domain_sep), msg=canonical-encoding(tuple))` is a RECOMMENDED hardening, NOT the load-bearing requirement.

### N12-CB-04(d) — KCV pre-image (spec §4.4, line 252)

```
KCV = truncate_N( H_alg( canonical_json_dumps({
    "domain_sep": "EATP-12/kcv/v1",
    "vault_id": ...,
    "kek_generation": <int>,
    "master_secret": <hex>
}) ) )
```

Pinned: **`N = 8` bytes** (leading 8 bytes of the digest), encoded as **16 lowercase-hex characters**, fixed across all conformant SDKs (fix [10] closing the §4.5.1 circular deferral). Note the KCV pre-image OMITS `passphrase_provenance` (4 fields vs the commitment's 5). `kcv-mismatch` (§4.6) on a relabelled/tampered blob.

**CRITICAL encoder note (load-bearing for byte-identical V6 guarantee — see § pitfalls F-CRYPTO-13):** the spec names **`canonical_json_dumps`** (RFC 8785 / JCS, "the same form the rest of the suite uses for hashed pre-images", §4.4 line 225/628). In shipped kailash-py that name is the **delegate cross-SDK family** at `src/kailash/trust/_json.py:149` — which uses `ensure_ascii=False` (raw UTF-8) to match Rust `serde_json` (`_json.py:172-177`). This is the OPPOSITE of the trust-plane _signing_ family `serialize_for_signing` (`crypto.py:225-326`, `ensure_ascii=True`, `\uXXXX`-escaped, `crypto.py:242-251`). The two families are intentionally non-cross-mixing (issue #1258, `_json.py:187-203`). The binding's commitment pre-image MUST use `canonical_json_dumps` (delegate family) per the spec's literal citation — using `serialize_for_signing` would produce a DIFFERENT byte stream on any non-ASCII `vault_id`/provenance and silently break the cross-SDK V6 byte-identical fixture. **This is the single most important encoder-selection decision in the cluster and must be pinned at architecture time.**

---

## Reusable infrastructure (cite file:line)

1. **Canonical-JSON helper — `canonical_json_dumps`** — `src/kailash/trust/_json.py:149`. RFC 8785 / JCS, `sort_keys=True` + `separators=(",",":")` + `ensure_ascii=False` (`_json.py:172-181`), rejects NaN/Infinity (`allow_nan=False`) and non-string keys. This IS the encoder the spec's commitment + KCV pre-images cite (`canonical_json_dumps`). Byte-vectors pinned at `tests/test-vectors/delegate-canonical.json` (`_json.py:204-205`).
   - Sibling signing encoder `serialize_for_signing` — `crypto.py:225-326` (`ensure_ascii=True`). NOT the one the commitment cites; relevant only because the _audit-anchor_ `content_signing_bytes` pre-image (N12-AU-02) uses the signing family. Do not conflate.
2. **EATP-08 §3.3 algorithm registry** — `src/kailash/trust/signing/algorithm_id.py`. `ALGORITHM_REGISTRY` (`algorithm_id.py:108`) holds `"eatp-v1"` → `RegistryEntry(signature="Ed25519 (RFC 8032)", hash="SHA-256 (FIPS 180-4)", status=ACTIVE)` (`algorithm_id.py:109-114`). `eatp-v1` is the **sole Active** token; `eatp-v1.1`/`eatp-v2`/etc. are Reserved (`algorithm_id.py:28-33`). `coerce_algorithm_id` (exported `signing/__init__.py:39`) + `AlgorithmStatus.ACTIVE` (`algorithm_id.py:82`) give the dispatch-gate primitive N12-CB-04 needs for `kek_commitment_alg = "eatp-v1"`. The hash primitive is resolved from the row's `hash` column — exactly the "compound token, NOT bare `sha-256`" model N12-CB-04 mandates (F-CRYPTO-11 fix).
3. **`alg_id` envelope precedent** — `src/kailash/trust/envelope.py:1388-1482`. `sign_envelope`/`verify_envelope` already carry an optional `alg_id: AlgorithmIdentifier` defaulting to `eatp-v1` (`envelope.py:1397-1399`, `1454-1455`), with the EATP-08 §8 substrate-framed pinned-schema-position model (`alg_id` adds metadata to the surrounding shape, NOT the canonical pre-image, `envelope.py:1404-1412`). This is the exact precedent EATP-11's `hash_anchor` + N12-CB-04 follow.
4. **SLIP-0039 wrapper** — `src/kailash/trust/vault/shamir.py`. `reconstruct(shards, *, passphrase=b"")` (`shamir.py:317`) → `combine_mnemonics` (`shamir.py:392`); `ShamirRitual` dataclass; `generate(...)`. Frozen API surface the binding wraps. **Does NO identity/commitment/foreign-shard check** — it returns whatever the shards combine to (the F-CRYPTO-1 gap N12-CB-02 closes).
5. **Memory-hygiene precedent** — `shamir.py:350-362` documents the consume-and-`del` discipline (`rules/trust-plane-security.md` MUST NOT Rule 3) that N12-IN-05 formalizes.

---

## Net-new surfaces (per spec §3.4 / §4.4 / §6, all confirmed ABSENT)

1. **Per-(`target_handle`, `kek_generation`) commitment registry**, keyed by `kek_commitment_alg` (N12-CB-04(c)) — additive (`vault_kek_recommit` ADDS, never deletes until retire). Sourced/derived from the audited anchor chain, NOT a locally-mutable store.
2. **KCV** — key-free 8-byte/16-hex check value (N12-CB-04(d)); optional Complete-level keyed AEAD over blob associated-data.
3. **Recommit anchor** (`vault_kek_recommit`) + **retire anchor** (`vault_kek_retire`) — additive-migration + sunset; `commitment-alg-mismatch` vs `retired-commitment-alg` vs `kek-commitment-mismatch` are three DISTINCT codes (§4.4 line 250).
4. **`force_stale` gate** (N12-SG-03) — flag default `False`; distinct `vault:restore-stale`/`vault:override` capability + mandatory HELD approval; `vault_key_restore_forced_stale` anchor with named fields `restored_generation` + `overridden_current_generation`, dual-emitted to `safety` tier, sourcing step-6 `shard_commitments` from the **CAPTURED** distribution.
5. **`restore_vault_key`** entrypoint — entirely net-new (no restore surface exists today). Hosts the step 6→7→8 ordered pipeline.
6. **Key-manager generation surface** — `kek_generation:int` monotonic counter + KEK-class tag on `KeyMetadata` (F-SUBSTRATE-1, `kailash-py#630`). Shipped `KeyMetadata` (`key_manager.py:110-118`) carries none of these.
7. **Per-generation denylist** (N12-SG-05) — `revoked-generation` distinct from per-key `KeyMetadata.is_revoked` (`key_manager.py:116`); derived from rotation/denylist anchor chain.
8. **Passphrase provenance** tag + opaque `passphrase_ref` restore-surface parameter + printable-ASCII (32–126) pre-call validator (N12-PP-01).
9. **`BackupReceipt`** serialized blob — carries `kek_generation:int`, `kek_commitment_alg`, the commitment, the KCV, `slip39_params` (incl. `master_secret_bits`), `shard_commitments` (F-XSDK-5 / fix [3]). Net-new; `back_up_vault_key` currently returns bare `List[List[str]]` (`backup.py:53`) and raises `NotImplementedError` (`backup.py:96`).
10. **Audit subtypes + dispatcher** — 8 `vault_*` `EXTERNAL_SIDE_EFFECT` subtypes (F-XSDK-12); `AuditDispatcher.dispatch(anchor, tier="recovery")` named-tier surface is itself net-new (F-SUBSTRATE-2, shipped `dispatch()` keys on `VerificationLevel` per `trust/pact/audit.py`, not a `tier`). [Cross-cluster — flagged, not owned here.]

---

## Key risks / pitfalls

1. **F-CRYPTO-13 canonical-encoding collision (the #1 pitfall).** A bare `H(a||b||...)` concatenation lets `(vault_id='ab', salt='c')` collide with `(vault_id='a', salt='bc')` regardless of secret entropy. The defense is the unambiguous length-delimited `canonical_json_dumps` (JCS) encoding. **The architecture MUST pin the delegate-family `_json.py:149` encoder — NOT the signing-family `serialize_for_signing` (`crypto.py:225`).** The two differ on `ensure_ascii` (`_json.py:172` vs `crypto.py:242`) and are deliberately non-interchangeable (issue #1258). Picking the wrong one passes ASCII-only fixtures and silently diverges cross-SDK on the first non-ASCII `vault_id` — invisible until a real-world unicode tenant id hits the byte-identical V6 guarantee. **Verify the Appendix B golden hex was computed with `ensure_ascii=False` before pinning.**

2. **F-CRYPTO-14 — `vault_salt` is DELETED.** Any architecture or implementation that re-introduces a per-vault salt re-opens the unsatisfiable-V6 gap. The construction commits to `master_secret` directly; `domain_sep` is the only separation. (spec §4.4 line 242.)

3. **Captured-vs-current generation confusion (second/fourth-cycle [1]/[14]/[19]).** The commitment recompute (N12-CB-02(b), step 7) is over the **CAPTURED** generation (the value bound into the commitment), NEVER the vault's current generation. The current-vs-captured ORDINAL comparison is the **separate, later** step 8 (staleness). Conflating them breaks the `force_stale` path: `force_stale` overrides ONLY step 8, and step 7 then PASSES for a legitimate superseded backup precisely because it recomputes over the captured generation. An implementation that recomputes the commitment over the current generation will reject every legitimate old backup. (spec §4.4 line 263, §6 line 454.)

4. **Step-6/7/8 gate ordering is LITERAL and load-bearing (third/fourth cycle [1]/[19]).** Order: **step 6** foreign-shard (`unknown-shard`) → **step 7** commitment/identity authentication (`kek-commitment-mismatch`/`key-identity-mismatch`) → **step 8** ordinal staleness/denylist (`stale-generation`/`revoked-generation`). On the DEFAULT (non-forced) path, a genuine-old relabelled blob is refused at **step 6** with `unknown-shard` (its ciphertexts are not in the consulted current distribution because a KEK rotation re-shards) — NOT at step 7. `kek-commitment-mismatch` (step 7) fires ONLY for a blob whose ciphertexts ARE in the consulted distribution (a current-generation blob with only its generation integer tampered — V3(g)). The third cycle SWAPPED steps 7↔8 to match the prose; an implementation that re-orders these returns the wrong first error and fails cross-SDK determinism. The forced-stale path sources step-6 `shard_commitments` from the CAPTURED distribution so the genuine old set reaches reconstruction. (spec §6 lines 447-454, §9.9 [19] line 692.)

5. **`commitment-alg-mismatch` ≠ `kek-commitment-mismatch` ≠ `retired-commitment-alg` (F-XSDK-10 / fix [5]).** Three distinct codes for three distinct conditions: NO registered commitment under the recorded alg (`commitment-alg-mismatch`); a registered commitment that doesn't match (`kek-commitment-mismatch` = injection); a registered-but-retired entry (`retired-commitment-alg`). A decades-old `eatp-v1` (SHA-256) paper backup MUST still verify after the suite advances to `eatp-v1.1` (SHA-512/256) because the `eatp-v1` row stays registered — collapsing these codes self-inflicts denial-of-recovery on the highest-value secret. The additive registry (N12-CB-04(c)) is what makes this work.

6. **Per-generation denylist vs per-key revocation (F-CRYPTO-6).** `revoked-generation` (N12-SG-05) catches a current-but-compromised KEK and fires **even when the generation equals current** — the ordinal stale guard cannot. Shipped `KeyMetadata.is_revoked` (`key_manager.py:116`) is per-key and per-`KeyMetadata`-row, NOT per-generation and NOT derived from the audited chain. Reusing it would be a category error.

7. **Passphrase is key-stretching, NOT an authenticator (N12-PP-01 / F-CRYPTO-4).** `combine_mnemonics` returns a DIFFERENT MAC-valid secret per passphrase (`shamir.py:392`). The defense against attacker-controlled passphrase substitution is that a wrong passphrase yields a different `master_secret` → a different commitment → mismatch. So provenance MUST be bound into the commitment (it is the 5th tuple field). Printability (32–126) MUST be validated BEFORE the wrapper call (`invalid-passphrase`, deterministic) rather than surfacing the raw library `ValueError` (`shamir.py:317-392` currently surfaces it raw — F-XSDK-6).

8. **Substrate honesty (Ruling 2 — F-SUBSTRATE-1/2).** `kek_generation`, KEK-class metadata, and the named-tier `dispatch()` are REQUIRED net-new surfaces present in NEITHER shipped SDK (`key_manager.py:110-118` has no generation; `trust/pact/audit.py` `dispatch()` keys on `VerificationLevel`). The requirement is NOT weakened — conformance requires the metadata extension (`kailash-py#630`). Architecture must NOT cite these as if they exist today.

---

## Open questions for architecture

1. **Encoder binding (highest priority):** confirm the Appendix B golden commitment/KCV hex was generated with `canonical_json_dumps` (`ensure_ascii=False`, `_json.py:149`) and NOT `serialize_for_signing`. If the fixture used the signing family, the spec's `canonical_json_dumps` citation and the fixture disagree — a blocking cross-SDK divergence to resolve BEFORE implementation. (The audit-anchor `content_signing_bytes` pre-image legitimately uses the signing family; the _commitment_ pre-image does not. Two encoders, two purposes — pin both explicitly.)
2. **Commitment registry storage:** the spec mandates "derivable from the audited anchor chain, not a locally-mutable store" for both the commitment registry (N12-CB-04(c)) and the denylist (N12-SG-05). Does the kailash-py audit-store (`trust/audit_store.py`, `trust/audit_service.py`) expose a query surface to reconstruct per-(handle,gen) commitment sets by folding the anchor chain, or is a derived-cache + fold-on-read pattern needed?
3. **Substrate sequencing:** `kek_generation` counter + KEK-class on `KeyMetadata` (`kailash-py#630`) gates N12-SG-01/02/05 and N12-CB-01 (generation is a commitment tuple field). Does the binding land behind the substrate extension, or ship an adapter that synthesizes generation from the rotation anchor chain until `#630` lands?
4. **Named-tier dispatcher (F-SUBSTRATE-2):** does the binding ship a recovery-tier adapter mapping onto the shipped `VerificationLevel`-keyed `dispatch()` (`trust/pact/audit.py`), or block on the `kailash-py#630` net-new tier surface? The N12-AU-02a fail-closed interlock (recovery tier MUST accept `dispatch()` despite its seal) depends on this.
5. **`BackupReceipt` location + serialization:** does it live in `vault/backup.py` (replacing the `List[List[str]]` return of the current stub, `backup.py:53`)? `rules/eatp.md` mandates `@dataclass` + `to_dict()`/`from_dict()` — confirm the blob's wire form is JCS-canonical for the cross-SDK self-describing guarantee (F-XSDK-5).
6. **Capability axis (cross-cluster dependency):** `vault:restore-stale` / `vault:override` / `vault:retire-alg` / `vault:approve` live on `RoleScope.capabilities` (F-AUTHZ-1/10/11 corrections route the gate to the bound role, NOT `intersect`). This cluster CONSUMES those capabilities but the §4.3 clearance cluster OWNS them — confirm the capability-gate interface before wiring the `force_stale` / retire gates.

---

**Receipt:** This analysis written to
`workspaces/eatp-12-vault-binding-py/01-analysis/02-commitment-and-stale-guard.md`.
All current-state claims grep/read-verified against `src/kailash/trust/**` on
2026-06-14. Empty greps stated explicitly. No source files were edited.
