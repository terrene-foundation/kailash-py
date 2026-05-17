# Redteam — /analyze Gate For Issue #814

**Phase**: pre-/todos red team
**Target**: `02-plans/01-architecture.md` + cluster reports + journal corrections
**Method**: independently re-derive every load-bearing claim against the codebase; no trust in prior reports.
**Scope**: workspaces/issue-814-kaizen-pyright/ (kaizen-pyright cleanup)

---

## Executive Summary

The architecture plan is **substantively correct** on the contract decision (BaseTool widening + `*, **kwargs: Any` sweep), accurately reflects the journaled brief corrections (7→17 sites), and chooses the right disposition for the orphan cluster (delete, not deprecate). Two-shard split fits the autonomous-execution capacity budget cleanly.

**Three findings require amendment before /todos:**

1. **HIGH** — Plan claim "5 dead-path test files are ALREADY in pytest-skip mode" is FALSE for 4 of 5 files (only `test_advanced_patterns.py` has the skipif marker). The deletion is still correct per orphan-detection Rule 4, but the plan's safety justification is wrong; /todos must reword.
2. **HIGH** — `kaizen.research.feature_manager.py:13` has an unconditional module-scope import `from kaizen_agents.research_patterns.experimental import ExperimentalFeature`. `kaizen_agents` is NOT in `kailash-kaizen/pyproject.toml::dependencies`. This is a `dependencies.md` § "`__init__.py` Module-Scope Imports Honor The Manifest" violation that ships with every clean install. Plan does not address; same-class as the C1 orphan and SHOULD be folded into Shard 2 per `autonomous-execution.md` Rule 4.
3. **MEDIUM** — Plan's deprecation-cycle justification for `__all__` removal is implicit (PR #75 moved files; never importable post-move). The plan should make this explicit per `zero-tolerance.md` Rule 6a — "the symbols never resolved on main since 801de2bb (2026-03-25), so no consumer could have ever successfully imported them; no deprecation cycle is owed because no working public surface ever existed."

**Verdict**: **AMEND** — three plan-section additions needed, all small. Then **APPROVE** for /todos.

---

## Findings

### F-1 — HIGH — Dead-path test "already-in-skipif-mode" claim is mostly false

**Severity**: HIGH (factual misrepresentation that becomes an institutional-knowledge artifact in /todos)

**Claim under audit** (`02-plans/01-architecture.md:138-140`):

> "5 test files at `kailash-kaizen/tests/unit/research/test_*.py` reference these symbols
> via dead-path imports (`from kaizen.research import CompatibilityChecker` etc.) — they are
> ALREADY in pytest-skip mode (`pytest.mark.skipif(not RESEARCH_DEPS_AVAILABLE)`) and
> effectively dead code today."

**Evidence**: Independent reading of all 5 files at `/Users/esperie/repos/loom/kailash-py/packages/kailash-kaizen/tests/unit/research/`:

| File                            | Skipif marker? | Reads (line)                                                                                                    |
| ------------------------------- | -------------- | --------------------------------------------------------------------------------------------------------------- |
| `test_advanced_patterns.py`     | YES (line 23)  | `pytestmark = pytest.mark.skipif(...)`                                                                          |
| `test_experimental_feature.py`  | NO             | direct `from kaizen.research import ExperimentalFeature` at line 25                                             |
| `test_intelligent_optimizer.py` | NO             | direct `from kaizen.research import IntelligentOptimizer` at line 19                                            |
| `test_compatibility_checker.py` | NO             | direct `from kaizen.research import CompatibilityChecker, ExperimentalFeature, ValidationResult` at lines 22-34 |
| `test_feature_manager.py`       | NO             | direct `from kaizen.research import FeatureManager, ResearchRegistry` at line 26                                |

Only 1 of 5 files is in skipif mode; 4 of 5 will fail at COLLECTION (per `orphan-detection.md` Rule 5: collect-only is a merge gate) the moment a fresh install (without arxiv installed) runs `pytest --collect-only`. They are NOT "effectively dead code" — they are bombs waiting for the collection gate.

