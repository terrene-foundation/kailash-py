# PHASE 4: Validation

> **Usage**: Paste this AFTER all todos are complete (todos/active/ is empty)
> **Prerequisite**: All implementation todos in `todos/completed/`
> **Final Phase**: Human validates outcome and approves for release

---

## HUMAN INPUT REQUIRED

### Validation Scope

**Feature/Module Being Validated**: **\*\***\_\_\_**\*\***

### Validation Type

<!-- Check all that apply -->

- [ ] New feature validation
- [ ] Bug fix validation
- [ ] Parity validation (comparing old vs new system)
- [ ] Full system E2E validation

### If Parity Validation:

**Old System Location**: **\*\***\_\_\_**\*\***
**Expected Behavior Baseline**: **\*\***\_\_\_**\*\***

### LLM Configuration for NLP Evaluation

<!-- Check .env for model names - assume Claude's memory is outdated -->

**Model to Use**: (e.g., gpt-4, gpt-4-turbo)

---

## CLAUDE CODE INSTRUCTIONS

### Prerequisite Check

**STOP if implementation not complete:**

```
Required: todos/active/ is empty (all moved to completed/)
Required: All tests passing (100%)
Required: docs/00-developers/ updated
```

If not complete: **STOP EXECUTION**. Display: "BLOCKED: Phase 3 incomplete. Missing: [list specific items]". Do NOT proceed until resolved.

### Validation Tasks

#### 1. User Workflow Testing

Using `testing-specialist` and `e2e-runner`:

**1.1 Backend API Testing**
Test all workflows via backend API endpoints only:

- Document each endpoint tested
- Include request/response examples
- Verify expected outcomes

**1.2 Frontend API Testing**
Test all workflows via frontend API endpoints only:

- Verify frontend-backend integration
- Check error handling paths
- Document edge cases

**1.3 Browser Testing (Playwright)**
Using `e2e-runner`:

- Test complete user journeys in real browser
- Use Page Object Model patterns
- Collect artifacts on failure (screenshots, videos, traces)

#### 2. Workflow Documentation

For each user workflow tested:

1. **Step-by-Step Documentation**
   - Document each step in detail
   - Include expected state at each step
   - Document transitions between steps

2. **Test Generation**
   - Generate tests for each step
   - Generate tests for transitions
   - Include metrics collection

#### 3. Parity Validation (If Applicable)

**Only for parity validation - comparing old vs new system:**

**3.1 Old System Baseline**

1. Test run the OLD system through all required workflows
2. Document outputs for each workflow
3. Run multiple times to determine output type:
   - **Deterministic**: Labels, numbers, fixed values
   - **Natural Language**: Generated text, summaries, responses

**3.2 Output Classification**

| Output     | Type                | Evaluation Method            |
| ---------- | ------------------- | ---------------------------- |
| [Output 1] | Deterministic / NLP | Exact match / LLM evaluation |
| [Output 2] | Deterministic / NLP | Exact match / LLM evaluation |

**3.3 Natural Language Evaluation**

**CRITICAL: DO NOT test NLP outputs with simple keyword/regex assertions**

For natural language outputs, use LLM evaluation:

```python
from openai import OpenAI
import json

def evaluate_nlp_output(expected: str, actual: str, criteria: str) -> dict:
    """
    Use LLM to evaluate if actual output meets expected criteria.
    Returns: {"matches": bool, "confidence": float, "rationale": str}
    """
    client = OpenAI()  # Uses API key from .env

    response = client.chat.completions.create(
        model="gpt-4",  # Check .env for model name
        messages=[{
            "role": "system",
            "content": "You are an evaluator comparing expected vs actual NLP outputs."
        }, {
            "role": "user",
            "content": f"""
            Expected behavior: {expected}
            Actual output: {actual}
            Evaluation criteria: {criteria}

            Evaluate if the actual output matches the expected behavior.
            Return JSON: {{"matches": bool, "confidence": 0.0-1.0, "rationale": "..."}}
            """
        }],
        response_format={"type": "json_object"}
    )

    return json.loads(response.choices[0].message.content)

# Threshold for acceptance
CONFIDENCE_THRESHOLD = 0.85
```

**3.4 Parity Report**
Document:

- Feature parity: What old system did vs what new system does
- Output parity: Comparison results with confidence levels
- Gaps identified: Any functionality lost in transition

#### 4. Comprehensive Test Execution

Using `testing-specialist`:

**Before Integration/E2E tests:**

```bash
./tests/utils/test-env up && ./tests/utils/test-env status
```

NEVER run pytest directly for integration/E2E without verifying test-env is up.

1. **Run All Test Tiers**

   ```bash
   # Unit tests
   pytest tests/unit/ --timeout=1 -v

   # Integration tests (Docker must be running - verify with test-env status)
   pytest tests/integration/ --timeout=5 -v

   # E2E tests (Docker must be running - verify with test-env status)
   pytest tests/e2e/ --timeout=10 -v
   ```

2. **Coverage Report**

   ```bash
   pytest --cov=src --cov-report=term-missing --cov-report=html
   ```

3. **NO MOCKING Compliance**
   - Verify Tier 2-3 tests use real infrastructure
   - Flag any mocks in integration/E2E tests

