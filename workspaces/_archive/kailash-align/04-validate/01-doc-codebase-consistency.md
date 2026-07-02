# Doc-Codebase Consistency Audit

**Date**: 2026-04-01
**Scope**: kailash-align, kailash-rl, kailash-ml workspaces + actual codebase
**Verdict**: 23 inconsistencies found (4 CRITICAL, 8 HIGH, 7 MEDIUM, 4 LOW)

---

## Executive Summary

The workspace documents were created during analysis (phase 01) and todos (phase 02), then the codebase was partially implemented. Several documents still reflect superseded decisions (notably the `kailash-ml[rl]` -> `kailash-rl` split). The actual code has diverged from the architecture doc in structural ways (composition vs inheritance, separate config dataclasses vs monolithic AlignmentConfig). Most inconsistencies are stale references rather than functional bugs.

---

## 1. kailash-align Workspace

### 1.1 Brief (00-overview.md) vs Actual Code

| # | Severity | Finding | Detail |
|---|----------|---------|--------|
| 1 | HIGH | **Architecture doc says `AdapterRegistry(ModelRegistry)` (inheritance)** but actual `registry.py` uses composition (HAS-A). | Architecture doc Section 2 line 96: `class AdapterRegistry(ModelRegistry)`. Actual code line 50: `class AdapterRegistry:` with `self._model_registry = model_registry`. The composition approach is correct per ALN-001, but the architecture doc was never updated. |
| 2 | HIGH | **Architecture doc pyproject.toml is wrong in multiple fields** | Doc says `version = "1.0.0"`, actual is `0.1.0`. Doc says `trl>=0.8`, actual is `trl>=0.25,<1.0`. Doc says `lm-eval>=0.4` in base deps, actual has it in `[eval]` extra. Doc says `accelerate>=0.28`, actual is `>=1.4,<2.0`. Doc says `datasets>=2.18`, actual is `>=3.0,<4.0`. |
| 3 | MEDIUM | **Architecture doc has no `[eval]` or `[serve]` extras with real deps** | Doc shows `serve = []` (empty). Actual pyproject.toml has `serve = ["llama-cpp-python>=0.3", "gguf>=0.10"]` and `eval = ["lm-eval>=0.4,<1.0"]`. The `[serve]` extra was filled during implementation (R2-01). |
| 4 | MEDIUM | **Architecture doc CLI entry point wrong** | Doc says `kailash-align-prepare = "kailash_align.cli:cli"`. Actual is `kailash-align-prepare = "kailash_align.cli:main"`. |
| 5 | MEDIUM | **Brief says `kailash-align[rlhf]` (+ QLoRA)** | This is accurate -- `[rlhf]` extra exists with `bitsandbytes>=0.43`. No inconsistency. |
| 6 | LOW | **Brief says 4 Kaizen agents** | No `agents/` directory exists under `packages/kailash-align/src/kailash_align/`. Journal 0004 records deferring agents to v1.1. Brief was not updated to reflect this deferral. |
| 7 | LOW | **Brief references "journal 0036"** for framework value-add | Only 16 journal entries exist (0001-0016). "Journal 0036" appears to be from a prior workspace iteration that was renumbered. The reference is dangling. |
| 8 | MEDIUM | **Brief says `kailash-ml[rl]` in RT2-01/RT2-02 red team findings** | These predate journal 0016 (kailash-rl decision). The brief's red team section still says "classical RL users install kailash-ml[rl]" -- should say "kailash-rl". |

### 1.2 Architecture Doc vs Actual Code

