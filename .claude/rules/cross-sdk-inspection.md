---
priority: 10
scope: path-scoped
paths:
  - "**/src/**"
  - "**/tests/**"
---

# Cross-SDK Issue Inspection

See `.claude/guides/rule-extracts/cross-sdk-inspection.md` for the full Rule-3a structural-invariant test pair, the Rule-4 byte-vector example, and extended examples.

## Scope

These rules apply to ALL bug fixes, feature implementations, and issue resolutions in BOTH BUILD repos (the Rust SDK and kailash-py).

## MUST Rules

### 1. Cross-SDK Inspection on Every Issue

When an issue is found or fixed in ONE BUILD repo, you MUST inspect the OTHER BUILD repo for the same or equivalent issue.

**Why:** Bugs in shared architecture (trust plane, DataFlow, Nexus) almost always exist in both SDKs — fixing only one leaves users of the other SDK hitting the same issue.

**Rust SDK issue found → inspect kailash-py**:

- Does the Python SDK have the same bug?
- Does the Python SDK need the equivalent feature?
- File a GitHub issue on `terrene-foundation/kailash-py` if relevant.

**kailash-py issue found → inspect the Rust SDK**:

- Does the Rust SDK have the same bug?
- Does the Rust SDK need the equivalent feature?
- File a GitHub issue on the Rust SDK BUILD repo (resolver key `build.rs`; resolve the real org/repo via the gitignored `loom-links.local.json` per `cross-repo.md` MUST-1) if relevant.

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

1. **A Tier 2 test through the sibling path that DOES bind parameters** — the bug class may still manifest at a different API surface in this SDK (e.g., Express `bulk_create`, `update`, `upsert`). The test mirrors the sibling SDK's repro scenario through the equivalent parameter-binding path in this SDK.
2. **A structural invariant test that pins the signature** — asserts the API signature that prevents the bug class from existing at this surface (e.g., `execute_raw` takes only `sql` as a positional arg, no `params`). If a future refactor grows the signature to match the sibling SDK's shape, the invariant test fails loudly and forces a re-audit.

```python
# DO — BOTH: (1) a Tier 2 test through the sibling parameter-binding path
#      (e.g. Express bulk_create); (2) a signature-invariant test pinning the
#      absent arg (assert execute_raw takes only `sql`) so an arity-growth
#      refactor toward the sibling shape fails loudly. Full pair in the guide.
# DO NOT — close the cross-SDK issue with a hand-waving comment (no test, no
#      invariant; a future refactor silently reopens the bug class).
```

**Why:** "Our signature doesn't have the arg" is true today and false the day someone ports a convenience method from the sibling SDK. See guide for the full test pair + BLOCKED corpus. The structural invariant test is the only mechanism that makes the signature _itself_ part of the contract — the moment the signature grows toward the sibling shape, the test fails and the agent reading the failure has a direct pointer back to the cross-SDK bug class. The sibling-path Tier 2 test proves the bug class does not manifest through the surface it COULD manifest through; without it, "different API" conceals a parallel bug the other SDK's API shape hid. Evidence: issue #525 (cross-SDK of the Rust SDK's #424) — Python `execute_raw(sql)` structurally cannot hit the Rust binding-layer UTF-8 corruption; disposition landed both an Express `bulk_create` sibling-path test AND a signature invariant test locking `LightweightPool.execute_raw(sql)` at PR #528.

Origin: Issue #525 / PR #528 (2026-04-19) — the Rust SDK's #424 parity check.

### 4. Cross-SDK Hash / Fingerprint Helpers MUST Pin Byte Vectors From Sibling SDK

Any helper that claims byte-shape parity with a sibling SDK (cross-SDK fingerprint, hash, mask, audit-chain digest, log-correlation token) MUST pin AT LEAST 3 byte-vector test cases empirically derived from the sibling SDK's actual output AND cover sentinel values (empty input, all-zero, all-one, single-byte). The byte vectors live in the cross-SDK regression test as raw hex strings, NOT abstract assertions like "same length" or "starts with sha256:".

