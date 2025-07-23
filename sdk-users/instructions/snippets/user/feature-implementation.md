# Feature Implementation Instructions

*Copy-paste this entire section to Claude Code for feature additions*

---
 
You are implementing a feature. Follow these steps exactly and show me complete outputs at each step. Do not summarize or skip any validation steps.

## 1. CONTEXT LOADING AND ULTRATHINK ACTIVATION

### Essential Context Loading
Load these files before starting (DO NOT proceed until loaded):
- Root `CLAUDE.md` - Core validation rules and critical patterns
- `sdk-users/CLAUDE.md` - Implementation patterns and architectural guidance
- `sdk-users/7-gold-standards/` - Core gold standards for implementation

**For implementation guidance during development, remember these key resource locations** (use MCP tools to search when needed):
- `sdk-users/3-development/` - Core implementation guides and patterns
- `sdk-users/2-core-concepts/nodes/` - Node selection and usage patterns
- `sdk-users/2-core-concepts/cheatsheet/` - Copy-paste implementation patterns
- `sdk-users/2-core-concepts/validation/common-mistakes.md` - Error database with solutions

### Framework-First Approach (MANDATORY)
Check for existing framework solutions that can accelerate implementation (use MCP tools to search):
- `sdk-users/apps/dataflow/` - Workflow-native database framework
- `sdk-users/apps/nexus/` - Multi-channel unified platform
- Other frameworks in `sdk-users/apps/` that may provide relevant components

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
- **Todo management system** two-tiered: Repo level todos are in `todos/` and module level todos are in their respective `src/` sub-directories.
- **Available solutions** in `sdk-users/apps/` that can provide ready-made solutions. Demonstrate your understanding by showing me:
  - What frameworks are available and what do they provide
  - How they can be used to accelerate implementation
  - How to implement using these frameworks
- **How to use MCP tools** to search relevant documentation when needed

**Search relevant documentation as needed during implementation using MCP tools instead of loading everything upfront.**

### ULTRATHINK CAP ACTIVATION
Put on your ultrathink cap. Before we begin any implementation, you MUST analyze deeply and provide specific answers to these questions:

1. **What are the most likely failure points for this specific task?**
   - Consider past patterns from `sdk-users/2-core-concepts/validation/common-mistakes.md`
   - Think about integration points that commonly break
   - Identify areas where tests typically fail

2. **What existing SDK components should I reuse instead of creating new code?**
   - Use MCP tools to search `src/kailash/` for existing implementations
   - Use MCP tools to search `sdk-users/` for documented patterns
   - Use MCP tools to search `sdk-users/apps/` frameworks for ready-made solutions
   - Verify there isn't already a solution in the codebase

3. **What tests will definitively prove this works in production?**
   - Unit tests for each component function
   - Integration tests with real services
   - E2E tests covering complete user flows
   - Specific test scenarios for edge cases

4. **What documentation needs updating and how will you validate it?**
   - What examples need to be tested
   - How will you verify every code example works

**Think deeply and be specific. Document your detailed analysis before proceeding. Do not give generic answers.**

## 2. REQUIREMENTS ANALYSIS AND PLANNING

### Systematic Requirements Breakdown
This prevents incomplete implementations by ensuring we understand exactly what needs to be built.

1. **List all functional requirements in detail:**
   - What specific functionality must be implemented?
   - What inputs and outputs are required?
   - What business logic must be covered?
   - What edge cases must be handled?

2. **List all non-functional requirements:**
   - Performance requirements (latency, throughput)
   - Security requirements (authentication, authorization)
   - Scalability requirements (concurrent users, data volume)
   - Reliability requirements (uptime, error handling)

3. **Identify user personas and their complete flows:**
   - Who are the users of this functionality?
   - What are their complete workflows from start to finish?
   - What are their success criteria?
   - What would frustrate them or cause them to fail?

4. **Map to existing SDK capabilities:**
   - What existing nodes can be reused?
   - What existing patterns should be followed?
   - What existing tests can be extended?
   - What existing documentation can be updated?

**For each requirement, you MUST show me:**
- What it means in concrete terms
- How to verify it works (specific tests)
- What could go wrong (failure scenarios)
- How it maps to existing SDK components

**Do not proceed until you have provided and documented complete analysis for all requirements.**

### Framework Solutions Check (CRITICAL)
**MANDATORY**: Search for existing solutions before writing any new code:
- Use MCP tools to search `sdk-users/apps/dataflow/` for database-related solutions
- Use MCP tools to search `sdk-users/apps/nexus/` for platform-related solutions
- Use MCP tools to search `sdk-users/` for similar implementations

**Document and show me what existing solutions you found and what you can reuse.**

### Architectural Decision Documentation
Before writing any code, you MUST create an ADR (Architecture Decision Record). This prevents wrong implementations by documenting the approach and reasoning.

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

### Implementation Plan
Analyze the implementation thoroughly:
- What existing components can you reuse? (Be specific with file paths)
- What new components need to be created? (List each one)
- What are the integration points? (How will components connect?)
- What could go wrong? (Identify 3 most likely failure points)

