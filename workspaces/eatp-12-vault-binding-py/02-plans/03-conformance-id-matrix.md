# EATP-12 v1.0 — Per-Conformance-ID → Shard Assertion Matrix

Closes **HIGH-5** (redteam Round 1): every N12-\* conformance ID gets its own row + primary-owner shard. **Range-notation is BLOCKED** — one row per ID + sub-clause, à la `skills/spec-compliance/SKILL.md`. This is the gate that no Conformant-mandatory ID is orphaned.

**Source of IDs:** `briefs/eatp-12-v1.0-spec.md` (929-line normative spec). 54 unique IDs (incl. lettered sub-clauses). Per-ID glosses + conformance levels were re-derived directly from the spec text (read-only extraction, 2026-06-14).

**Shard legend (revised wave plan — see `01-architecture-and-waves.md` §4):**

| Shard | Wave | Scope                                                                                                                                    |
| ----- | ---- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| F1    | 1    | §3.4 substrate: `key_class{KEK,DATA}`, monotonic `kek_generation`                                                                        |
| F2    | 1    | core DTOs (VaultKeyHandle, Backup/RestoreReceipt, ClearanceContext, PassphraseRef, HolderId)                                             |
| FT    | 1    | **(NEW)** closed `N12FT01Error` enum (single source of truth) + wrapper→code map + FT-02/FT-03 ordered-gate pure-function **skeletons**  |
| C1    | 1    | commitment (CB-01) + KCV (CB-04(d)) computation, **ASCII** byte-pinned; passphrase + key-id bound into commitment                        |
| T1    | 1    | §12.1–12.3 Tier-1 fixtures (inputs + commitment + KCV), **ASCII only**                                                                   |
| D1    | 2    | EATP-09 named-tier dispatcher **adapter** (routing, DispatchReceipt, fail-closed interlock)                                              |
| D2    | 2    | audit **envelope schema** (vault\_\* subtypes, per-subtype field schema, trust-anchored time) + §12.4–12.11 anchor-body fixtures (ASCII) |
| I1    | 2    | handle-based input surface (IN-01..05) + ritual/param-pinning entry gates (TH-01, CRY-PIN family)                                        |
| C2a   | 3    | commitment **registry** + recompute-under-recorded-alg + 3-way code discrimination + CB-03 foreign-shard                                 |
| C2b   | 3    | recommit (additive) + retire + FT-03 write-path **wiring** + EATP-08 sunset                                                              |
| C3    | 3    | stale-generation guard (SG family) + FT-02 8-step gate-order **wiring** + RT-05 restore→D6 trigger                                       |
| B1    | 4    | clearance gate (CL-01/02/02a) + CL-04 cooling-off suspension                                                                             |
| B2    | 4    | holder registry (SH-01) + k-floor-no-silent-drop (SH-03)                                                                                 |
| R1    | 5    | rotation (RT-01/02/03/04/06) + for-cause generation-advance (SH-04)                                                                      |
| X1    | 5    | Complete-level optional (CL-03/03(c)/05, SH-02)                                                                                          |
| T2    | 6    | V1–V8 Tier-2 conformance vectors                                                                                                         |
| S1    | 6    | `specs/trust-crypto.md` §30 + workspace specs (post-code)                                                                                |

Co-ownership notation: **primary** shard owns the ID's core behavior; a `+X` co-owner wires a recording/binding half elsewhere. FT-02/FT-03 split skeleton (FT) vs wiring (C3/C2b) per CRIT-2.

---

## The matrix (54 rows)

