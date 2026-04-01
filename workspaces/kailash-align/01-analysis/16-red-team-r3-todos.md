# Red Team Report R3: Todo List Structural Integrity

**Scope**: All 28 todo files in `todos/active/` (ALN-000 through ALN-601)
**Date**: 2026-04-01
**Trigger**: Expanded todo list completed; structural review before `/implement`
**Severity scale**: CRITICAL (blocks implementation), HIGH (will cause production failures at runtime), MEDIUM (design flaw, fixable during implementation), LOW (improvement opportunity)

---

## 1. TRL Version Pin Contradiction (CRITICAL)

### Finding

ALN-100 (package skeleton) specifies `trl>=0.25,<1.0` in its pyproject.toml (line 83) and lists this as an acceptance criterion: "TRL pinned to `>=0.25,<1.0` (R1-08)." However:

- R1-C1 was **accepted** in `14-red-team-r1-corrections.md`: "Bump to `trl>=1.0,<2.0` for stable GRPO/RLOO API."
- ALN-000 (milestone tracker) correctly states: "Must bump pin from `>=0.25,<1.0` to `>=1.0,<2.0` for stable GRPO/RLOO API (red team C1)"
- ALN-601 (release) correctly states: "Verify `trl>=1.0,<2.0` works with all methods"
- ALN-221 references TRL's `vllm_server_url` parameter available in "TRL >=1.0"

**ALN-100's pyproject.toml and acceptance criteria still show the OLD pin.** This is a direct contradiction. If implemented as written, ALN-100 will produce a package that cannot install the stable GRPO/RLOO APIs that ALN-213 and ALN-214 depend on. The pin `<1.0` explicitly excludes the version where those APIs are stable.

### Required Action

Update ALN-100:
1. Change `trl>=0.25,<1.0` to `trl>=1.0,<2.0` in the pyproject.toml specification
2. Update the acceptance criterion from "TRL pinned to `>=0.25,<1.0`" to "TRL pinned to `>=1.0,<2.0`"
3. Update the dependency pin rationale table entry for TRL

---

## 2. Missing `[online]` Extra in ALN-100 (CRITICAL)

### Finding

R1-C4 was accepted: "Add `[online]` extra with `vllm>=0.6`." ALN-221 explicitly references adding vLLM to pyproject.toml as an `[online]` extra and specifies the exact TOML:

```toml
[project.optional-dependencies]
online = ["vllm>=0.6"]
```

ALN-100 defines 4 extras: `[rlhf]`, `[eval]`, `[serve]`, `[full]`. **There is no `[online]` extra.** The `[full]` meta-extra references `kailash-align[rlhf,eval,serve]` but not `[online]`.

If ALN-100 is implemented as written:
- ALN-221 will need to retroactively modify pyproject.toml (adding a new extra to an already-released package skeleton)
- `pip install kailash-align[online]` will fail with "unknown extra"
- The `[full]` extra will not include `[online]`

### Required Action

Update ALN-100:
1. Add `online = ["vllm>=0.6"]` to `[project.optional-dependencies]`
2. Update `[full]` to include `[online]`: `kailash-align[rlhf,eval,serve,online]`
3. Add vLLM to the dependency pin rationale table

---

## 3. ALN-202 `loss_type` Coverage Is Incomplete (HIGH)

### Finding

ALN-202's title says "DPO training + loss_type variants (IPO, SimPO, NCA, CPO, 10+ more)" and the `AlignmentConfig` code sketch in ALN-200 includes `loss_type: Optional[str] = None`. However:

- ALN-202 does **not** mention `loss_type` in its acceptance criteria
- ALN-202 does **not** mention passing `loss_type` through to `DPOConfig.to_trl_config()`
- The `DPOConfig.to_trl_config()` code sketch in ALN-200 does **not** include `loss_type` in the returned `TRLDPOConfig`

The research identified `loss_type` as a "quick win" that unlocks 14 DPO variants with zero new trainer code. But the todo that should implement it (ALN-202) never mentions the actual passthrough mechanism.

