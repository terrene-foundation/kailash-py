---
type: CONVERGENCE
status: converged
session: 2026-05-25 (post-merge fresh /redteam round on origin/main after v2.26.2 release)
target_ref: origin/main HEAD a14ee4ede (v2.26.2 tag)
parent_convergence: 10-cycle2-convergence.md (feat/1035-m1-m3-m4-hardening HEAD 6bb3e67b7)
merge_path: feat/1035-m1-m3-m4-hardening → PR #1170 → main → release/v2.26.2 → PR #1171 → main → tag v2.26.2 → PyPI
agent_verdicts: 3 (2 valid + 1 falsified-and-discarded)
---

# /redteam Post-Merge Convergence Receipt — issue-1035-delegate-py

**Status: CONVERGED on origin/main HEAD `a14ee4ede` (v2.26.2 tagged + live on PyPI).**

## Why this round

Cycle 2 converged on `feat/1035-m1-m3-m4-hardening` HEAD `6bb3e67b7` (R2 + R3 clean × 2, receipt at `10-cycle2-convergence.md`). After merge to main via PR #1170 and release-prep via PR #1171, the post-merge state on `origin/main` is a NEW verification surface — the cycle 2 verdict was on the feat branch, not on the merged main. This round verifies the merge did not introduce drift, the release-prep is metadata-only, and the published v2.26.2 artifact matches the converged state.

## Three parallel agent verdicts

| Agent                            | Verdict                                                            | Notes                                                                                                                                                                                                                    |
| -------------------------------- | ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| reviewer                         | **CONVERGED** — 0 C / 0 H / 0 M / 5 INFO                           | Merge-integrity CLEAN; release-prep CLEAN; mechanical sweeps CLEAN; fresh probes A1–A5 all PASS                                                                                                                          |
| pact-specialist (closure-parity) | **CONVERGED** — 8/8 VERIFIED-CLOSED                                | Verification table over all R1/R2 findings; drift-check `feat..origin/main` zero-byte; slim-core import OK; pytest collect 513 (≥512 baseline)                                                                           |
| security-reviewer                | **FALSIFIED (discarded)** — claimed NEEDS_WORK with 2 HIGH + 3 MED | Cited line numbers (trust.py:104-115 / runtime.py:1051,1278-1293 / dispatch.py:117-130) do NOT exist on origin/main; agent evidently read the F3 LEAVE ALONE working-tree drift instead of `git show origin/main:<path>` |

## Cross-agent disagreement resolution (by construction, per `rules/agents.md` § Cross-Agent CRIT/HIGH Disagreement Resolution)

Three independent reads against ground truth:

```
$ git show origin/main:src/kailash/delegate/trust.py | grep -n "_TENANT_HASH_SALT\|hmac\.new\|hashlib\."
143:_TENANT_HASH_SALT: bytes = secrets.token_bytes(32)
160:    return hmac.new(
161:        _TENANT_HASH_SALT,

$ git show origin/main:src/kailash/delegate/runtime.py | grep -n "_consume_lock"
1065:        self._consume_lock: asyncio.Lock = asyncio.Lock()
1313:        async with self._consume_lock:

$ git show origin/main:src/kailash/delegate/dispatch.py | grep -n "Mapping\|Sequence\|^.* Set"
61:from collections.abc import Awaitable, Callable, Mapping, Sequence, Set
137:    if isinstance(obj, Mapping):
140:    elif isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
143:    elif isinstance(obj, Set):
```

All three M1/M3/M4 fixes are present on origin/main at the line numbers reviewer + closure-parity cite. Security-reviewer's findings cite a DIFFERENT line layout (older state, no M1/M3/M4) — those lines match the F3 LEAVE ALONE drift, NOT origin/main. The agent's deliverable explicitly says "I have a critical disposition issue: the brief's assertions about cycle 2 fixes don't match the runtime state" — that mismatch is on the agent's read source, not on the runtime. Per `rules/verify-resource-existence.md` MUST-2 ("the verification command MUST be a live read against the same API surface the failing operation targets — NOT a grep against documentation, source comments, spec files, or the script's own intent statements"), the security-reviewer's verdict is structurally falsified.

**Net verdict: CONVERGED.** Two valid agent verdicts + direct orchestrator verification = three independent confirmations that v2.26.2 on origin/main matches cycle 2's converged state.

## Closure-parity table (from pact-specialist agent)

| Row | Finding (cycle 2 origin)                                                | Verification                                                                                                                                  |
| --- | ----------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | M1: `_consumed` TOCTOU                                                  | `runtime.py:1065` `_consume_lock: asyncio.Lock`; `runtime.py:1313-1329` `async with self._consume_lock:`; regression test exists              |
| 2   | M3: payload-depth subclass bypass                                       | `dispatch.py:61` Mapping/Sequence/Set imports; `dispatch.py:137/140/143` ABC walker with str/bytes/bytearray exclusion; 14 regression tests   |
| 3   | M4: unsalted tenant hash                                                | `trust.py:143` `_TENANT_HASH_SALT = secrets.token_bytes(32)`; `trust.py:160-161` `hmac.new(_TENANT_HASH_SALT, ...sha256)`; 7 regression tests |
| 4   | R1-MED-1: Set ABC missing from M3                                       | dispatch.py L143 `isinstance(obj, Set)` — Set walked uniformly                                                                                |
| 5   | R1-MED-2: lazy `_get_tenant_hash_salt` thread-safety                    | trust.py `grep -c "_get_tenant_hash_salt"` = 0 (helper fully removed per orphan-detection Rule 4a)                                            |
| 6   | R1-MED-3: `with_posture()` fresh lock invariant                         | `with_posture()` constructs new `DelegateRuntime` via `__init__` which allocates fresh `_consume_lock`                                        |
| 7   | R1-MED-4: `with_posture()` un-consumed reset                            | new runtime defaults `_consumed=False`; docstring "FRESH `_consumed = False`" explicit                                                        |
| 8   | R2-LOW-1+2: docstrings (M4 chroot/jail + with_posture shared-substrate) | trust.py module docstring covers chroot/jail entropy-starved edge; runtime.py covers "Shared substrate contract"                              |

