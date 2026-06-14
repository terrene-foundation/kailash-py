# Cluster E — §7 Conformance Vectors + §12 Golden Fixtures

EATP-12 v1.0 Trust Vault Key-Binding — conformance-gap analysis for the
BYTE-LEVEL conformance surface: §7 conformance vectors (V1–V8) and §12 Appendix
B golden fixtures (NORMATIVE). Read-only audit against shipped `kailash-py` at
`src/kailash/trust/**`, commit checked out on `main` 2026-06-14.

Spec source: `workspaces/eatp-12-vault-binding-py/briefs/eatp-12-v1.0-spec.md`
— §7 lines 470–532, §12 lines 763–929.

**Headline (evidence-first).** The conformant-level vectors (V1–V7) and the
Complete-level vector (V8) describe behaviour over a binding surface that is
almost entirely ABSENT (`back_up_vault_key` is a `NotImplementedError` stub;
`restore_vault_key`, the commitment/KCV/generation/denylist machinery, and every
`subtype=vault_*` audit anchor are net-new — confirmed by siblings Cluster A
`01-substrate-and-input.md` and Cluster C `02-commitment-and-stale-guard.md`).
HOWEVER, the §12 golden-fixture canonical pre-images ARE reproducible TODAY:
the §12.2 KEK-identity commitment hash and the §12.3 KCV both regenerate
byte-identically from the §12.1 fixed inputs using the SHIPPED canonical encoder
`kailash.trust.signing.crypto.serialize_for_signing` (verified inline below).
This means the golden-fixture diff target can be authored and pinned as Tier-1
deterministic vectors NOW, ahead of the binding implementation, exactly as the
EATP-08 precedent did.

**Reproduction receipt (run this session against shipped code):**

```text
$ python3 -c 'serialize_for_signing-equivalent encoder over §12.1 inputs'
commitment pre-image matches spec §12.2 literal: True
sha256 (§12.2 commitment): f325754cc891869ee326b89037571ceb83278562249b1de9ee59348134d9405c   # == spec
kcv first-8-bytes (§12.3):  00051364b85b0a43                                                 # == spec
```

