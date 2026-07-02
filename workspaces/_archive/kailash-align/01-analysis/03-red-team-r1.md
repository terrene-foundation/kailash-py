# Red Team Round 1: kailash-align

## Methodology

This red team assessment examines the kailash-align analysis across 11 dimensions identified during the analyze phase. Each finding is rated by severity (CRITICAL, HIGH, MEDIUM, LOW) and includes a concrete recommendation. Source materials: 7 research files, the value proposition analysis, and the overview brief.

---

## RT1-01: ~2.5 GB Install -- Is This a Dealbreaker?

**Severity**: LOW
**Verdict**: Not a dealbreaker. Expected for the target audience.

**Analysis**: The ~2.5 GB is dominated by PyTorch (~1.5-2.0 GB). Every LLM fine-tuning tool (Axolotl, Unsloth, LLaMA-Factory) has the same baseline. The critical mitigation is already in place: kailash-align is a separate package from kailash-ml. Users who only need tabular ML pay 195 MB, not 2.5 GB.

The realistic scenario is more favorable than the headline number. If kailash-ml[dl] is already installed (users doing deep learning work), the incremental cost of kailash-align is only ~100-200 MB (trl + peft + accelerate + lm-eval + datasets). Users downloading an 8-30 GB base model are not bothered by a 2.5 GB toolchain.

**Remaining concern**: The `lm-eval` dependency should be made optional (`[eval]` extra) since users who only train + deploy do not need benchmarking tools. This saves 30-50 MB and avoids lm-eval's transitive dependencies.

**Recommendation**: Move `lm-eval` to `[eval]` optional extra. Document incremental size clearly in README ("If you already have kailash-ml[dl] installed, kailash-align adds ~150 MB").

---

## RT1-02: GGUF Conversion Reliability -- Will Users Hit Errors Constantly?

**Severity**: HIGH
**Verdict**: This is the highest-risk technical component in kailash-align.

**Analysis**: Based on research (see `01-research/03-serving-infrastructure-analysis.md`), GGUF conversion reliability is rated MEDIUM, and the failure modes are pernicious:

1. **Silent malformed GGUF**: `convert_hf_to_gguf.py` can produce a valid-looking file that crashes or generates garbage at inference time. No error during conversion. This is the most dangerous failure mode because users blame kailash-align, not the conversion tool.
2. **Architecture-specific failures**: The conversion script has a hardcoded list of supported architectures. New model architectures require llama.cpp updates that may lag weeks or months behind HuggingFace releases.
3. **Tokenizer mismatch**: Some tokenizers do not roundtrip correctly through GGUF format. The user sees garbled output with no clear error message.
4. **External binary dependency**: `llama-quantize` is a compiled C++ binary that must be built or obtained separately. This is a friction point that will generate support requests from users unfamiliar with C++ build toolchains.

**The failure scenario**: A user spends hours training a model, runs `align.deploy(model, target="ollama")`, gets a silently broken GGUF file that produces garbled output, and blames kailash-align.

**Recommendation**:

- Implement a post-conversion validation step: load the GGUF via a short inference test (5-10 tokens) and compare against the original model's output for the same prompt. If outputs diverge significantly, warn the user.
- Provide a "bring your own GGUF" escape hatch (already planned). Make it prominent in docs and error messages.
- Restrict v1 to an explicitly tested architecture allowlist (Llama 3, Mistral, Phi-3, Qwen 2.5). Other architectures get a warning, not a hard block.
- Always produce F16 GGUF first, then quantize as a separate step. Never skip the F16 intermediate.
- Pin the llama.cpp / `gguf` package version to a known-working release.

---

## RT1-03: kailash-ml Dependency -- Ordering Risk

**Severity**: CRITICAL
**Verdict**: This is the hardest blocker. Must be explicitly sequenced.

**Analysis**: kailash-align depends on kailash-ml for `ModelRegistry` (which `AdapterRegistry` extends). kailash-ml does not exist yet. The dependency chain is:

```
kailash-align -> kailash-ml (for ModelRegistry)
                 kailash-ml does not exist yet
```

This creates a hard ordering constraint: kailash-ml must ship (at least the ModelRegistry component) before kailash-align can begin implementing its highest-value component (AdapterRegistry). The 7-12 session estimate for kailash-align does not include the effort to build kailash-ml. If kailash-ml takes 5-8 sessions of its own, the total calendar time doubles.

**Specific risks**:

1. **API instability**: kailash-ml's ModelRegistry is being designed now. Its API may change during implementation, breaking AdapterRegistry's contract.
2. **DataFlow model dependency**: AdapterRegistry extends ModelRegistry's DataFlow models. If those models change shape, AdapterRegistry's storage breaks.
3. **Timeline coupling**: Any delay in kailash-ml directly delays kailash-align Phase 1.

**Recommendation**:

- Make the ordering explicit: kailash-ml is a prerequisite, not a parallel workstream.
- Define the minimum viable ModelRegistry interface NOW, before either package starts implementation. Freeze the extension points that AdapterRegistry depends on.
- Consider shipping a kailash-ml v0.1 with just ModelRegistry + basic model versioning, then expanding it later. This unblocks kailash-align sooner.
- Alternatively, define an AdapterRegistry interface that can start with a standalone implementation, then refactor to extend ModelRegistry once kailash-ml ships. This decouples the timelines but adds refactoring cost.
- The total effort estimate must account for kailash-ml work separately.

---

## RT1-04: 7-12 Session Estimate -- Is This Realistic?

**Severity**: HIGH
**Verdict**: The estimate is optimistic by 2-4 sessions.

**Analysis**: Decomposing against the actual components:

| Component                  | Estimated Sessions | Rationale                                                        |
| -------------------------- | ------------------ | ---------------------------------------------------------------- |
| AdapterRegistry (WS-A1)    | 1-2                | Extends ModelRegistry, DataFlow models, CRUD. Medium complexity. |
| AlignmentPipeline (WS-A2)  | 1-2                | Thin TRL wrapper. SFT + DPO orchestration.                       |
| AlignmentEvaluator (WS-A3) | 1                  | lm-eval wrapper + DataFlow storage.                              |
| AlignmentServing (WS-A4)   | 2-3                | GGUF conversion, Ollama deployment, vLLM config. Highest risk.   |
| KaizenModelBridge (WS-A5)  | 0.5-1              | 150-250 lines. Existing adapters work.                           |
| OnPremModelCache (WS-A6)   | 0.5-1              | Thin HuggingFace wrapper + CLI.                                  |
| 4 Kaizen agents            | 1-2                | If kept in v1.                                                   |
| Package scaffolding        | 0.5-1              | pyproject.toml, package structure, conftest, CI.                 |
| Testing (all tiers)        | 2-3                | Integration tests require GPU. E2E requires Ollama.              |
| Documentation + README     | 0.5-1              | API docs, user guide, examples.                                  |
| **Total**                  | **9.5-16**         |                                                                  |

The estimate of 7-12 is optimistic by 2-4 sessions. The GGUF conversion validation and TRL version compatibility testing are the most likely sources of slippage. Testing overhead is consistently underestimated: Tier 2/3 tests with real GPU hardware and running Ollama are slow and require manual environment setup.

Additionally, this estimate excludes kailash-ml (see RT1-03). The combined kailash-ml + kailash-align effort could reach 15-24 sessions.

**Recommendation**: Revise the estimate to 10-16 sessions for kailash-align alone. Deferring agents to v1.1 brings the lower bound to 8-12, which is closer to the original range. Budget kailash-ml sessions separately (5-8 sessions).

---

## RT1-05: AlignmentStrategistAgent -- Genuinely Useful?

**Severity**: MEDIUM
**Verdict**: Not genuinely useful. Deterministic logic disguised as agent reasoning.

**Analysis**: The value proposition analysis rates AlignmentStrategistAgent as LOW value. The assessment is correct. The recommendation space is narrow:

| Scenario                   | Recommendation       | Confidence                  |
| -------------------------- | -------------------- | --------------------------- |
| Have instruction data only | SFT                  | 100% (deterministic)        |
| Have preference data only  | DPO                  | 100% (deterministic)        |
| Have both                  | SFT then DPO         | 95% (almost always correct) |
| Have neither               | "Collect data first" | 100% (deterministic)        |

An LLM call to make this recommendation is wasteful: it adds 1-3 seconds of latency and API cost for a decision a lookup table handles correctly. Worse, implementing this as an agent risks violating the agent-reasoning rule. "Given a 7B model with 24GB VRAM, recommend r=16 with gradient checkpointing" is deterministic logic. The LLM adds no value because the domain is well-understood and the decision space is small.

TrainingConfigAgent has the same problem. Both are scripts wearing agent costumes.

