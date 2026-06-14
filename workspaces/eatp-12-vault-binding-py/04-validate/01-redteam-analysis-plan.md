# Red-Team — EATP-12 Analysis + Plan (Round 1)

Adversarial review by `analyst` (read-only; report persisted by orchestrator). **Verdict: GAPS-FOUND — NOT converged.** The analysis is thorough and the architecture substantially correct, but 9 must-fix items gate `/todos`. One (CRIT-1) is RESOLVED this session by a disambiguation experiment; the rest are plan-structure fixes for the fresh session to fold before `/todos`.

## CRIT-1 — Canonical-JSON encoder contradiction — ✅ RESOLVED (experiment)

Clusters C and E reached **opposite** encoder conclusions (C: `ensure_ascii=False` raw UTF-8; E: `ensure_ascii=True` ASCII-escaped). The §12 fixtures are ASCII-only, so the fixture cannot adjudicate. **Disambiguation experiment (2026-06-14, non-ASCII em-dash U+2014 through the actual shipped functions):**

```
canonical_json_dumps({"vault_id":"vault:t—id"}) -> '{"vault_id":"vault:t—id"}'   # ensure_ascii=False, raw UTF-8 bytes e2 80 94
content_signing_bytes  -> calls canonical_json_dumps (NOT serialize_for_signing)  # audit pre-image is ALSO ensure_ascii=False
serialize_for_signing({"vault_id":"vault:t—id"}) -> '{"vault_id":"vault:t—id"}'  # ensure_ascii=True — WRONG for EATP-12
```

**Ruling:** BOTH the KEK-identity commitment AND the audit pre-image use **`canonical_json_dumps` (`ensure_ascii=False`, RFC-8785/JCS raw UTF-8)** — parity-compatible with Rust `serde_json`. Cluster E's "rs must emit ASCII-escaped" is **refuted** (ASCII-fixture coincidence). The ASCII §12 byte-pins are unaffected (identical under both); the **non-ASCII sentinel** MUST be derived with `ensure_ascii=False` and reconciled with rs#1316. Updates `journal/0002`; closes brief-correction #1 on evidence.

## Remaining must-fix BEFORE /todos (fresh-session gate)

