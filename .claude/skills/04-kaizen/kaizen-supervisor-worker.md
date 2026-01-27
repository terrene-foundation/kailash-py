# Supervisor-Worker Pattern

Task delegation with semantic matching.

## Pattern

```python
# NOTE: kaizen.agents.coordination is DEPRECATED (removal in v0.5.0)
# Use kaizen.orchestration.patterns instead
from kaizen.orchestration.patterns import SupervisorWorkerPattern

pattern = SupervisorWorkerPattern(
    supervisor=supervisor_agent,
    workers=[qa_agent, code_agent, research_agent],
    coordinator=coordinator,
    shared_pool=shared_memory_pool
)

# Semantic task routing
result = pattern.execute_task("Analyze this codebase")
```

## Implementation Status
- ✅ Semantic matching with A2A
- ✅ Eliminates 40-50% manual selection logic

## References
- **Examples**: `apps/kailash-kaizen/examples/2-multi-agent/supervisor-worker/`
- **Specialist**: `.claude/agents/frameworks/kaizen-specialist.md` lines 115-165
