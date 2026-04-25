# Issue #604 — Signed-Record Site Inventory

Inventory of every signed-record producer / verifier site in `src/kailash/trust/` and
`packages/kailash-pact/` that the `AlgorithmIdentifier` scaffold (PR `8cbb57ed`) must
thread through.

Cross-SDK sibling: `esperie/kailash-rs#33`. Wire format: pending mint ISS-31. Until then,
all producers emit `algorithm = "ed25519+sha256"` (the constant `ALGORITHM_DEFAULT`).

## Contract

- **Producers** — record `alg_id.algorithm` in their signed-record output dict / dataclass.
- **Verifiers** — extract `algorithm`; missing → default to `ALGORITHM_DEFAULT` AND emit
  one-time `DeprecationWarning` per process containing the literal text
  `"scaffold for #604; wire format pending mint ISS-31"`. Present and non-default → raise
  (only `"ed25519+sha256"` supported today).
- **Storage dataclasses** — gain an `algorithm: str = ALGORITHM_DEFAULT` field; emit
  `"algorithm": "ed25519+sha256"` on every JSON serialisation.
- **Cryptographic comparison** — UNCHANGED. `hmac.compare_digest()` is the comparison
  primitive (per `rules/eatp.md` § Cryptography); threading `alg_id` adds the metadata
  field to the surrounding shape, NOT the verification primitive.

## Layered surface map

The threading is bounded by a small set of canonical producer/verifier primitives. Every
downstream caller routes through one of these — once the primitives + storage dataclasses
carry `algorithm`, downstream call sites get the field as a side effect of round-tripping
the signed record, with NO API surface change.

### Layer 0 — Cryptographic primitives (canonical)

| File | Producer | Verifier | Storage record? |
| ---- | -------- | -------- | --------------- |
| `src/kailash/trust/signing/crypto.py` | `sign(payload, private_key) -> str` line 120 | `verify_signature(payload, signature, public_key) -> bool` line 168 | No (returns raw signature string) |

**Disposition:** Layer 0 primitives DELIBERATELY DO NOT thread `alg_id` — they return /
consume a raw signature string and have no signed-record envelope. The algorithm metadata
is recorded by the caller's wrapping dataclass (Layer 1). Adding `alg_id` to `sign()` /
`verify_signature()` would force every downstream call site to pass it through — but
those call sites already record `algorithm` at the Layer 1 envelope they construct.

This is the rule-2 "single filter point at the emitter" pattern from
`rules/event-payload-classification.md` MUST Rule 1: the algorithm field is recorded once,
in the wrapping signed-record dataclass, NOT at every primitive site.

### Layer 1 — Canonical signed-record dataclasses + sign/verify pairs

| File | Storage dataclass | Producer | Verifier |
| ---- | ----------------- | -------- | -------- |
| `src/kailash/trust/envelope.py` | `ConstraintEnvelope` (signature returned separately as hex string; HMAC, NOT signed-record) | `sign_envelope(envelope, secret_ref)` line 1378 | `verify_envelope(envelope, signature, secret_ref)` line 1399 |
| `src/kailash/trust/pact/envelopes.py` | `SignedEnvelope` (frozen dataclass, lines ~1170–1318) | `sign_envelope(envelope, private_key, signed_by, ...) -> SignedEnvelope` line 1321 | `SignedEnvelope.verify(self, public_key) -> bool` line 1204 |
| `src/kailash/trust/signing/timestamping.py` | `TimestampResponse` / `TimestampToken` (signed) | `RFC3161TimestampManager.create_anchor`, `_sign_token` | `RFC3161TimestampManager.verify_anchor` line 844, `_verify_token_signature` line 485 |
| `src/kailash/trust/signing/crl.py` | `CRLMetadata` (signed) | `CRLMetadata.sign(self, private_key)` line 490 | `CRLMetadata.verify_signature(self, public_key)` line 511 |
| `src/kailash/trust/messaging/signer.py` + `messaging/verifier.py` | `MessageEnvelope` (signed) | `MessageSigner.sign_message(...)` line 89 | `MessageVerifier._verify_signature(...)` line 330 |

These five Layer-1 primitive pairs are where the `algorithm` metadata MUST be recorded.

### Layer 2 — Audit + chain stores (built atop Layer 1)