The encoder is `json.dumps(obj, separators=(",", ":"), sort_keys=True,
ensure_ascii=True, allow_nan=False)` — `src/kailash/trust/signing/crypto.py:326`
(`serialize_for_signing`, def at `:225`). This is JCS-compatible (sorted keys,
no whitespace, integers-as-integers) AND ASCII-escaped, matching §12's stated
contract (§12 line 765: "JCS (RFC 8785): UTF-8, sorted keys, no insignificant
whitespace, integers as integers. All hex is lowercase.").

---

## Conformance vector table

One row per V1–V8 sub-vector. "Maps to N12-\*" cites the spec's normative IDs as
written in §7. Test-tier per the repo's 3-tier rule (`rules/testing.md`):
**Tier-1** = deterministic fixture/byte-pin, offline, no real vault;
**Tier-2** = integration against a real key-management substrate + real audit
dispatcher (NO mocking per Tier-2 contract).

| Vector                                                                                    | What it asserts                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | Level      | Maps to N12-\*                                                                                               | Test-tier                                                                                                                                   |
| ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- | ------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------- |
| **V1** default-3-of-5 backup→restore roundtrip                                            | Backup resolves handle internally (no raw KEK over API), `shamir.generate` under pinned params, registers commitment+`kek_commitment_alg`+KCV+`shard_commitments`, dispatcher-mediated `recovery` dispatch, returns `BackupReceipt`; `EXTERNAL_SIDE_EFFECT` anchor (`subtype=vault_key_backup`) carries the closed field set & NEVER shard/KEK bytes; restore from EXACTLY k=3 reconstructs a KEK byte-equal to original; emits `vault_key_restore` anchor                                                                                              | Conformant | IN-01, IN-02, IN-05, CRY-PIN, CB-01/02/03/04, AU-01, AU-02b, CL-02, RT-05, SG (gen==g), FT-02 (4/5 governed) | Tier-2 (roundtrip needs real shamir + handle re-establishment + dispatcher); audit pre-image byte-pin is **Tier-1** (cross-ref §12.4/§12.8) |
| **V2(a)** backup missing `vault:backup`                                                   | Rejected `missing-clearance` BEFORE handle resolved (no KEK materialized); denial anchor `vault_key_backup_denied` → `safety` tier carries principal + missing-cap + OPAQUE unresolved target-handle ref (NOT resolved vault_id/commitment)                                                                                                                                                                                                                                                                                                             | Conformant | CL-02, AU-01                                                                                                 | Tier-2 (clearance gate + dispatcher); denial-anchor pre-image byte-pin **Tier-1** (§12.5)                                                   |
| **V2(b)** restore missing `vault:restore`, 3 valid shards                                 | Rejected `missing-clearance` BEFORE any shard combined (clearance & quorum gates independent)                                                                                                                                                                                                                                                                                                                                                                                                                                                           | Conformant | CL-02                                                                                                        | Tier-2                                                                                                                                      |
| **V2(c)** restore cross-tenant/domain (clearance in A, target in B)                       | Rejected `missing-clearance` on tenant/domain scope, fail-closed (tenant via bound tenant first, then domain via `RoleScope.domain`); capability check reads `RoleScope.capabilities` NOT `DelegateConstraintEnvelope` (permissive envelope still rejected)                                                                                                                                                                                                                                                                                             | Conformant | CL-02a, F-AUTHZ-1                                                                                            | Tier-2                                                                                                                                      |
| **V2-denial-flood** bounded growth, no lost attribution                                   | Denial anchors NOT dropped; under flood emit ONE signed `vault_denial_summary` (`safety` tier) at dispatch-time covering the window: distinct principals/missing-caps sorted-ascending inline up to cap `M`, complete attribution beyond `M` via `principal_set_root` (sorted-hash/Merkle); record size `O(M)` regardless of distinct-principal cardinality; dispatch-time aggregation NOT EATP-09 §4.1 post-hoc compaction                                                                                                                             | Conformant | AU-04, fix[6]/[7]/[8]                                                                                        | Tier-2 (flood behaviour + tier routing); summary pre-image byte-pin **Tier-1** (§12.9)                                                      |
| **V3(a)** stale-gen, `force_stale=False`                                                  | Refused `stale-generation` (clearance+threshold notwithstanding); no KEK re-established                                                                                                                                                                                                                                                                                                                                                                                                                                                                 | Conformant | SG-02                                                                                                        | Tier-2                                                                                                                                      |
| **V3(b)** `force_stale=True`, then with `vault:restore-stale`                             | First refused `missing-clearance` (force_stale needs higher cap); with cap (+HELD where configured) restore PROCEEDS: step-6 foreign-shard check sources commitments from CAPTURED `g` distribution (not current `g+1`) so does NOT `unknown-shard`, step-7 commitment auth PASSES over captured `g`, force_stale overrides ONLY step-8 ordinal staleness; emits distinct `vault_key_restore_forced_stale` anchor to `recovery` DUAL-emitted to `safety`, with `restored_generation=g`/`overridden_current_generation=g+1`/captured holders/commitments | Conformant | SG-03, FT-02(step6), CB(step7), AU-04, fix[2], F-AUTHZ-9                                                     | Tier-2; forced-stale anchor pre-image byte-pin **Tier-1** (§12.11)                                                                          |
| **V3(c)** genuine-old-gen blob relabelled to `g+1`, default path                          | Refused `unknown-shard` at **step 6** (default path sources commitments from CURRENT `g+1`; genuine-old true-`g` ciphertexts absent because rotation re-shards); first code `unknown-shard` NOT `kek-commitment-mismatch`; loud forced-stale anchor NOT emitted; force_stale NOT silently satisfied                                                                                                                                                                                                                                                     | Conformant | FT-02 step6, fix[19]                                                                                         | Tier-2                                                                                                                                      |
| **V3(d)** audit-chain inspection of the rotation                                          | `vault_kek_rotation` anchor present, dispatcher-mediated, chained in `recovery`, recording `g→g+1`, carrying NEW gen re-shard distribution (holders/shard_count/shard_commitments/new commitment)                                                                                                                                                                                                                                                                                                                                                       | Conformant | RT-06, fix[3], F-AUDIT-6/F-BND-5                                                                             | Tier-2; rotation-anchor pre-image byte-pin **Tier-1** (§12.6)                                                                               |
| **V3(e)** current-gen `g+1` on compromised denylist                                       | Refused `revoked-generation` even though gen==current                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   | Conformant | SG-05, F-CRYPTO-6                                                                                            | Tier-2                                                                                                                                      |
| **V3(f)** relabel-to-OLDER `g-1`, default path                                            | Refused `unknown-shard` at **step 6** (same precedence as V3c; relabel direction immaterial on default path — step 6 consults current distribution regardless of claimed label); single canonical first code `unknown-shard` (fix[19] corrects prior over-claim of `kek-commitment-mismatch`)                                                                                                                                                                                                                                                           | Conformant | FT-02 step6, fix[19]                                                                                         | Tier-2                                                                                                                                      |
| **V3(g)** generation-integer tamper, ciphertexts ARE current `g+1`                        | Refused `kek-commitment-mismatch` at **step 7** (ciphertexts in consulted current distribution → step6 PASSES; step7 recomputes commitment over claimed tampered `g`, finds no registered commitment over `(secret,g)`) — the case the commitment check defends                                                                                                                                                                                                                                                                                         | Conformant | CB-02, F-CRYPTO-3                                                                                            | Tier-2                                                                                                                                      |
| **V4(a)** amicable holder rotation, restore from NEW set                                  | New-set restore succeeds + reconstructs KEK; `vault_holder_rotation` anchor records old/new {k,n}, departing holder, new distribution, `kek_generation=g` (unchanged for amicable), new commitments, `for_cause=false`                                                                                                                                                                                                                                                                                                                                  | Conformant | RT-03                                                                                                        | Tier-2                                                                                                                                      |
| **V4(b)** restore from OLD set after rotation                                             | OLD-set restore MUST fail `unknown-shard` (foreign/old — NOT `corrupted-shard`), or `mixed-shard-set` if mixed, even though old shards remain SLIP-0039-valid                                                                                                                                                                                                                                                                                                                                                                                           | Conformant | F-XSDK-4, F-BND-4                                                                                            | Tier-2                                                                                                                                      |
| **V4(c)** for-cause revocation                                                            | Triggers generation-advancing KEK-rotation: SINGLE `vault_kek_rotation` anchor carries `for_cause=true`, `prior_kek_generation=g`, `kek_generation=g+1`, AND new re-shard distribution (one anchor, no two-anchor split); departed holder's retained `g` shards become stale (refused by SG-02)                                                                                                                                                                                                                                                         | Conformant | SH-04, fix[4], F-AUTHZ-5, F-CRYPTO-8                                                                         | Tier-2                                                                                                                                      |
| **V5(a)** 2 valid shards                                                                  | `insufficient-shards` (EATP-10 code, NOT `insufficient-threshold`)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      | Conformant | FT-01                                                                                                        | Tier-2                                                                                                                                      |
| **V5(b)** 3 shards, one corrupt SLIP-0039 MAC                                             | `corrupted-shard` (integrity only)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      | Conformant | FT-01                                                                                                        | Tier-2                                                                                                                                      |
| **V5(c)** homogeneous self-generated foreign 3-of-5                                       | `unknown-shard` — caught by `shard_commitments` check BEFORE reconstruction (closes "mixed-identifier" gap)                                                                                                                                                                                                                                                                                                                                                                                                                                             | Conformant | CB-03, F-CRYPTO-2                                                                                            | Tier-2                                                                                                                                      |
| **V5(d)** 3 shards incl. one revoked holder                                               | `revoked-holder`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | Conformant | FT-01                                                                                                        | Tier-2                                                                                                                                      |
| **V5(e)** fully-valid 3-shard, caller lacks `vault:restore`                               | `missing-clearance`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     | Conformant | CL-02                                                                                                        | Tier-2                                                                                                                                      |
| **V5(f)** mixed: one foreign + two valid                                                  | `mixed-shard-set` (step 5 fires before step-6 commitment check), distinct from `corrupted-shard`                                                                                                                                                                                                                                                                                                                                                                                                                                                        | Conformant | FT-02 step5                                                                                                  | Tier-2                                                                                                                                      |
| **V5(g)** k+1=4 valid shards                                                              | per deployment's FT-02 choice: `too-many-shards` OR deterministic-trim success — PINNED, not SDK-dependent                                                                                                                                                                                                                                                                                                                                                                                                                                              | Conformant | FT-02, F-XSDK-2                                                                                              | Tier-2 + **Tier-1 pin** of the chosen branch                                                                                                |
| **V5(h)** k+1=4 foreign shards                                                            | reject branch → `too-many-shards` (step3 before step6); trim branch → trim-to-k then `unknown-shard` (step6); PINNED canonical gate order                                                                                                                                                                                                                                                                                                                                                                                                               | Conformant | FT-02, F-XSDK-13                                                                                             | Tier-2 + **Tier-1 pin**                                                                                                                     |
| **V6(a)** cross-SDK reproducibility (the byte-parity core)                                | Same pinned `(secret, ritual, passphrase, extendable, iteration_exponent, master_secret_bits)` → any 3-of-5 serialized shards from impl A reconstruct in B byte-equal & vice-versa; **KEK-identity commitment byte-identical across A/B**; **KCV byte-identical**; **canonical audit-envelope pre-image byte-identical, verified vs §12 golden hex**; mnemonic words DIFFER (fresh random id per `generate()`) — guarantee is at secret/commitment/KCV/audit-canonical level, NOT raw-mnemonic                                                          | Conformant | CRY-PIN, CB-01, CB-04(d), AU-03/AU-04, F-XSDK-9, F-CRYPTO-9                                                  | **Tier-1** (commitment+KCV+audit pre-image are deterministic byte-pins — reproducible NOW); shard-reconstruct roundtrip is Tier-2           |
| **V6(b)** divergent params (`extendable`/`iteration_exponent`/`master_secret_bits`)       | MUST fail reproducibility → mapped `parameter-mismatch` (defined FT-01 code; SLIP-0039 "identifier parameters don't match")                                                                                                                                                                                                                                                                                                                                                                                                                             | Conformant | FT-01, F-XSDK-1, F-XSDK-10                                                                                   | Tier-2 (real SLIP-0039 param mismatch)                                                                                                      |
| **V6(c)** restore recording an alg with NO registered commitment at captured gen          | MUST fail `commitment-alg-mismatch` (NOT silent success, NOT injection code `kek-commitment-mismatch`)                                                                                                                                                                                                                                                                                                                                                                                                                                                  | Conformant | CB-04(b), F-CRYPTO-11                                                                                        | Tier-2                                                                                                                                      |
| **V6(d)** legit cross-hash restore after suite advanced to alg Y via `vault_kek_recommit` | MUST succeed (commitment recomputed under backup's RECORDED `kek_commitment_alg`, compared to registered commitment under that same alg); relabel/injection still fails; additive registry keeps both `C_X` and `C_Y` live                                                                                                                                                                                                                                                                                                                              | Conformant | CB-04(c), fix[2], F-XSDK-10                                                                                  | Tier-2                                                                                                                                      |
| **V6(e)(i)** old `eatp-v1`-recorded backup after `vault_kek_recommit` to `eatp-v1.1`      | MUST succeed (recompute under recorded `eatp-v1` vs `C_X`, still live in additive per-(target_handle,g) registry)                                                                                                                                                                                                                                                                                                                                                                                                                                       | Conformant | CB-04(c), fix[2]                                                                                             | Tier-2                                                                                                                                      |
| **V6(e)(ii)** backup recording `eatp-v2.slh-dsa`, never registered/recommitted at `g`     | MUST fail `commitment-alg-mismatch` (NOT `kek-commitment-mismatch`, NOT silent success)                                                                                                                                                                                                                                                                                                                                                                                                                                                                 | Conformant | CB-04(b)                                                                                                     | Tier-2                                                                                                                                      |
| **V7(a)** audit envelope content + mediation                                              | Both backup & restore anchors present in `recovery` (AU-02), carry `alg_id` as pinned-FIRST `event_payload.alg_id` field covered by `content_signing_bytes` pre-image; required `event_payload` fields per AU-04; fixture confirms NO shard mnemonic / KEK byte / data-key byte / passphrase / per-holder wrapping secret anywhere (any appearance = HIGH); both enrolled via `dispatch()` (non-dispatch direct write detected as non-chained) & committed by next global anchor                                                                        | Conformant | AU-02/AU-03/AU-04, N9-D-01, N9-G-01, F-AUDIT-1/8                                                             | Tier-2 (mediation + chaining); secrets-absence + alg_id-first byte-pin **Tier-1** (§12.4)                                                   |
| **V7(b)** adversarial KEK-leak probe                                                      | Plaintext KEK appears in NO return value, log line, or receipt field                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    | Conformant | IN-05, F-BND-9                                                                                               | Tier-2                                                                                                                                      |
| **V7(c)** dispatcher fails after reconstruction, before install                           | Restore MUST ABORT: reconstructed KEK NOT installed, `del`-ed; no active handle returned; outage surfaced as RETRYABLE operational incident (not permanent brick)                                                                                                                                                                                                                                                                                                                                                                                       | Conformant | AU-02b fail-closed + bounded degradation, F-AUDIT-2, F-LIVE-2                                                | Tier-2 (fault injection)                                                                                                                    |
| **V7(d)** restore vs indefinitely-sealed `recovery` tier                                  | Restore MUST succeed (indefinite seal blocks `rotate()`/compaction, NOT security-critical `dispatch()`; EATP-09 §3.4 "further restricts" escape MUST NOT apply to `recovery` for vault anchors)                                                                                                                                                                                                                                                                                                                                                         | Conformant | AU-02a, F-LIVE-1                                                                                             | Tier-2                                                                                                                                      |
| **V7(e)** host-clock skew during forced-stale                                             | Host fast-forward/backdate MUST NOT alter recorded forced-stale anchor `timestamp` (trust-anchored per AU-04a); where trust-anchored time unavailable field reads `unverified` with `time_attested:false`                                                                                                                                                                                                                                                                                                                                               | Conformant | AU-04a, F-TEMP-3                                                                                             | Tier-2; degraded-time pre-image byte-pin **Tier-1** (§12.10)                                                                                |
| **V7(f)** restricted `safety` tier (sealed-at-rotation) under denial-flood + forced-stale | Denial anchors + `vault_denial_summary` MUST NOT be dropped; forced-stale dual-emit either lands or yields RETRYABLE operational incident surfaced to operator (never silent gap, never permanent brick); EATP-09 §3.4 escape MUST NOT apply to `safety` for these vault anchors                                                                                                                                                                                                                                                                        | Conformant | AU-02a `safety` extension, fix[9]                                                                            | Tier-2                                                                                                                                      |
| **V8(a)** revoked-holder restore under per-holder wrapping                                | Fail `revoked-holder`; revocation MUST NOT drop un-revoked set below `k`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                | Complete   | SH-02, SH-03                                                                                                 | Tier-2 (Complete only)                                                                                                                      |
| **V8(b)** data-key backup; cross-vault restore                                            | data-key backup → `not-a-kek`; cross-vault restore → `key-identity-mismatch`                                                                                                                                                                                                                                                                                                                                                                                                                                                                            | Complete   | IN-02, CB-02                                                                                                 | Tier-2                                                                                                                                      |
| **V8(c)** unregistered-holder backup                                                      | Fail `unregistered-holder`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              | Complete   | SH-01, F-AUTHZ-6                                                                                             | Tier-2                                                                                                                                      |
| **V8(d)** restore without HELD approver; approver==requester                              | Both fail `missing-clearance` (approval token absent from signed `event_payload`; self-approval rejected)                                                                                                                                                                                                                                                                                                                                                                                                                                               | Complete   | CL-03, F-AUTHZ-7                                                                                             | Tier-2                                                                                                                                      |
| **V8(e)** in-cooling-off second unsupervised restore + local-clock fast-forward           | Require HELD approver or reject `missing-clearance`; local-clock fast-forward MUST NOT lift suspension (trust-anchored window)                                                                                                                                                                                                                                                                                                                                                                                                                          | Complete   | CL-04, F-AUTHZ-4, F-TEMP-2                                                                                   | Tier-2                                                                                                                                      |
| **V8(f)** backup lacking ceremony witness token; witness==requester                       | Rejected at Complete; self-witness fails                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                | Complete   | CL-05, F-AUTHZ-12                                                                                            | Tier-2                                                                                                                                      |

Conformance-level note (§7 line 472): V1–V7 MUST pass at **Conformant**; V8 is
REQUIRED only at **Complete**. A Conformant (non-Complete) implementation is NOT
required to pass V8.

---

## Golden fixture inventory (§12)

Each §12.N fixture is a NORMATIVE byte-identical diff target. "Byte-identical
must-match" names the literal hex/pre-image the §12 subsection pins. "Cross-SDK
parity surface" = whether kailash-rs MUST reproduce the same bytes (the
release-coordination gate, V6).

| Fixture (§12.N)                                                         | Subtype / artifact                                                           | What must be byte-identical                                                                                                                                                                                                                                 | Cross-SDK parity?                             |
| ----------------------------------------------------------------------- | ---------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------- |
| **§12.1** fixed inputs                                                  | seed tuple (not an anchor)                                                   | All §12.1 field values verbatim — every derived hash depends on them; materialized at `master_secret_bits=128`                                                                                                                                              | yes (both SDKs seed from these)               |
| **§12.2** KEK-identity commitment (CB-01)                               | commitment pre-image + SHA-256                                               | pre-image `{"domain_sep":"EATP-12/kek-identity-commitment/v1",...}` AND hash `f325754c…d9405c`                                                                                                                                                              | **YES** — V6 anti-injection anchor            |
| **§12.3** KCV (CB-04(d))                                                | KCV pre-image + first-8-bytes-of-SHA-256                                     | pre-image `{"domain_sep":"EATP-12/kcv/v1",...}` AND `00051364b85b0a43`                                                                                                                                                                                      | **YES** — V6 KCV byte-pin                     |
| **§12.4** outcome anchor `vault_key_backup`                             | canonical `event_payload` JCS + `content_signing_bytes` signed pre-image hex | the full `event_payload` object literal AND the lowercase-hex signed pre-image (`7b226576656e74…`) — `alg_id` pinned-FIRST in payload; top-level wrapper JCS-sorted to `event_payload`,`event_type`,`signer_delegate_id` (fix[17])                          | **YES** — V6 audit-canonical-form diff target |
| **§12.5** denial anchor `vault_key_restore_denied` (attested)           | canonical `event_payload` + signed pre-image hex                             | denial payload (NO resolved vault_id/commitment/ritual; `time_attested:true`+`timestamp`) AND hex                                                                                                                                                           | yes (denial byte-identical diff target)       |
| **§12.6** outcome anchor `vault_kek_rotation`                           | canonical `event_payload` + signed pre-image hex                             | gen-advance + re-shard distribution, `for_cause:false`, `kek_generation:8`, NO `kcv`, gen-8 commitment `7c6bb84f…a842` over rotated secret `ffeeddcc…1100`                                                                                                  | yes                                           |
| **§12.7** outcome anchor `vault_kek_recommit`                           | canonical `event_payload` + signed pre-image hex                             | from-to pair, `kek_generation` unchanged, NO re-shard fields, illustrative `new_kek_identity_commitment` (`aa..`)                                                                                                                                           | yes                                           |
| **§12.8** outcome anchor `vault_key_restore` (fix[18]/[19])             | canonical `event_payload` + signed pre-image hex                             | restore-class shape: ritual-creation fields ({k,n}/kcv/slip39_params/side_channel_hardened) STRUCK; holders/shard_count/shard_commitments copied from latest backup (§12.4 values) NOT presenting subset; `re_established_handle_ref`, `generation_checked` | yes                                           |
| **§12.9** denial-summary anchor `vault_denial_summary` (fix[6]/[8])     | canonical `event_payload` + signed pre-image hex                             | windowed summary, `safety` tier, `distinct_principals`/`distinct_missing_capabilities` sorted-ascending, illustrative `principal_set_root` (`ff..`), `coalesced_count:1024`, window_start/window_end                                                        | yes                                           |
| **§12.10** denial anchor `unverified` time (fix[13])                    | canonical `event_payload` + signed pre-image hex                             | degraded-time variant of §12.5: `time_attested:false` + `timestamp:"unverified"` (NOT omitted, NOT null)                                                                                                                                                    | yes                                           |
| **§12.11** outcome anchor `vault_key_restore_forced_stale` (fix[2]/[7]) | canonical `event_payload` + signed pre-image hex                             | `restored_generation:6`, `overridden_current_generation:7`, `kek_generation==generation_checked==restored_generation==6`, holders/commitments from CAPTURED gen-6 distribution, gen-6 commitment `b7e52b4d…028edf` over §12.1 KEK captured at gen 6         | yes                                           |

**Reproducibility note (§12 line 929):** "A conformant implementation
regenerating these pre-images from the §12.1 inputs MUST obtain byte-identical
results; any divergence (key order, number form, field inclusion, encoding) is a
cross-SDK non-conformance under V6." §12.2/§12.3 are reproducible independent of
the audit substrate (confirmed this session — both reproduce via shipped
`serialize_for_signing`).

---

## The fixed inputs (§12.1 transcribed verbatim — seeds every fixture)

```
master_secret (128-bit, hex) : 00112233445566778899aabbccddeeff
vault_id                     : vault:fixture-0001
kek_generation               : 7
passphrase_provenance        : vault-derived:v1
ritual                       : ShamirRitual(threshold=3, total_shards=5)
holders                      : [holder:h1, holder:h2, holder:h3, holder:h4, holder:h5]
slip39_params                : extendable=true, iteration_exponent=1, group_threshold=1, master_secret_bits=128
alg_id (deployment)          : eatp-v1
signer_delegate_id           : delegate:vault-signer-00
principal (requester)        : delegate:requester-01
timestamp (trust-anchored)   : 2026-06-12T00:00:00Z
```

Supplementary fixed values used by derived fixtures (from §12.6/§12.11 prose):

- The five `shard_commitments` in the fixture are placeholder ciphertext-hash
  stand-ins (`aa..`,`bb..`,`cc..`,`dd..`,`ee..`, each 32 bytes / 64 hex). A live
  backup substitutes real SHA-256 ciphertext hashes. The cross-SDK guarantee is
  at the commitment/KCV/audit-canonical level, NOT the raw-mnemonic level
  (SLIP-0039 emits a fresh random identifier per `generate()`).
- `kek_commitment_alg = "eatp-v1"` — the EATP-08 §3.3 registry token whose Hash
  column resolves to SHA-256 (fix[11]); recorded alg string is `"eatp-v1"`, hash
  primitive is SHA-256.
- §12.6 rotated (gen-8) secret: `ffeeddccbbaa99887766554433221100` (illustrative
  rotated KEK distinct from the gen-7 fixture KEK) → gen-8 commitment
  `7c6bb84f453b66583bc68d9815c6b7ffa87d4afd56e2770e57687507f359a842`.
- §12.11 forced-stale: gen-6 commitment over §12.1 KEK captured at gen 6 →
  `b7e52b4d35a951df41f3c2b7d50edf20dbd92ed829308cd13a221113ce028edf`.

**128-vs-256 pin (§12 line 787):** the fixture is materialized at the 128-bit
master-secret length; `slip39_params.master_secret_bits = 128` is baked into the
§12.2 commitment, §12.3 KCV, and §12.4 signed pre-image. V6's input tuple pins
`master_secret_bits = 128` to match. 256-bit is the other legal value (§4.1's
`{128,256}` set); a future re-materialization at 256-bit would require
regenerating EVERY hash in Appendix B and re-pinning V6, and MUST NOT silently
re-open the 128-vs-256 divergence.

---

## Test architecture recommendation

Per the repo's 3-tier rule (`rules/testing.md`) and the EATP-08 precedent
(`tests/regression/test_eatp08_alg_id_canonical_vectors.py` +
`tests/test-vectors/eatp08-alg-id-canonical.json`):

**Tier-1 deterministic fixtures (author NOW, independent of binding impl).** The
§12 golden pre-images are pure functions of the §12.1 inputs + the canonical
encoder. They can and SHOULD be authored as a JSON vector file + a regression
test BEFORE `back_up_vault_key`/`restore_vault_key` exist, exactly as EATP-08
did. Recommended split:

1. **`tests/test-vectors/eatp12-vault-canonical.json`** — vendored canonical
   vector file (the §12 golden fixture), following the
   `eatp08-alg-id-canonical.json` shape (`contract`, `version`, `spec_ref`,
   `cross_sdk_sibling`, plus a `fixtures` array of `{section, subtype,
canonical_event_payload, signed_preimage_hex}` and the `commitment`/`kcv`
   pre-image+hash pins). This file is the cross-SDK diff target kailash-rs
   VENDORS byte-for-byte (`cross-sdk-inspection.md` Rule 4a — vendored, NOT
   re-authored).
2. **`tests/regression/test_eatp12_vault_canonical_vectors.py`** — a regression
   test that, for EACH §12 fixture: (a) re-canonicalizes the `event_payload`
   via `serialize_for_signing` and asserts byte-equality with the pinned
   canonical JSON; (b) wraps it in `{"event_payload":…,"event_type":…,
"signer_delegate_id":…}`, re-canonicalizes the TOP-LEVEL wrapper (fix[17]
   JCS-sort), and asserts the UTF-8 hex == the pinned `signed_preimage_hex`;
   (c) for §12.2/§12.3, recomputes the SHA-256 (and first-8-bytes for KCV) from
   the pre-image and asserts == the pinned hash. These three are pure
   deterministic byte-pins — Tier-1, offline, no real vault. **They are
   authorable this session against shipped code** (the encoder exists; §12.2 and
   §12.3 already verified to reproduce).
   - Use STRICT-xfail (`@pytest.mark.xfail(strict=True)`) ONLY for the subset
     that depends on binding constants not yet in code (e.g. the `domain_sep`
     literals if/when they move into a vault module); the pure-encoder pins
     (commitment/KCV/audit pre-image from inline inputs) need NO xfail because
     they reproduce today. Per `rules/testing.md` § "Deferred-Implementation
     Conformance Vectors Use xfail-Strict": any pin that asserts behaviour the
     binding does not yet enforce MUST be strict-xfail (auto-fails XPASS when the
     impl catches up), NOT skip/delete.
3. **The `alg_id`-pinned-FIRST + secrets-absence assertions (V7a)** are
   structural Tier-1 checks over the canonical `event_payload`: assert the
   serialized payload's first key is `alg_id` per AU-02/AU-03 (NOT the literal
   JCS-first-field form of D3 — fix[17]/F-AUDIT-8), and assert NO substring of
   any shard mnemonic / KEK byte / passphrase / per-holder wrapping secret
   appears. Grep-style absence is acceptable Tier-1 here because the fixture's
   secret material is fixed and known.