```python
# DO — pin ≥3 real sibling-SDK byte vectors + sentinels (empty/all-zero/single-byte)
#      as raw hex: assert fingerprint_secret(raw) == expected for each. Full example + the
#      empty-input digest-vs-MAC divergence in the guide.
# DO NOT — abstract parity claim (assert len==4 and all-hex) — proves shape, not bytes.
```

**BLOCKED rationalizations:**

- "Both SDKs use SHA-256; the implementations must agree"
- "Length + hex-char regex is sufficient"
- "We'll align the byte shapes when a divergence is reported"
- "The sibling SDK's vectors will drift; pinning them creates maintenance"
- "Cross-SDK log correlation is a nice-to-have, not a contract"

**Why:** Cross-SDK forensic correlation depends on identical byte output for identical input across every helper that claims parity. A "same length, same prefix" assertion passes when the underlying algorithm is `Blake2bMac<U4>` (empty-key MAC) on one side and `Blake2bVar(4)` (digest) on the other — the lengths agree, the bytes don't. The empty-input sentinel is the canonical sibling-SDK divergence point: a digest mode emits a stable hash; a MAC mode emits a length-prefixed empty MAC. Pinning ≥3 vectors + sentinels converts "we both call SHA-256" hand-waving into a structural contract that breaks loudly when implementations drift. Evidence: the Rust SDK PR #598 first cut shipped `Blake2bMac<U4>` empty-key MAC mode while kailash-py uses `Blake2bVar(4)` digest mode + empty-input sentinel "00000000"; 4 hex chars vs 16 hex chars; empty-input divergence; cross-SDK log correlation silently broken until 2 reviewers caught it. Applies to every future hash helper claiming kailash-py / the Rust SDK parity (`fingerprint_secret`, `mask_url`, `audit_chain_hash`, etc.).

Origin: the Rust SDK PR #598 (2026-04-25) cross-SDK fingerprint helper — first cut had empty-input + algorithm-mode divergence with kailash-py; caught by reviewers but only because abstract parity assertions were absent. Codified to make the absence loud.

### Rule 4a: Sibling-Canonical Fixtures MUST Be Vendored, Not Re-Authored

When the sibling SDK is the canonical author of a cross-SDK fixture file (test vectors, byte-pin canonicals, conformance JSON), the local SDK's test directory MUST vendor the canonical file (commit the same bytes) — NOT maintain a parallel hand-authored copy. Local consumers (Rust loaders, Python binding tests, pin-gen reproducibility scripts) MUST be updated to read the canonical shape in the same PR. Orphaned consumers reading the old shape are a Rule 4 (orphan-detection) violation.

```
# DO — vendor the canonical file from the sibling repo
$ cp ../kailash-py/tests/fixtures/trace-event-canonical.json \
     bindings/<rust-sdk-repo>/test-vectors/trace-event-canonical.json
$ git add bindings/<rust-sdk-repo>/test-vectors/trace-event-canonical.json
# Update Rust loader + Python binding test + pin-gen script to read canonical shape — same PR.

# DO NOT — maintain a parallel hand-authored copy
# rs-side fixture: { "id": "v1", "input": "..." }   ← drifted shape
# py-side fixture: { "name": "v1", "input_repr": "..." }   ← canonical shape
# fingerprints happen to match for V4-V5 but not V1-V3; cross-SDK contract silently broken.
```

**BLOCKED rationalizations:**

- "Re-authoring is faster than vendoring; the JSON is short"
- "We'll vendor when the sibling SDK formalizes the canonical"
- "Field-name divergence is cosmetic, fingerprints still match"
- "Vendoring creates a sync burden every time the sibling updates the fixture"
- "Our loader can normalize either shape; vendoring isn't strictly required"