**Recommendation**: Drop AlignmentStrategistAgent and TrainingConfigAgent from v1 entirely. If agents are desired in v1, keep only DataCurationAgent and EvalInterpreterAgent (the two with genuine ambiguity in their decision spaces -- data quality analysis and evaluation interpretation involve judgment, not lookup). This eliminates the agent-reasoning compliance risk and saves ~1 session of implementation effort.

---

## RT1-06: lm-eval-harness -- Will AlignmentEvaluator Be Practical?

**Severity**: MEDIUM
**Verdict**: Practical with appropriate defaults and guardrails.

**Analysis**: Three practical concerns:

1. **Speed**: Running MMLU (57 tasks, ~14K questions) on an 8B model takes 30-60 minutes on a single A100. Even with `limit=100`, running 5-10 tasks takes 25-50 minutes. Users expecting "instant feedback" after training will be disappointed.

2. **Memory**: Evaluation loads the full model into GPU memory. If the user just finished training (which consumed most GPU memory), they may need to restart their Python process or explicitly free the training model before evaluating. This implicit workflow constraint is easy to miss and produces confusing CUDA OOM errors.

3. **Air-gap complications**: lm-eval downloads task definitions and evaluation datasets from the internet on first use. Pre-caching all standard benchmark datasets (MMLU alone is ~250MB) adds to the air-gap preparation burden.

**Recommendation**:

- Default to `limit=100` for interactive use. Document full-dataset evaluation as a separate "thorough evaluation" workflow.
- Add a `"quick"` task preset: `evaluate(tasks=["quick"])` runs ARC-Easy + HellaSwag + TruthfulQA with limit=100 (~5 minutes total).
- Add a `free_training_resources()` method or document the need to delete the training model before evaluation on memory-constrained hardware.
- For air-gap mode, provide a `kailash-align-prepare eval-tasks` command that pre-caches the top 5 evaluation benchmarks.
- Make lm-eval an optional dependency (`[eval]` extra), as the dependency analysis recommends.
- Add progress reporting: evaluation should yield progress events so users know it is working.

---

## RT1-07: Air-Gapped Support -- YAGNI Risk?

**Severity**: LOW
**Verdict**: Low complexity, high value for target audience. Keep in v1.

**Analysis**: Air-gap support is:

- `OnPremConfig`: ~20 lines (dataclass with 4 fields)
- `OnPremModelCache`: ~150 lines (wrapper around HuggingFace Hub utilities)
- `kailash-align-prepare` CLI: ~200 lines (download/list/verify commands)
- Offline mode propagation: ~30 lines (passing `local_files_only=True` through the pipeline)

**Total: ~400 lines.** This is less than a single DataFlow model definition.

The implementation wraps existing, proven HuggingFace offline mechanisms (`HF_HUB_OFFLINE=1`, `local_files_only=True`, `snapshot_download()`). No novel offline technology is being invented.

For the target audience (government, healthcare, finance on-prem deployments), air-gap support is a hard requirement -- without it, they cannot use kailash-align at all. The brief explicitly scopes this.

The main cost is testing. Verifying that offline mode works end-to-end requires manual testing with network disabled. This is not automatable in CI.

**Recommendation**: Keep in v1. Add a `--verify-offline` flag to `kailash-align-prepare` that verifies the environment works without internet (by temporarily setting `HF_HUB_OFFLINE=1` and running a dry-run model load).

---

## RT1-08: TRL/PEFT/transformers Version Churn

**Severity**: HIGH
**Verdict**: The dependency chain is fragile and needs explicit version management.

**Analysis**: The five-level dependency chain `torch -> transformers -> trl -> peft -> accelerate` has each library releasing independently with no guaranteed cross-compatibility.

**Concrete version pinning problem**: The architecture doc specifies `trl>=0.8`, but the API changed significantly between 0.8 and 0.29 (current as of March 2026). SFTConfig/DPOConfig classes replaced TrainingArguments, data collators were restructured. Pinning `>=0.8` means users could install a TRL version where AlignmentPipeline's code does not compile.

**Known fragilities**:

- QLoRA (bitsandbytes) + gradient checkpointing + specific transformers versions can produce silent numerical errors.
- TRL's data collator changes between minor versions can break dataset formatting.
- PEFT adapter compatibility is tied to the transformers version that created the adapter. Adapters saved with transformers 4.42 may not load correctly with transformers 4.48.
- lm-eval-harness has a history of breaking changes between minor versions: task definitions, metric names, and API signatures change.