| # | Severity | Finding | Detail |
|---|----------|---------|--------|
| 9 | HIGH | **Architecture doc AlignmentConfig is a single monolithic dataclass** | Doc shows `method`, `lora_config: dict`, `training_args: dict`, `use_qlora: bool`, etc. Actual code has **4 separate frozen dataclasses**: `LoRAConfig`, `SFTConfig`, `DPOConfig`, plus mutable `AlignmentConfig` that composes them. The actual design is significantly better (validated, frozen sub-configs). |
| 10 | MEDIUM | **Architecture doc shows `AlignmentPipeline.__init__` takes `registry` + `onprem_config`** | Actual takes `config: AlignmentConfig` + `adapter_registry`. The OnPrem config is on AlignmentConfig itself (`local_files_only`, `base_model_revision`). Pipeline does not receive `OnPremConfig` directly. |
| 11 | HIGH | **Architecture doc directory layout is incomplete** | Doc lists 7 source files + agents/ directory. Actual has 13 source files: `__init__.py`, `_version.py`, `bridge.py`, `cli.py`, `config.py`, `evaluator.py`, `exceptions.py`, `merge.py`, `models.py`, `onprem.py`, `pipeline.py`, `registry.py`, `serving.py`. Missing from doc: `_version.py`, `exceptions.py`, `merge.py`, `models.py`. No `agents/` directory exists. |
| 12 | LOW | **Architecture doc AlignmentResult dataclass differs** | Doc has `adapter_version`, `experiment_id`, `checkpoint_path`, `base_model_id`. Actual has `adapter_name`, `adapter_path`, `adapter_version`, `training_metrics`, `experiment_dir`, `method`. Different field names and shapes. |

### 1.3 Cross-Workspace Synthesis (12) vs Current State

| # | Severity | Finding | Detail |
|---|----------|---------|--------|
| 13 | CRITICAL | **Synthesis doc recommends `kailash-ml[rl]` with 2-3 engines as Phase 1** | Journal 0016 superseded this with `kailash-rl` as separate package. The synthesis doc Section 2 still says "Phase 1: `kailash-ml[rl]`" and "Phase 2: Extract to `kailash-rl`". The decision was to skip Phase 1 entirely. |
| 14 | HIGH | **Synthesis doc Phase D says "kailash-ml[rl] engines"** | Should say "kailash-rl engines". All of Phase D content moved to `workspaces/kailash-rl/`. |
| 15 | MEDIUM | **Synthesis doc Section 1 says current pipeline has "hard if-elif on method name"** | This is still accurate. `pipeline.py` lines 80-96 use `if self._config.method == "sft"` / `elif ... "dpo"` / `elif ... "sft_then_dpo"`. The MethodRegistry (ALN-210) has not been implemented yet. |

### 1.4 ALN-000 Milestone Tracker vs Actual Todos

| # | Severity | Finding | Detail |
|---|----------|---------|--------|
| 16 | CRITICAL | **ALN-000 lists 23 active ALN todos (excluding M6 which moved)** | Actual `todos/active/` has 24 files (23 ALN-xxx + ALN-000 itself). Tracker lists ALN-001, ALN-100 through ALN-402, ALN-600, ALN-601. Cross-checking: all listed todos have corresponding files. No phantom todos. No missing files. Count matches: 23 todos + 1 tracker = 24 files. **Consistent.** |
| 17 | LOW | **ALN-000 cross-workspace deps reference ALN-500-503** | Line 106 says "ALN-500-503 | kailash-ml | [rl] extra in pyproject.toml". These were moved to RL-001 through RL-004. The reference is stale -- should say "Moved to RL-001-004 in workspaces/kailash-rl/". |

### 1.5 Journal Internal Consistency

| # | Severity | Finding | Detail |
|---|----------|---------|--------|
| 18 | CRITICAL | **Duplicate journal numbers: two 0003 entries and two 0004 entries** | `0003-DISCOVERY-llama-cpp-python-resolves-serving-risks.md` AND `0003-RISK-kailash-ml-dependency-ordering.md`. Same for 0004. Journal rules require sequential naming. This violates `rules/journal.md` Rule 2. |
| 19 | HIGH | **Journal 0011 recommends `kailash-ml[rl]`, journal 0016 reverses to `kailash-rl`** | The entries themselves are internally consistent -- 0016 explicitly says "Previous decision (journal 0011) reversed." However, 0011's title "classical RL in kailash-ml[rl]" is misleading without reading 0016. Per journal rules, entries are immutable, so 0011 cannot be edited. But the reversal is properly documented. **No action needed on immutable entries.** |

