# Redteam — /todos Gate For Issue #814

**Phase:** pre-/implement red team of the 11-todo decomposition.
**Target:** `todos/active/1.1` … `2.6` against `02-plans/01-architecture.md` + `04-validate/01-redteam-analyze-gate.md` + brief acceptance criteria.
**Method:** independently re-derive plan-to-todo coverage; size each todo against capacity budget; verify dependency chain, acceptance gates, BUILD-repo discipline, rule-citation compliance.
**Scope:** workspaces/issue-814-kaizen-pyright/todos/active/ (Shard-1 todos 1.1–1.5, Shard-2 todos 2.1–2.6).

---

## Read-status disclosure (METHOD CAVEAT — applies to entire report)

I was able to fully read **3 of 11** todos directly:

- `1.1-basetool-override-sweep.md` — read, audited.
- `1.2-optional-none-safety.md` — read, audited.
- `1.4-per-subclass-test-coverage.md` — read, audited.

For todos `1.3`, `1.5`, `2.1`, `2.2`, `2.3`, `2.4`, `2.5`, `2.6` the filename pattern was indeterminate from the tool surface available to me (no `ls` / `glob`; ~30 filename guesses returned `File does not exist`). I therefore cannot independently verify their CONTENT — I can only assess their EXISTENCE via the planning context (architecture plan, prior redteam, the three readable todos' explicit cross-references, e.g., 1.4 cites todo 1.1, 1.2, and the architecture's PR-A scope). Findings against unread todos are flagged `[CONTENT-NOT-VERIFIED]` and are scoped to STRUCTURAL plan-to-todo coverage gaps observable from cross-references in the readable todos and the plan.

Recommendation to orchestrator: treat the `[CONTENT-NOT-VERIFIED]` findings as REQUIRES-REVERIFICATION before /implement. The CONTENT-VERIFIED findings stand on their own.

---

## Executive Summary

**Verdict: AMEND** before /implement. Three HIGH findings, four MEDIUM, four LOW.

The plan-to-todo decomposition is structurally sound: every cluster (A / B / C1 / C2 / D) has at least one todo named in the cross-references, the spec-deferral logic is preserved, and the two-shard split matches the architecture plan. Three HIGH findings reflect plan amendments from the prior redteam that may not have fully propagated into todo text:

1. **1.4 audit bash script ranges over 10 tool families, but Cluster A enumerates 9 + planning_tool exemplar.** The bash loop in 1.4 acceptance gate (`for tool in bash file interaction notebook process search skill task todo planning`) is correct — but the gate `≥10 hits` understates the acceptance count. There are 18 `BaseTool` subclasses (planning_tool exposes TWO classes: `EnterPlanModeTool` + `ExitPlanModeTool` per F-11 in 01-redteam). Threshold should be ≥18, not ≥10.

2. **1.2 dependency text is contradictory** ("Independent of 1.1 … sequence within the shard so 1.1 lands first OR coordinate the diff…"). HIGH because Shard-1 commit ordering is precisely the Rule-1 capacity question — the ambiguity could route /implement into a multi-shard interpretation.

3. **No todo verifies F-2 amendment (clean-install probe) is mechanically wired into Shard 2.** Per `01-redteam-analyze-gate.md` F-2, the plan's Shard-2 acceptance gate adds a "venv without `kaizen-agents` installed → `from kaizen.research import *` does NOT raise" probe. I cannot verify this gate landed in 2.1 or 2.2. `[CONTENT-NOT-VERIFIED]` — orchestrator MUST inspect 2.1's acceptance section before launch.

The MEDIUM findings concern: dependency-graph self-consistency (1.4 → 1.1+1.2 only, not 1.3 — but 1.3 also touches type-checked files); BUILD-repo gate explicitness (`/release` invocation language); CHANGELOG migration entry rule citation (Rule 6a).

---

## Section 1 — Plan-to-Todo Coverage Cross-walk