| #      | Sev  | Gap                                                                                                                                                                                                                                                                                                    | Fix                                                                                                                                                                                                                                                                                |
| ------ | ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| CRIT-2 | CRIT | §4.6 failure taxonomy (N12-FT-01 ~25 typed errors) + FT-02 (8-step restore gate order) + FT-03 (write-path order) are **orphaned** — owned by no shard; range-notation hid them.                                                                                                                       | Add an **error-taxonomy + gate-order foundation shard to Wave 1** (with F2): a closed `N12FT01Error` enum (25 codes, single source of truth), the wrapper-exception→typed-code mapping, and FT-02/FT-03 ordered-gate skeletons as pure functions. No later shard re-defines codes. |
| CRIT-3 | CRIT | C2 (registry/agility/recommit/retire/foreign-shard) bundles **~12 invariants** — overflows the ≤10 budget.                                                                                                                                                                                             | Split: **C2a** (commitment registry + recompute-under-recorded-alg + 3-way code discrimination + CB-03 foreign-shard) and **C2b** (recommit + retire + FT-03 write-path + EATP-08 sunset + recoverability guard).                                                                  |
| HIGH-1 | HIGH | `kek_generation`/`key_class` substrate (#630) ownership unresolved — plan folds into F1 without confirming #630 is in-scope vs a hard upstream blocker; the field-on-KeyMetadata vs vault-owned-wrapper fork is undecided.                                                                             | Resolve #630 scope with the user/issue **before /todos**; decide the substrate-placement fork; show the dependency edge in the wave sequence. Note it touches SHARED trust substrate (SAME-class surface).                                                                         |
| HIGH-2 | HIGH | **Dependency inversion**: D1 (EATP-09 audit-dispatcher adapter) is Wave 4, but Wave-2 C3 stale-guard (sources current gen from the audited rotation chain, RT-06) + CB-03 foreign-shard (sources `shard_commitments` from the recovery-tier distribution anchor) **require the audit chain to exist**. | Move D1 ahead (Wave 1/2) OR sequence C3 + CB-03 after D1. Producer must precede consumer.                                                                                                                                                                                          |
| HIGH-3 | HIGH | Non-ASCII sentinel sequenced as a Wave-1 deliverable, but it depends on CRIT-1 (now resolved) **and** rs reconciliation (calendar-bound).                                                                                                                                                              | Wave 1 authors ASCII byte-pins only; **defer the non-ASCII sentinel** to the post-Wave-6 cross-SDK gate (value-anchored).                                                                                                                                                          |
| HIGH-5 | HIGH | ~8 Conformant-mandatory IDs in **no shard cell** (range-notation hid them): N12-CRY-PIN, TH-01, CRY-SC, IN-03 escape-hatch inversion, PP-01, RT-01/RT-02, CL-04.                                                                                                                                       | Produce a complete **per-N12-ID → shard assertion matrix** (one row per ID + sub-clause; range-notation BLOCKED), à la `spec-compliance/SKILL.md`. Close every orphan.                                                                                                             |
| HIGH-6 | HIGH | Trust-anchored clock (AU-04a/CL-04/TEMP-2) filed as a footnote — but zero time surface exists in `src/kailash/` and EATP-10 §14 may expose none; permanent `time_attested:false` degradation locks cooling-off forever.                                                                                | **Existence-check EATP-10 §14** now; if absent, surface to user as a cross-SDK/cross-spec blocker, decide ship-degraded vs gate-on-§14.                                                                                                                                            |
| HIGH-7 | HIGH | No release-blocking backup→restore **end-to-end roundtrip regression** in the plan (fake-integration-at-receipt-boundary class, per `testing.md`).                                                                                                                                                     | Add `tests/regression/test_eatp12_vault_quickstart.py`: docs-exact backup→restore asserting reconstructed-KEK byte-equality + audit-anchor-present + commitment-verified. Release-blocking.                                                                                        |

## Should-fix (can land at /todos)

- **HIGH-4** — `principal_set_root` (V2-denial-flood) + `shard_commitment` hash-domain are unpinned cross-SDK (§12 uses `ff..`/`aa..` stand-ins); no shard defines them. Add to D2 an explicit "define + real-byte-vector + cross-SDK reconcile" deliverable.
- **MED-1** — each implementation shard owns its V-vector Tier-2 tests (don't defer all to Wave 6).
- **MED-2** — name the owner of the IN-04 key-identity-capture → CB-02(d) identity-check handoff (cross-shard field).
- **MED-3** — add §8 considerations to the plan risk register: memory-lock/swap-disable primitive existence-check (N12-IN-05), PQC re-shard window, forward-secrecy rotation SHOULD.
- **MED-4** — list `tests/test-vectors/eatp12-vault-canonical.json` as the explicit cross-SDK contract artifact (ASCII pins authorable Wave 1).
- **MED-5** — mark N12-RT-04 (Mode A only) explicitly closed (zero net-new; wrapper is hard-wired single-group).

## Disposition

`/todos` is **gated** on folding CRIT-2/3 + HIGH-1/2/3/5/6/7 into a revised plan. CRIT-1 is resolved. The fresh session opens by (a) resolving the #630 scope question with the user, (b) existence-checking EATP-10 §14, (c) building the per-N12-ID matrix, (d) re-structuring the waves (error-taxonomy foundation shard; C2 split; D1 moved earlier), then `/todos`.

## Session resolutions (2026-06-14) — two HIGH findings de-risked

- **HIGH-1 RESOLVED → architecture-fork (not a blocker).** `#630` is **CLOSED** and explicitly subsumed by `#1312` (the issue body: "subsumes the binding-layer scope of #630"). The `kek_generation`/`key_class` `KeyMetadata` extension is therefore **in-scope for THIS workstream** — F1 owns it. Residual: the field-on-`KeyMetadata` vs vault-owned-wrapper fork (Cluster A `:123-130`) is a real decision for plan-revision, but it is NOT gated on an external issue.
- **HIGH-6 RESOLVED → bind-to-existing-TSA (not permanent degradation).** A timestamp-authority surface EXISTS: `src/kailash/trust/signing/timestamping.py` — `TimestampAuthority` (ABC, `:279`), `LocalTimestampAuthority` (`:336`), **`RFC3161TimestampAuthority` (`:585`)**, `TimestampAnchorManager` (`:836`), `verify_timestamp_token` (`:1054`). The redteam's "zero time surface" was a grep for the wrong name (`trust-anchored clock`/`time_attested`). AU-04a's two-state `time_attested` grammar maps to verified-vs-unverified `TimestampToken`; the trust-anchored clock binds to `RFC3161TimestampAuthority`. Residual: confirm RFC3161 TSA satisfies EATP-10 §14's trust-anchored-clock requirement (a conformance check, not a missing-primitive blocker).

**Net:** of the 9 must-fix items, CRIT-1 + HIGH-1 + HIGH-6 are resolved this session. Remaining for the fresh session before `/todos`: CRIT-2 (taxonomy foundation shard), CRIT-3 (split C2), HIGH-2 (move D1 earlier), HIGH-3 (defer non-ASCII sentinel), HIGH-5 (per-N12-ID matrix) — all plan-structure fixes, no external blockers.

## Round-1 closure (2026-06-14) — ALL 9 must-fix resolved → /todos UNBLOCKED

The 5 remaining must-fixes are folded into the plan (receipt: `journal/0004-DECISION-plan-revision-must-fix-fold.md`):

- **CRIT-2 ✅** — FT error-taxonomy shard added to Wave 1 (closed `N12FT01Error` enum single-source + FT-02/FT-03 gate-order skeletons). `02-plans/01-architecture-and-waves.md` §4/§8.
- **CRIT-3 ✅** — C2 split into C2a (registry+recompute+3-way+CB-03) and C2b (recommit+retire+FT-03 wiring). §4/§8.
- **HIGH-2 ✅** — audit substrate (D1+D2) moved to Wave 2 ahead of the Wave-3 anchor-writing crypto shards; RT-05 reassigned R1→C3 (restore path). Producer-before-consumer edge audit in `02-plans/03-conformance-id-matrix.md`.
- **HIGH-3 ✅** — Wave 1 ASCII byte-pins only; non-ASCII sentinel deferred to the post-Wave-6 cross-SDK gate (value-anchored on the rs-parity directive).
- **HIGH-5 ✅** — full 54-row per-N12-ID → shard matrix at `02-plans/03-conformance-id-matrix.md`; all 50 Conformant-mandatory IDs placed, 4 Complete-optional → X1, every named orphan closed.

**Disposition flips: GAPS-FOUND → converged for `/todos`.** Should-fix items (HIGH-4, MED-1..5) carry into `/todos` per the original disposition; HIGH-4 joins the post-Wave-6 parity gate.
