# State Management for Autonomous Agents

**Version**: 1.0.0
**Status**: Production Ready
**Implementation**: TODO-204 (Phase 3: State Management)
**Test Coverage**: 21/21 tests passing (100%)

---

## Overview

The State Management system enables autonomous agents to track and persist execution state beyond basic checkpointing. This includes approval history, tool usage analytics, and workflow state integration with the Kailash SDK runtime.

### Key Features

- **Approval History Tracking**: Record all tool approval decisions for audit trails
- **Tool Usage Analytics**: Track tool invocation counts for cost estimation and analytics
- **Workflow State Integration**: Capture Kailash SDK workflow execution state
- **Full Checkpoint Integration**: All tracking state is captured in checkpoints
- **State Restoration**: Resume execution with complete state preservation

---

## Quick Start

### Basic State Tracking

```python
from kaizen.agents.autonomous.base import BaseAutonomousAgent, AutonomousConfig
from kaizen.signatures import Signature, InputField, OutputField

class TaskSignature(Signature):
    task: str = InputField(description="Task to perform")
    result: str = OutputField(description="Result")

# Create agent with default configuration
config = AutonomousConfig(
    max_cycles=10,
    llm_provider="ollama",
    model="llama3.2",
)

agent = BaseAutonomousAgent(config=config, signature=TaskSignature())

# Record approvals during execution
agent.record_approval("Bash", True, "once", {"command": "ls -la"})
agent.record_approval("Write", False, "deny_all")

# Record tool usage
agent.record_tool_usage("Bash")
agent.record_tool_usage("Read", increment=5)

# Update workflow state
agent.update_workflow_state(
    run_id="run_abc123",
    status="running",
    current_node="process_data",
)

# Access tracked state
approval_history = agent._get_approval_history()
tool_counts = agent._get_tool_usage_counts()
workflow_state = agent._get_workflow_state()
```

---

## Approval History Tracking

### Purpose

Track all tool approval decisions for:
- Audit trails and compliance reporting
- Security analysis and forensics
- User preference learning
- Checkpoint persistence and recovery

### Recording Approvals

```python
# Record a simple approval
agent.record_approval("Bash", True)  # Approved for this invocation

# Record approval with action type
agent.record_approval("Write", True, "all")  # Approve all future uses
agent.record_approval("Delete", False, "deny_all")  # Deny all future uses

# Record approval with tool input for audit
agent.record_approval(
    tool_name="Bash",
    approved=True,
    action="once",
    tool_input={"command": "rm -rf /tmp/test"}  # Truncated for storage
)
```

### Approval Record Structure

```python
{
    "tool_name": "Bash",           # Name of the tool
    "approved": True,              # Whether approved (True/False)
    "action": "once",              # Action type: "once", "all", "deny_all"
    "timestamp": "2025-01-01T12:00:00.000000",  # ISO timestamp
    "input_summary": "{'command': 'ls -la'}"    # Truncated tool input
}
```

### Retrieving Approval History

```python
# Get all approval records (returns a copy)
history = agent._get_approval_history()

# Iterate through approvals
for record in history:
    print(f"{record['tool_name']}: {'Approved' if record['approved'] else 'Denied'}")

# Filter by tool name
bash_approvals = [r for r in history if r['tool_name'] == 'Bash']
denied_tools = [r for r in history if not r['approved']]
```

---

## Tool Usage Tracking

### Purpose

Track tool invocation counts for:
- Cost estimation and budgeting
- Usage analytics and reporting
- Performance optimization
- Audit trails

### Recording Tool Usage

```python
# Record single tool use
agent.record_tool_usage("Bash")  # Increments by 1
agent.record_tool_usage("Read")

# Record multiple uses at once
agent.record_tool_usage("LLM", increment=5)  # Custom increment

# Track in execution hooks
async def tool_execution_hook(context):
    tool_name = context.data.get("tool_name")
    agent.record_tool_usage(tool_name)
```