| File | Storage dataclass | Sign path | Verify path |
| ---- | ----------------- | --------- | ----------- |
| `src/kailash/trust/audit_store.py` | `AuditEntry` / `AuditChainEntry` (HMAC chain) | `_compute_entry_hmac` (internal) | `verify_record(record_id)` line 1218 |
| `src/kailash/trust/audit_service.py` | wraps `audit_store` | (delegate) | (delegate) |
| `src/kailash/trust/chain_store/` | chain anchor records | (delegate to Layer 1) | (delegate to Layer 1) |
| `src/kailash/trust/chain.py` | (HMAC chain helpers) | (delegate) | (delegate) |
| `src/kailash/trust/key_manager.py` | key-rotation records | line 47 imports `verify_signature` | line 394 calls `verify_signature` |

Layer 2 stores routes through Layer 1 producers/verifiers — they receive the threading
for free as long as the Layer 1 storage dataclass round-trips `algorithm`.

### Layer 3 — Higher-level signed-record consumers (raw `verify_signature` callers)

These call `verify_signature(payload, signature, public_key)` directly against
already-extracted records. Per Layer 0 disposition, they do NOT thread `alg_id` because
they are not the storage / round-trip surface. The `algorithm` field is on the surrounding
record they extract from.

| File | Lines | Role |
| ---- | ----- | ---- |
| `src/kailash/trust/signing/multi_sig.py` | 384, 386, 568 | multi-signature aggregation; verifies each sub-signature |
| `src/kailash/trust/cli/commands.py` | 775, 1312, 1318, 1324 | CLI verification of trust chain genesis / capability / delegation |
| `src/kailash/trust/operations/__init__.py` | 173, 774, 829, 1150 | trust chain integrity checks |
| `src/kailash/trust/interop/biscuit.py` | 432, 585, 595 | Biscuit token verification |
| `src/kailash/trust/interop/w3c_vc.py` | 422 | W3C Verifiable Credentials |
| `src/kailash/trust/enforce/challenge.py` | 428 | challenge-response verification |
| `src/kailash/trust/enforce/selective_disclosure.py` | 389 | selective disclosure verification |
| `src/kailash/trust/messaging/verifier.py` | 348 | (see Layer 1; this is the call inside `_verify_signature`) |
| `src/kailash/trust/a2a/auth.py` | 262 | A2A message authentication |
| `src/kailash/trust/plane/bundle.py` | 341 | bundle verification |

### Layer 4 — KMS sign() façades (alg_id is owned by the cloud KMS, not us)

| File | Note |
| ---- | ---- |
| `src/kailash/trust/plane/key_managers/azure_keyvault.py` | `def sign(self, data: bytes) -> bytes` line 100 |
| `src/kailash/trust/plane/key_managers/aws_kms.py` | `def sign(self, data: bytes) -> bytes` line 87 (uses ECDSA P-256, NOT Ed25519 — see eatp.md) |
| `src/kailash/trust/plane/key_managers/vault.py` | `def sign(self, data: bytes) -> bytes` line 95 |
| `src/kailash/trust/plane/key_managers/manager.py` | abstract `sign` line 61, 135 |

KMS façades emit raw bytes; algorithm metadata is provider-determined and out of scope
for the `AlgorithmIdentifier` scaffold. Threaded ONLY where the result is wrapped in a
Layer 1 record (e.g. `audit_store` HMAC chain — but those use the local `crypto.py`
primitives, not the KMS sign).

### kailash-pact package

`packages/kailash-pact/src/pact/governance/`:

- `__init__.py` / `cli.py` / `results.py` / `testing.py` / `api/` — none of these are
  signed-record producers/verifiers. PACT governance verdicts are stored via EATP audit
  trail through Layer 2, NOT a separate signed-record surface here.
- `pact.SignedEnvelope` / `pact.sign_envelope` / `pact.verify_envelope` re-exports the
  Layer 1 `kailash.trust.pact.envelopes` symbols (already in scope above).

No additional pact-package threading required.

## Threading scope for this PR

Per `rules/security.md` § Multi-Site Kwarg Plumbing + `rules/autonomous-execution.md`
§ shard budget, the threading MUST land in this PR for every helper site OR a future
refactor that grows toward the un-threaded shape silently re-opens the bug class.

**Ship in this PR (single shard, in-budget):**

