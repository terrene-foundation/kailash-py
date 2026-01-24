# Migration Implementation Instructions

*Copy-paste this entire section to Claude Code for migration tasks*

---

You are migrating an existing system to Kailash SDK. Follow these steps exactly and show me complete outputs at each step. Do not summarize or skip any validation steps.

## 1. CONTEXT LOADING AND DEEP ANALYSIS ACTIVATION

### Essential Context Loading
Load these files before starting (DO NOT proceed until loaded):
- Root `CLAUDE.md` - Core validation rules and critical patterns
- `sdk-users/CLAUDE.md` - Implementation patterns and architectural guidance
- `README.md` - Project overview and structure
- Any existing migration documentation in `docs/migration/` or similar directories
- Current test structure and patterns in `tests/`
- System architecture documentation if available

**For implementation guidance during development, remember these key resource locations** (use MCP tools to search when needed):
- `sdk-users/3-development/` - Core implementation guides and patterns
- `sdk-users/2-core-concepts/nodes/` - Node selection and usage patterns
- `sdk-users/2-core-concepts/cheatsheet/` - Copy-paste implementation patterns
- `sdk-users/2-core-concepts/validation/common-mistakes.md` - Error database with solutions

### Framework-First Approach (MANDATORY)
Check for existing framework solutions that can replace current components (use MCP tools to search):
- `sdk-users/apps/dataflow/` - Replace custom state management
- `sdk-users/apps/nexus/` - Replace FastAPI endpoints
- Other frameworks in `sdk-users/apps/` that may replace custom code

### Critical Understanding Confirmation
After loading the essential files, you MUST confirm you understand:
- **3-tier testing strategy** (`sdk-users/3-development/testing/regression-testing-strategy.md` and `sdk-users/3-development/testing/test-organization-policy.md`)
  - **Tier 1 requirements**: Fast (<1s), isolated, can use mocks, no external dependencies, no sleep
  - **NO MOCKING policy** for Tier 2/3 tests - this is absolutely critical
  - Real Docker infrastructure requirement - never skip this for integration/E2E tests
- **Migration-specific testing**: Test against documented behavior, NOT current implementation
- **Bug fixing during migration**: Fix known bugs instead of replicating them
- **Project structure**: Understand how the current project is organized
- **Available frameworks** in `sdk-users/apps/` that can replace custom code

**Search relevant documentation as needed during implementation using MCP tools instead of loading everything upfront.**

### DEEP ANALYSIS ACTIVATION
Think deeply. Before we begin any migration, you MUST analyze thoroughly and provide specific answers to these questions:

1. **What are the most likely migration failure points for this specific component?**
   - Where might state migration break application continuity?
   - Which workflow transitions are most fragile?
   - What data/context patterns must be preserved?
   - Which business logic rules are critical?

2. **What existing SDK components should replace the current implementation?**
   - Use MCP tools to search for DataFlow patterns to replace state management
   - Use MCP tools to search for WorkflowBuilder patterns to replace LangGraph
   - Use MCP tools to search for LLMAgentNode patterns to replace custom AI logic
   - Verify there isn't already a migration pattern documented

3. **What tests will definitively prove the migration preserves correct behavior?**
   - Tests against documented behavior/requirements (not current implementation)
   - Tests for data continuity during state migration
   - Tests for workflow context preservation
   - Tests for business logic consistency

4. **What behavioral bugs should be fixed during migration?**
   - Review known bugs in project documentation
   - Identify where current implementation deviates from requirements
   - Plan fixes instead of replicating bugs

**Think deeply and be specific. Document your detailed analysis before proceeding. Do not give generic answers.**

## 2. REQUIREMENTS ANALYSIS AND PLANNING

### Systematic Behavioral Requirements Extraction
This prevents migrating bugs by understanding expected behavior from documentation.

1. **Extract functional requirements from documentation:**
   - What does the project documentation say this component should do?
   - What API contracts or interfaces must be preserved?
   - What business rules from requirements documents must be preserved?
   - What user workflows or use cases are affected?

2. **Document current implementation deviations:**
   - Where does current code differ from documented requirements?
   - What bugs are known (from bug reports or analysis)?
   - What workarounds exist that should be removed?
   - What performance issues need addressing?

3. **Identify affected users and workflows:**
   - Primary user personas and their use cases
   - Core business workflows that depend on this component
   - Integration points with other systems
   - Critical data flows

