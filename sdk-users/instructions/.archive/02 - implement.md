# Document before implementing
1. Record the related architectural decisions, in details in `# contrib (removed)/architecture/adr`, use multiple files if you have to.
2. The local todo management system is in `# contrib (removed)/project/todos/`.
   - Start with updating the master list (`000-master.md`)
   - Look through the entire file thoroughly and add the new todos.
3. Ensure that each todo's details are captured in `todos/active`.

# Building apps
Please follow this structured approach:
1. **Identify User Personas**: Determine all user personas who will be using this system.
2. **Map User Flows**: Define the multiple user flows that each persona will conduct.
3. **Define Enterprise Features**: Identify the enterprise-grade user features that must exist.
4. **Create Tier 3 E2E Tests**: Use the user flows from steps 1-3 to form comprehensive tier 3 end-to-end tests.
5. **Build Tier 1 & 2 Tests**: Create tier 1 (unit) and tier 2 (integration) tests derived from the components identified in your tier 3 tests.
6. **Consolidate for Dataflow Enhancement**: Eventually, all tier 3 E2E flows will be consolidated and used to improve kailash-dataflow.

**Important Guidelines:**
- Our testing strategy is in `sdk-users/testing/regression-testing-strategy.md`, and policy is in `sdk-users/testing/test-organization-policy.md`.
- As you implement these E2E tests and checks, actively reference our existing capabilities (documented in sdk-users) and architecture philosophy
- Ensure you do not deviate from established patterns
- Place all tests, user flows, and documentation for the app in the app's directory under `apps/`
- Do not modify the `src/` folder unless core SDK improvements are required.

Begin with step 1 and work systematically through each phase.
   - Ensure 100% kailash sdk compliance.
   - Do not create new code without checking it against the existing SDK components.
   - Do not assume any new functionality without verifying it against the user flow specifications.
   - If you meet any errors in the SDK, check `sdk-users/` because we may have resolved it before.

# Building the core SDK
1. Faithfully respect the kailash philosophy and architecture, then implement the best-in-class into the Kailash stack.
2. Proceed with the implementation.
   - Ensure 100% kailash sdk compliance.
   - Do not create new code without checking it against the existing SDK components.
   - Do not assume any new functionality without verifying it against the user flow specifications.
   - If you meet any errors in the SDK, check sdk-users/ because we may have resolved it before.
3. After each todo item (feature/fix), please test your implementation thoroughly.
   - Do not write new tests without checking that existing ones can be modified to include them.
   - We should have 3 kinds of tests which MUST follow the strategy in `sdk-users/testing/regression-testing-strategy.md`, and policy in `sdk-users/testing/test-organization-policy.md`:
      - **Unit tests (Tier 1)**
        - For each component, we should have unit tests that cover the functionality.
        - Can use mocks, must be fast (<1s per test), no external dependencies, no sleep.
      - **Integration tests (Tier 2)**
        - For each component, we should have integration tests to ensure that it works together with the system.
        - NO MOCKING, must use real Docker services
      - **User flow/e2e tests (Tier 3)**
        - For each user flow, we should have user flow tests that ensure that we meet developer expectations.
        - NO MOCKING, complete scenarios with real infrastructure
   - If you find any existing tests with policy violations, please fix them immediately.
4. Always use the docker implementation in `tests/utils`, and real data, processes, responses.
   - Always run `./tests/utils/test-env up && ./tests/utils/test-env status` before integration/E2E tests - NEVER use pytest directly!
   - Use our ollama to generate data or create LLMAgents freely.
   - DO NOT create new docker containers or images before checking that the docker for this repository exists.
     - If there isn't any and you need to create one, please inspect the current docker containers in this system to understand what ports and services are currently in use by other containers/images.
     - Deconflict by locking in a set of docker services and ports for this project.
     - Do not create docker containers or images manually, please use the docker-compose approach outlined in `tests/utils/CLAUDE.md`.
     - Update this setup and the CLAUDE.md in `tests/utils`. Update other references if required.
5. Do not stop until you are done with the implementation.