### 1.6 Config Validation Check

**Question**: Does config.py still validate only 3 methods?

**Answer**: Yes. `AlignmentConfig.__post_init__` line 285: `if self.method not in ("sft", "dpo", "sft_then_dpo")`. `AdapterSignature.__post_init__` line 251: same 3 methods. This is consistent with the current state -- ALN-200 (method-agnostic config) and ALN-210 (MethodRegistry) are both still pending. No inconsistency, but it confirms the pipeline is still hardcoded to SFT+DPO only.

### 1.7 Pipeline Hardcoding Check

**Question**: Is pipeline.py still hardcoded SFT+DPO?

**Answer**: Yes. `AlignmentPipeline.train()` uses if/elif/else on `self._config.method` for "sft", "dpo", "sft_then_dpo". Methods `_run_sft()` and `_run_dpo()` are the only training methods. Consistent with ALN-210 (MethodRegistry) being pending.

### 1.8 TRL Pin Check

**Question**: What is the actual TRL pin?

**Answer**: `trl>=0.25,<1.0`. ALN-000 says "Must bump pin from `>=0.25,<1.0` to `>=1.0,<2.0` for stable GRPO/RLOO API (red team C1)". The bump has NOT happened yet -- ALN-100 (package skeleton with TRL bump) is still pending. **Consistent**: the tracker correctly identifies this as a pending action.

---

## 2. kailash-rl Workspace

### 2.1 Brief (00-overview.md)

| # | Severity | Finding | Detail |
|---|----------|---------|--------|
| 20 | **OK** | **Brief correctly references kailash-ml as dependency** | "kailash-rl +-- kailash, kailash-ml +-- stable-baselines3>=2.3 +-- gymnasium>=0.29". Consistent with journal 0016 decision. |
| 21 | **OK** | **Brief correctly says `kailash-ml[rl]` becomes a redirect** | "kailash-ml[rl] extra will depend on kailash-rl as a redirect." |
| 22 | **OK** | **`packages/kailash-rl/` does NOT exist** | Expected: not implemented yet. All RL-xxx todos are pending. |

### 2.2 RL-000 Tracker vs Actual Todos

RL-000 lists: RL-100, RL-001, RL-002, RL-003, RL-004, RL-005.
Actual `todos/active/`: RL-000, RL-001, RL-002, RL-003, RL-004 (5 files).

| # | Severity | Finding | Detail |
|---|----------|---------|--------|
| 23 | HIGH | **RL-000 tracker lists RL-100 and RL-005 but no todo files exist for them** | RL-100 (Package skeleton, P0, 0.5 sessions) and RL-005 (Docs + PyPI release) are in the tracker table but have no corresponding `RL-100-*.md` or `RL-005-*.md` files in `todos/active/`. |

### 2.3 RL Todo Files: Stale `kailash-ml[rl]` References

| # | Severity | Finding | Detail |
|---|----------|---------|--------|
| 24 | CRITICAL | **RL-001 title says "kailash-ml[rl]"** | Frontmatter: `title: PolicyTrainer engine for kailash-ml[rl]`. Body says `package: kailash-rl` (correct) but title is stale. Also references `pip install kailash-ml[rl]` in docstrings and acceptance criteria. |
| 25 | HIGH | **RL-002 title says "kailash-ml[rl]"** | Same issue. Title: "EnvironmentRegistry engine for kailash-ml[rl]". Body says `package: kailash-rl` (correct). Docstrings say "Requires: pip install kailash-ml[rl]". |
| 26 | HIGH | **RL-003 title says "kailash-ml[rl]"** | Same pattern. Title: "EpisodeRecorder engine for kailash-ml[rl]". |
| 27 | HIGH | **RL-004 title says "kailash-ml[rl]"** | Title: "Integration tests for kailash-ml[rl]". All test imports reference `kailash_ml.rl` instead of `kailash_rl`. Every fixture (`from kailash_ml.rl import PolicyConfig`) and test (`from kailash_ml.rl import PolicyTrainer`) uses the old import path. |
| 28 | MEDIUM | **RL-001 through RL-003 have `milestone: M6-Classical-RL`** | This milestone was from the kailash-align workspace. The RL workspace has no M6 -- it should use its own milestone naming. |