**Why:** Parallel copies drift in shape (`id`/`input` vs `name`/`input_repr`) AND content (different cosmetic input data); vendoring guarantees byte-for-byte file-level parity. The cross-SDK fingerprint contract (Rule 4 above pins ≥3 byte-vectors) is met when the local implementation produces byte-identical output for every vector in the vendored fixture. Orphaned consumers reading the old shape fail at first CI run with KeyError / `cannot find field` / "missing field `id`" — the structural defense against silent drift is `same file, same bytes`. The "sync burden" argument inverts the actual cost: parallel copies create N × M sync work on every fixture edit; vendoring creates 1 sync work per edit (a file copy from sibling repo).

Origin: the Rust SDK PR #761 (merged 8286775f, 2026-05-02) — vendored `test-vectors/trace-event-canonical.json` from `terrene-foundation/kailash-py:main`. Pre-vendor: rs-side fixture had `id`/`input` shape with V1-V3 inputs cosmetically different from py-side; V4-V5 fingerprints already matched (Unicode coverage tests aligned, V1-V3 weren't). Post-vendor: all 5 V1-V5 fingerprints reproduce byte-for-byte through both Rust `compute_trace_event_fingerprint` AND Python binding `serialize_canonical_json`. Same-shard sibling consumer fix per `autonomous-execution.md` Rule 4 (Python binding test orphaned at first push, CI surfaced it, fix-immediately landed in same PR commit `10274a5d`). Codified GLOBAL via /sync rs Gate 1 (2026-05-02 second cycle).

### 4b. Byte-CHANGING Canonical-Encoder Switches Are Cross-SDK Lockstep, Not Single-SDK

When migrating a canonical-encoder / serialization helper that feeds a cross-SDK signing or hash pre-image (e.g. `json.dumps(..., default=str)` → a stricter `canonical_scalars`), you MUST first classify the switch as **byte-NEUTRAL** or **byte-CHANGING** by EMPIRICALLY byte-diffing production output on fixed inputs — NOT by reasoning about it. A byte-CHANGING switch where the sibling SDK mirrors this SDK's CURRENT bytes MUST NOT ship single-SDK; it is a coordinated cross-SDK lockstep (one re-pin event in both repos) and the current bytes MUST be pinned in a regression test as a loud tripwire until the lockstep lands. A byte-NEUTRAL switch (the normalization layer already pre-normalizes every divergent type, so the swap changes zero currently-emitted bytes) MAY ship single-SDK.

```python
# DO — empirically classify, then pin current bytes for the byte-CHANGING site (py-illustrative)
@pytest.mark.regression
def test_witness_sign_payload_pins_current_default_str_bytes():
    # CROSS_SDK_BLOCKED: AuditAnchor reaches the encoder un-normalized; default=str
    # stringifies the dataclass repr, canonical_scalars asdict-expands it → different SHA.
    # the sibling SDK mirrors these CURRENT bytes; a single-SDK switch diverges the two SDKs.
    assert _sign_payload(fixture) == "edfdf52b…"   # tripwire until the sibling-SDK lockstep
# (the byte-NEUTRAL sibling — envelope_hash, where normalization pre-normalizes — SHIPPED single-SDK)

# DO NOT — switch a byte-CHANGING signing encoder single-SDK (py-illustrative)
def to_canonical_json(self):
    return json.dumps(self._hashable_dict(), default=canonical_scalars)  # was default=str
    # ↑ silently diverges every on-disk signed artifact from the sibling SDK's bytes;
    #   no test pins the old bytes, so the cross-SDK break is invisible until a verify fails.
```

**BLOCKED rationalizations:**

- "canonical_scalars is stricter / more correct, so switching is an improvement"
- "I reasoned through the types; it can't change the bytes" (reason is not a byte-diff)
- "The sibling SDK will catch up on its next release"
- "It's one encoder; the lockstep ceremony is overkill"
- "Pinning the OLD bytes blocks the migration I'm trying to do"

