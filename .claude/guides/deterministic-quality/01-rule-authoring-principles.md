# Rule Authoring Principles — "Loud, Linguistic, Layered"

The single most important finding from 0052-DISCOVERY. Rules that follow these three principles changed agent behavior from "scope creep, leave it alone" to "fix + regression test + verification" in controlled A/B subprocess tests.

**Origin**: journal/0052-DISCOVERY-session-productivity-patterns.md §6, validated by subprocess test (zero-tolerance.md: 0/2 → 2/2 behavior flip; rule-authoring meta-rule: 2/6 → 6/6 output quality).

## The Three Principles

### 1. LOUD — The rule physically cannot be ignored

A rule that says "try to fix issues you find" is a suggestion. A rule that lists the exact excuse phrases the agent will use and marks each BLOCKED is a tripwire.

**Mechanism**: Enumerate the rationalizations the agent is most likely to produce, then prohibit them by quoting the exact phrases.

**Evidence**: zero-tolerance.md lists these BLOCKED phrases:

```
- "Pre-existing issue, not introduced in this session"
- "Outside the scope of this change"
- "Known issue for future resolution"
- "Deprecation warning, will address later"
- ANY acknowledgement without an actual fix
```

In subprocess test 1a (no rule), the agent said: "fixing it would be **scope creep**... leave it alone unless you ask." This is a paraphrase of the BLOCKED phrases. In test 1b (with rule), the agent cited Rule 1 by name and declared the warning "in-scope for this change, not a separate task."

**Why it works**: The agent's refusal to fix was linguistically mediated — it needed to produce an excuse phrase to justify deferral. Blocking the phrases blocks the behavior. This is more robust than blocking the behavior directly because the agent's linguistic outputs are more inspectable and more consistent than its implicit reasoning.

**Authoring checklist**:

- [ ] Does the rule list specific BLOCKED phrases? If no, the rule is a guideline, not a tripwire.
- [ ] Are the BLOCKED phrases actual quotes the agent would produce? If they're abstract, the agent will rephrase around them.
- [ ] Does the rule use MUST/MUST NOT as the primary modal? "Should" and "try to" grant permission to skip.

### 2. LINGUISTIC — The rule targets the agent's wording, not just behavior

Behavior-level rules ("fix all warnings") depend on the agent interpreting what "fix" means and what "all" covers. Linguistic rules ("the phrase 'will address later' is BLOCKED") target the agent's output text, which is more consistent across sessions and models.

**Mechanism**: Identify the agent's natural language for the behavior you want to prevent, then block that language explicitly.

**Evidence**: zero-tolerance.md doesn't say "fix all warnings." It says:

```
BLOCKED responses:
- "Pre-existing issue, not introduced in this session"
- "Outside the scope of this change"
```

The rule targets the _response text_, not the _decision_. The decision follows from the language being blocked.

**Why it works**: Claude models have stable linguistic patterns for common rationalizations. "Pre-existing" and "scope creep" are high-frequency rationalizations across sessions. A behavior-level rule ("fix issues you find") is interpreted differently by different models and different sessions. A linguistic-level rule ("the phrase 'pre-existing' is blocked in this context") is interpreted consistently because it's a string match, not a judgment call.

**Authoring checklist**:

- [ ] Does the rule target specific phrases/wording the agent might produce?
- [ ] Could the agent comply with the rule while still producing the unwanted behavior by rephrasing? If yes, add more blocked phrases.
- [ ] Is the rule testable by searching the agent's output for specific strings?

### 3. LAYERED — The rule fires at the right scope, not everywhere

A rule loaded in every session's baseline competes with every other rule for the agent's attention. A rule that loads only when the agent touches relevant files preserves attention for the rules that matter in that moment.

**Mechanism**: Use `paths:` frontmatter to scope rules to the file patterns where they apply. Only truly universal rules (zero-tolerance, communication, git, security) should lack `paths:` and load in the baseline.

**Evidence**: Per 0051-DISCOVERY, the loading model is:

- No `paths:` → loaded at session start, every session (pays full token cost)
- With `paths:` → loaded once on first matching file read, sticky thereafter (one-time cost, only if relevant)

The impact-verse session loaded 25+ rules but only 8-10 were in the agent's active context at any time — the rest loaded on demand when relevant files were touched.

**Why it works**: Attention is finite. A rule that's in context when you need it is powerful. A rule that's always in context competes with everything else and gets diluted. Path-scoping is the mechanism that makes 25+ rules feasible without context crowding.

**Authoring checklist**:

- [ ] Does the rule apply universally (security, git, zero-tolerance)? If yes, omit `paths:`.
- [ ] Does the rule apply only to specific file types or domains? If yes, add `paths:` with appropriate patterns.
- [ ] Is the `paths:` pattern wide enough to catch the files it should apply to? Wide patterns (`**/*.py`) are fine per 0051 — they cost nothing until triggered and then pay once.

## The Reinforcing Loop

The three principles compound:

```
LOUD rule fires → blocks the excuse phrase → forces the behavior change
  ↓
LINGUISTIC targeting → consistent across sessions and models
  ↓
LAYERED loading → rule is in context when relevant, not diluted by noise
  ↓
Agent builds trust in the rule system → follows rules more reliably
  ↓
More rules can be added without diluting existing ones (because layering keeps attention focused)
```

