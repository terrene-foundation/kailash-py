---
description: Decision guide for choosing between Delegate, BaseAgent, GovernedSupervisor, and Pipeline patterns
globs:
  - "**/*.py"
  - "**/*.rs"
---

# Delegate vs BaseAgent: When to Use Which

## Decision Tree

1. **Do you need an autonomous agent with tools?** → `Delegate`
2. **Do you need governed multi-agent coordination?** → `GovernedSupervisor`
3. **Do you need multiple agents collaborating?** → `Pipeline` patterns
4. **Do you need custom execution logic beyond TAOD?** → `BaseAgent` subclass

## Comparison

| Aspect | Delegate | BaseAgent | GovernedSupervisor |
|--------|----------|-----------|-------------------|
| Lines to start | 2 | 60+ | 3 |
| Tool support | ToolRegistry, auto-wired | Manual via Signature | Via Delegate internally |
| Streaming | Typed DelegateEvents | Manual | Callback-based |
| Budget tracking | Built-in | None | Built-in (9 modules) |
| Error handling | ErrorEvent yielded | Manual try/except | Fail-closed governance |
| Best for | Autonomous tasks | Custom logic | Governed teams |

## Migration: BaseAgent → Delegate

```python
# Before (BaseAgent — 60+ lines)
class MyAgent(BaseAgent):
    class Sig(Signature):
        task: str = InputField(description="Task")
        response: str = OutputField(description="Response")
    def forward(self, task: str) -> dict:
        return self.run(task=task)

agent = MyAgent(config=AgentConfig(model=os.environ["LLM_MODEL"]))
result = agent.forward("Analyze data")

# After (Delegate — 2 lines)
from kaizen_agents import Delegate
delegate = Delegate(model=os.environ["LLM_MODEL"])
async for event in delegate.run("Analyze data"):
    print(event)
```

## When BaseAgent IS the Right Choice

- You need a custom execution loop (not TAOD)
- You need synchronous-only execution
- You need to extend agent behavior with custom hooks
- You're building a reusable agent component for a Pipeline
