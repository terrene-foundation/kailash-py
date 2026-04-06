# Kaizen Bridge

Connect fine-tuned models to Kaizen agents via KaizenModelBridge.

Requires: `pip install kailash-align[agents]`

## KaizenModelBridge

Create Kaizen Delegates that use your fine-tuned model:

```python
from kailash_align.bridge import KaizenModelBridge, BridgeConfig

bridge = KaizenModelBridge(
    config=BridgeConfig(
        adapter_name="my-adapter",
        serving_backend="ollama",  # or "vllm"
    ),
)

# Create a Delegate backed by the fine-tuned model
delegate = bridge.create_delegate()
async for event in delegate.run("Analyze this customer feedback"):
    print(event)
```

## AdapterRegistry

Track all trained adapters:

```python
from kailash_align.registry import AdapterRegistry

registry = AdapterRegistry()

# List all adapters
adapters = registry.list()
for a in adapters:
    print(f"{a.name} v{a.version}: {a.method} on {a.base_model}")

# Get specific adapter
adapter = registry.get("my-adapter", version="latest")
print(f"Path: {adapter.path}")
print(f"Metrics: {adapter.metrics}")
```

## Alignment Agents

Use the 4 built-in alignment agents for workflow automation:

```python
from kailash_align.agents import AlignmentStrategistAgent

strategist = AlignmentStrategistAgent()
result = await strategist.recommend(
    base_model_info="Meta-Llama-3-8B, 8B params, llama architecture",
    dataset_summary="10k preference pairs, avg 200 tokens chosen, avg 150 tokens rejected",
    constraints="Single A100 40GB, 2 hour budget",
)
print(result["method_recommendation"])
```

### Full Orchestrated Workflow

```python
from kailash_align.agents.orchestrator import alignment_workflow

result = await alignment_workflow(
    base_model_info="Meta-Llama-3-8B, 8B params",
    dataset_summary="10k SFT examples + 5k preference pairs",
    gpu_memory="1x A100 40GB",
    dataset_size="15k rows, ~3M tokens",
)
print(result["strategy"]["method_recommendation"])
print(result["config"]["hyperparameters"])
```

## Common Errors

**`ImportError: kailash-kaizen required`** -- Install with `pip install kailash-align[agents]`.

**`BridgeConfigError: adapter not found`** -- The adapter must be deployed (via `serving.deploy()`) before creating a bridge.

**`OllamaConnectionError`** -- Ensure the model is loaded in Ollama before creating the delegate.