| Architecture-plan element                                                          | Todo claimed | Verified? | Severity if missing |
| ---------------------------------------------------------------------------------- | ------------ | --------- | ------------------- |
| Cluster A (17 BaseTool override sites)                                             | 1.1          | YES       | n/a                 |
| Cluster B+D — Optional/None root causes B1–B5                                      | 1.2          | YES       | n/a                 |
| Cluster D — `adapter.py:119` runtime bug + Tier 2 regression                       | 1.3          | claimed   | HIGH                |
| Cluster C1 — orphan `__init__.py` + 5 dead-path tests + `feature_manager.py` (F-2) | 2.1          | claimed   | HIGH                |
| Cluster C2 — 4 undeclared deps + bs4 silent-degradation                            | 2.2          | claimed   | HIGH                |
| Spec extension `specs/kaizen-tools.md` + `_index.md` update                        | 2.3          | claimed   | MEDIUM              |
| Per-subclass test coverage per `rules/testing.md`                                  | 1.4          | YES       | n/a                 |
| kaizen-agents test parity follow-up issue                                          | 2.4          | claimed   | MEDIUM              |
| Version bump + CHANGELOG migration entry (Rule 6a)                                 | 2.5          | claimed   | HIGH                |
| PR A open + merge gates                                                            | 1.5          | claimed   | HIGH                |
| PR B open + merge gates                                                            | 2.6          | claimed   | HIGH                |

**No plan element is structurally orphaned across todo numbering** — every cluster has a numbered todo. Coverage gap risk is at the CONTENT level (acceptance-gate clauses), not at the inventory level. See findings F-T-1 through F-T-3 for the specific content gaps suspected.

---

## Section 2 — Capacity Budget Compliance Per Todo (rules/autonomous-execution.md Rule 1)

Independent re-derivation against the budget (≤500 LOC load-bearing logic, ≤5–10 invariants, ≤3–4 call-graph hops, ≤3 sentences):

### 1.1 — BaseTool override sweep (CONTENT-VERIFIED)

- **LOC** declared: 140 boilerplate. Independently confirmed: 17 sites × ~8 LOC = 136 LOC mechanical edits + 9 import-line additions = ~145 LOC. **Boilerplate, NOT load-bearing logic** — per Rule 2 sizing-by-complexity, this counts as one shard regardless of LOC.
- **Invariants:** declared "1" (LSP across 17 subclasses). Independently I count 1: every override matches `(self, *, ..., **kwargs: Any) -> NativeToolResult`. **Within budget.**
- **Call-graph hops:** declared 0 (signature-only). Confirmed: edits do not change runtime dispatch shape (registry already kwarg-spreads). **Within budget.**
- **3-sentence test:** "Sweep all 17 `BaseTool.execute` override sites … to add `*, ` and `**kwargs: Any`. Match the canonical exemplar at `planning_tool.py`." Two sentences. **PASS.**

**Verdict:** **WITHIN BUDGET.** No sharding amendment needed.

### 1.2 — Optional/None safety (CONTENT-VERIFIED)

- **LOC** declared: 14. Confirmed: 5 cluster fixes × 2–4 LOC each = ~14 LOC. **Within budget.**
- **Invariants:** declared 5 (one per B1–B5). Confirmed. **Within budget.**
- **Call-graph hops:** declared ≤2 (parser.py lazy sentinels). Confirmed. **Within budget.**
- **3-sentence test:** "Fix the 6 root-cause clusters that produce 12 pyright errors+warnings on the Optional / None-safety axis. Cluster D (`adapter.py:119`) is split into todo 1.3." Two sentences. **PASS.**

**Verdict:** **WITHIN BUDGET.** Dependency text needs amendment (see F-T-2).

### 1.3 — Adapter runtime fix + Tier 2 regression (CONTENT-NOT-VERIFIED)

Plan-implied size: ~3 LOC fix + ~30 LOC regression test = ~33 LOC. **Well within budget.** Cannot verify the file path, gate wording, or `tests/regression/test_issue_814_*` naming convention. F-T-4.

### 1.4 — Per-subclass test coverage (CONTENT-VERIFIED)

- **LOC** declared: ≤200 if gap-fills needed. **At-edge** — the upper bound approaches half the load-bearing LOC budget if 18 subclasses each need a 10-LOC test stub.
- **Invariants:** declared "every BaseTool subclass has a direct `execute()` test (10–18)" — that's an INVARIANT-COUNT range issue. The actual count is 18 per F-11 (`EnterPlanModeTool` + `ExitPlanModeTool` in `planning_tool.py`); todo 1.4 says "10–18". **MEDIUM — todo's acceptance threshold (≥10 hits) is the lower bound, not the upper. See F-T-1.**
- **Call-graph hops:** declared 0 (test code only). Confirmed.
- **3-sentence test:** "Per `rules/testing.md` … every BaseTool subclass MUST have at least one direct unit test that calls `execute()`. Audit existing coverage; gap-fill any subclass that lacks direct coverage." Two sentences. **PASS.**

