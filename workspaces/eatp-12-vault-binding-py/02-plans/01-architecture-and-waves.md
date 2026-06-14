# EATP-12 v1.0 Trust Vault Key-Binding — Architecture & Wave Plan

**Issue:** #1312 · **Spec:** `briefs/eatp-12-v1.0-spec.md` (foundation EATP-12 v1.0, Published) · **Security tier:** CRITICAL (reconstructs the vault KEK — the deployment's highest-value secret).

This is a **conformance implementation against a fixed normative spec**, not a product. The analysis below is a conformance-gap synthesis of the five cluster deep-dives in `01-analysis/`, an architecture, a dependency-ordered wave/shard plan (per `rules/wave-loop.md` + `rules/autonomous-execution.md` § Per-Session Capacity Budget), and the brief-corrections gate (per `rules/agents.md` § Parallel Brief-Claim Verification).

---

## 1. Convergence summary (5 parallel cluster verifications)

| Cluster   | Scope                                          | Verdict                         | Reusable substrate                                                                                                                       | Net-new                                                                                  |
| --------- | ---------------------------------------------- | ------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| A (`01-`) | §3.4 substrate + §4.1 input                    | **ALL ABSENT**                  | SLIP-0039 wrapper (`trust/vault/shamir.py`); `KeyMetadata.key_id`                                                                        | 9 types; `key_class`; `kek_generation`; KEK/data-key hierarchy                           |
| C (`02-`) | §4.4 commitment + §4.4.1 passphrase + §6 stale | **ALL 9 ABSENT**                | `canonical_json_dumps` (`trust/_json.py:149`); eatp-08 alg registry (`signing/algorithm_id.py:108`); `shamir.reconstruct`                | commitment + KCV + per-(handle,gen) registry; recommit/retire; force_stale gate          |
| E (`03-`) | §7 vectors + §12 golden fixtures               | **fixtures reproducible TODAY** | `test_eatp08_alg_id_canonical_vectors.py` harness pattern; PACT conformance loader                                                       | V1–V8 vectors; §12 Tier-1 byte-pins                                                      |
| B (`04-`) | §4.2 clearance + §4.3 holder                   | **ALL 10 ABSENT (vault layer)** | `CapabilitySet` (`delegate/types.py:508`); `RoleScope` (`:557`); dispatch gate (`delegate/dispatch.py:1435`); HMAC (`delegate/audit.py`) | holder registry; `vault:*` tokens; tenant/domain binding check; cooling-off              |
| D (`05-`) | §4.5 audit + §5 rotation                       | **PARTIAL**                     | audit anchor/seal/hash-chain (`trust/pact/audit.py`); `EXTERNAL_SIDE_EFFECT`; `PostureStore`+`SUPERVISED`; `shamir.rotate_holders`       | EATP-09 named-tier adapter; `vault_*` subtypes; per-subtype schema; trust-anchored clock |

**Bottom line:** the cryptographic + authz + audit _substrate_ exists and is reusable; the _binding layer_ is ~0% (one `NotImplementedError` stub, no `restore_vault_key`). This is a build-from-substrate effort, dependency-heavy, security-critical.

---

## 2. Brief-corrections gate (per `rules/agents.md`)

The "brief" here is a Published normative spec, not a decaying user mental model — but the parallel sweep still surfaced findings that MUST be resolved before `/todos`:

1. **[CRITICAL — cross-SDK byte-parity hazard] Canonical-JSON encoder ambiguity.** The spec's N12-CB-01 commitment + N12-CB-04(d) KCV pre-images cite `canonical_json_dumps` (RFC 8785 / JCS). kailash-py has **two non-interchangeable** JCS-ish encoders: the **delegate family** `canonical_json_dumps` (`trust/_json.py:149`, `ensure_ascii=False`, raw UTF-8 — matches RFC 8785 + Rust `serde_json`) and the **signing family** `serialize_for_signing` (`signing/crypto.py:225`, `ensure_ascii=True`, `\uXXXX`-escaped). Independently flagged by clusters C **and** E. Every §12 golden fixture is ASCII-only, so **both encoders reproduce the published hex byte-identically** — the divergence is _invisible in the golden fixture_. **Disposition:** the spec explicitly names `canonical_json_dumps` (RFC 8785 / JCS → raw UTF-8), so the commitment MUST use the **delegate-family `ensure_ascii=False`** encoder for cross-SDK parity with Rust. This MUST be locked by a **non-ASCII sentinel vector** (a `vault_id` with a non-ASCII codepoint) added to the Tier-1 byte-pin set — and the non-ASCII pre-image MUST be reconciled with kailash-rs before either SDK releases vault binding (the §12 fixture cannot pin it). This is shard C1's first decision.

