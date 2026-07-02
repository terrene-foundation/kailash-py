# lm-eval-harness Integration Analysis

## 1. Programmatic API Surface

### `simple_evaluate()` -- Primary API

The main programmatic entry point for lm-eval-harness:

```python
import lm_eval

results = lm_eval.simple_evaluate(
    model="hf",
    model_args="pretrained=/path/to/model,trust_remote_code=True",
    tasks=["mmlu", "hellaswag", "arc_easy"],
    num_fewshot=0,
    batch_size=8,
    limit=100,  # Max samples per task (for quick evaluation)
    device="cuda:0",
)
```

Returns a dict with structure:

```python
{
    "results": {
        "mmlu": {"acc,none": 0.65, "acc_stderr,none": 0.01, ...},
        "hellaswag": {"acc_norm,none": 0.72, ...},
        "arc_easy": {"acc,none": 0.78, ...},
    },
    "config": {...},
    "versions": {...},
}
```

### `evaluate()` -- Lower-Level API

For pre-initialized models and tasks:

```python
from lm_eval import evaluator
from lm_eval.models.huggingface import HFLM

model = HFLM(
    pretrained="/path/to/model",
    batch_size=8,
    device="cuda:0",
)

results = evaluator.evaluate(
    lm=model,
    task_dict=task_dict,
    limit=100,
)
```

### Model Loading for PEFT Adapters

lm-eval-harness supports PEFT adapters natively:

```python
results = lm_eval.simple_evaluate(
    model="hf",
    model_args="pretrained=meta-llama/Llama-3.2-8B,peft=/path/to/adapter",
    tasks=["mmlu"],
)
```

This means AlignmentEvaluator does NOT need to merge adapters before evaluation -- lm-eval handles the adapter loading internally. This is a significant simplification.

## 2. Custom Task Definition

### YAML-Based Custom Tasks

lm-eval-harness supports custom tasks via YAML configuration:

```yaml
task: my_custom_task
dataset_path: /path/to/dataset
dataset_name: null
output_type: generate_until
doc_to_text: "Question: {{question}}\nAnswer:"
doc_to_target: "{{answer}}"
generation_kwargs:
  max_gen_toks: 256
  temperature: 0.0
metric_list:
  - metric: exact_match
    aggregation: mean
```

### Programmatic Custom Tasks

For AlignmentEvaluator's `evaluate_custom()` method:

```python
from lm_eval.api.task import ConfigurableTask

# Option 1: Load from YAML
task = ConfigurableTask(config=yaml_config_dict)

# Option 2: Use datasets.Dataset directly (via custom task wrapper)
# This requires more setup but allows arbitrary scoring functions
```

### AlignmentEvaluator Custom Evaluation Path

The architecture proposes `evaluate_custom(adapter_version, custom_dataset, scoring_fn)`. This would need to:

1. Load the fine-tuned model (merged or via PEFT adapter)
2. Generate responses for each input in `custom_dataset`
3. Apply `scoring_fn(generated, reference)` per sample
4. Aggregate scores

This is NOT a native lm-eval feature. lm-eval's custom tasks use predefined metrics (exact_match, perplexity, BLEU, etc.), not arbitrary Python scoring functions.

**Implementation choice**: For custom evaluation with arbitrary scoring functions, kailash-align should use `transformers.pipeline("text-generation")` directly rather than wrapping lm-eval. lm-eval is best for standardized benchmarks only.

## 3. How AlignmentEvaluator Would Wrap lm-eval

### For Standard Benchmarks

```python
class AlignmentEvaluator:
    async def evaluate(self, adapter_version, tasks, eval_config=None):
        config = eval_config or EvalConfig()

        # Build model_args string
        if adapter_version.merge_state == "merged":
            model_args = f"pretrained={adapter_version.adapter_path}"
        else:
            model_args = (
                f"pretrained={adapter_version.base_model_id},"
                f"peft={adapter_version.adapter_path}"
            )

        if self._onprem and self._onprem.offline_mode:
            model_args += ",trust_remote_code=False"

        # Call lm-eval
        results = lm_eval.simple_evaluate(
            model="hf",
            model_args=model_args,
            tasks=tasks,
            num_fewshot=config.num_fewshot,
            batch_size=config.batch_size,
            limit=config.limit,
            device=config.device,
        )

        # Convert to EvalResult dataclass
        return self._to_eval_result(adapter_version, results, tasks)
```