| ID             | §      | Level                                       | Requirement (gloss)                                                                                                                            | **Primary shard** | Co-owner                                   |
| -------------- | ------ | ------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- | ----------------- | ------------------------------------------ |
| N12-AU-01      | §4.5   | Conformant                                  | Every pass writes one outcome anchor; every denial a distinct denial anchor; shard/KEK excluded                                                | **D2**            | all anchor-writers                         |
| N12-AU-01a     | §4.5   | Conformant                                  | Anchor is well-formed EATP Audit Anchor, chains within tier via `previous_anchor_hash`                                                         | **D2**            | —                                          |
| N12-AU-02      | §4.5   | Conformant                                  | Outcome anchors dispatch to `recovery` tier via `AuditDispatcher.dispatch()` under `event_payload.alg_id`                                      | **D1**            | —                                          |
| N12-AU-02a     | §4.5   | Conformant                                  | recovery/safety tier accepts `dispatch()` despite seal (fail-closed ordering never bricks restores)                                            | **D1**            | —                                          |
| N12-AU-02b     | §4.5   | Conformant                                  | KEK MUST NOT go active / shards MUST NOT release until anchor dispatched (fail-closed interlock)                                               | **D1**            | C2a, C3 (restore path)                     |
| N12-AU-03      | §4.5   | Conformant                                  | Pre-image = `content_signing_bytes`; rides `EXTERNAL_SIDE_EFFECT` + validated `vault_*` subtype                                                | **D2**            | —                                          |
| N12-AU-04      | §4.5.1 | Conformant                                  | Exact per-subtype field names/types/encodings; matched by Appendix B golden fixture                                                            | **D2**            | —                                          |
| N12-AU-04a     | §4.5.1 | Conformant                                  | Forced-stale/denylist timestamps trust-anchored (EATP-10 §14); `"unverified"` sentinel when unavailable                                        | **D2**            | C3 (forced-stale), B1 (CL-04 clock)        |
| N12-CB-01      | §4.4   | Conformant                                  | Every backup registers KEK-identity commitment over canonical tuple (vault_id+gen+secret+passphrase)                                           | **C1**            | —                                          |
| N12-CB-02      | §4.4   | Conformant                                  | Restore verifies commitment; reject `kek-commitment-mismatch`/`key-identity-mismatch` before any key                                           | **C2a**           | —                                          |
| N12-CB-02(b)   | §4.4   | Conformant                                  | Recompute over backup's **captured** generation, never vault's current                                                                         | **C2a**           | —                                          |
| N12-CB-02(d)   | §4.4   | Conformant                                  | Reject `key-identity-mismatch` if target_handle vault identity ≠ shard set's captured identity                                                 | **C2a**           | —                                          |
| N12-CB-03      | §4.4   | Conformant                                  | Check presented shards against distribution's `shard_commitments`; reject `unknown-shard` pre-reconstruction                                   | **C2a**           | D1 (chain source)                          |
| N12-CB-04      | §4.4   | Conformant                                  | Commitment alg = EATP-08 §3.3 registry token (`eatp-v1`); record `kek_commitment_alg`; additive registry                                       | **C2a**           | C1 (record at backup)                      |
| N12-CB-04(b)   | §4.4   | Conformant                                  | Recompute under backup's **recorded** alg; `commitment-alg-mismatch` only if never registered                                                  | **C2a**           | —                                          |
| N12-CB-04(c)   | §4.4   | Conformant                                  | Hash-sunset migration additive: `vault_kek_recommit` ADDS new-alg commitment, no delete; both live                                             | **C2b**           | —                                          |
| N12-CB-04(d)   | §4.4   | Conformant                                  | `BackupReceipt` carries key-free 8-byte (16-hex) domain-separated KCV; tamper fails offline `kcv-mismatch`                                     | **C1**            | —                                          |
| N12-CB-04(e)   | §4.4   | Conformant                                  | Signed `vault_kek_retire` marks alg entry non-verifiable; restore under it fails `retired-commitment-alg`                                      | **C2b**           | —                                          |
| N12-CL-01      | §4.2   | Conformant                                  | `back_up_vault_key` verifies `vault:backup` in bound role CapabilitySet; reject `missing-clearance`                                            | **B1**            | —                                          |
| N12-CL-02      | §4.2   | Conformant                                  | `restore_vault_key` verifies `vault:restore` (independent of quorum/commitment/gen); reject pre-combine                                        | **B1**            | —                                          |
| N12-CL-02a     | §4.2   | Conformant                                  | Independently verify cascade tenant + role domain vs vault's, fail-closed (tenant→domain→token)                                                | **B1**            | —                                          |
| N12-CL-03      | §4.2   | **Complete**                                | OPTIONAL governance-approver HELD; distinct `vault:approve`, no self-approval, bound into signed payload                                       | **X1**            | —                                          |
| N12-CL-03(c)   | §4.2   | **Complete**                                | Approver identity + signed token inside `event_payload` (covered by `content_signing_bytes`)                                                   | **X1**            | —                                          |
| N12-CL-04      | §4.2.1 | Conformant                                  | During D6 7-day cooling-off (trust clock), suspend principal `vault:*`; 2nd op needs HELD or `missing-clearance`                               | **B1**            | C3 (RT-05 trigger), D2 (clock)             |
| N12-CL-05      | §4.2   | **Complete**                                | At Complete, backup/gen path requires independent in-pre-image `vault:witness` (≠ requester/approver)                                          | **X1**            | —                                          |
| N12-CRY-PIN    | §3.3   | Conformant                                  | Emit shards under fixed pinned SLIP-0039 params; record them in audit envelope                                                                 | **I1**            | D2 (record)                                |
| N12-CRY-PIN(d) | §3.3   | Conformant                                  | Master-secret length 128/256-bit; else `invalid-secret-length`; record `master_secret_bits`                                                    | **I1**            | D2 (record)                                |
| N12-CRY-PIN(e) | §3.3   | Conformant                                  | Shard randomness from CSPRNG; public path exposes no caller-seedable `EntropySource`                                                           | **I1**            | —                                          |
| N12-CRY-SC     | §3.3   | Conformant (disclosure) / Complete (`true`) | Record `side_channel_hardened` bool (default `false`); `true` REQUIRES hardware-backed reconstruction (Complete)                               | **D2**            | I1 (surface), X1 (true-assert)             |
| N12-FT-01      | §4.6   | Conformant                                  | Surface enumerated distinct typed errors (reuse EATP-10 codes); MUST NOT collapse to one generic                                               | **FT**            | —                                          |
| N12-FT-02      | §4.6   | Conformant                                  | Over-supply deterministic; 8-step canonical first-failing **restore** gate order applied                                                       | **FT** (skeleton) | **C3** (wiring)                            |
| N12-FT-03      | §4.6   | Conformant                                  | Registry-write paths (recommit/retire/rotation) apply pinned first-failing gate order                                                          | **FT** (skeleton) | **C2b** (wiring), R1                       |
| N12-IN-01      | §4.1   | Conformant                                  | Public entry accepts key handle (not raw bytes); resolve KEK internally; raw bytes don't cross API                                             | **I1**            | —                                          |
| N12-IN-02      | §4.1   | Conformant                                  | Handle resolves to KEK-class-tagged object; reject `not-a-kek`; never shard data keys directly                                                 | **I1**            | F1 (key_class)                             |
| N12-IN-03      | §4.1   | Conformant                                  | Raw-bytes escape hatch **disabled by default** (build-flag); else `escape-hatch-disabled`; when on: full gates + HELD + dual-emit              | **I1**            | —                                          |
| N12-IN-04      | §4.1   | Conformant                                  | `back_up_vault_key` records resolved KEK stable key-ID; bind into KEK-identity commitment                                                      | **I1**            | C1 (bind)                                  |
| N12-IN-05      | §4.1   | Conformant                                  | Reconstructed KEK consumed in trusted module, `del` in `finally`, returned opaque; no plaintext output                                         | **I1**            | —                                          |
| N12-PP-01      | §4.4.1 | Conformant                                  | Define passphrase provenance; bind into commitment; ref by `passphrase_ref`; exclude from audit; `invalid-passphrase`                          | **C1**            | —                                          |
| N12-RT-01      | §5.1   | Conformant                                  | Holder rotation calls shipped `rotate_holders` (no reimpl); require `vault:rotate`; satisfy TH-01 floor                                        | **R1**            | —                                          |
| N12-RT-02      | §5.1   | Conformant                                  | Amicable rotation writes `vault_holder_rotation` anchor (mediated, fail-closed); `for_cause=false`                                             | **R1**            | —                                          |
| N12-RT-03      | §5.1   | Conformant                                  | Post-rotation new shard set only valid; old-ritual shards rejected (`unknown-shard`/`revoked-holder`/`mixed-shard-set`)                        | **R1**            | —                                          |
| N12-RT-04      | §5.3   | Conformant                                  | Mode A (single-group full re-shard) only; MUST NOT claim Mode B conformance (zero net-new per MED-5)                                           | **R1**            | —                                          |
| N12-RT-05      | §5.4   | Conformant                                  | ANY restore materializing the KEK triggers D6 by reference (SUPERVISED + 7-day cooling-off); no carve-out                                      | **C3**            | B1 (CL-04 enforces)                        |
| N12-RT-06      | §5.2   | Conformant                                  | Every generation advance emits audited `vault_kek_rotation` anchor; current gen derives from that chain                                        | **R1**            | D1 (chain read), C3 (consumes current-gen) |
| N12-SG-01      | §6     | Conformant                                  | Every backup tagged monotonic `kek_generation`, recorded in envelope/blob AND bound into commitment                                            | **C3**            | F1 (field), C1 (bind)                      |
| N12-SG-01(b)   | §6     | Conformant                                  | Captured generation **bound into** commitment (not merely co-located) — true gen cryptographically recoverable                                 | **C3**            | C1 (bind)                                  |
| N12-SG-02      | §6     | Conformant                                  | Restore refuses stale/relabelled gen by default (`unknown-shard`/`kek-commitment-mismatch`/`stale-generation`)                                 | **C3**            | —                                          |
| N12-SG-03      | §6     | Conformant                                  | `force_stale` requires distinct `vault:restore-stale`; overrides only step 8; loud `vault_key_restore_forced_stale` to safety; default `False` | **C3**            | —                                          |
| N12-SG-05      | §6     | Conformant                                  | Compromised-generation denylist; restore refuses `revoked-generation` (even gen==current); loud dual-emit                                      | **C3**            | —                                          |
| N12-SH-01      | §4.3   | Conformant                                  | Every shard binds to holder from deployment registry; reject `unregistered-holder`; record holder IDs                                          | **B2**            | —                                          |
| N12-SH-02      | §4.3   | **Complete**                                | OPTIONAL per-holder wrapping for revocation (MAY at Conformant); SHOULD for-cause + advance gen per SH-04                                      | **X1**            | —                                          |
| N12-SH-03      | §4.3   | Conformant                                  | Revocation MUST NOT silently drop un-revoked set below `k`; require rotation + surface to operator                                             | **B2**            | —                                          |
| N12-SH-04      | §4.3   | Conformant                                  | For-cause revocation performs generation-advancing KEK-rotation; one `vault_kek_rotation` anchor `for_cause=true`                              | **R1**            | B2 (revocation decision)                   |
| N12-TH-01      | §3.3   | Conformant                                  | Reject any ritual outside `2 ≤ k ≤ n ≤ 9` with `invalid-ritual` at all levels (1-of-n / 1-of-1 forbidden)                                      | **I1**            | R1 (rotation floor)                        |

