# Bug Fix Instructions

*Copy-paste this entire section to Claude Code for bug fixes and small changes*

---

You are fixing a bug. Follow these steps exactly and show me complete outputs at each step. Do not summarize or skip any validation steps.

## 1. CONTEXT LOADING AND ERROR INVESTIGATION

### Essential Context Loading
Load these files before starting (DO NOT proceed until loaded):
- Root `CLAUDE.md` - Core validation rules and critical patterns
- `sdk-users/CLAUDE.md` - Implementation patterns and architectural guidance
- Use MCP tools to search for related error patterns in `sdk-users/2-core-concepts/validation/common-mistakes.md`

### Critical Understanding Required
- **3-tier testing strategy**: Unit (fast, mocks OK), Integration (real Docker, NO MOCKS), E2E (complete flows, NO MOCKS)
- **Real Docker infrastructure requirement** - never skip this for integration tests
- **Framework-first approach** - check existing solutions before creating new code
- **NO MOCKING policy** for Tier 2/3 tests - this is absolutely critical

### Error Investigation Process
If you encounter any error during implementation, use this investigation approach:

1. **Check common mistakes first:**
   - Use MCP tools to search `sdk-users/2-core-concepts/validation/common-mistakes.md`
   - Is this a known issue with documented solution?
   - Have we seen this error pattern before?

2. **Check existing code for patterns:**
   - Use MCP tools to search `src/kailash/` for similar implementations
   - Use MCP tools to search `tests/` for how existing tests handle similar scenarios
   - Use MCP tools to search `apps/` frameworks for established patterns

3. **Verify environment setup:**
   - Is Docker running? Show: `docker ps`
   - Are services healthy? Show: `./tests/utils/test-env status`
   - Are all required services started?

4. **Create minimal reproduction:**
   - Show me the full error message
   - Create the smallest possible test case that reproduces the issue
   - Identify the specific line or component causing the failure

**Show me your investigation results at each step. Do not proceed until the error is fully understood and resolved.**

## 2. SYSTEMATIC BUG ANALYSIS

Before writing any code, analyze the bug thoroughly and completely:

### Expected vs Actual Behavior Analysis
- **What is the expected behavior?** (Be specific - show exact expected output)
- **What is the actual behavior?** (Show exact error/output with complete stack trace)
- **When did this start happening?** (Recent changes, environment changes)
- **What conditions trigger the bug?** (Specific inputs, configurations, timing)

### Existing Solutions Check
- Use MCP tools to search for similar fixes in `src/kailash/`
- Use MCP tools to search `apps/kailash-dataflow/`, `apps/kailash-mcp/`, `apps/kailash-nexus/` for related patterns
- Check if existing tests cover this scenario - if not, that's likely part of the bug
- Look for similar error patterns in closed issues or previous fixes

### Root Cause Analysis
- **What component is failing?** (Be specific - file, function, line number)
- **What was the code trying to do when it failed?** (Intended operation)
- **What assumptions were made that turned out to be wrong?** (Input validation, state assumptions)
- **Are there any recent changes that might have caused this?** (git log analysis)

### Impact Assessment
- **What functionality is broken?** (User-visible impact)
- **What other components might be affected?** (Downstream dependencies)
- **How critical is this bug?** (Severity assessment)
- **Are there workarounds available?** (Temporary solutions)

**Show me your complete analysis before proceeding. Do not proceed until you've thoroughly understood the bug.**

## 3. WRITE FAILING TEST FIRST

Create a test that reproduces the bug BEFORE fixing it. This is critical for test-driven development.

### Test Creation Strategy
- **For unit-level bugs**: Place in `tests/unit/test_[component].py`
- **For integration bugs**: Place in `tests/integration/test_[component].py`
- **For E2E bugs**: Place in `tests/e2e/test_[feature].py`

### Test Requirements
- Test must reproduce the exact bug scenario
- Test must fail for the right reason (the bug, not test setup issues)
- Test must be minimal and focused on the specific bug
- Test must follow existing test patterns in the codebase

### Test Setup and Execution
**For integration tests**: Always run `./tests/utils/test-env up && ./tests/utils/test-env status` first

**Run test to confirm it fails:**
`pytest tests/unit/test_[component].py::test_[specific_test] -v`

**Show me the failing test output - the test must fail for the right reason.**

### Test Validation
- Does the test fail with the expected error?
- Does the test actually reproduce the bug conditions?
- Is the test isolated and doesn't depend on other tests?
- Does the test follow the 3-tier testing strategy?

**Do not proceed with the fix until you have a reproducible failing test.**

## 4. IMPLEMENT MINIMAL BUG FIX

### Fix Implementation Principles
- **Make the smallest possible change** to fix the issue
- **Follow existing code patterns** in the same file/module
- **Do not refactor unrelated code** - focus only on the bug
- **Ensure 100% kailash SDK compliance**
- **Do not assume any new functionality** without verifying it exists

### Fix Implementation Process
1. **Identify the exact line(s) causing the bug**
2. **Understand why the current code fails**
3. **Design the minimal fix** that addresses the root cause
4. **Implement the fix** following existing patterns
5. **Verify the fix doesn't break existing functionality**