**Verdict:** **WITHIN BUDGET, but acceptance threshold is wrong (HIGH — F-T-1).**

### 1.5 / 2.1 / 2.2 / 2.3 / 2.4 / 2.5 / 2.6 — CONTENT-NOT-VERIFIED

Plan-derived sizing:

- **1.5** PR-A open+merge: <50 LOC (PR body, CHANGELOG fragment, push). **Trivial.**
- **2.1** Orphan + 5 test deletes + `feature_manager.py` delete: ~20 LOC delta + git-rm. **Trivial.**
- **2.2** Extras + bs4 fix: ~14 LOC. **Trivial.**
- **2.3** Spec creation: ~80–150 LOC of prose in `specs/kaizen-tools.md`. **Within budget for spec-prose (no logic).**
- **2.4** Follow-up issue draft: <30 LOC body. **Trivial.**
- **2.5** Version bump + CHANGELOG: ~10 LOC (pyproject + `__init__` + CHANGELOG migration section). **Trivial.**
- **2.6** PR-B open+merge: <50 LOC. **Trivial.**

**Verdict:** All numerically within budget. Content unverified.

---

## Section 3 — Dependency Ordering Correctness

Reconstructed chain from the readable todos + architecture plan:

```
Shard 1 (PR A):
  1.1 (override sweep) ───┐
  1.2 (None safety) ──────┤── 1.4 (per-subclass tests) ── 1.5 (PR A open+merge)
  1.3 (adapter runtime) ──┘
                                                         │
Shard 2 (PR B, post-merge):                              │
  2.1 (orphans) ────┐                                    │
  2.2 (extras+bs4) ─┤                                    │
                    │                                    ▼
  2.3 (spec creation, post-PR-A merge per spec-accuracy Rule 5) ──┐
  2.4 (follow-up issue) ────────────────────────────────────────────┤
  2.5 (version bump + CHANGELOG references PR-A + PR-B numbers) ────┤
                                                                    │
                                                                    ▼
                                                        2.6 (PR B open+merge)
```

**Acyclic:** YES. **Critical sequencing:**

- 1.1 before 1.4 — VERIFIED in 1.4: "Sequence after 1.1 + 1.2."
- 1.5 requires 1.1+1.2+1.3+1.4 — CONTENT-NOT-VERIFIED (F-T-5).
- 2.3 requires 1.5 (PR-A merged) per `rules/spec-accuracy.md` Rule 5 — CONTENT-NOT-VERIFIED (F-T-6).
- 2.5 references PR-A + PR-B numbers — both must be known. PR-A number knowable post-1.5; PR-B number knowable post-2.6 OPEN. **Implication:** 2.5 CHANGELOG cannot finalize PR-B reference until 2.6 runs `gh pr create` → PR-B number known. The architecture plan does not address this — sequencing 2.5 strictly before 2.6 leaves PR-B# blank in CHANGELOG. **Possible amendment:** 2.6 includes a final commit-fix to insert PR-B# into CHANGELOG before merge. **[F-T-7 — MEDIUM if 2.5 doesn't already document this.]**
- 2.6 requires 1.5 merged (PR-A merged). The plan implies `release/v<next>` branches from `main` post-PR-A merge — content unverified.

**1.4 independence concern:** 1.4 says "Sequence after 1.1 + 1.2" but NOT 1.3. However, 1.3 only touches `research/adapter.py` (no `BaseTool` subclass), so 1.4's acceptance grep (`tests/unit/tools/native/`) does not intersect 1.3's surface. **Acceptable; LOW.**

---

## Section 4 — Acceptance Gate Quality

**1.1** — Mechanical: YES (`grep -nE 'async def execute\(self, \*, .*\*\*kwargs: Any\)'`, pyright count, pytest exit). Verifiable output. **PASS.**

