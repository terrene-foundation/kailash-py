---
priority: 10
scope: path-scoped
paths:
  - "**/src/**"
  - "**/tests/**"
---

# Cross-SDK Issue Inspection

See `.claude/guides/rule-extracts/cross-sdk-inspection.md` for the full DO/DO-NOT code examples, the per-rule BLOCKED-rationalization corpora, and the extended evidence + standalone Origins for Rules 3a–6.

## Scope

These rules apply to ALL bug fixes, feature implementations, and issue resolutions in BOTH BUILD repos (the Rust SDK and kailash-py).

## MUST Rules

### 1. Cross-SDK Inspection on Every Issue

When an issue is found or fixed in ONE BUILD repo, you MUST inspect the OTHER BUILD repo for the same or equivalent issue — in BOTH directions: does the sibling SDK have the same bug, OR need the equivalent feature? File a cross-SDK GitHub issue on the sibling repo if relevant — kailash-py at `terrene-foundation/kailash-py`, the Rust SDK by resolver key `build.rs` (resolve the real org/repo via the gitignored `loom-links.local.json` per `cross-repo.md` MUST-1).

**Why:** Bugs in shared architecture (trust plane, DataFlow, Nexus) almost always exist in both SDKs — fixing only one leaves users of the other SDK hitting the same issue.

### 2. Cross-Reference in Issues

When filing a cross-SDK issue, MUST include:

- Link to the originating issue in the other repo
- Tag: `cross-sdk` label
- Note: "Cross-SDK alignment: this is the [Rust/Python] equivalent of [link]"

**Why:** Without cross-references, the same bug gets fixed independently with different approaches, causing semantic divergence between SDKs that violates EATP D6.

### 3. EATP D6 Compliance

Per EATP SDK conventions (D6: independent implementation, matching semantics):

- Both SDKs implement features independently
- Semantics MUST match (same API shape, same behavior)
- Implementation details may differ (Rust idioms vs Python idioms)

**Why:** Semantic divergence between SDKs means code ported from Python to Rust (or vice versa) silently changes behavior, breaking user trust in the platform's cross-language promise.

### 3a. Structural API-Divergence Disposition

