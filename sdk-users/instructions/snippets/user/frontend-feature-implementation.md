# Frontend Feature Implementation Instructions

*Copy-paste this entire section to Claude Code for frontend feature development*

---

You are implementing a frontend feature. Follow these steps exactly and show me complete outputs at each step. Do not summarize or skip any validation steps.

## 1. CONTEXT LOADING AND ULTRATHINK ACTIVATION

### Essential Context Loading
Load these files before starting (DO NOT proceed until loaded):
- Root `CLAUDE.md` - Core validation rules and critical patterns
- `frontend/CLAUDE.md` - Frontend-specific patterns and architectural guidance  
- `frontend/package.json` - Dependencies, scripts, and project configuration
- `todos/000-master.md` - Current project state and priorities

**For frontend implementation guidance during development, remember these key resource locations** (use tools to search when needed):
- `frontend/src/elements/` - Existing React components and patterns
- `frontend/src/hooks/` - Custom React hooks for state management and API calls
- `frontend/src/services/` - API integration and external service patterns
- `frontend/tailwind.config.js` - Styling system configuration and design tokens
- `frontend/webpack.config.js` - Build system and development server configuration

### Framework-First Approach (MANDATORY)
Check for existing frontend solutions that can accelerate implementation:
- **Component Library**: Search `frontend/src/elements/` for reusable components
- **Design System**: Check `frontend/src/index.css` for existing Tailwind patterns
- **State Management**: Review `frontend/src/hooks/useApi.js` for data fetching patterns
- **API Integration**: Examine `frontend/src/services/api.js` for backend communication
- **Chart Libraries**: Look for existing Chart.js/visualization components
- **UI Patterns**: Search for similar user interface patterns in existing components

### Critical Understanding Confirmation
After loading the essential files, you MUST confirm you understand:
- **Component Architecture**: React functional components with hooks, component composition patterns
- **State Management**: Local state with useState, global state with React Query, WebSocket integration
- **Styling System**: Tailwind CSS utility classes, responsive design patterns, design tokens
- **API Integration**: React Query for data fetching, error handling, loading states, real-time updates
- **Testing Strategy**: Jest for unit tests, Testing Library for component tests, E2E testing with real browsers
- **Build System**: Webpack development server, production builds, asset optimization
- **User Experience**: Accessibility, responsive design, loading states, error boundaries

**Search relevant documentation and existing code as needed during implementation using tools instead of loading everything upfront.**

### ULTRATHINK CAP ACTIVATION
Put on your ultrathink cap. Before we begin any implementation, you MUST analyze deeply and provide specific answers to these questions:

1. **What are the most likely failure points for this specific frontend task?**
   - Consider common React pitfalls (state updates, useEffect dependencies, memory leaks)
   - Think about API integration issues (loading states, error handling, data synchronization)
   - Identify responsive design breakpoints and cross-browser compatibility issues
   - Consider accessibility violations and keyboard navigation problems
   - Think about performance issues (bundle size, rendering performance, image optimization)

2. **What existing frontend components should I reuse instead of creating new ones?**
   - Search `frontend/src/elements/` for similar UI patterns
   - Check for existing hooks in `frontend/src/hooks/` that handle similar functionality
   - Look for existing API patterns in `frontend/src/services/`
   - Verify Tailwind utility classes are used consistently with existing design system
   - Ensure chart/visualization components follow established patterns

3. **What tests will definitively prove this frontend feature works for users?**
   - Unit tests for component logic and edge cases
   - Integration tests for API data flow and state management
   - Visual regression tests for UI consistency across browsers/devices
   - Accessibility tests for keyboard navigation and screen readers
   - Performance tests for bundle size and rendering speed
   - User experience tests for complete workflows

4. **What documentation needs updating and how will you validate it?**
   - Component documentation with props, usage examples, and accessibility notes
   - API integration examples that work with real data
   - Design system documentation for new patterns or tokens
   - User workflow documentation for new features

**Think deeply and be specific. Document your detailed analysis before proceeding. Do not give generic answers.**

## 2. REQUIREMENTS ANALYSIS AND PLANNING