# Testing the kailash implementation
1. I want you to extensively test your implementation.
   - Do not write new tests without checking that existing ones can be modified to include them.
   - We should have 3 kinds of tests which MUST follow the strategy in `sdk-users/testing/regression-testing-strategy.md`, and policy in `sdk-users/testing/test-organization-policy.md`:
     - **Unit tests (Tier 1)**
        - For each component, we should have unit tests that cover the functionality.
        - Can use mocks, must be fast (<1s per test), no external dependencies, no sleep.
      - **Integration tests (Tier 2)**
        - For each component, we should have integration tests to ensure that it works together with the system.
        - NO MOCKING, must use real Docker services
      - **User flow/e2e tests (Tier 3)**
        - For each user flow, we should have user flow tests that ensure that we meet developer expectations.
        - NO MOCKING, complete scenarios with real infrastructure
   - If you find any existing tests with policy violations, please fix them immediately.
2. Always use the docker implementation in `tests/utils`, and real data, processes, responses.
   - Always run `./tests/utils/test-env up && ./tests/utils/test-env status` before integration/E2E tests - NEVER use pytest directly!
   - Use our ollama to generate data or create LLMAgents freely.
   - DO NOT create new docker containers or images before checking that the docker for this repository exists.
     - If there isn't any and you need to create one, please inspect the current docker containers in this system to understand what ports and services are currently in use by other containers/images.
     - Deconflict by locking in a set of docker services and ports for this project.
     - Do not create docker containers or images manually, please use the docker-compose approach outlined in `tests/utils/CLAUDE.md`.
     - Update this setup and the CLAUDE.md in `tests/utils`. Update other references if required.
3. Do not stop until you are done with the implementation.

# Checking tests completeness
1. Let's resolve testing issues or gaps, if any. I need it to be of the best production quality.
2. The regression testing strategy is in `sdk-users/testing/regression-testing-strategy.md`, and policy in `sdk-users/testing/test-organization-policy.md`.
3. Additional tests written MUST follow the policy in `sdk-users/testing/test-organization-policy.md`.
   - Do not write new tests without checking that existing ones can be modified to include them.
   - Ensure that the integration and e2e tests that are demanding and real-world in nature.
4. Always use the docker implementation in `tests/utils`, and real data, processes, responses.
   - Always run `./tests/utils/test-env up && ./tests/utils/test-env status` before integration/E2E tests - NEVER use pytest directly!
   - Use our ollama to generate data or create LLMAgents freely.
   - DO NOT create new docker containers or images before checking that the docker for this repository exists.
     - If there isn't any and you need to create one, please inspect the current docker containers in this system to understand what ports and services are currently in use by other containers/images.
     - Deconflict by locking in a set of docker services and ports for this project.
     - Do not create docker containers or images manually, please use the docker-compose approach outlined in `tests/utils/CLAUDE.md`.
     - Update this setup and the CLAUDE.md in `tests/utils`. Update other references if required.
5. Apply test coverage improvement process. 
    - Follow the same 3-tier testing strategy.
    - Aim for >80% test coverage.
    - Create comprehensive unit, integration, and E2E tests.
    - Use real Docker services for integration/E2E tests.
    - NO MOCKING in integration/E2E tiers. 
   
# Updating the documentation
1. Please update all documentations and references in details.
2. Look through the docs in `sdk-users/`, using the `CLAUDE.md` as the entrypoint.
   - Important directories are `developer/`, `nodes/`, and `cheatsheet/`.
   - Check existing docs (file by file) for patterns, and ensure that they are up-to-date.
   - Cross-reference the actual SDK implementation and the corresponding tests in `tests/` to understand the expected behavior, and the correct usage patterns.
     - Tests in `tests/` are written in accordance with the policies in `sdk-users/testing/regression-testing-strategy.md`, and `sdk-users/testing/test-organization-policy.md`.
     - You are not required to write new tests into the `tests/` directory.
   - Your focus is to ensure that the code and guide in the documentation are correct and up-to-date.
     - Please write temporary tests to validate the codebases, before and after your changes.
     - Do this for every file without fail.
     - Always run `./test-env up && ./test-env status` before integration/E2E tests - NEVER use pytest directly!
   - Check through the other directories to ensure that we don't have any underused or redundant information.
   - Keep `sdk-users/` lean, concise, and focused for developers and users.