**Why:** A canonical signing encoder is a byte-for-byte cross-SDK contract (Rule 4); switching it single-SDK silently diverges every artifact the sibling SDK must re-verify, and the break surfaces only when a cross-SDK verify fails in production. Empirical byte-diff (run the code, compare SHAs) is the only sound classifier — "I reasoned the types are equivalent" is exactly how the audit-chain / witness-family / envelope-HMAC sites were each almost switched single-SDK. Pinning the current bytes converts the deferred lockstep from an un-tracked memory into a test that fails loudly the moment someone switches one side.

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
# DO — re-pin the manifest in the same commit that changes the vector
$ edit tests/trust/pact/conformance/vectors/audit_anchor.json   # the canonical fix
$ shasum -a256 tests/trust/.../audit_anchor.json                 # recompute
$ edit PACT_VECTORS.sha256                                       # re-pin in SAME commit
$ shasum -a256 -c PACT_VECTORS.sha256                            # verify green before push

# DO NOT — change the vector, leave the manifest stale
$ edit tests/trust/.../audit_anchor.json && git commit           # manifest unchanged
# ↑ remote `Verify vector integrity` (shasum -c) goes RED ("audit_anchor.json: FAILED");
#   a "converged" redteam that never ran shasum -c declares clean over a red CI gate.
```

**BLOCKED rationalizations:**

- "The vector change is correct; the manifest is a separate concern"
- "CI will catch the manifest if it's stale" (catching it red ≠ shipping it green)
- "The redteam already converged" (a convergence claim over a red remote gate is false — `verify-resource-existence.md` MUST-4)
- "shasum -c isn't part of the canonical-conformance lens-set"

**Why:** An integrity manifest exists to make silent tampering of a pinned vector loud; a vector change that omits the re-pin either reds the CI gate (best case) or — if the manifest also drifts — silently no-ops the integrity check for that file until a future real tamper goes undetected. The redteam integrity-manifest sweep is the lens that makes a "converged" claim cite `shasum -c` evidence rather than assume it; without it a round can declare 2-clean-rounds while the remote conformance gate is red. Evidence: PR #1411 (2026-06-20) shipped the correct `audit_anchor.json` canonical fix but omitted the `PACT_VECTORS.sha256` re-pin → red `Cross-SDK Conformance` gate that a prior "converged (2 clean passes)" redteam missed because no round ran `shasum -c`.

**Trust Posture Wiring (conformance-vector integrity-manifest re-pin):**

- **Severity:** `halt-and-report` at gate-review (reviewer at `/implement` + release-specialist at `/release` confirm any conformance-vector diff re-pins its `*.sha256`); `block` at the structural CI gate (`shasum -a256 -c` is a structural exit-code signal per `hook-output-discipline.md` MUST-2).
- **Grace period:** 7 days from rule landing.
- **Cumulative posture impact:** same-class violations (vector changed without manifest re-pin) contribute per `trust-posture.md` MUST-4 (3× same-rule / 5× total in 30d → drop 1 posture).
- **Regression-within-grace:** trigger key `integrity_manifest_not_repinned` fires emergency downgrade (1 step) per `trust-posture.md` MUST-4.
- **Receipt requirement:** SessionStart `[ack: cross-sdk-inspection]` IFF `posture.json::pending_verification` includes this rule_id (soft-gate; one file-level `cross-sdk-inspection` ack shared across all sub-rules of this file).
- **Detection mechanism:** Phase 1 — the CI `Verify vector integrity` step (`shasum -a256 -c *.sha256`) is the structural detector; the canonical-vector `/redteam` integrity-manifest-sweep lens enumerates every `*.sha256` and runs the check. Phase 2 (deferred): a pre-commit hook asserting that a changed `*.json` under a vectors dir co-changes its manifest.
- **Violation scope:** this clause (conformance-vector integrity-manifest re-pin). Every violation row names the vector file + its stale manifest.
- **Origin:** PR #1411 Gap 1 (2026-06-20) — the `PACT_VECTORS.sha256` re-pin omission a "converged" redteam missed because no round ran `shasum -c`; closed by commit `b4929d924` + a new integrity-manifest-sweep lens.

### 4d. New Fields On A Cross-SDK Signed Model MUST Prune-When-Unset From The Signing Pre-Image

When a commit ADDS a new optional field to a data model whose serialization feeds a cross-SDK signing OR hash pre-image (an Ed25519-signed envelope, a signed trace, an audit-chain record), the field MUST NOT change the pre-image of instances that do NOT set it. `model_dump(mode="json")` / `to_dict()` emits a `None`-default field as a `null` key, so a naive addition changes the signed bytes for EVERY existing instance — a pre-existing or sibling-SDK-signed artifact then fails verification even though nothing about it changed. The signing pre-image builder MUST PRUNE the UNSET (`None`/absent) new field so a not-configured instance signs BYTE-IDENTICALLY to the pre-addition form; a CONFIGURED value stays in the pre-image (cryptographically bound). Classify empirically (byte-diff a not-configured instance against the pre-addition bytes — reason is not a byte-diff) and pin a regression test asserting the not-configured instance's signed bytes carry NO new key AND a configured instance's DO. The not-configured case is byte-NEUTRAL (no cross-SDK lockstep); ONLY the configured case is a coordinated lockstep (the sibling SDK adds the same field + the same prune-when-unset rule + matching key-order/number-typing).

```python
# DO — a shared signing-pre-image builder prunes the UNSET new field
_NEW_OPTIONAL_FIELDS = ("circuit_failure_threshold", "circuit_window_seconds", "circuit_cooldown_seconds")
def _signing_dict(model) -> dict:
    payload = model.model_dump(mode="json")
    nested = payload.get("operational")
    if isinstance(nested, dict):
        for f in _NEW_OPTIONAL_FIELDS:
            if nested.get(f) is None:
                nested.pop(f, None)          # unset → zero bytes → byte-identical to pre-addition
    return payload