### Systematic Requirements Breakdown
This prevents incomplete implementations by ensuring we understand exactly what needs to be built.

1. **List all functional requirements in detail:**
   - What specific user interactions must be supported?
   - What data must be displayed and how should it be formatted?
   - What user workflows must be completed from start to finish?
   - What edge cases must be handled (empty states, error states, loading states)?
   - What browser compatibility requirements must be met?

2. **List all non-functional requirements:**
   - Performance requirements (page load time, bundle size, rendering performance)
   - Accessibility requirements (WCAG compliance, keyboard navigation, screen readers)
   - Responsive design requirements (mobile, tablet, desktop breakpoints)
   - Cross-browser requirements (Chrome, Firefox, Safari, Edge versions)
   - SEO requirements (meta tags, semantic HTML, structured data)

3. **Identify user personas and their complete flows:**
   - Who are the users of this frontend feature?
   - What are their complete workflows from landing to task completion?
   - What are their success criteria and frustration points?
   - What devices and browsers do they typically use?
   - What accessibility needs do they have?

4. **Map to existing frontend capabilities:**
   - What existing React components can be reused or extended?
   - What existing hooks handle similar state management?
   - What existing API patterns should be followed?
   - What existing design patterns should be maintained?

**For each requirement, you MUST show me:**
- What it means in concrete terms for the user experience
- How to verify it works (specific test scenarios)
- What could go wrong (failure scenarios and edge cases)
- How it maps to existing frontend patterns

**Do not proceed until you have provided and documented complete analysis for all requirements.**

### Frontend Solutions Check (CRITICAL)
**MANDATORY**: Search for existing solutions before writing any new code:
- Search `frontend/src/elements/` for similar React components
- Search `frontend/src/hooks/` for similar state management patterns
- Search `frontend/src/services/` for similar API integration patterns
- Search existing component libraries (Chart.js, Lucide React, etc.) for UI patterns
- Check `frontend/src/index.css` for existing Tailwind utility patterns

**Document and show me what existing solutions you found and what you can reuse.**

### Architectural Decision Documentation
Before writing any code, you MUST create an ADR (Architecture Decision Record) in `adr/`. This prevents wrong implementations by documenting the approach and reasoning.

You MUST create an ADR with the following structure:

1. **Title**: ADR-XXX-frontend-feature-name.md (replace XXX with next number)
2. **Context**:
   - Why is this frontend change needed?
   - What user problem does it solve?
   - What are the current UI/UX limitations?
   - What are the business requirements?

3. **Decision**:
   - What specific frontend approach will be taken?
   - What React patterns/technologies will be used?
   - How does it integrate with existing component architecture?
   - What are the implementation details?

4. **Consequences**:
   - What are the positive user experience impacts?
   - What are the negative impacts (bundle size, complexity)?
   - What are the risks (browser compatibility, performance)?
   - How will this affect other frontend components?

5. **Alternatives**:
   - What other frontend approaches were considered?
   - Why were they rejected?
   - What are the trade-offs?

**Show me the complete ADR file contents before proceeding with any implementation. Do not write code until the ADR is approved.**

### Implementation Plan
Analyze the frontend implementation thoroughly:
- What existing components can you reuse? (Be specific with file paths)
- What new components need to be created? (List each one with purpose)
- What are the data flow patterns? (How will state flow between components?)
- What are the styling requirements? (New Tailwind classes, responsive breakpoints)
- What could go wrong? (Identify 3 most likely frontend failure points)

**Show me your complete frontend implementation plan before proceeding.**

## 3. TODO SYSTEM UPDATE

Update the todo management system before starting implementation. This ensures proper tracking and prevents incomplete work.

- The todo management system is two-tiered: Repo level todos are in `todos/` and module level todos are in their respective `src/` sub-directories. You MUST:

1. **Start with updating the master list** (`000-master.md`):
   - Look through the entire file thoroughly
   - Add the new frontend todo with clear description
   - Update the status of any related existing todos
   - Keep the file concise and easy to navigate