ALN-210 mentions `loss_type` passes through correctly as a unit test, but by that point the `DPOConfig.to_trl_config()` method is already implemented (in ALN-200/202) without it.

### Required Action

1. Add to ALN-200 `DPOConfig.to_trl_config()`: include `loss_type` parameter passthrough
2. Add to ALN-202 acceptance criteria: "loss_type parameter passed through to TRL DPOConfig"
3. Add to ALN-202 acceptance criteria: "Unit test: DPO with loss_type='ipo' passes through correctly"

---

## 4. ALN-221 Does Not Mention Adding vLLM to pyproject.toml (HIGH)

### Finding

ALN-221's acceptance criteria says: "`[online]` extra in pyproject.toml with `vllm>=0.6` dependency." This is correct. However, since ALN-221 depends on ALN-220 (not ALN-100), and ALN-100 does not include the `[online]` extra (Finding #2), ALN-221 must modify pyproject.toml retroactively.

This creates an ordering problem: ALN-221 is in M3 (Online RL Infrastructure), but pyproject.toml modifications belong in M0 (Foundation). If ALN-100 is implemented and released without `[online]`, adding it later may require a version bump.

### Required Action

This is resolved by fixing Finding #2 (adding `[online]` to ALN-100). If that is done, ALN-221 merely needs to verify the extra is present, not create it.

---

## 5. ALN-222 Lacks Concrete GPU Memory Numbers (HIGH)

### Finding

R1-C3 required "concrete memory estimates per method and model size." ALN-222 includes a GPU memory analysis table:

```
| Method | 3B    | 7B     | 13B    | 70B     |
|--------|-------|--------|--------|---------|
| SFT    | ~8 GB | ~16 GB | ~28 GB | ~140 GB |
```

This is present and correct. However, the acceptance criteria says "estimate_memory() returns MemoryEstimate with breakdown" but the `estimate_memory()` method body is `...` (ellipsis). The todo provides the table but does not specify the **formula** used to compute these estimates.

Without a documented formula, the implementer must either:
1. Hardcode the table values (not scalable to arbitrary model sizes)
2. Invent a formula (which may differ from the table values)

The table values appear to use the approximation: `model_params * dtype_bytes * method_multiplier`, where method multipliers are roughly SFT=1x, DPO=1.3x, GRPO=1.8x. But this is not stated.

### Required Action

Add to ALN-222:
1. Document the memory estimation formula (e.g., `model_memory = params_B * 1e9 * dtype_bytes / 1e9`)
2. Document the method multipliers used in the table
3. Specify whether the table includes optimizer states, activations, and gradient memory

---

## 6. Circular Dependency Risk in M2 (ALN-213 -> ALN-221 -> ALN-222 -> ALN-213) (HIGH)

### Finding

The milestone tracker (ALN-000) shows:

- ALN-213 (GRPO) depends on ALN-210, ALN-220
- ALN-221 (vLLM) blocks ALN-213
- ALN-222 (GPU memory) blocks ALN-213

But ALN-213's `depends_on` in its frontmatter is `[ALN-210, ALN-220]`. It does NOT list ALN-221 or ALN-222 as dependencies, even though the milestone tracker says they block ALN-213.

The milestone tracker (ALN-000) says ALN-221 and ALN-222 block ALN-213, but the individual todo files disagree:
- ALN-221 `blocks: [ALN-213]` -- correct
- ALN-222 `blocks: [ALN-213]` -- correct
- ALN-213 `depends_on: [ALN-210, ALN-220]` -- **missing ALN-221 and ALN-222**

This means an implementer reading only ALN-213 would think they can start it after ALN-210 and ALN-220 are done, without waiting for the vLLM integration or GPU memory manager. GRPO without vLLM support is functional (TRL falls back to native generation), but ALN-213's code sketch references `use_vllm` and `vllm_gpu_utilization` from ALN-221/222.

### Required Action

