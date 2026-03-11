# Permission System User Guide

**Version**: 1.0
**Last Updated**: 2025-10-25
**Status**: Production-Ready

---

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Permission Modes](#permission-modes)
4. [Budget Management](#budget-management)
5. [Approval Workflows](#approval-workflows)
6. [Permission Rules](#permission-rules)
7. [Integration Guide](#integration-guide)
8. [Best Practices](#best-practices)
9. [Troubleshooting](#troubleshooting)

---

## Overview

The **Permission System** provides fine-grained control over autonomous agent tool execution with budget enforcement, interactive approval workflows, and flexible permission policies.

### Key Features

- **8-Layer Permission Decision Engine**: BYPASS → Budget → PLAN → Denied → Allowed → Rules → Mode Defaults → ASK
- **Budget Enforcement**: Token-based cost tracking with configurable limits
- **Interactive Approval**: User approval requests via Control Protocol
- **Permission Modes**: 4 built-in modes (DEFAULT, BYPASS, ACCEPT_EDITS, PLAN)
- **Custom Rules**: Regex-based tool matching with flexible policies
- **Thread-Safe**: Concurrent execution with lock-based synchronization
- **Production-Ready**: <5ms permission checks, fail-closed design

### Architecture

```
BaseAgent.execute_tool()
    ↓
1. Estimate Cost (BudgetEnforcer)
    ↓
2. Check Permissions (PermissionPolicy)
    ↓
3. Request Approval if needed (ToolApprovalManager)
    ↓
4. Execute Tool (_tool_executor)
    ↓
5. Record Usage (BudgetEnforcer)
```

---

## Quick Start

### Basic Usage (DEFAULT Mode)

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.core.config import BaseAgentConfig
from kaizen.core.autonomy.permissions.types import PermissionMode
from kaizen.signatures import Signature, InputField, OutputField

class TaskSignature(Signature):
    task: str = InputField(description="Task to perform")
    result: str = OutputField(description="Task result")

# Create config with DEFAULT permission mode
config = BaseAgentConfig(
    llm_provider="openai",
    model="gpt-4",
    permission_mode=PermissionMode.DEFAULT,  # Ask for risky operations
    budget_limit_usd=10.0  # $10 budget limit
)

# Create agent with permission system
agent = BaseAgent(
    config=config,
    signature=TaskSignature(),
    control_protocol=my_control_protocol  # Required for approval requests
)

# Execute tool (automatically enforces permissions)
try:
    result = await agent.execute_tool(
        tool_name="Bash",
        params={"command": "ls -la"}
    )
    print(f"Tool executed: {result}")
except PermissionDeniedError as e:
    print(f"Permission denied: {e}")
```

### BYPASS Mode (For Trusted Environments)

```python
config = BaseAgentConfig(
    llm_provider="openai",
    model="gpt-4",
    permission_mode=PermissionMode.BYPASS,  # Auto-approve everything
    budget_limit_usd=None  # Unlimited budget
)

agent = BaseAgent(config=config, signature=TaskSignature())

# All tools execute without approval
result = await agent.execute_tool("Bash", {"command": "ls"})  # ✅ Auto-approved
```

---

## Permission Modes

The permission system supports 4 built-in modes:

### 1. DEFAULT Mode (Recommended)

**Behavior**: Ask user for approval on risky operations.

```python
config = BaseAgentConfig(
    permission_mode=PermissionMode.DEFAULT
)
```

**Rules**:
- ✅ **Safe tools** (Read, Grep, Glob): Auto-approved
- ❓ **Risky tools** (Bash, PythonCode, Write, Edit): Request approval
- ✅ **Budget limits**: Enforced
- ✅ **Custom rules**: Applied

**Use Cases**:
- Interactive development
- User-supervised automation
- Security-sensitive environments

---

### 2. BYPASS Mode (Trusted Environments)

**Behavior**: Auto-approve all operations without checks.

```python
config = BaseAgentConfig(
    permission_mode=PermissionMode.BYPASS,
    budget_limit_usd=None  # Typically unlimited in BYPASS
)
```

**Rules**:
- ✅ **All tools**: Auto-approved
- ⚠️ **Budget limits**: Still enforced (unless None)
- ⚠️ **Denied tools**: Still blocked
- ❌ **Custom rules**: Ignored
- ❌ **Approval requests**: Skipped

**Use Cases**:
- Production environments with external controls
- CI/CD pipelines
- Batch processing
- Sandboxed execution

**⚠️ Security Warning**: Only use in trusted, isolated environments.

---

### 3. ACCEPT_EDITS Mode (File Operations)

**Behavior**: Auto-approve file modifications, ask for other risky tools.

```python
config = BaseAgentConfig(
    permission_mode=PermissionMode.ACCEPT_EDITS
)
```

**Rules**:
- ✅ **File operations** (Write, Edit): Auto-approved
- ✅ **Read operations** (Read, Grep): Auto-approved
- ❓ **System operations** (Bash, PythonCode): Request approval
- ✅ **Budget limits**: Enforced
- ✅ **Custom rules**: Applied

**Use Cases**:
- Code refactoring workflows
- Batch file processing
- Documentation generation
- Safe automation tasks

---

### 4. PLAN Mode (Read-Only)

**Behavior**: Read-only, no execution allowed.

```python
config = BaseAgentConfig(
    permission_mode=PermissionMode.PLAN
)
```

**Rules**:
- ✅ **Read operations** (Read, Grep, Glob): Allowed
- ❌ **Execution operations** (Bash, PythonCode, Write, Edit): Denied
- ✅ **Budget limits**: Enforced (for LLM calls)
- ✅ **Custom rules**: Applied

**Use Cases**:
- Planning and analysis
- Code review
- Security audits
- Information gathering

---

## Budget Management

### Setting Budget Limits

```python
config = BaseAgentConfig(
    permission_mode=PermissionMode.DEFAULT,
    budget_limit_usd=10.0  # $10 limit
)

agent = BaseAgent(config=config, signature=TaskSignature())
```

### Checking Remaining Budget

```python
# Access execution context
remaining = agent.execution_context.budget_limit - agent.execution_context.budget_used
print(f"Remaining budget: ${remaining:.2f}")
```

### Budget Enforcement Flow

```python
# Budget checked BEFORE tool execution (Layer 2 of permission decision)

# Example: Budget exceeded
config = BaseAgentConfig(
    budget_limit_usd=0.01  # $0.01 limit
)

agent = BaseAgent(config=config, signature=TaskSignature())

try:
    # This will fail if estimated cost > remaining budget
    await agent.execute_tool("LLM", {
        "prompt": "Very long prompt...",  # Estimated at $0.05
        "model": "gpt-4"
    })
except PermissionDeniedError as e:
    print(f"Budget exceeded: {e}")
    # Output: "Insufficient budget: estimated $0.05 but only $0.01 remaining"
```

### Tool Cost Estimates

The `BudgetEnforcer` estimates costs for different tool types:

| Tool Type | Cost Estimate | Notes |
|-----------|---------------|-------|
| Read | $0.001 | Fixed cost |
| Write | $0.005 | Fixed cost |
| Edit | $0.005 | Fixed cost |
| Bash | $0.01 | Fixed cost |
| PythonCode | $0.01 | Fixed cost |
| Delete | $0.002 | Fixed cost |
| Grep | $0.001 | Fixed cost |
| Glob | $0.001 | Fixed cost |
| HTTP | $0.005 | Fixed cost |
| WebFetch | $0.01 | Fixed cost |
| LLM | Token-based | Calculated from prompt |
| AgentNode | Token-based | Calculated from messages |
| Unknown tools | $0.01 | Conservative estimate with 20% buffer |

### Unlimited Budget

```python
config = BaseAgentConfig(
    budget_limit_usd=None  # Unlimited budget
)
```

**Note**: Budget tracking is disabled when `budget_limit_usd=None`.

---

## Approval Workflows

### Interactive Approval (DEFAULT Mode)

When a risky tool requires approval, the system sends a request via Control Protocol:

```python
from kaizen.core.autonomy.control.protocol import ControlProtocol
from kaizen.core.autonomy.control.transport import InMemoryTransport

# Setup Control Protocol for approval
transport = InMemoryTransport()
control_protocol = ControlProtocol(transport=transport)

config = BaseAgentConfig(
    permission_mode=PermissionMode.DEFAULT
)

agent = BaseAgent(
    config=config,
    signature=TaskSignature(),
    control_protocol=control_protocol  # Required for approval
)

# Tool execution triggers approval request
result = await agent.execute_tool("Bash", {"command": "ls"})
# → User receives approval prompt via Control Protocol
# → User selects: "Approve Once", "Approve All", "Deny Once", "Deny All"
```

### Approval Prompt Format

The approval manager generates context-aware prompts:

**Bash Tool Example**:
```
⚠️ Tool Approval Required

Tool: Bash
Command: rm -rf /tmp/old_files
Estimated Cost: $0.01
Remaining Budget: $9.99

⚠️ WARNING: System command execution can modify files and system state.

Choose action:
- Approve Once: Allow this execution only
- Approve All: Auto-approve all future "Bash" executions
- Deny Once: Block this execution only
- Deny All: Block all future "Bash" executions
```

**Write Tool Example**:
```
⚠️ Tool Approval Required

Tool: Write
File Path: /app/config.py
Content Preview: def configure_app():\n    return {...
Estimated Cost: $0.005
Remaining Budget: $9.995

⚠️ WARNING: File write operation will overwrite existing content.

Choose action:
- Approve Once
- Approve All
- Deny Once
- Deny All
```

### "Approve All" / "Deny All" Modes

Users can permanently allow or block specific tools:

```python
# User selects "Approve All" for "Bash"
# → agent.execution_context.allowed_tools.add("Bash")
# → All future "Bash" calls auto-approved (Layer 5 of permission decision)

# User selects "Deny All" for "Write"
# → agent.execution_context.denied_tools.add("Write")
# → All future "Write" calls denied (Layer 4 of permission decision)
```

### Timeout Handling

Approval requests have a configurable timeout (default: 60 seconds):

```python
from kaizen.core.autonomy.permissions.approval_manager import ToolApprovalManager

# Custom timeout
approval_manager = ToolApprovalManager(
    control_protocol=control_protocol,
    timeout=30.0  # 30 second timeout
)

# Timeout behavior: Fail-closed (deny execution)
try:
    result = await approval_manager.request_approval(
        tool_name="Bash",
        tool_input={"command": "ls"},
        estimated_cost=0.01,
        context=agent.execution_context
    )
except asyncio.TimeoutError:
    # Approval request timed out → deny execution
    print("Approval timeout: execution denied for security")
```

---

## Permission Rules

### Custom Rules with Regex Matching

Define fine-grained permissions based on tool names and input patterns:

```python
from kaizen.core.autonomy.permissions.types import PermissionRule

# Rule 1: Allow read operations on /app directory
read_app_rule = PermissionRule(
    tool_pattern="Read",
    input_pattern=r"^/app/.*",  # Regex: files starting with /app/
    allowed=True,
    reason="Read access to application directory"
)

# Rule 2: Deny write operations on /etc directory
deny_etc_write = PermissionRule(
    tool_pattern="Write",
    input_pattern=r"^/etc/.*",  # Regex: files starting with /etc/
    allowed=False,
    reason="System directory /etc is protected"
)

# Rule 3: Allow safe bash commands (ls, pwd, echo)
safe_bash = PermissionRule(
    tool_pattern="Bash",
    input_pattern=r"^(ls|pwd|echo).*",  # Regex: commands starting with ls, pwd, or echo
    allowed=True,
    reason="Safe read-only bash commands allowed"
)

# Apply rules to agent config
config = BaseAgentConfig(
    permission_mode=PermissionMode.DEFAULT,
    permission_rules=[read_app_rule, deny_etc_write, safe_bash]
)

agent = BaseAgent(config=config, signature=TaskSignature())
```

### Rule Evaluation (Layer 6)

Rules are evaluated in order until a match is found:

```python
# Example: Read /app/config.py
tool_name = "Read"
tool_input = {"file_path": "/app/config.py"}

# → Checks against rules in order:
# 1. read_app_rule: tool_pattern="Read", input_pattern=r"^/app/.*"
#    → MATCHES! (file_path starts with /app/)
#    → Returns: allowed=True ✅

# Example: Write /etc/hosts
tool_name = "Write"
tool_input = {"file_path": "/etc/hosts"}

# → Checks against rules in order:
# 1. read_app_rule: tool_pattern="Read" → NO MATCH (different tool)
# 2. deny_etc_write: tool_pattern="Write", input_pattern=r"^/etc/.*"
#    → MATCHES! (file_path starts with /etc/)
#    → Returns: allowed=False, reason="System directory /etc is protected" ❌
```

### Input Pattern Matching

Rules match against the first string value found in `tool_input`:

```python
# Input: {"file_path": "/app/config.py", "content": "..."}
# → Checks "file_path" value against input_pattern

# Input: {"command": "ls -la"}
# → Checks "command" value against input_pattern

# Input: {"prompt": "Explain this code"}
# → Checks "prompt" value against input_pattern
```

### Wildcard Rules

```python
# Allow all Read operations
allow_all_reads = PermissionRule(
    tool_pattern="Read",
    input_pattern=r".*",  # Match any input
    allowed=True,
    reason="All reads allowed"
)

# Deny all Bash operations
deny_all_bash = PermissionRule(
    tool_pattern="Bash",
    input_pattern=r".*",  # Match any input
    allowed=False,
    reason="Bash execution disabled"
)
```

---

## Integration Guide

### Step 1: Configure Permission System

```python
from kaizen.core.config import BaseAgentConfig
from kaizen.core.autonomy.permissions.types import PermissionMode, PermissionRule

config = BaseAgentConfig(
    # Base agent config
    llm_provider="openai",
    model="gpt-4",

    # Permission system config
    permission_mode=PermissionMode.DEFAULT,
    budget_limit_usd=50.0,
    allowed_tools={"Read", "Grep"},  # Pre-approved tools
    denied_tools={"Delete"},  # Blocked tools
    permission_rules=[
        PermissionRule(
            tool_pattern="Write",
            input_pattern=r"^/tmp/.*",
            allowed=True,
            reason="Allow writes to /tmp"
        )
    ]
)
```

### Step 2: Create Agent with Control Protocol

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.core.autonomy.control.protocol import ControlProtocol
from kaizen.core.autonomy.control.transport import InMemoryTransport

# Setup Control Protocol
transport = InMemoryTransport()
control_protocol = ControlProtocol(transport=transport)

# Create agent
agent = BaseAgent(
    config=config,
    signature=TaskSignature(),
    control_protocol=control_protocol  # Required for approval workflows
)
```

### Step 3: Execute Tools with Automatic Permission Enforcement

```python
from kaizen.core.autonomy.permissions.types import PermissionDeniedError

async def execute_with_permissions():
    try:
        # Permission flow:
        # 1. Estimate cost → Check budget
        # 2. Check permissions → Apply rules
        # 3. Request approval if needed
        # 4. Execute tool
        # 5. Record actual usage

        result = await agent.execute_tool(
            tool_name="Write",
            params={
                "file_path": "/tmp/output.txt",
                "content": "Hello, World!"
            }
        )

        print(f"Success: {result}")

    except PermissionDeniedError as e:
        print(f"Permission denied: {e}")
        # Handle denial (log, retry with different tool, etc.)
```

### Step 4: Monitor Budget Usage

```python
# Check budget before expensive operations
ctx = agent.execution_context

print(f"Budget limit: ${ctx.budget_limit}")
print(f"Budget used: ${ctx.budget_used:.3f}")
print(f"Remaining: ${ctx.budget_limit - ctx.budget_used:.3f}")

if ctx.has_budget(estimated_cost=1.0):
    result = await agent.execute_tool("LLM", {"prompt": "..."})
else:
    print("Insufficient budget for LLM call")
```

---

## Best Practices

### 1. Choose the Right Permission Mode

| Scenario | Recommended Mode | Reason |
|----------|------------------|--------|
| Interactive development | DEFAULT | User control over risky operations |
| Production with safeguards | BYPASS + denied_tools | Fast execution with critical tool blocks |
| Code refactoring | ACCEPT_EDITS | Auto-approve edits, control system ops |
| Planning/analysis | PLAN | Read-only, no side effects |
| CI/CD pipelines | BYPASS + budget limits | Fast, budget-controlled |

### 2. Set Appropriate Budget Limits

```python
# Development: High limit for experimentation
dev_config = BaseAgentConfig(
    budget_limit_usd=100.0
)

# Production: Conservative limit with monitoring
prod_config = BaseAgentConfig(
    budget_limit_usd=10.0
)

# Batch processing: Unlimited with external controls
batch_config = BaseAgentConfig(
    permission_mode=PermissionMode.BYPASS,
    budget_limit_usd=None
)
```

### 3. Use Denied Tools for Critical Operations

```python
config = BaseAgentConfig(
    permission_mode=PermissionMode.BYPASS,  # Fast execution
    denied_tools={"Delete", "SystemShutdown", "NetworkConfig"}  # Critical blocks
)
```

### 4. Pre-Approve Safe Tools

```python
config = BaseAgentConfig(
    permission_mode=PermissionMode.DEFAULT,
    allowed_tools={"Read", "Grep", "Glob"}  # Skip approval for safe tools
)
```

### 5. Monitor Budget Usage

```python
# Log budget usage after operations
async def execute_with_logging(agent, tool_name, params):
    initial_budget = agent.execution_context.budget_used

    try:
        result = await agent.execute_tool(tool_name, params)
        cost = agent.execution_context.budget_used - initial_budget

        logger.info(f"Tool {tool_name} executed, cost: ${cost:.3f}")

        return result
    except PermissionDeniedError as e:
        logger.warning(f"Tool {tool_name} denied: {e}")
        raise
```

### 6. Handle Approval Timeouts

```python
from kaizen.core.autonomy.permissions.approval_manager import ToolApprovalManager

# Set reasonable timeout for interactive workflows
approval_manager = ToolApprovalManager(
    control_protocol=control_protocol,
    timeout=120.0  # 2 minutes for user to respond
)
```

### 7. Use Permission Rules for Fine-Grained Control

```python
# Principle of least privilege
config = BaseAgentConfig(
    permission_mode=PermissionMode.DEFAULT,
    permission_rules=[
        # Allow specific safe operations
        PermissionRule("Read", r"^/app/data/.*", allowed=True),
        PermissionRule("Write", r"^/tmp/.*", allowed=True),

        # Deny dangerous operations
        PermissionRule("Bash", r".*(rm|del|format).*", allowed=False),
        PermissionRule("Write", r"^/etc/.*", allowed=False),
    ]
)
```

---

## Troubleshooting

### Issue: Permission Denied for Safe Tools

**Symptom**:
```
PermissionDeniedError: Tool 'Read' is explicitly disallowed
```

**Cause**: Tool is in `denied_tools` list.

**Solution**:
```python
# Remove from denied_tools
config = BaseAgentConfig(
    denied_tools=set()  # Clear denied tools
)

# Or explicitly allow
config = BaseAgentConfig(
    allowed_tools={"Read"}
)
```

---

### Issue: Budget Exceeded Unexpectedly

**Symptom**:
```
PermissionDeniedError: Insufficient budget: estimated $0.05 but only $0.01 remaining
```

**Cause**: Budget limit too low or cost estimation inaccurate.

**Solution**:
```python
# Check actual budget usage
print(f"Used: ${agent.execution_context.budget_used}")
print(f"Limit: ${agent.execution_context.budget_limit}")

# Increase budget limit
config = BaseAgentConfig(
    budget_limit_usd=50.0  # Increase from 10.0
)

# Or disable budget limits
config = BaseAgentConfig(
    budget_limit_usd=None
)
```

---

### Issue: Approval Timeout

**Symptom**:
```
Approval timeout for Bash, denying execution
```

**Cause**: User didn't respond within timeout period (default 60s).

**Solution**:
```python
# Increase timeout
approval_manager = ToolApprovalManager(
    control_protocol=control_protocol,
    timeout=180.0  # 3 minutes
)

# Or use BYPASS mode for non-interactive scenarios
config = BaseAgentConfig(
    permission_mode=PermissionMode.BYPASS
)
```

---

### Issue: Control Protocol Not Configured

**Symptom**:
```
RuntimeError: Approval manager not configured but approval required
```

**Cause**: No `control_protocol` provided to BaseAgent when using DEFAULT mode.

**Solution**:
```python
from kaizen.core.autonomy.control.protocol import ControlProtocol
from kaizen.core.autonomy.control.transport import InMemoryTransport

# Setup Control Protocol
transport = InMemoryTransport()
control_protocol = ControlProtocol(transport=transport)

# Pass to BaseAgent
agent = BaseAgent(
    config=config,
    signature=signature,
    control_protocol=control_protocol  # Required for DEFAULT mode
)
```

---

### Issue: Permission Rules Not Matching

**Symptom**: Rules defined but not being applied.

**Cause**: Regex pattern doesn't match input.

**Solution**:
```python
# Debug rule matching
import re

tool_pattern = "Write"
input_pattern = r"^/app/.*"
tool_input = {"file_path": "/tmp/output.txt"}

# Find first string value in input
first_string = next(
    (v for v in tool_input.values() if isinstance(v, str)),
    None
)

print(f"First string: {first_string}")
print(f"Pattern match: {bool(re.match(input_pattern, first_string))}")

# Output:
# First string: /tmp/output.txt
# Pattern match: False (doesn't start with /app/)

# Fix: Adjust pattern to match actual input
correct_pattern = r"^/tmp/.*"
```

---

## Next Steps

- **[Security Best Practices](permission-security-best-practices.md)** - Security guidelines and threat mitigation
- **[Budget Management Guide](permission-budget-management.md)** - Advanced budget strategies
- **[Approval Workflow Guide](permission-approval-workflows.md)** - Custom approval patterns
- **[Troubleshooting Guide](permission-troubleshooting.md)** - Common issues and solutions

---

**© 2025 Kailash Kaizen | Permission System v1.0**