**Recommendation**:

- Tighten version pins as the dependency analysis recommends: `trl>=0.25,<1.0`, `transformers>=4.40,<5.0`, `peft>=0.10,<1.0`, `torch>=2.2,<3.0`, `lm-eval>=0.4,<1.0`.
- Create a CI matrix that tests against the minimum and maximum of each pinned range.
- Document tested version combinations in a compatibility matrix in the README.
- Consider maintaining a `requirements-lock.txt` with exact "known-good" versions for users who need guaranteed reproducibility.
- Surface area mitigation: AlignmentPipeline uses only SFTTrainer + DPOTrainer + their Config classes. This limits exposure to TRL changes, but the version pin must still be tight enough to prevent installing incompatible versions.

---

## RT1-09: Serving Scope in v1 -- Should It Be Deferred?

**Severity**: MEDIUM
**Verdict**: Keep serving in v1, but scope it narrowly.

**Analysis**: The brief explicitly states "serving IS v1 scope." The value proposition analysis confirms this is where half the value lives. AdapterRegistry + AlignmentServing are the two HIGH-value pillars. Without serving, kailash-align is a thin training wrapper over TRL that does not justify a separate package.

However, RT1-02 (GGUF reliability) makes serving the highest-risk component. The tension is real: serving is the highest value AND the highest risk.

The value proposition's scoping recommendation is sound:

| v1 (must have)                               | v1.1 (defer)                              |
| -------------------------------------------- | ----------------------------------------- |
| `export_gguf()` for tested architectures     | Advanced quantization beyond Q4_K_M/Q8_0  |
| `deploy_ollama()` for happy path             | `local_hf` strategy for KaizenModelBridge |
| `generate_vllm_config()`                     | Custom Modelfile templates                |
| "Bring your own GGUF" escape hatch           | Automated vLLM process management         |
| Clear error messages for conversion failures |                                           |

vLLM deployment (no GGUF conversion, just config generation) is low risk and high value. Ollama deployment (GGUF conversion required) is high risk but is the primary local dev workflow.

**Recommendation**: Keep serving in v1 with the narrowed scope. Make vLLM the recommended production deployment target (no format conversion risk). Position Ollama as the local development/testing target with explicit architecture support documentation.

---

## RT1-10: Four Agents in v1 -- Too Many?

**Severity**: MEDIUM
**Verdict**: Too many. Defer all four to v1.1.

**Analysis**: The value proposition analysis rates the agents as:

| Agent                    | Genuine Value | Issue                                                           |
| ------------------------ | ------------- | --------------------------------------------------------------- |
| AlignmentStrategistAgent | LOW           | Deterministic logic, agent-reasoning violation risk             |
| DataCurationAgent        | MEDIUM        | Genuine ambiguity, but not required for core workflow           |
| TrainingConfigAgent      | LOW           | Deterministic logic, agent-reasoning violation risk             |
| EvalInterpreterAgent     | MEDIUM        | Genuine decision support, but experts make this call themselves |

None of the four agents are required for the core training-evaluation-serving-integration lifecycle. The workflow works without them: users configure training manually, run evaluation, and make deployment decisions based on scores.

The implementation cost is not trivial:

- Each agent requires unit tests with mocked LLM responses + integration tests with real LLM calls (slow, expensive, flaky)
- Agent-reasoning compliance validation for each agent
- 4 agents = 4-8 test files + 1-2 sessions of implementation

Additionally, two of the four agents (AlignmentStrategistAgent, TrainingConfigAgent) risk agent-reasoning rule violations because their decision spaces are deterministic. Building them as agents and then having red team flag them as non-compliant wastes effort.

**Recommendation**: Defer all 4 agents to v1.1. This saves 1-2 sessions from the implementation plan. If the user insists on agents in v1, implement only DataCurationAgent and EvalInterpreterAgent, and explicitly document that AlignmentStrategistAgent and TrainingConfigAgent were dropped due to agent-reasoning compliance concerns.

---

## RT1-11: KaizenModelBridge -- Kaizen Internals Exposure

**Severity**: LOW
**Verdict**: Minimal risk. The bridge uses only public APIs.

**Analysis**: The Kaizen Delegate audit (research 01) and existing model config analysis (research 07) demonstrate that KaizenModelBridge needs minimal access to Kaizen internals:

1. It uses `OllamaStreamAdapter` -- public API, already exists and is well-tested.
2. It uses `OpenAIStreamAdapter` -- public API, works with vLLM's OpenAI-compatible endpoint.
3. It constructs a `Delegate` -- public constructor with documented parameters.
4. It does NOT modify the Delegate class, adapter base class, or AgentLoop.

The bridge is a factory method (~150-250 lines) that assembles existing public components. It imports from `kaizen_agents.delegate` and `kaizen_agents.delegate.adapters.*`, both stable public APIs.

The `local_hf` strategy (direct HuggingFace transformers inference within the same Python process) is the only strategy that would require a NEW adapter. It is correctly deferred to v1.1.

Model discovery (`discover_deployed_models()`) requires HTTP calls to Ollama's `/api/tags` endpoint. This is external to Kaizen and straightforward with httpx (already a transitive dependency).

The cost model gap (Delegate's `_estimate_cost()` assumes cloud pricing, local models are effectively $0/token) is a known limitation but low priority. Users running local models for cost reasons already understand the cost model is different.

**Recommendation**: No concern. KaizenModelBridge is the simplest component in kailash-align. Keep as designed.

---

## Summary

| ID     | Finding                             | Severity | Action                                                                        |
| ------ | ----------------------------------- | -------- | ----------------------------------------------------------------------------- |
| RT1-01 | ~2.5 GB install size                | LOW      | Document incremental size. Move lm-eval to [eval] extra.                      |
| RT1-02 | GGUF conversion reliability         | HIGH     | Post-conversion validation, architecture allowlist, BYOG escape hatch.        |
| RT1-03 | kailash-ml does not exist yet       | CRITICAL | Make ordering explicit. Freeze ModelRegistry interface before implementation. |
| RT1-04 | 7-12 session estimate optimistic    | HIGH     | Revise to 10-16. Defer agents to reduce lower bound to 8-12.                  |
| RT1-05 | AlignmentStrategistAgent low value  | MEDIUM   | Drop from v1. Agent-reasoning violation risk.                                 |
| RT1-06 | lm-eval-harness practical concerns  | MEDIUM   | Default limit=100, "quick" preset, make lm-eval optional [eval] extra.        |
| RT1-07 | Air-gap YAGNI risk                  | LOW      | Keep in v1. Add --verify-offline to preparation CLI.                          |
| RT1-08 | TRL/PEFT/transformers version churn | HIGH     | Tighten pins, CI version matrix, document tested combinations.                |
| RT1-09 | Serving scope in v1                 | MEDIUM   | Keep with narrowed scope. vLLM for production, Ollama for dev.                |
| RT1-10 | Four agents excessive for v1        | MEDIUM   | Defer all agents to v1.1.                                                     |
| RT1-11 | KaizenModelBridge Kaizen exposure   | LOW      | No concern. 150-250 lines, public APIs only.                                  |

## Risk Matrix

| Risk                               | Likelihood | Impact   | Mitigation                                                              |
| ---------------------------------- | ---------- | -------- | ----------------------------------------------------------------------- |
| kailash-ml ModelRegistry not ready | High       | Critical | Freeze interface early; consider standalone AdapterRegistry as fallback |
| GGUF conversion fails silently     | High       | High     | Post-conversion validation + BYOG escape hatch                          |
| TRL API breaking changes           | Medium     | Medium   | Tighten version pin to >=0.25,<1.0 + integration tests                  |
| Session estimate slippage          | Medium     | Medium   | Defer agents, start serving early to surface GGUF issues sooner         |
| lm-eval slow for large benchmarks  | High       | Low      | Default limits + quick preset                                           |
| Air-gap testing insufficient       | Medium     | Medium   | Manual testing checklist, --verify-offline CLI flag                     |

## Critical Path

The critical path for kailash-align is:

1. **kailash-ml ships** (RT1-03) -- hard prerequisite, not parallelizable with AdapterRegistry
2. **AdapterRegistry implemented** (depends on kailash-ml ModelRegistry) -- highest-value component
3. **AlignmentPipeline + AlignmentServing** (highest implementation risk from GGUF conversion)
4. **AlignmentEvaluator + KaizenModelBridge + OnPremModelCache** (medium risk, parallelizable with each other)

The most dangerous assumption in the current plan is that kailash-ml will be ready when kailash-align development begins. If kailash-ml slips, everything downstream slips. This single dependency defines the project timeline more than any other factor.