### Retrieving Tool Usage Counts

```python
# Get all tool usage counts (returns a copy)
counts = agent._get_tool_usage_counts()

# Access specific tool count
bash_count = counts.get("Bash", 0)
total_llm_calls = counts.get("LLM", 0)

# Calculate total tool invocations
total = sum(counts.values())

# Find most used tools
sorted_tools = sorted(counts.items(), key=lambda x: x[1], reverse=True)
print(f"Most used: {sorted_tools[0][0]} ({sorted_tools[0][1]} times)")
```

### Cost Estimation with Tool Usage

```python
# Define cost per tool
TOOL_COSTS = {
    "LLM": 0.01,      # $0.01 per call
    "Bash": 0.001,    # $0.001 per call
    "Read": 0.0001,   # $0.0001 per call
}

# Calculate total cost
counts = agent._get_tool_usage_counts()
total_cost = sum(
    counts.get(tool, 0) * cost
    for tool, cost in TOOL_COSTS.items()
)
print(f"Estimated cost: ${total_cost:.4f}")
```

---

## Workflow State Tracking

### Purpose

Track Kailash SDK workflow execution state for:
- Checkpoint persistence and recovery
- Debugging and troubleshooting
- Workflow analytics and monitoring
- Integration with Kailash SDK runtime

### Updating Workflow State

```python
# Update with individual fields
agent.update_workflow_state(
    run_id="run_abc123",
    status="running",
    current_node="process_data",
    execution_time=1.5,
)

# Update with additional custom fields
agent.update_workflow_state(
    run_id="run_abc123",
    status="running",
    node_results={"node1": "success", "node2": "pending"},
    error_count=0,
    retry_count=2,
)

# Partial updates preserve existing state
agent.update_workflow_state(status="completed")  # Only updates status
```

### Workflow State Structure

```python
{
    "run_id": "run_abc123",          # Workflow execution ID
    "status": "running",              # Status: running, completed, failed
    "current_node": "process_data",   # Currently executing node
    "node_results": {...},            # Results from completed nodes
    "execution_time": 1.5,            # Total execution time (seconds)
    "last_updated": "2025-01-01T12:00:00.000000",  # Auto-updated
    # ... any additional custom fields
}
```

### Retrieving Workflow State

```python
# Get workflow state (returns a copy)
state = agent._get_workflow_state()

# Access specific fields
run_id = state.get("run_id")
status = state.get("status")
current_node = state.get("current_node")

# Check if workflow is complete
if state.get("status") == "completed":
    print(f"Workflow {run_id} completed in {state.get('execution_time')}s")
```

---

## State Persistence

### Automatic Checkpoint Integration

All tracking state is automatically included in checkpoints:

```python
# Capture state (includes all tracking)
state = agent._capture_state()

# AgentState includes:
# - approval_history: list of approval records
# - tool_usage_counts: dict of tool -> count
# - workflow_state: dict of workflow execution state
# - workflow_run_id: current workflow run ID

print(f"Approvals: {len(state.approval_history)}")
print(f"Tools used: {list(state.tool_usage_counts.keys())}")
print(f"Workflow: {state.workflow_run_id}")
```

### State Restoration

When restoring from a checkpoint, all tracking state is recovered:

```python
# Restore from checkpoint
agent._restore_state(checkpoint_state)

# All tracking state is now restored
history = agent._get_approval_history()  # Restored approvals
counts = agent._get_tool_usage_counts()   # Restored counts
wf_state = agent._get_workflow_state()    # Restored workflow state
```

### Checkpoint Data Structure

```json
{
  "checkpoint_id": "ckpt_abc123",
  "agent_id": "my_agent",
  "timestamp": "2025-01-01T12:00:00",
  "step_number": 5,
  "approval_history": [
    {"tool_name": "Bash", "approved": true, "action": "once", ...}
  ],
  "tool_usage_counts": {"Bash": 3, "Read": 10},
  "workflow_run_id": "run_abc123",
  "workflow_state": {"status": "running", "current_node": "node1", ...}
}
```

