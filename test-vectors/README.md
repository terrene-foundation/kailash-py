<!--
Copyright 2026 Terrene Foundation
SPDX-License-Identifier: Apache-2.0
-->

# Canonical cross-SDK test vectors

These JSON fixtures pin the **byte-level canonical contracts** that kailash-py
and kailash-rs must both reproduce for the same logical input. They are the
ground truth for cross-implementation hash / fingerprint parity.

Regenerate the audit-chain + trace-event fixtures from the production canonical
path (never by hand):

```bash
.venv/bin/python test-vectors/regenerate_canonical_vectors.py
```

A non-empty diff after regeneration means a production canonical byte changed —
review it as a **cross-SDK byte-contract change** (coordinate the kailash-rs
side in lockstep; see § Cross-impl enforcement).

## Fixture index

| Fixture                      | Contract                                           | Producer                                        | Cross-impl enforcement (this repo)                                                                       |
| ---------------------------- | -------------------------------------------------- | ----------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `audit-chain-canonical.json` | `AuditAnchor.compute_hash` (kailash-rs#449 §2)     | `AuditAnchor._canonical_input` / `compute_hash` | **Python self-consistent** — rs digest verified at the post-Wave-6 cross-SDK gate, NOT in this repo's CI |
| `trace-event-canonical.json` | `compute_trace_event_fingerprint` (kailash-rs#449) | `protocols._canonical_json` / fingerprint       | **Python self-consistent** — as above                                                                    |

The fixtures under `../tests/test-vectors/` (`trust-plane-canonical.json`,
`eatp12-vault-canonical.json`, `eatp08-alg-id-canonical.json`,
`delegate-canonical.json`) belong to the signing / vault / delegate families;
each carries its own provenance (a `provenance` block, or producer/vendor prose
in its `description`). The cross-implementation enforcement status of every
canonical contract (in-repo byte-pin vs deferred to an external gate) is indexed
in `specs/trust-canonical-encoders.md` § "Cross-implementation enforcement
status".

## Cross-impl enforcement — honest status

Each fixture carries a `provenance` block naming the **producer** and a
`cross_impl_status`. Today every `expected_*` value is **reproduced by the
Python production path** (`cross_impl_status: "python-self-consistent"`): the
in-repo tests prove _Python agrees with Python_, which catches a Python-side
regression but does **not** by itself prove an independent kailash-rs
implementation produces the same bytes. The independent rust digest is verified
at the **post-Wave-6 cross-SDK gate** (out of this repo's CI), as the
`provenance.cross_impl_note` records on each fixture.

To upgrade a fixture from `python-self-consistent` to in-repo cross-impl
enforcement, vendor the independently-produced golden from kailash-rs (per
`rules/cross-sdk-inspection.md` Rule 4a — same file, same bytes) and set
`cross_impl_status: "vendored-from-kailash-rs"`, so a divergence on the **rust**
side fails CI here too.

> The historical claim that these fixtures enforced "byte-for-byte equality
> between SDKs" was overstated — they enforce Python self-consistency plus the
> external gate (issue #1402). The wording in the test docstrings + this index
> reflects the accurate scope.

## Typed-scalar `__pytype__` convention

Vectors that exercise typed-scalar metadata / payload (audit `U5`, trace `V6`)
carry their non-JSON-native values under a `__pytype__` tag so the fixture stays
valid JSON yet round-trips to real Python objects (and a sibling SDK loader
implements the same inverse). The codec is the single source of truth in
`regenerate_canonical_vectors.py` (`encode_typed` / `decode_typed`):

| Python type | Fixture encoding                                  |
| ----------- | ------------------------------------------------- |
| `Decimal`   | `{"__pytype__": "Decimal", "repr": "1.50"}`       |
| `UUID`      | `{"__pytype__": "UUID", "repr": "<8-4-4-4-12>"}`  |
| `datetime`  | `{"__pytype__": "datetime", "repr": "<iso8601>"}` |
| `set`       | `{"__pytype__": "set", "items": [ ... ]}`         |
| `bytes`     | `{"__pytype__": "bytes", "b64": "<base64>"}`      |

These values route through `kailash.trust._canonical.canonical_scalars` in
production — never `default=str` (issues #1403 / #1405).