---

## Orphan-closure verification (the HIGH-5 gate)

**50 Conformant-mandatory IDs** — every one has a primary shard (no empty cell):

- AU (8): AU-01,01a,02,02a,02b,03,04,04a → D1/D2 ✓
- CB (10): CB-01,02,02(b),02(d),03,04,04(b),04(c),04(d),04(e) → C1/C2a/C2b ✓
- CL (4 conformant): CL-01,02,02a,04 → B1 ✓
- CRY (4): CRY-PIN,PIN(d),PIN(e),SC → I1/D2 ✓
- FT (3): FT-01,02,03 → FT(+C3/C2b wiring) ✓
- IN (5): IN-01,02,03,04,05 → I1 ✓
- PP (1): PP-01 → C1 ✓
- RT (6): RT-01,02,03,04,05,06 → R1(+C3 for RT-05) ✓
- SG (5): SG-01,01(b),02,03,05 → C3 ✓
- SH (3 conformant): SH-01,03,04 → B2/R1 ✓
- TH (1): TH-01 → I1 ✓

**4 Complete-optional IDs** → X1 (Wave 5): CL-03, CL-03(c), CL-05, SH-02.

**Total: 50 + 4 = 54 = full ID namespace.** No range-notation; no orphan.

**Redteam HIGH-5 named orphans — all now placed:** N12-CRY-PIN → I1; TH-01 → I1; CRY-SC → D2; IN-03 (escape-hatch, disabled-by-default) → I1; PP-01 → C1; RT-01/RT-02 → R1; CL-04 → B1.

