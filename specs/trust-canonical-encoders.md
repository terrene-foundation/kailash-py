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

| Encoder                                               | Location                                        | Typed-scalar policy                                   |
| ----------------------------------------------------- | ----------------------------------------------- | ----------------------------------------------------- |
| `serialize_for_signing`                               | `kailash/trust/signing/crypto.py`               | `canonical_scalars` whitelist (no `default=str`)      |
| `AuditAnchor._canonical_input` (metadata)             | `kailash/trust/pact/audit.py`                   | `canonical_scalars` whitelist (no `default=str`)      |
| `compute_trace_event_fingerprint` (`_canonical_json`) | `kailash/diagnostics/protocols.py`              | `canonical_scalars` whitelist (no `default=str`)      |
| selective-disclosure witness signers                  | `kailash/trust/enforce/selective_disclosure.py` | **still `default=str`** — NOT yet unified (follow-up) |

Common config for Family B: `sort_keys=True, separators=(",",":"),
ensure_ascii=True, allow_nan=False`.

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

## Status (2026-06-20 canonical-conformance fix)

Before this fix the Family-B members **diverged on typed-scalar inputs**:
`serialize_for_signing` carried the whitelist while the audit-chain and
trace-event fingerprint paths used `json.dumps(..., default=str)`. The fix
extracted the whitelist into `kailash.trust._canonical.canonical_scalars` and
routed the audit + fingerprint paths through it, so those three members now
share **one** deterministic typed-scalar policy (issues #1403 / #1405).

**Remaining non-conformant member:** the selective-disclosure witness signers
(`selective_disclosure.py`) still use `default=str`. They are a distinct
cross-SDK signing contract with their own fixtures and rust counterpart;
unifying them is a separate same-class follow-up (out of the #1400-#1407 scope),
tracked so the family is not silently assumed fully unified.

## Cross-SDK note

Both families are documented cross-SDK byte contracts (kailash-rs#449). Any
change to a Family-B canonical byte (the audit-chain timestamp/metadata format,
the trace-event fingerprint) is a **breaking cross-SDK change**: the kailash-rs
counterpart must land identical changes in lockstep and the vendored fixtures
(`test-vectors/*-canonical.json`) re-vendored, or the SDKs produce divergent
bytes for the same logical input. See `rules/cross-sdk-inspection.md` Rule 4 +
`test-vectors/README.md`.