4. **Map to SDK migration patterns:**
   - State management → DataFlow models with auto-generated nodes
   - Custom workflows → WorkflowBuilder with string-based nodes
   - Custom services → SDK nodes (HTTPRequestNode, DatabaseNode, etc.)
   - Complex logic → LLMAgentNode + appropriate control nodes

**For each requirement, you MUST show me:**
- What the documented behavior should be (with source reference)
- How current implementation differs (if at all)
- What SDK components will implement correct behavior
- How to test the behavior is preserved/fixed

**Do not proceed until you have provided and documented complete behavioral analysis.**

### Migration Component Mapping (CRITICAL)
**MANDATORY**: Map current components to SDK replacements:
- Use MCP tools to identify current component structure
- Use MCP tools to find SDK replacement patterns
- Document exact mapping (Current File → SDK Pattern)
- Identify any custom logic that needs preservation

**Document and show me the complete component mapping before proceeding.**

### Migration Decision Documentation
Before migrating any code, you MUST create a migration-specific ADR (Architecture Decision Record) in your project's documentation folder. This documents the approach and ensures correct behavior preservation.

You MUST create an ADR with the following structure:

1. **Title**: ADR-XXX-migrate-component-name.md (replace XXX with next number)
2. **Context**:
   - Current implementation limitations and bugs
   - Expected behavior from documentation
   - Migration risks and challenges
   - SDK components that will replace current code

3. **Decision**:
   - Specific SDK patterns to use
   - How to preserve application continuity
   - How to maintain workflow transitions
   - Bug fixes to implement during migration

4. **Consequences**:
   - Improved maintainability with SDK patterns
   - Performance implications
   - Breaking changes (if any)
   - Rollback strategy

5. **Behavioral Validation**:
   - How to test against documented requirements
   - Critical workflows that must continue working
   - Performance benchmarks to maintain

**Show me the complete ADR file contents before proceeding with any migration. Do not write code until the ADR is approved.**

### Migration Plan
Analyze the migration thoroughly:
- What behavioral tests need to be written first? (List each one)
- What state migration utilities are needed? (Be specific)
- What compatibility layers are required? (Temporary bridges)
- What rollback mechanisms must be in place? (Safety first)

**Show me your complete migration plan before proceeding.**

## 3. MIGRATION TODO SYSTEM

Update the todo management system before starting implementation. This ensures proper tracking and prevents incomplete work.

- The todo management system is two-tiered: Repo level todos are in `todos/` and module level todos are in their respective `src/` sub-directories. You MUST:

1. **Start with updating the master list** (`000-master.md`):
   - Look through the entire file thoroughly
   - Add the new todo with clear description
   - Update the status of any related existing todos
   - Keep the file concise and easy to navigate

2. **Create detailed entry** in `todos/active/` with:
   - Clear description of what needs to be implemented
   - Specific acceptance criteria for completion
   - Dependencies on other components
   - Expected behavior from documentation
   - Known bugs to fix
   - SDK components to use
   - Validation criteria
   - Risk assessment and mitigation strategies
   - Testing requirements for each component

3. **Break down into subtasks** with clear completion criteria:
   - Each subtask should be completable in 1-2 hours
   - Each subtask should have specific verification steps
   - Each subtask should have clear success criteria
   - Each subtask should identify potential failure points
   - Write behavioral tests
   - Implement state migration
   - Replace with SDK components
   - Validate behavior preservation
   - Fix identified bugs

**Show me the todo entries you've created before proceeding with any implementation. Do not start coding until todos are properly documented.**

## 4. TEST-FIRST MIGRATION

Write tests BEFORE implementation. This prevents missing tests and ensures working code. You MUST follow the 3-tier testing strategy exactly as specified in `sdk-users/3-development/testing/regression-testing-strategy.md` and `sdk-users/3-development/testing/test-organization-policy.md`.

**Always ensure that your TDD covers all the detailed todo entries**

Do not write new tests without checking that existing ones can be modified to include them. You MUST have all 3 kinds of tests:

**Tier 1 (Unit tests):**
- For each component, we should have unit tests that cover the functionality
- Can use mocks, must be fast (<1s per test), no external dependencies, no sleep
- Location: `tests/unit/`
- Must cover all public methods, edge cases, and error conditions
- Must follow the existing test patterns in the codebase