1. Update ALN-213 `depends_on` to `[ALN-210, ALN-220, ALN-221, ALN-222]`
2. OR: Split ALN-213 into two parts -- basic GRPO (depends on ALN-210, ALN-220) and GRPO+vLLM (depends on ALN-221, ALN-222)

---

## 7. ALN-500-503 Scope Creep: Classical RL in kailash-align Workspace (MEDIUM)

### Finding

ALN-500-503 are todos for `kailash-ml[rl]` engines (PolicyTrainer, EnvironmentRegistry, EpisodeRecorder, RL integration tests). Their frontmatter says:

```yaml
repo: kailash-py
package: kailash-ml
```

These are in the **kailash-align workspace** but target the **kailash-ml package**. This creates several problems:

1. **Wrong workspace**: The kailash-align workspace's brief, analysis, and red team reports are about LLM alignment. Classical RL engines belong in a kailash-ml workspace.
2. **No cross-workspace dependency tracking**: If kailash-ml has its own workspace with its own todos, ALN-500-503 could conflict with or duplicate work there.
3. **Release coupling**: ALN-601 says "kailash-ml: 0.1.0 -> 0.2.0 (new [rl] engines)." This couples the kailash-ml release to the kailash-align release cycle. If kailash-ml has other changes planned, this creates version coordination overhead.
4. **Test infrastructure**: ALN-503 tests require `gymnasium` and `stable-baselines3`, which are not kailash-align dependencies. The test conftest and CI configuration for kailash-align would need to handle kailash-ml[rl] dependencies.

### Assessment

The cross-workspace synthesis (doc 12) recommends `kailash-ml[rl]` as Phase D, and placing the todos here ensures they are tracked. However, the workspace boundary violation is real. The deferred items section in ALN-000 already lists items deferred to "v1.1" -- ALN-500-503 could be deferred to a dedicated kailash-ml workspace instead.

### Required Action

Either:
1. Move ALN-500-503 to a `workspaces/kailash-ml-rl/` workspace with their own brief (recommended)
2. OR: Add a clear "Cross-Workspace" section to each ALN-500-503 todo explaining why they are tracked here, and document that they modify `packages/kailash-ml/` not `packages/kailash-align/`

---

## 8. Missing Security Review Todo (MEDIUM)

### Finding

Per `rules/agents.md` Rule 2 and `rules/deployment.md` Rule 5, security review is mandatory before commits and before release. The todo list has no dedicated security review todo.

Specific security concerns in this workspace:
- **R1-C2**: Reward function arbitrary code execution (covered by ALN-220)
- **Subprocess calls**: ALN-221 (vLLM), ALN-301 (Ollama, llama.cpp) execute subprocess commands
- **Remote model loading**: `trust_remote_code=False` is specified, but no todo verifies this is enforced across all `from_pretrained()` calls
- **GGUF validation**: ALN-301 loads untrusted GGUF files via `llama_cpp.Llama()` -- a native C library
- **Network exposure**: ALN-221 VLLMManager starts an HTTP server (localhost-only by design, but should be verified)

ALN-402 (integration tests) covers functional testing but not security validation. There is no todo for:
1. Security review of all subprocess invocations
2. Input validation on all user-provided strings (model IDs, adapter names, paths)
3. Verification that `trust_remote_code=False` is consistent across all call sites
4. Threat model for GGUF file loading

### Required Action

Add a security review checkpoint. Options:
1. Add security review acceptance criteria to ALN-402
2. OR: Create ALN-403 (security review) as a gate before ALN-601 (release)

---

## 9. Missing Test Coverage for Method-Specific Config Dataclasses (MEDIUM)

### Finding

ALN-211 (KTO), ALN-212 (ORPO), ALN-213 (GRPO), ALN-214 (RLOO) each define method-specific config dataclasses (KTOConfig, ORPOConfig, GRPOConfig, RLOOConfig). These configs have numeric fields that should be validated with `math.isfinite()` per trust-plane-security rules.