## Fresh adversarial probes (reviewer A1–A5 + security-reviewer B1–B4 that DID apply)

- **A1 PASS** — DelegateRuntime has no `__repr__` / `__getstate__` / `__reduce__` / `__copy__` / `__deepcopy__`; `_consume_lock` identity is not surfaced via any serialization path; default `object.__repr__` yields memory address only
- **A2 PASS** — `_check_payload_depth` three-branch isinstance binds depth-cap to recursion level, not container shape; MappingView/proxy deception cannot evade
- **A3 PASS** — zero `==` comparison sites on `hexdigest()[:8]` output across 5 downstream consumers; all interpolate for display
- **A4 PASS** — `with_posture()` constructs via public `__init__`; freshens `_consumed`, `_consume_lock`, `_lifecycle_state`; shared substrate (signer/envelope/cascade/dispatch_surface/audit_engine/identity) is documented contract per R2.5
- **A5 PASS** — CHANGELOG [2.26.2] claims byte-for-byte match merged diff (M1 lock + M3 walker + M4 salt + 487→512+1 test count + 6 parallel agent verdicts)
- **B1 PASS** — `AuditChainEngine` uses `hmac.compare_digest` at `audit.py:594` (constant-time compare)
- **B2 PASS** — `DelegateConstraintEnvelope.to_dict()` routes through `canonical_json_dumps` at all call sites
- **B3 PASS** — `Ed25519Verifier` uses `Ed25519PublicKey.from_public_bytes` with 32-byte length pre-check; no PEM-injection surface
- **B4 PASS** — no `logger.*tenant_id` raw bleed in any delegate module; all `tenant_id` log refs route through `_tenant_id_hash` or `<global>` sentinel
- **B5 DEFER-OK** — `CascadeTenantViolationError` hashes in user-facing message but instance attributes carry raw `parent_tenant` / `child_tenant`. This is a known design choice (audit-completeness vs error-introspection-redaction trade-off); the M4 fix scope was tenant-hash-leakage in **logged messages**, not exception attributes. Not a regression from cycle 2; surfaced for future hardening if Sentry-class introspection is in threat model.

## Slim-core import surface (v2.26.0 lesson — `journal/0008`)

- `kailash.delegate.trust` module-init: `_TENANT_HASH_SALT = secrets.token_bytes(32)` (the new module-scope side effect introduced this cycle, documented in `05-codify/01-PROPOSAL-slim-core-eager-import.md`)
- All other module-scope state in `kailash.delegate.*`: zero `os.urandom`, file I/O, network calls, or extras-only imports outside of `Ed25519Verifier` which lazy-imports `cryptography` per the v2.26.1 corrective patch
- Slim-core import test (closure-parity agent): `python -c "from kailash.delegate import DelegateRuntime, TenantScopedCascade, AuditChainEngine"` succeeds WITHOUT cryptography installed — slim-core guarantee preserved

## Test count regression check

- Cycle 2 final (feat/1035-m1-m3-m4-hardening HEAD 6bb3e67b7): 512 passed + 1 skipped
- Post-merge (origin/main HEAD a14ee4ede): collect count **513** (closure-parity worktree), exit 0
- Delta accounted for by collection-set difference (closure-parity included `tests/integration/delegate/`); no regression detected

## Drift check

```
git diff origin/feat/1035-m1-m3-m4-hardening origin/main -- src/kailash/delegate/ tests/regression/test_issue_1035_delegate_*.py
```

**Output: empty.** Zero-byte diff. The merge into main is structurally identical to the converged feat branch.

## Release-prep verification (PR #1171 → commit c66329686)

- Touched files: 3 (`CHANGELOG.md`, `pyproject.toml`, `src/kailash/__init__.py`)
- Code changes: zero (metadata-only per `rules/git.md` Release-Prep PR convention)
- Version anchors:
  - `pyproject.toml::version = "2.26.2"` ✓
  - `src/kailash/__init__.py::__version__ = "2.26.2"` ✓
  - Both atomically updated per `rules/zero-tolerance.md` Rule 5
- CHANGELOG [2.26.2] entry accuracy: 100% byte-for-byte match against merged diff (per reviewer A5)

## Outstanding follow-ups (NON-blocking, all DEFER-OK)

- **B5 (CascadeTenantViolationError attribute redaction)** — known design choice; not a cycle 2 regression. Future hardening only if Sentry-class exception introspection enters threat model.
- All cycle-2 deferred follow-ups remain (F-18/F-19 conformance vectors; M5 `advance_lifecycle` orphan awaiting `Delegate.compose()`; L1/L2/L3 hardening pieces; F11 connector-ABC concrete-defaults — half delivered, design half untouched).
- The security-reviewer agent's tool-misuse pattern (read working tree instead of `git show origin/main:`) is a **process observation** for future codify — prompts that target origin/main MUST also pre-fetch the agent's WORKING DIRECTORY context (e.g., warn about F3 drift explicitly), OR have agents validate their read source with `git rev-parse HEAD` before reporting.

## Critical institutional flag

**v2.26.2 is now the resolvable latest on PyPI.** Cycle 2 work is fully landed, fully released, fully verified post-merge. No further code work needed on the #1035 substrate this session.

The v2.26.0 yank remains a maintainer-web-UI action (https://pypi.org/manage/project/kailash/release/2.26.0/) — out of scope for this autonomous round.