**Explicit numbering gaps (verified absent in spec, not orphans):** no `N12-SG-04`; no `N12-CL-06`; CL-03(a)/(b)/(d) are lettered bullets within CL-03, not standalone IDs.

## Dependency-edge audit (producer-before-consumer, HIGH-2 closure)

- **D1 (Wave 2) precedes** CB-03 (C2a, Wave 3 — sources `shard_commitments` from recovery-tier distribution anchor) ✓
- **D1 (Wave 2) precedes** C3 stale-guard (Wave 3 — derives current-gen from the audited chain) ✓
- **D2 (Wave 2, anchor schema) precedes** every anchor-writing crypto shard (C2a/C2b/C3, Wave 3) ✓ — latent edge HIGH-2's logic implied; closed by landing the full audit substrate (D1+D2) in Wave 2.
- **RT-05 (C3, Wave 3, restore→D6 trigger) precedes** CL-04 (B1, Wave 4, cooling-off enforcement) ✓ — reassigned RT-05 from the rotation shard to the restore path (it fires on restore, not rotation).
- **FT skeleton (Wave 1) precedes** FT-02 wiring (C3) + FT-03 wiring (C2b/R1) ✓
- **C3 (Wave 3) reads current-gen via D1 chain at bootstrap gen; R1 (Wave 5) adds the advance** — no backward edge; the multi-generation stale case is exercised at the post-Wave-5 inter-wave gate.