However:
- ALN-211 mentions "KTOConfig field validation" in acceptance criteria but does not specify NaN/Inf testing
- ALN-212 mentions "ORPOConfig field validation" but no NaN/Inf testing
- ALN-213 mentions "GRPOConfig validation, NaN/Inf validation" -- correct
- ALN-214 mentions "RLOOConfig field validation" but no explicit NaN/Inf testing

Only ALN-213 explicitly calls out NaN/Inf validation. The others should be consistent.

### Required Action

Update ALN-211, ALN-212, ALN-214 acceptance criteria to explicitly include:
- NaN/Inf rejection on numeric fields (learning_rate, beta, temperature, etc.)
- `math.isfinite()` validation in `__post_init__`

---

## 10. Missing Method: PPO/RLHF Trainer (MEDIUM)

### Finding

The research (doc 08, doc 12) identifies PPO/RLHF as a method in the "Online RL" category. The synthesis says:

> "Online RL: GRPO, RLOO, Online DPO, **PPO/RLHF** -- PPOTrainer (experimental)"

The MethodRegistry in ALN-210 registers: SFT, DPO, KTO, ORPO, GRPO, RLOO, Online DPO. **PPO is missing from the registry.**

ALN-215 registers experimental trainers (Online DPO, XPO, NashMD, CPO, BCO) but **does not include PPO**.

The deferred items section in ALN-000 does not list PPO either -- it lists SPIN/DAPO as deferred, but PPO is neither implemented nor explicitly deferred.

PPO was the original RLHF method (Ouyang et al., 2022). While GRPO supersedes it for most use cases, PPO remains the reference implementation that many papers compare against. TRL has `PPOTrainer` and `PPOConfig`.

### Assessment

PPO may be intentionally omitted because GRPO is strictly better for the same use cases. However, this should be explicit.

### Required Action

Either:
1. Add PPO registration to ALN-215 (experimental trainers) -- it is an online method with reward functions, similar to GRPO
2. OR: Add PPO to the "Deferred to v1.1" section in ALN-000 with rationale ("GRPO supersedes PPO for all practical use cases")

---

## 11. Missing Method: SPIN Trainer (LOW)

### Finding

The synthesis lists SPIN in the "Self-play" category at P2 priority. ALN-000 defers it: "SPIN/DAPO trainers -- Custom implementation needed, TRL experimental."

However, TRL **does** have `SPINTrainer`. It is not "custom implementation needed" -- it is in TRL as an experimental trainer. ALN-215 could register it alongside XPO/NashMD. The deferred rationale is incorrect.

### Required Action

Re-evaluate SPIN:
1. If truly deferred: fix the rationale to "Low adoption, experimental" (not "custom implementation needed")
2. If included: add to ALN-215 experimental trainers (same pattern as XPO/NashMD)

---

## 12. Missing Method: RewardTrainer / PRMTrainer (LOW -- ACKNOWLEDGED)

### Finding

R1-M5 identified that RewardTrainer is needed for non-verifiable GRPO rewards. The corrections document (14) says "Move RewardTrainer to Phase B (needed for non-verifiable GRPO use cases)."

ALN-000 defers it: "Reward model training (RewardTrainer) -- Needed for non-verifiable GRPO, defer to after M2."

The R1 correction says Phase B (= M2 in the todo structure), but ALN-000 defers to AFTER M2. This is an inconsistency between the accepted correction and the implementation.

### Assessment

The pragmatic decision is reasonable: GRPO v1.0 ships with rule-based rewards (verifiable), and RewardTrainer is added later for general alignment. But it contradicts the accepted R1 correction.

### Required Action

Update ALN-000 "Deferred to v1.1" section to acknowledge the R1-M5 correction and explain the decision: "Accepted R1-M5 recommendation to promote, but deferred to v1.1 for scope control. v1.0 supports rule-based rewards only."

---

## 13. Cross-Workspace Dependencies Partially Documented (MEDIUM)

### Finding

