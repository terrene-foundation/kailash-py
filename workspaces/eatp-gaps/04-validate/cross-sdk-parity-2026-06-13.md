# Cross-SDK Trust-Plane Parity Audit — kailash-py vs kailash-rs (2026-06-13)

**Scope:** comprehensive cross-SDK parity of the shared signed-record / EATP trust-wire
contract (the surface that MUST byte-align per EATP D6). Independent-implementation
domains (DataFlow, Nexus, ML) are out of scope — they share no wire contract.

**Method:** READ-only, authorized per `workspaces/eatp-gaps/journal/0001-DECISION-cross-repo-authorized-rs-alg-id-parity.md`.
Keystone (alg_id) compared by hand; broader surface via 3 parallel READ-only agents.
Every claim cites `file:line` in one of:

- py: `/Users/esperie/repos/loom/kailash-py` (branch `feat/eatp08-v1.1-conformance`)
- rs: `/Users/esperie/repos/loom/kailash-rs` (`main`, workspace v4.7.0, `crates/eatp` 0.1.0)

---

## Headline

The cross-SDK trust-wire contract has **diverged in a wire-breaking way**. The immediate
cause is asymmetric EATP-08 adoption: **kailash-py advanced to EATP-08 v1.1** (`eatp-v1`,
top-level `alg_id` string) on `feat/eatp08-v1.1-conformance`; **kailash-rs is still on the
pre-publication #604/#519 scaffold** (`ed25519+sha256`, nested `{"algorithm":"<id>"}`,
comment "awaiting mint ISS-31"). A record signed by either SDK now fails the other's
verifier. This is exactly the gate #1304 flagged: **do NOT release `kailash` with eatp-v1
until rs ships the matching adoption.**

Underneath that, the audit surfaced **pre-existing parity debt** independent of EATP-08.

---

## CRITICAL findings

### C1 — alg_id wire shape is mutually incompatible

- py: `AlgorithmIdentifier.to_dict() → {"alg_id":"eatp-v1"}` — top-level string token
  (`src/kailash/trust/signing/algorithm_id.py:61,393-402`).
- rs: `AlgorithmId::to_canonical_bytes() → {"algorithm":"ed25519+sha256"}` — nested object
  (`crates/eatp/src/algorithm.rs:88,119-129`).
- Because `alg_id` is inside the JCS canonical signing pre-image on both sides, the canonical
  bytes differ for the same logical record → Ed25519 verify fails cross-SDK. py §32.1
  explicitly marks the rs nested form NON-conformant; py accepts it ONLY via the D2d legacy
  path with a dated pre-adoption witness. rs has no concept of `eatp-v1`, no registry, no
  `D2dWitness`, no `unsupported-algorithm` code.
- **Propagation:** the rs nested form is not isolated to one identifier — it is embedded in
  rs `signed_artifact.rs:105` and `audit/mod.rs::seal_audit_event:205`, so every rs
  signed-record surface carrying the algorithm field is divergent.

### C2 — contract version is one major apart, untracked by any shared field

- py declares "EATP-08 v1.1 / eatp-v1 / ADOPTION_DATE 2026-04-26" (`specs/trust-crypto.md:675,691,697`).
- rs declares "EATP v0.8.0 / issue #519 scaffold / mint ISS-31" (`specs/eatp.md:3`, `algorithm.rs:63,66`).
- rs has **zero** `eatp-v1` / `EATP-08` occurrences anywhere in its specs or crates. rs carries
  no reciprocal "coordinate before release" reference — the drift is one-directional and
  tracked only in prose, not in any version field.

---

## HIGH findings

### H1 — conformance vectors are PARALLEL-AUTHORED, not vendored (cross-sdk-inspection Rule 4a)

- `trust-plane-canonical.json`: py `tests/test-vectors/` (sha256 `ade951ea…`, 11 vectors,
  `contract:"trust-plane-canonical-bytes"`, `version:"1.0.0"`, `$type`-tagged) vs rs
  `crates/eatp/test-vectors/` (sha256 `c0e64668…`, 19 vectors, `contract:"canonical-trust-plane-v1"`,
  `version:1`, flat). Files differ; only overlapping vector _values_ coincidentally hash-match.
- `audit-chain-canonical.json`: py 2 vectors vs rs 7 (parallel; 2 SHA pins overlap).
- `signed-artifact-vectors.json`: exists **only** on rs (`crates/eatp/tests/signed_artifact_vectors.rs`);
  its header claims "byte-for-byte identical between kailash-rs and kailash-py" but the py
  sibling **never landed**. So the signed-record byte contract is unverified on the py side —
  and the rs vectors pin the OLD nested `alg_id` shape.
