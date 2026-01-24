# Kailash SDK Migration Directives

## 📋 Migration Process Overview

This guide provides strict directives for implementing the Kailash SDK migration using Test-Driven Development (TDD) and continuous validation.

## Essential Context Loading
Load these files before starting (DO NOT proceed until loaded):
- Root `CLAUDE.md` - Core validation rules and critical patterns
- `sdk-users/CLAUDE.md` - Implementation patterns and architectural guidance
- `sdk-users/7-gold-standards/` - Core gold standards for implementation
- `# contrib (removed)/project/todos/000-master.md` - Current project state and priorities

**For implementation guidance during development, remember these key resource locations** (use MCP tools to search when needed):
- `sdk-users/3-development/` - Core implementation guides and patterns
- `sdk-users/2-core-concepts/nodes/` - Node selection and usage patterns
- `sdk-users/2-core-concepts/cheatsheet/` - Copy-paste implementation patterns
- `sdk-users/2-core-concepts/validation/common-mistakes.md` - Error database with solutions

### Framework-First Approach (MANDATORY)
Check for existing framework solutions that can accelerate implementation (use MCP tools to search):
- `apps/kailash-dataflow/` - Workflow-native database framework
- `apps/kailash-mcp/` - Zero-configuration MCP framework
- `apps/kailash-nexus/` - Multi-channel unified platform
- Other frameworks in `apps/` that may provide relevant components

### Critical Understanding Confirmation
After loading the essential files, you MUST demonstrate your understanding of the following:
- **Gold standards** in `sdk-users/7-gold-standards/`
  - Absolute Imports
  - Custom Node Development
  - Parameter Passing
  - Test Creation
- **kailash-nexus** in `sdk-users/apps/nexus.`
- **kailash-dataflow** in `sdk-users/apps/dataflow.`
- **3-tier testing strategy** (`sdk-users/3-development/testing/regression-testing-strategy.md` and `sdk-users/3-development/testing/test-organization-policy.md`)
  - **Tier 1 requirements**: Fast (<1s), isolated, can use mocks, no external dependencies, no sleep
  - **NO MOCKING policy** for Tier 2/3 tests - this is absolutely critical
  - Real Docker infrastructure requirement - never skip this for integration/E2E tests
- **Todo management system** structure in `# contrib (removed)/project/todos/`
- **Available solutions** in `apps/` that can provide ready-made solutions. Demonstrate your understanding by showing me:
  - What frameworks are available and what do they provide
  - How they can be used to accelerate implementation
  - How to implement using these frameworks
- **How to use MCP tools** to search relevant documentation when needed

**Search relevant documentation as needed during implementation using MCP tools instead of loading everything upfront.**

## Document-First Migration Strategy

### Migration Documentation Structure

**IMPORTANT**: Use the two-document approach for comprehensive migration:

1. **Systematic Patterns**: [WORKFLOW_MIGRATION_PATTERNS.md](WORKFLOW_MIGRATION_PATTERNS.md)
   - Gateway patterns
   - Data model and infrastructure patterns
   - Framework translation guide
   - Standard configuration templates
   - Error handling and recovery patterns
   - Data validation schemas
   - Testing strategy framework
   - Monitoring and alerting patterns
   - Operational readiness checklists

2. **Workflow-Specific Analysis**:
   - Workflow-specific business logic
   - Workflow-specific configuration parameters
   - Workflow-specific testing scenarios
   - Workflow-specific monitoring metrics
   - Workflow-specific error scenarios

### For Complex Workflow Migrations (RECOMMENDED)

When migrating workflows with intricate business logic, use this document-first approach:

1. **Create Comprehensive Original Analysis**
   - Trace backwards from main.py or views.py to ensure all logic captured
   - **Reference systematic patterns**: Use [WORKFLOW_MIGRATION_PATTERNS.md](WORKFLOW_MIGRATION_PATTERNS.md) for framework concerns
   - **Focus on workflow specifics**: Capture workflow-unique business logic, configurations, edge cases
   - Ensure that there are no gaps and we have all the information and connectivity to recreate the migrated workflows with 100% replicability
   - Document EVERY workflow-specific business logic in detail
   - Capture all API calls with exact parameters
   - Map all state transitions and context updates
   - Document workflow-specific edge cases and error handling
   - Include workflow-specific performance requirements
   - Include trigger conditions and integration points
   - Include model method signatures unique to this workflow
   - Include specific error response formats
   - Other workflow-specific implementation details

2. **Self-Critique the Analysis from Multiple Perspectives**
   - **Migration Engineer**: Can this be implemented in Kailash SDK?
   - **Testing Engineer**: Are all edge cases testable?
   - **Operations Engineer**: Can this be monitored and maintained?
   - **Business Analyst**: Are business rules clear and complete?
   - Review for 100% completeness using systematic patterns as baseline
   - Identify workflow-specific gaps not covered by patterns
   - Validate business rule capture against original requirements

3. **Validate Content Separation (Critical)**
   - **Systematic Content Check**: Does anything in workflow doc apply to other workflows?
   - **Missing Patterns Check**: Are there systematic patterns not captured in patterns doc?
   - **Business Context Check**: Does workflow doc explain WHY not just WHAT?
   - **Performance Baseline Check**: Are actual measurements included?
   - **Integration Flow Check**: Are state transitions clearly documented?

4. **Use Combined Documentation to Guide Migration**
   - Use systematic patterns for framework translation
   - Use workflow analysis for specific business logic
   - Implement based on documented logic
   - Preserve all critical business rules
   - Maintain performance optimizations
   - Keep analysis files for validation

### Content Separation Quality Gates

Before proceeding with migration, validate content separation:

#### Must-Pass Criteria ✅
- [ ] **No Systematic Patterns in Workflow Doc**: Everything in workflow doc is workflow-unique
- [ ] **Complete Business Justification**: All workflow rules have WHY explanations
- [ ] **Performance Baselines**: Actual measurements from original implementation
- [ ] **State Transition Flows**: Clear diagrams for integration scenarios
- [ ] **Configuration Separation**: Only workflow-specific config in workflow doc

### Four-Pass Critique Strategy (MANDATORY)

Perform 4 deep analysis critique passes to ensure migration completeness:
In each pass, please:
- Document all business logic, API calls, state transitions
- Identify gaps in requirements, performance, security, integration
- Validate from migration, testing, operations, and business perspectives
- Ensure systematic vs workflow-specific content is properly separated

## Architectural Decision Documentation
Before writing any code, you MUST create an ADR (Architecture Decision Record) in `# contrib (removed)/architecture/adr/`. This prevents wrong implementations by documenting the approach and reasoning.

You MUST create an ADR with the following structure:

1. **Title**: ADR-XXX-feature-name.md (replace XXX with next number)
2. **Context**:
   - Why is this change needed?
   - What problem does it solve?
   - What are the current limitations?
   - What are the business requirements?

3. **Decision**:
   - What specific approach will be taken?
   - What technologies/patterns will be used?
   - How does it integrate with existing SDK?
   - What are the implementation details?

4. **Consequences**:
   - What are the positive impacts?
   - What are the negative impacts?
   - What are the risks?
   - How will this affect other components?

5. **Alternatives**:
   - What other approaches were considered?
   - Why were they rejected?
   - What are the trade-offs?

**Show me the complete ADR file contents before proceeding with any implementation. Do not write code until the ADR is approved.**

## Implementation Plan
Analyze the implementation thoroughly:
- What existing components can you reuse? (Be specific with file paths)
- What new components need to be created? (List each one)
- What are the integration points? (How will components connect?)
- What could go wrong? (Identify 3 most likely failure points)

**Show me your complete implementation plan before proceeding.**

## TODO SYSTEM UPDATE

Update the todo management system before starting implementation. This ensures proper tracking and prevents incomplete work.

The local todo management system is in `# contrib (removed)/project/todos/`. You MUST:

1. **Start with updating the master list** (`000-master.md`):
   - Look through the entire file thoroughly
   - Add the new todo with clear description
   - Update the status of any related existing todos
   - Keep the file concise and easy to navigate

2. **Create detailed entry** in `todos/active/` with:
   - Clear description of what needs to be implemented
   - Specific acceptance criteria for completion
   - Dependencies on other components
   - Risk assessment and mitigation strategies
   - Testing requirements for each component

3. **Break down into subtasks** with clear completion criteria:
   - Each subtask should be completable in 1-2 hours
   - Each subtask should have specific verification steps
   - Each subtask should have clear success criteria
   - Each subtask should identify potential failure points

**Show me the todo entries you've created before proceeding with any implementation. Do not start coding until todos are properly documented.**

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

## TEST COVERAGE VERIFICATION

Verify test coverage:
- Run test coverage analysis: `pytest --cov=src/kailash --cov-report=html --cov-report=term`
- Aim for >80% test coverage at the solution's level
- Ensure tests are importing the actual modules
- Ensure that tests are not over-mocked that they don't reflect reality
- Ensure that implementation and infrastructure dependencies are real and available
- Skips do not count towards coverage and ensure no tests are skipped
- Use real Docker services for integration/E2E tests
  - Must use the docker implementation in `tests/utils`
  - Always run `./tests/utils/test-env up && ./tests/utils/test-env status` before tests
- Review coverage report carefully to identify untested code paths
- Add additional tests for any uncovered critical code
- Follow the same 3-tier testing strategy for new testsplea
- **NO MOCKING** in integration/E2E tiers
- If tests contain capabilities and components are missing
  - Do not simply skip or remove them because we follow TDD and will write tests first before implementation.
  - The tests covers capabilities that we must have, thus if tests are missing capabilities or functionality:
    - Identify the missing capabilities
    - Write new tests to cover those capabilities
    - Ensure they follow the existing patterns and policies
    - Do not remove tests that are not implemented yet

Ensure that no tests are trivial:
- Ensure tests actually verify intended functionality
- Cover edge cases and error conditions
- Avoid redundant or trivial tests that do not add value
- Ensure tests are meaningful and cover actual behavior
- Avoid tests that only check for syntax or trivial conditions
- Ensure tests are not just placeholders or empty stubs
- Ensure tests are not just checking for presence of code or artifact without verifying actual functionality
- Ensure that performance tests are meaningful and cover actual performance characteristics

**Show me the coverage report and address any gaps before proceeding.**

## DOCUMENTATION VALIDATION

Validate ALL documentation updates. For each doc file you've changed, you MUST create temporary tests to verify every code example actually works.

For each doc file changed:
1. Create a temp test file (e.g., `/tmp/test_docs_feature.py`)
2. Copy-paste every code example from the documentation
3. Add necessary imports and setup code
4. Run it with real Docker infrastructure
5. Confirm it works exactly as documented

You MUST show me the validation results for each file:
- **File**: [path to documentation file]
- **Temp test**: [path to temp test file]
- **Command**: [command used to run the test]
- **Output**: [full output proving it works]

Always run `./tests/utils/test-env up && ./tests/utils/test-env status` before running documentation tests. Use real services, not mocks.

Cross-reference the actual SDK implementation and the corresponding tests in `tests/` to understand the expected behavior and correct usage patterns. Tests in `tests/` are written in accordance with the policies in `sdk-users/3-development/testing/regression-testing-strategy.md` and `sdk-users/3-development/testing/test-organization-policy.md`.

**Show me validation results for each file:**
- File: [path to documentation file]
- Temp test: [path to temp test file]
- Output: [full output proving it works]

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

#### **1. Deep Analysis - What Did We Actually Accomplish?**
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
Create critiques documentation containing:
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

---

**Remember**: Quality over speed. It's better to have one component working perfectly than five components partially working.

**STOP SIGN**: If phase critique reveals critical gaps, pause implementation and address gaps before continuing.
