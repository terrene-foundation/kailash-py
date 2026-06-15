# 01 — Parallel brief-claim verification (4 independent deep-dive agents)

Per `rules/agents.md` § "Parallel Brief-Claim Verification When Issue Count ≥ 3". Four
agents, four claim clusters, one wall-clock unit. All citations re-derived from source.

## Cluster 1 — D2c marker store (call-site map + crypto reuse)

- **CONFIRMED**: `D2dWitness` (`algorithm_id.py:168-220`) is a frozen 3-field value object
  (`witnessed_at`, `chain_head_date`, `principal`); no signature, no `first_seen`, no
  `marker_sig`. Docstring `:188-192` "signed-not-remembered" is aspirational, not code.
- **CONFIRMED**: `assert_d2d_witness_pre_adoption` (`:223-257`) has exactly 2 raise paths
  (`witness is None` :241; `not is_pre_adoption()` :249) — both `implicit-v1-witness-failure`.
  No unverifiable/expired/non-corroborating branch.
- **CONFIRMED**: zero `marker_sig`/`first_seen`/`MarkerStore` in `src/kailash/trust/`.
- **Blast radius (mechanical for callers)**: NO production code constructs a `D2dWitness`
  (0 src hits; 3 test constructions only). The marker-population path is greenfield. 5
  wire-decode consumers forward `witness=witness` unchanged:
  `timestamping.py:162`, `timestamping.py:269`, `crl.py:182`, `messaging/envelope.py:300`,
  `pact/envelopes.py:1376`. Behavioral change is contained in `D2dWitness` +
  `assert_d2d_witness_pre_adoption`.
- **Crypto reuse (ready)**: `kailash.trust.signing.crypto` — `verify_signature(payload, sig,
pubkey)` (`crypto.py:170`), `sign(...)` (`:122`), `serialize_for_signing(obj)` (`:225`,
  the JCS canonical pre-image builder, `sort_keys`+`separators=(",",":")`+`allow_nan=False`).
  Marker signs `serialize_for_signing({principal, first_seen, chain_head_date})`.
- **Trusted-verifier-key config — MUST BE ADDED (inference, not existing)**: no
  `trusted_verifier_key` in the trust layer. Closest pattern: `MultiSigPolicy.signer_public_keys:
Dict[str,str]` (`multi_sig.py:170`) iterated by `verify_multi_sig` (`:493`). Recommend
  resolving the trusted key INSIDE the gate from module/instance config — NOT threading it
  through `decode_wire_alg_id` — keeping call-graph ≤3 hops and the 5 consumer signatures
  untouched.
- **Insertion point**: extend `assert_d2d_witness_pre_adoption` in place (single chokepoint
  both D2d branches `:487`/`:610` call; already raises the §4.3.2 code). 2 checks → 5.
- **Invariant count CONFIRMED ~5**: sig-verify · first_seen-corroboration · expiry ·
  monotonic-boundary · fail-closed. `D2dWitness` also needs `first_seen` + `marker_sig` +
  an expiry/TTL field (none exists today).

## Cluster 2 — V6/V7 vectors + monotonic enforcement (BRIEF CORRECTION)

- **CONFIRMED**: vector file has no V6/V7/strip/marker entries. Schema = 3 sibling
  collections (`registry[]` byte-pins: `token`/`status`/`dispatchable`/`canonical_member`/
  `expected_sha256`; `non_conformant[]` decode-regime: `name`/`value_repr`/`shape`/
  `decode_post_adoption`/`decode_with_pre_adoption_witness`/`reason`). **No
  `conformance_level` field** — V6/V7 need a new `level` field added to the schema.
- **CORRECTION — `monotonic-upgrade-violation` is NOT implemented**. Only a forward-reference
  docstring at `algorithm_id.py:197-198` ("enforced by the record consumer, not this temporal
  gate"). The enforcer does NOT exist anywhere in `src/`. V6 sub-case (i) (prior-v2 →
  `monotonic-upgrade-violation`) is therefore NOT "author a vector" — it requires
  IMPLEMENTING the enforcer (new load-bearing code, record-consumer layer, cross-file).
  Sub-cases (ii) `missing-alg-id-post-adoption` and (iii) `implicit-v1-witness-failure` are
  already enforced in `algorithm_id.py` (`:505-506`/`:623-624`, `:242-243`/`:250-251`) and
  immediately testable.
- Decode-regime tests are hand-written (not data-driven), assert `exc.value.code ==
"<code>"`. `test_issue_604_alg_id_threading.py` already has executable analogues of V6 (ii)
  - (iii) through the `SignedEnvelope.from_dict` surface, with `_PRE_ADOPTION_WITNESS` /
    `_POST_ADOPTION_WITNESS` fixtures.

## Cluster 3 — Compatible-Legacy logging §7.1 (BRIEF CORRECTION)

- **CORRECTION — logging is NOT greenfield (brief claim FALSE)**. Two `logger.info`
  D2d-acceptance lines already ship: `algorithm_id.py:488-498` (nested-object form) and
  `:611-621` (unsigned-`algorithm` form). Both carry `witnessed_at`/`chain_head_date`/
  `ADOPTION_DATE` and fire on successful acceptance.
- §7.1 work reduces to: (a) INFO→WARN decision (a D2d acceptance is a degraded/fallback
  path → `observability.md` Rule 3 argues WARN); (b) optionally consolidate the two into one
  helper for uniform level/fields; (c) guard that `principal`/chain-head id is NOT logged at
  raw severity (`observability.md` Rule 8 — DEBUG or sha256[:8]). Currently `principal` is
  NOT logged (safe today); preserve that.
- Module logger present (`algorithm_id.py:51`); printf-lazy style (compliant). Note
  `messaging/envelope.py` has no module logger (irrelevant — it routes through the primitive).

## Cluster 4 — Cross-SDK parity (BRIEF CORRECTION — direction inverted)

- **CORRECTION — kailash-py is the CANONICAL AUTHOR, not the vendoring consumer**.
  `eatp08-alg-id-canonical.json:7`: "kailash-py is the canonical AUTHOR … kailash-rs VENDORS
  this file byte-for-byte (#1315)". So V6/V7 byte values (`canonical_member`,
  `expected_sha256`) are DERIVED HERE deterministically via `serialize_for_signing(
AlgorithmIdentifier(algorithm=token).to_dict())` + sha256 — NOT coordinated with rs.
  **No upstream byte-value dependency blocks the py work.**
- Parity assertion is byte-pinned (Rule-4 compliant): `test_eatp08_alg_id_canonical_vectors.py`
  re-derives `canonical_member` + `expected_sha256` per registry row and asserts equality;
  `test_vectors_file_loads_and_pins_the_active_default` asserts vector-set == `ALGORITHM_REGISTRY`
  (so a new token without a vector row fails loudly).
- Canonicalization helper: `serialize_for_signing` (`crypto.py:225`, `ensure_ascii=True` →
  ASCII-escaped, load-bearing for rs serde_json parity). Distinct from the delegate-family
  `kailash.trust._json.canonical_json_dumps` (`ensure_ascii=False`, issue #1258) — alg-id
  vectors use the signing family. Alg-id tokens are ASCII so the distinction is moot for
  these bytes, but use the signing-family helper.
- **Handoff boundary**: full V6/V7 authoring is doable here (registry + vectors + byte-pins).
  The only cross-repo step is the downstream rs vendor-pull, which happens in the rs sibling
  session — py → rs, not a blocker.
