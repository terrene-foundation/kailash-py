# rs handoff — BH3 origin-authentication signing pre-images (Python reference)

Status: **READY** — the Python SDK is the Foundation reference; the Rust SDK
mirrors these exact pre-image byte forms (EATP D6: independent implementation,
byte-identical cross-verification).

BH3 (issue acceptance criterion): bind an agent-declared action-trace to its
ORIGINATING INSTRUCTION — not merely sign the submitted trace. A fabricated
trace MUST fail authentication even when it passes an Ed25519 signature check.
SAFR v1.0 (§ The Governance Envelope) *recommends* a trace be "authenticated
against its origin, not merely as a record of what the agent reported"; SAFR is
a non-binding white paper — derive with "specifies/recommends", never "requires".

> If the Rust SDK has already pinned a divergent origin pre-image format, flag
> for reconciliation BEFORE either side pins — the two MUST be byte-identical
> for cross-verification (EATP D6).

---

## 1. The two signed pre-image forms

Both forms are canonicalized by the trust-plane signing encoder
(`serialize_for_signing`: `sort_keys=true`, `separators=(",",":")`,
`ensure_ascii=true`, non-finite floats rejected — the issue-#959 canonical
contract the Rust side already mirrors for reasoning-trace signatures). The base
payload is `ReasoningTrace.to_signing_payload()` (sorted keys).

**Form 1 — without origin binding** (backward-compatible): byte-IDENTICAL to the
CURRENT reasoning-trace signing pre-image. No `origin` key in the signed bytes.
An unbound trace signature verifies exactly as it did pre-BH3.

**Form 2 — with origin binding**: Form-1 payload PLUS a single `origin` key whose
value is the origin digest (see §2). Under `sort_keys=true` the `origin` key
sorts between `methodology` and `rationale`; no other byte changes vs Form 1.

## 2. Origin-digest input definition

`origin_digest = "sha256:" + hex(sha256(jcs_encode(originating_instruction)))`

- `jcs_encode` is the RFC 8785 (JSON Canonicalization Scheme) encoder already
  shipped for the `subject_hash` work (the conditional-`subject_hash` audit-anchor
  feature). REUSE it — do NOT write a second canonicalizer. The digest is over
  CANONICAL bytes, never a naive `str()`.
- Format is exactly `sha256:<64-lowercase-hex>` (matches the `subject_hash`
  prefix convention).
- Fail-closed at sign time: a non-finite float / non-JSON-native instruction
  raises (RFC 8785 rejects it) rather than producing an unauthenticatable record.

## 3. Discriminator-exclusion + fail-closed contract

- A record carries an `origin_bound` boolean discriminator. It is **EXCLUDED
  from the signed pre-image**.
- Deserialization defaults a MISSING `origin_bound` to `false`. Stripping the
  discriminator on a Form-2 record forces the Form-1 (no-origin) reconstruction,
  so a signature made over Form-2 no longer matches → REJECT. (Same shape as the
  `schema_version`-exclusion trick in the conditional-`subject_hash` feature.)
- Verification is fail-closed on EVERY path (return reject/false, never
  silent-pass, never raise-out):
  - **Bound record + authoritative instruction**: (1) Ed25519-verify the
    signature over the Form-2 pre-image reconstructed from the record's STORED
    origin digest (integrity); then (2) recompute the digest from the
    AUTHORITATIVE instruction the verifier holds and constant-time-compare to
    the stored digest (origin authentication). A mismatch REJECTS even when the
    signature is valid — the fabricated-trace defense.
  - **Bound record, no instruction supplied**: REJECT (cannot authenticate an
    origin claim on integrity alone).
  - **Unbound record, instruction demanded**: REJECT (downgrade defense — an
    unbound record makes no authenticatable claim).
  - **Unbound record, no instruction**: verify the Form-1 pre-image
    (backward-compatible plain trace signature).

## 4. Verified golden vectors (byte-pinned)

Produced by executing the reference implementation this session. The Rust side
MUST reproduce the pre-image string byte-for-byte and the SHA-256 exactly.

Fixture trace (sorted signing payload):
`{"alternatives_considered":["defer"],"confidence":0.9,"confidentiality":"restricted","decision":"approve deploy","evidence":[{"cost":500}],"methodology":"cost_benefit","rationale":"cost within envelope","timestamp":"2026-01-15T10:30:00+00:00"}`

Originating instruction:
`{"instruction":"deploy service X to staging","issued_by":"D1-R1","nonce":"abc123"}`

**Vector A — without origin (Form 1)**
- `expected_signing_preimage` =
  `{"alternatives_considered":["defer"],"confidence":0.9,"confidentiality":"restricted","decision":"approve deploy","evidence":[{"cost":500}],"methodology":"cost_benefit","rationale":"cost within envelope","timestamp":"2026-01-15T10:30:00+00:00"}`
- `sha256(preimage)` = `0d2a1d1cc71e316b6f3fe334a4c24a8d523d7d95e0bbfc9d73a6cbe8015cae94`

**Vector B — with origin (Form 2)**
- `origin_digest` = `sha256:be309592b937446a1e63c99921f72d200a44096a5e8cd73a4e450271371276fc`
- `expected_signing_preimage` =
  `{"alternatives_considered":["defer"],"confidence":0.9,"confidentiality":"restricted","decision":"approve deploy","evidence":[{"cost":500}],"methodology":"cost_benefit","origin":"sha256:be309592b937446a1e63c99921f72d200a44096a5e8cd73a4e450271371276fc","rationale":"cost within envelope","timestamp":"2026-01-15T10:30:00+00:00"}`
- `sha256(preimage)` = `7f14605527f68692f0133f737eabb89c7474a82f90672ec617fcd818099c05de`

Invariant: `Form-2-preimage` with the `"origin":"<digest>",` segment removed is
byte-identical to `Form-1-preimage` (Vector A). Vectors are shipped as conformance
fixtures (`bh3_origin_bound.json` / `bh3_origin_unbound.json`) pinning the raw
pre-image string + its sha256 (NOT a startswith), integrity-manifested.

## 5. Testable acceptance criteria for the Rust SDK to mirror

1. **Without-origin byte identity** — the Form-1 pre-image equals the current
   (pre-BH3) reasoning-trace pre-image byte-for-byte; an unbound signature
   verifies via the existing reasoning-trace verify path.
2. **With-origin verify passes** — a bound record authenticates against the true
   originating instruction.
3. **Fabricated origin fails despite a valid signature** — a record whose declared
   origin digest != the digest of the authoritative instruction is REJECTED even
   though its Ed25519 signature verifies over the signed pre-image.
4. **Discriminator strip fails closed** — dropping `origin_bound` from a bound
   record forces the unbound reconstruction → signature mismatch → REJECT (both
   with and without the authoritative instruction).
5. **Bound-without-instruction fails closed**; **unbound-with-instruction-demanded
   fails closed** (downgrade defense); **claims-bound-but-no-digest fails closed**.
6. **Golden-vector reproduction** — the Rust encoder reproduces Vector A and
   Vector B pre-image strings + SHA-256 byte-for-byte.
