# Kailash SDK Migration Directives

## 📋 Migration Process Overview

This guide provides strict directives for implementing the Kailash SDK migration using Test-Driven Development (TDD) and continuous validation.

## 🧪 TEST-FIRST DEVELOPMENT (MANDATORY)

Write tests BEFORE implementation. This prevents missing tests and ensures working code. You MUST follow the 3-tier testing strategy exactly as specified in `sdk-users/3-development/testing/regression-testing-strategy.md` and `sdk-users/3-development/testing/test-organization-policy.md`.

### Critical Requirements

**Always ensure that your TDD covers all the detailed todo entries**

Do not write new tests without checking that existing ones can be modified to include them. You MUST have all 3 kinds of tests:

### Tier 1: Unit Tests
- **Location**: `tests/unit/`
- **Requirements**: 
  - Fast execution (<1s per test)
  - Can use mocks
  - No external dependencies
  - No sleep statements
- **Coverage**: 
  - All public methods
  - Edge cases
  - Error conditions
  - Business logic validation
- **Pattern**: Follow existing test patterns in the codebase

### Tier 2: Integration Tests
- **Location**: `tests/integration/`
- **Requirements**:
  - **NO MOCKING** - must use real Docker services
  - Test actual component interactions
  - Use docker implementation in `tests/utils`
- **Setup**: Always run before tests:
  ```bash
  ./tests/utils/test-env up && ./tests/utils/test-env status
  ```

### Tier 3: E2E Tests
- **Location**: `tests/e2e/`
- **Requirements**:
  - **NO MOCKING** - complete scenarios with real infrastructure
  - Test complete user workflows from start to finish
  - Use real data, processes, and responses
- **Coverage**:
  - Complete business workflows
  - Multi-module interactions
  - Performance requirements

### Test Quality Validation

Before proceeding with implementation, validate all tests:

1. **Business Logic Coverage**
   - [ ] Tests replicate required original business logic
   - [ ] All acceptance criteria from todos covered
   - [ ] Edge cases and error paths tested

2. **Test Legitimacy Checks**
   - [ ] Tests verify intended functionality, not just syntax
   - [ ] Tests cover actual behavior, not trivial conditions
   - [ ] Tests are not placeholders or empty stubs
   - [ ] Performance tests measure real characteristics
   - [ ] Tests would fail if implementation is wrong

3. **Test Plan Review**
   - [ ] Show complete test plan before implementation
   - [ ] All test files created and reviewed
   - [ ] Test structure matches implementation plan

## 🛠️ IMPLEMENTATION WITH CONTINUOUS VALIDATION

**Always read the detailed todo entries before starting implementation. Extend from core SDK, don't create.**

### Implementation Rules

1. **Small, Verifiable Chunks**: Implement one component at a time
2. **Test After Each Component**: Do not proceed until all tests pass
3. **Continuous Validation**: Validate against requirements after each step
4. **No Shortcuts**: Follow SDK patterns exactly

### Implementation Checkpoints

For each component, you MUST complete this checklist:

**Component: [name]**
- [ ] Implementation complete in `[directory]`
- [ ] Unit tests pass (show full output)
- [ ] Integration tests pass (show full output)
- [ ] Documentation updated if needed
- [ ] No policy violations found
- [ ] Business logic preserved
- [ ] Performance requirements met

### Mandatory Validation Commands

**After EACH component, run these commands and show COMPLETE output:**

1. **Docker Infrastructure**:
   ```bash
   # Check existing containers first
   docker ps -a
   
   # Use existing test utils
   ./tests/utils/test-env up && ./tests/utils/test-env status
   ```
   
   **Docker Creation Rules**:
   - DO NOT create new docker containers before checking existing
   - Use docker-compose approach from `tests/utils/CLAUDE.md`
   - Deconflict ports by checking current usage
   - Document any new services in test infrastructure

2. **Unit Tests**:
   ```bash
   pytest tests/unit/test_[component].py -v --tb=short
   ```

3. **Integration Tests**:
   ```bash
   pytest tests/integration/test_[component].py -v --tb=short
   ```

4. **E2E Tests** (when applicable):
   ```bash
   pytest tests/e2e/test_[workflow].py -v --tb=short
   ```

### Component Validation Checklist

After each component implementation, validate:

1. **SDK Pattern Compliance**
   - [ ] Checked `src/kailash/` for similar implementations
   - [ ] Using existing base classes and interfaces
   - [ ] Following established coding conventions
   - [ ] Respecting directory structure

2. **Documentation Check**
   - [ ] Checked `sdk-users/` for similar patterns
   - [ ] Not duplicating existing functionality
   - [ ] Consistent with documented patterns
   - [ ] Updated relevant documentation

3. **Test Verification**
   - [ ] All tests actually passing (not skipped)
   - [ ] Tests verify correct functionality
   - [ ] No trivial or placeholder tests
   - [ ] Performance tests are meaningful

4. **Production Quality**
   - [ ] Proper error handling implemented
   - [ ] Logging added where appropriate
   - [ ] Edge cases handled
   - [ ] Documentation strings included