**Show me your complete implementation plan before proceeding.**

## 3. TODO SYSTEM UPDATE

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
   - Risk assessment and mitigation strategies
   - Testing requirements for each component

3. **Break down into subtasks** with clear completion criteria:
   - Each subtask should be completable in 1-2 hours
   - Each subtask should have specific verification steps
   - Each subtask should have clear success criteria
   - Each subtask should identify potential failure points

**Show me the todo entries you've created before proceeding with any implementation. Do not start coding until todos are properly documented.**

## 4. TEST-FIRST DEVELOPMENT

Write tests BEFORE implementation. This prevents missing tests and ensures working code. You MUST follow the 3-tier testing strategy exactly as specified in `sdk-users/3-development/testing/regression-testing-strategy.md` and `sdk-users/3-development/testing/test-organization-policy.md`.

**Always ensure that your TDD covers all the detailed todo entries**
z
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

## 5. IMPLEMENTATION WITH CONTINUOUS VALIDATION

**Always read the detailed todo entries before starting implementation**

Implement in small, verifiable chunks. After each component, please test your implementation thoroughly. **Do not proceed to the next component until the current one is completely working.**

### Implementation Checkpoints
For each component, you MUST:

**Component 1**: [name]
- [ ] Implementation complete in which directory
- [ ] Unit tests pass (show full output)
- [ ] Integration tests pass (show full output)
- [ ] Documentation updated if needed
- [ ] No policy violations found

**Component 2**: [name]
- [ ] Implementation complete in which directory
- [ ] Unit tests pass (show full output)
- [ ] Integration tests pass (show full output)
- [ ] Documentation updated if needed
- [ ] No policy violations found

### Mandatory Validation After Each Component
**After EACH component, you MUST run these commands and show me the COMPLETE output:**

1. **Start Docker infrastructure:**
   - Always use the docker implementation in `tests/utils`, and real data, processes, responses
   - **DO NOT create new docker containers** or images before checking that the docker for this repository exists
   - If there isn't any and you need to create one:
     - Inspect the current docker containers in this system to understand what ports and services are currently in use by other containers/images.
     - Deconflict by locking in a set of docker services and ports for this project.
     - Do not create docker containers or images manually, please use the docker-compose approach outlined in `tests/utils/CLAUDE.md`.

   `./tests/utils/test-env up && ./tests/utils/test-env status`

2. **Run unit tests:**
   `pytest tests/unit/test_component.py -v`

3. **Run integration tests:**
   `pytest tests/integration/test_component.py -v`

4. **Ensure missing components in tests are implemented:**
   - Do not simply skip or remove them.
   - Identify what capabilities do these components support
   - Write new tests to cover those capabilities
   - Ensure they follow the existing patterns and policies
   - Do not remove tests that are not implemented yet

5. **Verify component follows SDK patterns:**
   - Ensure 100% kailash SDK compliance
   - Do not create new code without checking it against existing SDK components
   - Do not assume any new functionality without verifying it against specifications
   - If you meet any errors, check `sdk-users/` because we may have resolved it before

**Show me the COMPLETE output after each component. Do not summarize. Do not proceed to the next component if any tests fail.**

### Continuous Validation Requirements
After each component, you MUST validate the following against the detailed todo entries:

1. **Does it follow existing SDK patterns?**
   - Check `sdk-users/` for similar implementations
   - Follow the established coding conventions
   - Use existing base classes and interfaces
   - Respect the established directory structure

2. **Did you check `sdk-users/` for similar implementations?**
   - Look at existing documentation patterns
   - Check for existing solutions to similar problems
   - Verify you're not duplicating existing functionality
   - Ensure consistency with documented patterns

3. **Are all tests actually passing?** (show output)
   - Run all unit tests and show complete output
   - Run all integration tests and show complete output
   - Verify no tests are being skipped or marked as xfail
   - Check that tests are actually testing the right functionality

4. **Is the code production-quality?**
   - Follow established error handling patterns
   - Include proper logging where appropriate
   - Handle edge cases and error conditions
   - Include proper documentation strings

5. **Did you verify that our tests are not trivial?**
   - Ensure tests actually verify intended functionality
   - Cover edge cases and error conditions
   - Avoid redundant or trivial tests that do not add value
   - Ensure tests are meaningful and cover actual behavior
   - Avoid tests that only check for syntax or trivial conditions
   - Ensure tests are not just placeholders or empty stubs
   - Ensure tests are not just checking for presence of code or artifact without verifying actual functionality
   - Ensure that performance tests are meaningful and cover actual performance characteristics

**STOP if any answer is no. Fix before continuing to the next component.**

## 6. TEST COVERAGE VERIFICATION

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

## 7. DOCUMENTATION VALIDATION

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

## 8. FINAL COMPREHENSIVE VALIDATION

### Full Test Suite Execution
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

### Component Completion Verification
For the features you have implemented, confirm you have created ALL required components:

