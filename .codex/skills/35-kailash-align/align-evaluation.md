# Align Evaluation

Evaluation workflow using AlignmentEvaluator: ROUGE scoring, win-rate comparison, safety checks, and the mandatory eval-before-serve pattern.

## Eval-Before-Serve (Mandatory)

No fine-tuned model reaches production without passing evaluation against the base model. This is enforced at the pipeline level — `AlignmentServing.deploy()` requires an evaluation result.

```
Train → Evaluate → Compare vs Base → Pass? → Serve
                                       │
                                   Fail? → Block deployment, report gaps
```

```python
from kailash_align import AlignmentPipeline, AlignmentConfig
from kailash_align.evaluation import AlignmentEvaluator

# Train
config = AlignmentConfig(method="dpo", base_model_id="meta-llama/Llama-3.1-8B")
pipeline = AlignmentPipeline(config=config)
train_result = await pipeline.train(dataset=preference_dataset, adapter_name="my-adapter")

# Evaluate (mandatory before serving)
evaluator = AlignmentEvaluator(config=config)
eval_result = await evaluator.evaluate(
    adapter_id=train_result.adapter_id,
    eval_dataset=eval_dataset,
)

# eval_result.passed            — True if fine-tuned model beats base
# eval_result.base_scores       — base model scores
# eval_result.adapter_scores    — fine-tuned model scores
# eval_result.improvement        — percentage improvement over base
# eval_result.safety_passed     — True if safety checks passed
```

## ROUGE Scoring

Standard ROUGE metrics for text generation quality. Useful for SFT evaluation and summarization tasks.

```python
eval_result = await evaluator.evaluate(
    adapter_id=train_result.adapter_id,
    eval_dataset=eval_dataset,
    metrics=["rouge1", "rouge2", "rougeL"],
)

# eval_result.adapter_scores["rouge1"] = 0.45
# eval_result.adapter_scores["rouge2"] = 0.23
# eval_result.adapter_scores["rougeL"] = 0.41
# eval_result.base_scores["rouge1"] = 0.38    (base model comparison)
```

## Win-Rate Comparison

Head-to-head comparison where an LLM judge evaluates which model produces better responses. Primary metric for preference-aligned models (DPO, GRPO, PPO).

```python
eval_result = await evaluator.evaluate(
    adapter_id=train_result.adapter_id,
    eval_dataset=eval_dataset,
    metrics=["win_rate"],
    judge_model="gpt-4o",           # LLM judge for win-rate
    num_comparisons=200,             # Number of head-to-head comparisons
)

# eval_result.adapter_scores["win_rate"] = 0.63
# Interpretation: fine-tuned model preferred 63% of the time vs base model
# win_rate > 0.5 means fine-tuned model is better
```

### Win-Rate Threshold

```python
# Default: fine-tuned model must win >50% of comparisons
eval_result = await evaluator.evaluate(
    adapter_id=train_result.adapter_id,
    eval_dataset=eval_dataset,
    metrics=["win_rate"],
    win_rate_threshold=0.55,   # Require 55% win rate to pass
)
```

## Safety Checks

Safety evaluation ensures the fine-tuned model has not regressed on safety-critical behaviors. Runs a curated set of adversarial prompts and checks for harmful outputs.

```python
eval_result = await evaluator.evaluate(
    adapter_id=train_result.adapter_id,
    eval_dataset=eval_dataset,
    metrics=["win_rate", "safety"],
    safety_dataset=safety_prompts,    # Adversarial prompts
)

# eval_result.safety_passed = True
# eval_result.safety_details = {
#     "harmful_output_rate": 0.02,    # 2% of adversarial prompts produced concerning output
#     "refusal_rate": 0.95,           # 95% of harmful prompts correctly refused
#     "categories_tested": ["violence", "pii", "bias", "illegal"],
# }

# Safety failure blocks deployment regardless of other metrics
if not eval_result.safety_passed:
    # AlignmentServing.deploy() will refuse
    pass
```

## Benchmark Evaluation (lm-eval-harness)

For comprehensive evaluation across standard benchmarks. Requires `pip install kailash-align[eval]`.

```python
eval_result = await evaluator.evaluate(
    adapter_id=train_result.adapter_id,
    benchmarks=["mmlu", "hellaswag", "arc_challenge", "gsm8k"],
)

# eval_result.benchmark_scores = {
#     "mmlu": {"accuracy": 0.68},
#     "hellaswag": {"accuracy": 0.82},
#     "arc_challenge": {"accuracy": 0.73},
#     "gsm8k": {"accuracy": 0.45},
# }
# eval_result.base_benchmark_scores = {
#     "mmlu": {"accuracy": 0.65},     # Base model comparison
#     ...
# }
```

## Base Model Comparison

Every evaluation automatically runs the same tests on the base model (without the adapter) and computes the delta. The fine-tuned model must demonstrate improvement to pass.

```python
eval_result = await evaluator.evaluate(
    adapter_id=train_result.adapter_id,
    eval_dataset=eval_dataset,
    metrics=["rouge1", "win_rate"],
)

# Automatic comparison
print(f"Base ROUGE-1:    {eval_result.base_scores['rouge1']:.4f}")
print(f"Adapter ROUGE-1: {eval_result.adapter_scores['rouge1']:.4f}")
print(f"Improvement:     {eval_result.improvement['rouge1']:.2%}")

# eval_result.passed is True only if:
# 1. Adapter scores beat base scores on primary metric
# 2. Safety checks passed (if run)
# 3. No regression on secondary metrics beyond tolerance
```

## Regression Detection

Checks that the fine-tuned model has not regressed on capabilities outside the fine-tuning objective.

```python
eval_result = await evaluator.evaluate(
    adapter_id=train_result.adapter_id,
    eval_dataset=eval_dataset,
    metrics=["win_rate"],
    regression_benchmarks=["mmlu", "hellaswag"],  # Check for regression
    regression_tolerance=0.02,   # Allow up to 2% drop on regression benchmarks
)

# eval_result.regression_detected = False
# eval_result.regression_details = {
#     "mmlu": {"base": 0.65, "adapter": 0.64, "delta": -0.01, "within_tolerance": True},
#     "hellaswag": {"base": 0.82, "adapter": 0.83, "delta": 0.01, "within_tolerance": True},
# }
```

## Full Evaluation Pipeline

```python
# Complete evaluation with all checks
eval_result = await evaluator.evaluate(
    adapter_id=train_result.adapter_id,
    eval_dataset=eval_dataset,
    metrics=["rouge1", "rouge2", "rougeL", "win_rate", "safety"],
    judge_model="gpt-4o",
    safety_dataset=safety_prompts,
    regression_benchmarks=["mmlu"],
    regression_tolerance=0.02,
    win_rate_threshold=0.55,
)

if eval_result.passed:
    # Safe to deploy
    from kailash_align.serving import AlignmentServing
    serving = AlignmentServing()
    await serving.deploy(
        adapter_id=train_result.adapter_id,
        eval_result=eval_result,  # Required — deploy refuses without this
        target="ollama",
    )
else:
    print(f"Evaluation failed: {eval_result.failure_reasons}")
```

## Critical Rules

- Eval-before-serve is mandatory — `deploy()` requires an `eval_result`
- Base model comparison is automatic — fine-tuned must demonstrably improve
- Safety checks block deployment on failure regardless of other metrics
- Win-rate is the primary metric for preference-aligned models (DPO, GRPO, PPO)
- ROUGE is the primary metric for SFT and summarization tasks
- Regression detection prevents catastrophic forgetting on out-of-domain capabilities
