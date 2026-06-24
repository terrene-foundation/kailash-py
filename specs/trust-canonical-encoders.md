# Trust Plane — Canonical JSON Encoder Families

Parent domain: Kailash Trust Plane. This sub-spec is the single index of the
canonical-JSON encoders used across the trust plane, their exact serde
configuration, and which subsystems use which (issue #1403). It exists so a
reader can answer "which byte contract applies on this input?" without grepping
every call site. See `trust-crypto.md` for signing and `trust-eatp.md` for the
EATP protocol.

---

## The two families

There are **two** canonical-JSON byte contracts, split on `ensure_ascii`. The
split is intentional and documented (issue #1258); the two families never
cross-mix.

### Family A — DELEGATE (`ensure_ascii=False`, raw UTF-8)

Matches Rust `serde_json::to_string`'s default output (no `\uXXXX` escaping).

| Encoder                                               | Location                                 | Config                                                                      |
| ----------------------------------------------------- | ---------------------------------------- | --------------------------------------------------------------------------- |
| `canonical_json_dumps`                                | `kailash/trust/_json.py`                 | `sort_keys=True, separators=(",",":"), ensure_ascii=False, allow_nan=False` |
| `_canonical_json_bytes` (delegate conformance digest) | `kailash/delegate/conformance/schema.py` | same config, inlined (import-minimization fence)                            |
| EATP-12 KEK commitment / KCV                          | `kailash/trust/vault/commitment.py`      | via `canonical_json_dumps`                                                  |

### Family B — SIGNING / HASH (`ensure_ascii=True`, ASCII-escaped)

Matches Rust `serde_json::to_string(&BTreeMap)` with non-ASCII escaped to
`\uXXXX`. **Typed scalars** (`Decimal` / `UUID` / `datetime` / `set` / `bytes` /
`Enum` / dataclass) route through the **single shared whitelist**
`kailash.trust._canonical.canonical_scalars` — there is **no `default=str`**
fallback (`str(obj)` is implementation-defined and breaks cross-version /
cross-SDK byte parity).

| Encoder                                                | Location                                        | Typed-scalar policy                                       |
| ------------------------------------------------------ | ----------------------------------------------- | --------------------------------------------------------- |
| `serialize_for_signing`                                | `kailash/trust/signing/crypto.py`               | `canonical_scalars` whitelist (no `default=str`)          |
| `AuditAnchor._canonical_input` (metadata)              | `kailash/trust/pact/audit.py`                   | `canonical_scalars` whitelist (no `default=str`)          |
| `compute_trace_event_fingerprint` (`_canonical_json`)  | `kailash/diagnostics/protocols.py`              | `canonical_scalars` whitelist (no `default=str`)          |
| `ConstraintEnvelope.envelope_hash`                     | `kailash/trust/envelope.py`                     | `canonical_scalars` whitelist (no `default=str`)          |
| `ConstraintEnvelope.to_canonical_json` (HMAC preimage) | `kailash/trust/envelope.py`                     | `default=str` — byte-CHANGING under `canonical_scalars` † |
| selective-disclosure witness family                    | `kailash/trust/enforce/selective_disclosure.py` | `default=str` — byte-CHANGING under `canonical_scalars` † |

Common config for the Family-B **wire-format** members (`serialize_for_signing`,
`AuditAnchor._canonical_input`, `compute_trace_event_fingerprint`,
`to_canonical_json`): `sort_keys=True, separators=(",",":"), ensure_ascii=True,
allow_nan=False`. **`envelope_hash` is the deliberate exception:** it omits
`separators`, so it serialises with Python's DEFAULT `(", ", ": ")` (spaced, NOT
compact) and the default `ensure_ascii=True`. The spaced form is itself part of
the envelope tamper-hash contract — the Rust SDK + the `tests/fixtures/cross-sdk/envelope/`
vectors reproduce this exact (spaced) serialisation; the `canonical_scalars`
switch left it byte-identical.

† **Byte-changing members are pinned on `default=str` by the cross-SDK byte
contract, not by an oversight.** `to_canonical_json` serializes the free-form
`metadata: dict[str, Any]` (an unvalidated typed scalar there — `datetime` /
`set` / `bytes` — renders differently under `canonical_scalars`), and the
selective-disclosure witness family hashes a nested `chain.AuditAnchor`
dataclass that `_audit_record_to_dict` does not pre-normalize. Switching either
to `canonical_scalars` py-only is an UNCOORDINATED cross-SDK byte change and is
BLOCKED. Per `kailash-rs#1452` (2026-06-20), kailash-rs is on its `#449`-conformant
`canonicalize` encoder for these surfaces — NOT a `default=str`-class encoder (the
INVERSE of py here). The cross-SDK alignment is now
RESOLVED by `kailash-rs#1451` (PR #1504, 2026-06-20): the canonical direction is
`+00:00`, and kailash-rs is the converging side — it re-signs its own artifacts to
that direction (the witness-redaction partition is 3 cross-SDK-agreeing
subject-keyed vectors + 4 timestamp-bearing divergent vectors). py's current
`default=str` bytes stay pinned until that convergence re-sign executes; the
re-sign is a coordinated cross-SDK lockstep, never py-only — the same discipline as
the audit-chain timestamp format (`kailash-rs#449`/`#1448`). The current bytes are pinned by
`tests/regression/test_canonical_encoder_family_conformance.py` so a silent
py-only switch fails loudly. See § Cross-SDK note.

### Timestamp rendering — a deliberate asymmetry

The PACT audit chain renders an anchor's OWN top-level `timestamp` via
`isoformat(timespec="microseconds")` — always six fractional digits + `+00:00`
(issue #1400). A `datetime` VALUE nested inside metadata (or a trace-event
`payload`), however, renders via `canonical_scalars` as a plain `isoformat()`,
so a whole-second metadata datetime emits NO fractional part. This asymmetry is
intentional: nested datetimes follow the established `serialize_for_signing`
signing-family contract (bare `isoformat()`, issue #959), and changing them to
fixed-width would break every existing trust-plane signature. A peer SDK MUST
render nested datetimes with bare `isoformat()` (and the anchor timestamp with
six digits) to stay byte-equal — pinned by `U6_whole_second_metadata_datetime`
in `test-vectors/audit-chain-canonical.json`; cross-SDK confirmation is part of
the kailash-rs#449 lockstep.

---

## Status (2026-06-20 canonical-conformance fix + family sweep)

The #1400-#1407 fix extracted the typed-scalar whitelist into
`kailash.trust._canonical.canonical_scalars` and routed the audit-chain +
trace-event fingerprint paths through it, joining `serialize_for_signing` so
those three members share **one** deterministic policy (issues #1403 / #1405).

A follow-up empirical byte-diff sweep then classified **every** remaining
`json.dumps(..., default=str)` site in the trust plane against
`canonical_scalars` (97 occurrences; 8 candidate signing/hash sites, 89 local
persistence/display/dedup sites where `default=str` is correct). Two further
dispositions landed:

- **`ConstraintEnvelope.envelope_hash` → `canonical_scalars` (shipped).** The
  constraint `to_dict()` layer already pre-normalizes every divergent type and
  `_hashable_dict` excludes the free-form `metadata` dict, so the swap is
  byte-neutral on every current envelope — the #1403/#1405 latent-divergence
  closure pattern. Pinned by `test_envelope_hash_pinned_byte_vector`.
- **Byte-changing members stay on `default=str`, pinned, not switched.** The
  selective-disclosure witness family (`_hash_value` / `_compute_chain_hash` /
  the export+verify sign-payloads) and `ConstraintEnvelope.to_canonical_json`
  are byte-CHANGING under `canonical_scalars` (nested `chain.AuditAnchor`
  dataclass and free-form envelope `metadata`, respectively). They are documented
  cross-SDK byte contracts, so a py-only switch is an uncoordinated cross-SDK change
  and is BLOCKED. Per `kailash-rs#1452` (2026-06-20), kailash-rs is on its
  `#449`-conformant `canonicalize` encoder for these surfaces (the INVERSE of py's
  `default=str`); the cross-SDK alignment is now resolved by `kailash-rs#1451`
  (PR #1504, 2026-06-20): the canonical direction is `+00:00` and kailash-rs is the
  converging side (it re-signs its own artifacts; the convergence re-sign is the
  remaining coordinated lockstep, never py-only). They remain on
  `default=str` and their CURRENT bytes are pinned by
  `tests/regression/test_canonical_encoder_family_conformance.py` (the first
  byte-conformance tests of `selective_disclosure.py`'s witness-encoder family —
  `_hash_value` / `_compute_chain_hash` / the export+verify sign-payloads; the
  module's redaction helpers `_redact_record` / `RedactedAuditRecord` already
  have prior coverage in `tests/trust/unit/`). A coordinated cross-SDK
  migration, if undertaken, must change both SDKs in lockstep and re-pin the
  vectors together, never py-only.

**Local (no cross-SDK contract) sites keep `default=str` by design:**
`_hash_result` (`src/kailash/trust/enforce/decorators.py:302-307` — a local
16-char fingerprint of an arbitrary decorated-function return; the cross-SDK
contract is downstream at `serialize_for_signing`, which signs the already-hashed
string) and `compute_query_hash`
(`packages/kailash-dataflow/src/dataflow/trust/audit.py:663-687` — a
DataFlow-local privacy-truncated dedup hash, self-verified, no Rust counterpart).

## Cross-SDK note

Both families are documented cross-SDK byte contracts (kailash-rs#449). Any
change to a Family-B canonical byte (the audit-chain timestamp/metadata format,
the trace-event fingerprint) is a **breaking cross-SDK change**: the kailash-rs
counterpart must land identical changes in lockstep and the vendored fixtures
(`test-vectors/*-canonical.json`) re-vendored, or the SDKs produce divergent
bytes for the same logical input. See `rules/cross-sdk-inspection.md` Rule 4 +
`test-vectors/README.md`.

---

## Cross-implementation enforcement status (in-repo vs deferred)

This index answers a question distinct from § The two families (which asks
"which encoder config applies on this input?"): **which canonical contracts
have their cross-implementation byte equality ENFORCED by this repo's CI, vs
DEFERRED to an external gate?** (issue #1402).

Today **no in-repo test ingests an independently-produced kailash-rs digest** —
every row below is either a Python-self-consistent byte-pin (the Python
production path reproduces its own pinned fixture) or a fixture vendored from
kailash-rs. The independent rust digest is checked at the named external gate,
NOT here. A test docstring or fixture comment that reads as "BOTH SDKs MUST
produce byte-for-byte" describes the byte-pin CONTRACT the rs side is expected
to meet — it does NOT mean this repo's CI verifies the rs side.

| Canonical contract / fixture                       | Encoder / site                                                             | In-repo enforcement                                                         | Independent cross-SDK check deferred to                                                 |
| -------------------------------------------------- | -------------------------------------------------------------------------- | --------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| `test-vectors/audit-chain-canonical.json`          | `AuditAnchor._canonical_input` / `compute_hash`                            | Python-self-consistent byte-pin                                             | post-Wave-6 cross-SDK gate (kailash-rs#449)                                             |
| `test-vectors/trace-event-canonical.json`          | `compute_trace_event_fingerprint` / `_canonical_json`                      | Python-self-consistent byte-pin                                             | post-Wave-6 cross-SDK gate (kailash-rs#449)                                             |
| `tests/test-vectors/trust-plane-canonical.json`    | `serialize_for_signing`                                                    | Python-self-consistent byte-pin                                             | external cross-SDK gate (kailash-rs#449 / #1451)                                        |
| `tests/test-vectors/delegate-canonical.json`       | `canonical_json_dumps`                                                     | Python-self-consistent byte-pin                                             | external cross-SDK gate (kailash-rs#449 / #1451)                                        |
| `tests/test-vectors/eatp12-vault-canonical.json`   | vault `kek_identity_commitment` / `key_check_value` + EATP-12 audit-anchor | Python-self-consistent byte-pin                                             | post-Wave-6 cross-SDK gate                                                              |
| `tests/test-vectors/eatp08-alg-id-canonical.json`  | `serialize_for_signing` (alg_id wire)                                      | Python-authored byte-pin                                                    | kailash-rs VENDORS the file byte-for-byte (esperie-enterprise/kailash-rs#1315, Rule 4a) |
| `tests/trust/pact/conformance/vectors/*` (PACT N6) | audit-anchor / governance canonical                                        | Python-self-consistent byte-pin + `shasum -c PACT_VECTORS.sha256` integrity | external cross-SDK gate                                                                 |
| `tests/fixtures/cross-sdk/{jsonrpc,envelope,...}`  | `JsonRpcRequest` / `ConstraintEnvelope.to_canonical_json` etc.             | Python-self-consistent byte-pin + `shasum -c VECTORS.sha256` integrity      | external cross-SDK gate (EATP D6)                                                       |

To upgrade a row from "Python-self-consistent" to in-repo cross-impl
enforcement, vendor the independently-produced golden from kailash-rs (per
`rules/cross-sdk-inspection.md` Rule 4a) and add a conformance job so an rs-side
divergence fails CI here — the broader cross-SDK byte gate is `kailash-rs#449`
(the canonical-encoder alignment item `kailash-rs#1451` was resolved by PR #1504). The
`test-vectors/README.md` § "Cross-impl enforcement — honest status" carries the
same status for the two repo-root fixtures; each `tests/test-vectors/*.json`
fixture carries its producer + `cross_impl_status` in its own `provenance` block
(or, for `eatp08-alg-id-canonical.json`, in its `description`).