ALN-000 has a cross-workspace dependency table:

| This Workspace | External | Dependency |
|----------------|----------|------------|
| ALN-001 | kailash-ml | ML-002 ModelRegistry API frozen |
| ALN-101 | kailash-ml | ML-201 ModelRegistry implementation |
| ALN-400 | kailash-kaizen | OllamaStreamAdapter + OpenAIStreamAdapter |
| ALN-500-503 | kailash-ml | [rl] extra in pyproject.toml |

Missing dependencies:
1. **ALN-221 -> httpx**: `_wait_for_ready()` uses `httpx.AsyncClient()`. httpx is a transitive dependency of kailash but should be listed in kailash-align's dependencies if used directly.
2. **ALN-401 -> huggingface_hub**: Uses `snapshot_download()`, `scan_cache_dir()`, `try_to_load_from_cache()`. huggingface_hub is a transitive dependency via transformers, but these are deep API usages.
3. **ALN-401 -> click**: CLI uses click for argument parsing. Not in kailash-align's pyproject.toml dependencies.

### Required Action

1. Add `click>=8.0` to kailash-align base dependencies (needed for CLI)
2. Verify `httpx` is available transitively or add explicitly
3. Verify `huggingface_hub` is available transitively (it is via `transformers`)

---

## 14. ALN-402 Has Incorrect Dependency List (MEDIUM)

### Finding

ALN-402 frontmatter: `depends_on: [ALN-300, ALN-301, ALN-400, ALN-401]`

But ALN-402 also tests method expansion features (from ALN-211-215). The milestone tracker shows ALN-211, ALN-212, ALN-213, ALN-214, ALN-215 all block ALN-402. These dependencies are correctly shown in ALN-000's milestone table but are **not reflected in ALN-402's frontmatter**.

An implementer reading ALN-402 would think they can start it after M4+M5, but it actually needs M2 (method expansion) to be complete as well.

### Required Action

Update ALN-402 `depends_on` to include `[ALN-211, ALN-212, ALN-213, ALN-214, ALN-215, ALN-300, ALN-301, ALN-400, ALN-401]`.

---

## 15. Effort Estimates Are Reasonable Under Autonomous Execution Model (VERIFIED -- NO ISSUE)

### Finding

Applying the autonomous execution model (10x multiplier, sessions not days):

| Milestone | Estimated Sessions | Assessment |
|-----------|-------------------|------------|
| M0: Foundation | 1 | Reasonable (contract + skeleton) |
| M1: Core Training | 3 | Reasonable (2 trainers + config) |
| M2: Method Expansion | 3 | Reasonable (6 trainers, registry-driven) |
| M3: Online RL Infra | 2 | Reasonable (reward + vLLM + memory) |
| M4: Eval + Serving | 2-3 | **Tight** for ALN-301 (GGUF+Ollama+vLLM = 2-3 sessions alone) |
| M5: Integration | 1-2 | Reasonable |
| M6: Classical RL | 2-3 | Reasonable |
| M7: Docs + Release | 1 | Reasonable |

**M4 is the risk area.** ALN-301 alone is estimated at 2-3 sessions (GGUF conversion, quantization, Ollama deployment, vLLM config generation, BYOG escape hatch, post-conversion validation). Combined with ALN-300 (evaluator, 1-2 sessions) and ALN-302 (merge, 0.5 sessions), M4 is 3.5-5.5 sessions. The milestone total says "2-3 sessions (parallel)" which assumes ALN-300 and ALN-301 run in parallel, but ALN-301 depends on ALN-302 which depends on ALN-201. The parallelization opportunity is limited.

### Required Action

Adjust M4 session estimate from "2-3" to "3-4" to account for ALN-301's complexity.

---

## 16. Missing: Chat/Multi-Turn Data Format Support (MEDIUM)

### Finding

R1-M1 identified chat/conversational data format as missing. The corrections document accepted this: "M1: Add chat/multi-turn data format to inventory."

