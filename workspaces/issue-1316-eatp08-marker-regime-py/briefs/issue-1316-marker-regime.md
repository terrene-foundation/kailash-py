# Brief: #1316 — EATP-08 ISS-32 marker-regime tail (D2c + V6/V7 + Compatible-Legacy logging)

**Source issue**: `terrene-foundation/kailash-py#1316` (OPEN) — "[conformance] EATP-08 ISS-32
— D2b/D2c/D2d marker regime + bare-literal reject (spec-referenced tracker)".

**Spec anchor**: `foundation/docs/02-standards/eatp/08-algorithm-identifier.md@v1.1.1`
§4.5/§4.6/§5.1/§7.1, vectors V6/V7/V9. Foundation erratum PR #17; ruling mint PR #27
(resolves `terrene-foundation/mint#26`).

**Value anchor** (user-stated, this session): the only open actionable py-side item;
HIGH, spec-anchored. Delivers EATP-08 §4 backward-compat conformance + cross-SDK parity
with `esperie-enterprise/kailash-rs` ISS-33. Approved scope-first then `/analyze` by the
user 2026-06-15.

## Already shipped (do NOT redo)

- **E6** silent default-fill removed (#1304 / merged #1309): `from_dict` no longer
  default-fills a missing/empty `alg_id`; post-adoption missing raises
  `missing-alg-id-post-adoption` (D2b).
- **D2d dated/witnessed gate**: `D2dWitness`, `assert_d2d_witness_pre_adoption`,
  `ADOPTION_DATE = 2026-04-26` — pre-registry explicit form accepted as `eatp-v1` only with
  a witness dated strictly before adoption.
- **Bare-literal reject** (v1.1.1 / mint#26, PR #1315): bare top-level-string
  `alg_id:"ed25519+sha256"` → `unsupported-algorithm`, not D2d.

## Outstanding tail (this workstream)

1. **D2c signed-marker store** (§4.3.1 / §4.3.2). `D2dWitness` today is a TRUSTED passed-in
   value (`witnessed_at`, `chain_head_date`, `principal`); D2c requires the witnessed
   `{principal, first_seen, marker_sig}` marker to be **signed-not-remembered** (verifier
   key / transparency log / Foundation witness service) AND the §4.3.2 detection rule:
   `implicit-v1-witness-failure` when the marker is missing / expired / unverifiable OR does
   not corroborate the claimed pre-adoption head date.
2. **V6 (alg-id-strip-attack)** executable vector — three sub-cases: prior-v2 →
   `monotonic-upgrade-violation`; fresh post-adoption → `missing-alg-id-post-adoption`;
   fresh attacker-chosen-pre-adoption-date → `implicit-v1-witness-failure`.
3. **V7 (witnessed-adoption-marker, Complete level)** — local-marker-tamper detection via
   the signed marker.
4. **Compatible-Legacy logging** (§7.1) — log every D2a/D2d acceptance for migration
   tracking until the marker store + adoption-date gate fully ship.

## Acceptance (from issue)

- All §4.2/§4.3/§4.5 normative requirements implemented; V4–V7 + V9 pass at stated
  conformance levels.
- Cross-SDK byte/behavior parity with `esperie-enterprise/kailash-rs` (ISS-33 / #1315) on the
  alg-id-canonical vectors, incl. the v1.1.1 bare-literal negative sub-case.

## Code-state findings (this session, evidence)

- `src/kailash/trust/signing/algorithm_id.py:169` — `D2dWitness` value object; `:209`
  `is_pre_adoption()` (both dates `< ADOPTION_DATE`). Docstring `:190` claims
  "signed-not-remembered" but NO signature is verified anywhere.
- `:223` `assert_d2d_witness_pre_adoption()` raises `implicit-v1-witness-failure` only on
  missing-or-post-adoption — NOT on unverifiable/expired/non-corroborating marker.
- Greenfield: zero `marker_sig` / `first_seen` / `MarkerStore` in `src/kailash/trust/`.
  `principal` field exists but is "informational".
- `tests/test-vectors/eatp08-alg-id-canonical.json` (81 lines) — NO V6/V7/strip/marker
  vectors; must be authored fresh and byte-matched to kailash-rs.
- Existing crypto layer: `kailash.trust.signing` (Ed25519 mandatory per `rules/eatp.md`).

## Recommended design decision (to confirm at /analyze against spec)

**(a) Verifier-key signed marker** — Ed25519 signature over `{principal, first_seen,
chain_head_date}`, verified against a configured trusted verifier key; self-contained, no
external infra, full cross-SDK byte parity. (b) transparency log and (c) Foundation witness
service require external infrastructure whose existence is UNVERIFIED — do not scope (b)/(c)
until a live existence check confirms the endpoint. (a) is not a one-way door: (b)/(c) can
later become the marker _source_ without changing the verification contract.

## Boundaries

- **Cross-SDK parity is half-out-of-repo**: kailash-rs ISS-33 lives in
  `esperie-enterprise/kailash-rs` — NOT touchable from this session (repo-scope-discipline).
  Parity is achieved here by authoring the canonical vector file to match; rs-side landing is
  a separate session in that repo.
- **Spec not local**: `08-algorithm-identifier.md` §4.3.1/§4.3.2 is not in this repo. The
  issue body quotes the marker shape (`{principal, first_seen, marker_sig}`) + the §4.3.2
  detection predicate; lock shard-1's exact field shape against the spec text before
  implementing.
