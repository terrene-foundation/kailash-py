# User Flow: Autonomous Plan Generation and Execution

## 1. Overview

This flow describes how a user (or parent agent) submits a high-level objective and the kaizen-agents orchestration layer decomposes it into a governed plan, executes it with L3 primitives, and returns results.

---

## 2. Flow: "Review this codebase for security vulnerabilities"

### Step 1: User Submits Objective

```python
from kaizen.agents.l3 import AutonomousSupervisor

supervisor = AutonomousSupervisor(
    model="claude-sonnet-4-6",
    envelope=ConstraintEnvelope(
        financial=FinancialConstraints(max_cost=10.00),
        operational=OperationalConstraints(
            allowed_actions=["read_file", "grep", "lint", "write_report"],
            blocked_actions=["write_file", "execute_command"]
        ),
        temporal=TemporalConstraints(max_duration_seconds=3600),
        data_access=DataAccessConstraints(
            classification_ceiling=DataClassification.CONFIDENTIAL,
            allowed_scopes=["project-alpha"]
        ),
        communication=CommunicationConstraints(max_messages=100)
    ),
    tools=["read_file", "grep", "lint", "write_report"]
)

result = await supervisor.run("Review this codebase for security vulnerabilities")
```

### Step 2: TaskDecomposer (Orchestration Layer)

The supervisor's internal pipeline calls TaskDecomposer:

```
Input:
  objective: "Review this codebase for security vulnerabilities"
  envelope: { financial: $10, tools: [read, grep, lint, report], time: 1h }

Output (LLM-generated):
  subtasks:
    1. "Scan all Python files for common vulnerability patterns (SQL injection, XSS, command injection)"
    2. "Analyze authentication and authorization implementation"
    3. "Check dependency versions against known CVE databases"
    4. "Aggregate findings into a structured security report"
  rationale: "Parallel scanning across categories, sequential aggregation"
```

### Step 3: AgentDesigner + EnvelopeAllocator (Orchestration Layer)

For each subtask, generate an AgentSpec with appropriate tools and budget:

```
Subtask 1 → AgentSpec(
    spec_id="vuln-scanner",
    tools=["read_file", "grep"],
    envelope={ financial: $2.50, time: 20min },
    capabilities=["code-analysis", "pattern-matching"]
)

Subtask 2 → AgentSpec(
    spec_id="auth-reviewer",
    tools=["read_file", "grep"],
    envelope={ financial: $2.50, time: 20min },
    capabilities=["code-analysis", "auth-patterns"]
)

Subtask 3 → AgentSpec(
    spec_id="dep-checker",
    tools=["read_file"],
    envelope={ financial: $1.50, time: 10min },
    capabilities=["dependency-analysis"]
)

Subtask 4 → AgentSpec(
    spec_id="report-writer",
    tools=["write_report"],
    envelope={ financial: $2.00, time: 10min },
    capabilities=["report-generation"],
    required_context_keys=["scan_results", "auth_results", "dep_results"]
)

Reserve: $1.50 (contingency for retries/recovery)
```

### Step 4: PlanComposer (Orchestration Layer)

Wire subtasks into a Plan DAG:

```
Plan DAG:
  [vuln-scanner] ──DataDependency──┐
  [auth-reviewer] ─DataDependency──┼── [report-writer]
  [dep-checker] ──DataDependency───┘

  Edges:
    vuln-scanner → report-writer (DataDependency)
    auth-reviewer → report-writer (DataDependency)
    dep-checker → report-writer (DataDependency)

  Topology: Fan-out (3 parallel scanners) → Fan-in (1 aggregator)
```

### Step 5: PlanValidator (SDK — Deterministic)

```
validate_structure(plan):
  ✓ No cycles
  ✓ All edges reference existing nodes
  ✓ Root nodes: vuln-scanner, auth-reviewer, dep-checker
  ✓ Leaf node: report-writer
  ✓ Input mappings consistent with edges

validate_envelopes(plan):
  ✓ Sum($2.50 + $2.50 + $1.50 + $2.00) = $8.50 <= $10.00
  ✓ Each node envelope tighter than parent
  ✓ Tool subsets valid
```

### Step 6: PlanEvaluator (Orchestration Layer — LLM)

```
Semantic check:
  ✓ Decomposition covers the objective (vulnerability scanning, auth, deps)
  ✓ Tools match capabilities (grep for scanning, read_file for analysis)
  ✓ Data flow is correct (scanners produce findings, aggregator consumes them)
  ✓ Budget is reasonable for scope

Result: PASS
```

### Step 7: PlanExecutor (SDK — Deterministic)