3. Look through the migration docs in `sdk-users/migration-guides/`
   - Ensure that the docs are up-to-date and reflect the latest changes in the SDK.
   - Update any outdated information, and ensure that the guides are clear and concise.
   - Remove any redundant or underused migration guides.

# Updating the todo management system
1. The local todo management system is in `# contrib (removed)/project/todos/`.
2. Start with updating the master list (`000-master.md`)
   - Look through the entire file thoroughly.
   - Add outstanding todos that are not yet implemented.
   - Update the status of existing todos.
   - Remove old completed entries that don't add context to outstanding todos.
   - Keep this file concise, lean, and easy to navigate.
3. Ensure that each todo's details are captured in
   - `todos/active` for outstanding todos.
   - `todos/completed` for completed todos.
   - move completed todos from `todos/active` to `todos/completed` with the date of completion.

# Updating the guidance system
1. Check the `CLAUDE.md` in root and other directories.
   - Check if we need to update the guidance system.
   - Ensure that only the absolute essentials are included.
   - Adopt a multi-step approach by using the existing `CLAUDE.md` network (root -> sdk-users/ -> specific guides).
     - Do not try to solve everything in one place, make use of the hierarchical documentation system.
   - Issue commands instead of explanations.
   - Ensure that your commands are sharp and precise, covering only critical patterns that prevent immediate failure.
   - Run through the guidance flow yourself and ensure the following:
     - You can trace a complete path from basic patterns to advanced custom development.
     - Please maintain the concise, authoritative tone that respects context limits!
2. For the modules in `apps/`.
   - Please trace through the `CLAUDE.md` guidance system.
   - Temp test all the instructions to ensure that they are correct.
   - For each user persona and their workflows, please run through the e2e using temp tests.
   - Run through the guidance flow as a user and ensure that you can trace everything to build from basic to advanced.

# Full check on the todo entries
1. Check the `todos/` directory on all the outstanding todos.
   - Ensure that you read the detailed todos in `todos/active`.
2. Inspect the codebase for:
   - Implementation, tests, documentation (`sdk-users/`, `contrib`, `apps/`).
3. Update the todos if they are found to have been completed.

# Full tests
1. Running all tests will take very long, let's clear Tier 1, then Tier 2, before clearing Tier 3 one at a time.
   - Always run `./test-env up && ./test-env status` before integration/E2E tests - NEVER use pytest directly!
2. The regression testing strategy is in `sdk-users/testing/regression-testing-strategy.md`, and policy in `sdk-users/testing/test-organization-policy.md`.
3. Please use the docker implementation in `tests/utils`, and real data, processes, responses.
4. DO NOT create new docker containers or images before checking that the docker for this repository exists.
   - If there isn't any and you need to create one, please inspect the current docker containers in this system to understand what ports and services are currently in use by other containers/images.
   - Deconflict by locking in a set of docker services and ports for this project.
   - Do not create docker containers or images manually, please use the docker-compose approach outlined in `tests/utils/CLAUDE.md`.
   - Update this setup and the CLAUDE.md in `tests/utils`. Update other references if required.
5. Use our ollama to generate data or create LLMAgents freely.
6. For the tests, please use the docker implementation in `tests/utils`, and real data, processes, responses.
7. Additional tests written MUST follow the policy in 'sdk-users/testing/test-organization-policy.md'.
8. Do not write new tests without checking that existing ones can be modified to include them.
9. Please update the developer and user guides (inside `sdk-users/`).
   - Every time a feature is done and fully tested.
   - Ensure that wrong usages are corrected.
   - Ensure that guides are clear and concise.
10. Apply test coverage improvement process. 
    - Follow the same 3-tier testing strategy.
    - Aim for >80% test coverage.
    - Create comprehensive unit, integration, and E2E tests.
    - Use real Docker services for integration/E2E tests.
    - NO MOCKING in integration/E2E tiers. 
11. Commit after each tier of tests is cleared.

# Commit to github
1. Run locally to ensure that the github actions will pass.
2. Commit and push to github.
3. Issue PR, wait for the CI to pass. Correct errors if any, else merge the PR.

# Release versions
1. Please follow `# contrib (removed)/development/workflows/release-checklist.md`
2. Continue with release process.
3. Release to github and pypi.
