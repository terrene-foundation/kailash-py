---
priority: 10
scope: path-scoped
paths:
  - "**/src/**"
  - "**/tests/**"
---

# Cross-SDK Issue Inspection

## Scope

These rules apply to ALL bug fixes, feature implementations, and issue resolutions in BOTH BUILD repos (kailash-rs and kailash-py).

## MUST Rules

### 1. Cross-SDK Inspection on Every Issue

When an issue is found or fixed in ONE BUILD repo, you MUST inspect the OTHER BUILD repo for the same or equivalent issue.

**Why:** Bugs in shared architecture (trust plane, DataFlow, Nexus) almost always exist in both SDKs — fixing only one leaves users of the other SDK hitting the same issue.

**kailash-rs issue found → inspect kailash-py**:

- Does the Python SDK have the same bug?
- Does the Python SDK need the equivalent feature?
- File a GitHub issue on `terrene-foundation/kailash-py` if relevant.

**kailash-py issue found → inspect kailash-rs**:

- Does the Rust SDK have the same bug?
- Does the Rust SDK need the equivalent feature?
- File a GitHub issue on `terrene-foundation/kailash-rs` if relevant.

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
# DO — both tests; one exercises the sibling path, one locks the signature
@pytest.mark.regression
async def test_issue_XXX_cross_sdk_parity_via_sibling_path(test_suite):
    # The Rust bug triggered at execute_raw(sql, params). Python execute_raw
    # has no params. The parameter-binding path in Python is Express.bulk_create.
    db = DataFlow(test_suite.config.url)
    # ... exercise shrinking-arity bulk_create against real Postgres
    assert poisoned_result.get("success") is True

@pytest.mark.regression
def test_issue_XXX_execute_raw_has_no_params_arg():
    # Structural invariant: if this signature ever grows a `params` kwarg,
    # the sibling bug class becomes reachable here and cross-SDK parity
    # MUST be re-audited.
    import inspect
    from dataflow.core.pool_lightweight import LightweightPool
    sig = inspect.signature(LightweightPool.execute_raw)
    non_self = [p.name for n, p in sig.parameters.items() if n != "self"]
    assert non_self == ["sql"], f"signature drifted: {sig}"

# DO NOT — close the cross-SDK issue with only a hand-waving comment
gh issue close XXX --comment "N/A — Python execute_raw has no params arg"
# ↑ no test, no invariant; a future refactor silently reopens the bug class
#   and the original sibling-report loses its correlation
```

**BLOCKED rationalizations:**

- "The signatures are obviously different, no test needed"
- "Our implementation can't have that bug"
- "The structural invariant is enforced by the type system"
- "Cross-SDK is belt-and-suspenders; one test is enough"
- "We'll add the invariant test when the signature changes"

**Why:** "Our signature doesn't have the arg" is true today and false the day someone ports a convenience method from the sibling SDK. The structural invariant test is the only mechanism that makes the signature _itself_ part of the contract — the moment the signature grows toward the sibling shape, the test fails and the agent reading the failure has a direct pointer back to the cross-SDK bug class. The sibling-path Tier 2 test proves the bug class does not manifest through the surface it COULD manifest through; without it, "different API" conceals a parallel bug the other SDK's API shape hid. Evidence: issue #525 (cross-SDK of kailash-rs#424) — Python `execute_raw(sql)` structurally cannot hit the Rust binding-layer UTF-8 corruption; disposition landed both an Express `bulk_create` sibling-path test AND a signature invariant test locking `LightweightPool.execute_raw(sql)` at PR #528.

Origin: Issue #525 / PR #528 (2026-04-19) — kailash-rs#424 parity check.

### 4. Cross-SDK Hash / Fingerprint Helpers MUST Pin Byte Vectors From Sibling SDK

Any helper that claims byte-shape parity with a sibling SDK (cross-SDK fingerprint, hash, mask, audit-chain digest, log-correlation token) MUST pin AT LEAST 3 byte-vector test cases empirically derived from the sibling SDK's actual output AND cover sentinel values (empty input, all-zero, all-one, single-byte). The byte vectors live in the cross-SDK regression test as raw hex strings, NOT abstract assertions like "same length" or "starts with sha256:".

```python
# DO — pin actual byte vectors from sibling SDK
@pytest.mark.regression
def test_fingerprint_secret_matches_kailash_rs_byte_for_byte():
    # Vectors derived from kailash-rs Blake2bVar(4) digest output at v3.23.0
    cases = [
        (b"",                             "00000000"),  # empty-input sentinel
        (b"hello",                        "8ed5b1d4"),
        (b"\x00" * 32,                    "0a0e0a8b"),
        (b"OPENAI_API_KEY=sk-12345",      "f3c2b1d8"),
    ]
    for raw, expected in cases:
        assert fingerprint_secret(raw) == expected, f"divergence on {raw!r}"

# DO NOT — abstract parity claim with no byte pinning
def test_fingerprint_secret_has_4_hex_chars():
    out = fingerprint_secret(b"hello")
    assert len(out) == 4 and all(c in "0123456789abcdef" for c in out)
    # ↑ proves shape but NOT byte-for-byte equivalence to the sibling SDK