---

## Best Practices

### 1. Record Approvals Immediately

```python
# Record approval right after the decision is made
async def handle_tool_approval(tool_name, tool_input, approved, action):
    # Record before executing or skipping tool
    agent.record_approval(tool_name, approved, action, tool_input)

    if not approved:
        raise PermissionError(f"Tool {tool_name} was denied")
```

### 2. Use Consistent Tool Names

```python
# Define tool names as constants
class ToolNames:
    BASH = "Bash"
    READ = "Read"
    WRITE = "Write"
    LLM = "LLM"

# Use constants throughout
agent.record_tool_usage(ToolNames.BASH)
agent.record_approval(ToolNames.WRITE, True)
```

### 3. Track Workflow State at Key Points

```python
# Update at workflow start
agent.update_workflow_state(run_id=run_id, status="running")

# Update at each node
for node in nodes:
    agent.update_workflow_state(current_node=node.id)
    # ... execute node
    agent.update_workflow_state(
        node_results={**state.get("node_results", {}), node.id: result}
    )

# Update at workflow end
agent.update_workflow_state(
    status="completed",
    execution_time=end_time - start_time
)
```

### 4. Preserve State on Errors

```python
try:
    result = await execute_workflow()
    agent.update_workflow_state(status="completed")
except Exception as e:
    agent.update_workflow_state(
        status="failed",
        error_message=str(e),
        error_type=type(e).__name__,
    )
    # State is preserved for debugging
    raise
```

---

## API Reference

### BaseAutonomousAgent Methods

#### `record_approval(tool_name, approved, action="once", tool_input=None)`

Record an approval decision for audit trail and checkpoint persistence.

**Parameters**:
- `tool_name` (str): Name of the tool requiring approval
- `approved` (bool): Whether the tool was approved
- `action` (str): Action type - "once", "all", "deny_all"
- `tool_input` (dict, optional): Tool input for audit context

#### `record_tool_usage(tool_name, increment=1)`

Record tool usage for tracking and analytics.

**Parameters**:
- `tool_name` (str): Name of the tool that was used
- `increment` (int): Amount to increment count by (default: 1)

#### `update_workflow_state(run_id=None, status=None, current_node=None, node_results=None, execution_time=None, **kwargs)`

Update workflow execution state for checkpoint persistence.

**Parameters**:
- `run_id` (str, optional): Workflow execution run ID
- `status` (str, optional): Workflow status (running, completed, failed)
- `current_node` (str, optional): Currently executing node ID
- `node_results` (dict, optional): Results from completed nodes
- `execution_time` (float, optional): Total execution time in seconds
- `**kwargs`: Additional workflow state fields

#### `_get_approval_history() -> List[Dict[str, Any]]`

Get approval history for checkpoint. Returns a copy of the approval records.

#### `_get_tool_usage_counts() -> Dict[str, int]`

Get tool usage counts for checkpoint. Returns a copy of the usage counts.

#### `_get_workflow_state() -> Dict[str, Any]`

Get workflow execution state for checkpoint. Returns a copy of the workflow state.

---

## Related Documentation

- [Checkpoint & Resume System](./checkpoint-resume-system.md)
- [Hooks System](./hooks-system.md)
- [Autonomous Agents](./autonomous-agents.md)
- [Production Deployment](../deployment/production.md)

---

## Changelog

### Version 1.0.0 (2025-12-30)

**Initial Release (TODO-204 Phase 3)**:
- Approval history tracking with audit records
- Tool usage counting with custom increments
- Workflow state integration with Kailash SDK
- Full checkpoint persistence integration
- State restoration from checkpoints
- 21/21 tests passing (100% coverage)

---

**Last Updated**: 2025-12-30
**Maintained By**: Kailash Kaizen Team
