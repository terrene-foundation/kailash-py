# Red Team Round 2: kailash-align

**Date**: 2026-04-01
**Scope**: Verify R1 resolutions, cross-workspace integration risks, deep dive on serving pipeline.
**Input**: R1 report (7 findings), research files (TRL ecosystem, serving infrastructure, Delegate audit), kailash-ml architecture + todos, cross-workspace synthesis.

---

## 1. R1 Resolution Verification

### RT3-03 (CRITICAL): Freezing ModelRegistry Interface in Protocols

**R1 Resolution**: Define ModelRegistry contract in `kailash-ml-protocols` before either package starts implementation.

**R2 Assessment**: PARTIALLY RESOLVED -- residual risk remains.

**What the protocols package actually defines** (from kailash-ml architecture):

```python
# kailash_ml_protocols/protocols.py
class AgentInfusionProtocol(Protocol):
    async def suggest_model(...) -> dict: ...
    async def suggest_features(...) -> list[dict]: ...
    async def interpret_results(...) -> dict: ...

class MLToolProtocol(Protocol):
    async def predict(...) -> dict: ...
    async def get_metrics(...) -> dict: ...
    async def trigger_retrain(...) -> str: ...
```

**The problem**: `kailash-ml-protocols` defines `AgentInfusionProtocol` and `MLToolProtocol` for the circular dependency resolution between kailash-ml and kailash-kaizen. It does NOT currently define a `ModelRegistryProtocol` or any interface that AdapterRegistry would use to extend ModelRegistry.

AdapterRegistry (`class AdapterRegistry(ModelRegistry)`) uses **concrete inheritance**, not protocol-based composition. It extends the actual `ModelRegistry` class from `kailash_ml.engines.model_registry`, not a protocol. This means:

1. **The `kailash-ml-protocols` package does not solve the AdapterRegistry dependency problem.** The protocols package resolves the kailash-ml/kailash-kaizen circular dependency, not the kailash-ml/kailash-align sequential dependency.

2. **AdapterRegistry depends on the concrete ModelRegistry class**: `register()`, `promote()`, `load()`, `compare()`, `export_mlflow()`, plus the DataFlow models `MLModel` and `MLModelVersion`.

3. **Interface freezing is not achievable via protocols alone.** To freeze the interface, one of two paths is needed:
   - **(A)** Add a `ModelRegistryProtocol` to `kailash-ml-protocols` that defines the extension surface, then have AdapterRegistry depend on the protocol, not the class. This requires refactoring AdapterRegistry from inheritance to composition.
   - **(B)** Freeze the concrete ModelRegistry API shape (method signatures + DataFlow model schemas) as a design contract, then implement kailash-align against a mock ModelRegistry that matches the contract.

**Option B is more realistic** -- the architecture doc already specifies ModelRegistry's methods and DataFlow models in detail (TSG-302). But the risk is: if implementation of TSG-302 changes the method signatures or DataFlow model shapes, AdapterRegistry breaks.

**Specific extension surface AdapterRegistry needs from ModelRegistry**:

| Method/Model                                        | What AdapterRegistry Uses                            | Risk if Changed                                      |
| --------------------------------------------------- | ---------------------------------------------------- | ---------------------------------------------------- |
| `register(name, artifact, metrics, feature_schema)` | Called by `register_adapter()` for base registration | HIGH -- signature change breaks adapter registration |
| `promote(name, version, stage)`                     | Inherited directly                                   | LOW -- simple method                                 |
| `load(name, version, stage)`                        | Used to load base model reference                    | MEDIUM -- return type matters                        |
| `MLModel` DataFlow model                            | Extended by `AlignAdapter` model                     | HIGH -- field changes cascade                        |
| `MLModelVersion` DataFlow model                     | Extended by `AlignAdapterVersion` model              | HIGH -- schema changes cascade                       |
| `ArtifactStore` protocol                            | Used for adapter artifact storage                    | MEDIUM -- protocol is simple                         |
| `Stage` enum                                        | Used directly                                        | LOW -- enum values stable                            |

**Revised risk**: MEDIUM (down from CRITICAL). The ModelRegistry API is well-specified in TSG-302 with detailed acceptance criteria. The risk is implementation drift, not design ambiguity. But the protocols package does not provide the safety net R1 assumed.

**Action**: Document the ModelRegistry extension contract explicitly (method signatures + DataFlow model schemas that AdapterRegistry depends on) as a separate section in kailash-ml-protocols or as a design contract document. Do NOT rely on `kailash-ml-protocols` alone -- it solves a different problem.

