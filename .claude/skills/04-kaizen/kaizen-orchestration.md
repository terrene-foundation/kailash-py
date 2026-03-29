# Kaizen Orchestration: Multi-Agent Coordination

The orchestration module provides patterns for coordinating multiple agents.

## Pipelines

### Sequential Pipeline

Agents run in order. Each receives the previous agent's response as input.

```python
from kailash_kaizen import BaseAgent
from kailash_kaizen.pipelines import SequentialPipeline

class ResearchAgent(BaseAgent):
    def run(self, input_text):
        return {"response": f"Research on: {input_text}"}

class WriterAgent(BaseAgent):
    def run(self, input_text):
        return {"response": f"Article about: {input_text}"}

researcher = ResearchAgent(name="researcher")
writer = WriterAgent(name="writer")

pipeline = SequentialPipeline([researcher, writer])
result = pipeline.run("Write about AI agents")
# researcher runs first, writer receives researcher's output
```

### Parallel Pipeline

All agents run concurrently with the same input.

```python
from kailash_kaizen.pipelines import ParallelPipeline

analyst = AnalystAgent(name="analyst")
reviewer = ReviewerAgent(name="reviewer")

pipeline = ParallelPipeline([analyst, reviewer])
result = pipeline.run("Evaluate this proposal")
# Both agents receive the same input and run concurrently
```

### Router Pipeline

Route input to the best-matching agent based on conditions.

```python
from kailash_kaizen.pipelines import RouterPipeline

pipeline = RouterPipeline()
pipeline.add_route("code", coder_agent)     # Routes if input contains "code"
pipeline.add_route("write", writer_agent)   # Routes if input contains "write"
pipeline.set_default(general_agent)         # Fallback

result = pipeline.run("Write a blog post")  # Routes to writer_agent
```

## Supervisor Pattern

```python
from kailash_kaizen import BaseAgent

class Supervisor(BaseAgent):
    def __init__(self, workers):
        super().__init__(name="supervisor")
        self.workers = workers

    def run(self, input_text):
        # Route to appropriate worker
        for worker in self.workers:
            if worker.can_handle(input_text):
                return worker.run(input_text)
        return {"response": "No worker available for this task"}

class CoderWorker(BaseAgent):
    def can_handle(self, input_text):
        return "code" in input_text.lower()

    def run(self, input_text):
        return {"response": f"Coded: {input_text}"}

class WriterWorker(BaseAgent):
    def can_handle(self, input_text):
        return "write" in input_text.lower()

    def run(self, input_text):
        return {"response": f"Written: {input_text}"}

supervisor = Supervisor([CoderWorker(name="coder"), WriterWorker(name="writer")])
result = supervisor.run("Write a documentation page")
```

## Hook-Based Coordination

```python
from kailash_kaizen import HookManager

hooks = HookManager()

@hooks.on("agent_start")
def log_start(agent_name, input_text):
    print(f"{agent_name} starting with: {input_text[:50]}")

@hooks.on("agent_complete")
def log_complete(agent_name, response):
    print(f"{agent_name} completed")

@hooks.on("agent_error")
def log_error(agent_name, error):
    print(f"{agent_name} failed: {error}")

# Attach hooks to pipeline
pipeline = SequentialPipeline([researcher, writer])
pipeline.set_hooks(hooks)
result = pipeline.run("Research AI safety")
```

## Retry and Timeout

```python
from kailash_kaizen.pipelines import SequentialPipeline

pipeline = SequentialPipeline(
    [researcher, writer],
    max_retries=3,
    timeout_seconds=120,
)
result = pipeline.run("Complex research task")
```

## Best Practices

1. **Use Sequential for dependent tasks** -- when each step needs the previous result
2. **Use Parallel for independent analysis** -- when agents analyze the same input independently
3. **Use Router for task classification** -- when different inputs need different handling
4. **Add hooks for observability** -- log agent starts, completions, and errors
5. **Set timeouts** -- prevent runaway agent executions
6. **Test each agent independently** -- unit test agents before composing them

<!-- Trigger Keywords: orchestration, multi-agent, pipeline, sequential, parallel, router, supervisor, coordination -->