1. Layer 1 storage dataclasses gain `algorithm: str = ALGORITHM_DEFAULT` field with
   `to_dict`/`from_dict` round-trip:
   - `SignedEnvelope` in `src/kailash/trust/pact/envelopes.py`
   - `TimestampToken` / `TimestampResponse` in `src/kailash/trust/signing/timestamping.py`
   - `CRLMetadata` in `src/kailash/trust/signing/crl.py`
   - `MessageEnvelope` in `src/kailash/trust/messaging/envelope.py` (or wherever the
     dataclass lives)
2. Layer 1 producers gain `alg_id: Optional[AlgorithmIdentifier] = None` parameter and
   record `alg_id.algorithm` in the storage dataclass:
   - `pact.envelopes.sign_envelope`
   - `RFC3161TimestampManager.create_anchor`
   - `CRLMetadata.sign`
   - `MessageSigner.sign_message`
3. Layer 1 verifiers extract `algorithm` from the storage dataclass; missing → default +
   one-time `DeprecationWarning`; non-default → raise `NotImplementedError` (the only
   permitted scaffold-era stub from `8cbb57ed`):
   - `SignedEnvelope.verify`
   - `RFC3161TimestampManager.verify_anchor`
   - `CRLMetadata.verify_signature`
   - `MessageVerifier._verify_signature`
4. `__init__.py` exports of the scaffold symbols
   (`AlgorithmIdentifier`, `ALGORITHM_DEFAULT`, `coerce_algorithm_id`).
5. Tier 1 + Tier 2 regression tests (round-trip default, non-default raises, legacy
   record warns).
6. Spec updates: `specs/trust-crypto.md`, `specs/trust-eatp.md`.

**Layer 0, Layer 3, Layer 4 — explicitly NOT threaded:**

- Layer 0 (`crypto.sign` / `crypto.verify_signature`) — return raw signatures, the
  algorithm field is recorded at Layer 1 by the caller's wrapping dataclass. Threading
  Layer 0 forces 14+ Layer-3 sites to update with no security value (the algorithm field
  is recorded in the surrounding record, not the bare signature).
- Layer 3 (cli / interop / multi-sig / etc.) — call `verify_signature(payload, sig, pub)`
  with already-extracted signature triplets. The `algorithm` field is on the SURROUNDING
  record they extract from (Layer 1 dataclass round-trip handles it). Adding `alg_id` here
  would duplicate the field at the call-site without changing wire format.
- Layer 4 KMS — provider-determined algorithm, out of scope.

## Why this scope is correct

`rules/event-payload-classification.md` MUST Rule 1 — "single filter point at the emitter"
— is the structural defence against drift. Layer 1 IS the emitter for signed records.
Recording `algorithm` at Layer 1 means every Layer 2/3 caller round-trips the field as a
field on the dataclass they already round-trip; no Layer 3 caller needs a code change.
Threading at every Layer 3 call site would violate the same rule by placing the field at
14+ caller sites instead of one emitter.

Future drift scenario — when mint ISS-31 stabilises and `ed25519+sha512` becomes
permitted: only the Layer 1 storage dataclasses' `__post_init__` validation + the
canonical serialiser change. Layer 0/3/4 do not need re-threading because the field
already round-trips through Layer 1 as part of the storage shape.

## Cross-SDK alignment

Cross-SDK with `esperie/kailash-rs#33`. Field shape MUST be identical:
- JSON key: `"algorithm"`
- Default value: `"ed25519+sha256"`
- Lexicographic JSON key ordering preserved (already the case via `serialize_for_signing`
  in `crypto.py` line 261)

Snake_case differences between Python (`alg_id`) and Rust (`alg_id`) parameter names are
acceptable per `rules/eatp.md` § Cross-SDK Alignment.

## Origin / references

- Issue: `terrene-foundation/kailash-py#604`
- Cross-SDK sibling: `esperie/kailash-rs#33`
- Scaffold commit: `8cbb57ed` (this branch)
- Related rules: `security.md` § Multi-Site Kwarg Plumbing,
  `event-payload-classification.md` MUST Rule 1, `eatp.md` § Cryptography,
  `zero-tolerance.md` Rule 2 (the `__post_init__` `NotImplementedError` is the single
  permitted scaffold-era stub).
