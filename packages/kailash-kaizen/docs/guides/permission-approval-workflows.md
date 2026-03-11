# Permission System Approval Workflows Guide

**Version**: 1.0
**Last Updated**: 2025-10-25
**Focus**: Interactive Approval Patterns

---

## Table of Contents

1. [Overview](#overview)
2. [Approval Architecture](#approval-architecture)
3. [Control Protocol Integration](#control-protocol-integration)
4. [Approval Prompts](#approval-prompts)
5. [Approval Modes](#approval-modes)
6. [Custom Approval Flows](#custom-approval-flows)
7. [Timeout Handling](#timeout-handling)
8. [Multi-User Approvals](#multi-user-approvals)
9. [Approval Analytics](#approval-analytics)
10. [Best Practices](#best-practices)

---

## Overview

The **Approval Workflow System** provides human-in-the-loop control for risky autonomous operations with:

- **Context-Aware Prompts**: Different templates for Bash, Write, and generic tools
- **Risk Warnings**: Highlight dangerous operations to users
- **Persistent Decisions**: "Approve All" / "Deny All" for efficiency
- **Timeout Enforcement**: Fail-closed design (deny on timeout)
- **Budget Visibility**: Show remaining budget in approval requests
- **Performance**: <100ms approval requests (ADR-012 NFR-3)

### Key Concept: Ask Mode

```
Permission Decision Flow:
    ↓
1. Check Permission Policy
    ↓
2. Returns: allowed=True → Auto-approve ✅
   Returns: allowed=False → Deny ❌
   Returns: allowed=None → ASK mode ❓
    ↓
3. Send Approval Request via Control Protocol
    ↓
4. User Responds:
   - "Approve Once" → Execute this time only
   - "Approve All" → Add to allowed_tools (future auto-approve)
   - "Deny Once" → Block this time only
   - "Deny All" → Add to denied_tools (future auto-deny)
    ↓
5. Execute or Deny based on user response
```

---

## Approval Architecture

### Components

```
┌──────────────────────────────────────────┐
│   ToolApprovalManager                     │
│   - control_protocol: ControlProtocol     │  ← Transport for approval requests
│   - timeout: float (default 60s)          │  ← Request timeout
│   - request_approval() → bool             │  ← Send approval request
│   - _generate_prompt() → str              │  ← Create context-aware prompts
└──────────────┬───────────────────────────┘
               │
               ↓
┌──────────────────────────────────────────┐
│   ControlProtocol                         │
│   - transport: Transport                  │  ← InMemory / HTTP / SSE / stdio
│   - send_request() → ControlResponse      │  ← Send/receive approval
└──────────────┬───────────────────────────┘
               │
               ↓
┌──────────────────────────────────────────┐
│   User Interface                          │
│   - Display approval prompt               │  ← CLI / Web / Desktop UI
│   - Capture user response                 │  ← Button click / keyboard input
│   - Return choice to Control Protocol     │  ← "Approve Once", "Deny All", etc.
└───────────────────────────────────────────┘
```

### Approval Flow in execute_tool()

```python
# BaseAgent.execute_tool() approval step
async def execute_tool(self, tool_name: str, params: dict) -> Any:
    # ... Steps 1-2: Estimate cost, check permissions ...

    # STEP 3: Request approval if needed
    if allowed is None:  # ASK mode
        if self.approval_manager is None:
            raise RuntimeError("Approval manager not configured but approval required")

        approved = await self.approval_manager.request_approval(
            tool_name=tool_name,
            tool_input=params,
            estimated_cost=estimated_cost,
            context=self.execution_context
        )

        if not approved:
            raise PermissionDeniedError(f"User denied approval for {tool_name}")

    # STEP 4: Execute tool (only if approved)
    result = await self._tool_executor.execute(tool_name, params)

    # ...
```

---

## Control Protocol Integration

### Setup

```python
from kaizen.core.autonomy.control.protocol import ControlProtocol
from kaizen.core.autonomy.control.transport import InMemoryTransport
from kaizen.core.autonomy.permissions.approval_manager import ToolApprovalManager

# 1. Create transport
transport = InMemoryTransport()

# 2. Create Control Protocol
control_protocol = ControlProtocol(transport=transport)

# 3. Create Approval Manager
approval_manager = ToolApprovalManager(
    control_protocol=control_protocol,
    timeout=60.0  # 60 second timeout
)

# 4. Create BaseAgent with approval support
agent = BaseAgent(
    config=config,
    signature=signature,
    control_protocol=control_protocol  # Required for approvals
)

# approval_manager automatically created in BaseAgent.__init__()
```

### Transport Options

```python
# Option 1: In-Memory (for testing, single-process)
from kaizen.core.autonomy.control.transport import InMemoryTransport

transport = InMemoryTransport()

# Option 2: HTTP (for web applications)
from kaizen.core.autonomy.control.transport import HTTPTransport

transport = HTTPTransport(
    client_url="http://localhost:8000/approval",
    server_port=8001
)

# Option 3: SSE (Server-Sent Events, for real-time updates)
from kaizen.core.autonomy.control.transport import SSETransport

transport = SSETransport(
    server_port=8002,
    endpoint="/events"
)

# Option 4: stdio (for CLI applications)
from kaizen.core.autonomy.control.transport import StdioTransport

transport = StdioTransport()
```

---

## Approval Prompts

### Bash Tool Prompt

```python
# Template: approval_manager._generate_bash_prompt()

"""
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
"""
```

**Prompt Components**:
1. **Tool identification**: "Tool: Bash"
2. **Command preview**: "Command: rm -rf /tmp/old_files"
3. **Cost visibility**: "Estimated Cost: $0.01"
4. **Budget awareness**: "Remaining Budget: $9.99"
5. **Risk warning**: "System command execution can modify files..."
6. **Action choices**: Approve Once/All, Deny Once/All

---

### Write Tool Prompt

```python
# Template: approval_manager._generate_write_prompt()

"""
⚠️ Tool Approval Required

Tool: Write
File Path: /app/config.py
Content Preview:
def configure_app():
    return {
        "debug": True,
        ...
    }

Estimated Cost: $0.005
Remaining Budget: $9.995

⚠️ WARNING: File write operation will overwrite existing content.

Choose action:
- Approve Once: Allow this execution only
- Approve All: Auto-approve all future "Write" executions
- Deny Once: Block this execution only
- Deny All: Block all future "Write" executions
"""
```

**Write-Specific Features**:
1. **File path**: Show exact file being modified
2. **Content preview**: Show first 100 chars of content
3. **Overwrite warning**: Highlight data loss risk

---

### Generic Tool Prompt

```python
# Template: approval_manager._generate_generic_prompt()

"""
⚠️ Tool Approval Required

Tool: LLM
Parameters:
- prompt: "Explain quantum mechanics in detail"
- model: "gpt-4"

Estimated Cost: $0.05
Remaining Budget: $9.95

Choose action:
- Approve Once: Allow this execution only
- Approve All: Auto-approve all future "LLM" executions
- Deny Once: Block this execution only
- Deny All: Block all future "LLM" executions
"""
```

**Generic Template**:
- **Parameters**: Show all tool input parameters
- **No risk warning**: For non-risky tools (Read, HTTP, etc.)

---

### Custom Prompts

```python
# Extend ToolApprovalManager for custom prompts
class CustomApprovalManager(ToolApprovalManager):
    def _generate_prompt(self, tool_name, tool_input, cost, context):
        """Override for custom prompt generation."""

        # Custom prompt for LLM tool
        if tool_name == "LLM":
            return f"""
🤖 AI Model Approval Required

Model: {tool_input.get('model', 'default')}
Prompt Length: {len(tool_input.get('prompt', ''))} characters
Estimated Cost: ${cost:.3f}
Remaining Budget: ${context.budget_limit - context.budget_used:.3f}

Prompt Preview:
{tool_input.get('prompt', '')[:200]}...

⚠️ This will call OpenAI API and consume budget.

Approve this call?
"""

        # Delegate to parent for other tools
        return super()._generate_prompt(tool_name, tool_input, cost, context)

# Usage
custom_approval = CustomApprovalManager(
    control_protocol=control_protocol,
    timeout=60.0
)
```

---

## Approval Modes

### Approve Once

**Behavior**: Approve this single execution only.

```python
# User clicks "Approve Once"
# → Tool executes this time
# → Next call to same tool → asks again

# Example
await agent.execute_tool("Bash", {"command": "ls"})
# → Approval request sent
# → User: "Approve Once"
# → Tool executes ✅

await agent.execute_tool("Bash", {"command": "pwd"})
# → Approval request sent AGAIN
# → User must respond again
```

**Use Cases**:
- Review each operation individually
- High-security environments
- Untrusted agents

---

### Approve All

**Behavior**: Permanently allow this tool for the session.

```python
# User clicks "Approve All"
# → agent.execution_context.allowed_tools.add("Bash")
# → All future "Bash" calls auto-approved

# Example
await agent.execute_tool("Bash", {"command": "ls"})
# → Approval request sent
# → User: "Approve All"
# → Tool executes ✅
# → "Bash" added to allowed_tools

await agent.execute_tool("Bash", {"command": "pwd"})
# → NO approval request (already in allowed_tools)
# → Tool executes ✅ (auto-approved)

await agent.execute_tool("Bash", {"command": "whoami"})
# → NO approval request
# → Tool executes ✅ (auto-approved)
```

**Use Cases**:
- Reduce approval fatigue
- Trust established for specific tool
- Batch operations

**Security Note**: Adds tool to allowed_tools for **entire session**, not just specific input.

---

### Deny Once

**Behavior**: Block this single execution only.

```python
# User clicks "Deny Once"
# → Tool execution blocked this time
# → PermissionDeniedError raised
# → Next call to same tool → asks again

# Example
await agent.execute_tool("Write", {"file_path": "/etc/hosts"})
# → Approval request sent
# → User: "Deny Once"
# → PermissionDeniedError raised ❌

await agent.execute_tool("Write", {"file_path": "/tmp/output.txt"})
# → Approval request sent AGAIN
# → User can approve this safer operation
```

**Use Cases**:
- Block specific dangerous operation
- Allow tool in general but not this instance
- Temporary denial

---

### Deny All

**Behavior**: Permanently block this tool for the session.

```python
# User clicks "Deny All"
# → agent.execution_context.denied_tools.add("Delete")
# → All future "Delete" calls auto-denied

# Example
await agent.execute_tool("Delete", {"file_path": "/tmp/temp.txt"})
# → Approval request sent
# → User: "Deny All"
# → PermissionDeniedError raised ❌
# → "Delete" added to denied_tools

await agent.execute_tool("Delete", {"file_path": "/tmp/old.log"})
# → NO approval request (already in denied_tools)
# → PermissionDeniedError raised ❌ (auto-denied)
```

**Use Cases**:
- Block dangerous tools for entire session
- Enforce read-only operations
- Prevent accidental destructive actions

---

## Custom Approval Flows

### Workflow 1: Two-Factor Approval

```python
# Require approval from 2 different users for critical operations
class TwoFactorApprovalManager(ToolApprovalManager):
    def __init__(self, control_protocol, timeout=60.0, critical_tools=None):
        super().__init__(control_protocol, timeout)
        self.critical_tools = critical_tools or {"Delete", "Bash"}

    async def request_approval(self, tool_name, tool_input, estimated_cost, context):
        """Override to require 2 approvals for critical tools."""

        if tool_name in self.critical_tools:
            # First approval
            prompt1 = f"⚠️ CRITICAL OPERATION - First Approval Required\n\n{self._generate_prompt(tool_name, tool_input, estimated_cost, context)}"

            request1 = ControlRequest.create(
                request_type="approval",
                question=prompt1,
                choices=["Approve", "Deny"]
            )

            response1 = await self.control_protocol.send_request(request1, timeout=self.timeout)

            if not response1.approved:
                return False

            # Second approval (different user via different transport)
            prompt2 = f"⚠️ CRITICAL OPERATION - Second Approval Required\n\n{self._generate_prompt(tool_name, tool_input, estimated_cost, context)}"

            request2 = ControlRequest.create(
                request_type="approval",
                question=prompt2,
                choices=["Approve", "Deny"]
            )

            response2 = await self.control_protocol.send_request(request2, timeout=self.timeout)

            return response2.approved

        # Non-critical tools: single approval
        return await super().request_approval(tool_name, tool_input, estimated_cost, context)

# Usage
two_factor_approval = TwoFactorApprovalManager(
    control_protocol=control_protocol,
    critical_tools={"Delete", "Bash", "SystemShutdown"}
)
```

---

### Workflow 2: Role-Based Approvals

```python
# Different approval requirements based on user role
class RoleBasedApprovalManager(ToolApprovalManager):
    def __init__(self, control_protocol, user_role, timeout=60.0):
        super().__init__(control_protocol, timeout)
        self.user_role = user_role

    async def request_approval(self, tool_name, tool_input, estimated_cost, context):
        """Role-based approval logic."""

        # Admin: Auto-approve everything
        if self.user_role == "admin":
            logger.info(f"Admin auto-approval: {tool_name}")
            return True

        # Developer: Auto-approve non-destructive tools
        if self.user_role == "developer":
            safe_tools = {"Read", "Grep", "Glob", "HTTP", "LLM"}
            if tool_name in safe_tools:
                logger.info(f"Developer auto-approval: {tool_name}")
                return True

        # Viewer: Always require approval (or deny destructive)
        if self.user_role == "viewer":
            destructive_tools = {"Write", "Edit", "Delete", "Bash"}
            if tool_name in destructive_tools:
                logger.warning(f"Viewer denied destructive tool: {tool_name}")
                return False

        # Default: Request approval
        return await super().request_approval(tool_name, tool_input, estimated_cost, context)

# Usage
admin_approval = RoleBasedApprovalManager(control_protocol, user_role="admin")
dev_approval = RoleBasedApprovalManager(control_protocol, user_role="developer")
viewer_approval = RoleBasedApprovalManager(control_protocol, user_role="viewer")
```

---

### Workflow 3: Time-Based Approvals

```python
# Different approval logic based on time of day
import datetime

class TimeBasedApprovalManager(ToolApprovalManager):
    def is_business_hours(self) -> bool:
        """Check if current time is business hours (9 AM - 5 PM weekdays)."""
        now = datetime.datetime.now()

        # Weekend: Not business hours
        if now.weekday() >= 5:  # Saturday = 5, Sunday = 6
            return False

        # Business hours: 9 AM - 5 PM
        return 9 <= now.hour < 17

    async def request_approval(self, tool_name, tool_input, estimated_cost, context):
        """Time-based approval logic."""

        # During business hours: Allow risky tools with approval
        if self.is_business_hours():
            return await super().request_approval(tool_name, tool_input, estimated_cost, context)

        # After hours: Deny risky tools (no human available to approve)
        risky_tools = {"Bash", "Delete", "Write", "Edit"}
        if tool_name in risky_tools:
            logger.warning(f"After-hours denial: {tool_name}")
            return False

        # Safe tools: Auto-approve even after hours
        return True

# Usage
time_based_approval = TimeBasedApprovalManager(
    control_protocol=control_protocol
)
```

---

### Workflow 4: Cost-Threshold Approvals

```python
# Require approval only for expensive operations
class CostThresholdApprovalManager(ToolApprovalManager):
    def __init__(self, control_protocol, cost_threshold=1.0, timeout=60.0):
        super().__init__(control_protocol, timeout)
        self.cost_threshold = cost_threshold

    async def request_approval(self, tool_name, tool_input, estimated_cost, context):
        """Approval required only if cost exceeds threshold."""

        # Cheap operation: Auto-approve
        if estimated_cost < self.cost_threshold:
            logger.info(f"Auto-approved (cost ${estimated_cost:.3f} < threshold ${self.cost_threshold})")
            return True

        # Expensive operation: Request approval
        logger.warning(f"Approval required (cost ${estimated_cost:.3f} >= threshold ${self.cost_threshold})")

        # Add cost warning to prompt
        original_prompt = self._generate_prompt(tool_name, tool_input, estimated_cost, context)

        enhanced_prompt = f"""
💰 EXPENSIVE OPERATION DETECTED

{original_prompt}

⚠️ This operation costs ${estimated_cost:.2f}, which exceeds the ${self.cost_threshold:.2f} threshold.
"""

        request = ControlRequest.create(
            request_type="approval",
            question=enhanced_prompt,
            choices=["Approve Once", "Approve All", "Deny Once", "Deny All"]
        )

        response = await self.control_protocol.send_request(request, timeout=self.timeout)

        # Handle "Approve All" / "Deny All"
        if response.action == "all":
            if response.approved:
                context.allowed_tools.add(tool_name)
            else:
                context.denied_tools.add(tool_name)

        return response.approved

# Usage
cost_threshold_approval = CostThresholdApprovalManager(
    control_protocol=control_protocol,
    cost_threshold=0.50  # Approve operations < $0.50
)
```

---

## Timeout Handling

### Default Timeout Behavior

```python
# Default: 60 second timeout, fail-closed
approval_manager = ToolApprovalManager(
    control_protocol=control_protocol,
    timeout=60.0  # Deny after 60 seconds
)

# Timeout scenario
try:
    approved = await approval_manager.request_approval(
        tool_name="Bash",
        tool_input={"command": "ls"},
        estimated_cost=0.01,
        context=agent.execution_context
    )
except asyncio.TimeoutError:
    # User didn't respond within 60 seconds
    # → Fail-closed: Deny execution
    logger.warning("Approval timeout: execution denied")
    approved = False

if not approved:
    raise PermissionDeniedError("Approval timeout")
```

### Custom Timeout

```python
# Short timeout for production
prod_approval = ToolApprovalManager(
    control_protocol=control_protocol,
    timeout=30.0  # 30 second timeout
)

# Long timeout for interactive development
dev_approval = ToolApprovalManager(
    control_protocol=control_protocol,
    timeout=300.0  # 5 minute timeout
)
```

### Timeout Retry Logic

```python
# Retry approval request on timeout
async def request_approval_with_retry(
    approval_manager: ToolApprovalManager,
    tool_name: str,
    tool_input: dict,
    estimated_cost: float,
    context: ExecutionContext,
    max_retries: int = 2
):
    """Request approval with retry on timeout."""

    for attempt in range(max_retries + 1):
        try:
            approved = await approval_manager.request_approval(
                tool_name, tool_input, estimated_cost, context
            )
            return approved

        except asyncio.TimeoutError:
            if attempt < max_retries:
                logger.warning(f"Approval timeout (attempt {attempt + 1}/{max_retries + 1}), retrying...")
                await asyncio.sleep(1)
            else:
                logger.error("Max approval retries exceeded, denying execution")
                return False

# Usage
approved = await request_approval_with_retry(
    approval_manager,
    "Bash",
    {"command": "ls"},
    0.01,
    agent.execution_context,
    max_retries=2
)
```

---

## Multi-User Approvals

### Concurrent User Approval

```python
# Multiple users can respond to approval requests
class MultiUserApprovalManager(ToolApprovalManager):
    def __init__(self, control_protocols: List[ControlProtocol], timeout=60.0):
        """
        Multi-user approval manager.

        Args:
            control_protocols: List of control protocols (one per user)
            timeout: Timeout per approval request
        """
        self.control_protocols = control_protocols
        self.timeout = timeout

    async def request_approval(self, tool_name, tool_input, estimated_cost, context):
        """Send approval request to all users, accept first response."""

        prompt = self._generate_prompt(tool_name, tool_input, estimated_cost, context)

        request = ControlRequest.create(
            request_type="approval",
            question=prompt,
            choices=["Approve Once", "Approve All", "Deny Once", "Deny All"]
        )

        # Send to all users concurrently
        tasks = [
            protocol.send_request(request, timeout=self.timeout)
            for protocol in self.control_protocols
        ]

        # Wait for first response (race)
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

        # Cancel pending requests
        for task in pending:
            task.cancel()

        # Get first response
        response = done.pop().result()

        # Handle "Approve All" / "Deny All"
        if response.action == "all":
            if response.approved:
                context.allowed_tools.add(tool_name)
            else:
                context.denied_tools.add(tool_name)

        return response.approved

# Usage
user1_protocol = ControlProtocol(InMemoryTransport())
user2_protocol = ControlProtocol(HTTPTransport(client_url="http://user2:8000"))
user3_protocol = ControlProtocol(SSETransport(server_port=8002))

multi_user_approval = MultiUserApprovalManager(
    control_protocols=[user1_protocol, user2_protocol, user3_protocol]
)
```

---

## Approval Analytics

### Tracking Approval Metrics

```python
# Track approval/denial rates
class ApprovalAnalytics:
    def __init__(self):
        self.approvals = 0
        self.denials = 0
        self.timeouts = 0
        self.tool_stats = {}

    def record_approval(self, tool_name: str, approved: bool, timeout: bool = False):
        """Record approval decision."""
        if timeout:
            self.timeouts += 1
        elif approved:
            self.approvals += 1
        else:
            self.denials += 1

        # Per-tool stats
        if tool_name not in self.tool_stats:
            self.tool_stats[tool_name] = {"approvals": 0, "denials": 0, "timeouts": 0}

        if timeout:
            self.tool_stats[tool_name]["timeouts"] += 1
        elif approved:
            self.tool_stats[tool_name]["approvals"] += 1
        else:
            self.tool_stats[tool_name]["denials"] += 1

    def get_summary(self) -> dict:
        """Get approval analytics summary."""
        total = self.approvals + self.denials + self.timeouts

        return {
            "total_requests": total,
            "approvals": self.approvals,
            "denials": self.denials,
            "timeouts": self.timeouts,
            "approval_rate": self.approvals / total if total > 0 else 0.0,
            "denial_rate": self.denials / total if total > 0 else 0.0,
            "timeout_rate": self.timeouts / total if total > 0 else 0.0,
            "tool_stats": self.tool_stats
        }

# Usage
analytics = ApprovalAnalytics()

# Track each approval
approved = await approval_manager.request_approval(...)
analytics.record_approval("Bash", approved=approved)

# Get summary
summary = analytics.get_summary()
print(f"Approval rate: {summary['approval_rate']*100:.1f}%")
print(f"Denial rate: {summary['denial_rate']*100:.1f}%")
print(f"Timeout rate: {summary['timeout_rate']*100:.1f}%")
```

---

## Best Practices

### 1. Choose Appropriate Timeout

```python
# Interactive UI: Longer timeout (users need time to read)
ui_approval = ToolApprovalManager(control_protocol, timeout=120.0)

# CLI: Medium timeout (users are active)
cli_approval = ToolApprovalManager(control_protocol, timeout=60.0)

# Automated: Short timeout or no approval
auto_approval = ToolApprovalManager(control_protocol, timeout=10.0)
```

### 2. Provide Clear Context in Prompts

```python
# ✅ GOOD: Specific, actionable information
"""
⚠️ Tool Approval Required

Tool: Bash
Command: rm -rf /tmp/old_files
Target: 47 files (estimated)
Estimated Cost: $0.01
Remaining Budget: $9.99

⚠️ WARNING: This will permanently delete 47 files from /tmp/old_files.
"""

# ❌ BAD: Vague, no context
"""
Approve tool execution?
"""
```

### 3. Use "Approve All" Wisely

```python
# ✅ GOOD: Safe for trusted, repetitive operations
# User approves "Read" with "Approve All"
# → Future reads auto-approved (safe, read-only)

# ⚠️ CAUTION: Risky for destructive operations
# User approves "Delete" with "Approve All"
# → Future deletes auto-approved (DANGEROUS!)

# Mitigation: Warn users about "Approve All" for risky tools
if tool_name in {"Delete", "Bash", "PythonCode"}:
    prompt += "\n\n⚠️ WARNING: 'Approve All' will auto-approve ALL future executions of this tool, including potentially dangerous operations."
```

### 4. Monitor Approval Patterns

```python
# High denial rate → agent is misbehaving or rules too strict
# High timeout rate → users are unavailable or prompts unclear
# 100% approval rate → users not reviewing carefully (approval fatigue)

# Alert on anomalies
if analytics.denial_rate > 0.50:
    logger.warning("High denial rate (>50%), review agent behavior")

if analytics.timeout_rate > 0.30:
    logger.warning("High timeout rate (>30%), check user availability")

if analytics.approval_rate == 1.0 and total_requests > 20:
    logger.info("100% approval rate, possible approval fatigue")
```

### 5. Fail-Closed Always

```python
# ✅ GOOD: Deny on error or timeout
try:
    approved = await approval_manager.request_approval(...)
except Exception as e:
    logger.error(f"Approval request failed: {e}")
    approved = False  # Fail-closed

# ❌ BAD: Approve on error (security risk!)
try:
    approved = await approval_manager.request_approval(...)
except Exception as e:
    logger.error(f"Approval request failed: {e}")
    approved = True  # DANGEROUS! ⚠️
```

---

## Summary

**Approval Workflow Patterns**:

| Pattern | Use Case | Security | UX |
|---------|----------|----------|-----|
| **Approve Once** | High-security, review each operation | **HIGH** | Low (approval fatigue) |
| **Approve All** | Trusted operations, batch processing | **MEDIUM** | High (reduces interruptions) |
| **Two-Factor** | Critical operations, compliance | **VERY HIGH** | Low (2x approvals) |
| **Role-Based** | Multi-user environments, RBAC | **HIGH** | Medium (automatic for some users) |
| **Time-Based** | Business hours automation | **MEDIUM** | Medium (transparent) |
| **Cost-Threshold** | Budget-aware approvals | **MEDIUM** | High (only expensive ops) |

**Next Steps**:

- **[Permission System User Guide](permission-system-user-guide.md)** - Complete usage guide
- **[Security Best Practices](permission-security-best-practices.md)** - Security hardening
- **[Troubleshooting Guide](permission-troubleshooting.md)** - Common approval issues

---

**© 2025 Kailash Kaizen | Approval Workflows v1.0**
