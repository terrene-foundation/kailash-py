---
type: DECISION
date: 2026-06-05
created_at: 2026-06-05T00:00:00Z
author: agent
project: kailash-py
topic: "#1258 canonical-JSON encoder contracts: document + pin, do not unify"
phase: implement
tags: [trust, cross-sdk, canonical-json, signing, issue-1258]
---

# DECISION — #1258: document + pin the two canonical encoders; do NOT unify

**Date:** 2026-06-05
**Issue:** #1258 — trust: two canonical-JSON signing encoders diverge on `ensure_ascii`; `canonical_json_dumps` lacks pinned non-ASCII cross-SDK byte-vectors
**Phase:** analyze → implement (pre-redteam)
**Severity:** MEDIUM (latent cross-SDK byte-parity verification gap; no active break)

## Context

The trust layer ships **three** canonical-JSON encoders, each matching a
DIFFERENT Rust `serde` byte contract for a DIFFERENT subsystem (verified by
reading source + running both Python encoders against empirically-derived
vectors):

| Encoder                                              | `ensure_ascii`      | `sort_keys`            | Subsystem                                           | Rust counterpart                   |
| ---------------------------------------------------- | ------------------- | ---------------------- | --------------------------------------------------- | ---------------------------------- |
| `kailash.trust._json.canonical_json_dumps`           | `False` (raw UTF-8) | `True`                 | `kailash.delegate.*` (SPEC-09 S8.2)                 | `serde_json` default `to_string`   |
| `kailash.trust.signing.crypto.serialize_for_signing` | `True` (escaped)    | `True`                 | trust-plane signing (Ed25519/W3C-VC/multi-sig/PACT) | ASCII-escaped serde (fixture #959) |
| `pact.conformance.vectors.canonical_json_dumps`      | `False`             | `False` (struct order) | PACT conformance vectors                            | serde struct field-decl order      |

The third (pact) encoder is OUT OF SCOPE for #1258 (separate package, separate
cross-SDK contract — Rust struct field order). Cross-referenced here for
completeness; not modified.

## Brief-claim correction (per agents.md § brief verification)

The issue body claims the fixture `tests/test-vectors/trust-plane-canonical.json`
"pins `{"name":"漢字"}` → `{"name":"漢字"}`" (raw). **This is inaccurate.** The
fixture's V6 vector actually pins `{"name":"漢字"}` (ASCII-escaped),
which CORRECTLY matches `serialize_for_signing`'s `ensure_ascii=True`. Verified
empirically: `serialize_for_signing({"name":"漢字"})` →
`{"name":"漢字"}`, sha256 `0741d59c…` == fixture V6 expected_sha256.
The fixture was internally consistent all along; only the issue's prose misread
it. The real gap was (a) missing non-ASCII vectors for `canonical_json_dumps`
and (b) undocumented per-subsystem divergence.

## Decision (acceptance criterion 3: "decide whether to unify")

**DO NOT unify the two contracts.** Disposition committed (per
`value-prioritization.md` MUST-4 — no OR-escape-hatch):

1. **Document** each encoder's canonical contract in its module docstring
   (which subsystem, which `ensure_ascii`, which Rust counterpart, the
   intentional divergence, and the no-Unicode-normalization invariant).
2. **Pin** ≥3 non-ASCII byte-vectors for EACH encoder:
   - signing: extended fixture with V8 (NFC composed), V9 (NFD decomposed),
     V10 (astral-plane object key) — on top of existing V6/V7.
   - delegate: NEW fixture `tests/test-vectors/delegate-canonical.json`
     (8 vectors: ASCII, BMP, NFC, NFD, astral emoji, astral object key,
     mixed-sort non-ASCII keys, empty-dict sentinel).
3. **Do NOT unify** in kailash-py.

### Why not unify