---

## 3. kailash-ml Workspace

### 3.1 Stale `kailash-ml[rl]` References

| # | Severity | Finding | Detail |
|---|----------|---------|--------|
| 29 | MEDIUM | **kailash-ml brief (00-overview.md) references `kailash-ml[rl]` as if it still holds engines** | Lines 165, 169 reference `kailash-ml[rl]` as containing SB3+Gymnasium. Per 0016, this should be a redirect to `kailash-rl`. |
| 30 | MEDIUM | **kailash-ml implementation-plan.md Phase 5 references `kailash-ml[rl]`** | "Goal: kailash-ml[rl] works as a thin SB3/Gymnasium wrapper." Should reference `kailash-rl`. |
| 31 | MEDIUM | **kailash-ml architecture.md references `pip install kailash-ml[rl]` as ~505MB** | Should clarify this is now a redirect to `kailash-rl`. |

### 3.2 kailash-ml pyproject.toml `[rl]` Extra Status

**Question**: Does `[rl]` extra still exist? Should it redirect to kailash-rl?

**Answer**: The `[rl]` extra exists and contains:
```toml
rl = [
    "kailash-ml[dl]",
    "stable-baselines3>=2.3",
    "gymnasium>=0.29",
]
```

| # | Severity | Finding | Detail |
|---|----------|---------|--------|
| 32 | HIGH | **kailash-ml `[rl]` extra not yet updated to redirect** | Per journal 0016 implication 5: "kailash-ml `[rl]` extra becomes a redirect: `kailash-ml[rl]` depends on `kailash-rl`". Currently it still has raw SB3+gymnasium deps. Should be `rl = ["kailash-rl"]` once kailash-rl is published. This is expected since kailash-rl is not implemented yet, but the intent should be documented. |

---

## 4. Cross-Workspace Consistency

### 4.1 Journal 0011 vs 0016

| # | Severity | Finding | Detail |
|---|----------|---------|--------|
| 33 | **OK** | **0016 properly supersedes 0011** | 0016 explicitly says "Previous decision (journal 0011) reversed." 0011 recommended `kailash-ml[rl]`; 0016 reverses to `kailash-rl` as first-class package. The reversal chain is properly documented. However, downstream docs (synthesis, analysis, RL todos) have NOT been updated to reflect 0016. |

### 4.2 Synthesis Doc (12) vs Decision 0016

**Already covered in finding #13-14**: Synthesis doc still recommends `kailash-ml[rl]` as Phase 1, which was rejected by 0016.

### 4.3 Classical RL Ecosystem Doc (09) vs Decision 0016

| # | Severity | Finding | Detail |
|---|----------|---------|--------|
| 34 | MEDIUM | **Analysis doc 09 recommends `kailash-ml[rl]` for v1** | Section 4 conclusion: "`kailash-ml[rl]` for v1, with a path to `kailash-rl` if RL adoption grows." This was the pre-0016 recommendation. The doc accurately reflected the state at time of writing, but is now superseded. |

### 4.4 CLAUDE.md Platform Table

| # | Severity | Finding | Detail |
|---|----------|---------|--------|
| 35 | MEDIUM | **CLAUDE.md does not list kailash-rl** | The Kailash Platform table at the bottom of CLAUDE.md lists 7 frameworks (Core, DataFlow, Nexus, Kaizen, PACT, ML, Align). Journal 0016 says kailash-rl is the "9th Kailash framework" but CLAUDE.md was not updated. Expected: add `| **RL** | Classical reinforcement learning | pip install kailash-rl |`. |