**Tier 2 (Integration tests):**
- For each component, we should have integration tests to ensure that it works together with the system
- **NO MOCKING** - must use real Docker services
- Location: `tests/integration/`
- Must test actual component interactions with real services
- Must use the docker implementation in `tests/utils`
- Always run `./tests/utils/test-env up && ./tests/utils/test-env status` before these tests

**Tier 3 (E2E tests):**
- For each user flow, we should have user flow tests that ensure that we meet developer expectations
- **NO MOCKING** - complete scenarios with real infrastructure
- Location: `tests/e2e/`
- Must test complete user workflows from start to finish
- Must use real data, processes, and responses

**Show me the complete test plan and initial test files. Do not proceed with implementation until all test files are created and reviewed.**

## 5. MIGRATION WITH CONTINUOUS VALIDATION

**Always validate against documented requirements and detailed todos, not just current implementation.**

Migrate in small, verifiable chunks. After each component migration, validate behavior preservation.
**Do not proceed to the next component until behavior is validated.**

### Migration Checkpoints
For each component, you MUST:

**Component 1**: [Current component name → SDK replacement]
- [ ] Behavioral tests written (show test names)
- [ ] Migration implemented (show SDK components used)
- [ ] Unit tests pass (show full output)
- [ ] Integration tests pass (show full output)
- [ ] User flows preserved (show E2E test output)
- [ ] Known bugs fixed (list fixes made)

**Component 2**: [Current component name → SDK replacement]
- [ ] Behavioral tests written (show test names)
- [ ] Migration implemented (show SDK components used)
- [ ] Unit tests pass (show full output)
- [ ] Integration tests pass (show full output)
- [ ] User flows preserved (show E2E test output)
- [ ] Known bugs fixed (list fixes made)

### Mandatory Validation After Each Component
Run complete test suite in the correct order. You MUST show me the COMPLETE output - do not summarize anything.
Please follow our 3-tier testing strategy exactly as specified in `sdk-users/3-development/testing/regression-testing-strategy.md` and `sdk-users/3-development/testing/test-organization-policy.md`

1. **Tier 1 (all unit tests):**
   `pytest tests/unit/ -v`

2. **Tier 2 (all integration tests):**
   `./tests/utils/test-env up && ./tests/utils/test-env status`
   `pytest tests/integration/ -v`

3. **Tier 3 (relevant E2E tests):**
   `pytest tests/e2e/test_specific_feature.py -v`

Use our ollama to generate data or create LLMAgents freely. Always use the docker implementation in `tests/utils`, and real data, processes, responses.

If you find any existing tests with policy violations, please fix them immediately. Additional tests written MUST follow our test directives.

**Show me the COMPLETE output from each tier. Do not summarize. If any tests fail, STOP and fix before continuing.**

### Continuous Migration Validation
After each component, you MUST validate:

1. **Does it implement documented behavior?**
   - Check against requirements documents
   - Verify conversation scripts match
   - Ensure user flows work correctly
   - Confirm bugs are fixed

2. **Are SDK patterns used correctly?**
   - DataFlow for state management
   - WorkflowBuilder for workflows
   - SDK nodes for integrations
   - Proper error handling

3. **Is conversation continuity preserved?**
   - State migration works correctly
   - Context inheritance maintained
   - Priority routing preserved
   - No conversation breaks

4. **Are performance requirements met?**
   - Response times within SLAs
   - No performance regressions
   - Efficient SDK usage
   - Proper caching

5. **Can we rollback if needed?**
   - Compatibility layer works
   - Feature flags functional
   - Old code still accessible
   - Data integrity maintained

**STOP if any validation fails. Fix before continuing to the next component.**

## 6. MIGRATION COVERAGE VERIFICATION

Verify test coverage on migration completeness:
- Run test coverage analysis: `pytest --cov=src/<module> --cov-report=html --cov-report=term`
- Aim for >80% test coverage at the solution's level
- Ensure all documented behaviors are tested
- Verify bug fixes have regression tests
- Check state migration paths are covered
- Validate rollback scenarios are tested
- Ensure tests are importing the actual modules
- Ensure that tests are not over-mocked that they don't reflect reality
- Ensure that implementation and infrastructure dependencies are real and available
- Skips do not count towards coverage and ensure no tests are skipped
- Use real Docker services for integration/E2E tests
  - Must use the docker implementation in `tests/utils`
  - Always run `./tests/utils/test-env up && ./tests/utils/test-env status` before tests