2. **Create detailed entry** in `todos/active/` with:
   - Clear description of what frontend functionality needs to be implemented
   - Specific user experience acceptance criteria for completion
   - Dependencies on other components (backend APIs, design assets)
   - Risk assessment and mitigation strategies for frontend issues
   - Testing requirements for each component (unit, integration, visual)

3. **Break down into frontend subtasks** with clear completion criteria:
   - Each subtask should be completable in 1-2 hours
   - Each subtask should have specific UI/UX verification steps
   - Each subtask should have clear success criteria for user experience
   - Each subtask should identify potential frontend failure points

**Show me the todo entries you've created before proceeding with any implementation. Do not start coding until todos are properly documented.**

## 4. TEST-FIRST DEVELOPMENT (FRONTEND-ADAPTED)

Write tests BEFORE implementation. This prevents missing tests and ensures working frontend code. You MUST follow the 3-tier testing strategy adapted for frontend development:

**Always ensure that your TDD covers all the detailed todo entries**

Do not write new tests without checking that existing ones can be modified to include them. You MUST have all 3 kinds of tests:

**Tier 1 (Unit/Component tests):**
- For each component, we should have unit tests that cover the functionality
- Use React Testing Library, can use mocks for API calls, must be fast (<1s per test)
- Location: `frontend/src/__tests__/` or co-located `ComponentName.test.jsx`
- Must cover all component props, state changes, event handlers, and edge cases
- Must test accessibility features and error boundaries
- Must follow existing test patterns in the codebase

**Tier 2 (Integration tests):**
- For each feature, we should have integration tests with real API data
- **NO MOCKING** of backend APIs - must use real running backend
- Location: `frontend/src/__tests__/integration/`
- Must test complete data flows from API to UI
- Must test user interactions with real data
- Must test error states with real error responses
- Always ensure backend is running before these tests

**Tier 3 (E2E/Visual tests):**
- For each user flow, we should have browser-based tests
- **NO MOCKING** - complete scenarios in real browsers with real infrastructure
- Location: `frontend/e2e/` or `tests/e2e/frontend/`
- Must test complete user workflows from start to finish
- Must test across different browsers and device sizes
- Must test accessibility features with real assistive technologies
- Must test visual consistency and responsive behavior

**Show me the complete frontend test plan and initial test files. Do not proceed with implementation until all test files are created and reviewed.**

## 5. IMPLEMENTATION WITH CONTINUOUS VALIDATION

**Always read the detailed todo entries before starting implementation. Extend from existing components, don't create from scratch.**

Implement in small, verifiable chunks. After each component, please test your implementation thoroughly.
**Do not proceed to the next component until the current one is completely working for users.**

### Implementation Checkpoints
For each frontend component, you MUST:

**Component 1**: [ComponentName.jsx]
- [ ] Component implementation complete in `frontend/src/elements/`
- [ ] Props interface documented with TypeScript or PropTypes
- [ ] Responsive design tested at mobile/tablet/desktop breakpoints
- [ ] Accessibility features implemented (ARIA labels, keyboard navigation)
- [ ] Unit tests pass (show full output)
- [ ] Visual consistency verified with existing design system
- [ ] No console errors or warnings in browser dev tools

**Component 2**: [ComponentName.jsx]
- [ ] Component implementation complete in `frontend/src/elements/`
- [ ] Props interface documented with TypeScript or PropTypes
- [ ] Responsive design tested at mobile/tablet/desktop breakpoints
- [ ] Accessibility features implemented (ARIA labels, keyboard navigation)
- [ ] Unit tests pass (show full output)
- [ ] Visual consistency verified with existing design system
- [ ] No console errors or warnings in browser dev tools

### Mandatory Validation After Each Component
**After EACH frontend component, you MUST run these commands and show me the COMPLETE output:**

1. **Start development servers:**
   - Backend API: `cd src/logistics_intelligence/api && python main_no_auth.py`
   - Frontend dev server: `cd frontend && npm start`
   - Verify both are accessible: `curl http://localhost:8000/api/health && curl http://localhost:9002`

2. **Run component tests:**
   `cd frontend && npm test -- --testPathPattern=ComponentName.test.jsx --verbose`

3. **Run integration tests:**
   `cd frontend && npm test -- --testPathPattern=integration --verbose`

