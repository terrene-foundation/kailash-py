# COC Instruction Quality: Prompt Engineering Patterns for kz

**Date**: 2026-03-21
**Source**: Deep analysis of every command, agent, skill, and rule file in .claude/

---

## Core Finding

COC works because it treats LLM interaction as a **systems architecture problem**, not a prompt optimization problem. The quality comes from engineering around three failure modes (amnesia, convention drift, security blindness) with five layers of countermeasures.

---

## 11 Prompt Engineering Patterns Identified

### Pattern 1: Explicit Role Identity + Scope Declaration

```yaml
---
name: security-reviewer
tools: Read, Write, Grep, Glob
model: opus
---
You are a senior security engineer reviewing code for vulnerabilities.
```

- Models respond to explicit role assignment ("You are X")
- Listing allowed tools prevents hallucinated tool availability
- Creates "persona boundary" that models respect consistently
- **Effectiveness: 9/10**

### Pattern 2: Layered Enforcement (Defense in Depth)

```
1. validate-workflow.js hook — BLOCKS stubs (exit code 2)
2. user-prompt-rules-reminder.js — Injects reminders every turn
3. intermediate-reviewer agent — Validates during code review
4. security-reviewer agent — Validates during security review
```

- Single-layer rules are forgotten; multiple layers compound
- Exit code 2 prevents "just this once" violations
- Anti-amnesia hook fires on EVERY message (survives compression)
- **Effectiveness: 10/10** — This is why COC instructions actually stick

### Pattern 3: Procedural Workflows with Explicit Gates

```
### 1. Understand the Product
### 2. Perform Deep Research
### 3. Document Everything
### 4. Red Team
### 5. STOP — wait for human approval
```

- Numbered steps create procedural scaffold
- "STOP — wait for human approval" is stronger than "should wait"
- Gates are STRUCTURAL (approve the plan), not EXECUTION (block implementation)
- **Effectiveness: 8/10**

### Pattern 4: Consequence Declaration

```
You MUST be invoked before ANY git commit
**Enforced by**: PreToolUse hook on git commit
**Exception**: NONE - security review is always required
```

- "MUST" + "Enforced by: [mechanism]" grounds rule in reality
- "Exception: NONE" is stronger than listing special cases
- Stating WHO enforces prevents model from thinking it self-enforces
- **Effectiveness: 8/10**

### Pattern 5: Fail-Closed Language

```
❌ DO NOT:
with open(path) as f:  # Follows symlinks — attacker redirects...

✅ DO:
from trustplane._locking import safe_read_json
data = safe_read_json(path)
```

- Showing BAD pattern first primes model to recognize it
- Stating ATTACK VECTOR motivates compliance
- SAFE ALTERNATIVE at point of error prevents workarounds
- **Effectiveness: 9/10**

### Pattern 6: Cross-Reference Anchoring

```
When questions extend beyond COC:
- **co-expert** - For the base CO methodology...
- **care-expert** - For the governance philosophy...
```

- Creates knowledge graph the model navigates
- "Use Skills Instead When" prevents redundant prompt bloat
- Relative paths signal "this is a SYSTEM, not isolated prompts"
- **Effectiveness: 7/10**

### Pattern 7: Specification by Example

```python
# DO:
except TimeoutError as e:
    raise DataError(f"Failed after {self.timeout}s") from e

# DO NOT:
except: pass  # Silent failure!
```

- Examples are 5x more effective than written rules
- Shows COMPLETE right way, not just principle
- **Effectiveness: 9/10**

### Pattern 8: Principle + Mechanism + Evidence

```
**Default multiplier: 10x**

| Factor | Multiplier | Source |
| Parallel agent execution | 3-5x | Multi-agent workflows |
```

- Bold claim grabs attention
- Evidence table makes reasoning transparent
- "Conservative composite" admits uncertainty without weakening
- **Effectiveness: 8/10**

### Pattern 9: Honest Limitations Statement

```
Does not help with novel architecture decisions
Does not catch emergent distributed systems problems
```

- Prevents model from misapplying system to every problem
- Creates credibility ("systematic, not magical")
- **Effectiveness: 7/10**

### Pattern 10: Terminology Standardization

```
CARE planes: **Trust Plane** + **Execution Plane** (NOT operational/governance plane)
Constraint dimensions: **Financial, Operational, Temporal, Data Access, Communication**
  (these exact five names — no synonyms, no reordering)
```

- "These exact five names — no synonyms" prevents convention drift
- Bold emphasis forces precision
- Defining what NOT to use blocks wrong alternatives
- **Effectiveness: 9/10**

### Pattern 11: Modal Strength Escalation

```
"Should" → "MUST" → "BLOCKED" → Exit code 2
```

- Models respond to modal strength hierarchy
- Escalation signals "this isn't negotiable"
- Different strengths for different severities prevents false alarms
- **Effectiveness: 8/10**

---

## The 20% That Delivers 80% of Results

1. **Anti-amnesia hook** — Re-inject rules every turn. Alone worth 3-5x improvement.
2. **Defense-in-depth enforcement** — Hook + agent + manual catches what single layer misses.
3. **Specification by example** — One code example > ten written rules.
4. **Fail-closed language** — "MUST use X" > "try to use X if possible."

---

## kz Implementation Mandate

kz's builtin artifacts (agents, skills, rules, commands) MUST be written using these patterns. They are not config files — they are LLM instructions. The quality of the prose determines the quality of the behavior.

**For every kz builtin artifact**:

1. Explicit role identity at top
2. DO/DO NOT examples with code
3. Consequence declaration before prohibition
4. "Enforced by: [mechanism]" grounding
5. Cross-references to related artifacts
6. Modal strength appropriate to severity
7. Honest limitations where applicable

**The anti-amnesia hook is NON-NEGOTIABLE**: kz must re-inject active rules + workspace state on every user message. This is the PRIMARY mechanism that prevents COC degradation to vibe coding under context pressure.