- Review coverage report carefully to identify untested code paths
- Add additional tests for any uncovered critical code
- Follow the same 3-tier testing strategy for new tests
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

**Show me the coverage report focusing on migrated components.**

## 7. DOCUMENTATION VALIDATION

Validate migration documentation and examples.

For each migrated component's documentation:
1. Create temp test validating new SDK patterns work
2. Verify examples use correct SDK components
3. Ensure migration guides are accurate
4. Test rollback procedures documented

**Show me validation results for migration documentation:**
- File: [migration guide path]
- Temp test: [validation test path]
- Output: [proof new patterns work correctly]

## 8. FINAL MIGRATION VALIDATION

### Full Test Suite Execution
Run complete test suite to ensure no regressions:

1. **All behavioral tests (new):**
   `pytest tests/unit/ -v -k "behavior"`

2. **All integration tests:**
   `./tests/utils/test-env up && ./tests/utils/test-env status`
   `pytest tests/integration/ -v`

3. **All user flow tests:**
   `pytest tests/e2e/ -v`

**Show me the COMPLETE output from each tier. If any tests fail, STOP and fix.**

### Migration Completion Verification
Confirm all migration components are complete:

- [ ] Behavioral tests in `tests/` validate documented requirements
- [ ] SDK components replace custom code in project source
- [ ] State migration utilities handle data conversion
- [ ] Compatibility layers enable rollback
- [ ] Documentation updated with migration patterns
- [ ] Known bugs fixed with regression tests
- [ ] Migration ADR documents decisions
- [ ] Migration tracking updated

**Show me specific file locations confirming each component exists.**

### Final Migration Checklist
Before declaring migration complete:

- [ ] All behavioral tests pass (show output)
- [ ] User flows work identically (show E2E results)
- [ ] Performance meets requirements (show benchmarks)
- [ ] Known bugs are fixed (list fixes)
- [ ] Rollback tested (show compatibility)
- [ ] Documentation accurate (show validation)
- [ ] Migration tracking updated (show updates)
- [ ] Ready for cutover (show final validation)

**If any item is unchecked, STOP and fix it before declaring complete.**

## 9. POST-MIGRATION TASKS

### Migration Tracking Completion
Update migration tracking:

1. Update your migration tracking file:
   - Mark component as completed
   - Note any discovered issues
   - Update next priorities

2. Document completion details:
   - Include lessons learned
   - Document any gotchas
   - Note performance improvements

### Migration Documentation Update
Update migration guides:

1. Add component-specific patterns discovered
2. Document any SDK workarounds needed
3. Update behavioral requirements if refined
4. Add to migration playbook

### Final Validation
Before considering migration complete:

1. Can the migrated system handle all documented user flows?
2. Are all known bugs fixed with tests?
3. Is performance equal or better?
4. Can we rollback if critical issues found?
5. Is the code more maintainable with SDK patterns?

**If you cannot answer "yes" to all questions, continue working until you can.**

## 10. DEEP ANALYSIS CRITIQUE

Think deeply. Review this migration critically:

1. **Does the migration deliver correct behavior per documentation?**
   - Are workflows operating correctly?
   - Are outputs matching expectations?
   - Are business rules properly implemented?
   - Are known bugs actually fixed?

2. **What migration risks remain?**
   - Any application continuity issues?
   - Any data migration problems?
   - Any integration concerns?
   - Any performance regressions?

3. **Is the SDK usage optimal?**
   - Are DataFlow models used efficiently?
   - Are WorkflowBuilder patterns correct?
   - Are SDK nodes properly configured?
   - Is error handling comprehensive?

4. **What would frustrate users during cutover?**
   - Any behavior changes?
   - Any performance issues?
   - Any missing features?
   - Any data migration problems?

**Be honest about risks. Show me specific concerns with examples.**
**Record your critique in your migration documentation**

## 11. MIGRATION CUTOVER PROCEDURES

1. Create migration branch with all changes
2. Run parallel testing comparing old vs new
3. Implement gradual rollout with feature flags
4. Monitor for behavior differences
5. Have rollback plan ready

**Never do hard cutover without parallel testing period.**

## 12. Migration Success Metrics

Track these metrics during and after migration:
1. User flow success rate (must be 100%)
2. Response time comparison (must be equal or better)
3. Error rate comparison (must be equal or lower)
4. Code maintainability score (must improve)
5. Test coverage (must be >80%)

**Show me metrics before declaring migration successful.**