```
Execution:
  1. NodeReady: vuln-scanner, auth-reviewer, dep-checker (all roots)
  2. Spawn 3 agents in parallel via AgentFactory
     - Each gets: scoped context, bounded envelope, communication channel
  3. Agents execute (LLM calls happen here)
  4. NodeCompleted: vuln-scanner (found 3 issues, spent $1.80)
     - Budget reclaimed: $0.70 returned to parent pool
  5. NodeCompleted: auth-reviewer (found 1 issue, spent $2.10)
     - Budget reclaimed: $0.40 returned to parent pool
  6. NodeCompleted: dep-checker (found 2 CVEs, spent $0.90)
     - Budget reclaimed: $0.60 returned to parent pool
  7. NodeReady: report-writer (all dependencies met)
  8. Spawn report-writer with context from scanners
  9. NodeCompleted: report-writer (report generated, spent $1.50)
  10. PlanCompleted: all nodes done

Total spent: $6.30 / $10.00 budget
Events emitted: 14 (ready, started, completed for each node + plan)
```

### Step 8: Result Returned to User

```python
result = SecurityReport(
    summary="Found 6 security issues across 3 categories",
    findings=[
        Finding(severity="HIGH", category="SQL Injection", file="api/users.py", line=42),
        Finding(severity="HIGH", category="XSS", file="templates/profile.html", line=18),
        Finding(severity="MEDIUM", category="Command Injection", file="utils/shell.py", line=7),
        Finding(severity="MEDIUM", category="Missing Auth", file="api/admin.py", line=1),
        Finding(severity="HIGH", category="CVE-2026-1234", dependency="requests==2.28.0"),
        Finding(severity="MEDIUM", category="CVE-2026-5678", dependency="flask==2.2.3"),
    ],
    budget_used="$6.30 / $10.00",
    agents_spawned=4,
    audit_trail_id="plan-abc123"
)
```

---

## 3. Failure Flow: Node Fails Mid-Execution

### Scenario: auth-reviewer encounters an error

```
Step 1: auth-reviewer fails with "rate limit exceeded"
Step 2: PlanExecutor classifies per gradient:
  - retry_budget: 2 → retry count 0 < 2 → AutoApproved (retry)
Step 3: NodeRetrying { node: auth-reviewer, attempt: 1, max: 2 }
Step 4: Agent respawned, retry succeeds
Step 5: Normal flow continues

Alternative: After 2 retries, still failing:
Step 6: retry_budget exhausted → after_retry_exhaustion: HELD
Step 7: NodeHeld { node: auth-reviewer, reason: "retries_exhausted" }
Step 8: FailureDiagnoser analyzes:
  - Error: rate limit → retryable but persistent
  - Diagnosis: "Rate limit on API. Suggest: reduce concurrency or switch model."
Step 9: Recomposer generates PlanModification:
  - UpdateSpec { node: auth-reviewer, new_spec: { model: "haiku", ... } }
Step 10: Modification applied, node restarts with cheaper model
Step 11: Node completes, flow resumes
```

---

## 4. Governance Visibility Flow

### What the audit trail records

```
EATP Records for this plan execution:
  1. Genesis Record: supervisor created (envelope: $10, tools: [read, grep, lint, report])
  2. Delegation Record: supervisor → vuln-scanner (envelope: $2.50)
  3. Delegation Record: supervisor → auth-reviewer (envelope: $2.50)
  4. Delegation Record: supervisor → dep-checker (envelope: $1.50)
  5. Audit Anchor: auth-reviewer retry (attempt 1)
  6. Audit Anchor: auth-reviewer model switch (UpdateSpec)
  7. Delegation Record: supervisor → report-writer (envelope: $2.00)
  8. Budget Reclamation: $0.70 from vuln-scanner
  9. Budget Reclamation: $0.40 from auth-reviewer
  10. Budget Reclamation: $0.60 from dep-checker
  11. Budget Reclamation: $0.50 from report-writer
  12. Audit Anchor: plan completed (total: $6.30)

Post-hoc query: "Show me every action the auth-reviewer took"
→ Returns: delegation envelope, model used, retry count, budget consumed, findings produced
```

---

## 5. Progressive Disclosure: Minimal Example

For users who don't need full governance:

```python
# Minimal — no explicit envelope (uses sensible defaults)
from kaizen.agents.l3 import AutonomousSupervisor

supervisor = AutonomousSupervisor(model="claude-sonnet-4-6")
result = await supervisor.run("Summarize this document")
# Default envelope: $1 budget, 5min timeout, all tools, PUBLIC classification
# Still gets: plan generation, typed messaging, audit trail
# Just without strict governance constraints
```