4. **Visual validation in browser:**
   - Open http://localhost:9002 in Chrome, Firefox, Safari
   - Test responsive design at mobile (375px), tablet (768px), desktop (1024px) breakpoints
   - Test keyboard navigation through all interactive elements
   - Verify screen reader accessibility with browser dev tools
   - Check browser console for errors or warnings

5. **Performance validation:**
   - Run Lighthouse performance audit
   - Check bundle size with webpack-bundle-analyzer
   - Verify no memory leaks with React Developer Tools Profiler

**Show me the COMPLETE output after each component. Do not summarize. Do not proceed to the next component if any tests fail or if there are console errors.**

### Continuous Validation Requirements
After each component, you MUST validate the following against the detailed todo entries:

1. **Does it follow existing React patterns?**
   - Check `frontend/src/elements/` for similar component implementations
   - Follow established component composition patterns
   - Use existing hooks and state management patterns
   - Respect the established directory structure

2. **Did you check existing frontend code for similar implementations?**
   - Look at existing component patterns
   - Check for existing design system usage
   - Verify you're not duplicating existing functionality
   - Ensure consistency with documented patterns

3. **Are all tests actually passing?** (show output)
   - Run all component tests and show complete output
   - Run all integration tests and show complete output
   - Verify no tests are being skipped or marked as failing
   - Check that tests are actually testing the right functionality

4. **Is the code production-quality for users?**
   - Follow established error handling patterns (error boundaries, fallback UI)
   - Include proper loading states and skeleton screens
   - Handle edge cases (empty states, slow networks, errors)
   - Include proper accessibility attributes and semantic HTML

5. **Did you verify that our tests are not trivial?**
   - Ensure tests actually verify intended user interactions
   - Cover edge cases and error conditions users might encounter
   - Avoid tests that only check for component rendering without user value
   - Ensure tests are meaningful and cover actual user behavior
   - Test accessibility features and keyboard navigation
   - Test responsive behavior across device sizes

**STOP if any answer is no. Fix before continuing to the next component.**

## 6. TEST COVERAGE VERIFICATION (FRONTEND)

Verify frontend test coverage:
- Run test coverage analysis: `cd frontend && npm test -- --coverage --watchAll=false`
- Aim for >80% test coverage for component logic
- Ensure tests are importing and testing actual component behavior
- Ensure integration tests use real backend data, not excessive mocks
- Ensure visual/E2E tests use real browsers and user interactions
- Use real development servers for integration/E2E tests
- Review coverage report carefully to identify untested code paths
- Add additional tests for any uncovered critical user interactions
- Follow the same 3-tier testing strategy for new tests
- **NO MOCKING** in integration/E2E tiers

Ensure that no tests are trivial:
- Ensure tests actually verify intended user functionality
- Cover edge cases and error conditions users might encounter
- Avoid redundant tests that don't add user value
- Ensure tests are meaningful and cover actual user behavior
- Avoid tests that only check for component existence without interactions
- Ensure accessibility tests actually verify usability with assistive technologies
- Ensure responsive tests actually verify layout at different screen sizes

**Show me the coverage report and address any gaps before proceeding.**

## 7. DOCUMENTATION VALIDATION (FRONTEND)

Validate ALL frontend documentation updates.

**Important frontend implementation guidance docs**:
- `frontend/CLAUDE.md` - Frontend setup and troubleshooting guide
- `frontend/README.md` - Project overview and getting started
- Component documentation within component files
- API integration documentation in `frontend/src/services/`

For each documentation file you've changed, you MUST create temporary tests to verify every code example actually works.
1. Create a temp test file (e.g., `/tmp/test_frontend_docs.jsx`)
2. Copy-paste every code example from the documentation
3. Add necessary imports and setup code
4. Run it with real development servers (both frontend and backend)
5. Confirm it works exactly as documented in a real browser

You MUST show me the validation results for each file:
- **File**: [path to documentation file]
- **Temp test**: [path to temp test file]
- **Command**: [command used to run the test]
- **Output**: [full output proving it works]
- **Browser verification**: [screenshot or description of working feature]