- [ ] Core implementation in `src/kailash/`
- [ ] Unit tests in `tests/unit/`
- [ ] Integration tests in `tests/integration/`
- [ ] E2E tests in `tests/e2e/`
- [ ] Documentation in `sdk-users/`
- [ ] Migration guide if this is a breaking change
- [ ] ADR in `adr/`
- [ ] Todo entries updated in `todos/`

**Show me the specific file locations and confirm each file exists with proper content. Do not claim completion until every component is verified.**

### Final Completion Checklist
Before declaring this implementation complete, you MUST verify every item on this checklist:

- [ ] All tests pass (show complete output for all tiers)
- [ ] Documentation validated (show temp test results for each file)
- [ ] Todo items updated to completed (show the updated todo files)
- [ ] No policy violations found (confirmed by reviewing policy documents)
- [ ] Critique (`docs/critiques`) addressed (show specific fixes made)
- [ ] Component completion verified (show file locations for each component)
- [ ] Ready for PR (show git status and final test results)

**If any item is unchecked, STOP and fix it before declaring complete. Do not proceed until EVERY item is verified.**

### Final Validation
Before considering this implementation complete, put on your ultrathink cap and run through this final validation:

1. Can another developer understand and maintain this code?
2. Are all edge cases and error conditions handled?
3. Do all tests actually verify the intended functionality?
4. Is the documentation accurate and complete?
5. Does this follow all established SDK patterns?

**If you cannot answer "yes" to all questions, continue working until you can.**

**Do not declare the feature complete until all validation steps pass and you've shown me the complete outputs for every step.**

## 9. POST-IMPLEMENTATION TASKS

### Todo System Completion Update
After completing the implementation, update the todo management system:

1. The local todo management system is in `/todos/`.
2. Start with updating the master list (`000-master.md`):
   - Look through the entire file thoroughly
   - Update the status of completed todos
   - Remove old completed entries that don't add context to outstanding todos
   - Keep this file concise, lean, and easy to navigatea
3. Ensure that each todo's details are captured in:
   - `todos/active` for outstanding todos
   - `todos/completed` for completed todos
   - Move completed todos from `todos/active` to `todos/completed` with the date of completion

## Guidance system update
Check the `CLAUDE.md` in root and other directories:

1. Check if we need to update the guidance system
   - Ensure that only the absolute essentials are included
   - Adopt a multi-step approach by using the existing `CLAUDE.md` network (root -> sdk-users/ -> specific guides)
   - Do not try to solve everything in one place, make use of the hierarchical documentation system
   - Issue commands instead of explanations
   - Ensure that your commands are sharp and precise, covering only critical patterns that prevent immediate failure
   - Run through the guidance flow yourself and ensure the following:
     - You can trace a complete path from basic patterns to advanced custom development
     - Please maintain the concise, authoritative tone that respects context limits!

2. For modules in `apps/`:
   - Please trace through the `CLAUDE.md` guidance system
   - Temp test all the instructions to ensure that they are correct
   - For each user persona and their workflows, please run through the e2e using temp tests
   - Run through the guidance flow as a user and ensure that you can trace everything to build from basic to advanced

## 10. ULTRATHINK CAP CRITIQUE

Put on your ultrathink cap again. Starting fresh, critique this implementation.
- Read adr, guidance, and documentations thoroughly.
- Check the detailed todo entries in `todos/`.
- Make sure you understand the intent and purpose of this project.
- Read your past critiques in the core or apps `docs/critiques` accordingly.

Then, review this project without any prejudice:

1. **Is the codebase delivering the solution's intents, purposes, and user objectives**
   - Does it meet the functional requirements?
   - Does it meet user expectations?
   - Does it follow the architectural decisions made in the ADR?
   - Does it integrate well with existing components?

2. **What looks wrong or incomplete?**
   - Are there missing error handlers?
   - Are there untested code paths?
   - Are there performance bottlenecks?
   - Are there security vulnerabilities?

3. **What tests are missing or inadequate?**
   - Are all edge cases covered?
   - Are error conditions properly tested?
   - Are integration points thoroughly tested?
   - Are performance characteristics verified?

4. **What documentation is unclear or missing?**
   - Are usage examples clear and complete?
   - Are parameters and return values documented?
   - Are error conditions explained?
   - Are integration requirements clear?

5. **What would frustrate a user trying to use this?**
   - Are error messages helpful?
   - Are setup requirements clear?
   - Are examples runnable?
   - Are common mistakes addressed?

**Be honest, fair, and transparent. Find real problems. Show me specific issues with code examples.**
**Record your critique in the core or apps `docs/critiques` accordingly`**

## 11. GIT and RELEASE PROCEDURES
**Important**
1. Never use git reset --hard or git reset --soft.
2. Always check all local changes (from all sessions) and add/stage all modified and untracked files.
3. Before any potentially destructive git operations, check if there are any uncommitted changes. If there are, stash or commit them first.

**Commit to github**
1. Run locally to ensure that the github actions will pass.
2. Commit and push to github.
3. Issue PR, wait for the CI to pass. Correct errors if any, else merge the PR.

**Release versions**
2. Continue with release process.
3. Release to github and pypi.