No todo in the active list addresses this. The data validators in ALN-202 (DPO), ALN-211 (KTO), ALN-212 (ORPO) only handle flat text formats. TRL 1.0+ supports conversational format (`messages` with role/content dicts), and many real-world datasets use this format.

This is not a blocker for v1.0 (flat format works), but it was accepted as a correction and has no corresponding todo or deferral note.

### Required Action

Either:
1. Create ALN-203 (data format expansion) covering chat templates and multi-turn data
2. OR: Add to ALN-000 "Deferred to v1.1" with rationale

---

## 17. Missing: Multi-GPU / Distributed Training Support (LOW)

### Finding

R1-M2 identified multi-GPU/distributed training as unaddressed. The corrections accepted: "M2: Document DeepSpeed/FSDP integration via `accelerate`."

No todo addresses `accelerate` configuration. The `accelerate` library is already in the dependency list, but `AlignmentConfig` has no `accelerate_config_path` parameter.

For v1.0 (single-GPU focus), this is acceptable. But it was accepted as a correction.

### Required Action

Add to ALN-000 "Deferred to v1.1" or add an `accelerate_config_path: Optional[str] = None` field to `AlignmentConfig` in ALN-200.

---

## 18. ALN-200 Method Validation Will Break After ALN-210 (LOW)

### Finding

ALN-200's `AlignmentConfig.__post_init__` has:

```python
if self.method not in ("sft", "dpo", "sft_then_dpo"):
    raise ValueError(...)
```

With a comment: "Validate against METHOD_REGISTRY (ALN-210) instead of hardcoded tuple. For now, keep backward-compatible validation; ALN-210 will replace this."

This is correctly flagged as a transitional state. However, R1-H3 warned about this exact pattern: "Phase A expands validation without implementation, creating validation-implementation gap." The correction said: "Phase A must pair validation expansion with at least a pass-through."

The todos handle this correctly (ALN-200 keeps the restricted validation, ALN-210 replaces it), so the phasing is safe. This is a verification, not a finding.

### Status: VERIFIED -- NO ISSUE

---

## R1 Finding Coverage Matrix

All 13 R1 findings cross-referenced against todos:

