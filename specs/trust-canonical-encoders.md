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

Common config for Family B: `sort_keys=True, separators=(",",":"),
ensure_ascii=True, allow_nan=False` (the `envelope_hash`/audit-anchor metadata
sites omit `separators` — compact whitespace is already the default for those
sort-keyed dumps).

† **Byte-changing members are pinned on `default=str` by the cross-SDK byte
contract, not by an oversight.** `to_canonical_json` serializes the free-form
`metadata: dict[str, Any]` (an unvalidated typed scalar there — `datetime` /
`set` / `bytes` — renders differently under `canonical_scalars`), and the
selective-disclosure witness family hashes a nested `chain.AuditAnchor`
dataclass that `_audit_record_to_dict` does not pre-normalize. Switching either
to `canonical_scalars` py-only would diverge the emitted bytes from the
kailash-rs counterpart that mirrors the current `default=str` output — the same
class of breaking change as the audit-chain timestamp format (`kailash-rs#449`
lockstep). The current bytes are pinned by
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
  dataclass and free-form envelope `metadata`, respectively). Because they are
  documented cross-SDK byte contracts that kailash-rs mirrors on the current
  `default=str` output, a py-only switch would diverge the SDKs — the same class
  as the audit-chain timestamp change. They remain on `default=str` and their
  CURRENT bytes are pinned by
  `tests/regression/test_canonical_encoder_family_conformance.py` (these are
  also `selective_disclosure.py`'s first tests). A coordinated cross-SDK
  migration, if undertaken, must change both SDKs in lockstep and re-pin the
  vectors together, never py-only.

**Local (no cross-SDK contract) sites keep `default=str` by design:**
`decorators._hash_result` (a local 16-char fingerprint of an arbitrary
decorated-function return; the cross-SDK contract is downstream at
`serialize_for_signing`) and `dataflow/trust/audit.py::compute_query_hash` (a
DataFlow-local privacy-truncated dedup hash, self-verified, no Rust counterpart).

## Cross-SDK note

Both families are documented cross-SDK byte contracts (kailash-rs#449). Any
change to a Family-B canonical byte (the audit-chain timestamp/metadata format,
the trace-event fingerprint) is a **breaking cross-SDK change**: the kailash-rs
counterpart must land identical changes in lockstep and the vendored fixtures
(`test-vectors/*-canonical.json`) re-vendored, or the SDKs produce divergent
bytes for the same logical input. See `rules/cross-sdk-inspection.md` Rule 4 +
`test-vectors/README.md`.