### For Custom Evaluation

```python
    async def evaluate_custom(self, adapter_version, custom_dataset, scoring_fn):
        # Load model directly (not via lm-eval)
        model, tokenizer = self._load_model(adapter_version)
        pipe = transformers.pipeline("text-generation", model=model, tokenizer=tokenizer)

        scores = []
        for sample in custom_dataset:
            generated = pipe(sample["input"], max_new_tokens=256)[0]["generated_text"]
            score = scoring_fn(generated, sample["reference_output"])
            scores.append(score)

        return EvalResult(
            aggregate_score=sum(scores) / len(scores),
            ...
        )
```

## 4. Storage of Evaluation Results in DataFlow

### DataFlow Model: AlignEvalResult

```python
@db.model
class AlignEvalResult:
    id: int = field(primary_key=True)
    adapter_name: str
    adapter_version: str
    base_model_id: str
    task_name: str
    metric_name: str
    metric_value: float
    num_fewshot: int
    limit: int | None
    eval_config_json: str  # Serialized EvalConfig
    evaluated_at: datetime
    created_at: datetime
    updated_at: datetime
```

This stores one row per (adapter_version, task, metric) combination. A single evaluation of 5 tasks with 3 metrics each produces 15 rows.

### Comparison Queries

```python
# Compare two adapter versions on the same tasks
results_a = await db.express.list("AlignEvalResult", {
    "adapter_name": name, "adapter_version": "v1"
})
results_b = await db.express.list("AlignEvalResult", {
    "adapter_name": name, "adapter_version": "v2"
})
```

## 5. Practical Concerns

### lm-eval Is Large and Slow

- **Package size**: lm-eval v0.4+ is a large package with many optional dependencies. As of late 2025, the base package no longer requires torch/transformers (lighter install), but when used with HuggingFace models, those dependencies are still needed.
- **Evaluation time**: Running MMLU (57 tasks, ~14K questions) on an 8B model takes 30-60 minutes on a single A100. With `limit=100`, this drops to ~5 minutes per task.
- **Memory**: Evaluating a merged 8B model requires ~16GB VRAM. With PEFT adapter (unmerged), it requires the same as the base model.

### Air-Gap Concerns

lm-eval downloads task definitions from its own repository on first use. For air-gapped environments:

- Task definitions can be pre-cached by running a dummy evaluation on the internet-connected machine
- Custom tasks via YAML files work fully offline
- Some tasks download datasets from the internet (e.g., MMLU downloads from HuggingFace Hub)

**Recommendation**: For air-gapped mode, default to a curated set of tasks that can be fully cached, and document which tasks require internet access for dataset download.

### Versioning Risk

lm-eval-harness has a history of breaking changes between minor versions. Task definitions, metric names, and API signatures change. Pin to a specific version range.

## 6. Assessment

### Value of AlignmentEvaluator

| Feature                           | Value    | Alternative Without kailash-align            |
| --------------------------------- | -------- | -------------------------------------------- |
| Standard benchmark evaluation     | Medium   | User runs lm-eval CLI directly               |
| Result storage in DataFlow        | **High** | User keeps results in notebooks/spreadsheets |
| Adapter version comparison        | **High** | Manual -- compare two lm-eval runs by hand   |
| Custom evaluation with scoring_fn | Medium   | User writes a script                         |
| Air-gapped evaluation             | Low      | Same lm-eval CLI with offline flags          |

The primary value is **persistent, queryable evaluation results linked to adapter versions**. Without this, users lose the connection between "which adapter" and "how well it performed."

### Implementation Complexity

AlignmentEvaluator is medium complexity:

- Standard evaluation: Thin wrapper (~50 lines of production code)
- Custom evaluation: Model loading + generation loop (~100 lines)
- DataFlow storage: Model definition + save/query methods (~80 lines)
- Comparison: Query + diff logic (~50 lines)

Total: ~280 lines. Not trivial but not complex either.