**Tier-2 integration (requires the binding + real substrate; gate on impl).**
Every V1–V8 BEHAVIOURAL assertion (roundtrip reconstruction, clearance/quorum
gates, gate-ordering of FT-02 step3/5/6/7/8, dispatcher-mediated audit
chaining + tier routing, fail-closed dispatcher-failure abort, sealed-tier
behaviour, trust-anchored-time invariance, holder rotation, for-cause
KEK-rotation, V8 witness/HELD-approver/cooling-off) is Tier-2: it needs a real
SLIP-0039 shamir (`src/kailash/trust/vault/shamir.py` exists), a real trusted
module that re-establishes the KEK behind an opaque handle, and a real
`AuditDispatcher` over `recovery`+`safety` tiers (NO mocking per Tier-2
contract). These tests land WITH the implementation shards, not ahead.
A `vault_key_backup`/`vault_key_restore` Tier-2 roundtrip is ALSO the
orphan-detection wiring test (`orphan-detection.md` Rule 1/2) for the
backup/restore facade + the commitment/KCV managers.

**Crypto-pair round-trip (orphan-detection.md Rule 2a).** backup→restore is a
seal/unseal pair: a Tier-2 test MUST round-trip through the facade (call backup,
feed its output to restore, assert the reconstructed KEK byte-equals the
original — V1's core assertion), NOT two isolated unit tests that could drift.

---

## Cross-SDK byte-parity surface (the release-coordination gate)

The fixtures that MUST match kailash-rs byte-for-byte — the V6 cross-SDK
contract and the release-coordination gate — are:

| Surface                                | §12 anchor                       | Why it's the gate                                                                                                                                                                                                                                                  |
| -------------------------------------- | -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **KEK-identity commitment**            | §12.2 (`f325754c…`)              | V6(a) anti-injection anchor — MUST be byte-identical across A/B for same `(domain_sep, vault_id, kek_generation, secret, passphrase_provenance)` under recorded `kek_commitment_alg`. Per-shard ciphertext hashes are NOT required to match (F-XSDK-9/F-CRYPTO-9). |
| **KCV**                                | §12.3 (`00051364b85b0a43`)       | V6(a) CB-04(d) — byte-identical across A/B for same `(vault_id, generation, secret)`.                                                                                                                                                                              |
| **Canonical audit-envelope pre-image** | §12.4–§12.11 signed-preimage hex | V6(a) AU-03/AU-04 — the `content_signing_bytes` pre-image of EACH `vault_*` payload MUST be byte-identical across A/B, verified vs the materialized §12 golden hex. This is the diff target both SDKs reproduce.                                                   |

Per `cross-sdk-inspection.md` Rule 4 (pin ≥3 byte-vectors + sentinels) and
Rule 4a (sibling-canonical fixtures vendored, NOT re-authored): kailash-py is
the canonical AUTHOR of `eatp12-vault-canonical.json` (first SDK to materialize
EATP-12 v1.0 §12); kailash-rs VENDORS the same file byte-for-byte. The encoder
parity already holds at the substrate level — `trust/_json.py` documents the
deliberate signing-encoder divergence: the SIGNING encoder
`serialize_for_signing` emits ASCII-escaped (`ensure_ascii=True`), and §12's
"All hex is lowercase / JCS" contract is consistent with that ASCII-escaped
form (verified: §12.2/§12.3 reproduce). kailash-rs MUST reproduce the SAME
ASCII-escaped JCS bytes (serde_json with sorted keys + `\uXXXX` escaping),
NOT raw-UTF-8 — this is the single highest-risk cross-SDK divergence point and
MUST be an explicit row in the release-coordination checklist.

Cross-SDK divergence sentinels to pin (per Rule 4): include at least the
empty/degraded cases the spec already enumerates — §12.10 `timestamp:"unverified"`
(NOT null, NOT omitted) and the §12.6 NO-`kcv`-on-rotation-anchor shape — as
explicit byte-pins, because field-INCLUSION divergence (a rotation anchor that
wrongly carries `kcv`, a degraded anchor that omits `timestamp`) is the
most-likely silent cross-SDK drift and §12 line 929 names "field inclusion" as a
non-conformance class.

---

## Open questions for architecture

1. **Where do the `domain_sep` literals live?** §12.2/§12.3 pin
   `"EATP-12/kek-identity-commitment/v1"` and `"EATP-12/kcv/v1"`. These reproduce
   today from inline inputs, but the binding MUST source them from a single
   module constant (not re-typed at each call site) so the Tier-1 pin and the
   production path share one source of truth. Recommend a
   `kailash.trust.vault` constants module; the pin test imports it (the
   EATP-08 test imports `ALGORITHM_DEFAULT`/`ADOPTION_DATE_PARSED` — same shape).
2. **Which canonical encoder is authoritative for `content_signing_bytes`?**
   §12 says JCS + lowercase-hex. The shipped `serialize_for_signing`
   (ASCII-escaped) reproduces §12.2/§12.3. ARCHITECTURE MUST confirm the audit
   `content_signing_bytes` path uses `serialize_for_signing` (ASCII-escaped),
   NOT the `delegate.*` raw-UTF-8 `canonical_json_dumps` — these two encoders
   diverge on non-ASCII (`trust/_json.py` documents this deliberately, issue
   #1258). All §12 fixtures are ASCII-only, so the divergence is invisible in the
   golden fixture itself — a TRAP: a future non-ASCII vault_id/principal would
   diverge silently. Recommend a sentinel fixture with a non-ASCII principal to
   force the encoder choice to be tested. **This is a flagged risk, not yet
   resolved by the fixture.**
3. **FT-02 deployment choice (V5g/V5h) — reject vs trim.** §7 says the
   too-many-shards behaviour is "per the deployment's N12-FT-02 choice … pinned,
   not SDK-dependent." ARCHITECTURE MUST pick ONE branch for kailash-py AND pin
   it (both SDKs return the same first code, F-XSDK-13). The §12 fixture does NOT
   materialize V5g/V5h, so the choice is unpinned by the golden fixture — an open
   decision the Tier-1 vector file should record explicitly once chosen.
4. **Anchor field-ordering verification mechanism.** The §12 signed pre-images
   bake the JCS top-level wrapper sort (fix[17]: `event_payload`,`event_type`,
   `signer_delegate_id`). The production `content_signing_bytes(event_type,
event_payload, signer_delegate_id)` takes args in a DIFFERENT order than the
   byte order (§12 line 767). The Tier-1 test MUST assert the production
   function re-sorts the wrapper (not relies on arg order) — recommend the test
   call the real `content_signing_bytes` once it exists and diff vs §12 hex,
   converting the pure-data pin into a behavioural pin at that point (strict-xfail
   until then).
5. **`principal_set_root` algorithm (V2-denial-flood / §12.9).** §12.9 uses an
   illustrative `ff..` stand-in; the spec says "sorted-hash/Merkle digest over
   the full distinct-principal set" but does NOT pin the exact construction.
   This is a cross-SDK parity hazard (two SDKs MUST agree on the digest), yet the
   golden fixture cannot pin it (stand-in only). ARCHITECTURE MUST define the
   exact `principal_set_root` construction AND add a real (non-stand-in) byte
   vector for it, or V2-denial-flood cross-SDK parity is untestable.
6. **Shard-commitment hash domain.** The fixture uses `aa..`/`bb..` placeholders;
   a live `shard_commitment` is "the real SHA-256 ciphertext hash." ARCHITECTURE
   MUST define exactly what is hashed (the serialized SLIP-0039 share bytes? the
   raw ciphertext?) so the CB-03 foreign-shard check (V3c/V3f/V5c) is reproducible
   — this is NOT pinned by §12 (placeholders) and is load-bearing for V5c's
   "caught before reconstruction" guarantee.

---

**File written:** `workspaces/eatp-12-vault-binding-py/01-analysis/03-conformance-vectors-and-fixtures.md`
(this file). Existence-checked implicitly by the Write tool succeeding.