### Fix Validation Requirements
- Does the fix address the root cause?
- Does the fix follow established SDK patterns?
- Is the fix minimal and focused?
- Are there any potential side effects?

**Show me the specific code changes (before/after diff) and explain why this fix addresses the root cause.**

## 5. COMPREHENSIVE FIX VERIFICATION

Run tests in this exact order and show me complete outputs:

### Step 1: Verify the Fix Works
**Run the failing test** to confirm it now passes:
`pytest tests/unit/test_[component].py::test_[specific_test] -v`

**Expected result**: The test should now pass

### Step 2: Run Related Unit Tests
**Run all related unit tests** to ensure no regressions:
`pytest tests/unit/test_[affected_component].py -v`

**Expected result**: All unit tests should pass

### Step 3: Run Integration Tests (if applicable)
**If integration tests exist** for the affected component:
1. Start Docker infrastructure:
   `./tests/utils/test-env up && ./tests/utils/test-env status`
2. Run integration tests:
   `pytest tests/integration/test_[affected_component].py -v`

**Expected result**: All integration tests should pass

### Step 4: Run Broader Test Suite
**Run all unit tests** to catch any unexpected regressions:
`pytest tests/unit/ -v`

**Expected result**: All unit tests should pass

**Show me the COMPLETE test output from each command. Do not summarize. Do not proceed if any tests fail.**

### Step 5: Update documentation (if needed)
If the bug fix affects documented behavior:
1. **Update relevant documentation files**
   - Look through the docs in `sdk-users/`, using the `CLAUDE.md` as the entrypoint.
   - Important directories are `3-development/`, `2-core-concepts/nodes/`, `2-core-concepts/cheatsheet/`, and `migration-guides`.
   - Check for any outdated or incorrect information with respect to the bug fix.

2. **Create temp test files** to validate examples: `/tmp/test_bugfix_docs.py`

3. **Run documentation tests** with real infrastructure

4. **Check if similar patterns exist** in `sdk-users/2-core-concepts/validation/common-mistakes.md` and document the fix pattern for future reference

**Show me the final validation results and any documentation updates you've made.**

## 6. SIDE EFFECTS AND REGRESSION ANALYSIS

### Component Impact Analysis
Analyze potential side effects of your fix:

1. **What other components use the fixed code?**
   - Search for imports and references
   - Check for downstream dependencies
   - Verify interface contracts are maintained

2. **Are there any performance implications?**
   - Does the fix add computational overhead?
   - Are there memory usage changes?
   - Are there timing-sensitive operations affected?

3. **Are there any behavioral changes?**
   - Does the fix change expected outputs?
   - Are there new error conditions?
   - Are there configuration changes needed?

### Regression Prevention
- **Run the full test suite** to catch any regressions
- **Check for similar bugs** in related components
- **Verify error handling** is comprehensive
- **Ensure logging is appropriate** for debugging

### Documentation Impact
- **Does the fix change documented behavior?**
- **Are there new error conditions to document?**
- **Do any examples need updating?**
- **Are there migration notes needed?**

**Show me your impact analysis and any additional validation steps you've taken.**

## 7. FINAL VALIDATION CHECKLIST

Before declaring the bug fixed, verify every item on this checklist:

### Test Results Verification
- [ ] **Original failing test now passes** (show complete output)
- [ ] **All related unit tests pass** (show complete output)
- [ ] **All integration tests pass** (show complete output)
- [ ] **No regressions in broader test suite** (show complete output)
- [ ] **Test coverage maintained or improved**

### Code Quality Verification
- [ ] **Fix follows existing SDK patterns** (show pattern consistency)
- [ ] **Fix is minimal and focused** (show code diff)
- [ ] **No unrelated code changes** (show git diff)
- [ ] **Proper error handling included** (show error paths)
- [ ] **Appropriate logging added** (show logging statements)

### Documentation Verification
- [ ] **No documentation changes needed** OR **documentation updated and validated**
- [ ] **Examples still work** (show validation results)
- [ ] **Error messages are helpful** (show error output)
- [ ] **Migration notes added if needed** (show migration guidance)

### Integration Verification
- [ ] **Docker infrastructure working** (show test-env status)
- [ ] **All services healthy** (show service status)
- [ ] **No environmental issues** (show environment validation)
- [ ] **Ready for deployment** (show deployment readiness)

### Final Confirmation
- [ ] **Bug is definitively fixed** (show before/after comparison)
- [ ] **No new bugs introduced** (show regression testing results)
- [ ] **Performance impact acceptable** (show performance analysis)
- [ ] **Ready for code review** (show final git status)

**Show me the final test results confirming everything works. Include complete output for:**
- Final test run showing the bug is fixed
- Complete regression test results
- Docker environment status
- Git status showing changes ready for commit

**Do not declare the bug fixed until all checklist items are verified and you've shown me the complete outputs for every validation step.**

## 8. POST-FIX VALIDATION

### Environment Cleanup
After completing the bug fix:
1. **Verify test environment is clean:**
   `./tests/utils/test-env status`
2. **Check for any leftover artifacts:**
   - Temporary files
   - Test databases
   - Debug outputs
