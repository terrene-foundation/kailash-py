# Kaizen Checkpoint & Resume

Save and restore agent execution state for long-running workflows.

## Concept

Checkpointing lets you:

- Save agent state mid-execution
- Resume from saved state after failures
- Interrupt and continue later
- Build fault-tolerant agent systems

## AgentCheckpoint

```python
from kaizen.checkpoint import AgentCheckpoint, InMemoryCheckpointStorage

# Create checkpoint storage
storage = InMemoryCheckpointStorage()

# Save a checkpoint
checkpoint = AgentCheckpoint(
    agent_name="researcher",
    state={"current_topic": "AI safety", "sources_found": 5},
    iteration=3,
)
storage.save(checkpoint)

# Load a checkpoint
restored = storage.load("researcher")
print(restored.state)  # {"current_topic": "AI safety", "sources_found": 5}
print(restored.iteration)  # 3
```

## File-Based Storage

```python
from kaizen.checkpoint import FileCheckpointStorage

# Persist checkpoints to disk
storage = FileCheckpointStorage("/tmp/agent_checkpoints")

# Save and load work the same way
storage.save(checkpoint)
restored = storage.load("researcher")
```

## Agent Interrupts

```python
from kaizen.interrupt import AgentInterrupt

# Create an interrupt with chaining
interrupt = (
    AgentInterrupt("researcher")
    .with_reason("Rate limit reached")
    .with_state({"progress": 0.5})
    .with_resume_hint("Wait 60 seconds before resuming")
)

# Check interrupt properties
print(interrupt.agent_name)   # "researcher"
print(interrupt.reason)       # "Rate limit reached"
print(interrupt.state)        # {"progress": 0.5}
print(interrupt.resume_hint)  # "Wait 60 seconds before resuming"
```

## Resumable Agent Pattern

```python
from kaizen import BaseAgent
from kaizen.checkpoint import InMemoryCheckpointStorage, AgentCheckpoint

class ResumableAgent(BaseAgent):
    def __init__(self, name, storage=None):
        super().__init__(name=name)
        self.storage = storage or InMemoryCheckpointStorage()

    def run(self, input_text):
        # Check for existing checkpoint
        checkpoint = self.storage.load(self.name)
        start_iteration = checkpoint.iteration if checkpoint else 0

        results = []
        for i in range(start_iteration, 10):
            try:
                result = self._process_step(i, input_text)
                results.append(result)

                # Save progress
                self.storage.save(AgentCheckpoint(
                    agent_name=self.name,
                    state={"results": results, "step": i},
                    iteration=i + 1,
                ))
            except Exception:
                # State saved at last successful step
                break

        return {"response": str(results)}

    def _process_step(self, step, input_text):
        return f"Step {step}: {input_text}"
```

## Best Practices

1. **Save after each meaningful step** -- not too frequently (overhead) or too rarely (lost work)
2. **Include enough state to resume** -- all mutable data needed to continue
3. **Use file storage for production** -- in-memory is fine for development
4. **Clean up old checkpoints** -- implement retention policies
5. **Test resume paths** -- verify agents actually resume correctly

<!-- Trigger Keywords: checkpoint, resume, agent state, fault tolerance, interrupt, save state -->