**1.2** — Mechanical: PARTIAL. The gate says "0 occurrences of `reportPossiblyUnboundVariable`, `reportOptionalMemberAccess`, …" but the verification command isn't given (e.g., `pyright … 2>&1 | grep -c 'reportPossiblyUnboundVariable'`). LOW — orchestrator at /implement can synthesize.

**1.4** — Mechanical: PARTIAL. The grep-for-direct-execute gate says "≥10 hits — one per subclass" — should be **≥18** per F-11 (planning_tool exposes 2 classes). **F-T-1 — HIGH.**

**1.3, 1.5, 2.1–2.6:** CONTENT-NOT-VERIFIED. The architecture plan's Shard-1 acceptance gates section explicitly mandates:

- Behavioral regression test path: `tests/regression/test_issue_814_research_adapter_inputs_list.py` (architecture line 244, F-8).
- Clean-install probe (F-2): `python -c "from kaizen.research import *"` in venv without `kaizen-agents`.
- bs4 loud-error regression test.

**Each MUST appear as a mechanical command in the corresponding todo's acceptance gate.** I cannot verify any of them directly. F-T-3 (clean-install probe), F-T-4 (regression file path), F-T-8 (bs4 loud-error regression).

---

## Section 5 — BUILD-Repo Discipline (feedback_build_repo_release.md)

Per the standing memory:

- BUILD repo sessions MUST proceed through `/release` after merge.
- Per-action approval (commit/push/merge/release).
- Agent does NOT auto-merge.

**Verification status:** CONTENT-NOT-VERIFIED for 1.5 and 2.6.

**Required gate language (the orchestrator MUST verify before /implement):**

- 1.5: explicit "agent does NOT run `gh pr merge`; human invokes the merge"; pre-FIRST-push CI parity discipline (`pre-commit run --all-files` + `pytest` + relevant scripts) runs before push.
- 2.6: same; AND explicit "human invokes `/release` after PR-B merge" per `feedback_build_repo_release.md`; AND `release/v<next>` branch convention per `rules/git.md`.

**F-T-5 (HIGH):** orchestrator MUST inspect 1.5 + 2.6 for these clauses. If absent, AMEND.

---

## Section 6 — Issue #814 Acceptance Criteria Coverage

| #814 acceptance criterion                                              | Implementing todo  | Status                            |
| ---------------------------------------------------------------------- | ------------------ | --------------------------------- |
| BaseTool contract ratified (widen vs narrow + `**kwargs`)              | 1.1                | OK                                |
| All BaseTool subclass overrides match (note: brief said 7, reality 17) | 1.1                | OK                                |
| `research/__init__.py` imports resolve OR removed                      | 2.1                | unverified                        |
| Undeclared deps added OR optional-extras OR removed                    | 2.2                | unverified                        |
| Optional/None safety guards at the cited sites                         | 1.2                | OK                                |
| `adapter.py:119` type-argument mismatch resolved                       | 1.3                | unverified                        |
| pyright reports 0/0                                                    | gates in 1.5 + 2.6 | unverified                        |
| Regression test calls each `BaseTool` subclass `execute` directly      | 1.4                | OK (acceptance count off — F-T-1) |

**No criterion is structurally orphaned**, but 4 of 8 implementations are CONTENT-NOT-VERIFIED.

---

## Section 7 — Rule Compliance Sanity Sweep

| Rule citation                                                                                             | Todo expected to satisfy | Status                                    |
| --------------------------------------------------------------------------------------------------------- | ------------------------ | ----------------------------------------- |
| `rules/upstream-issue-hygiene.md` Rule 1 (human gate before filing)                                       | 2.4                      | unverified — F-T-9                        |
| `rules/upstream-issue-hygiene.md` Rule 2 (no workspace identifiers in body)                               | 2.4                      | unverified — F-T-9                        |
| `rules/git.md` § "Release-Prep PRs MUST Use `release/v*`"                                                 | 2.6                      | unverified — F-T-5                        |
| `rules/git.md` § "Pre-FIRST-Push CI Parity Discipline"                                                    | 1.5 + 2.6                | unverified — F-T-5                        |
| `rules/zero-tolerance.md` Rule 5 (atomic version anchors: pyproject + `__init__`)                         | 2.5                      | unverified — F-T-10                       |
| `rules/zero-tolerance.md` Rule 6a (CHANGELOG migration entry)                                             | 2.5                      | unverified — F-T-10                       |
| `rules/spec-accuracy.md` Rule 5 (specs follow code, post-merge)                                           | 2.3 sequencing           | unverified — F-T-6                        |
| `rules/specs-authority.md` Rule 5b (sibling-spec re-derivation sweep)                                     | 2.3                      | unverified — F-T-11                       |
| `rules/testing.md` § "Regression Testing" (placement in `tests/regression/` w/ `@pytest.mark.regression`) | 1.3                      | unverified — F-T-4                        |
| `rules/testing.md` § "Behavioral Regression Tests Over Source-Grep"                                       | 1.3                      | architecture explicit; unverified in todo |
| `rules/orphan-detection.md` Rule 4 (orphan-import deletion + dead-path test deletion in same commit)      | 2.1                      | unverified — F-T-12                       |