Unification would be a **breaking cross-SDK signing-format migration**, NOT a
casual edit, and either direction _breaks_ cross-SDK parity (the opposite of
the issue's goal):

- Changing `serialize_for_signing` → `ensure_ascii=False` invalidates every
  existing trust-plane signature AND the pinned #959 fixture (vendored to
  kailash-rs), AND breaks the ~10 signing callers (chain, key_manager,
  multi_sig, timestamping, crl, rotation, w3c_vc) plus the sibling signers
  (`selective_disclosure.py`, `pact/audit.py`) that _deliberately_ chose
  `ensure_ascii=True`.
- Changing `canonical_json_dumps` → `ensure_ascii=True` breaks delegate
  cross-SDK parity with `serde_json`'s default raw-UTF-8 `to_string`.

Each encoder matches an already-shipping, byte-pinned Rust counterpart.
Unilateral change in kailash-py would desynchronize from kailash-rs. The
verification gap (the actual #1258 defect) is closed by documentation + pinned
vectors; the divergence itself is correct and intentional.

### Long-term target (if ever unified)

If a future coordinated cross-SDK migration unifies these, the target form
should be raw-UTF-8 (`serde_json` default, the idiomatic Rust form). That is a
breaking migration requiring (a) Rust-side coordination, (b) regeneration of
all existing signatures + both fixtures, (c) a deprecation/migration cycle. It
is genuinely blocked on kailash-rs coordination and is NOT this issue's scope.

## Cross-SDK follow-up (per cross-sdk-inspection.md Rule 4a)

`tests/test-vectors/delegate-canonical.json` is py-authored canonical; the
sibling kailash-rs `serde_json` delegate path MUST vendor the same file
byte-for-byte and assert reproduction. Filing the rs-side cross-issue is
gated on user approval (`upstream-issue-hygiene.md` MUST-1) AND on the
kailash-rs repo location being confirmed (see root `.session-notes` trap:
`terrene-foundation/kailash-rs` does not currently resolve on GitHub).

## Delivered (working-tree; BUILD-repo — commit gated on user)

- `src/kailash/trust/_json.py` — `canonical_json_dumps` docstring + module note.
- `src/kailash/trust/signing/crypto.py` — `serialize_for_signing` docstring.
- `tests/test-vectors/trust-plane-canonical.json` — +V8/V9/V10 + description.
- `tests/test-vectors/delegate-canonical.json` — NEW (8 vectors).
- `tests/regression/test_issue_1258_canonical_encoder_parity.py` — NEW (16 tests).
- `tests/regression/test_issue_959_trust_canonical_bytes.py` — fixed misleading
  V6 section comment ("preserved as-is (not escaped)" → "escaped to \uXXXX").
- `tests/unit/cross_sdk/test_canonical_json.py` — +2 non-ASCII unit tests.

## Verification receipts

- All vectors deterministically generated + cross-checked: existing 8 fixture
  vectors reproduce 0-mismatch; new vectors' sha256 match empirical derivation.
- `pytest tests/regression/test_issue_959_…  test_issue_1258_…  tests/unit/cross_sdk/`
  → 70 passed; `tests/unit/cross_sdk/` → 78 passed.
- `ruff check` clean; `ruff format --check` clean (4 files formatted); both
  fixtures valid JSON (11 + 8 vectors).
- pyright CLI (project venv v1.1.371) on `crypto.py`: 0 errors/warnings/info
  (the harness-LSP "unreachable" hint on the `is_dataclass` branch is a
  false positive — branch is a tested path).

## Redteam R1 receipt (2026-06-05)

Multi-agent redteam round, workflow run `wf_0ef55411-92a` (task `w6d8gr7cf`):
3 parallel agents (reviewer, security-reviewer, general-purpose verifier) +
adversarial verification of every MED+ finding.

- **Verdict: CONVERGED.** overalls = [APPROVE, APPROVE, APPROVE]; 0 findings at
  MED+; 0 confirmed-real after adversarial verification. Severity histogram:
  2 LOW, 13 INFO.
- The verifier independently re-derived every byte-vector in BOTH fixtures
  (0 mismatches), confirmed the ASCII-agree / non-ASCII-diverge contract,
  confirmed V8/V9 + D3/D4 NFC≠NFD byte-distinctness, confirmed the brief-claim
  correction (V6 is escaped, not raw), and confirmed the pact encoder
  characterization (ensure_ascii=False + sort_keys=False).
- security-reviewer confirmed: no production signing/verification logic changed
  (docstrings only); ensure_ascii=True LOAD-BEARING claim accurate; NFC/NFD
  non-normalization is correct pre-image-stability posture; no secrets; the
  do-not-unify decision preserves cross-SDK parity (no security gap).

### LOW-1 (FIXED this session)

reviewer flagged that the `canonical_json_dumps` docstring's "signing uses only
`serialize_for_signing`" over-generalized — the selective-disclosure
(`enforce/selective_disclosure.py`) and PACT-audit (`pact/audit.py`) signers
share the `ensure_ascii=True` contract via their OWN `json.dumps(..., default=str)`
call sites (no typed-scalar whitelist), so they diverge byte-for-byte from
`serialize_for_signing` on typed-scalar inputs. Reworded the docstring to state
the signing family is uniform on `ensure_ascii=True` but NOT one byte-identical
encoder. Fixed in `src/kailash/trust/_json.py` this session.

### LOW-2 → GATED FOLLOW-UP (NOT this shard; do NOT block #1258)

The verifier found a **fourth** canonical encoder surface:
`kailash_mcp.protocol.messages` exposes four `to_canonical_json` methods
(`JsonRpcError`, `JsonRpcRequest`, `JsonRpcResponse`, `McpToolInfo`), all using
`json.dumps(self.to_dict(), sort_keys=True, separators=(",",":"), ensure_ascii=False)`
and documented as "byte-identical canonical JSON ... per EATP D6" / "byte-stable
cross-SDK form" — yet with NO pinned non-ASCII byte-vectors
(`cross-sdk-inspection.md` Rule 4 gap). Same bug class as #1258, but a DISTINCT
package (kailash-mcp), DISTINCT spec surface (MCP JSON-RPC / EATP D6), DISTINCT
Rust counterpart, and 4 message-type encoders to pin. Per `autonomous-execution.md`
MUST Rule 4 (bounded by shard budget) this is a NEW shard, NOT a continuation —
filing a follow-up issue is the correct disposition.

**Recommended follow-up issue (DRAFT — filing gated on user approval per
`upstream-issue-hygiene.md` MUST-1):** "mcp: pin non-ASCII cross-SDK byte-vectors
for kailash_mcp.protocol.messages.*.to_canonical_json (EATP D6 byte-parity gap)"
— pin ≥3 non-ASCII vectors (BMP / NFC / NFD / astral) per message type against
kailash-rs serde_json output, mirroring the #1258 / #959 fixture pattern.

## Redteam R2 receipt (2026-06-05) — convergence confirmed

Focused confirming round (single reviewer agent `aee56c16e4e2d3f4b`) on the
post-R1 LOW-1 docstring reword:

- **Verdict: R2 CONVERGED — LOW-1 resolved, no new findings.**
- Reviewer confirmed the reworded "Sibling encoder" paragraph is byte-accurate
  to ground truth (signing family uniform on ensure_ascii=True but NOT one
  byte-identical encoder); grep-verified `default=str` at the sibling signing
  call sites (`selective_disclosure.py` 47/279/341/385, `pact/audit.py` 219/258)
  AND `serialize_for_signing` count = 0 in both files.
- Core delegate-vs-signing ensure_ascii contract + do-NOT-unify clause intact;
  no stub introduced.
- 127 regression + cross_sdk tests pass; `ruff check src/kailash/trust/_json.py`
  clean.

**Two consecutive clean rounds (R1 all-APPROVE/0-real, R2 LOW-1-resolved/0-new)
= CONVERGENCE.**

## User-flow walk receipt (2026-06-05)

The user-facing path for this deliverable is: a developer (or CI) runs the
test suite and reads the encoder docstrings to understand the canonical
contract. Walked:

```
$ .venv/bin/python -m pytest tests/regression/test_issue_1258_canonical_encoder_parity.py \
    tests/regression/test_issue_959_trust_canonical_bytes.py tests/unit/cross_sdk/ -q
→ 127 passed
$ .venv/bin/python -c "from kailash.trust._json import canonical_json_dumps; print(canonical_json_dumps({'name':'漢字'}))"
→ {"name":"漢字"}          # raw UTF-8 (delegate contract)
$ .venv/bin/python -c "from kailash.trust.signing.crypto import serialize_for_signing; print(serialize_for_signing({'name':'漢字'}))"
→ {"name":"漢字"}  # ASCII-escaped (signing contract)
```
Disposition: both encoders behave exactly as the (now-documented) contracts
state; divergence is visible and intentional; tests green. Deliverable walks.

## Acceptance criteria (#1258) — final status

- [x] Document each encoder's canonical contract in module docstrings — DONE
      (`_json.py` canonical_json_dumps + module note; `crypto.py` serialize_for_signing).
- [x] Pin ≥3 non-ASCII byte-vectors for EACH encoder — DONE (signing: V6/V7 +
      new V8/V9/V10 = 5 non-ASCII; delegate: D2–D7 = 6 non-ASCII). Derived from
      the canonicalization contract; rs-side live-verify is the gated cross-SDK
      follow-up (the pinned bytes ARE the contract rs must match).
- [x] Decide whether to unify — DONE (DECISION: do NOT unify; rationale above).

## For Discussion

1. (Counterfactual) If the kailash-rs repo becomes reachable, should the
   delegate `delegate-canonical.json` vendoring + the MCP `to_canonical_json`
   byte-pin follow-up be filed as ONE cross-SDK issue or two? The pact encoder
   (3rd) and MCP encoders (4th) both lack pinned non-ASCII vectors — is a single
   "audit every cross-SDK canonical encoder for byte-pins" sweep issue cleaner
   than per-encoder issues?
2. (Data-referencing) The decision rests on "each encoder matches a different
   already-shipping Rust serde contract." We verified the Python side
   empirically (0-mismatch byte-vectors) but the Rust counterparts are asserted
   from the serde contract, not run. Is the do-not-unify decision safe to hold
   WITHOUT a live kailash-rs reproduction, or does it need the rs-side vendor +
   verify before the issue is truly closed?
3. Should the long-term unification target (raw-UTF-8 / serde default) be
   captured as a tracked cross-SDK migration item now, or left dormant until a
   concrete driver (e.g. a JS consumer needing one canonical form) appears?

## CI fix (2026-06-05) — Windows UnicodeDecodeError

PR #1269's 4 windows-latest jobs failed: `test_conventions.py` (a trust
source-convention scanner) raised `UnicodeDecodeError: 'charmap' codec can't
decode byte 0x81` reading `crypto.py` with the locale codec (cp1252) on Windows.
Root cause: my crypto.py docstring embedded a raw **decomposed** é
(`e` + U+0301 = `0xCC 0x81`); `0x81` is undefined in cp1252.