---

## 5. Actual Codebase Check Summary

### 5.1 What Exists vs What Docs Say

| Component | Architecture Doc | Actual Code | Status |
|-----------|-----------------|-------------|--------|
| AdapterRegistry | Inherits ModelRegistry | Composition (HAS-A) | **DIVERGED** (code is better) |
| AlignmentPipeline | Monolithic AlignmentConfig | Composed config (LoRA + SFT + DPO) | **DIVERGED** (code is better) |
| AlignmentEvaluator | In base deps via lm-eval | In `[eval]` extra | **DIVERGED** (code is better) |
| AlignmentServing | Uses subprocess for GGUF | Uses llama-cpp-python (`[serve]` extra) | **DIVERGED** (code is better) |
| KaizenModelBridge | Exists | Exists (`bridge.py`) | **Consistent** |
| OnPremModelCache | Exists | Exists (`onprem.py`) | **Consistent** |
| 4 Kaizen Agents | Listed in brief | Do not exist (deferred per journal 0004) | **Documented deferral** |
| AdapterMerger | Not in architecture doc | Exists (`merge.py`) | **Code ahead of docs** |
| Exceptions module | Not in architecture doc | Exists (`exceptions.py`) | **Code ahead of docs** |
| DataFlow models | Not in architecture doc | Exists (`models.py`) | **Code ahead of docs** |
| Version module | Not in architecture doc | Exists (`_version.py`) | **Code ahead of docs** |

### 5.2 Version Consistency

| Location | Version |
|----------|---------|
| `pyproject.toml` | `0.1.0` |
| `_version.py` | `0.1.0` |
| Architecture doc | `1.0.0` |

Architecture doc is wrong. `pyproject.toml` and `_version.py` are consistent.

---

## Finding Severity Summary

| Severity | Count | Key Issues |
|----------|-------|------------|
| CRITICAL | 4 | Synthesis doc recommends superseded `kailash-ml[rl]`; duplicate journal numbers; RL todo titles say `kailash-ml[rl]`; RL-000 lists phantom todos |
| HIGH | 8 | Architecture doc wrong on inheritance/pyproject/layout; RL todo import paths wrong; kailash-ml `[rl]` redirect not done |
| MEDIUM | 7 | Config/pipeline differences; stale references in briefs and analysis docs; CLAUDE.md missing kailash-rl |
| LOW | 4 | Missing agents (documented deferral); dangling journal reference; stale ALN-500 ref; AlignmentResult shape difference |

---

## Recommended Actions

### Immediate (before next implementation session)

1. **Fix RL-001 through RL-004 titles and import paths** -- replace `kailash-ml[rl]` with `kailash-rl`, replace `kailash_ml.rl` imports with `kailash_rl`
2. **Create RL-100 and RL-005 todo files** -- tracker references them but files do not exist
3. **Fix duplicate journal numbers** -- rename `0003-RISK-kailash-ml-dependency-ordering.md` to `0017-RISK-...` and `0004-RISK-model-registry-extension-not-in-protocols.md` to `0018-RISK-...` (or use the next available numbers)
4. **Remove ALN-500-503 reference from ALN-000** cross-workspace deps table

### Before next /codify

5. **Update architecture.md** -- the codebase has evolved significantly from the architecture doc. The doc should reflect composition, separate config dataclasses, `[eval]`/`[serve]` extras, actual file layout, and version 0.1.0
6. **Update synthesis doc (12)** -- add "SUPERSEDED by journal 0016" note in Section 2, update Phase D to reference kailash-rl
7. **Update 00-overview.md** -- fix RT2-01/RT2-02 to reference kailash-rl instead of kailash-ml[rl]; note agents deferred; fix dangling journal 0036 reference

### When kailash-rl is implemented

8. **Update kailash-ml `[rl]` extra** to redirect: `rl = ["kailash-rl"]`
9. **Update CLAUDE.md** platform table to include kailash-rl
10. **Update kailash-ml workspace docs** to reflect the redirect