- **Reference pattern that IS correct:** `trace-event-canonical.json` is vendored byte-identical
  (per rs PR #761). The others should follow it.

### H2 — three signing surfaces are PY-ONLY (no rs verifier exists)

- Signed CRL (`src/kailash/trust/signing/crl.py:543`) — rs has only a `revoked: bool` flag on
  `DelegationRecord` (`crates/eatp/src/delegation.rs:131`), no signed CRL structure.
- Signed timestamp tokens (`src/kailash/trust/signing/timestamping.py:88`) — rs has only an
  **unsigned** `Rfc3161Timestamp` placeholder (`crates/eatp/src/chain.rs:38`).
- Messaging `SecureMessageEnvelope` (`src/kailash/trust/messaging/envelope.py:181`) — no rs
  counterpart. These break EATP D6 by absence, not drift.

---

## MEDIUM findings

### M1 — canonical-JSON ENGINE is aligned, but two high-traffic records bypass it

- ✅ py `serialize_for_signing` (`crypto.py:225-326`) and rs `canonicalize`
  (`crates/eatp/src/canonical.rs:98`) are byte-for-byte aligned (sort_keys, `separators=(",",":")`,
  `ensure_ascii=True`/`\uXXXX`, UTF-16 surrogate pairs, no Unicode normalization) and
  fixture-pinned (#959). This is the solid foundation.
- ⚠️ rs maintains **two parallel canonicalizers** (`crates/eatp/src/canonical.rs` +
  `crates/trust-plane/src/canonical.rs`) with no cross-test pinning them byte-equal.
- ⚠️ rs `AuditEvent::compute_hash` (`audit/mod.rs:113-155`) hand-rolls field concatenation
  incl. `f64::to_le_bytes` for `duration_ms` — platform/representation-specific, NOT routed
  through `canonicalize`; not cross-SDK-reproducible.
- ⚠️ py `SecureMessageEnvelope.get_signing_payload` (`envelope.py:233`) concatenates fields as
  a raw string instead of using py's own JCS serializer — inconsistent within py itself.

### M2 — the primary delegation/chain record carries NO alg_id on EITHER side

- py `trust/chain.py:148` uses free-text `signature_algorithm:"Ed25519"`; rs `DelegationRecord`
  (`delegation.rs:106-163`) has no algorithm field at all. The most-used signed record in both
  SDKs is OUTSIDE the EATP-08 agility migration — a future rotation has no wire signal there.

### M3 — delegate conformance vectors only partially overlap

- py ships 5 DV vectors as JSON (`tests/fixtures/delegate-conformance/canonical.json`:
  DV-3/5/7/9/10); rs ships only DV-5 + DV-10 as in-code Rust
  (`crates/kailash-delegate-conformance/vectors/catalog.rs`). DV-3 (envelope tighten),
  DV-7 (TAOD monotonicity), DV-9 (audit round-trip) have no rs counterpart. Vectors are not a
  shared file, so agreement rests on the SHA-receipt protocol, not a common fixture.

### M4 — fingerprint_secret aligned but under-pinned

- py `url_credentials.py:459` and rs `crates/kailash-core/src/fingerprint.rs:133` both
  BLAKE2b-4 / 8-hex / empty→`"00000000"`. But py has no byte-vector regression test pinning
  rs output — cross-sdk-inspection Rule 4's ≥3-vector requirement is only half-met.

---

## Parity scorecard

| Surface                                                  | Verdict                                             |
| -------------------------------------------------------- | --------------------------------------------------- |
| Canonical-JSON engine                                    | ✅ ALIGNED (fixture-pinned)                         |
| fingerprint_secret algorithm+sentinel                    | ✅ ALIGNED (under-tested)                           |
| trace-event-canonical.json                               | ✅ VENDORED (reference pattern)                     |
| Trust scoring / sealed audit / genesis-chain / multi-sig | ◑ semantic PARITY (multi-sig byte-shape unverified) |
| alg_id wire shape                                        | ❌ DIVERGED (wire-breaking)                         |
| EATP contract version                                    | ❌ DIVERGED (one major apart)                       |
| trust-plane / audit-chain / signed-artifact vectors      | ❌ PARALLEL-AUTHORED (Rule 4a)                      |
| Signed CRL / timestamp tokens / messaging envelope       | ❌ PY-ONLY (no rs verifier)                         |
| audit-hash + messaging pre-image                         | ❌ bypass shared canonicalizer                      |
| primary delegation/chain alg_id                          | ❌ absent both sides                                |

---

## Disposition (recommendations — NOT executed; cross-repo writes need user gate)

1. **Gate the py release.** PR #1309 (py EATP-08 v1.1) stays LAND-not-release until rs ships
   matching `eatp-v1` adoption. (Already the PR's stated posture.)
2. **rs needs an EATP-08 v1.1 port** mirroring py `algorithm.rs`: `eatp-v1` registry token,
   top-level `alg_id` string wire shape, registry + `unsupported-algorithm` dispatch, D2d
   witnessed legacy path. This is the rs sibling of #1304 — file on kailash-rs (human-gated,
   scrubbed per upstream-issue-hygiene).
3. **Resolve the ed25519+sha256 transition** — still an open Foundation/mint erratum question
   (#1304); the D2d path is the py-side bridge but the registry-alias ruling is unresolved.
4. **Vendor the conformance vectors** (Rule 4a): land the py `signed-artifact-vectors.json`
   sibling; reconcile the two `trust-plane-canonical.json` / `audit-chain-canonical.json` to a
   single vendored file with alg_id-bearing vectors in the new `eatp-v1` shape.
5. **Pre-existing debt** (independent of EATP-08, file as separate cross-SDK issues): rs
   two-canonicalizer cross-pin; rs audit-hash routing through `canonicalize`; py messaging
   pre-image using JCS; the PY-ONLY CRL/timestamp/messaging surfaces.

Receipts: this file + the 3 agent transcripts (ids ab933ccdf4bfbb3c3, a51a9df3a6fd1ac17,
ae35ef873a060b61d).