# both sign AND verify call _signing_dict(...) (a mismatch breaks within-version signatures)

# DO NOT — add the field, sign the raw model_dump (null key changes EVERY signature)
payload = serialize_for_signing(model.model_dump(mode="json"))   # emits "circuit_*":null for a breaker-less
# → every pre-existing / cross-SDK-signed instance now fails verify(); a backward-compat + cross-SDK break
```

**BLOCKED rationalizations:**

- "The field is optional, adding it is backward-compatible"
- "`exclude_none=True` on the dump fixes it" (it drops OTHER pre-existing nulls too — a wider break)
- "I reasoned the bytes; a not-set field can't matter" (reason is not a byte-diff)
- "The within-version sign/verify round-trip passes" (it can't catch cross-VERSION — both halves use the new code)
- "It's a new SDK version; existing signatures re-issuing is fine"

**Why:** A signed model's pre-image is a byte-for-byte cross-SDK + cross-version contract (Rule 4); a new null key on every instance invalidates every signature the sibling SDK or a prior version produced, and the within-version test suite cannot see it because sign and verify share the new code. Prune-when-unset makes the addition byte-neutral for the not-configured case (the BH3 unbound/bound pattern applied to field additions), confining the lockstep to instances that actually opt into the new field.

**Trust Posture Wiring (cross-SDK signed-model field additions):**

- **Severity:** `halt-and-report` at gate-review (reviewer + security-reviewer at `/implement` confirm any new field on a signing/hash-pre-image model prunes-when-unset AND ships a byte-identity regression pin); `advisory` at the hook layer (per `hook-output-discipline.md` MUST-2 a lexical model-field-addition scan cannot carry `block`).
- **Grace period:** 7 days from clause landing (2026-07-11 → 2026-07-18).
- **Cumulative posture impact:** same-class violations (a new field on a cross-SDK signed model that changes the not-configured pre-image) contribute to `trust-posture.md` MUST-4 cumulative-window math (3× same-rule / 5× total in 30d → drop 1 posture).
- **Regression-within-grace:** trigger key `cross_sdk_signed_field_addition` fires emergency downgrade (1 step) per `trust-posture.md` MUST-4.
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

CHANGELOG: "Aligned the trace-event fingerprint with the Rust SDK (parity vector #598)."

# DO NOT — public artifact names the private repo / org / crate-path / qualified issue

CHANGELOG: "Aligned with <private-org>/kailash-rs#598 (bindings/kailash-rs/test-vectors/…)."
```