| R1 ID | Severity | Finding | Covered By | Status |
|-------|----------|---------|------------|--------|
| C1 | CRITICAL | TRL version pin | ALN-000 (tracker), **NOT ALN-100** | **GAP** (Finding #1) |
| C2 | CRITICAL | Reward function security | ALN-220 (RewardRegistry) | Covered |
| C3 | HIGH | GPU memory analysis | ALN-222 (GPU memory manager) | Covered (partially -- Finding #5) |
| C4 | HIGH | vLLM missing from architecture | ALN-221 (vLLM integration) | Covered, **but missing from ALN-100** (Finding #2) |
| H1 | HIGH | MethodRegistry lazy imports | ALN-210 (lazy references) | Covered |
| H2 | HIGH | ORPO data format | ALN-212 (reuses DPO validator) | Covered |
| H3 | HIGH | Phase A validation gap | ALN-200 + ALN-210 phasing | Covered (verified) |
| M1 | MEDIUM | Chat/multi-turn data | **NO TODO** | **GAP** (Finding #16) |
| M2 | MEDIUM | Multi-GPU / distributed | **NO TODO** | **GAP** (Finding #17) |
| M3 | MEDIUM | Human-day estimates | ALN-000 (uses sessions) | Covered |
| M4 | MEDIUM | GRPO/RL boundary | ALN-500-503 scope | Documented |
| M5 | MEDIUM | RewardTrainer phasing | Deferred in ALN-000 | Inconsistent (Finding #12) |
| L1 | LOW | kailash-rs parity | Deferred in ALN-000 | Covered |

## R2 Finding Coverage Matrix

All 6 R2 findings cross-referenced against todos:

| R2 ID | Severity | Finding | Covered By | Status |
|-------|----------|---------|------------|--------|
| R2-C1 | CRITICAL | kailash-rs ML roadmap | kailash-rs workspace | N/A (different repo) |
| R2-C2 | CRITICAL | Train-in-Python framing | ALN-000 deferred section | Covered |
| R2-H1 | HIGH | py wraps / rs implements | N/A (informational) | Documented |
| R2-H2 | HIGH | kailash-align-serving brief | kailash-rs workspace | N/A (different repo) |
| R2-M1 | MEDIUM | No journal entry | Journal 0013 | Covered |
| R2-M2 | MEDIUM | Cross-SDK ML strategy | ALN-000 cross-workspace section | Covered |

---

## Summary

| ID | Severity | Finding | Action Required |
|----|----------|---------|-----------------|
| 1 | CRITICAL | ALN-100 TRL pin is `>=0.25,<1.0`, contradicts accepted R1-C1 fix (`>=1.0,<2.0`) | Update ALN-100 pyproject.toml and acceptance criteria |
| 2 | CRITICAL | ALN-100 missing `[online]` extra for vLLM, contradicts accepted R1-C4 fix | Add `[online]` extra to ALN-100 |
| 3 | HIGH | ALN-202 does not implement `loss_type` passthrough despite being titled for it | Add loss_type to DPOConfig.to_trl_config() and acceptance criteria |
| 4 | HIGH | ALN-221 vLLM pyproject.toml addition depends on ALN-100 which lacks the extra | Resolved by fixing Finding #2 |
| 5 | HIGH | ALN-222 GPU memory table present but estimation formula undocumented | Document formula and method multipliers |
| 6 | HIGH | ALN-213 `depends_on` missing ALN-221/222 (inconsistent with milestone tracker) | Update ALN-213 depends_on |
| 7 | MEDIUM | ALN-500-503 are kailash-ml todos in kailash-align workspace | Move to kailash-ml workspace or document explicitly |
| 8 | MEDIUM | No security review todo before release | Add security criteria to ALN-402 or create ALN-403 |
| 9 | MEDIUM | NaN/Inf validation inconsistent across method configs (ALN-211/212/214) | Add explicit NaN/Inf criteria |
| 10 | MEDIUM | PPO trainer missing from registry -- neither implemented nor deferred | Add to ALN-215 or defer explicitly |
| 11 | LOW | SPIN deferral rationale incorrect ("custom implementation needed" but TRL has it) | Fix rationale |
| 12 | LOW | RewardTrainer deferral contradicts accepted R1-M5 correction | Acknowledge in ALN-000 |
| 13 | MEDIUM | Missing dependencies: click for CLI, httpx verification | Add to ALN-100 dependencies |
| 14 | MEDIUM | ALN-402 `depends_on` missing ALN-211-215 | Update frontmatter |
| 15 | -- | Effort estimates verified reasonable (M4 is tight) | Adjust M4 to 3-4 sessions |
| 16 | MEDIUM | Accepted R1-M1 (chat data format) has no todo or deferral | Create todo or defer explicitly |
| 17 | LOW | Accepted R1-M2 (multi-GPU) has no todo or deferral | Defer explicitly |
| 18 | -- | ALN-200 method validation phasing verified correct | No action |

**Critical findings**: 2
**High findings**: 4
**Medium findings**: 7
**Low findings**: 4
**Verified (no issue)**: 2
**Total**: 19

---

## Convergence Criteria

Two CRITICAL findings must be fixed before `/implement` begins:

1. **Finding #1**: ALN-100 TRL pin must be updated to `>=1.0,<2.0`
2. **Finding #2**: ALN-100 must include `[online]` extra with `vllm>=0.6`

The 4 HIGH findings should also be addressed:

3. **Finding #3**: ALN-202 must pass through `loss_type`
4. **Finding #5**: ALN-222 must document estimation formula
5. **Finding #6**: ALN-213 must update `depends_on`
6. **Finding #4**: Automatically resolved by fixing Finding #2

MEDIUM findings can be addressed during implementation but should be tracked.
