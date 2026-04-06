# Evaluation

Measure alignment quality before deployment.

## Standard Benchmarks

Uses lm-eval-harness. Requires: `pip install kailash-align[eval]`

```python
from kailash_align.evaluator import AlignmentEvaluator
from kailash_align.config import EvalConfig

evaluator = AlignmentEvaluator()

# Quick evaluation (limit=50 per task)
result = await evaluator.evaluate(
    adapter_name="my-adapter",
    config=EvalConfig(
        tasks=["hellaswag", "arc_easy", "mmlu"],
        limit=50,
    ),
)

for task in result.tasks:
    print(f"{task.name}: {task.score:.3f} (metric: {task.metric})")
print(f"Average: {result.average_score:.3f}")
```

## Safety Evaluation

Evaluate for harmful outputs before deployment:

```python
result = await evaluator.evaluate(
    adapter_name="my-adapter",
    config=EvalConfig(
        tasks=["truthfulqa_mc2", "toxigen"],
        limit=100,
    ),
)
```

## Custom Evaluation

For domain-specific evaluation without lm-eval:

```python
result = await evaluator.evaluate_custom(
    adapter_name="my-adapter",
    test_prompts=[
        "Explain quantum computing to a 5-year-old",
        "Write a Python function to sort a list",
    ],
    evaluator_fn=your_custom_scorer,
)
```

## Eval-Before-Serve Pattern

Always evaluate before deploying to production:

```python
# Train
result = await pipeline.train(dataset=data, adapter_name="v2")

# Evaluate
eval_result = await evaluator.evaluate("v2")

# Only deploy if quality threshold met
if eval_result.average_score > 0.75:
    await serving.deploy(adapter_name="v2", target="ollama")
else:
    print(f"Score {eval_result.average_score:.3f} below threshold")
```

## Common Errors

**`ImportError: lm_eval not found`** -- Install with `pip install kailash-align[eval]`.

**`EvalError: adapter not found`** -- The adapter must be registered in the AdapterRegistry before evaluation.

**`TimeoutError`** -- Large evaluation sets can take hours. Use `limit=50` for quick iterations.
