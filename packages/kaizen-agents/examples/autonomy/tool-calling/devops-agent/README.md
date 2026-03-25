# DevOps Agent

## Overview

Safe system administration agent with bash command execution, danger-level approval workflows, and comprehensive audit trails. The agent executes DevOps tasks with intelligent safety checks, requesting approval for dangerous operations and logging all actions for compliance.

## Prerequisites

- **Python 3.8+**
- **Ollama** with llama3.1:8b-instruct-q8_0 model (FREE)
- **Unix-like system** (Linux, macOS)
- **Kailash Kaizen** installed

## Installation

```bash
ollama serve && ollama pull llama3.1:8b-instruct-q8_0
pip install kailash-kaizen
```

## Usage

```bash
python devops_agent.py "task description"
```

Examples:
```bash
python devops_agent.py "check disk usage and memory"
python devops_agent.py "analyze system processes"
python devops_agent.py "check log files for errors"
```

## Expected Output

```
============================================================
🤖 DEVOPS AGENT
============================================================
📋 Task: check disk usage and memory
🔧 LLM: ollama/llama3.1:8b-instruct-q8_0
📝 Audit Trail: .kaizen/audit/devops
🔒 Safety: Danger-level approval workflow
============================================================

🔧 Starting DevOps task: check disk usage and memory

📋 Planned 3 commands:

[1/3] ==================================================
🔍 Command: df -h
⚠️  Danger Level: SAFE
⚙️  Executing...
✅ Success
📄 Output:
Filesystem      Size  Used Avail Use% Mounted on
/dev/sda1       100G   45G   50G  47% /
==================================================

[2/3] ==================================================
🔍 Command: free -h
⚠️  Danger Level: SAFE
⚙️  Executing...
✅ Success
📄 Output:
              total        used        free
Mem:           16Gi       8.2Gi       7.8Gi
==================================================

============================================================
🔧 DEVOPS EXECUTION REPORT
============================================================

📊 Summary: 3/3 commands succeeded

📋 Command Results:
  ✅ [SAFE] df -h
  ✅ [SAFE] free -h
  ✅ [SAFE] ps aux | head -n 10

============================================================

💰 Cost: $0.00 (using Ollama local inference)
📝 Audit Log: .kaizen/audit/devops/audit_trail.jsonl
🔒 Commands Executed: 3
```

## Danger Levels

| Level | Commands | Permission | Example |
|-------|----------|------------|---------|
| **SAFE** | df, du, ls, pwd | ALLOW | `df -h` |
| **LOW** | cat, grep, find | ALLOW | `cat /etc/hosts` |
| **MEDIUM** | mkdir, touch, cp | ASK | `mkdir /tmp/test` |
| **HIGH** | rm, mv, chmod | ASK | `rm /tmp/file` |
| **CRITICAL** | rm -rf, dd, mkfs | DENY | `rm -rf /` ❌ |

## Features

### 1. Bash Command Execution
- Safe command execution with timeout (30s)
- Stdout/stderr capture
- Return code checking
- Error handling with graceful fallback

### 2. Danger-Level Approval
- **SAFE/LOW**: Auto-approved (read-only commands)
- **MEDIUM/HIGH**: Request approval via Control Protocol
- **CRITICAL**: Automatically denied (destructive commands)
- Pattern-based command classification

### 3. Audit Trail
- All commands logged to JSONL
- Timestamp, agent ID, tool name, params
- Success/failure status
- Compliance-ready (SOC2, GDPR, HIPAA)

### 4. Circuit Breaker
- Retry with exponential backoff for transient failures
- Maximum 3 retries per command
- Fail-fast for permanent errors

## Troubleshooting

### Issue: "Command denied"
Check danger level and permission rules. HIGH/CRITICAL commands require approval or are blocked.

### Issue: "Command timed out"
Increase timeout in `execute_bash_safely()` or use background execution.

### Issue: "Audit log not writable"
```bash
chmod 755 .kaizen/audit/devops
```

## Production Notes

### Security
- Never execute user input directly (validate/sanitize)
- Use permission policies for all commands
- Audit all actions for compliance
- Run agent with least privilege (non-root)

### Monitoring
- Track command success rates
- Monitor danger-level distribution
- Alert on CRITICAL command attempts
- Dashboard with Grafana/Prometheus

### Scaling
- Distribute tasks across multiple agents
- Use job queue for async execution
- Implement rate limiting for API protection

## Related Examples

- [Code Review Agent](../code-review-agent/) - File tools with permissions
- [Data Analysis Agent](../data-analysis-agent/) - HTTP tools with checkpoints
- [Interrupt Examples](../../interrupts/) - Graceful shutdown patterns
