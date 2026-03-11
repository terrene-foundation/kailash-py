# Permission System Troubleshooting Guide

**Version**: 1.0
**Last Updated**: 2025-10-25
**Focus**: Common Issues & Solutions

---

## Table of Contents

1. [Quick Diagnostics](#quick-diagnostics)
2. [Permission Denied Errors](#permission-denied-errors)
3. [Budget Issues](#budget-issues)
4. [Approval Workflow Issues](#approval-workflow-issues)
5. [Rule Matching Problems](#rule-matching-problems)
6. [Integration Issues](#integration-issues)
7. [Performance Problems](#performance-problems)
8. [Debugging Tools](#debugging-tools)

---

## Quick Diagnostics

### Permission System Health Check

```python
# Run this to diagnose permission system issues
def diagnose_permission_system(agent: BaseAgent):
    """Comprehensive permission system diagnostics."""

    print("=== Permission System Diagnostics ===\n")

    # 1. Check configuration
    print("1. Configuration:")
    print(f"   Permission Mode: {agent.execution_context.mode}")
    print(f"   Budget Limit: ${agent.execution_context.budget_limit}")
    print(f"   Budget Used: ${agent.execution_context.budget_used:.3f}")
    print(f"   Allowed Tools: {agent.execution_context.allowed_tools}")
    print(f"   Denied Tools: {agent.execution_context.denied_tools}")
    print(f"   Permission Rules: {len(agent.execution_context.rules)} rules\n")

    # 2. Check permission policy
    print("2. Permission Policy:")
    if agent.permission_policy:
        print("   ✅ Permission policy configured")
    else:
        print("   ❌ Permission policy NOT configured")
    print()

    # 3. Check approval manager
    print("3. Approval Manager:")
    if agent.approval_manager:
        print("   ✅ Approval manager configured")
        print(f"   Timeout: {agent.approval_manager.timeout}s")
    else:
        print("   ❌ Approval manager NOT configured")
        print("   ⚠️  Approval requests will fail in DEFAULT mode")
    print()

    # 4. Check Control Protocol
    print("4. Control Protocol:")
    if agent.approval_manager and agent.approval_manager.control_protocol:
        print("   ✅ Control protocol configured")
    else:
        print("   ❌ Control protocol NOT configured")
        print("   ⚠️  Approval workflows unavailable")
    print()

    # 5. Test permission check
    print("5. Test Permission Checks:")
    test_tools = ["Read", "Write", "Bash"]
    for tool in test_tools:
        try:
            allowed, reason = agent.permission_policy.check_permission(
                tool, {}, estimated_cost=0.01
            )

            if allowed is True:
                status = "✅ AUTO-APPROVED"
            elif allowed is False:
                status = f"❌ DENIED ({reason})"
            else:
                status = "❓ REQUIRES APPROVAL"

            print(f"   {tool}: {status}")
        except Exception as e:
            print(f"   {tool}: ❌ ERROR ({e})")
    print()

    # 6. Budget check
    print("6. Budget Status:")
    if agent.execution_context.budget_limit:
        remaining = agent.execution_context.budget_limit - agent.execution_context.budget_used
        usage_percent = (agent.execution_context.budget_used / agent.execution_context.budget_limit) * 100

        print(f"   Remaining: ${remaining:.2f} ({100-usage_percent:.1f}%)")

        if usage_percent > 90:
            print("   ⚠️  Budget 90% exhausted!")
        elif usage_percent > 75:
            print("   ⚠️  Budget 75% used")
    else:
        print("   ∞ Unlimited budget")
    print()

# Usage
diagnose_permission_system(agent)
```

**Output Example**:
```
=== Permission System Diagnostics ===

1. Configuration:
   Permission Mode: DEFAULT
   Budget Limit: $10.0
   Budget Used: $2.456
   Allowed Tools: {'Read', 'Grep'}
   Denied Tools: {'Delete'}
   Permission Rules: 3 rules

2. Permission Policy:
   ✅ Permission policy configured

3. Approval Manager:
   ✅ Approval manager configured
   Timeout: 60.0s

4. Control Protocol:
   ✅ Control protocol configured

5. Test Permission Checks:
   Read: ✅ AUTO-APPROVED
   Write: ❓ REQUIRES APPROVAL
   Bash: ❓ REQUIRES APPROVAL

6. Budget Status:
   Remaining: $7.54 (75.4%)
```

---

## Permission Denied Errors

### Issue 1: "Tool is explicitly disallowed"

**Symptom**:
```python
PermissionDeniedError: Tool 'Bash' is explicitly disallowed
```

**Cause**: Tool is in `denied_tools` set.

**Diagnosis**:
```python
print(f"Denied tools: {agent.execution_context.denied_tools}")
# Output: Denied tools: {'Bash', 'Delete'}
```

**Solution**:
```python
# Option 1: Remove from denied_tools
agent.execution_context.denied_tools.remove("Bash")

# Option 2: Reconfigure agent without denial
config = BaseAgentConfig(
    permission_mode=PermissionMode.DEFAULT,
    denied_tools=set()  # Clear denied tools
)

# Option 3: Use BYPASS mode (if appropriate)
config = BaseAgentConfig(
    permission_mode=PermissionMode.BYPASS
)
```

---

### Issue 2: "Permission denied in PLAN mode"

**Symptom**:
```python
PermissionDeniedError: Tool 'Write' not allowed in PLAN mode (read-only)
```

**Cause**: PLAN mode only allows read operations.

**Diagnosis**:
```python
print(f"Permission mode: {agent.execution_context.mode}")
# Output: Permission mode: PLAN
```

**Solution**:
```python
# Option 1: Switch to different mode
config = BaseAgentConfig(
    permission_mode=PermissionMode.DEFAULT  # Allow writes with approval
)

# Option 2: Use ACCEPT_EDITS mode for file operations
config = BaseAgentConfig(
    permission_mode=PermissionMode.ACCEPT_EDITS  # Auto-approve writes
)

# Option 3: Use read-only equivalent
# Instead of Write, use analysis tools
await agent.execute_tool("Read", {"file_path": "..."})  # ✅ Allowed in PLAN
```

---

### Issue 3: "Permission denied by rule"

**Symptom**:
```python
PermissionDeniedError: System directory /etc is protected
```

**Cause**: Permission rule blocked the operation.

**Diagnosis**:
```python
# Check which rule matched
for rule in agent.execution_context.rules:
    print(f"Rule: {rule.tool_pattern} + {rule.input_pattern} → {rule.allowed}")

# Example output:
# Rule: Write + ^/etc/.* → False (DENY)
# Rule: Write + ^/app/.* → True (ALLOW)
```

**Solution**:
```python
# Option 1: Modify rule to allow specific path
modified_rule = PermissionRule(
    tool_pattern="Write",
    input_pattern=r"^/etc/myapp/.*",  # Allow specific subdirectory
    allowed=True,
    reason="Application config directory"
)

config = BaseAgentConfig(
    permission_rules=[modified_rule]
)

# Option 2: Remove restrictive rule
config = BaseAgentConfig(
    permission_rules=[]  # No rules
)

# Option 3: Use different file path
await agent.execute_tool("Write", {
    "file_path": "/app/config.py"  # Allowed by rule
})
```

---

### Issue 4: "User denied approval"

**Symptom**:
```python
PermissionDeniedError: User denied approval for Bash
```

**Cause**: User clicked "Deny Once" or "Deny All" in approval prompt.

**Diagnosis**:
```python
# Check if tool was permanently denied
print(f"Denied tools: {agent.execution_context.denied_tools}")

# If "Bash" is in denied_tools:
# Output: Denied tools: {'Bash'}  ← User clicked "Deny All"
```

**Solution**:
```python
# Option 1: Remove from denied_tools (if user clicked "Deny All")
agent.execution_context.denied_tools.discard("Bash")

# Option 2: Use different tool
await agent.execute_tool("PythonCode", {"code": "..."})  # Alternative to Bash

# Option 3: Request approval again with better justification
# (If user clicked "Deny Once", next call will prompt again)
```

---

## Budget Issues

### Issue 5: "Insufficient budget"

**Symptom**:
```python
PermissionDeniedError: Insufficient budget: estimated $5.00 but only $2.00 remaining
```

**Cause**: Operation cost exceeds remaining budget.

**Diagnosis**:
```python
ctx = agent.execution_context

print(f"Budget limit: ${ctx.budget_limit}")
print(f"Budget used: ${ctx.budget_used:.2f}")
print(f"Remaining: ${ctx.budget_limit - ctx.budget_used:.2f}")

# Example output:
# Budget limit: $10.0
# Budget used: $8.00
# Remaining: $2.00
```

**Solution**:
```python
# Option 1: Increase budget limit
agent.execution_context.budget_limit = 20.0  # Increase to $20

# Option 2: Reset budget usage (if appropriate)
agent.execution_context.budget_used = 0.0  # Reset usage

# Option 3: Use cheaper alternative
# Instead of GPT-4 ($5.00), use GPT-3.5 ($0.10)
await agent.execute_tool("LLM", {
    "prompt": "...",
    "model": "gpt-3.5-turbo"  # Cheaper model
})

# Option 4: Disable budget limits
config = BaseAgentConfig(
    budget_limit_usd=None  # Unlimited
)
```

---

### Issue 6: "Budget tracking inaccurate"

**Symptom**: Budget usage doesn't match expected costs.

**Diagnosis**:
```python
# Enable detailed budget logging
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("kaizen.permissions.budget")

# Execute operation and check logs
await agent.execute_tool("LLM", {"prompt": "Hello"})

# Logs show:
# DEBUG: Estimated cost: $0.0001
# DEBUG: Actual cost: $0.0002 (from result metadata)
# DEBUG: Budget updated: $0.0002 recorded
```

**Cause**: Actual cost differs from estimated cost.

**Solution**:
```python
# Actual cost is extracted from result metadata
# To improve estimates, update TOOL_COSTS:

from kaizen.core.autonomy.permissions.budget_enforcer import BudgetEnforcer

# View current costs
print(BudgetEnforcer.TOOL_COSTS)

# Update costs (requires modifying source)
# OR use wrapper for custom estimation
class CustomBudgetEnforcer(BudgetEnforcer):
    @staticmethod
    def estimate_cost(tool_name: str, tool_input: dict) -> float:
        # Custom estimation logic
        if tool_name == "CustomTool":
            return 0.05  # Custom cost

        # Delegate to parent
        return BudgetEnforcer.estimate_cost(tool_name, tool_input)
```

---

### Issue 7: "Budget exhausted unexpectedly"

**Symptom**: Budget runs out faster than expected.

**Diagnosis**:
```python
# Track per-operation costs
async def execute_with_tracking(agent, tool_name, params):
    initial = agent.execution_context.budget_used

    result = await agent.execute_tool(tool_name, params)

    cost = agent.execution_context.budget_used - initial

    print(f"{tool_name} cost: ${cost:.4f}")

    return result

# Execute multiple operations
await execute_with_tracking(agent, "LLM", {"prompt": "..."})
# Output: LLM cost: $0.0025 (higher than expected $0.0001!)

# Identify expensive operations
```

**Solution**:
```python
# Use cost-threshold approval to catch expensive operations
from kaizen.core.autonomy.permissions.approval_manager import ToolApprovalManager

class BudgetAwareApproval(ToolApprovalManager):
    async def request_approval(self, tool_name, tool_input, estimated_cost, context):
        # Alert user if operation is expensive
        if estimated_cost > 0.10:
            logger.warning(f"Expensive operation: {tool_name} costs ${estimated_cost:.2f}")

        return await super().request_approval(tool_name, tool_input, estimated_cost, context)
```

---

## Approval Workflow Issues

### Issue 8: "Approval timeout"

**Symptom**:
```
WARNING: Approval timeout for Bash, denying execution
PermissionDeniedError: Approval timeout
```

**Cause**: User didn't respond within timeout period.

**Diagnosis**:
```python
print(f"Approval timeout: {agent.approval_manager.timeout}s")
# Output: Approval timeout: 60.0s
```

**Solution**:
```python
# Option 1: Increase timeout
agent.approval_manager.timeout = 180.0  # 3 minutes

# Option 2: Use shorter timeout for automated scenarios
agent.approval_manager.timeout = 10.0  # 10 seconds

# Option 3: Switch to BYPASS mode (no approvals)
config = BaseAgentConfig(
    permission_mode=PermissionMode.BYPASS
)

# Option 4: Pre-approve tool with "Approve All"
agent.execution_context.allowed_tools.add("Bash")  # Skip future approvals
```

---

### Issue 9: "Approval manager not configured"

**Symptom**:
```python
RuntimeError: Approval manager not configured but approval required
```

**Cause**: No `control_protocol` provided to BaseAgent in DEFAULT mode.

**Diagnosis**:
```python
print(f"Approval manager: {agent.approval_manager}")
# Output: Approval manager: None
```

**Solution**:
```python
# Option 1: Provide Control Protocol
from kaizen.core.autonomy.control.protocol import ControlProtocol
from kaizen.core.autonomy.control.transport import InMemoryTransport

transport = InMemoryTransport()
control_protocol = ControlProtocol(transport=transport)

agent = BaseAgent(
    config=config,
    signature=signature,
    control_protocol=control_protocol  # Required!
)

# Option 2: Switch to BYPASS mode (no approvals needed)
config = BaseAgentConfig(
    permission_mode=PermissionMode.BYPASS
)

# Option 3: Pre-approve all tools
config = BaseAgentConfig(
    permission_mode=PermissionMode.DEFAULT,
    allowed_tools={"Read", "Write", "Bash", "LLM"}  # Pre-approved
)
```

---

### Issue 10: "Control protocol connection failed"

**Symptom**:
```python
ConnectionError: Control protocol transport not connected
```

**Cause**: Transport (HTTP, SSE) connection issue.

**Diagnosis**:
```python
# Check transport status
transport = agent.approval_manager.control_protocol.transport

print(f"Transport type: {type(transport)}")
print(f"Connected: {transport.is_connected()}")

# For HTTP transport:
# print(f"Client URL: {transport.client_url}")
# print(f"Server port: {transport.server_port}")
```

**Solution**:
```python
# Option 1: Use InMemoryTransport for testing
from kaizen.core.autonomy.control.transport import InMemoryTransport

transport = InMemoryTransport()  # No connection needed

# Option 2: Fix HTTP connection
from kaizen.core.autonomy.control.transport import HTTPTransport

transport = HTTPTransport(
    client_url="http://localhost:8000/approval",  # Correct URL
    server_port=8001
)

# Ensure server is running
await transport.connect()

# Option 3: Retry connection
import asyncio

for attempt in range(3):
    try:
        await transport.connect()
        break
    except ConnectionError:
        if attempt < 2:
            await asyncio.sleep(1)
        else:
            raise
```

---

## Rule Matching Problems

### Issue 11: "Rule not matching expected input"

**Symptom**: Rule should match but doesn't apply.

**Diagnosis**:
```python
import re

# Test rule manually
tool_pattern = "Write"
input_pattern = r"^/app/.*"
tool_input = {"file_path": "/tmp/output.txt"}

# Extract first string from input
first_string = next(
    (v for v in tool_input.values() if isinstance(v, str)),
    None
)

print(f"Tool pattern matches: {tool_pattern == 'Write'}")
print(f"First string: {first_string}")
print(f"Pattern match: {bool(re.match(input_pattern, first_string))}")

# Output:
# Tool pattern matches: True
# First string: /tmp/output.txt
# Pattern match: False (doesn't start with /app/)
```

**Solution**:
```python
# Fix 1: Adjust regex pattern to match actual input
correct_pattern = r"^/tmp/.*"  # Match /tmp/ instead of /app/

# Fix 2: Use more permissive pattern
wildcard_pattern = r".*"  # Match any input

# Fix 3: Check rule ordering (first match wins)
rules = [
    PermissionRule("Write", r"^/etc/.*", allowed=False),  # Specific denial first
    PermissionRule("Write", r".*", allowed=True),  # General allow last
]
```

---

### Issue 12: "Rule matches wrong input"

**Symptom**: Rule applies to unintended tool/input.

**Diagnosis**:
```python
# Check all rules in order
for i, rule in enumerate(agent.execution_context.rules):
    print(f"Rule {i}: {rule.tool_pattern} + {rule.input_pattern} → {rule.allowed}")

# Test against specific input
tool_name = "Write"
tool_input = {"file_path": "/app/config.py"}

for i, rule in enumerate(agent.execution_context.rules):
    # Check tool match
    tool_match = bool(re.match(rule.tool_pattern, tool_name))

    # Check input match
    first_string = next((v for v in tool_input.values() if isinstance(v, str)), None)
    input_match = bool(re.match(rule.input_pattern, first_string)) if first_string else False

    if tool_match and input_match:
        print(f"Rule {i} MATCHES → {rule.allowed}")
        break
```

**Solution**:
```python
# Make rule patterns more specific
specific_rule = PermissionRule(
    tool_pattern="Write",  # Exact match, not regex
    input_pattern=r"^/app/config\.py$",  # Exact file path
    allowed=True
)

# Or use negative lookahead for exclusions
exclude_etc = PermissionRule(
    tool_pattern="Write",
    input_pattern=r"^(?!/etc/).*",  # NOT starting with /etc/
    allowed=True
)
```

---

### Issue 13: "ReDoS (Regular Expression Denial of Service)"

**Symptom**: Permission check takes extremely long (>1 second).

**Diagnosis**:
```python
import time

pattern = r"(a+)+$"  # VULNERABLE pattern
test_input = "a" * 30 + "X"

start = time.time()
try:
    re.match(pattern, test_input)
except:
    pass
duration = time.time() - start

print(f"Regex took {duration:.2f}s")
# Output: Regex took 45.23s (REDOS!)
```

**Solution**:
```python
# Use non-backtracking patterns
safe_pattern = r"^[a-zA-Z0-9_/.-]+$"  # Character class (fast)

# Avoid nested quantifiers
vulnerable = r"(a+)+$"  # VULNERABLE
safe = r"^a+$"  # SAFE

# Test patterns with worst-case input
def test_regex_safety(pattern: str, max_time: float = 0.1):
    """Test if regex is safe from ReDoS."""
    test_inputs = [
        "a" * 30 + "X",  # Nested quantifier killer
        "." * 100,  # Wildcard killer
        "(" * 50,  # Grouping killer
    ]

    for test_input in test_inputs:
        start = time.time()
        try:
            re.match(pattern, test_input)
        except:
            pass
        duration = time.time() - start

        if duration > max_time:
            print(f"⚠️ ReDoS risk: {pattern} took {duration:.2f}s on '{test_input[:20]}...'")
            return False

    print(f"✅ Pattern safe: {pattern}")
    return True

# Test your patterns
test_regex_safety(r"^/app/.*")
```

---

## Integration Issues

### Issue 14: "BaseAgent permission fields not initialized"

**Symptom**:
```python
AttributeError: 'BaseAgent' object has no attribute 'execution_context'
```

**Cause**: Old BaseAgent version without permission integration.

**Solution**:
```python
# Ensure using Kaizen v0.5.0+ with permission system
import kaizen

print(f"Kaizen version: {kaizen.__version__}")
# Should be >= 0.5.0

# Update Kaizen
# pip install --upgrade kailash-kaizen
```

---

### Issue 15: "Permission check not enforced"

**Symptom**: Tools execute without permission checks.

**Diagnosis**:
```python
# Check if execute_tool() includes permission flow
import inspect

source = inspect.getsource(agent.execute_tool)
print(source)

# Look for:
# - BudgetEnforcer.estimate_cost()
# - permission_policy.check_permission()
# - approval_manager.request_approval()
```

**Solution**:
```python
# Ensure using BaseAgent (not custom agent)
from kaizen.core.base_agent import BaseAgent

agent = BaseAgent(config=config, signature=signature)

# If using custom agent, ensure it includes permission flow
class CustomAgent(BaseAgent):
    async def execute_tool(self, tool_name: str, params: dict) -> Any:
        # MUST call super().execute_tool() to include permissions
        return await super().execute_tool(tool_name, params)
```

---

## Performance Problems

### Issue 16: "Permission checks are slow"

**Symptom**: execute_tool() takes >100ms.

**Diagnosis**:
```python
import time

start = time.time()
result = await agent.execute_tool("Read", {"file_path": "..."})
duration = time.time() - start

print(f"execute_tool() took {duration*1000:.2f}ms")
# Output: execute_tool() took 250ms (TOO SLOW!)

# Profile permission check
start = time.time()
allowed, reason = agent.permission_policy.check_permission("Read", {}, 0.001)
check_duration = time.time() - start

print(f"Permission check took {check_duration*1000:.2f}ms")
# Output: Permission check took 200ms (SLOW!)
```

**Cause**: Expensive regex patterns in rules.

**Solution**:
```python
# Optimize regex patterns
# Instead of: r".*very.*complex.*pattern.*"
# Use: r"^simple_prefix.*"

# Or disable rules if not needed
config = BaseAgentConfig(
    permission_rules=[]  # No rules = faster
)

# Or use BYPASS mode
config = BaseAgentConfig(
    permission_mode=PermissionMode.BYPASS  # Skip permission checks
)
```

---

### Issue 17: "High memory usage"

**Symptom**: Memory usage grows over time.

**Diagnosis**:
```python
import sys

# Check execution context size
ctx_size = sys.getsizeof(agent.execution_context)
print(f"ExecutionContext size: {ctx_size} bytes")

# Check allowed/denied tools
print(f"Allowed tools: {len(agent.execution_context.allowed_tools)} items")
print(f"Denied tools: {len(agent.execution_context.denied_tools)} items")
```

**Cause**: Large allowed_tools/denied_tools sets.

**Solution**:
```python
# Periodically clear sets
agent.execution_context.allowed_tools.clear()
agent.execution_context.denied_tools.clear()

# Or use short-lived agents
async def create_fresh_agent():
    """Create new agent instead of reusing."""
    return BaseAgent(config=config, signature=signature)

# Use for each session
agent = await create_fresh_agent()
```

---

## Debugging Tools

### Enable Debug Logging

```python
import logging

# Enable all permission system logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Specific loggers
logging.getLogger("kaizen.permissions").setLevel(logging.DEBUG)
logging.getLogger("kaizen.permissions.policy").setLevel(logging.DEBUG)
logging.getLogger("kaizen.permissions.budget").setLevel(logging.DEBUG)
logging.getLogger("kaizen.permissions.approval").setLevel(logging.DEBUG)
```

### Permission Decision Trace

```python
# Log detailed permission decision process
class DebugPermissionPolicy(PermissionPolicy):
    def check_permission(self, tool_name, tool_input, estimated_cost):
        """Override with debug logging."""

        print(f"\n=== Permission Decision Trace for {tool_name} ===")
        print(f"Estimated cost: ${estimated_cost:.4f}")

        # Layer 1: BYPASS
        if self.context.mode == PermissionMode.BYPASS:
            print("Layer 1: BYPASS mode → AUTO-APPROVED ✅")
            return True, None

        # Layer 2: Budget
        if not self.context.has_budget(estimated_cost):
            print(f"Layer 2: Budget check → DENIED (insufficient budget) ❌")
            return False, "Insufficient budget"
        print("Layer 2: Budget check → PASSED")

        # Layer 3: PLAN mode
        if self.context.mode == PermissionMode.PLAN:
            if tool_name in ["Read", "Grep", "Glob"]:
                print("Layer 3: PLAN mode + read-only tool → ALLOWED ✅")
                return True, None
            else:
                print("Layer 3: PLAN mode + write tool → DENIED ❌")
                return False, "Not allowed in PLAN mode"

        # ... continue for all 8 layers

        return super().check_permission(tool_name, tool_input, estimated_cost)

# Use debug policy
agent.permission_policy = DebugPermissionPolicy(agent.execution_context)
```

---

## Summary

**Quick Reference**:

| Issue | Quick Fix |
|-------|-----------|
| Permission denied | Check denied_tools, mode, rules |
| Budget exceeded | Increase limit or use cheaper tools |
| Approval timeout | Increase timeout or use BYPASS mode |
| Rule not matching | Debug regex with test script |
| Slow permission checks | Optimize regex or disable rules |
| Missing approval manager | Provide control_protocol to BaseAgent |

**Next Steps**:

- **[Permission System User Guide](permission-system-user-guide.md)** - Complete usage documentation
- **[Security Best Practices](permission-security-best-practices.md)** - Security hardening
- **[Budget Management Guide](permission-budget-management.md)** - Advanced budget strategies
- **[Approval Workflow Guide](permission-approval-workflows.md)** - Custom approval patterns

---

**© 2025 Kailash Kaizen | Troubleshooting v1.0**