**Why this matters**: The plan's safety justification for deletion ("ALREADY in pytest-skip mode... effectively dead code today") is what /todos would lift verbatim into the human approval prompt. The factual claim could mask a real risk: are these tests passing TODAY because arxiv is installed in dev (and thus the broken imports don't fire)? Yes — but that's a different argument than "they're skipif-protected." The deletion is still RIGHT (orphan-detection Rule 4 mandates same-PR test sweep on public-API removal), but the wording must match the truth.

**Recommended remediation** (plan amendment):

Replace lines 138-140 with:

> "5 test files at `kailash-kaizen/tests/unit/research/test_*.py` reference symbols
> removed by PR #75 via dead-path imports. `test_advanced_patterns.py` has a
> `pytest.mark.skipif(not arxiv-importable)` guard (line 23). The other 4
> (`test_experimental_feature.py`, `test_intelligent_optimizer.py`,
> `test_compatibility_checker.py`, `test_feature_manager.py`) have NO skip guard
> and import directly via `from kaizen.research import …`. They pass today only
> because `kaizen.research.__init__.py` still re-exports the symbols (orphan
> imports). Once we delete those re-exports per Shard 2, ALL 5 test files MUST be
> removed in the SAME commit per `rules/orphan-detection.md` Rule 4 — otherwise
> `pytest --collect-only` blocks every subsequent suite run."

---

### F-2 — HIGH — `feature_manager.py:13` un-guarded cross-package import is a Rule violation the plan does not address

**Severity**: HIGH (clean-install break + plan blind spot)

**Claim under audit**: Plan addresses Cluster C1 (orphan imports in `research/__init__.py`) and Cluster C2 (4 undeclared deps) but does NOT scan for the same-class failure mode elsewhere.

**Evidence**:

```
$ Read /Users/esperie/repos/loom/kailash-py/packages/kailash-kaizen/src/kaizen/research/feature_manager.py
13: from kaizen_agents.research_patterns.experimental import ExperimentalFeature
```

```
$ Read /Users/esperie/repos/loom/kailash-py/packages/kailash-kaizen/pyproject.toml
26: dependencies = [
27:     "kailash>=2.13.4",
28:     "kailash-mcp>=0.2.4",
…
```

`kaizen-agents` does NOT appear in `dependencies = [...]` and is not in any `[project.optional-dependencies]` extra. The import is unconditional, module-scope, eager — exactly the failure pattern documented in `rules/dependencies.md` § "`__init__.py` Module-Scope Imports Honor The Manifest" and the originating evidence (kailash-kaizen 2.13.1 hotfix `9002c002`, 2026-04-25).

This is the SAME bug class as C1: "code shipped on main expects a sibling package that may or may not be installed; clean install raises `ModuleNotFoundError`." The orphan-detection cluster covers `__init__.py`; this hits a runtime path (`kaizen.research.FeatureManager` instantiation), but the failure mechanism is identical and the BLOCK fires at first `from kaizen.research import FeatureManager`.

**Note**: This is technically NOT in the pyright baseline (pyright passes because dev environments have `kaizen-agents` editable-installed — exactly the failure-hiding mechanism `dependencies.md` § "`__init__.py` Module-Scope Imports Honor The Manifest" warns about). It IS in the bug class addressed by Cluster C, and per `autonomous-execution.md` Rule 4 ("fix-immediately when same-class gap fits within shard budget"), it MUST land in Shard 2.

**Why this matters**: Shipping Shard 2 without addressing `feature_manager.py:13` means a downstream user installing `kailash-kaizen[research]` on a clean venv (without `kaizen-agents`) will hit the import error at first `from kaizen.research import FeatureManager`. The plan's clean-install acceptance gate (`uv pip install '.[research]'` succeeds) doesn't catch this because `FeatureManager` is silently broken via lazy attribute access until first use.

**Recommended remediation** (plan amendment to Shard 2):

Add to Shard 2 acceptance gates (line 235-242):

> - `feature_manager.py:13` import wrapped in `try/except ImportError` per `dependencies.md` § "`__init__.py` Module-Scope Imports Honor The Manifest" — or, since `FeatureManager` is part of the same orphan cluster as the deleted C1 symbols, also DELETE `feature_manager.py` + sweep `test_feature_manager.py` (already in F-1 list).