---

### RT3-02 (HIGH): GGUF Post-Conversion Validation + BYOG

**R1 Resolution**: Add post-conversion validation (single-prompt inference test) + "bring your own GGUF" escape hatch.

**R2 Assessment**: SOUND, but validation implementation has three unresolved details.

**Detail 1: What does "single-prompt inference test" mean concretely?**

The validation must load the GGUF file and generate at least one token. This requires either:

- **Option A**: Use `llama-cpp-python` to load the GGUF and run inference in-process. This adds a ~200MB dependency and platform-specific compiled binaries.
- **Option B**: Deploy to Ollama, run a single `/api/chat` call, verify non-empty response. This requires Ollama to be running during export -- which may not be the case if the user is only exporting GGUF for transfer.
- **Option C**: Use `llama-cpp-python`'s low-level API (`llama_model_quantize_params`) for quantization AND validation in one step, avoiding the separate `llama-quantize` binary.

**Recommendation**: Option C is the best path. `llama-cpp-python` bundles the compiled llama.cpp libraries and exposes both quantization and inference APIs via Python. This eliminates the `llama-quantize` binary dependency AND provides validation capability. The ~200MB size is acceptable given kailash-align is already 2.5GB.

This changes the external dependency model: instead of requiring users to build llama.cpp from source and set `LLAMA_CPP_DIR`, kailash-align would add `llama-cpp-python` as an optional dependency under the `[serve]` extra.

**Detail 2: Validation on non-CUDA hardware.**

Post-conversion validation requires loading a 7-14GB model (F16 GGUF) into memory and generating tokens. On CPU, this takes 30-120 seconds for a single prompt. On Apple Silicon with Metal, 10-30 seconds. On CUDA, 2-5 seconds.

The validation step MUST have a configurable timeout and must be skippable (`validate=False`). Default: enabled with 120-second timeout.

**Detail 3: BYOG escape hatch interface.**

```python
# Clear interface needed:
await serving.deploy_ollama(
    gguf_path="/path/to/my-preconverted.gguf",  # BYOG
    model_name="my-model",
)
# vs. the normal path:
await serving.deploy(adapter_version, target="ollama")
```

This is straightforward but must be documented as the primary recommendation for unsupported architectures.

**Revised severity**: MEDIUM (down from HIGH). The path is clearer now: `llama-cpp-python` solves both the binary dependency AND validation problems. Remaining risk is platform compatibility of llama-cpp-python wheels (limited on some Linux ARM variants).

---

### RT3-04 (MEDIUM): Session Estimate Revised to 8-14

**R1 Resolution**: Revised from 7-12 to 8-14 sessions.

**R2 Assessment**: 8-14 is REALISTIC, but the distribution is skewed.

**Breakdown with R2 adjustments**:

| Phase                        | Sessions | R1 Estimate | R2 Adjustment | Reason                                                                                                                |
| ---------------------------- | -------- | ----------- | ------------- | --------------------------------------------------------------------------------------------------------------------- |
| Phase 1: AdapterRegistry     | 1        | 1           | 1             | Standard DataFlow model + class extension. BUT depends on ModelRegistry existing.                                     |
| Phase 2: AlignmentPipeline   | 2-3      | 2-3         | 2             | TRL surface area is small. Pin to `>=0.25,<1.0`. Low complexity once base model loading works.                        |
| Phase 3a: Evaluator          | 1-2      | 1-2         | 1-2           | lm-eval integration is well-documented. Main risk is custom evaluation scoring.                                       |
| Phase 3b: Serving            | 2-4      | 2-4         | 2-3           | Using `llama-cpp-python` simplifies the binary dependency. GGUF conversion for 4 target architectures is well-tested. |
| Phase 4: Bridge + OnPrem     | 1-2      | 1-2         | 1-2           | Bridge is ~200 lines (Delegate audit confirms). OnPrem is ~400 lines wrapping HF Hub.                                 |
| Phase 5: Integration testing | --       | --          | 1-2           | Cross-component testing (train -> eval -> serve -> bridge). Not in R1 estimate.                                       |
| **Total**                    |          | **8-14**    | **8-12**      |                                                                                                                       |

**Key insight**: R1's upper bound of 14 assumed worst-case GGUF issues. With `llama-cpp-python` simplifying the tooling, and the 4 target architectures being well-supported, 12 is a more realistic upper bound. But R1 did NOT account for integration testing (Phase 5), which adds 1-2 sessions.