5. **Business Logic Preservation**
   - [ ] Original functionality maintained
   - [ ] Performance requirements met
   - [ ] API compatibility preserved
   - [ ] No breaking changes introduced

### Implementation Legitimacy Checks

After implementation, critique for legitimacy:

1. **Correctness**
   - Does it solve the actual problem?
   - Are all requirements met?
   - Is the business logic correct?

2. **Performance**
   - Does it meet performance targets?
   - Is caching implemented correctly?
   - Are queries optimized?

3. **Maintainability**
   - Is the code readable and documented?
   - Does it follow SDK patterns?
   - Can other developers understand it?

4. **Completeness**
   - Are all edge cases handled?
   - Is error handling comprehensive?
   - Are all tests meaningful?

## 🚫 Common Pitfalls to Avoid

1. **Writing Implementation Before Tests**
   - Always write tests first
   - Tests drive the implementation

2. **Skipping Integration Tests**
   - Never mock in Tier 2/3
   - Always use real services

3. **Trivial Tests**
   - Tests must verify behavior
   - Avoid testing syntax only

4. **Ignoring Existing Patterns**
   - Always check SDK for examples
   - Don't reinvent the wheel

5. **Proceeding with Failing Tests**
   - Fix all issues before continuing
   - Never skip or disable tests

## ✅ Definition of Done

A component is ONLY complete when:

1. All tests written and passing (all tiers)
2. Implementation follows SDK patterns
3. Documentation updated
4. Performance requirements met
5. Code reviewed for legitimacy
6. Business logic preserved
7. No breaking changes introduced

## 📊 Progress Tracking

Track each component's progress:

| Component | Tests Written | Unit Pass | Integration Pass | E2E Pass | Reviewed | Complete |
|-----------|--------------|-----------|------------------|----------|----------|----------|
| Example   | ✅           | ✅        | ✅              | ✅       | ✅       | ✅       |

**STOP SIGN**: If any column is ❌, do not proceed to next component.

---

## 🔍 MANDATORY PHASE CRITIQUE & VALIDATION

**CRITICAL**: After completing each phase, perform this mandatory critique step before proceeding.

### Phase Completion Critique Checklist

#### **1. UltraThink Analysis - What Did We Actually Accomplish?**
- [ ] List every component implemented with evidence
- [ ] Verify all acceptance criteria from phase requirements met
- [ ] Check all tests actually PASS (not skipped or mocked in integration/E2E)
- [ ] Validate business logic preservation with real examples

#### **2. Critical Gap Analysis - What's Missing?**
- [ ] **Integration Reality Check**: Do integration tests use REAL services?
- [ ] **Performance Validation**: Are performance claims measured with real data?
- [ ] **Business Continuity**: Does existing functionality still work?
- [ ] **Security & Compliance**: Are business-critical requirements satisfied?
- [ ] **Developer Experience**: Can the team actually use what was built?

#### **3. Production Readiness Assessment**
- [ ] **Error Handling**: Graceful failure modes implemented?
- [ ] **Monitoring**: Health checks and observability in place?
- [ ] **Documentation**: Usage examples and migration guides created?
- [ ] **Backward Compatibility**: Existing systems not broken?

#### **4. Workflow Integration Validation** (Kailash-Specific)
- [ ] **Actual Workflows**: Created real WorkflowBuilder examples using components?
- [ ] **Node Generation**: Verified DataFlow models generate working nodes?
- [ ] **Runtime Execution**: Tested `runtime.execute(workflow.build())` pattern?
- [ ] **SDK Compliance**: Following CLAUDE.md essential patterns exactly?

#### **5. Critique Documentation Requirements**
Create `src/shipping/phase-critiques/phase-{N}-critique.md` containing:
- **What Actually Works**: Evidence-based component validation
- **Critical Gaps**: Honest assessment of missing pieces
- **Production Risks**: Security, performance, compliance issues
- **Next Phase Blockers**: Dependencies that must be resolved

#### **6. Mandatory Validation Commands**
Run these commands and document COMPLETE output:

```bash
# Verify all tests pass with real services
./tests/utils/test-env up && ./tests/utils/test-env status
pytest tests/unit/ -v --tb=short
pytest tests/integration/ -v --tb=short --no-skip
pytest tests/e2e/ -v --tb=short --no-skip

# Validate component functionality
python -c "from your.module import component; component.validate_production_ready()"

# Performance benchmarking
python scripts/benchmark_phase_{N}.py --validate-requirements
```

#### **7. Go/No-Go Decision**
**Before proceeding to next phase:**
- [ ] All acceptance criteria met with evidence
- [ ] All tests pass against real infrastructure  
- [ ] Performance requirements validated with measurements
- [ ] No critical security or compliance gaps
- [ ] Team can actually use the implemented components

**If ANY checkbox is unchecked, DO NOT proceed to next phase.**

#### **8. Stakeholder Sign-off**
- [ ] Technical lead review of critique findings
- [ ] Business owner validation of requirements met
- [ ] Security review if applicable
- [ ] Documentation review for completeness

---

**Remember**: Quality over speed. It's better to have one component working perfectly than five components partially working.

**STOP SIGN**: If phase critique reveals critical gaps, pause implementation and address gaps before continuing.