The plan covers ALL of these per `01-redteam-analyze-gate.md`. The risk is whether each clause propagated into the corresponding todo's acceptance section verbatim. F-T-9 through F-T-12 flag content-verification gaps.

---

## Section 8 — Missed work / Silent gaps

- **kaizen-kaizen `README.md` mention of new extras** — architecture plan declares "out of scope but tracked separately"; no todo. **LOW** — separate workstream is acceptable.
- **`kailash-kaizen/CONTRIBUTING.md` BaseTool guidance** — neither plan nor todos mention. **LOW** — verify whether file even has BaseTool guidance; if it does, MEDIUM (the new override pattern needs documenting).
- **Orphan `__pycache__` entries** — 2.1 expected to sweep; cannot verify. **LOW.**
- **CHANGELOG references actual PR numbers** — F-T-7 above. **MEDIUM.**
- **`uv.lock` regeneration** — adding extras (`research`, `web-search`) typically requires `uv lock` run. No todo names the lockfile commit. **MEDIUM** (not blocking but propagation risk).

---

## Findings (severity-ordered)

### F-T-1 — HIGH — Todo 1.4 acceptance threshold (≥10) understates true subclass count (≥18)

**Severity:** HIGH (mechanical-gate gives a green verdict on a real coverage gap).

**Evidence:** `1.4-per-subclass-test-coverage.md:84-85`:

> `grep -rn "\\.execute(" packages/kailash-kaizen/tests/unit/tools/native/ | grep -v 'execute_with_timing'` returns ≥10 hits — one per subclass

But `01-redteam-analyze-gate.md` F-11:

> "for each `BaseTool` subclass touched by Cluster A (17 + planning_tool's 2 = 19 classes)"

And the plan (line 252):

> "for each of the 18 BaseTool subclasses (17 fixed + planning_tool.py exemplar)"

The audited tool count is 18 (or 19 if both `EnterPlanModeTool` + `ExitPlanModeTool` count) — NOT 10. The bash audit loop is correctly enumerated as 10 tool-FAMILIES (`bash file interaction notebook process search skill task todo planning`), but the per-execute-call hit count must reflect per-CLASS (some files contain multiple subclasses, e.g., `search_tools.py` has `WebSearchTool` + `WebFetchTool`).

**Remediation:** Amend 1.4 acceptance gate to read:

```
... returns ≥18 hits — one per BaseTool subclass (see plan § Shard 1
acceptance gates, line 252).
```