**Net**: 8-12 sessions (tightened range). The kailash-ml dependency wait time is NOT included -- this is pure execution time once ModelRegistry is available.

---

### RT3-05 (LOW): Defer Agents to v1.1

**R1 Resolution**: Defer all 4 agents (AlignmentStrategist, DataCuration, TrainingConfig, EvalInterpreter) to v1.1.

**R2 Assessment**: CORRECT decision. Nothing is lost for v1.

**What is lost by deferring**:

- No AI-guided method selection (SFT vs DPO) -- but this is deterministic (see R1 analysis)
- No AI-guided training config -- but recommended configs can be documented as defaults
- No automated data quality analysis -- genuine value, but not blocking for the core workflow
- No automated eval interpretation -- expert users don't need it; non-expert users can read metric descriptions

**What is preserved**:

- The agent architecture (tools.py, agent class stubs in agents/) can be scaffolded in v1 code structure without implementation
- The Kaizen Delegate integration (KaizenModelBridge) IS in v1 -- agents that USE fine-tuned models work; agents that GUIDE fine-tuning are deferred

**Risk of deferral**: If v1.1 never ships, the agents never exist. But the core lifecycle (train -> eval -> serve -> integrate) works without them. This is the right call.

---

## 2. Cross-Workspace Integration Analysis

### 2.1 AdapterRegistry <-> ModelRegistry Extension Surface

**What AdapterRegistry specifically needs**:

1. **Class to inherit from**: `ModelRegistry` class with its `__init__(db: DataFlow, artifact_store)` signature
2. **Methods to call via `super()`**: `register()`, `promote()`, `load()`
3. **DataFlow models to extend**: `MLModel` (add adapter-specific fields), `MLModelVersion` (add lora_config_json, base_model_id, merge_state, gguf_path, quantization_config_json)
4. **`Stage` enum**: STAGING, SHADOW, PRODUCTION, ARCHIVED
5. **`ArtifactStore` protocol**: `save(path, data)`, `load(path)`, `delete(path)`, `exists(path)`
6. **`ModelArtifact` dataclass**: The wrapper around serialized model bytes/paths

**What it does NOT need**: `compare()`, `export_mlflow()`, `import_mlflow()` -- these are used directly, not extended.

**Risk assessment**: The extension surface is moderate (6 touch points). The DataFlow model extension is the highest risk because DataFlow model field changes affect database schema, which cascades to migration handling. If `MLModelVersion` gains or loses fields between design and implementation, `AlignAdapterVersion`'s schema breaks.

**Mitigation**: TSG-302 acceptance criteria explicitly list the DataFlow model fields. Treat these fields as frozen once TSG-302 implementation begins. Any field changes after that point require a coordination ticket for kailash-align.

### 2.2 KaizenModelBridge <-> Delegate Discovery

**How Delegate currently discovers models** (from audit):

1. Explicit `model` parameter to `Delegate(model="...")`
2. `DEFAULT_LLM_MODEL` environment variable
3. `KZ_MODEL` via KzConfig loader

There is NO automatic model discovery. Delegate requires an explicit model string.

**Is the bridge design viable?** YES. The audit confirms:

- `OllamaStreamAdapter` already exists and works for local Ollama models
- `OpenAIStreamAdapter` already works for vLLM (OpenAI-compatible API)
- `KaizenModelBridge.create_delegate()` is a factory that constructs a Delegate with the right adapter and model string

The bridge does NOT need to modify Delegate internals. It constructs a Delegate with pre-configured adapter pointing at the local serving endpoint. This is a clean integration with zero risk of breaking Delegate.

**One gap identified**: `discover_deployed_models()` needs to call Ollama's `/api/tags` endpoint to list locally available models. This is a simple HTTP GET via httpx (already a transitive dependency). Low risk.

**Cost tracking gap** (noted in audit): Delegate's `_estimate_cost()` uses cloud pricing. Local models have $0/token cost. If the user sets `budget_usd` on a governed Delegate pointing at a local model, the budget would never be consumed. This is not a correctness bug (budget is not exceeded), but it means budget tracking is meaningless for local models. Worth documenting, not worth fixing in v1.

### 2.3 AlignmentEvaluator <-> DataFlow Result Storage

**The question**: Does DataFlow support nested dicts and arrays for evaluation results?

**lm-eval-harness output format**:

```python
{
    "results": {
        "mmlu": {"acc,none": 0.65, "acc_stderr,none": 0.01},
        "hellaswag": {"acc_norm,none": 0.72},
    },
    "config": {...},
    "versions": {...},
}
```