**BLOCKED rationalizations:** "the repo name is public knowledge anyway" / "the CHANGELOG needs the exact cross-ref to be useful" / "it's only the org slug, not a customer name" / "the crate path documents where the vector lives" / "we'll scrub it before the next public release".

**Why:** Public artifacts (PyPI/crates long-description, README, CHANGELOG) are indexed by every registry, search engine, and downstream consumer; a private-repo-qualified reference is a permanent, correlatable breadcrumb to the private Rust SDK's existence, org, and internal layout — the Foundation-Independence (Directive 0) + `#255`/`#260` no-private-identifiers fence. The bare de-org'd number carries the technical cross-reference without the disclosure; naming the repo is what the fence blocks.

**Trust Posture Wiring (cross-SDK references in public-published artifacts):**

- **Severity:** `halt-and-report` at gate-review (reviewer + security-reviewer at `/implement` + release-specialist at `/release` grep CHANGELOG / README / package-metadata diffs for a private-repo-qualified Rust-SDK reference before publish); `advisory` at the hook layer per `hook-output-discipline.md` MUST-2.
- **Grace period:** 7 days from clause landing (2026-07-03 → 2026-07-10).
- **Cumulative posture impact:** same-class violations (a private-repo-qualified Rust-SDK reference landing in a public-published artifact) contribute to `trust-posture.md` MUST-4 cumulative-window math (3× same-rule / 5× total in 30d → drop 1 posture).
- **Regression-within-grace:** trigger key `public_artifact_private_repo_disclosure` fires emergency downgrade (1 step) per `trust-posture.md` MUST-4.
- **Receipt requirement:** SessionStart soft-gate `[ack: cross-sdk-inspection]` IFF `posture.json::pending_verification` includes this rule_id (one file-level `cross-sdk-inspection` ack shared across all sub-rules of this file).
- **Detection mechanism:** Phase 1 (gate-review) — release-specialist at `/release` + reviewer at `/implement` grep the public-artifact diff (`CHANGELOG.md`, `README.md`, `pyproject.toml`/`Cargo.toml` metadata) for `kailash-rs`, `<org>/kailash-rs`, `bindings/kailash-rs`, and `kailash-rs#` — any hit that is not a bare de-org'd number is a finding. Phase 2 (deferred) — a `scan-synced-disclosure.mjs` extension asserting no private-repo-qualified Rust-SDK token in public-published paths.
- **Violation scope:** this clause (Rule 6 — private-repo-qualified Rust-SDK references in public-published artifacts). Every violation row names the public artifact + the qualified token.
- **Origin:** kailash-py #1487/#1488 (2026-07-02) — CHANGELOG (27 refs) + README (3 bare refs) genericized after the repo-path correction surfaced the private org in public-reaching artifacts. Landed at loom via `/sync-from-build` py Shard B (journal/0402).

## Examples

```
# Issue #52 in the Rust SDK: per-request API key override
# → Filed kailash-py#12 as cross-SDK alignment
gh issue create --repo terrene-foundation/kailash-py \
  --title "feat(kaizen): per-request API key override" \
  --label "cross-sdk" \
  --body "Cross-SDK alignment with the Rust SDK's #52"
```

## Automation

When the Claude Code Maintenance workflow is active, the fix job prompt
includes cross-SDK inspection as Phase 4.5 (between codify and commit).
When paused, this must be done manually.
