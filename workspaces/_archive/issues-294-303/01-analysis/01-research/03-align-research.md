# Research: Align (#297, #298)

## Package Structure

```
packages/kailash-align/src/kailash_align/
├── __init__.py          # 50 public exports, lazy loading
├── config.py            # AlignmentConfig, LoRAConfig, DPOConfig, OnPremConfig, etc.
├── pipeline.py          # AlignmentPipeline(config, adapter_registry)
├── evaluator.py         # AlignmentEvaluator(adapter_registry)
├── onprem.py            # OnPremModelCache (download/list/verify/cache_path)
├── cli.py               # kailash-align-prepare CLI
├── bridge.py            # KaizenModelBridge
├── registry.py          # AdapterRegistry
├── method_registry.py   # MethodRegistry
├── rewards.py           # RewardRegistry
├── merge.py             # AdapterMerger
├── serving.py           # AlignmentServing
├── vllm_backend.py      # VLLMBackend, HFGenerationBackend
├── gpu_memory.py        # GPUMemoryEstimate
├── exceptions.py        # Custom exceptions
├── models.py            # Data models
└── _version.py          # v0.2.1
```

**No `agents/` directory exists.**

## Issue #297: 4 Kaizen Agent Definitions

### Pattern from kailash-ml

kailash-ml has a mature agents/ directory with 6 agents + tools.py. Each agent:

- Lazy-imports Kaizen to avoid hard dependency
- Uses `BaseAgent`, `Signature`, `InputField`, `OutputField`
- Constructor: `__init__(self, *, model: str | None = None)`
- Falls back to `os.environ.get("DEFAULT_LLM_MODEL")`

### Required Agents (per issue)

1. **AlignmentStrategistAgent** — base model selection, training method, data requirements
2. **DataCurationAgent** — dataset quality, gaps, curation strategies
3. **TrainingConfigAgent** — hyperparameters, LoRA config, hardware
4. **EvalInterpreterAgent** — interpret eval results, recommend next steps

### Required Tools (8 in tools.py)

- `get_base_model_info_tool()`, `list_training_methods_tool()`, `estimate_training_cost_tool()`
- `get_dataset_stats_tool()`, `check_preference_quality_tool()`
- `get_gpu_memory_tool()`, `estimate_lora_memory_tool()`, `list_quantization_options_tool()`

### Integration Points

- Agents read from `AlignmentConfig`, `OnPremConfig`, `AdapterRegistry`
- Tools are dumb data endpoints (LLM-first rule)
- `[agents]` extra should gate kailash-kaizen dependency

---

## Issue #298: On-Prem Workflow Completion

### What Exists

- **OnPremConfig** (config.py, frozen dataclass): `offline_mode`, `model_cache_dir`, `ollama_host`, `vllm_endpoint`
- **OnPremModelCache** (onprem.py): `download()`, `list()`, `verify()`, `cache_path()`
- **CLI** (cli.py): `kailash-align-prepare download|list|verify`

### What's Missing

1. **OnPremSetupGuide class** — `generate_checklist(models, cache_dir) -> str` returning markdown

2. **Config plumbing**:
   - `AlignmentPipeline.__init__` currently: `(config: AlignmentConfig, adapter_registry=None)`
   - Needs: `onprem_config: OnPremConfig | None = None`
   - When `offline_mode=True`: set `local_files_only=True` on all HuggingFace calls
   - `AlignmentEvaluator.__init__` currently: `(adapter_registry=None)`
   - Needs: `onprem_config: OnPremConfig | None = None`
   - Same offline_mode wiring

3. **Integration test**: download tiny model, load with offline_mode=True

### Constructor Signatures (current)

```python
# pipeline.py line 58
def __init__(self, config: AlignmentConfig, adapter_registry: Any = None) -> None:

# evaluator.py line 116
def __init__(self, adapter_registry: Any = None) -> None:
```