```

**BLOCKED rationalizations:**

- "Both SDKs use SHA-256; the implementations must agree"
- "Length + hex-char regex is sufficient"
- "We'll align the byte shapes when a divergence is reported"
- "The sibling SDK's vectors will drift; pinning them creates maintenance"
- "Cross-SDK log correlation is a nice-to-have, not a contract"

**Why:** Cross-SDK forensic correlation depends on identical byte output for identical input across every helper that claims parity. A "same length, same prefix" assertion passes when the underlying algorithm is `Blake2bMac<U4>` (empty-key MAC) on one side and `Blake2bVar(4)` (digest) on the other — the lengths agree, the bytes don't. The empty-input sentinel is the canonical sibling-SDK divergence point: a digest mode emits a stable hash; a MAC mode emits a length-prefixed empty MAC. Pinning ≥3 vectors + sentinels converts "we both call SHA-256" hand-waving into a structural contract that breaks loudly when implementations drift. Evidence: kailash-rs PR #598 first cut shipped `Blake2bMac<U4>` empty-key MAC mode while kailash-py uses `Blake2bVar(4)` digest mode + empty-input sentinel "00000000"; 4 hex chars vs 16 hex chars; empty-input divergence; cross-SDK log correlation silently broken until 2 reviewers caught it. Applies to every future hash helper claiming kailash-py / kailash-rs parity (`fingerprint_secret`, `mask_url`, `audit_chain_hash`, etc.).

Origin: kailash-rs PR #598 (2026-04-25) cross-SDK fingerprint helper — first cut had empty-input + algorithm-mode divergence with kailash-py; caught by reviewers but only because abstract parity assertions were absent. Codified to make the absence loud.

### Rule 4a: Sibling-Canonical Fixtures MUST Be Vendored, Not Re-Authored

When the sibling SDK is the canonical author of a cross-SDK fixture file (test vectors, byte-pin canonicals, conformance JSON), the local SDK's test directory MUST vendor the canonical file (commit the same bytes) — NOT maintain a parallel hand-authored copy. Local consumers (Rust loaders, Python binding tests, pin-gen reproducibility scripts) MUST be updated to read the canonical shape in the same PR. Orphaned consumers reading the old shape are a Rule 4 (orphan-detection) violation.

```
# DO — vendor the canonical file from the sibling repo
$ cp ../kailash-py/tests/fixtures/trace-event-canonical.json \
     bindings/kailash-rs/test-vectors/trace-event-canonical.json
$ git add bindings/kailash-rs/test-vectors/trace-event-canonical.json
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

Origin: kailash-rs PR #761 (merged 8286775f, 2026-05-02) — vendored `test-vectors/trace-event-canonical.json` from `terrene-foundation/kailash-py:main`. Pre-vendor: rs-side fixture had `id`/`input` shape with V1-V3 inputs cosmetically different from py-side; V4-V5 fingerprints already matched (Unicode coverage tests aligned, V1-V3 weren't). Post-vendor: all 5 V1-V5 fingerprints reproduce byte-for-byte through both Rust `compute_trace_event_fingerprint` AND Python binding `serialize_canonical_json`. Same-shard sibling consumer fix per `autonomous-execution.md` Rule 4 (Python binding test orphaned at first push, CI surfaced it, fix-immediately landed in same PR commit `10274a5d`). Codified GLOBAL via /sync rs Gate 1 (2026-05-02 second cycle).

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
- **Receipt requirement:** SessionStart `[ack: cross-sdk-inspection]` IFF `posture.json::pending_verification` includes this rule_id (soft-gate; shared with Rule 4b).
- **Detection mechanism:** Phase 1 — the CI `Verify vector integrity` step (`shasum -a256 -c *.sha256`) is the structural detector; the canonical-vector `/redteam` integrity-manifest-sweep lens enumerates every `*.sha256` and runs the check. Phase 2 (deferred): a pre-commit hook asserting that a changed `*.json` under a vectors dir co-changes its manifest.
- **Violation scope:** this clause (conformance-vector integrity-manifest re-pin). Every violation row names the vector file + its stale manifest.
- **Origin:** PR #1411 Gap 1 (2026-06-20) — the `PACT_VECTORS.sha256` re-pin omission a "converged" redteam missed because no round ran `shasum -c`; closed by commit `b4929d924` + a new integrity-manifest-sweep lens.

### 5. Inspection Checklist

When closing any issue, verify:

- [ ] Does the other SDK have this issue? (check or file)
- [ ] If feature: is it in the other SDK's roadmap?
- [ ] If bug: could the same bug exist in the other SDK?
- [ ] Cross-reference added to both issues if applicable

**Why:** Closing without cross-SDK verification is the primary cause of feature drift — the checklist is the last gate before an issue is forgotten.

## Examples

```
# Issue #52 in kailash-rs: per-request API key override
# → Filed kailash-py#12 as cross-SDK alignment
gh issue create --repo terrene-foundation/kailash-py \
  --title "feat(kaizen): per-request API key override" \
  --label "cross-sdk" \
  --body "Cross-SDK alignment with terrene-foundation/kailash-rs#52"
```

## Automation

When the Claude Code Maintenance workflow is active, the fix job prompt
includes cross-SDK inspection as Phase 4.5 (between codify and commit).
When paused, this must be done manually.
