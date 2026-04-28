# kz Intelligence Architecture: Model-Driven vs Rule-Based

**Date**: 2026-03-21
**Finding**: 85-90% model-driven, 10-15% rule-based

---

## The Architecture Principle

COC is **deliberately asymmetric**:

- **Orchestration** (90% of decisions): Model reads natural language goals and JUDGES
- **Safety** (10% of decisions): Deterministic regex/pattern matching that BLOCKS

kz MUST replicate this exact ratio. The temptation will be to add rule-based routers, keyword matchers, and state machines for "reliability." Resist it. The model IS the reliability — rules are the safety floor.

## Decision Taxonomy

### Model-Driven (85-90%)

| Decision                       | How                                                           | Example                                                    |
| ------------------------------ | ------------------------------------------------------------- | ---------------------------------------------------------- |
| Which agent to invoke          | Model reads agent descriptions, semantic matching             | "This task involves database schema → dataflow-specialist" |
| Is analysis complete           | Red team convergence — agents judge gap closure               | "No more findings after 3 rounds → converged"              |
| What todos are missing         | Deep-analyst + requirements-analyst assess against plans      | "The plan mentions auth but no auth todo exists"           |
| Is a todo done                 | Tests pass + evidence provided + reviewer satisfied           | "File written, test passes, reviewer approves"             |
| Which specialist for this todo | Semantic match of todo description to specialist capabilities | "Todo says 'API endpoint' → nexus-specialist"              |
| Is redteam converged           | Agent consensus on findings                                   | "All agents report no remaining gaps"                      |
| What knowledge to codify       | Deep-analyst judges architectural significance                | "This pattern appeared 5 times → worth codifying"          |
| How to handle an error         | Model reads error taxonomy, decides retry/escalate/fail       | "429 → retry with backoff; 401 → ask user"                 |

### Rule-Based (10-15%)

| Decision                   | How                                                           | Mechanism      |
| -------------------------- | ------------------------------------------------------------- | -------------- |
| Is this a secret?          | Regex: `/AKIA[0-9A-Z]{16}/`, `/sk-[a-zA-Z0-9]{20,}/`          | EXIT 2 (BLOCK) |
| Is this a stub?            | Keyword: `TODO`, `FIXME`, `STUB`, `raise NotImplementedError` | EXIT 2 (BLOCK) |
| Is this command dangerous? | Pattern: `rm -rf /`, `mkfs.`, fork bomb syntax                | EXIT 2 (BLOCK) |
| Is a model name hardcoded? | String match: `"gpt-4"`, `"claude-3"` in code                 | WARN or BLOCK  |
| Do versions match?         | Compare version strings in pyproject.toml vs **init**.py      | WARN           |

### Hybrid (5%)

| Decision                 | Rule Part                             | Model Part                |
| ------------------------ | ------------------------------------- | ------------------------- |
| Is .env configured?      | File exists + key-model pairing check | Model explains what to do |
| Is pool config sensible? | PostgreSQL detection + env var lookup | Model recommends action   |

## Critical kz Design Implications

### 1. NO keyword-based agent routing

```python
# WRONG — rule-based routing
if "database" in task_description:
    agent = "dataflow-specialist"
elif "api" in task_description:
    agent = "nexus-specialist"

# RIGHT — model-driven routing
# Agent descriptions are in the system prompt.
# The model reads them and DECIDES which to invoke.
# Adding a new agent = adding a new .md file.
# No code changes needed.
```

### 2. NO state machine for phase transitions

```python
# WRONG — state machine
class PhaseState(Enum):
    ANALYZE = "analyze"
    TODOS = "todos"
    IMPLEMENT = "implement"

if state == PhaseState.ANALYZE and todos_created:
    transition_to(PhaseState.TODOS)

# RIGHT — goal-directed natural language
# The command file says "Red team until no gaps remain"
# The model decides when that goal is met
# Phase transitions are semantic, not mechanical
```

### 3. YES deterministic safety hooks

```python
# RIGHT — regex for secrets (always catch, never miss)
SECRET_PATTERNS = [
    re.compile(r'AKIA[0-9A-Z]{16}'),
    re.compile(r'sk-[a-zA-Z0-9]{20,}'),
    re.compile(r'ghp_[0-9a-zA-Z]{36}'),
]

# RIGHT — keyword for stubs (always catch, never miss)
STUB_PATTERNS = [
    re.compile(r'\bTODO\b'),
    re.compile(r'\bFIXME\b'),
    re.compile(r'\braise NotImplementedError\b'),
]
```

### 4. The anti-amnesia pattern is BOTH

The `user-prompt-rules-reminder` hook is RULE-BASED (runs on every turn, injects text). But what it injects is read by the MODEL as natural language instructions. This is the bridge between the two worlds:

```
Hook (RULE): Fire on every UserPromptSubmit
  → Read rules/*.md files
  → Summarize into 3-5 lines
  → Inject into model context
Model (INTELLIGENCE): Read injected summary
  → Re-activate compliance with rules
  → Apply zero-tolerance to next action
```

## kz Implementation Rule

**For every kz feature, ask: should the MODEL decide, or should a RULE decide?**

- If the answer is "safety" → RULE (deterministic, cannot be bypassed)
- If the answer is "intelligence" → MODEL (semantic, goal-directed)
- If the answer is "persistence" → HOOK (fires deterministically, content read by model)

The middleware pipeline reflects this:

- `DestructiveCommandGuard` → RULE
- `ToolPermissionChecker` → RULE + MODEL (rule checks policy, model decides edge cases)
- `EnvelopeChecker` → RULE (PACT dimensions are mathematical, not semantic)
- `BudgetPreChecker` → RULE (arithmetic, not judgment)
- Agent selection → MODEL
- Phase transitions → MODEL
- Convergence assessment → MODEL
- Error classification → MODEL (reads error taxonomy, applies judgment)