When the sibling SDK reports a bug at an API surface this SDK does NOT expose (e.g., the Rust `execute_raw(sql, params)` bug class requires a `params` arg that the Python `execute_raw(sql)` doesn't have), the disposition MUST include BOTH:

1. **A Tier 2 test through the sibling path that DOES bind parameters** — the bug class may still manifest at a different API surface in this SDK (e.g., Express `bulk_create`, `update`, `upsert`).
2. **A structural invariant test that pins the signature** — asserts the API signature that prevents the bug class from existing at this surface. If a future refactor grows the signature to match the sibling shape, the invariant test fails loudly and forces a re-audit.

```python
# DO — BOTH: (1) a Tier 2 test through the sibling parameter-binding path
#      (e.g. Express bulk_create); (2) a signature-invariant test pinning the
#      absent arg (assert execute_raw takes only `sql`). Full pair + BLOCKED corpus in the guide.
# DO NOT — close the cross-SDK issue with a hand-waving comment (no test, no
#      invariant; a future refactor silently reopens the bug class).
```

**Why:** "Our signature doesn't have the arg" is true today and false the day someone ports a convenience method from the sibling SDK; the structural invariant test makes the signature itself part of the contract. See guide for the full test pair, BLOCKED corpus, and #525 / PR #528 evidence.

### 4. Cross-SDK Hash / Fingerprint Helpers MUST Pin Byte Vectors From Sibling SDK

Any helper that claims byte-shape parity with a sibling SDK (cross-SDK fingerprint, hash, mask, audit-chain digest, log-correlation token) MUST pin AT LEAST 3 byte-vector test cases empirically derived from the sibling SDK's actual output AND cover sentinel values (empty input, all-zero, all-one, single-byte). The byte vectors live in the cross-SDK regression test as raw hex strings, NOT abstract assertions like "same length" or "starts with sha256:".

```python
# DO — pin ≥3 real sibling-SDK byte vectors + sentinels (empty/all-zero/single-byte)
#      as raw hex: assert fingerprint_secret(raw) == expected for each. Full example in the guide.
# DO NOT — abstract parity claim (assert len==4 and all-hex) — proves shape, not bytes.
```

**Why:** Cross-SDK forensic correlation depends on identical byte output for identical input; a "same length, same prefix" assertion passes when one side is `Blake2bMac<U4>` (MAC) and the other `Blake2bVar(4)` (digest) — lengths agree, bytes don't. See guide for the empty-input divergence, BLOCKED corpus, and PR #598 evidence.

### Rule 4a: Sibling-Canonical Fixtures MUST Be Vendored, Not Re-Authored

When the sibling SDK is the canonical author of a cross-SDK fixture file (test vectors, byte-pin canonicals, conformance JSON), the local SDK's test directory MUST vendor the canonical file (commit the same bytes) — NOT maintain a parallel hand-authored copy. Local consumers (Rust loaders, Python binding tests, pin-gen reproducibility scripts) MUST be updated to read the canonical shape in the same PR. Orphaned consumers reading the old shape are a Rule 4 (orphan-detection) violation.

```
# DO — vendor the canonical file from the sibling repo (cp the fixture; update every
#      local consumer to the canonical shape in the SAME PR). Full example in the guide.
# DO NOT — maintain a parallel hand-authored copy (shape drifts: id/input vs name/input_repr;
#      fingerprints match for some vectors, silently break for others).
```

**Why:** Parallel copies drift in shape AND content; vendoring guarantees byte-for-byte file-level parity, and orphaned consumers reading the old shape fail loudly at first CI run. See guide for the BLOCKED corpus and PR #761 evidence.

### 4b. Byte-CHANGING Canonical-Encoder Switches Are Cross-SDK Lockstep, Not Single-SDK

When migrating a canonical-encoder / serialization helper that feeds a cross-SDK signing or hash pre-image (e.g. `json.dumps(..., default=str)` → a stricter `canonical_scalars`), you MUST first classify the switch as **byte-NEUTRAL** or **byte-CHANGING** by EMPIRICALLY byte-diffing production output on fixed inputs — NOT by reasoning about it. A byte-CHANGING switch where the sibling SDK mirrors this SDK's CURRENT bytes MUST NOT ship single-SDK; it is a coordinated cross-SDK lockstep (one re-pin event in both repos) and the current bytes MUST be pinned in a regression test as a loud tripwire until the lockstep lands. A byte-NEUTRAL switch (the normalization layer already pre-normalizes every divergent type, so the swap changes zero currently-emitted bytes) MAY ship single-SDK.

```python
# DO — empirically byte-diff, classify, then pin CURRENT bytes for a byte-CHANGING signing
#      site as a tripwire until the sibling-SDK lockstep lands. Full example in the guide.
# DO NOT — switch a byte-CHANGING signing encoder single-SDK (silently diverges every
#      on-disk signed artifact from the sibling's bytes; break surfaces only at a prod verify).
```

**Why:** A canonical signing encoder is a byte-for-byte cross-SDK contract (Rule 4); switching it single-SDK silently diverges every artifact the sibling must re-verify. Empirical byte-diff is the only sound classifier — reasoning about type-equivalence is exactly how the audit-chain / witness-family / envelope-HMAC sites were each almost switched single-SDK. See guide for the BLOCKED corpus + evidence.

**Trust Posture Wiring (byte-changing cross-SDK lockstep):**

- **Severity:** `halt-and-report` at gate-review (reviewer + security-reviewer at `/implement` confirm any canonical-encoder switch on a signing/hash site is classified byte-neutral-vs-byte-changing with an empirical byte-diff, and byte-changing switches carry a pinned-bytes tripwire + cross-SDK issue); `advisory` at hook layer.
- **Grace period:** 7 days from rule landing.
- **Cumulative posture impact:** same-class violations (a byte-changing canonical switch shipped single-SDK, or unclassified) contribute per `trust-posture.md` MUST-4 (3× same-rule / 5× total in 30d → drop 1 posture).
- **Regression-within-grace:** trigger key `cross_sdk_canonical_single_sdk_switch` fires emergency downgrade (1 step) per `trust-posture.md` MUST-4.
- **Receipt requirement:** SessionStart `[ack: cross-sdk-inspection]` IFF `posture.json::pending_verification` includes this rule_id (soft-gate).
- **Detection mechanism:** Phase 1 — gate-level reviewer at `/implement`: for any diff touching a canonical-encoder/serialization helper on a signing/hash path, demand the empirical byte-diff classification + (for byte-changing) the pinned-current-bytes regression test + the cross-SDK lockstep issue. Phase 2 (deferred): a regression-suite invariant enumerating signing-site encoders and asserting each pinned.
- **Violation scope:** this clause (canonical-encoder switches on cross-SDK signing/hash pre-images). Every violation row names the encoder site + the missing classification or tripwire.
- **Origin:** kailash 2.43.1 cross-SDK canonical-encoder family sweep (2026-06-20) — byte-diff classification of 97 `default=str` sites: audit-chain + witness-family + envelope-HMAC byte-CHANGING/lockstep, envelope_hash byte-NEUTRAL/shipped; `specs/trust-canonical-encoders.md`.

### 4c. Conformance-Vector Changes Re-Pin Their Integrity Manifest In The Same Commit

When a commit changes a cross-SDK conformance vector / test-fixture file pinned by a committed integrity manifest (`*.sha256`, e.g. `PACT_VECTORS.sha256`), the manifest MUST be re-pinned in the SAME commit. A `/redteam` over any canonical-vector change MUST include an **integrity-manifest sweep** lens: enumerate every `*.sha256` and run `shasum -a256 -c` on each.

```bash
# DO — re-pin the manifest in the SAME commit that changes the vector; run `shasum -a256 -c`
#      green before push. Full example in the guide.
# DO NOT — change the vector, leave the manifest stale (reds the remote integrity gate; a
#      "converged" redteam that never ran shasum -c declares clean over a red CI gate).
```

**Why:** An integrity manifest exists to make silent tampering of a pinned vector loud; a vector change that omits the re-pin either reds the CI gate or silently no-ops the check until a future real tamper goes undetected. See guide for the BLOCKED corpus + PR #1411 evidence.

**Trust Posture Wiring (conformance-vector integrity-manifest re-pin):**

- **Severity:** `halt-and-report` at gate-review (reviewer at `/implement` + release-specialist at `/release` confirm any conformance-vector diff re-pins its `*.sha256`); `block` at the structural CI gate (`shasum -a256 -c` is a structural exit-code signal per `hook-output-discipline.md` MUST-2).
- **Grace period:** 7 days from rule landing.
- **Cumulative posture impact:** same-class violations (vector changed without manifest re-pin) contribute per `trust-posture.md` MUST-4 (3× same-rule / 5× total in 30d → drop 1 posture).
- **Regression-within-grace:** trigger key `integrity_manifest_not_repinned` fires emergency downgrade (1 step) per `trust-posture.md` MUST-4.
- **Receipt requirement:** SessionStart `[ack: cross-sdk-inspection]` IFF `posture.json::pending_verification` includes this rule_id (soft-gate; shared with Rule 4b).
- **Detection mechanism:** Phase 1 — the CI `Verify vector integrity` step (`shasum -a256 -c *.sha256`) is the structural detector; the canonical-vector `/redteam` integrity-manifest-sweep lens enumerates every `*.sha256` and runs the check. Phase 2 (deferred): a pre-commit hook asserting that a changed `*.json` under a vectors dir co-changes its manifest.
- **Violation scope:** this clause (conformance-vector integrity-manifest re-pin). Every violation row names the vector file + its stale manifest.
- **Origin:** PR #1411 Gap 1 (2026-06-20) — the `PACT_VECTORS.sha256` re-pin omission a "converged" redteam missed because no round ran `shasum -c`; closed by commit `b4929d924` + a new integrity-manifest-sweep lens.

### 4d. New Fields On A Cross-SDK Signed Model MUST Prune-When-Unset From The Signing Pre-Image

When a commit ADDS a new optional field to a data model whose serialization feeds a cross-SDK signing OR hash pre-image (an Ed25519-signed envelope, a signed trace, an audit-chain record), the field MUST NOT change the pre-image of instances that do NOT set it. `model_dump(mode="json")` / `to_dict()` emits a `None`-default field as a `null` key, so a naive addition changes the signed bytes for EVERY existing instance — a pre-existing or sibling-SDK-signed artifact then fails verification even though nothing about it changed. The signing pre-image builder MUST PRUNE the UNSET (`None`/absent) new field so a not-configured instance signs BYTE-IDENTICALLY to the pre-addition form; a CONFIGURED value stays in the pre-image (cryptographically bound). Classify empirically (byte-diff a not-configured instance against the pre-addition bytes) and pin a regression test asserting the not-configured instance's signed bytes carry NO new key AND a configured instance's DO. The not-configured case is byte-NEUTRAL (no cross-SDK lockstep); ONLY the configured case is a coordinated lockstep (the sibling SDK adds the same field + the same prune-when-unset rule + matching key-order/number-typing).

```python
# DO — a shared signing-pre-image builder (called by BOTH sign and verify) prunes the UNSET
#      new field so a not-configured instance signs byte-identically to pre-addition. Full example in the guide.
# DO NOT — add the field and sign the raw model_dump (the null key changes EVERY signature;
#      every pre-existing / cross-SDK-signed instance now fails verify()).
```

**Why:** A signed model's pre-image is a byte-for-byte cross-SDK + cross-version contract (Rule 4); a new null key on every instance invalidates every signature the sibling SDK or a prior version produced, and the within-version test suite cannot see it (sign and verify share the new code). See guide for the BLOCKED corpus + kailash-py #1510 evidence.

**Trust Posture Wiring (cross-SDK signed-model field additions):**

- **Severity:** `halt-and-report` at gate-review (reviewer + security-reviewer at `/implement` confirm any new field on a signing/hash-pre-image model prunes-when-unset AND ships a byte-identity regression pin); `advisory` at the hook layer (per `hook-output-discipline.md` MUST-2 a lexical model-field-addition scan cannot carry `block`).
- **Grace period:** 7 days from clause landing (2026-07-11 → 2026-07-18).
- **Cumulative posture impact:** same-class violations (a new field on a cross-SDK signed model that changes the not-configured pre-image) contribute to `trust-posture.md` MUST-4 cumulative-window math (3× same-rule / 5× total in 30d → drop 1 posture).
- **Regression-within-grace:** a same-class violation within the 7-day grace window routes through the GENERIC `regression_within_grace` emergency trigger per `trust-posture.md` MUST-4 (1× = drop 1 posture) — no dedicated per-clause trigger key (minting one would drag `trust-posture.md`, a self-referential-codify allowlist file, into a self-ref edit; the universal `regression_within_grace` trigger already covers a post-cutoff grace-period clause). Named deviation from the canonical key-per-clause shape, recorded here per `trust-posture.md` Rule 8 — the same no-dedicated-key disposition `security.md` § Enforcement-Surface Parity and `git.md` § CI-check/merge took.
- **Receipt requirement:** SessionStart `[ack: cross-sdk-inspection]` IFF `posture.json::pending_verification` includes this rule_id (soft-gate; one file-level `cross-sdk-inspection` ack shared across all sub-rules of this file).
- **Detection mechanism:** Phase 1 — gate-level reviewer at `/implement`: for any diff adding a field to a model reachable from a `serialize_for_signing` / signing / hash pre-image, demand the prune-when-unset builder + the byte-identity regression pin (not-configured → no new key; configured → new key present). Phase 2 (deferred): a regression-suite invariant enumerating signed-model fields and asserting each new one prunes-when-unset.
- **Violation scope:** this clause (new-field additions to cross-SDK signing/hash pre-image models). Every violation row names the model + the un-pruned field.
- **Origin:** kailash-py #1510 BH5 (PR #1671 → release #1672, kailash 2.48.0, 2026-07-11) — adding `circuit_*` fields to `OperationalConstraintConfig` (nested in the signed `ConstraintEnvelopeConfig`) changed the Ed25519 pre-image for every envelope; a two-round `/redteam` caught the HIGH, fixed via `_envelope_signing_dict` prune-when-unset (the BH3 unbound-form backward-compat pattern).

### 5. Inspection Checklist

When closing any issue, verify:

- [ ] Does the other SDK have this issue? (check or file)
- [ ] If feature: is it in the other SDK's roadmap?
- [ ] If bug: could the same bug exist in the other SDK?
- [ ] Cross-reference added to both issues if applicable

**Why:** Closing without cross-SDK verification is the primary cause of feature drift — the checklist is the last gate before an issue is forgotten.

### 6. Cross-SDK References In Public-Published Artifacts Are BLOCKED

Public-published artifacts — CHANGELOG, README (the PyPI/crates long-description), package metadata, and any world-readable doc — MUST NOT carry a private-repo-QUALIFIED reference to the Rust SDK: its org/repo slug (`<org>/kailash-rs`), a bare repo name that identifies it (`kailash-rs`), a crate/binding PATH (`bindings/kailash-rs/…`), or an issue/version reference that NAMES the repo (`kailash-rs#52`, "kailash-rs v3.x"). A bare, already-de-org'd issue/PR number (`#52`) in prose that does not name the private repo IS permitted — once the repo is unnamed, the number discloses nothing. Reference the Rust SDK by role ("the Rust SDK") or by resolver key (`build.rs`), never by org/repo/crate-path; the real org/repo lives only in the gitignored `loom-links.local.json` (`cross-repo.md` MUST-1).

```markdown
# DO — public artifact names the SDK by role, keeps the bare number

# "Aligned the trace-event fingerprint with the Rust SDK (parity vector #598)."

# DO NOT — public artifact names the private repo / org / crate-path / qualified issue

# "Aligned with <private-org>/kailash-rs#598 (bindings/kailash-rs/test-vectors/…)."
```

**Why:** Public artifacts (PyPI/crates long-description, README, CHANGELOG) are indexed by every registry and downstream consumer; a private-repo-qualified reference is a permanent, correlatable breadcrumb to the private Rust SDK's existence, org, and internal layout. The bare de-org'd number carries the technical cross-reference without the disclosure. See guide for the BLOCKED corpus + #1487 / #1488 evidence.

**Trust Posture Wiring (cross-SDK references in public-published artifacts):**

- **Severity:** `halt-and-report` at gate-review (reviewer + security-reviewer at `/implement` + release-specialist at `/release` grep CHANGELOG / README / package-metadata diffs for a private-repo-qualified Rust-SDK reference before publish); `advisory` at the hook layer per `hook-output-discipline.md` MUST-2.
- **Grace period:** 7 days from clause landing (2026-07-03 → 2026-07-10).
- **Cumulative posture impact:** same-class violations (a private-repo-qualified Rust-SDK reference landing in a public-published artifact) contribute to `trust-posture.md` MUST-4 cumulative-window math (3× same-rule / 5× total in 30d → drop 1 posture).
- **Regression-within-grace:** trigger key `public_artifact_private_repo_disclosure` fires emergency downgrade (1 step) per `trust-posture.md` MUST-4.
- **Receipt requirement:** SessionStart soft-gate `[ack: cross-sdk-inspection]` IFF `posture.json::pending_verification` includes this rule_id (shared with Rules 4b/4c).
- **Detection mechanism:** Phase 1 (gate-review) — release-specialist at `/release` + reviewer at `/implement` grep the public-artifact diff (`CHANGELOG.md`, `README.md`, `pyproject.toml`/`Cargo.toml` metadata) for `kailash-rs`, `<org>/kailash-rs`, `bindings/kailash-rs`, and `kailash-rs#` — any hit that is not a bare de-org'd number is a finding. Phase 2 (deferred) — a `scan-synced-disclosure.mjs` extension asserting no private-repo-qualified Rust-SDK token in public-published paths.
- **Violation scope:** this clause (Rule 6 — private-repo-qualified Rust-SDK references in public-published artifacts). Every violation row names the public artifact + the qualified token.
- **Origin:** kailash-py #1487/#1488 (2026-07-02) — CHANGELOG (27 refs) + README (3 bare refs) genericized after the repo-path correction surfaced the private org in public-reaching artifacts. Landed at loom via `/sync-from-build` py Shard B (journal/0402).

## Automation

When the Claude Code Maintenance workflow is active, the fix job prompt includes cross-SDK inspection as Phase 4.5 (between codify and commit). When paused, this must be done manually.