This is a nested dict with string keys and float values.

**DataFlow storage approach**: The architecture specifies `AlignEvalResult` DataFlow model with results stored alongside adapter version. Looking at kailash-ml's precedent, `MLModelVersion` uses `metrics_json` (a TEXT/JSON column) to store metrics as serialized JSON.

**DataFlow's JSON support**:

- `dialect.json_column_type()` returns `JSONB` (PostgreSQL), `JSON` (MySQL), or `TEXT` (SQLite)
- `dialect.json_extract()` provides cross-database JSON path queries
- Express API stores Python dicts as JSON text in TEXT columns

**Assessment**: DataFlow supports this pattern well. The `AlignEvalResult` model should store `task_results_json` as a TEXT field containing `json.dumps(task_results)`. Retrieval deserializes with `json.loads()`. This is the same pattern used by `MLModelVersion.metrics_json` and `AlignExperiment.lora_config_json`.

**Risk**: LOW. The pattern is proven. The only concern is query performance for filtering by specific metric values (e.g., "find all adapters where MMLU > 0.7"). This requires `json_extract()` which works but is slower than indexed columns. For v1, this is acceptable -- evaluation results are read individually, not queried in bulk.

---

## 3. Deep Dive: Serving Pipeline Risk

### 3.1 GGUF Conversion Success Rate by Architecture