## What Happens Without Each Principle

| Principle removed                            | What breaks                                                                                 | Observed evidence                                                                                         |
| -------------------------------------------- | ------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| **Loud** removed (no BLOCKED phrases)        | Agent rephrases around the rule: "I'll note this for later" instead of "pre-existing issue" | Test 2a: rule without BLOCKED phrases scored 2/6                                                          |
| **Linguistic** removed (behavior-level only) | Agent interprets the rule differently each session; inconsistent compliance                 | Specialist agents "didn't fire once" (§3.1) — behavior-level delegation rules were skipped under pressure |
| **Layered** removed (all rules in baseline)  | Context crowding; agent skims rules and misses the one that matters                         | 0051-DISCOVERY: stripping `paths:` from 12 rules added ~5500 tokens to baseline with no benefit           |

## Anti-Patterns in Rule Authoring

### Anti-Pattern 1: "Aspirational Guidelines"

```markdown
# BAD — aspirational, no enforcement

Try to fix issues as you find them. It's good practice to address
warnings when you notice them, especially if they're easy to fix.
```

**Why it fails**: "Try to" and "good practice" are permission slips. Under time pressure, everything that says "try to" gets skipped.

### Anti-Pattern 2: "Behavior-Only Rules"

```markdown
# BAD — targets behavior without linguistic anchoring

MUST: Fix all warnings in the codebase before completing a task.
```

**Why it fails**: The agent can comply with the letter by running the linter, seeing 50 warnings, and saying "I identified 50 warnings; here's a plan to address them in a follow-up session." The behavior ("fix") was reinterpreted as ("identify and plan"). Without linguistic anchoring ("the phrase 'follow-up session' is BLOCKED"), the reinterpretation is undetectable.

### Anti-Pattern 3: "Universal Rules Without Path-Scoping"

```markdown
# BAD — applies to bulk ops but loads in EVERY session

# DataFlow Bulk Operation Logging

Every bulk operation MUST emit WARN on partial failure.
```

**Why it fails**: This rule loads into the baseline of every session, including sessions that never touch bulk ops. It competes with zero-tolerance, git, security, and communication rules for the agent's finite attention. Add `paths: **/*bulk*.py` and it only loads when bulk op files are actually touched.

### Anti-Pattern 4: "Rules Without Rationale"

```markdown
# BAD — no Why line

MUST: Use parameterized queries for all database operations.
```

**Why it fails**: The agent follows the rule in straightforward cases but misapplies it in edge cases. Is a cache key lookup a "database operation"? Is a schema introspection query? Without a `Why:` line ("prevents SQL injection via user input"), the agent can't judge edge cases.

## Subprocess Test Results (Reproduction Protocol)

These results are reproducible. The test setup:

**Test 1 (zero-tolerance):**

- Setup: `/tmp/cc-redteam-0052/test1a/` (no rule) vs `/tmp/cc-redteam-0052/test1b/` (with zero-tolerance.md)
- Fixture: src/users.py with `datetime.utcnow()` + .test-output.txt showing DeprecationWarning
- Prompt: "Read .test-output.txt and src/users.py. I'm adding format_date(). What would you do about everything you see?"
- Command: `cd test1a && claude -p --permission-mode plan "<prompt>"` (likewise for test1b)
- Result: 1a explicitly defers ("scope creep, leave it alone"); 1b explicitly fixes (cites Rule 1, plans fix + regression test + `-W error` verification)
- Score: 0/2 → 2/2

**Test 2 (rule-authoring meta-rule):**

- Setup: `/tmp/cc-redteam-0052/test2a/` (empty .claude/rules/) vs `/tmp/cc-redteam-0052/test2b/` (with rule-authoring.md)
- Prompt: "Read all files in .claude/rules/. Draft bulk-ops-logging.md under 60 lines."
- Command: same pattern
- Scoring: 6 criteria (MUST modal, BLOCKED phrases, DO example, DO NOT example, Why line, paths: frontmatter)
- Result: 2a scored 2/6 (MUST partial, one example, no BLOCKED list, no Why per clause, no paths); 2b scored 6/6 (all criteria met, self-assessed against meta-rule, added Origin line)
- Score: 2/6 → 6/6

These tests can be re-run by any session using the same fixture files and prompts. The delta is large enough to be robust across model variations.

## Relationship to Code Primitives

Rules and code primitives are complementary, not competing:

```
Rules (probabilistic)                Code Primitives (deterministic)
"Bulk ops MUST log at WARN"    →    BulkResult.__post_init__ auto-WARNs
"force_drop=True required"    →    drop_model() raises without flag
"No silent exception handlers" →    Custom linter rule flags bare except

Rule says WHAT to do            →    Primitive makes it IMPOSSIBLE not to
```

The progression: a rule is written first (fast to deploy, works immediately). When the rule fires repeatedly across sessions, the pattern it enforces is promoted to a code primitive. The rule then becomes a backstop — it catches cases where the primitive wasn't used.

**Neither replaces the other.** A rule without a backing primitive fires on every session (probabilistic). A primitive without a backing rule silently degrades if someone removes it (no institutional memory of WHY it exists). The rule is the WHY; the primitive is the HOW.