2. **[resolved] `delegate/*` paths.** Cluster C initially flagged the spec's `delegate/audit.py` / `delegate/dispatch.py` citations as wrong; cluster B confirmed they are **correct** — the repo has both `src/kailash/delegate/` and `src/kailash/trust/`. Spec citations stand; the canonical-JSON helper the spec calls `delegate/audit.py`'s form actually lives at `trust/_json.py:149` (re-exported), a cosmetic offset only.

3. **[dependency, not a blocker] EATP-09 named-tier dispatcher absent.** Only the gradient-keyed `TieredAuditDispatcher` (`trust/pact/audit.py:475`) exists; the spec sanctions a binding **adapter** onto it. Cluster D assessed the adapter as feasible but a real 3-layer surface (owns `DispatchReceipt`, fail-closed ordering, per-tier chain) — its own shard, not a shim.

4. **[degradation risk] Trust-anchored clock absent.** Broad grep over `src/kailash/` returned zero hits for a trusted-time source. AU-04a / CL-04 / TEMP-2 depend on EATP-10 §14's trust-anchored clock; if no usable source ships, those carry a permanent-degradation risk (fail-closed: suspension stays in force when time can't be consulted). Flag to the spec authors as a cross-SDK question; implement fail-closed.

5. **[substrate dependency] `KeyMetadata` generation/key-class extension (#630).** `kek_generation` + `key_class` are net-new on `KeyMetadata` (`trust/key_manager.py:94`). They gate IN-02 (type check), SG (stale guard), RT-06 (rotation). This is the keystone — Wave 1 Foundation.

---

## 3. Architecture (substrate → binding)

```
                       ┌─────────────────────────────────────────────┐
   §3.4 SUBSTRATE      │ KeyMetadata + key_class{KEK,DATA} + kek_generation (monotonic)
   (Wave 1 keystone)   │ KEK/data-key wrapping hierarchy
                       └───────────────┬─────────────────────────────┘
                                       │
   CORE TYPES (Wave 1)  VaultKeyHandle · BackupReceipt · RestoreReceipt · ClearanceContext · PassphraseRef · HolderId
                                       │
   TAXONOMY (Wave 1)   FT closed N12FT01Error enum (FT-01) + FT-02/FT-03 ordered-gate skeletons (single source of truth)
   AUDIT SUBSTRATE     D1 EATP-09 dispatcher adapter (AU-02/02a/02b)  ·  D2 envelope schema (AU-01/01a/03/04/04a)
   (Wave 2, producer)     ← lands BEFORE the crypto shards that write anchors (HIGH-2)
   ┌───────────────────────────────────┬──────────────────────────┬──────────────┐
   │ CRYPTO CORE (anti-injection)      │ INPUT + CLEARANCE        │ ROTATION     │
   │ C1 commitment(CB-01)+KCV(CB-04d)  │ I1 handle surface +      │ R1 rotation  │
   │   +PP-01+IN-04 [ASCII byte-pins]  │   ritual/param gates     │   RT-01/02/  │
   │ C2a registry+recompute+3-way+     │   (IN-01..05,TH-01,      │   03/04/06   │
   │   CB-03 foreign-shard             │    CRY-PIN family)       │   +SH-04     │
   │ C2b recommit+retire+FT-03 wiring  │ B1 clearance(CL-01/02/   │              │
   │ C3 stale-guard(SG)+FT-02 wiring   │   02a)+CL-04 cooling-off │              │
   │   +RT-05 restore→D6 trigger       │ B2 holder reg(SH-01/03)  │              │
   └───────────────────────────────────┴───────────┬──────────────┴──────────────┘
                                       │
   COMPLETE (Wave 5)    X1 approver-HELD(CL-03/03(c)) · witness(CL-05) · per-holder-wrap(SH-02)
   CONFORMANCE (Wave 6) T2 V1–V8 vectors (Tier-2) · S1 specs/trust-crypto.md §30 + workspace specs
```

**Anchor-substrate decision (cluster D open Q):** the audit anchor rides the **delegate engine** (correct `content_signing_bytes` pre-image `{event_type, event_payload, signer_delegate_id}` + per-tier chain), NOT the PACT gradient dispatcher. `alg_id` has no top-level slot in the pre-image → it rides `event_payload` (confirms F-AUDIT-8).

---

## 4. Wave plan (explicit declaration per `rules/wave-loop.md` MUST-1)

Six waves, dependency-ordered. Each non-final wave runs the inter-wave gate (G1 redteam-to-convergence scoped to the wave → G2 journal/spec capture → G3 amend later-wave todos → G4 re-rank → G5 launch next). Per-wave invariant surface kept ≤10 base (the crypto/audit waves carry a live Tier-1 byte-pin / unit harness → MUST-3 multiplier applies, ceiling 30–50).

**Revised 2026-06-14** to fold the 5 Round-1 redteam must-fixes (see §8). Per-ID shard ownership is the full matrix in `03-conformance-id-matrix.md` (closes HIGH-5). The key structural change: the **audit substrate (D1+D2) moves to Wave 2** so it precedes every anchor-writing crypto shard (closes HIGH-2), and a **new FT taxonomy shard** anchors Wave 1 (closes CRIT-2).

| Wave                            | Shards                                                                                                                                                                             | Value / why this order                                                                                                                                     | Invariant surface                                                                                                                                                                                                                                                         | Gate                          |
| ------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------- |
| **1 — Foundation**              | F1 §3.4 substrate · F2 core types · **FT error-taxonomy (closed enum + FT-02/FT-03 skeletons)** · C1 commitment+KCV (**ASCII** byte-pin) · T1 §12.1–12.3 fixtures (**ASCII only**) | Keystone — `kek_generation` + commitment pre-image + the single-source typed-error enum every later gate returns. Resolves the encoder decision first.     | ~8 (key_class, gen monotonicity, JCS encoder, commitment pre-image, KCV truncation, fixture byte-identity, closed-enum single-source, gate-skeleton determinism) + harness                                                                                                | inter-wave                    |
| **2 — Audit substrate + Input** | **D1 EATP-09 dispatcher adapter · D2 audit envelope+§12.4–12.11 fixtures** · I1 handle surface + ritual/param gates (IN-01..05, TH-01, CRY-PIN family)                             | Audit substrate is the **producer** every Wave-3 crypto shard consumes (HIGH-2); I1 makes the surface callable + enforces pinned params at the entry gate. | ~10 (recovery/safety routing, fail-closed interlock, DispatchReceipt, per-subtype schema, trust-anchored time, handle-not-bytes, KEK-class tag, escape-hatch-off, consume-and-del, ritual+length pinning) + harness                                                       | inter-wave                    |
| **3 — Crypto registry + stale** | **C2a registry+recompute+3-way+CB-03 · C2b recommit+retire+FT-03 wiring** · C3 stale-guard (SG)+FT-02 wiring+RT-05 trigger                                                         | The load-bearing anti-injection path; all consume the Wave-2 audit chain (CB-03 foreign-shard, C3 current-gen).                                            | ~14 (additive registry, recompute-under-recorded-alg, 3-way discrimination, foreign-shard, captured-gen, recommit-additive, retire, FT-03 order, gen-bound-into-commitment, default-stale-refusal, force_stale step-8-only, denylist, FT-02 8-step, restore→D6) + harness | inter-wave                    |
| **4 — Authz**                   | B1 clearance (CL-01/02/02a) + CL-04 cooling-off · B2 holder registry (SH-01/03)                                                                                                    | Conformant-mandatory gates; CL-04 consumes the Wave-3 RT-05 D6 trigger + the Wave-2 trust clock.                                                           | ~7 (capability-on-bound-role, tenant→domain→token fail-closed, cooling-off suspension, holder registry, k-floor-no-silent-drop)                                                                                                                                           | inter-wave                    |
| **5 — Rotation + Complete**     | R1 rotation (RT-01/02/03/04/06) + for-cause gen-advance (SH-04) · X1 Complete-level (CL-03/03(c)/05, SH-02)                                                                        | Generation-advance closes the for-cause-revocation loop; Complete-level optional knobs.                                                                    | ~8                                                                                                                                                                                                                                                                        | inter-wave                    |
| **6 — Conformance + spec**      | T2 V1–V8 vectors (Tier-2) · S1 specs/trust-crypto.md §30 + workspace specs                                                                                                         | Final conformance proof + spec truth-update (post-code per `spec-accuracy.md` Rule 5).                                                                     | ~4                                                                                                                                                                                                                                                                        | **terminal holistic redteam** |

**Post-Wave-6 cross-SDK gate (value-anchored — user directive "ensure kailash-rs parity", 2026-06-14):** (a) holistic multi-wave redteam across all merged shards (per `rules/agents.md` § Holistic Post-Multi-Wave Redteam) — ≥3 parallel reviewers (reviewer + security-reviewer + closure-parity); then (b) **derive the non-ASCII sentinel vector** (`vault_id` with a non-ASCII codepoint, `ensure_ascii=False` per CRIT-1) — deferred here from Wave 1 per **HIGH-3** because it is calendar-bound on rs reconciliation; then (c) **cross-SDK byte-parity coordination with kailash-rs** (V6 commitment + KCV + audit pre-image + the non-ASCII sentinel). **This is a separate cross-repo grant + release-coordination gate; neither SDK releases vault binding before parity is confirmed.**

---

## 5. Sharding compliance (per `rules/autonomous-execution.md` MUST-1)

Every shard is sized ≤500 LOC load-bearing / ≤5–10 invariants / ≤3–4 call-graph hops, describable in ≤3 sentences. F2 (core types) is DTO boilerplate (scales ~5× further). FT (taxonomy) is a closed enum + pure-function skeletons (low-invariant). C1/C2a/C2b/C3/D1/D2 are the load-bearing-logic shards — each its own session/worktree. The crypto + audit shards carry a live Tier-1 byte-pin / unit harness, so the MUST-3 feedback-loop multiplier applies (Wave 3's ~14 cumulative invariants sit under the 30–50 harness ceiling per `wave-loop.md` MUST-1 bound-B).

## 6. Specs disposition (per `rules/spec-accuracy.md` Rule 5)

`specs/` describes only shipped behaviour. EATP-12 behaviour ships incrementally across Waves 1–6, so `specs/trust-crypto.md` §30 (currently "Awaiting Mint ISS-37") is updated to the concrete EATP-12 v1.0 contract **in Wave 6 / S1, after the code lands** — NOT spec-ahead-of-code. The authoritative design surface during implementation is the EATP-12 spec in `briefs/`.

## 7. Effort (autonomous-execution framing)

~6 waves; the crypto core (C1/C2a/C2b/C3) and audit (D1–D2) are the deep shards. Greenfield-on-mature-substrate → not the 10× regime for the novel crypto pre-image work (first-pass ~2–3×); the DTO + wiring shards are at full multiplier. The cross-SDK parity coordination is calendar-bound (depends on kailash-rs availability), outside the autonomous multiplier.

## 8. Plan revision — Round-1 redteam must-fix fold (2026-06-14)

The Round-1 `/redteam` (`04-validate/01-redteam-analysis-plan.md`) returned **GAPS-FOUND** with 9 must-fix items. CRIT-1 (encoder), HIGH-1 (#630 scope), HIGH-6 (trust clock) were resolved in-session at redteam time. This revision folds the remaining 5 (all plan-structure, no external blockers):

| #      | Sev  | Gap                                                                                                                          | Fold                                                                                                                                                                                                                                                        |
| ------ | ---- | ---------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| CRIT-2 | CRIT | §4.6 taxonomy (FT-01 ~25 typed codes, FT-02 8-step restore order, FT-03 write-path order) orphaned — range-notation hid them | **New FT shard in Wave 1**: closed `N12FT01Error` enum (single source of truth, no later shard re-defines codes) + wrapper→code map + FT-02/FT-03 ordered-gate **pure-function skeletons**. C3 wires FT-02; C2b/R1 wire FT-03.                              |
| CRIT-3 | CRIT | C2 bundled ~12 invariants — overflowed the ≤10 budget                                                                        | **Split into C2a** (commitment registry + recompute-under-recorded-alg + 3-way code discrimination + CB-03 foreign-shard) **and C2b** (recommit additive + retire + FT-03 wiring + EATP-08 sunset).                                                         |
| HIGH-2 | HIGH | Dependency inversion — Wave-2 C3 + CB-03 consumed an audit chain that didn't exist until Wave 4                              | **Audit substrate (D1+D2) moved to Wave 2**, before the Wave-3 crypto shards that write/read anchors. Also surfaced + closed the latent D2-schema-before-anchor-writers edge. RT-05 (restore→D6) reassigned from R1 to C3 (it fires on restore).            |
| HIGH-3 | HIGH | Non-ASCII sentinel sequenced as a Wave-1 deliverable but calendar-bound on rs reconciliation                                 | **Wave 1 authors ASCII byte-pins only**; the non-ASCII sentinel is deferred to the post-Wave-6 cross-SDK gate (value-anchored on the user's "ensure kailash-rs parity" directive).                                                                          |
| HIGH-5 | HIGH | ~8 Conformant-mandatory IDs in no shard cell (range-notation hid them)                                                       | **Full per-N12-ID → shard matrix** at `03-conformance-id-matrix.md` — 54 rows, one per ID + sub-clause, all 50 Conformant-mandatory IDs placed, 4 Complete-optional → X1. Named orphans (CRY-PIN, TH-01, CRY-SC, IN-03, PP-01, RT-01/02, CL-04) all closed. |

**Should-fix items** (HIGH-4 principal_set_root/shard_commitment hash-domains, MED-1..5) land at `/todos` per the redteam disposition; HIGH-4's unpinned cross-SDK hash domains join the post-Wave-6 parity gate alongside the non-ASCII sentinel.

**Gate status: the 5 must-fixes are folded → `/todos` is unblocked.** Receipt: `journal/0004-DECISION-plan-revision-must-fix-fold.md`.
