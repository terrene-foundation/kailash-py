# Cross-SDK Parity — kailash-py ↔ kailash-rs

Read-only assessment per the user directive "ensure kailash-rs is on parity with this as well" (2026-06-14). Cross-repo READ authorized + journaled at `journal/0003`. **No cross-repo write has been made**; the two comment-drafts below are GATED on user approval per `upstream-issue-hygiene.md` MUST-1.

## Thread 1 — EATP-08 ISS-32 (v1.1.1 bare-literal ruling)

|                  | kailash-py                                                                                                | kailash-rs                                                                                                                                                   |
| ---------------- | --------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| State            | **MERGED** — #1315 (`c2185d35e`) + spec sync #1317 (`3e9ebfef8`)                                          | **NOT on parity**                                                                                                                                            |
| Tracker          | (closed via #1315)                                                                                        | **#1315 OPEN** — "EATP-08 v1.1: adopt eatp-v1 registry + top-level alg_id wire shape" (sibling of py#1304); broader v1.1 adoption, ISS-32 not yet called out |
| Canonical vector | `eatp08-alg-id-canonical.json` — bare-top-level-string row → `unsupported-algorithm` (both witness cases) | `test-vectors/signed-artifact-vectors.json` carries only the **nested** `{"algorithm":"ed25519+sha256"}` D2d form; **no bare-top-level-string row**          |

**Finding:** mint's py-#1315 body cited `kailash-rs#1315` as the sibling, but rs#1315 is the _v1.1 adoption_ tracker (unimplemented), not an ISS-32 fix. rs has not adopted the top-level alg_id wire shape at all yet, so the v1.1.1 bare-literal parity bar (bare top-level literal → `unsupported-algorithm`, witness MUST NOT rescue) is unrepresented on the rs side.

**Parity action (GATED — draft comment for rs#1315):**

> EATP-08 v1.1.1 / mint#26 (ISS-32) parity bar — when rs adopts the top-level `alg_id` wire shape, a **bare top-level-string** `alg_id` equal to the deprecated literal `ed25519+sha256` MUST reject with `unsupported-algorithm` (§3.3 / §5.1 step 2), with OR without a D2d witness — it is NOT a D2d pre-registry form. A present `alg_id` key MUST be authoritative (a sibling `algorithm` key MUST NOT rescue a bare literal). The two D2d forms remain the nested-object `alg_id` value and unsigned `algorithm` metadata. Canonical-vector parity: add the `deprecated_pre_registry_literal_bare_top_level_string` row matching kailash-py's `eatp08-alg-id-canonical.json`. (Reference: kailash-py #1315 merged 2026-06-14.)

## Thread 2 — EATP-12 Trust Vault Key-Binding

|                          | kailash-py                                                                     | kailash-rs                                                             |
| ------------------------ | ------------------------------------------------------------------------------ | ---------------------------------------------------------------------- |
| Tracker                  | **#1312 OPEN** (this workspace; 6-wave plan in `01-architecture-and-waves.md`) | **#1316 OPEN** — scope-aligned cross-SDK sibling; flags V6 byte-parity |
| EATP-10 Shamir substrate | **PRESENT** (`trust/vault/shamir.py`, reused)                                  | **ABSENT** — prerequisite **#1206 OPEN** (rs needs the wrapper first)  |
| Binding layer            | ~0% (stub) — plan ready                                                        | 0% (no vault code)                                                     |

**Finding:** EATP-12 parity is correctly tracked on both sides; rs is one substrate-layer behind (needs #1206 before #1316). The cross-SDK byte-parity gate (V6: KEK-identity commitment + KCV + audit canonical pre-image) is the release-coordination point — **neither SDK may release vault binding before this is reconciled.**

**The non-ASCII encoder finding (this session's `journal/0002`) MUST flow to rs#1316:** the §12 golden fixtures are ASCII-only, so the delegate-family (`ensure_ascii=False`, RFC-8785/JCS, matches Rust `serde_json`) vs signing-family (`ensure_ascii=True`) encoder divergence is invisible. Python MUST use the `ensure_ascii=False` JCS encoder for the commitment + add a non-ASCII sentinel vector; rs `serde_json` is natively raw-UTF-8 — so the two are parity-compatible ONLY if py picks the JCS encoder. This must be a shared acceptance criterion.

**Parity action (GATED — draft comment for rs#1316):**

> Cross-SDK byte-parity note (V6) — the EATP-12 commitment + KCV pre-image use RFC-8785/JCS canonical JSON (raw UTF-8, `ensure_ascii=False`), matching Rust `serde_json` default. The §12 Appendix B golden fixtures are ASCII-only, so the encoder choice is invisible in them; both SDKs MUST add a **non-ASCII `vault_id` sentinel vector** and reconcile its commitment hash byte-for-byte before either releases vault binding. (kailash-py records this as the load-bearing C1 decision; see py #1312.)

## Disposition

1. **EATP-12 trackers are parity-aligned** (py#1312 ↔ rs#1316); no new issue to file.
2. **Two GATED comment-drafts** above add the missing parity bars (rs#1315 ISS-32 vector row; rs#1316 non-ASCII encoder reconciliation). Post only on user y/n; each is a cross-repo write needing the `upstream-issue-hygiene.md` MUST-1 gate.
3. rs is substrate-behind on EATP-12 (#1206 Shamir) — surfaced for the user's cross-repo prioritization; not actionable from inside kailash-py.
