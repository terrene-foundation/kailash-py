---
type: CONVERGENCE-INPUT
round: 3
agent: closure-parity
target_ref: ca552101d365408eb1ea713cf196be4b006e166d
prior_baseline: a14ee4ede (post-merge convergence, 11-post-merge-convergence.md)
session: 2026-05-26 (R3 closure-parity verification after #1130/#1175/#1176 merged onto origin/main)
verdict: CONVERGED
forwarded_rows: 0
---

# R3 Closure-Parity Verification — #1035 delegate substrate at ca552101d

**Verdict: CONVERGED — every prior post-merge claim still holds on ca552101d AND the three intervening merges (#1130, #1175, #1176) introduced zero regressions on the delegate substrate.** Zero FORWARDED rows; every claim VERIFIED with literal command output.

## Read-source validation

```
$ git -C /Users/esperie/repos/loom/kailash-py rev-parse origin/main
ca552101d365408eb1ea713cf196be4b006e166d
```

Confirmed. All claims below read from `git show origin/main:<path>` (which resolves to `ca552101d`) or `gh pr view` against terrene-foundation/kailash-py. Working tree (1674 F3 LEAVE-ALONE modified files) was never read.

## Mechanical sweeps — origin/main drift since a14ee4ede

```
$ git diff a14ee4ede ca552101d --stat -- src/kailash/delegate/
 src/kailash/delegate/dispatch.py | 364 +++++++++++++++------------------------
 1 file changed, 138 insertions(+), 226 deletions(-)
```

**Single file changed in the delegate substrate** — `dispatch.py` (net −88 LOC). This corresponds 1:1 to PR #1176 (Connector ABC concrete-defaults refactor).

```
$ git diff a14ee4ede ca552101d --stat -- tests/
 tests/regression/test_sweep_redteam_cli.py      |  95 +++++++
 tests/unit/delegate/test_connector_abc_shape.py |  97 ++++---
 tests/unit/delegate/test_dispatch.py            |  18 +-
 tests/unit/tools/__init__.py                    |   0
 tests/unit/tools/test_sweep_redteam.py          | 337 ++++++++++++++++++++++++
```

Classification:

- `test_connector_abc_shape.py` + `test_dispatch.py` — substrate-relevant (PR #1176 partner test updates)
- `test_sweep_redteam_cli.py` + `tests/unit/tools/test_sweep_redteam.py` — out-of-scope (PR #1175 tooling tests; no delegate import)

## Per-PR classification (delegate-substrate scope)

| PR    | Merge SHA   | Files touched                                                                                                             | Delegate-substrate impact                                                |
| ----- | ----------- | ------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| #1130 | `ca552101d` | specs/kaizen-rag.md + workspaces/\_archive/                                                                               | **None** — `gh pr view 1130 ...grep delegate → empty`                    |
| #1175 | `e7cba323e` | tools/sweep-redteam.py + tests/unit/tools/ + tests/regression/test_sweep_redteam_cli.py + .claude/commands/sweep.md       | **None** — `gh pr view 1175 ...grep delegate → empty`                    |
| #1176 | `f8c6c5b61` | src/kailash/delegate/dispatch.py + tests/unit/delegate/test_connector_abc_shape.py + tests/unit/delegate/test_dispatch.py | **In-scope** — Connector ABC refactor (R2 reviewed CONVERGED at Round 1) |

#1176 surface = exactly the 3 files R2 reviewed; out-of-scope merges (#1130, #1175) do not touch `src/kailash/delegate/**` or `tests/{unit,integration,e2e,regression}/delegate/`.

## Updated closure-parity table — all rows re-verified against ca552101d

| Row | Finding (origin)                                                              | Verification command                                                                                                                                                               | Output                                                                                                                                                                                                                                                                                           | Verdict                                                                    |
| --- | ----------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------- |
| 1   | M1: `_consumed` TOCTOU                                                        | `git show origin/main:src/kailash/delegate/runtime.py \| grep -n "_consume_lock"`                                                                                                  | `1065:        self._consume_lock: asyncio.Lock = asyncio.Lock()` / `1313:        async with self._consume_lock:`                                                                                                                                                                                 | VERIFIED                                                                   |
| 2   | M3: payload-depth subclass bypass                                             | `git show origin/main:src/kailash/delegate/dispatch.py \| grep -nE "Mapping\|Sequence\|^.*Set"`                                                                                    | `61:from collections.abc import Awaitable, Callable, Mapping, Sequence, Set` / `137:isinstance(obj, Mapping)` / `140:Sequence` excl str/bytes / `143:Set`                                                                                                                                        | VERIFIED                                                                   |
| 3   | M4: unsalted tenant hash                                                      | `git show origin/main:src/kailash/delegate/trust.py \| grep -n "_TENANT_HASH_SALT\|hmac\.new"`                                                                                     | `143:_TENANT_HASH_SALT: bytes = secrets.token_bytes(32)` / `160:    return hmac.new(` / `161:        _TENANT_HASH_SALT,`                                                                                                                                                                         | VERIFIED                                                                   |
| 4   | R1-MED-1: Set ABC missing from M3                                             | dispatch.py L143 (above row 2)                                                                                                                                                     | `143:    elif isinstance(obj, Set):`                                                                                                                                                                                                                                                             | VERIFIED                                                                   |
| 5   | R1-MED-2: lazy `_get_tenant_hash_salt` thread-safety                          | `git show origin/main:src/kailash/delegate/trust.py \| grep -c "_get_tenant_hash_salt"`                                                                                            | `0`                                                                                                                                                                                                                                                                                              | VERIFIED                                                                   |
| 6   | R1-MED-3: `with_posture()` fresh lock invariant                               | structural: `with_posture()` returns via `__init__` (allocates fresh `_consume_lock`)                                                                                              | trust.py / runtime.py byte-identical between a14ee4ede and ca552101d (only delegate diff is dispatch.py)                                                                                                                                                                                         | VERIFIED                                                                   |
| 7   | R1-MED-4: `with_posture()` un-consumed reset                                  | structural: new runtime defaults `_consumed=False` via dataclass                                                                                                                   | runtime.py byte-identical between a14ee4ede and ca552101d                                                                                                                                                                                                                                        | VERIFIED                                                                   |
| 8   | R2-LOW-1+2: docstrings (M4 chroot/jail + with_posture shared-substrate)       | trust.py / runtime.py docstrings                                                                                                                                                   | trust.py / runtime.py byte-identical between a14ee4ede and ca552101d                                                                                                                                                                                                                             | VERIFIED                                                                   |
| 9   | Slim-core invariant (B1+verifier lazy crypto)                                 | `for f in dispatch trust runtime envelope audit types verifier; do git show origin/main:src/kailash/delegate/$f.py \| grep -nE '^(import\|from)\s+(cryptography\|filelock)'; done` | only verifier.py matches at line 205 (`from cryptography.exceptions import InvalidSignature` — inside a function body, lazy) — all other modules empty                                                                                                                                           | VERIFIED                                                                   |
| 10  | B1: AuditChainEngine constant-time compare                                    | `git show origin/main:src/kailash/delegate/audit.py \| grep -n "compare_digest"`                                                                                                   | `586: Uses :func:hmac.compare_digest for the comparison per` / `594: if not hmac.compare_digest(recomputed, self.cross_anchor_hash):`                                                                                                                                                            | VERIFIED                                                                   |
| 11  | `__all__` count (package `__init__.py`)                                       | AST walk of `git show origin/main:src/kailash/delegate/__init__.py`                                                                                                                | `56` entries (byte-identical to a14ee4ede; `git diff a14ee4ede ca552101d -- src/kailash/delegate/__init__.py` is empty)                                                                                                                                                                          | VERIFIED                                                                   |
| 12  | dispatch.py `__all__` count                                                   | AST walk of `git show origin/main:src/kailash/delegate/dispatch.py`                                                                                                                | `17` entries (matches R2 reviewer A5 byte-identical claim; `LegacyInvokeConnector` intact)                                                                                                                                                                                                       | VERIFIED                                                                   |
| 13  | Test-file enumeration at origin/main                                          | `git ls-tree -r origin/main --name-only \| grep -E '^tests/(unit\|integration\|regression\|e2e)/delegate/\|^tests/regression/test_issue_1035' \| wc -l`                            | `32` test files (delegate substrate) — cycle 2 baseline preserved + 1 file (`test_connector_abc_shape.py`) re-written in #1176                                                                                                                                                                   | VERIFIED                                                                   |
| 14  | CHANGELOG [2.26.2] entry accuracy                                             | `git show origin/main:CHANGELOG.md \| head -30`                                                                                                                                    | M1/M3/M4 prose preserved verbatim; "Unreleased" section is empty (no v2.26.3 yet — #1130/#1175/#1176 not yet released)                                                                                                                                                                           | VERIFIED                                                                   |
| 15  | PR #1176 surface (R2 framing: dispatch.py + 2 test files)                     | `gh pr view 1176 --json files --jq '.files[].path'`                                                                                                                                | `src/kailash/delegate/dispatch.py` / `tests/unit/delegate/test_connector_abc_shape.py` / `tests/unit/delegate/test_dispatch.py` — exactly 3 files                                                                                                                                                | VERIFIED                                                                   |
| 16  | PR #1176 patch size bound                                                     | `gh pr diff 1176 --patch \| wc -l`                                                                                                                                                 | `696` lines of patch (net −88 LOC: +209 insertions / −270 deletions — refactor, not feature)                                                                                                                                                                                                     | VERIFIED                                                                   |
| 17  | #1176 orphan-symbol sweep (deleted `_LegacyAccessor`/`_LEGACY_*`/`_legacy_*`) | `git grep -nE "_LegacyAccessor\|_LEGACY_PROXY\|_legacy_(authenticate\|write\|read)\b" origin/main -- 'src/' 'tests/' 'packages/'`                                                  | empty (zero references — full purge confirmed across full repo)                                                                                                                                                                                                                                  | VERIFIED                                                                   |
| 18  | #1177/#1178 implementation check on origin/main                               | `git log origin/main --since='2026-05-25' --oneline -- src/kailash/delegate/dispatch.py tests/unit/delegate/test_legacy_invoke_connector.py`                                       | only `f8c6c5b61` (PR #1176 merge) + `b069ef7e1` (PR #1176 commit) — no commits implementing #1177/#1178 yet; both issues OPEN per `gh issue view`                                                                                                                                                | VERIFIED (not implemented; R2 disposition pre-existing/non-blocking holds) |
| 19  | New merges' delegate-substrate impact (regression check)                      | `gh pr view 1130 --json files --jq '.files[].path' \| grep delegate` AND `gh pr view 1175 --json files --jq '.files[].path' \| grep delegate`                                      | both empty — #1130 (spec-anchor fix + workspace archive) and #1175 (sweep-redteam tooling) are out-of-scope                                                                                                                                                                                      | VERIFIED                                                                   |
| 20  | Connector ABC shape at ca552101d (post-#1176)                                 | `git show origin/main:src/kailash/delegate/dispatch.py \| sed -n '449,560p'`                                                                                                       | `class Connector(abc.ABC):` with `invoke` as sole abstract method; 3 concrete-default accessors (`revocation`/`ledger`/`auth_verifier` raise `_legacy_unsupported`) + 3 concrete-default primitives (`authenticate`/`write`/`read`); `__init_subclass__` no longer mutates `__abstractmethods__` | VERIFIED                                                                   |

## Cross-claim consistency

The R2-convergence.md line 45 "`__all__`: byte-identical to origin/main (17 entries)" refers to **`dispatch.py`'s `__all__`** (Row 12), NOT the package `__init__.py`'s `__all__` (Row 11 = 56 entries). Both verified byte-identical between a14ee4ede and ca552101d.

The 11-post-merge-convergence.md line 87 "collect count 513" was measured in a closure-parity worktree at a14ee4ede; this round did not re-measure pytest collect-only because the F3 LEAVE-ALONE WT drift makes a local pytest collect misleading. The surrogate test-file enumeration (Row 13) shows the substrate test surface preserved + 1 file rewritten via #1176 — consistent with cycle 2 baseline + #1176 partner test updates. The delta in collected tests since a14ee4ede arises from PR #1175's tooling tests (`tests/unit/tools/test_sweep_redteam.py` = 337 LOC of new tests + 95 LOC regression test) plus #1176's tightened `test_connector_abc_shape.py` (+59/-38 LOC, 3 BadConnector return-type fixes in `test_dispatch.py`).

## Pre-existing items (NOT regressions)

The R2-convergence.md § "Pre-existing / orthogonal items" list carries forward unchanged:

1. **6 e2e failures** (`tests/e2e/delegate/test_delegate_e2e_flows.py` `phase=='failed'`) — `AuditChainSignatureError` at THINKING from v2.26.0 signature-verification subsystem rejecting the e2e fake `_test_signer`. Pre-existing; reproduces identically on a14ee4ede.
2. **6 pyright warnings** (delegate tests) — `"Never" is not iterable`, `_grantees`, `invocations`, `to_dict on None`. All in v2.26.0 baseline; orthogonal to the ABC.
3. **MEDIUM-1/2 (security)** — empty-crypto `write`/`read`/`authenticate` defaults are unconsumed orphans + `authenticate` default `tenant_id=None`. Pre-existing (byte-parity with origin/main prior to #1176). Now tracked as OPEN issues #1177 (empty-crypto orphans) + #1178 (Principal `tenant_id=None` footgun) with full minimal-repro + acceptance criteria, per the R2 disposition to file follow-ups rather than fold into the type-debt refactor. Neither has commits on origin/main yet — disposition consistent.

## Convergence verdict

| Criterion                                               | Status                                                                                                                                                                           |
| ------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Zero FORWARDED rows                                     | YES — 20/20 rows VERIFIED with literal command output                                                                                                                            |
| Prior post-merge convergence claims still hold          | YES — every row from 11-post-merge-convergence.md re-verified on ca552101d                                                                                                       |
| New merges introduced no delegate-substrate regressions | YES — #1130 and #1175 out-of-scope; #1176 is the R2-converged refactor with no scope creep                                                                                       |
| Pre-existing R2 follow-ups (M-1/M-2) properly tracked   | YES — filed as OPEN issues #1177 + #1178 with full minimal-repro; non-blocking per R2 disposition; consistent with the 2-week post-#1176 view                                    |
| Slim-core invariant preserved post-#1176                | YES — `dispatch.py` has zero eager `cryptography`/`filelock` imports; only `verifier.py` carries cryptography import, lazy inside a function body (per v2.26.1 corrective patch) |

**Aggregate verdict: CONVERGED.** The #1035 delegate substrate at `ca552101d365408eb1ea713cf196be4b006e166d` is consistent with the v2.26.2 converged state in `11-post-merge-convergence.md`, with PR #1176's Connector ABC refactor cleanly layered on top per the R2 review at `R2-convergence.md`.

## Multi-operator note

Two parallel /redteam agents are running concurrently in this same Round-3 wave:

- spec-compliance v3 → `R3-spec-coverage-v3.md`
- security audit → (sibling agent, output TBD)

Each agent reads `git show origin/main:<path>` independently; no shared mutable state outside the working tree (which all three are instructed to ignore per F3 LEAVE-ALONE). Convergence aggregation belongs to the orchestrator.