| Architecture                     | Base Models                            | Conversion Reliability | Known Issues                                                                                                                                                                    |
| -------------------------------- | -------------------------------------- | ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Llama-3** (LlamaForCausalLM)   | Llama-3.2-1B/3B, Llama-3.1-8B/70B      | **HIGH**               | First-class llama.cpp support. Rarely fails.                                                                                                                                    |
| **Mistral** (MistralForCausalLM) | Mistral-7B-v0.3, Mixtral-8x7B          | **HIGH**               | Well-tested. Sliding window attention handled correctly.                                                                                                                        |
| **Phi-3** (Phi3ForCausalLM)      | Phi-3-mini-4k (3.8B), Phi-3-small (7B) | **MEDIUM-HIGH**        | Supported since llama.cpp b3000+. Phi-3 custom rope_scaling required specific handling -- now resolved. Phi-3.5 variants may have edge cases with `su` rope_scaling type.       |
| **Qwen2.5** (Qwen2ForCausalLM)   | Qwen2.5-0.5B/1.5B/3B/7B/14B/32B        | **MEDIUM-HIGH**        | Supported. Qwen-specific tokenizer handling added. Recent Qwen3-Embedding conversion bugs reported (June 2025 llama.cpp issue #14459), but base Qwen2.5 text models are stable. |

**Overall success rate for the 4 target architectures**: ~90-95% for standard configurations. Failures concentrate in:

- Custom rope_scaling variants not yet in llama.cpp's handler
- Models requiring `trust_remote_code=True` (e.g., some Qwen variants)
- Fine-tuned models with modified tokenizer configurations

**R2 recommendation**: The supported architecture allowlist from R1 is valid. Llama-3 and Mistral should be documented as "fully supported." Phi-3 and Qwen2.5 as "supported (tested configurations)."

### 3.2 llama-quantize: Pip vs Compiled

**R1 assumption**: `llama-quantize` is a compiled C++ binary requiring manual installation.

**R2 finding**: `llama-cpp-python` provides a Python-level quantization API via `llama_cpp.llama_model_quantize()`. This eliminates the need for the standalone `llama-quantize` binary.

```python
# llama-cpp-python approach (no separate binary needed):
import llama_cpp
params = llama_cpp.llama_model_quantize_default_params()
params.nthread = 4
params.ftype = llama_cpp.LLAMA_FTYPE_MOSTLY_Q4_K_M
llama_cpp.llama_model_quantize("model-f16.gguf", "model-q4km.gguf", params)
```

**Installation**: `pip install llama-cpp-python` bundles pre-built wheels for:

- Linux x86_64 (CPU, CUDA 11.8, CUDA 12.1)
- macOS x86_64 and ARM64 (Apple Silicon with Metal)
- Windows x86_64

This covers all target platforms for kailash-align.

**R2 recommendation**: Replace the `LLAMA_CPP_DIR` environment variable approach with `llama-cpp-python` as an optional dependency under `[serve]` extra. This provides:

1. GGUF conversion via `convert_hf_to_gguf.py` (from the `gguf` pip package -- Python, no binary needed)
2. Quantization via `llama_cpp.llama_model_quantize()` (Python API, no binary needed)
3. Validation via `llama_cpp.Llama()` + `create_completion()` (in-process inference test)

**Updated dependency for pyproject.toml**:

```toml
[project.optional-dependencies]
serve = ["llama-cpp-python>=0.3", "gguf>=0.10"]
```

### 3.3 Non-CUDA Hardware: Apple Silicon + CPU-Only

**Apple Silicon (M1/M2/M3/M4)**:

- `llama-cpp-python` has native Apple Silicon wheels with Metal acceleration
- GGUF conversion works (Python-only, no GPU needed)
- Quantization works via Metal (accelerated) or CPU (slower but functional)
- Post-conversion validation: 10-30 seconds for 8B model on M-series
- Training: PyTorch supports MPS backend (`device="mps"`) since PyTorch 2.0. SFTTrainer/DPOTrainer work on MPS with `mixed_precision="no"` (bf16 not supported on MPS, fp16 has limited support)

**CPU-only (no GPU)**:

- GGUF conversion: Works (Python-only)
- Quantization: Works but slow (minutes for 8B model)
- Post-conversion validation: 60-120 seconds for 8B model
- Training: Functionally works but extremely slow for 7B+ models (hours per epoch). Practical only for models <= 3B or very small datasets.

**vLLM on non-CUDA**:

- vLLM has experimental CPU support on macOS (Apple Silicon)
- Must build from source -- no pre-built wheels
- Performance is significantly worse than Ollama on Apple Silicon (Ollama uses llama.cpp's Metal backend; vLLM CPU mode does not use Metal)
- **R2 recommendation**: For Apple Silicon users, Ollama is the recommended deployment target, not vLLM. Document this clearly.

### 3.4 vLLM Config Generation: Testable Without GPU?

**YES.** `generate_vllm_config()` produces a JSON config file and a shell script. It does NOT start vLLM or load a model. This is pure Python string/dict generation.

**Testing approach**:

```python
def test_generate_vllm_config():
    config = serving._generate_vllm_config(adapter_version, merged_model_path)
    assert config["model"] == str(merged_model_path)
    assert config["dtype"] == "bfloat16"
    assert config["tensor-parallel-size"] == 1
    # No GPU needed -- this is config generation only
```

The entire serving module is testable without GPU EXCEPT for:

1. `export_gguf()` -- requires loading model weights (needs RAM, not GPU; ~16GB for 8B F16)
2. `deploy_ollama()` -- requires Ollama running (integration test, needs Ollama binary)
3. Post-conversion validation -- requires loading GGUF (needs RAM)

Unit tests for serving config generation, Modelfile creation, and vLLM config output can run on any CI machine. Integration tests for the full pipeline need a GPU-equipped runner or Apple Silicon with sufficient RAM.

---

## 4. New Findings (R2-Specific)

### RT3-R2-01: llama-cpp-python as Optional Dependency (NEW)

**Severity**: MEDIUM (positive -- reduces risk)
**Type**: Design improvement

Using `llama-cpp-python` under `[serve]` extra resolves three R1 concerns simultaneously:

1. Eliminates `llama-quantize` binary dependency (was R1's biggest friction point)
2. Provides validation API (single-prompt inference test)
3. Provides pre-built wheels for all target platforms

**Trade-off**: Adds ~200MB to `[serve]` install. Given kailash-align is already ~2.5GB, this is negligible.

**Action**: Update architecture doc to use `llama-cpp-python` instead of raw llama.cpp binary. Update pyproject.toml `[serve]` extra.

### RT3-R2-02: ModelRegistry Extension Contract Not in Protocols (NEW)

**Severity**: MEDIUM
**Type**: Dependency risk

The `kailash-ml-protocols` package solves the kailash-ml/kailash-kaizen circular dependency. It does NOT define a ModelRegistry interface that AdapterRegistry can depend on. AdapterRegistry uses concrete class inheritance.

**Impact**: If ModelRegistry's method signatures or DataFlow model schemas change during TSG-302 implementation, AdapterRegistry breaks. The protocols package provides no safety net for this.

**Action**: Create an explicit "ModelRegistry Extension Contract" document listing the frozen method signatures and DataFlow model schemas. Treat this as a design pact between kailash-ml and kailash-align workspaces. Any deviation requires coordination.

### RT3-R2-03: Apple Silicon as Primary Non-CUDA Path (NEW)

**Severity**: LOW (informational)
**Type**: Platform guidance

For the target audience (on-prem SLM deployment), Apple Silicon is the dominant non-CUDA platform. The serving pipeline works well on Apple Silicon via `llama-cpp-python` (Metal acceleration) and Ollama (native Metal support). vLLM is NOT recommended on Apple Silicon (experimental, CPU-only, poor performance).

**Action**: Document Ollama as the recommended deployment target for Apple Silicon. Document vLLM as CUDA-only in practice.

### RT3-R2-04: Budget Tracking Meaningless for Local Models (NEW)

**Severity**: LOW
**Type**: Documentation gap

Delegate's `budget_usd` tracking uses cloud API pricing. Local models (Ollama/vLLM) have $0/token cost. If a governed Delegate points at a local model with a budget constraint, the budget is never consumed. This is functionally correct (budget is not exceeded) but semantically misleading.

**Action**: Document in KaizenModelBridge that budget tracking is cloud-API-only. Local models should use `max_turns` or `max_tokens` for execution bounds instead of `budget_usd`.

---

## 5. Updated Risk Matrix

| Risk                                              | R1 Severity     | R2 Severity      | Change   | Reason                                                                     |
| ------------------------------------------------- | --------------- | ---------------- | -------- | -------------------------------------------------------------------------- |
| ModelRegistry API changes                         | CRITICAL        | **MEDIUM**       | Improved | API well-specified in TSG-302; but protocols don't cover extension surface |
| GGUF conversion fails silently                    | HIGH            | **MEDIUM**       | Improved | llama-cpp-python provides validation + quantization in Python              |
| TRL API breaking changes                          | MEDIUM          | **MEDIUM**       | Stable   | Pin `>=0.25,<1.0`; surface area is small                                   |
| lm-eval slow for large benchmarks                 | MEDIUM          | **LOW**          | Improved | Default `limit=100` + quick preset resolves                                |
| Air-gap testing insufficient                      | MEDIUM          | **MEDIUM**       | Stable   | Still requires manual testing with network disabled                        |
| Agent premature abstraction                       | LOW             | **CLOSED**       | Resolved | Deferred to v1.1 per R1                                                    |
| Install size (~2.5GB)                             | LOW             | **CLOSED**       | Resolved | Expected for LLM work; acknowledged                                        |
| llama-quantize binary dependency                  | HIGH (implicit) | **CLOSED**       | Resolved | llama-cpp-python eliminates this                                           |
| ModelRegistry extension contract not in protocols | --              | **MEDIUM** (NEW) | New      | Needs explicit design pact                                                 |
| Budget tracking for local models                  | --              | **LOW** (NEW)    | New      | Document, don't fix                                                        |

## 6. Summary: Prioritized Actions from R2

| ID        | Action                                                                              | Priority | Source            |
| --------- | ----------------------------------------------------------------------------------- | -------- | ----------------- |
| RT3-R2-02 | Create ModelRegistry Extension Contract (frozen signatures + DataFlow schemas)      | **P0**   | R2 new finding    |
| RT3-R2-01 | Add `llama-cpp-python` + `gguf` to `[serve]` extra; remove `LLAMA_CPP_DIR` approach | **P1**   | R2 new finding    |
| RT3-02    | Implement post-conversion validation using `llama_cpp.Llama()` inference test       | **P1**   | R1, refined in R2 |
| RT3-04    | Tighten TRL pin to `>=0.25,<1.0` in pyproject.toml                                  | **P1**   | R1, unchanged     |
| RT3-R2-03 | Document Ollama as recommended target for Apple Silicon; vLLM as CUDA-only          | **P2**   | R2 new finding    |
| RT3-R2-04 | Document budget_usd limitation for local models in KaizenModelBridge                | **P2**   | R2 new finding    |
| RT3-06    | Make lm-eval optional (`[eval]` extra); add "quick" preset                          | **P2**   | R1, unchanged     |

## 7. Convergence Assessment

**R1 had 7 findings (1C, 1H, 3M, 2L).**
**R2 has 4 open findings (0C, 3M, 1L) + 2 new informational findings.**

The CRITICAL finding (ModelRegistry dependency) is downgraded to MEDIUM -- the risk is real but manageable with an explicit extension contract. The HIGH finding (GGUF conversion) is downgraded to MEDIUM -- `llama-cpp-python` resolves the binary dependency and enables validation.

**Remaining open risks are all MEDIUM or lower.** No blockers to proceeding to `/todos` phase.

**Session estimate**: 8-12 sessions (tightened from R1's 8-14). Dependent on kailash-ml TSG-302 delivering the frozen ModelRegistry API.