#### 5. Self-Sustainability Validation

**EXIT CRITERIA**: Created agents and skills must work WITHOUT instruction templates.

**⚠️ HARD PREREQUISITE - FAIL IF MISSING:**

```
Required: .claude/agents/project/ with domain-specific agents
Required: .claude/skills/project/SKILL.md with project skills
Required: docs/00-developers/ with developer documentation
```

**If any of these are missing or empty:**

1. **STOP VALIDATION** - Do not proceed with Phase 4
2. **Create rework todos** in `todos/active/`:
   ```
   TODO-REWORK-001: Create [project]-analyst agent for [gap]
   TODO-REWORK-002: Expand SKILL.md with [missing pattern]
   TODO-REWORK-003: Document [feature] in docs/00-developers/
   ```
3. **Return to Phase 3 template** with rework todos
4. **Complete all rework todos** following Steps 1-8
5. **Resume Phase 4** only after rework todos complete

This is NOT a fallback - creating agents/skills on-the-fly in Phase 4 defeats the purpose of validation.

**Validation Test:**

1. Start a fresh Claude session (or new terminal)
2. Ask: "Using only the agents in `.claude/agents/project/` and skills in `.claude/skills/project/`, implement [simple feature X]"
3. Claude MUST be able to (all required):
   - Understand what to do (agents)
   - Know how to do it (skills)
   - Reference knowledge base (docs/00-developers/)

**FAIL CRITERIA:**
If Claude cannot complete without instruction templates:

1. **Identify gaps**: What did Claude need that wasn't in agents/skills?
2. **Create rework todos** for each gap identified
3. **Return to Phase 3** with rework todos
4. **Re-run validation test** after rework complete
5. Do NOT declare validation complete until test passes

**REWORK LIMITS:**
- Maximum 2 rework cycles allowed
- If still failing after 2nd rework: **ESCALATE to human for architectural review**
- Repeated failures indicate fundamental design issues, not implementation gaps

#### 6. Human Validation Checklist Generation

Generate a detailed checklist for human manual validation:

```markdown
## Manual Validation Checklist

### Pre-Conditions

- [ ] System is deployed/running
- [ ] Test data is populated
- [ ] User accounts are set up

### User Journey: [Name]

#### Steps

1. [ ] Navigate to [page/screen]
   - Expected: [what you should see]
   - Actual: **\*\***\_\_\_**\*\***

2. [ ] Perform [action]
   - Expected: [result]
   - Actual: **\*\***\_\_\_**\*\***

3. [ ] Verify [outcome]
   - Expected: [state]
   - Actual: **\*\***\_\_\_**\*\***

#### Edge Cases

- [ ] Empty input: **\*\***\_\_\_**\*\***
- [ ] Invalid input: **\*\***\_\_\_**\*\***
- [ ] Concurrent access: **\*\***\_\_\_**\*\***

#### Performance

- [ ] Response time < X ms
- [ ] Memory usage < Y MB
- [ ] No visible lag

### Acceptance Criteria Verification

- [ ] Criterion 1: [description] - PASS/FAIL
- [ ] Criterion 2: [description] - PASS/FAIL
- [ ] Criterion 3: [description] - PASS/FAIL
```

---

## PHASE 4 COMPLETE - FINAL GATE

Present to human:

### 1. Test Execution Summary

- Unit tests: X/Y passed (THRESHOLD: 100% required)
- Integration tests: X/Y passed (THRESHOLD: 100% required)
- E2E tests: X/Y passed (THRESHOLD: 100% required)
- Coverage: X% (THRESHOLD: 80% minimum, 100% for critical paths)

**FAIL VALIDATION if any threshold not met.**

### 2. Parity Validation Results (REQUIRED if parity validation selected)

- Deterministic outputs: All match / Mismatches: [list] (THRESHOLD: 100% match required)
- NLP outputs: Confidence scores for each (THRESHOLD: 0.85 minimum, 0.95 for critical)
- Overall parity: X% (THRESHOLD: 95% for migration, 90% for enhancement)

**FAIL VALIDATION if below thresholds.**

### 3. Self-Sustainability Assessment

- Agents created: [list] (REQUIRED: minimum 1)
- Skills created: [list] (REQUIRED: SKILL.md + minimum 1 pattern file)
- Validation test result: PASS/FAIL (REQUIRED: PASS)

**FAIL VALIDATION if any REQUIRED not met.**

### 4. Manual Validation Checklist

- Provide complete checklist for human execution
- Highlight critical paths to test

### 5. Artifacts Summary

- Code: [list of modules/files]
- Tests: [test file count by tier]
- Documentation: [docs created]
- Agents/Skills: [list if created]

---

## ⚠️ HUMAN VALIDATION GATE ⚠️

Human must manually validate using the checklist and respond:

- **APPROVED** - Proceed with PR/deployment
- **REVISE: [description]** - Claude fixes and re-validates
- **ABORT** - Implementation rejected, rollback

**Silence is NOT approval.** Wait for explicit response.

**This is the final quality gate before release.**

---

_Template Version: 2.0_
_Phase: 4 of 4 (Validation)_