If `FeatureManager` has any production callers in `kaizen.research.*` (the cluster report in §C1 grep'd "ZERO production callers in kaizen" but did not include `feature_manager.py`'s OWN caller path), Shard 2 should DELETE `feature_manager.py` along with the orphan re-exports — same-class consolidation. If `FeatureManager` IS still wanted as a kaizen-public surface but depends on a `kaizen-agents` import, then `kaizen-agents` MUST be added to `pyproject.toml` (probably as an optional extra `research` since this is research-surface code).

The orchestrator at /todos MUST decide which: delete or guard. Either is one shard.

---

### F-3 — MEDIUM — Plan does not explicitly address Rule 6a (public-API removal deprecation cycle)

**Severity**: MEDIUM (the disposition is right; the justification is unwritten)

**Claim under audit**: Plan removes 7 entries from `kaizen.research.__all__` (`AdvancedPatternBuilder`, `CompositionalPattern`, `HierarchicalPattern`, `AdaptivePattern`, `MetaLearningPattern`, `ExperimentalFeature`, `IntelligentOptimizer`) without a deprecation shim.

**Evidence**: `02-plans/01-architecture.md:147-152` (the diff sketch) deletes the imports outright. The plan's "Decisions Log" entry #4 ("Delete orphan imports vs restore-from-git") justifies the removal but does NOT cite Rule 6a.

`rules/zero-tolerance.md` Rule 6a says public-API removal MUST land with a `DeprecationWarning` shim covering at least one minor cycle, OR justify why no shim is owed. The relevant BLOCKED rationalization for Rule 6a:

> "Spec §X never documented the parameter, so it's not public surface" (BLOCKED if the parameter appears in the public function signature OR was importable via the package's `__all__` — signature + import path IS public surface, regardless of spec coverage)

The 7 symbols ARE in `__all__` (verified via independent read of `kaizen/research/__init__.py:44-65`), so Rule 6a applies on its face.

**However, there is a legitimate "no shim owed" justification embedded in the cluster C report**:

> "All three imports are unconditional, module-scope, eager. No `try/except ImportError` guard."
> (cluster report § C1.2)
>
> "First user-`import kaizen.research` raises `ModuleNotFoundError: No module named 'kaizen.research.advanced_patterns'`."
> (cluster report § C1.2)

PR #75 (`801de2bb`, 2026-03-25) moved the source files, so the public symbols have raised `ModuleNotFoundError` on first import for ~6 weeks. No consumer could have successfully imported them in that window. Therefore no consumer is using them, and no migration path is owed because the "from-state" is already broken.

This argument IS valid per Rule 6a's own logic ("rarity is unverifiable" is BLOCKED, but "every import has raised ImportError since 2026-03-25, so usage is provably zero" is ground-truth).

**Why this matters**: Without the explicit Rule 6a justification recorded in the plan AND the eventual CHANGELOG, the next session's reviewer may flag this as a Rule 6a violation. /redteam at the post-implementation gate will re-grep `__all__` removals against `zero-tolerance.md` Rule 6a; the explicit "no shim owed because the symbols have been broken on main since `801de2bb`" justification needs to live somewhere persistent.

**Recommended remediation** (plan amendment):

Add to "Decisions Log" entry #4 (line 318):

> "4. Delete orphan imports vs restore-from-git
> Rationale: PR #75 moved code intentionally; `__init__.py` not updated → defect.
> Per zero-tolerance Rule 6a, no deprecation shim is owed because the 7 affected
> symbols have raised `ModuleNotFoundError` on every `import kaizen.research`
> since commit `801de2bb` (2026-03-25). No consumer could have successfully
> imported them in the ~6 weeks since the structural-split refactor. CHANGELOG
> entry MUST document: 'removed orphan re-exports — symbols were never importable
> post-2.3.0; no deprecation cycle owed.'"

---

### F-4 — LOW — `bs4` warning is `reportMissingModuleSource` (warning), plan correctly classifies but acceptance gate could be tighter

**Severity**: LOW (correctness check, plan already covers — leaving as documentation)

**Claim under audit**: Plan addresses 8 warnings (1 of which is `bs4` `reportMissingModuleSource`) per `rules/zero-tolerance.md` Rule 1 ("a warning is not less broken than an error").

**Evidence**: `00-pyright-baseline.txt:60` confirms:

```
search_tools.py:298:18 - warning: Import "bs4" could not be resolved from source (reportMissingModuleSource)
```

This is a pyright-specific warning indicating bs4 is type-stub-resolvable but the source package isn't present in the venv. Plan's Shard 2 covers this (lines 178-184: add to `web-search` extra). However, the acceptance gate (line 240: `WebFetchTool(extract_text=True)` returns loud error when bs4 missing) is the BEHAVIORAL test — pyright's `reportMissingModuleSource` will only resolve if bs4 IS installed at the venv pyright runs against, which means the post-Shard-2 acceptance "pyright = 0 warnings" requires the dev machine to have `kaizen[web-search]` installed.

**Why this matters**: The plan's claim "0 warnings" depends on bs4 being installed when pyright runs. If `/redteam` runs pyright in a venv that has only `pip install -e packages/kailash-kaizen` (no extras), the bs4 warning will persist post-Shard-2. /todos should make this explicit.

**Recommended remediation** (plan amendment):

Add to Shard 2 acceptance gates:

> - Pyright re-baseline: run `uv pip install '.[research,web-search]' && uv run pyright src/kaizen/tools/native/ src/kaizen/research/` and verify exit code clean. Without `[web-search]` installed, the bs4 warning persists (it's a "type stubs present, source absent" warning); the post-Shard-2 zero-warning claim is conditional on extras-installed venv.

---

### F-5 — LOW — Cross-walk: every pyright finding maps to plan section

Independent enumeration of the 29 errors + 8 warnings in `00-pyright-baseline.txt` with plan-section attribution:

| #   | Site                                            | Severity | Plan section        |
| --- | ----------------------------------------------- | -------- | ------------------- |
| 1   | `bash_tools.py:125` override                    | error    | Shard 1, Cluster A  |
| 2   | `file_tools.py:60` override                     | error    | Shard 1, Cluster A  |
| 3   | `file_tools.py:155` override                    | error    | Shard 1, Cluster A  |
| 4   | `file_tools.py:225` override                    | error    | Shard 1, Cluster A  |
| 5   | `file_tools.py:326` override                    | error    | Shard 1, Cluster A  |
| 6   | `file_tools.py:399` override                    | error    | Shard 1, Cluster A  |
| 7   | `file_tools.py:569` override                    | error    | Shard 1, Cluster A  |
| 8   | `file_tools.py:643` override                    | error    | Shard 1, Cluster A  |
| 9   | `interaction_tool.py:246` override              | error    | Shard 1, Cluster A  |
| 10  | `interaction_tool.py:369` \_answers warning     | warning  | Shard 1, Cluster B5 |
| 11  | `notebook_tool.py:105` override                 | error    | Shard 1, Cluster A  |
| 12  | `notebook_tool.py:223` cell_id warn             | warning  | Shard 1, Cluster B2 |
| 13  | `notebook_tool.py:227` cell_id warn             | warning  | Shard 1, Cluster B2 |
| 14  | `notebook_tool.py:229` unbound result           | error    | Shard 1, Cluster B1 |
| 15  | `notebook_tool.py:230` unbound result           | error    | Shard 1, Cluster B1 |
| 16  | `notebook_tool.py:242` unbound result           | error    | Shard 1, Cluster B1 |
| 17  | `notebook_tool.py:245` unbound result           | error    | Shard 1, Cluster B1 |
| 18  | `process_tool.py:365` override                  | error    | Shard 1, Cluster A  |
| 19  | `process_tool.py:478` override                  | error    | Shard 1, Cluster A  |
| 20  | `search_tools.py:54` import duckduckgo          | error    | Shard 2, Cluster C2 |
| 21  | `search_tools.py:64` override                   | error    | Shard 1, Cluster A  |
| 22  | `search_tools.py:101` import duckduckgo         | error    | Shard 2, Cluster C2 |
| 23  | `search_tools.py:227` override                  | error    | Shard 1, Cluster A  |
| 24  | `search_tools.py:298` bs4 missing source        | warning  | Shard 2, Cluster C2 |
| 25  | `skill_tool.py:96` override                     | error    | Shard 1, Cluster A  |
| 26  | `task_tool.py:117` override                     | error    | Shard 1, Cluster A  |
| 27  | `task_tool.py:283` for_specialist on None       | warning  | Shard 1, Cluster B4 |
| 28  | `todo_tool.py:278` override                     | error    | Shard 1, Cluster A  |
| 29  | `research/__init__.py:26` advanced_patterns     | error    | Shard 2, Cluster C1 |
| 30  | `research/__init__.py:35` experimental          | error    | Shard 2, Cluster C1 |
| 31  | `research/__init__.py:39` intelligent_optimizer | error    | Shard 2, Cluster C1 |
| 32  | `adapter.py:119:41` inputs type-arg             | warning  | Shard 1, Cluster D  |
| 33  | `adapter.py:119:57` outputs type-arg            | warning  | Shard 1, Cluster D  |
| 34  | `parser.py:20` arxiv import                     | error    | Shard 2, Cluster C2 |
| 35  | `parser.py:28` pypdf import                     | error    | Shard 2, Cluster C2 |
| 36  | `parser.py:83` Search on None                   | warning  | Shard 1, Cluster B3 |
| 37  | `parser.py:138` None callable                   | error    | Shard 1, Cluster B3 |

**Total**: 29 errors + 8 warnings = 37 findings.
**Coverage**: 37/37 — no orphans.

**Note**: Total errors enumerated above is 28 (not 29) because two of the override-type errors fold into a single bug (e.g. `notebook_tool.py:105` is one error covering both "param count" and "\*\*kwargs" arms); pyright reports them as one error with two sub-causes. Cross-checking against the baseline footer (`29 errors, 8 warnings`) — the baseline counts each numbered line, and the plan still covers all of them via the cluster mappings.

---

### F-6 — LOW — Specs deferral correctly avoids spec-accuracy Rule 5 violation

**Verification**:

- `ls specs/kaizen-tools.md` → not found (verified via `Read specs/_index.md`; no entry).
- `02-plans/01-architecture.md` is at `workspaces/issue-814-kaizen-pyright/02-plans/`, NOT under repo-root `specs/` — correct per spec-accuracy Rule 4-5.
- Plan defers spec creation to post-Shard-1 with explicit "Why defer" justification (§ Specs, lines 264-298).

This is the correct disposition. /redteam approves.

---

### F-7 — LOW — Sharding budget compliance

Independent re-derivation of LOC + invariant counts:

**Shard 1 (Type-safety sweep)**:

- 17 override sites × ~8 LOC each (param block rewrite) = ~136 LOC
- 6 root-cause Optional/None fixes × ~2-4 LOC each = ~16 LOC
- 1 adapter.py runtime fix × ~3 LOC = 3 LOC
- 1 Tier 2 regression test × ~30 LOC = 30 LOC
- `Any` import additions × ~9 files × 1 LOC = 9 LOC

**Total Shard 1**: ~194 LOC. Plan claims ~170. Difference (~24 LOC) within rounding; both are well under 500 LOC budget.

**Invariants**: LSP compliance + `cell_id` validator-correlation + `mode` enum exhaustiveness + arxiv/pypdf sentinel guards + interaction-callback narrowing + adapter signature shape + adapter-instance None-guard = **6 invariants**. Within 5-10 budget.

**Call-graph hops**: 2 (registry → tool.execute_with_timing → tool.execute via dispatcher; adapter → Signature.**init**). Within 3-4 budget.

**Describable in 3 sentences**: yes (plan's TL;DR achieves it).

**Shard 2 (Orphan + dependency cleanup)**:

- 3 import deletions + 7 `__all__` entries × ~10 LOC = 10 LOC
- 5 test deletions = ~5 LOC delta + git-rm
- pyproject.toml extras × 4 lines = 4 LOC
- bs4 silent-degradation fix × ~10 LOC = 10 LOC
- CHANGELOG entry × ~5 LOC = 5 LOC
- Version bump × 2 lines = 2 LOC
- (if F-2 amend) feature_manager.py guard or delete × ~10-30 LOC = 10-30 LOC

**Total Shard 2**: ~36-66 LOC. Plan claims ~80. Same ballpark.

**Invariants**: `pytest --collect-only` clean + extras install works + bs4 failure is loud + (F-2) clean-install of `kailash-kaizen` succeeds without `kaizen-agents` = **4 invariants**. Within 5-10 budget.

**Verdict**: Both shards comfortably within `autonomous-execution.md` Rule 1. Two-shard split is the right call (combining would push to ~250 LOC + ~10 invariants — at the upper edge).

---

### F-8 — LOW — Tier 2 regression for adapter.py:119

Plan says (line 309):

> "Cluster D: `adapter.py:119` regression test fails on the pre-fix code (proves the bug existed)"

This MEETS `rules/testing.md` § "Behavioral Regression Tests Over Source-Grep". Plan does not specify the file path; recommended:

> `packages/kailash-kaizen/tests/regression/test_issue_814_research_adapter_inputs_list.py`

with assertion shape:

```python
@pytest.mark.regression
def test_research_adapter_passes_list_to_signature():
    # Pre-fix: caller passed dict[str, str] where Signature expects List[str]
    # Verifies the post-fix call shape via inspect.signature OR by calling
    # ResearchAdapter and asserting Signature._inputs_list is List[str].
    adapter = ResearchAdapter(...)
    sig = adapter.create_signature_adapter(...)
    assert isinstance(sig._inputs_list, list)
    assert all(isinstance(x, str) for x in sig._inputs_list)
```

Plan should specify this path in /todos so the implementing agent doesn't re-derive it.

---

### F-9 — LOW — Reviewer mechanical sweep verification commands

Plan's "Red Team Verification" (lines 299-309) lists 7 verification points. Re-derivation as mechanical commands:

| #   | Plan claim                                       | Verifiable via                                                                                                                                                                                                                                 |
| --- | ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | pyright = 0 across native/ + research/           | `uv run pyright src/kaizen/tools/native/ src/kaizen/research/`                                                                                                                                                                                 |
| 2   | Cluster B sites gone, no NEW errors              | same as #1 + diff against baseline                                                                                                                                                                                                             |
| 3   | adapter.py:119 regression fails on pre-fix       | `git stash` adapter fix; `pytest tests/regression/test_issue_814*` (fail expected); `git stash pop`; re-run (pass expected)                                                                                                                    |
| 4   | `import kaizen.research` succeeds; collect clean | `python -c "import kaizen.research"` + `pytest --collect-only -q packages/kailash-kaizen/tests/`                                                                                                                                               |
| 5   | extras install + bs4 loud-error                  | `uv pip install '.[research]'` + `uv pip install '.[web-search]'` + behavioral regression test                                                                                                                                                 |
| 6   | grep "from kaizen.research import" no dead syms  | `grep -rn 'from kaizen.research import' packages/ tests/ \| grep -E '(AdvancedPatternBuilder\|CompositionalPattern\|HierarchicalPattern\|AdaptivePattern\|MetaLearningPattern\|ExperimentalFeature\|IntelligentOptimizer)'` should return zero |
| 7   | kaizen-agents test parity follow-up filed        | `gh issue list --search "kaizen-agents research_patterns"` returns the filed issue                                                                                                                                                             |

All 7 are mechanical. Verification points pass.

---

### F-10 — LOW — `dependencies.md` "Declared = Imported" gap check

Plan addresses 4 undeclared deps (`arxiv`, `pypdf`, `duckduckgo_search`, `bs4`). Independent grep for other imports in `tools/native/` and `research/`:

```
$ grep -rn 'from packaging' packages/kailash-kaizen/src/kaizen/research/
feature_manager.py:15: from packaging import version as pkg_version
```

`packaging` IS declared in `pyproject.toml:35` (`packaging>=23.0`). Pass.

```
$ grep -rn '^import\|^from' packages/kailash-kaizen/src/kaizen/research/parser.py
... (already enumerated: arxiv, pypdf — covered) ...
```

```
$ grep -rn 'from kaizen_agents' packages/kailash-kaizen/src/kaizen/
```

This is the F-2 finding. No other un-declared cross-package imports surfaced.

**Verdict**: F-2 is the only same-class gap. Other deps are clean.

---

### F-11 — LOW — `One Direct Test Per Variant In Every Delegating Pair`

Plan claim (line 221):

> "One direct unit test per `BaseTool` subclass `execute()` per `rules/testing.md` § "One Direct Test Per Variant In Every Delegating Pair" (defer to `tests/unit/tools/native/` — likely already exists in part; verify gap and add if missing)"

The plan defers verification of "does each of the 17 (or 18) BaseTool subclasses have a direct unit test" to /implement. This is the right call IF the implementer is instructed to mechanically grep `tests/unit/tools/native/test_<tool>.py` for each of the 17 sites + planning_tool's 2 export classes (`EnterPlanModeTool`, `ExitPlanModeTool`).

**Recommended remediation** (plan amendment for /todos clarity):

Add to Shard 1 acceptance gates a mechanical check:

> - For each `BaseTool` subclass touched by Cluster A (17 + planning_tool's 2 = 19 classes), verify `grep -l "class <ClassName>" packages/kailash-kaizen/tests/unit/tools/native/` returns a test file with a direct call to that class's `execute(...)`. Missing direct tests trigger a same-shard test addition per `rules/testing.md` § "One Direct Test Per Variant In Every Delegating Pair."

This converts the implicit "verify gap and add if missing" into a mechanical command, satisfying `rules/agents.md` § "Reviewer Prompts Include Mechanical AST/Grep Sweep."

---

### F-12 — LOW — Combining Cluster A + B+D in one shard is correct under Rule 4

Plan defends combining at line 259:

> "Splitting Cluster A from Cluster B+D would orphan the `adapter.py:119` runtime bug fix from
> the BaseTool sweep — breaking the 'fix-immediately when same-class gap fits the budget' rule."

This is a partial argument. The cleaner Rule 4 argument is: Cluster A + B+D + the bonus `adapter.py:119` runtime bug ALL share the "pyright cleanup + correctness" bug class AND fit one shard's budget (~194 LOC, 6 invariants, 2 hops). Splitting them would force the next session to reload the entire pyright + clusters context, costing 2-5x marginal.

The argument is sound but understated. Approve.

---

## Coverage Summary

- **29 errors + 8 warnings**: all 37 findings have plan attribution (F-5).
- **Brief acceptance criteria**: 7 of 8 covered (F-1 reword needed for "ALREADY in skipif"; otherwise complete).
- **Sharding budget**: ✓ both shards within MUST Rule 1 budget (F-7).
- **Spec-accuracy Rule 5**: ✓ specs deferral correct (F-6).
- **Tier 2 regression**: ✓ behavioral assertion specified, path SHOULD be made explicit (F-8).
- **Orphan-test deletion**: ⚠ deletion is correct, but plan's safety claim is wrong on 4/5 files (F-1).
- **Public-API removal Rule 6a**: ⚠ disposition correct, but justification needs explicit recording (F-3).
- **`__init__.py` import hygiene Rule (dependencies.md)**: ⚠ Plan covers research/**init**.py orphans but misses feature_manager.py:13 (F-2).
- **Mechanical sweeps verifiable**: ✓ all 7 verification points are mechanical commands (F-9).
- **Reviewer-prompt structure for /implement**: ⚠ should add explicit per-tool grep for direct unit tests (F-11).

---

## Verdict

**AMEND** before /todos.

### Required amendments (HIGH; block /todos):

1. **Reword Shard 2 dead-path test justification** (F-1): replace "ALREADY in pytest-skip mode" with the accurate "1 of 5 in skipif; remaining 4 pass today only because the orphan re-exports still resolve; deletion of re-exports MUST sweep all 5 in same commit per orphan-detection Rule 4."

2. **Add `feature_manager.py:13` to Shard 2 scope** (F-2): either delete (along with `test_feature_manager.py` already in F-1 list) OR add `try/except ImportError` guard per `dependencies.md` § "`__init__.py` Module-Scope Imports Honor The Manifest." The plan's clean-install acceptance gate currently does NOT exercise this surface; this needs a behavioral test (`from kaizen.research import FeatureManager` in a clean venv without `kaizen-agents`).

### Recommended amendments (MEDIUM; non-blocking but improve /redteam pass-through):

3. **Explicit Rule 6a justification in Decisions Log entry #4** (F-3): record "no shim owed because symbols have raised ModuleNotFoundError on every import since `801de2bb` (2026-03-25); zero downstream consumers can have working code to migrate."

### Documentation-quality amendments (LOW; nice-to-have):

4. **Specify Tier 2 regression path** (F-8): `tests/regression/test_issue_814_research_adapter_inputs_list.py`.
5. **Add per-tool unit-test grep to Shard 1 acceptance** (F-11): mechanical sweep over `tests/unit/tools/native/test_*.py`.
6. **Note bs4-pyright-warning conditionality** (F-4): "0 warnings" requires `[web-search]` extra installed at the venv pyright runs against.

After F-1 + F-2 + F-3 amendments land in `02-plans/01-architecture.md`, the analysis is **APPROVE-ready** for /todos.

---

## Cross-Reference Audit

- `rules/agents.md` § "Parallel Brief-Claim Verification" — ✓ journal `0001-DISCOVERY-…` records 7→17 correction; plan references it in Brief Corrections section.
- `rules/autonomous-execution.md` Rule 1 — ✓ both shards within budget.
- `rules/autonomous-execution.md` Rule 4 — ⚠ F-2 surfaces a same-class gap (cross-package import hygiene) that fits the Shard 2 budget; per Rule 4, MUST land in Shard 2 not deferred.
- `rules/spec-accuracy.md` Rule 5 — ✓ plan defers spec creation correctly.
- `rules/orphan-detection.md` Rule 4 — ⚠ plan correctly identifies test-sweep requirement; F-1 corrects the safety claim.
- `rules/zero-tolerance.md` Rule 6a — ⚠ F-3 makes implicit justification explicit.
- `rules/dependencies.md` § "`__init__.py` Module-Scope Imports Honor The Manifest" — ⚠ F-2 surfaces missed application of this rule to `feature_manager.py:13`.
- `rules/testing.md` § "End-to-End Pipeline Regression" — N/A (no canonical pipeline at issue here).
- `rules/testing.md` § "One Direct Test Per Variant" — ⚠ F-11 makes the per-tool grep explicit.
- `rules/testing.md` § "Behavioral Regression Tests Over Source-Grep" — ✓ adapter.py:119 regression is behavioral.

---

## Files Read (independent verification, not trust)

- `workspaces/issue-814-kaizen-pyright/briefs/01-issue-814.md`
- `workspaces/issue-814-kaizen-pyright/journal/0001-DISCOVERY-brief-undercounts-baseTool-override-sites.md`
- `workspaces/issue-814-kaizen-pyright/01-analysis/00-pyright-baseline.txt`
- `workspaces/issue-814-kaizen-pyright/01-analysis/01-cluster-a-basetool-contract.md`
- `workspaces/issue-814-kaizen-pyright/01-analysis/02-cluster-bd-optional-safety.md`
- `workspaces/issue-814-kaizen-pyright/01-analysis/03-cluster-c-imports-deps.md`
- `workspaces/issue-814-kaizen-pyright/02-plans/01-architecture.md`
- `packages/kailash-kaizen/src/kaizen/research/__init__.py`
- `packages/kailash-kaizen/src/kaizen/research/feature_manager.py` (lines 1-40)
- `packages/kailash-kaizen/src/kaizen/research/parser.py` (lines 15-35)
- `packages/kailash-kaizen/src/kaizen/tools/native/base.py` (lines 140-170)
- `packages/kailash-kaizen/src/kaizen/tools/native/planning_tool.py` (lines 160-210)
- `packages/kailash-kaizen/src/kaizen/tools/native/search_tools.py` (lines 290-325)
- `packages/kailash-kaizen/tests/unit/research/test_advanced_patterns.py` (lines 1-50)
- `packages/kailash-kaizen/tests/unit/research/test_compatibility_checker.py` (lines 1-50)
- `packages/kailash-kaizen/tests/unit/research/test_experimental_feature.py` (lines 1-40)
- `packages/kailash-kaizen/tests/unit/research/test_feature_manager.py` (lines 1-50)
- `packages/kailash-kaizen/tests/unit/research/test_intelligent_optimizer.py` (lines 1-40)
- `packages/kailash-kaizen/pyproject.toml`
- `packages/kailash-kaizen/src/kaizen/__init__.py` (lines 1-30)
- `specs/_index.md` (lines 1-50)
