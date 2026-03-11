# Permission System Security Best Practices

**Version**: 1.0
**Last Updated**: 2025-10-25
**Security Level**: Production-Hardened

---

## Table of Contents

1. [Security Overview](#security-overview)
2. [Threat Model](#threat-model)
3. [Defense-in-Depth Strategy](#defense-in-depth-strategy)
4. [Permission Mode Security](#permission-mode-security)
5. [Budget Security](#budget-security)
6. [Approval Workflow Security](#approval-workflow-security)
7. [Rule Security](#rule-security)
8. [Deployment Security](#deployment-security)
9. [Monitoring & Auditing](#monitoring--auditing)
10. [Compliance](#compliance)

---

## Security Overview

The Permission System implements **defense-in-depth** security with multiple layers of protection:

```
┌─────────────────────────────────────────┐
│  Layer 1: Mode-Based Access Control    │  ← PermissionMode (BYPASS/PLAN/DEFAULT)
├─────────────────────────────────────────┤
│  Layer 2: Budget Enforcement            │  ← Cost limits prevent resource exhaustion
├─────────────────────────────────────────┤
│  Layer 3: Tool Whitelisting/Blacklisting│  ← allowed_tools / denied_tools
├─────────────────────────────────────────┤
│  Layer 4: Regex-Based Rules             │  ← Fine-grained input validation
├─────────────────────────────────────────┤
│  Layer 5: Interactive Approval          │  ← Human-in-the-loop for risky ops
├─────────────────────────────────────────┤
│  Layer 6: Fail-Closed Design            │  ← Deny on timeout/error
├─────────────────────────────────────────┤
│  Layer 7: Thread-Safe Execution         │  ← Lock-based synchronization
├─────────────────────────────────────────┤
│  Layer 8: Audit Trail Integration       │  ← Comprehensive logging
└─────────────────────────────────────────┘
```

### Security Principles

1. **Principle of Least Privilege**: Deny by default, grant only necessary permissions
2. **Fail-Closed Design**: On errors or timeouts, deny execution
3. **Defense in Depth**: Multiple independent security layers
4. **Separation of Concerns**: Permission logic isolated from execution logic
5. **Audit Everything**: Comprehensive logging for security analysis

---

## Threat Model

### Threats Addressed

| Threat | Mitigation | Layer |
|--------|------------|-------|
| **Unauthorized Tool Access** | denied_tools, permission rules | 3, 4 |
| **Resource Exhaustion** | Budget limits with cost estimation | 2 |
| **Privilege Escalation** | Mode-based controls, immutable policies | 1 |
| **Data Exfiltration** | PLAN mode (read-only), approval workflows | 1, 5 |
| **System Compromise** | Risky tool approval, regex validation | 4, 5 |
| **Budget Exhaustion Attack** | Pre-execution cost checks, limits | 2 |
| **Approval Bypass** | Timeout enforcement, fail-closed | 6 |
| **Race Conditions** | Thread-safe ExecutionContext | 7 |
| **Audit Evasion** | Mandatory logging, immutable trails | 8 |

### Out-of-Scope Threats

- **LLM Prompt Injection**: Handled by signature validation (separate system)
- **Network-Level Attacks**: Handled by infrastructure/firewall
- **Supply Chain Attacks**: Handled by dependency scanning
- **Physical Security**: Handled by operational security

---

## Defense-in-Depth Strategy

### Layer 1: Mode-Based Access Control

**Security Posture by Mode**:

```python
# HIGH SECURITY: Read-only planning
config = BaseAgentConfig(
    permission_mode=PermissionMode.PLAN,  # Only read operations allowed
    budget_limit_usd=1.0  # Minimal budget for LLM calls
)

# MEDIUM SECURITY: Interactive development (RECOMMENDED)
config = BaseAgentConfig(
    permission_mode=PermissionMode.DEFAULT,  # User approval for risky ops
    budget_limit_usd=50.0,
    denied_tools={"Delete", "SystemShutdown"}  # Critical operations blocked
)

# LOW SECURITY: Trusted environment (use with caution)
config = BaseAgentConfig(
    permission_mode=PermissionMode.BYPASS,  # Auto-approve everything
    budget_limit_usd=None,  # Unlimited budget
    denied_tools={"Delete", "FormatDisk"}  # Still block destructive ops
)
```

**Rule of Thumb**:
- **Development**: DEFAULT mode with high budget
- **Production (supervised)**: ACCEPT_EDITS mode with moderate budget
- **Production (automated)**: BYPASS mode + denied_tools + external controls
- **Security audits**: PLAN mode (read-only)

---

### Layer 2: Budget Enforcement

**Budget limits prevent**:
- Resource exhaustion attacks (infinite LLM calls)
- Runaway costs in production
- Accidental expensive operations

**Security Configuration**:

```python
# Conservative production budget
config = BaseAgentConfig(
    budget_limit_usd=10.0,  # $10 limit
    permission_mode=PermissionMode.DEFAULT
)

# Budget exceeded → PermissionDeniedError (fail-closed)
try:
    await agent.execute_tool("LLM", {"prompt": "..." * 10000})
except PermissionDeniedError as e:
    # Budget check BEFORE execution prevents actual LLM call
    logger.security(f"Budget attack prevented: {e}")
```

**Best Practice**: Set budget based on expected workload + 20% buffer.

---

### Layer 3: Tool Whitelisting/Blacklisting

**Whitelisting (Recommended for Security)**:

```python
# Allow ONLY safe tools (principle of least privilege)
config = BaseAgentConfig(
    permission_mode=PermissionMode.DEFAULT,
    allowed_tools={"Read", "Grep", "Glob", "HTTP"},  # Explicit whitelist
    denied_tools=set()  # Empty blacklist
)

# Any tool NOT in allowed_tools requires approval
# Even in BYPASS mode, only whitelisted tools auto-approved
```

**Blacklisting (For Critical Operations)**:

```python
# Block destructive operations
config = BaseAgentConfig(
    permission_mode=PermissionMode.BYPASS,  # Fast execution
    denied_tools={
        "Delete",           # File deletion
        "Bash",             # System commands
        "PythonCode",       # Arbitrary code execution
        "SystemShutdown",   # System control
        "NetworkConfig"     # Network modification
    }
)

# denied_tools ALWAYS blocks (even in BYPASS mode)
# → Provides safety net for trusted environments
```

**Security Comparison**:

| Approach | Security Level | Use Case |
|----------|----------------|----------|
| Whitelist only | **HIGH** | Security-sensitive environments |
| Blacklist only | **LOW** | Development, trusted automation |
| Whitelist + Blacklist | **MEDIUM** | Production with flexibility |

---

### Layer 4: Regex-Based Rule Validation

**Input Validation with Rules**:

```python
from kaizen.core.autonomy.permissions.types import PermissionRule

# Security rules for file operations
security_rules = [
    # DENY: Write to system directories
    PermissionRule(
        tool_pattern="Write",
        input_pattern=r"^/(etc|bin|sbin|boot|sys|proc)/.*",
        allowed=False,
        reason="System directories are protected"
    ),

    # DENY: Bash commands with dangerous keywords
    PermissionRule(
        tool_pattern="Bash",
        input_pattern=r".*(rm\s+-rf|sudo|chmod\s+777|wget.*\||curl.*\|).*",
        allowed=False,
        reason="Dangerous bash pattern detected"
    ),

    # DENY: SQL injection patterns in LLM prompts
    PermissionRule(
        tool_pattern="LLM",
        input_pattern=r".*(DROP\s+TABLE|DELETE\s+FROM|;--|\bOR\b.*=).*",
        allowed=False,
        reason="SQL injection pattern detected"
    ),

    # ALLOW: Read from application data directory
    PermissionRule(
        tool_pattern="Read",
        input_pattern=r"^/app/data/.*",
        allowed=True,
        reason="Application data reads allowed"
    ),
]

config = BaseAgentConfig(
    permission_mode=PermissionMode.DEFAULT,
    permission_rules=security_rules
)
```

**⚠️ Regex Security Warning**: Avoid ReDoS (Regular Expression Denial of Service)

```python
# VULNERABLE: Catastrophic backtracking
bad_pattern = r"(a+)+$"

# SAFE: Non-backtracking patterns
good_pattern = r"^[a-zA-Z0-9_]+$"
```

**Rule Ordering for Security**:

```python
# CORRECT: Specific denials before general allows
rules = [
    PermissionRule("Write", r"^/etc/.*", allowed=False),  # Specific denial
    PermissionRule("Write", r"^/app/.*", allowed=True),   # General allow
]

# INCORRECT: General allows before specific denials
bad_rules = [
    PermissionRule("Write", r".*", allowed=True),      # Matches everything!
    PermissionRule("Write", r"^/etc/.*", allowed=False),  # Never evaluated
]
```

---

### Layer 5: Interactive Approval Security

**Approval Workflow Hardening**:

```python
from kaizen.core.autonomy.permissions.approval_manager import ToolApprovalManager

# Secure approval configuration
approval_manager = ToolApprovalManager(
    control_protocol=control_protocol,
    timeout=60.0  # Reasonable timeout (fail-closed on expiry)
)

# Approval prompt includes:
# - Tool name and full input parameters (transparency)
# - Estimated cost (budget awareness)
# - Risk warnings for dangerous operations (user education)
# - "Approve All" / "Deny All" options (persistent decisions)
```

**Security Features**:

1. **Fail-Closed on Timeout**: No response → deny execution
2. **Context-Aware Prompts**: Different templates for Bash, Write, Generic
3. **Risk Warnings**: Highlight dangerous operations
4. **Budget Visibility**: Show remaining budget in prompt
5. **Persistent Decisions**: "Approve All" / "Deny All" for efficiency

**Approval Bypass Prevention**:

```python
# SECURE: Approval enforced before execution
async def execute_tool(self, tool_name, params):
    # Step 3: Request approval
    if allowed is None:  # ASK mode
        if self.approval_manager is None:
            raise RuntimeError("Approval manager not configured")

        approved = await self.approval_manager.request_approval(...)

        if not approved:
            raise PermissionDeniedError("User denied approval")

    # Step 4: Only execute if approved
    result = await self._tool_executor.execute(...)
```

---

### Layer 6: Fail-Closed Design

**Fail-Closed Principle**: On error or timeout, **deny** execution (never approve).

```python
# Example: Approval timeout
try:
    approved = await approval_manager.request_approval(
        tool_name="Bash",
        tool_input={"command": "ls"},
        estimated_cost=0.01,
        context=context,
        timeout=60.0
    )
except asyncio.TimeoutError:
    # FAIL-CLOSED: Timeout → deny execution
    logger.warning("Approval timeout, denying execution")
    return False  # NOT True!

# Example: Budget check error
try:
    has_budget = context.has_budget(estimated_cost)
except Exception as e:
    # FAIL-CLOSED: Error → deny execution
    logger.error(f"Budget check failed: {e}")
    raise PermissionDeniedError("Budget verification failed")
```

**Fail-Closed Scenarios**:

| Scenario | Behavior | Security Benefit |
|----------|----------|------------------|
| Approval timeout | Deny execution | Prevents unattended execution |
| Budget check error | Deny execution | Prevents cost overruns |
| Rule match error | Deny execution | Prevents regex exploits |
| Control protocol failure | Deny execution | Maintains security posture |
| Unknown tool | Conservative cost estimate | Prevents budget exhaustion |

---

### Layer 7: Thread-Safe Execution

**Concurrency Security**:

```python
# ExecutionContext uses threading.Lock for thread safety
class ExecutionContext:
    def __init__(self):
        self._lock = threading.Lock()
        self.budget_used = 0.0

    def has_budget(self, estimated_cost: float) -> bool:
        with self._lock:  # Thread-safe budget check
            if self.budget_limit is None:
                return True
            return (self.budget_used + estimated_cost) <= self.budget_limit

# Prevents race conditions:
# - Thread A checks budget: $9.00 used, $1.00 remaining
# - Thread B checks budget: $9.00 used, $1.00 remaining (SAME STATE!)
# - Thread A executes tool: $10.00 used (OK)
# - Thread B executes tool: $11.00 used (BUDGET EXCEEDED!)

# With lock:
# - Thread A acquires lock, checks budget, reserves cost, releases lock
# - Thread B waits for lock, checks budget, sees updated state
```

**Best Practice**: Always access `ExecutionContext` via agent methods (thread-safe).

---

### Layer 8: Audit Trail Integration

**Comprehensive Logging**:

```python
import logging

# Configure permission system logging
logger = logging.getLogger("kaizen.permissions")
logger.setLevel(logging.INFO)

# Security events logged:
# - Permission checks (allowed/denied with reason)
# - Budget usage (estimated vs actual cost)
# - Approval requests (user response, timeout)
# - Rule evaluations (match/no-match)
# - Mode changes
# - Tool whitelist/blacklist modifications
```

**Audit Log Example**:

```
[2025-10-25 10:30:15] INFO: Permission check: tool=Bash, allowed=None (ASK mode)
[2025-10-25 10:30:16] INFO: Approval request sent: tool=Bash, cost=$0.01, timeout=60s
[2025-10-25 10:30:45] INFO: Approval granted: tool=Bash, user_action=Approve Once
[2025-10-25 10:30:46] INFO: Tool executed: tool=Bash, actual_cost=$0.01, budget_used=$5.23
[2025-10-25 10:31:12] WARNING: Permission denied: tool=Write, reason=System directory protected
[2025-10-25 10:32:05] ERROR: Budget exceeded: estimated=$2.00, remaining=$0.50
```

**Integration with Observability System**:

```python
from kaizen.core.autonomy.observability import ObservabilityManager

# Enable observability for permission events
observability = ObservabilityManager(
    enable_metrics=True,
    enable_logging=True,
    enable_tracing=True,
    enable_audit=True
)

# Metrics tracked:
# - permission_checks_total (counter)
# - permission_denials_total (counter)
# - approval_request_duration (histogram)
# - budget_usage (gauge)
```

---

## Permission Mode Security

### BYPASS Mode Security

**⚠️ HIGH RISK**: Use only in controlled environments.

**Security Checklist**:

```python
# ✅ SAFE BYPASS Configuration
config = BaseAgentConfig(
    permission_mode=PermissionMode.BYPASS,

    # CRITICAL: Still enforce budget limits
    budget_limit_usd=100.0,  # NOT None

    # CRITICAL: Block destructive operations
    denied_tools={"Delete", "Bash", "PythonCode"},

    # OPTIONAL: Log all operations for audit
    # (via observability integration)
)

# ❌ UNSAFE BYPASS Configuration
bad_config = BaseAgentConfig(
    permission_mode=PermissionMode.BYPASS,
    budget_limit_usd=None,  # Unlimited! ⚠️
    denied_tools=set()  # No blocks! ⚠️
)
```

**External Controls Required**:

1. **Infrastructure Isolation**: Sandboxed execution (Docker, VMs)
2. **Network Restrictions**: Firewall rules, VPN
3. **File System Isolation**: chroot, namespaces
4. **Resource Limits**: cgroups, ulimit
5. **Monitoring**: Real-time anomaly detection

**Use Cases**:
- ✅ CI/CD pipelines (isolated runners)
- ✅ Batch processing (sandboxed containers)
- ✅ Production with external WAF/firewall
- ❌ Interactive development
- ❌ Multi-tenant environments
- ❌ Public-facing APIs

---

### DEFAULT Mode Security

**✅ RECOMMENDED**: Best balance of security and usability.

**Security Benefits**:

1. **Human-in-the-Loop**: User approval for risky operations
2. **Budget Awareness**: User sees costs before execution
3. **Audit Trail**: All approvals logged
4. **Flexible Policies**: Rules + mode defaults

**Hardening**:

```python
config = BaseAgentConfig(
    permission_mode=PermissionMode.DEFAULT,

    # Conservative budget
    budget_limit_usd=10.0,

    # Pre-approve safe tools (reduce approval fatigue)
    allowed_tools={"Read", "Grep", "Glob"},

    # Block critical operations
    denied_tools={"Delete", "SystemShutdown"},

    # Security rules
    permission_rules=[
        # Deny system directory writes
        PermissionRule("Write", r"^/(etc|bin|sbin)/.*", allowed=False),

        # Deny dangerous bash patterns
        PermissionRule("Bash", r".*(rm\s+-rf|sudo).*", allowed=False),
    ]
)
```

---

### PLAN Mode Security

**✅ HIGHEST SECURITY**: Read-only operations.

**Use Cases**:

```python
# Security audit workflow
audit_config = BaseAgentConfig(
    permission_mode=PermissionMode.PLAN,  # Read-only
    budget_limit_usd=1.0  # Minimal budget for LLM analysis
)

audit_agent = BaseAgent(config=audit_config, signature=AuditSignature())

# Can ONLY read files, grep, glob
await audit_agent.execute_tool("Read", {"file_path": "/app/config.py"})  # ✅ Allowed
await audit_agent.execute_tool("Write", {"file_path": "/tmp/out.txt"})  # ❌ Denied
await audit_agent.execute_tool("Bash", {"command": "ls"})  # ❌ Denied
```

**Benefits**:

- **Zero Side Effects**: Cannot modify system state
- **Safe Exploration**: Analyze code without execution risk
- **Compliance**: Meet read-only audit requirements

---

## Budget Security

### Budget Exhaustion Attacks

**Attack Scenario**:

```python
# Attacker crafts expensive LLM prompt
malicious_prompt = "Explain quantum mechanics " * 10000  # 100K tokens!

# Without budget limits:
await agent.execute_tool("LLM", {"prompt": malicious_prompt})
# → Cost: $50.00 (GPT-4 pricing)
# → Budget exhausted, production down
```

**Mitigation**:

```python
# Set conservative budget limit
config = BaseAgentConfig(
    budget_limit_usd=10.0  # $10 limit
)

# Budget check BEFORE execution
try:
    await agent.execute_tool("LLM", {"prompt": malicious_prompt})
except PermissionDeniedError as e:
    # Budget exceeded → execution blocked
    logger.security(f"Budget attack prevented: {e}")
    # "Insufficient budget: estimated $50.00 but only $10.00 remaining"
```

### Budget Monitoring

```python
# Real-time budget alerts
def monitor_budget(agent):
    ctx = agent.execution_context

    usage_percent = (ctx.budget_used / ctx.budget_limit) * 100

    if usage_percent > 90:
        logger.critical(f"Budget 90% exhausted: ${ctx.budget_used:.2f} / ${ctx.budget_limit:.2f}")

    elif usage_percent > 75:
        logger.warning(f"Budget 75% used: ${ctx.budget_used:.2f} / ${ctx.budget_limit:.2f}")

    elif usage_percent > 50:
        logger.info(f"Budget 50% used: ${ctx.budget_used:.2f} / ${ctx.budget_limit:.2f}")
```

---

## Approval Workflow Security

### Approval Request Forgery Prevention

**Security Design**:

```python
# Approval requests include full context
approval_request = ControlRequest.create(
    request_type="approval",
    question=f"""
    ⚠️ Tool Approval Required

    Tool: {tool_name}
    Input: {tool_input}  # FULL input shown (transparency)
    Estimated Cost: ${estimated_cost}
    Remaining Budget: ${remaining_budget}

    ⚠️ WARNING: {risk_warning}

    Choose action:
    - Approve Once
    - Approve All
    - Deny Once
    - Deny All
    """,
    choices=["Approve Once", "Approve All", "Deny Once", "Deny All"]
)

# User sees FULL parameters → cannot be tricked by partial info
```

### Timeout Security

```python
# Timeout prevents:
# 1. Unattended execution (user forgot to respond)
# 2. Approval bypass (agent continues without approval)
# 3. Resource holding (blocking other operations)

try:
    approved = await approval_manager.request_approval(
        ...,
        timeout=60.0  # Fail-closed after 60 seconds
    )
except asyncio.TimeoutError:
    # DENY execution (fail-closed)
    logger.security("Approval timeout: execution denied")
    raise PermissionDeniedError("Approval timeout")
```

---

## Rule Security

### Regex ReDoS Prevention

**Vulnerable Pattern**:

```python
# VULNERABLE: Catastrophic backtracking
bad_rule = PermissionRule(
    tool_pattern="Write",
    input_pattern=r"(a+)+$",  # ReDoS vulnerability!
    allowed=True
)

# Attack: Input "aaaaaaaaaaaaaaaaaaaX" → exponential backtracking
```

**Safe Pattern**:

```python
# SAFE: Non-backtracking
good_rule = PermissionRule(
    tool_pattern="Write",
    input_pattern=r"^[a-zA-Z0-9_/.-]+$",  # Character class (fast)
    allowed=True
)
```

**Testing for ReDoS**:

```python
import re
import time

pattern = r"(a+)+$"
test_input = "a" * 30 + "X"

start = time.time()
try:
    re.match(pattern, test_input)
except:
    pass
duration = time.time() - start

if duration > 1.0:
    print(f"⚠️ ReDoS vulnerability detected: {duration:.2f}s")
```

### Rule Bypass Prevention

**Secure Rule Ordering**:

```python
# CORRECT: Specific denials BEFORE general allows
rules = [
    # Layer 1: Specific denials
    PermissionRule("Write", r"^/etc/.*", allowed=False),
    PermissionRule("Bash", r".*(rm|sudo).*", allowed=False),

    # Layer 2: General allows
    PermissionRule("Write", r"^/tmp/.*", allowed=True),
    PermissionRule("Bash", r"^(ls|pwd|echo).*", allowed=True),
]

# First match wins → denials checked first → bypass prevented
```

---

## Deployment Security

### Production Deployment Checklist

```python
# ✅ Production-Ready Configuration
production_config = BaseAgentConfig(
    # Permission mode
    permission_mode=PermissionMode.DEFAULT,  # or BYPASS with external controls

    # Budget limits
    budget_limit_usd=50.0,  # Conservative limit

    # Tool restrictions
    denied_tools={"Delete", "Bash", "PythonCode", "SystemShutdown"},

    # Security rules
    permission_rules=[
        # Deny system directories
        PermissionRule("Write", r"^/(etc|bin|sbin|boot)/.*", allowed=False),

        # Deny dangerous bash
        PermissionRule("Bash", r".*(rm\s+-rf|sudo|chmod\s+777).*", allowed=False),

        # Allow application data
        PermissionRule("Write", r"^/app/data/.*", allowed=True),
    ]
)

# ✅ Infrastructure Security
# - Docker container with limited capabilities
# - Network segmentation (VPC, security groups)
# - File system isolation (read-only mounts)
# - Resource limits (cgroups, ulimit)
# - Monitoring (CloudWatch, Prometheus)
# - Audit logging (centralized SIEM)
```

### Container Security

```dockerfile
# Dockerfile with security hardening
FROM python:3.11-slim

# Non-root user
RUN useradd --create-home --shell /bin/bash kaizen
USER kaizen

# Read-only file system
VOLUME ["/app/data"]
WORKDIR /app

# Copy application
COPY --chown=kaizen:kaizen . .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Drop capabilities
USER kaizen

# Run with limited permissions
CMD ["python", "agent.py"]
```

```yaml
# docker-compose.yml with security
services:
  kaizen-agent:
    build: .
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    cap_add:
      - NET_BIND_SERVICE
    read_only: true
    volumes:
      - ./data:/app/data:rw
      - /tmp:/tmp:rw
    environment:
      - PERMISSION_MODE=DEFAULT
      - BUDGET_LIMIT_USD=50.0
    networks:
      - kaizen-network

networks:
  kaizen-network:
    driver: bridge
    internal: true  # No internet access
```

---

## Monitoring & Auditing

### Security Metrics

```python
from kaizen.core.autonomy.observability import ObservabilityManager

observability = ObservabilityManager(enable_metrics=True)

# Metrics to monitor:
# - permission_denials_total: High rate → potential attack
# - budget_usage_percent: Approaching 100% → resource exhaustion
# - approval_timeout_total: High rate → unattended execution
# - denied_tool_attempts_total: High rate → privilege escalation attempt
```

### Alerting Rules

```python
# Example: Prometheus alert rules
"""
- alert: HighPermissionDenialRate
  expr: rate(permission_denials_total[5m]) > 10
  for: 5m
  annotations:
    summary: "High permission denial rate detected"
    description: "{{ $value }} denials/sec for 5 minutes"

- alert: BudgetExhaustionRisk
  expr: budget_usage_percent > 90
  for: 1m
  annotations:
    summary: "Budget 90% exhausted"
    description: "Remaining budget: {{ $value }}%"

- alert: DeniedToolAttempts
  expr: increase(denied_tool_attempts_total[1h]) > 50
  annotations:
    summary: "Multiple denied tool access attempts"
    description: "Potential privilege escalation attack"
"""
```

---

## Compliance

### SOC 2 Compliance

| Control | Implementation |
|---------|----------------|
| Access Control | Permission modes, rules, whitelists |
| Audit Logging | Comprehensive permission event logs |
| Budget Controls | Cost limits, usage tracking |
| Least Privilege | Deny by default, explicit allows |
| Fail-Closed | Deny on timeout/error |

### GDPR Compliance

- **Data Minimization**: Rules prevent access to sensitive directories
- **Audit Trail**: All permission decisions logged (immutable)
- **Right to Access**: Audit logs queryable by data subject ID

### HIPAA Compliance

- **Access Controls**: PermissionMode + rules enforce minimum necessary
- **Audit Logs**: All permission events logged with timestamps
- **Encryption**: ExecutionContext state encrypted at rest (via observability)

---

## Summary

**Security Levels by Configuration**:

| Configuration | Security Level | Use Case |
|---------------|----------------|----------|
| PLAN mode + rules | **HIGHEST** | Security audits, compliance |
| DEFAULT mode + budget + rules | **HIGH** | Production (supervised) |
| ACCEPT_EDITS + budget + denied_tools | **MEDIUM** | Development, refactoring |
| BYPASS + budget + denied_tools | **LOW** | Trusted automation |
| BYPASS + unlimited budget | **MINIMAL** | Sandboxed/isolated only |

**Next Steps**:

- **[Permission System User Guide](permission-system-user-guide.md)** - Complete usage guide
- **[Budget Management Guide](permission-budget-management.md)** - Advanced budget strategies
- **[Troubleshooting Guide](permission-troubleshooting.md)** - Common security issues

---

**© 2025 Kailash Kaizen | Security Hardened v1.0**