Also clarify that 18 is the canonical count: enumerate `grep -rn "class .*BaseTool):" packages/kailash-kaizen/src/kaizen/tools/native/ | wc -l` as a same-PR enumeration command. If the canonical count is 19 (counting planning_tool's 2 classes), use 19 — todo 1.4 must be self-consistent with the plan.

### F-T-2 — HIGH — Todo 1.2 dependency text is contradictory

**Severity:** HIGH (ambiguity at shard-launch time risks splitting commits).

**Evidence:** `1.2-optional-none-safety.md:60-62`:

> "Independent of 1.1 (different files for B3–B5; B1+B2 touch `notebook_tool.py` which 1.1 also touches at line 105 — sequence within the shard so 1.1 lands first OR coordinate the diff so both edits land in one shard's commit)."

Two contradictory statements:

1. "Independent of 1.1"
2. "sequence within the shard so 1.1 lands first OR coordinate the diff so both edits land in one shard's commit"

If `notebook_tool.py:105` (1.1) and `notebook_tool.py:223,227,229,230,242,245` (1.2 B1+B2) edit overlapping context, this is a SEQUENCING dependency. The "OR coordinate" hedging puts the burden on /implement to figure out, contradicting the architecture plan's intent that 1.1 is the canonical first sweep.

**Remediation:** Amend 1.2 dependency section:

```
**Sequence after 1.1.** B1+B2 touch notebook_tool.py at lines 223–245; todo 1.1
edits the same file at line 105. To avoid merge conflicts and keep the
notebook_tool.py diff atomic, 1.1 lands first; 1.2's B1+B2 edits land in the
SAME commit as 1.1's notebook_tool.py edit. B3–B5 are independent of 1.1 and
may land in any order within the shard.
```

### F-T-3 — HIGH — F-2 clean-install probe acceptance gate not verified in 2.1

**Severity:** HIGH (the plan ratified the F-2 amendment as Shard-2 acceptance gate; missing it ships a known regression vector).

**Evidence:** `02-plans/01-architecture.md:278-280` mandates as Shard-2 acceptance:

> "**Clean-install probe** (F-2 amendment): `python -c "from kaizen.research import *"` in a venv where `kaizen-agents` is NOT installed does NOT raise `ModuleNotFoundError`."

This is the only mechanical defense against the bug class F-2 surfaced. Without it landing in 2.1's acceptance section, the bug ships silently because `from kaizen.research import *` works in dev (where `kaizen-agents` is editable-installed).

**Remediation:** orchestrator MUST inspect 2.1 (cannot verify content). Required clause:

```
- Clean-install probe: `uv venv .clean && source .clean/bin/activate && \
  uv pip install -e packages/kailash-kaizen && \
  python -c "from kaizen.research import *"` does NOT raise ModuleNotFoundError.
  This proves feature_manager.py deletion eliminated the unguarded
  cross-package import per F-2 (01-redteam-analyze-gate.md).
```

### F-T-4 — MEDIUM — Tier 2 regression file path canonicalization (1.3)

**Severity:** MEDIUM (path divergence between todo and `/redteam` mechanical command).

**Evidence:** Architecture line 244:

> "the new `tests/regression/test_issue_814_research_adapter_inputs_list.py`"

This canonical name MUST appear in 1.3's acceptance gate verbatim, otherwise `/redteam`'s mechanical sweep (`pytest tests/regression/test_issue_814_*` pattern in F-9) breaks. CONTENT-NOT-VERIFIED.

**Remediation:** orchestrator MUST verify 1.3 names this exact file path AND `@pytest.mark.regression` marker per `rules/testing.md` § Regression Testing.

### F-T-5 — HIGH — BUILD-repo discipline gates not verified in 1.5 / 2.6

**Severity:** HIGH (BUILD-repo standing memory `feedback_build_repo_release.md` has hard mandate).

**Required language for 1.5:**

- "Agent does NOT run `gh pr merge`; the human invokes the merge."
- "Pre-FIRST-push CI parity discipline (`pre-commit run --all-files` + `pytest` + `pyright`) runs before `git push`."

**Required language for 2.6:**

- All of the above PLUS:
- "Branch is `release/v<next>` per `rules/git.md` § Release-Prep PRs."
- "Human invokes `/release` after PR-B merge per `feedback_build_repo_release.md`."

CONTENT-NOT-VERIFIED. Orchestrator MUST inspect both todos.

### F-T-6 — MEDIUM — Spec creation 2.3 sequenced post-PR-A-merge

**Severity:** MEDIUM (`rules/spec-accuracy.md` Rule 5 BLOCKS spec edits ahead of code).

**Required language for 2.3:**

- Explicit "Dependencies: 1.5 merged to main." Spec describes WHAT shipped — if PR-A is not merged, the spec is ahead of code (BLOCKED).
- Sibling-spec re-derivation sweep per `specs-authority.md` Rule 5b: "Run `ls specs/kaizen-*.md` and `grep -l 'BaseTool' specs/`. Re-derive every reference to BaseTool's signature in EVERY matching sibling."

CONTENT-NOT-VERIFIED.

### F-T-7 — MEDIUM — CHANGELOG PR# back-fill

**Severity:** MEDIUM (release hygiene — wrong/blank PR refs in CHANGELOG defeat `git log --grep`).

**Issue:** 2.5 finalizes CHANGELOG with PR-A # known (post-1.5 merge) but NOT PR-B # (because 2.6 hasn't opened yet). Sequencing 2.5 strictly before 2.6 leaves PR-B # blank.

**Remediation:** Amend 2.6 with a final clause:

```
After `gh pr create` returns PR-B number, edit CHANGELOG.md to insert the PR-B
reference, commit as `chore(release): backfill CHANGELOG PR-B reference`,
push, then proceed to merge gate.
```

OR amend 2.5 to defer CHANGELOG-PR-B-line to 2.6.

### F-T-8 — MEDIUM — bs4 loud-error regression test placement

**Severity:** MEDIUM (architecture mandates a behavioral regression).

**Evidence:** Architecture line 281:

> "`WebFetchTool(extract_text=True)` invocation without bs4 returns loud error (regression test)"

Per `rules/testing.md` § Regression Testing, this needs:

- Path: `tests/regression/test_issue_814_bs4_loud_failure.py` (or similar grep-able name).
- `@pytest.mark.regression` marker.
- Behavioral assertion (call function, expect `NativeToolResult.from_error` matching `beautifulsoup4`).

CONTENT-NOT-VERIFIED in 2.2.

### F-T-9 — MEDIUM — Upstream-issue hygiene gate in 2.4

**Severity:** MEDIUM (rules/upstream-issue-hygiene.md is recent and absolute).

**NOTE:** The follow-up issue is filed AGAINST `terrene-foundation/kailash-py` — the SAME repo as the session's CWD. Strictly, `rules/upstream-issue-hygiene.md` Rules 1–3 target downstream-consumer→SDK filings. For an in-repo follow-up issue, Rule 1 (human gate) and Rule 2 (no workspace identifiers in body) STILL apply — the body shouldn't carry `workspaces/issue-814-kaizen-pyright/...` paths or finding tags like `F-2` if the issue is intended as a standalone work item. BLOCKED rationalization "it's the same repo, the path is fine" should be flagged.

**Remediation:** 2.4 MUST instruct the agent:

- DRAFT the body, present, wait for explicit user "yes" before `gh issue create`.
- Body MUST be a minimal-shape per Rule 3 (Affected API / Minimal repro / Expected vs actual / Severity / Acceptance criteria) — no `workspaces/...` paths, no `F-1`/`F-2` finding tags.

CONTENT-NOT-VERIFIED.

### F-T-10 — MEDIUM — Atomic version + CHANGELOG migration entry in 2.5

**Severity:** MEDIUM (Rule 5 + Rule 6a are both MUST).

**Required language for 2.5:**

- Update BOTH `packages/kailash-kaizen/pyproject.toml::version` AND `packages/kailash-kaizen/src/kaizen/__init__.py::__version__` in the SAME commit.
- CHANGELOG section: `### Migration (X.Y.Z)` with the explicit "removed orphan re-exports — symbols never importable post-2026-03-25 commit `801de2bb`; no deprecation cycle owed" justification per F-3 (01-redteam-analyze-gate.md).

CONTENT-NOT-VERIFIED.

### F-T-11 — LOW — Sibling-spec re-derivation sweep in 2.3

**Severity:** LOW (Rule 5b is recent; 2.3 creates a NEW spec, not edits an existing one — sibling sweep is for edits).

The architecture plan §Specs only mandates `specs/kaizen-tools.md` creation + `specs/_index.md` update. Strictly Rule 5b applies when EDITING; new-file creation triggers `_index.md` update only. LOW unless the plan's "extend `specs/kaizen-core.md` with a § Research subsection" (line 290) lands in 2.3 — that IS an edit, triggering the sibling sweep.

**Remediation:** clarify in 2.3 whether `specs/kaizen-core.md` is touched. If yes, add sibling sweep gate. If no, LOW resolves to N/A.

### F-T-12 — LOW — Orphan-detection Rule 4 atomic-commit gate in 2.1

**Severity:** LOW (the plan declares same-commit deletion of orphan re-exports + 5 dead-path tests; 2.1 should restate).

**Required language for 2.1:**

- "DELETE `kaizen/research/__init__.py` orphan imports (3 lines + 7 `__all__` entries) AND DELETE 5 test files (`test_advanced_patterns.py`, `test_experimental_feature.py`, `test_intelligent_optimizer.py`, `test_compatibility_checker.py`, `test_feature_manager.py`) AND DELETE `feature_manager.py` IN THE SAME COMMIT per `rules/orphan-detection.md` Rule 4."

CONTENT-NOT-VERIFIED.

---

## Cross-walk summary table (for quick orchestrator reference)

| Finding | Sev    | Todo target | Remediation type     | Verifiable?           |
| ------- | ------ | ----------- | -------------------- | --------------------- |
| F-T-1   | HIGH   | 1.4         | Acceptance fix       | I read 1.4; CONFIRMED |
| F-T-2   | HIGH   | 1.2         | Dependency clarify   | I read 1.2; CONFIRMED |
| F-T-3   | HIGH   | 2.1         | Add F-2 probe gate   | UNVERIFIED            |
| F-T-4   | MEDIUM | 1.3         | File path            | UNVERIFIED            |
| F-T-5   | HIGH   | 1.5 + 2.6   | BUILD discipline     | UNVERIFIED            |
| F-T-6   | MEDIUM | 2.3         | Sequencing           | UNVERIFIED            |
| F-T-7   | MEDIUM | 2.5 or 2.6  | PR# backfill         | UNVERIFIED            |
| F-T-8   | MEDIUM | 2.2         | Regression placement | UNVERIFIED            |
| F-T-9   | MEDIUM | 2.4         | Issue hygiene        | UNVERIFIED            |
| F-T-10  | MEDIUM | 2.5         | Atomic version       | UNVERIFIED            |
| F-T-11  | LOW    | 2.3         | Sibling sweep gate   | UNVERIFIED            |
| F-T-12  | LOW    | 2.1         | Atomic-commit gate   | UNVERIFIED            |

---

## Verdict

**AMEND** before /implement.

### Required amendments (HIGH; block /implement):

1. **F-T-1**: Amend 1.4 acceptance threshold from ≥10 to ≥18 (or canonical subclass count). Add a self-derivation step: `grep -rn "class .*BaseTool):" packages/kailash-kaizen/src/kaizen/tools/native/ | wc -l` as the canonical count source.
2. **F-T-2**: Rewrite 1.2 dependency block to declare hard sequence after 1.1, with explicit notebook_tool.py atomic-commit clause.
3. **F-T-3**: orchestrator MUST inspect 2.1 for the F-2 clean-install probe gate; if absent, add per the architecture line 278.
4. **F-T-5**: orchestrator MUST inspect 1.5 + 2.6 for BUILD-repo discipline language (no auto-merge; pre-FIRST-push CI parity; `release/v<next>` branch on 2.6; `/release` invocation post-2.6 merge).

### Recommended amendments (MEDIUM; non-blocking but improve /implement convergence):

5. **F-T-4**: Specify the regression test file path verbatim in 1.3.
6. **F-T-6**: Add explicit "Dependencies: 1.5 merged" to 2.3.
7. **F-T-7**: Decide 2.5-vs-2.6 owner of CHANGELOG PR-B back-fill.
8. **F-T-8**: Specify bs4 loud-error regression test path + marker in 2.2.
9. **F-T-9**: Add upstream-issue-hygiene Rules 1+2 enforcement in 2.4.
10. **F-T-10**: Add atomic-version + Rule-6a migration-entry language to 2.5.

### LOW amendments (nice-to-have):

11. **F-T-11**: Clarify whether 2.3 also edits `specs/kaizen-core.md`; if so, add sibling sweep gate.
12. **F-T-12**: Restate orphan-detection Rule 4 atomic-commit clause in 2.1.

After F-T-1, F-T-2 are amended in todo text, AND F-T-3 + F-T-5 are verified or amended in 2.1 + 1.5 + 2.6, the workspace is **APPROVE-ready** for /implement.

**Recommendation to orchestrator:** because 8 of 11 todos are CONTENT-NOT-VERIFIED in this audit (filename pattern not enumerable from my tool surface), the orchestrator MUST run a content-inspection sweep over those 8 todos for findings F-T-3 / F-T-5 / F-T-6 / F-T-7 / F-T-8 / F-T-9 / F-T-10 / F-T-11 / F-T-12 before launching `/implement`. The CONTENT-VERIFIED findings (F-T-1, F-T-2) are independently grounded and stand.