Fix (this fixup commit): ASCII-ify the crypto.py NFC/NFD docstring example
(`"é"`/decomposed-`"é"` → "composed, U+00E9" / "decomposed, U+0065 U+0301") —
also a doc improvement (invisible combining chars don't belong in a docstring).
crypto.py + _json.py now carry ZERO cp1252-undefined bytes. Also hardened the
two #1258 fixture loaders to `read_text(encoding="utf-8")`.

### Follow-up (noted, not in this PR — pre-existing, out of #1258 scope)

Three trust source-convention scanners read `*.py` source with the locale codec
(no `encoding=`): `tests/trust/unit/test_conventions.py` (3 sites),
`tests/trust/unit/test_sdk_conventions.py` (4), `tests/trust/test_dependency_direction.py`
(1). A Python-source scanner MUST read UTF-8; on Windows they crash on ANY
cp1252-undefined byte in scanned source (the codebase is full of non-ASCII
docstrings). My crypto.py ASCII fix removes the immediate trigger, but the
scanner fragility is latent. Recommended follow-up: add `encoding="utf-8"` to
those source reads (also resolves pre-existing F541 lint surfaced in
test_conventions.py). Reverted from this PR to keep #1258 scoped (per
autonomous-execution Rule 4 shard-bound — separate concern, separate shard).
