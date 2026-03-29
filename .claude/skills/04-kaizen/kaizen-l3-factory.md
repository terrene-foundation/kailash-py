# L3 AgentFactory — Runtime Agent Spawning

## What It Is

Runtime agent instantiation with PACT-governed lifecycle tracking. Spawn child agents dynamically with envelope enforcement, tool subsetting, and cascade termination.

## Key Components

- **AgentSpec**: Frozen blueprint for agent instantiation
- **AgentInstance**: Running entity with 6-state lifecycle machine
- **AgentInstanceRegistry**: Thread-safe registry with lineage/spec indexes
- **AgentFactory**: spawn() + terminate() with invariant validation

## Lifecycle State Machine

```
Pending → Running → Waiting → Running (resume)
                  → Completed (terminal)
                  → Failed (terminal)
                  → Terminated (terminal)
```

## Usage

```python
from kaizen.l3.factory import AgentFactory, AgentInstanceRegistry, AgentSpec

# Create registry and factory
registry = AgentInstanceRegistry()
factory = AgentFactory(registry)

# Spawn root agent
root_spec = AgentSpec(spec_id="coordinator", name="Coordinator", envelope={"financial_limit": 10000})
root = await factory.spawn(root_spec, parent_id=None)
await registry.update_state(root.instance_id, AgentLifecycleState.running())

# Spawn child with tighter envelope
child_spec = AgentSpec(
    spec_id="reviewer",
    name="Code Reviewer",
    tool_ids=["read_file", "grep"],  # Must be subset of parent's tools
    envelope={"financial_limit": 2000},
    max_children=3,
)
child = await factory.spawn(child_spec, parent_id=root.instance_id)

# Cascade termination (leaves first)
await factory.terminate(root.instance_id, TerminationReason.EXPLICIT_TERMINATION)
# → child terminated first (ParentTerminated), then root
```

## Spawn Preconditions (8 Checks)

1. Parent exists and is Running/Waiting
2. Child envelope satisfies monotonic tightening
3. Parent has sufficient budget
4. Parent not at max_children
5. Delegation depth not exceeded (checks all ancestors)
6. Tool IDs subset of parent's allowed tools
7. Required context keys present
8. No cascade termination in progress (AD-L3-10)

## Reference

- Spec: `workspaces/kaizen-l3/briefs/04-agent-factory.md`
- Source: `kaizen/l3/factory/`