Always ensure both development servers are running before testing documentation examples. Use real servers, not mocks.

**Show me validation results for each file:**
- File: [path to documentation file]
- Temp test: [path to temp test file]
- Output: [full output proving it works]
- Browser result: [verification that it works for users]

## 8. FINAL COMPREHENSIVE VALIDATION (FRONTEND)

### Full Test Suite Execution
Run complete frontend test suite in the correct order. You MUST show me the COMPLETE output - do not summarize anything.

1. **Tier 1 (all unit/component tests):**
   `cd frontend && npm test -- --watchAll=false --verbose`

2. **Tier 2 (all integration tests with real backend):**
   - Start backend: `cd src/logistics_intelligence/api && python main_no_auth.py`
   - Start frontend: `cd frontend && npm start`
   - Run integration tests: `npm test -- --testPathPattern=integration --watchAll=false --verbose`

3. **Tier 3 (E2E tests with real browsers):**
   - Ensure both servers are running
   - Run E2E tests: `npm run test:e2e` or manual browser testing
   - Test in multiple browsers (Chrome, Firefox, Safari)
   - Test responsive behavior at different screen sizes
   - Test accessibility with keyboard navigation and screen readers

**Show me the COMPLETE output from each tier. Do not summarize. If any tests fail, STOP and fix before continuing.**

### Frontend Component Completion Verification
For the features you have implemented, confirm you have created ALL required frontend components:

- [ ] React components in `frontend/src/elements/`
- [ ] Custom hooks in `frontend/src/hooks/` if needed
- [ ] API integration in `frontend/src/services/` if needed
- [ ] Styling with Tailwind classes following design system
- [ ] Unit/component tests in `frontend/src/__tests__/`
- [ ] Integration tests in `frontend/src/__tests__/integration/`
- [ ] E2E tests or manual testing documentation
- [ ] Component documentation with props and usage examples
- [ ] Accessibility features and ARIA labels
- [ ] Responsive design for mobile/tablet/desktop
- [ ] Error boundaries and loading states
- [ ] ADR in `adr/`
- [ ] Todo entries updated in `todos/`

**Show me the specific file locations and confirm each file exists with proper content. Do not claim completion until every component is verified to work for users.**

### Final Completion Checklist
Before declaring this frontend implementation complete, you MUST verify every item on this checklist:

- [ ] All tests pass (show complete output for all tiers)
- [ ] Documentation validated (show temp test results for each file)
- [ ] Visual validation completed in multiple browsers
- [ ] Responsive design tested at mobile/tablet/desktop breakpoints
- [ ] Accessibility tested with keyboard navigation and screen readers
- [ ] Performance tested (bundle size, loading speed, rendering performance)
- [ ] Todo items updated to completed (show the updated todo files)
- [ ] No console errors or warnings in browser dev tools
- [ ] Component completion verified (show file locations for each component)
- [ ] Ready for user testing (show working frontend at http://localhost:9002)

**If any item is unchecked, STOP and fix it before declaring complete. Do not proceed until EVERY item is verified to work for actual users.**

### Final Validation
Before considering this frontend implementation complete, put on your ultrathink cap and run through this final validation:

1. Can users easily understand and navigate this feature?
2. Are all user interactions smooth and responsive?
3. Do all tests actually verify the intended user experience?
4. Is the documentation accurate and helpful for users?
5. Does this follow all established frontend patterns and design system?
6. Is this accessible to users with disabilities?
7. Does this work well on mobile devices and different screen sizes?

**If you cannot answer "yes" to all questions, continue working until you can.**

**Do not declare the feature complete until all validation steps pass and you've shown me the complete outputs for every step.**

## 9. POST-IMPLEMENTATION TASKS

### Todo System Completion Update
After completing the frontend implementation, update the todo management system:

1. The todo management system is two-tiered: Repo level todos are in `todos/` and module level todos are in their respective `src/` sub-directories.
2. Start with updating the master list (`000-master.md`):
   - Look through the entire file thoroughly
   - Update the status of completed frontend todos
   - Remove old completed entries that don't add context to outstanding todos
   - Keep this file concise, lean, and easy to navigate
3. Ensure that each todo's details are captured in:
   - `todos/active` for outstanding todos
   - `todos/completed` for completed todos
   - Move completed todos from `todos/active` to `todos/completed` with the date of completion

## Guidance System Update
Check the `CLAUDE.md` in frontend directory and root:

1. Check if we need to update the frontend guidance system
   - Ensure that only the absolute essentials are included
   - Adopt a multi-step approach by using the existing `CLAUDE.md` network (root -> frontend/ -> specific guides)
   - Do not try to solve everything in one place, make use of the hierarchical documentation system
   - Issue commands instead of explanations for frontend setup
   - Ensure that your commands are sharp and precise, covering only critical patterns that prevent immediate frontend failures
   - Run through the guidance flow yourself and ensure the following:
     - You can trace a complete path from basic component creation to advanced user interactions
     - Please maintain the concise, authoritative tone that respects context limits!

2. For the frontend in `frontend/`:
   - Please trace through the `CLAUDE.md` guidance system
   - Temp test all the instructions to ensure that they work in real browsers
   - For each user persona and their workflows, please run through the e2e using real browser testing
   - Run through the guidance flow as a user and ensure that you can trace everything from setup to advanced features

### Final Validation
Before considering this frontend implementation complete, put on your ultrathink cap and run through this final validation:

1. Can users easily understand and navigate this feature?
2. Are all user interactions smooth and responsive?
3. Do all tests actually verify the intended user experience?
4. Is the documentation accurate and helpful for users?
5. Does this follow all established frontend patterns and design system?

**If you cannot answer "yes" to all questions, continue working until you can.**

**Do not declare the feature complete until all validation steps pass and you've shown me the complete outputs for every step.**

## 10. ULTRATHINK CAP CRITIQUE (FRONTEND)

Put on your ultrathink cap again. Starting fresh, critique this frontend implementation.
- Read adr, guidance, and documentations thoroughly.
- Check the detailed todo entries in `todos/`.
- Make sure you understand the user experience intent and purpose of this frontend feature.
- Test the actual feature in real browsers as a real user would.

Then, review this frontend project without any prejudice:

1. **Is the frontend delivering the user experience intents, purposes and user objectives**
   - Does it meet the functional requirements for users?
   - Does it meet user expectations for modern web applications?
   - Does it follow the architectural decisions made in the ADR?
   - Does it integrate well with existing frontend components?

2. **What looks wrong or incomplete from a user perspective?**
   - Are there missing error states or loading indicators?
   - Are there untested user interaction paths?
   - Are there performance bottlenecks that affect user experience?
   - Are there accessibility barriers for users with disabilities?
   - Are there responsive design issues on different devices?

3. **What tests are missing or inadequate for user confidence?**
   - Are all user interaction paths covered?
   - Are error conditions properly tested from user perspective?
   - Are accessibility features thoroughly tested?
   - Are performance characteristics verified across devices?

4. **What documentation is unclear or missing for users?**
   - Are component usage examples clear and complete?
   - Are user workflows documented?
   - Are error conditions explained to users?
   - Are accessibility features documented?

5. **What would frustrate a user trying to use this feature?**
   - Are error messages helpful and actionable?
   - Are loading states clear and informative?
   - Are interactions intuitive and discoverable?
   - Are common user mistakes handled gracefully?
   - Does it work well on their preferred devices and browsers?

**Be honest, fair, and transparent. Find real problems that affect users. Show me specific issues with code examples and actual user experience problems.**
**Test the feature yourself in multiple browsers and record your critique in the appropriate `docs/critiques` directory**

## 11. GIT Procedures
1. Never use git reset --hard or git reset --soft.
2. Always check all local changes (from all sessions) and add/stage all modified and untracked files.
3. Always stash any uncommitted changes before any potentially destructive git operations.
4. For frontend changes, ensure bundle builds successfully before committing: `cd frontend && npm run build`

## 12. Release Versions
1. Please follow `# contrib (removed)/development/workflows/release-checklist.md`
2. For frontend releases, ensure production build works: `cd frontend && npm run build`
3. Test production build locally before release
4. Continue with release process
5. Release to github and appropriate package managers