# Team Coordination and Subagent Workflow

**Purpose:** Master coordination document showing how all teams work together

---

## Team Dependencies and Critical Path

### Visual Timeline

```
Week 1-2:   Templates Team → SaaS structure + models
Week 3-4:   Templates Team → SaaS workflows + testing
            DataFlow Team → kailash-dataflow-utils package ←─┐
                                                             │
Week 5-6:   Templates Team → Internal Tools template        │
            DataFlow Team → Enhanced error messages ─────────┤
            Nexus Team → Configuration presets               │
                                                             │
Week 7-8:   Templates Team → API Gateway template           │
            DataFlow Team → Validation helpers + Quick hooks │
            Nexus Team → Quick deploy + enhanced errors      │
                                                             │
Week 9-10:  Core SDK Team → Telemetry + Error context ←─────┘
            CLI Team → kailash create command

Week 11-12: Core SDK Team → ValidatingLocalRuntime + Performance
            CLI Team → kailash dev command

Week 13-14: CLI Team → kailash marketplace commands
            Components Team → kailash-sso

Week 15-16: Components Team → kailash-sso (cont)

Week 17-18: Components Team → kailash-rbac

Week 19-20: Components Team → kailash-admin

Week 21-22: Components Team → kailash-payments

Week 23-24: Integration testing (ALL TEAMS)
            Beta launch preparation
```

---

## Critical Dependencies

### Templates Team (Leads)

**Blocks:**
- CLI Team (needs template structure)
- DataFlow Team (needs field patterns)
- Nexus Team (needs configuration patterns)

**Dependency:** None (can start immediately)

**Priority:** HIGHEST (foundation of repivot)

---

### DataFlow Team

**Blocks:**
- Templates Team (needs kailash-dataflow-utils)
- Core SDK Team (needs validation interface)
- Components Team (kailash-rbac needs DataFlow)

**Dependency:** Templates (need to see what patterns templates use)

**Can start:** Week 3 (after templates establish patterns)

---

### Nexus Team

**Blocks:**
- Templates Team (needs presets)
- CLI Team (needs quick_deploy API)

**Dependency:** Templates (need to see what configurations templates need)

**Can start:** Week 5 (after templates show configuration needs)

---

### Core SDK Team

**Blocks:**
- Quick Mode (needs ValidatingLocalRuntime)
- All teams (need telemetry)

**Dependency:** DataFlow (validation interface should align)

**Can start:** Week 9 (after DataFlow team designs validation)

---

### CLI Team

**Blocks:**
- User onboarding (primary interface)

**Dependency:**
- Templates (need template structure)
- Marketplace (need component list)

**Can start:** Week 9 (after templates finalized)

---

### Components Team

**Blocks:**
- Ecosystem growth

**Dependency:**
- Templates (components should fit template patterns)
- DataFlow (kailash-rbac needs DataFlow models)
- Marketplace infrastructure (CLI commands)

**Can start:** Week 13 (after infrastructure ready)

---

## Weekly Coordination Meetings

### Monday Standup (30 minutes) - ALL TEAMS

**Format:**
```
Templates Team:
- Last week: Completed SaaS models
- This week: Building auth workflows
- Blockers: None
- Needs: DataFlow team's kailash-dataflow-utils ETA

DataFlow Team:
- Last week: Started kailash-dataflow-utils
- This week: Finishing field helpers, publishing to PyPI
- Blockers: None
- Needs: Templates team to test package

[... each team reports ...]
```

**Action items:**
- Assign follow-ups
- Resolve blockers
- Adjust priorities

---

### Thursday Tech Review (1 hour) - ROTATING

**Week 1:** Templates team demos SaaS template structure
**Week 2:** Templates team demos auth workflows
**Week 3:** DataFlow team demos kailash-dataflow-utils
**Week 4:** Templates team demos complete SaaS template

**Format:**
- 30 min demo
- 15 min Q&A
- 15 min feedback and discussion

**Benefits:**
- Knowledge sharing
- Early feedback
- Quality assurance
- Team alignment

---

## Subagent Workflow - Master Process

### Universal Workflow (ALL Teams Follow This)

#### Phase 1: Requirements and Planning (Day 1-3)

**Day 1 Morning:**
```bash
> Use the requirements-analyst subagent to break down [your component] into detailed technical requirements with acceptance criteria and dependencies on other teams

# Output: requirements-breakdown.md with subtasks
```

**Day 1 Afternoon:**
```bash
> Use the sdk-navigator subagent to locate all relevant existing code, patterns, and examples for [your component] in the SDK

# Output: existing-patterns.md with file references
```

**Day 2 Morning:**
```bash
> Use the framework-advisor subagent to determine which frameworks (Core SDK, DataFlow, Nexus, Kaizen) your component uses and get integration guidance

> Use the [appropriate-specialist] subagent (dataflow-specialist, nexus-specialist, pattern-expert, or kaizen-specialist) to get framework-specific implementation guidance

# Output: framework-integration-plan.md
```

**Day 2 Afternoon:**
```bash
> Use the ultrathink-analyst subagent to analyze complexity, identify potential failure points, and plan error handling for [your component]

# Output: risk-analysis.md with failure points identified
```

**Day 3 Morning:**
```bash
> Use the todo-manager subagent to create detailed task breakdown with time estimates, dependencies, and daily milestones for [your component]

# Output: task-breakdown.md in todos/
```

**Day 3 Afternoon:**
```bash
> Use the intermediate-reviewer subagent to review task breakdown and validate approach before writing any code

# Output: approach-validation.md with approval or suggestions
```

**Deliverable:** Complete plan, validated approach, ready to write tests

---

#### Phase 2: Test-First Development (Day 4-5)

**Day 4-5 (Both Days):**
```bash
> Use the tdd-implementer subagent to create comprehensive test suite for [your component] before any implementation code

# Tests must cover:
# - Tier 1 (Unit): All functions, mocked dependencies
# - Tier 2 (Integration): Real infrastructure, NO MOCKING
# - Tier 3 (E2E): Complete user flows

# Output: Complete test suite (failing tests)
```

**Validation:**
```bash
> Use the testing-specialist subagent to review test suite ensuring 3-tier strategy and NO MOCKING policy in Tier 2-3

# Verify: Test coverage will be 80%+ when code implemented
```

**Deliverable:** Comprehensive test suite (all failing, ready for implementation)

---

#### Phase 3: Implementation (Day 6-10)

**Per Component/Feature (iterate):**

**Day 6-7:**
```bash
> Use the [framework-specialist] subagent to implement [feature/component] following framework-specific patterns

# For DataFlow features: dataflow-specialist
# For Nexus features: nexus-specialist
# For Core SDK features: pattern-expert
# For Kaizen wrappers: kaizen-specialist

# Code until tests pass
```

**Day 8:**
```bash
> Use the gold-standards-validator subagent to validate [implemented feature] follows absolute imports, error handling, and parameter passing standards

# Fix any violations immediately
```

**Day 9:**
```bash
> Use the intermediate-reviewer subagent to review [implemented feature] for code quality, edge case handling, and integration correctness

# Address feedback, refactor if needed
```

**Day 10:**
```bash
> Use the testing-specialist subagent to run complete test suite including integration tests with real infrastructure

# Verify: All tests pass, coverage ≥80%
```

**Deliverable:** Feature complete, tested, reviewed

---

#### Phase 4: Documentation and Integration (Day 11-13)

**Day 11:**
```bash
> Use the documentation-validator subagent to create or update documentation including README, API reference, and CLAUDE.md with tested examples

# Test EVERY code example in docs
```

**Day 12:**
```bash
# Integration testing with other teams' work
> Use the [framework-specialist] subagent to test integration points with dependencies from other teams

# For example:
# - Templates team: Test your component in template
# - DataFlow + Core SDK: Test validation integration
```

**Day 13:**
```bash
> Use the intermediate-reviewer subagent to perform final comprehensive review of complete feature including code, tests, and documentation

# Address all feedback before PR
```

**Deliverable:** Complete feature ready for PR

---

#### Phase 5: PR and Merge (Day 14-15)

**Day 14:**
```bash
> Use the git-release-specialist subagent to run pre-commit validation (black, isort, ruff) and create PR with comprehensive description

# PR description must include:
# - What was built
# - How to test
# - Integration points
# - Backward compatibility verification
# - Screenshots/demos (if UI)
```

**Day 15:**
```bash
# Code review by tech lead
# Address review feedback

> Use the intermediate-reviewer subagent to ensure all PR feedback addressed before final merge

# Merge after approval
```

**Deliverable:** Feature merged to main

---

## Subagent Usage Patterns by Task Type

### For New Components (Templates, Components)

**Heavy usage:**
- requirements-analyst (detailed breakdown)
- ultrathink-analyst (complexity analysis)
- tdd-implementer (test-first approach)
- framework-specialist (implementation guidance)
- intermediate-reviewer (quality gates)

**Moderate usage:**
- sdk-navigator (find examples)
- todo-manager (task tracking)
- testing-specialist (test validation)
- gold-standards-validator (compliance)

**Light usage:**
- git-release-specialist (PR creation)
- documentation-validator (doc testing)

### For Modifications (Core SDK, DataFlow, Nexus)

**Heavy usage:**
- sdk-navigator (find code to modify)
- pattern-expert (maintain patterns)
- gold-standards-validator (ensure no breaks)
- testing-specialist (regression testing)

**Moderate usage:**
- framework-specialist (framework-specific changes)
- intermediate-reviewer (change review)
- documentation-validator (doc updates)

**Light usage:**
- requirements-analyst (changes are specified)
- ultrathink-analyst (changes are simple)

### For CLI/Tooling

**Heavy usage:**
- requirements-analyst (UX is complex)
- pattern-expert (Python CLI patterns)
- testing-specialist (CLI testing)

**Moderate usage:**
- intermediate-reviewer (UX review)
- documentation-validator (help text)

---

## Integration Testing Coordination

### Week 8: Templates + DataFlow + Nexus

**Joint testing session:**
```bash
# All three teams together

# 1. Templates team generates SaaS template
# 2. Template uses DataFlow (with kailash-dataflow-utils)
# 3. Template uses Nexus (with presets)
# 4. Verify:
#    - Field helpers prevent errors
#    - Nexus.for_saas() works correctly
#    - Complete integration successful
```

**Subagent:**
```bash
> Use the testing-specialist subagent to coordinate cross-team integration testing of templates, DataFlow, and Nexus enhancements

> Use the intermediate-reviewer subagent to validate complete integration meets all requirements
```

---

### Week 12: Templates + DataFlow + Nexus + Core SDK + CLI

**Complete stack testing:**
```bash
# All teams together

# 1. CLI generates template
# 2. Template uses all enhancements:
#    - DataFlow validation helpers
#    - Nexus presets
#    - Enhanced error messages
#    - Telemetry tracking
# 3. Test with Claude Code (AI customization)
# 4. Verify end-to-end flow works

> Use the testing-specialist subagent to orchestrate complete end-to-end testing of all repivot components working together

> Use the intermediate-reviewer subagent to validate entire system meets success criteria before beta launch
```

---

### Week 22: Components Integration Testing

**Full ecosystem test:**
```bash
# Test all components together

# 1. Generate template
# 2. Install all components (sso, rbac, admin, payments)
# 3. Configure in template
# 4. Verify:
#    - All components work together
#    - No conflicts
#    - Integration is seamless

> Use the testing-specialist subagent to validate complete component stack integration

> Use the intermediate-reviewer subagent to ensure ecosystem integration is production-ready
```

---

## Quality Gates (Checkpoints)

### Week 4: Template Quality Gate

**Before proceeding to templates 2-3:**
- [ ] SaaS template works (95%+ success rate)
- [ ] Beta test with 5 users (NPS 35+)
- [ ] Claude Code customization works (70%+ first-try)
- [ ] CUSTOMIZE.md validated as clear

**Review:**
```bash
> Use the intermediate-reviewer subagent to evaluate SaaS template quality and recommend go/no-go for templates 2-3

# If issues found: Fix before proceeding
# If quality gate passed: Proceed to templates 2-3
```

---

### Week 8: Foundation Complete Gate

**Before proceeding to Core SDK/CLI work:**
- [ ] All 3 templates complete
- [ ] DataFlow enhancements complete
- [ ] Nexus enhancements complete
- [ ] Integration tested

**Review:**
```bash
> Use the intermediate-reviewer subagent to evaluate complete foundation (templates + framework enhancements) before proceeding to Core SDK and CLI work

# Verify: Foundation is solid for building Quick Mode on top
```

---

### Week 14: Infrastructure Complete Gate

**Before proceeding to components:**
- [ ] CLI working (create, dev, marketplace)
- [ ] Core SDK enhancements complete
- [ ] Quick Mode functional
- [ ] All infrastructure tested

**Review:**
```bash
> Use the intermediate-reviewer subagent to validate complete infrastructure is ready for ecosystem phase (component development)

# Verify: All pieces work together seamlessly
```

---

### Week 22: Components Complete Gate

**Before beta launch:**
- [ ] All 5 components published
- [ ] All components tested together
- [ ] Documentation complete
- [ ] Templates updated to use components

**Review:**
```bash
> Use the intermediate-reviewer subagent to perform final comprehensive review of complete repivot before public beta launch

# This is the final quality gate before users see it
```

---

## Communication Protocols

### Slack/Discord Channels

**#repivot-general:** General discussion, announcements
**#repivot-templates:** Templates team coordination
**#repivot-dataflow:** DataFlow enhancements
**#repivot-nexus:** Nexus enhancements
**#repivot-core-sdk:** Core SDK enhancements
**#repivot-cli:** CLI development
**#repivot-components:** Marketplace components
**#repivot-testing:** Cross-team integration testing

### Daily Updates (Async)

**Each developer posts daily:**
```
Today (2025-01-15):
✅ Completed: TimestampField implementation
🚧 In progress: UUIDField implementation
⏭️  Next: JSONField implementation
❓ Questions: Should JSONField auto-serialize or just validate?
🚫 Blockers: None
```

### Weekly Demos (Synchronous)

**Thursday 2pm:** Rotating demos
- Each team demos progress
- 30 min demo + Q&A
- Recorded for async team members

---

## Code Ownership

### Who Owns What

**Core SDK Team:**
- `src/kailash/runtime/` (telemetry, validation, errors)
- `src/kailash/sdk_exceptions.py` (error classes)

**DataFlow Team:**
- `apps/kailash-dataflow/src/dataflow/core/` (engine, nodes)
- `packages/kailash-dataflow-utils/` (field helpers package)

**Nexus Team:**
- `apps/kailash-nexus/src/nexus/core.py` (presets, quick deploy)

**Kaizen Team:**
- `apps/kailash-kaizen/` (no changes in Phase 1-2)

**Templates Team:**
- `templates/` (all templates)
- `.claude/skills/it-team/` (Golden Patterns)

**Components Team:**
- `packages/kailash-sso/` (SSO component)
- `packages/kailash-rbac/` (RBAC component)
- `packages/kailash-admin/` (Admin component)
- `packages/kailash-payments/` (Payments component)

**CLI Team:**
- `src/kailash/cli/` (all CLI commands)

**Shared ownership:**
- Documentation (`sdk-users/docs-it-teams/`, `sdk-users/docs-developers/`)
- Tests (`tests/integration/`, `tests/e2e/`)

---

## Conflict Resolution

### If Two Teams Need Same Code

**Example:** DataFlow and Core SDK both enhancing error messages

**Resolution process:**
1. Discuss in #repivot-general
2. Tech lead decides ownership
3. Document decision in ADR
4. Losing team provides input/review

**Principle:** Clear ownership, collaborative input

---

### If Timeline Slips

**Example:** Templates team behind schedule

**Resolution:**
1. Assess impact (who's blocked?)
2. Reprioritize or add resources
3. Adjust dependent teams' start dates
4. Communicate changes to all teams

**Principle:** Transparency, early adjustment

---

### If Quality Gate Fails

**Example:** Template beta testing NPS <25

**Resolution:**
1. Stop subsequent work
2. Diagnose issues (user interviews)
3. Fix templates
4. Re-test
5. Proceed only when quality gate passes

**Principle:** Don't build on shaky foundation

---

## Master Subagent Workflow Reference

### For ANY Development Task

**Step 1: Analyze (BEFORE coding)**
```bash
> Use the requirements-analyst subagent to break down task
> Use the sdk-navigator subagent to find existing patterns
> Use the ultrathink-analyst subagent to identify failure points
```

**Step 2: Plan (BEFORE tests)**
```bash
> Use the todo-manager subagent to create task breakdown
> Use the intermediate-reviewer subagent to validate approach
```

**Step 3: Test First (TDD)**
```bash
> Use the tdd-implementer subagent to write tests before code
> Use the testing-specialist subagent to validate test strategy
```

**Step 4: Implement**
```bash
> Use the [framework-specialist] subagent to guide implementation
> Use the pattern-expert subagent for general patterns
```

**Step 5: Validate**
```bash
> Use the gold-standards-validator subagent to check compliance
> Use the intermediate-reviewer subagent to review implementation
```

**Step 6: Document**
```bash
> Use the documentation-validator subagent to test all examples
```

**Step 7: Release**
```bash
> Use the git-release-specialist subagent to prepare PR
> Use the intermediate-reviewer subagent for final review
```

**This is the gold standard workflow. Follow it for every task.**

---

## Monitoring Progress

### Metrics to Track (Per Team)

**Templates Team:**
- Templates completed: 3/3
- Beta test NPS: Target 40+
- Time-to-first-screen: Target <30 min
- AI customization success: Target 70%+

**DataFlow Team:**
- Package published: Y/N
- Error message enhancements: Complete
- Validation helpers: Complete
- Backward compatibility: 100%

**Nexus Team:**
- Presets implemented: 4/4
- Quick deploy working: Y/N
- Error enhancements: Complete
- Backward compatibility: 100%

**Core SDK Team:**
- Telemetry working: Y/N
- Enhanced errors: Complete
- ValidatingLocalRuntime: Complete
- Backward compatibility: 100%

**CLI Team:**
- Commands complete: 5/5 (create, dev, upgrade, marketplace, component)
- User satisfaction with CLI: Target 8+/10

**Components Team:**
- Components published: 4/4 (excluding dataflow-utils)
- Install success rate: Target 100%
- Component satisfaction: Target NPS 50+

---

## Integration Test Scenarios

### Scenario 1: Complete User Journey (Week 12)

**Test the vision:**
```bash
# 1. IT team member uses CLI to create project
kailash create my-saas --template=saas-starter

# 2. Configure
cp .env.example .env
# (edit .env)

# 3. Run
kailash dev
# - Templates team: Project structure
# - DataFlow team: Models validate correctly
# - Nexus team: Server starts with preset

# 4. Customize with Claude Code
"Add Product model with name, price, description"
# - Templates team: AI instructions guide Claude
# - DataFlow team: Field helpers prevent errors
# - Core SDK team: Enhanced errors if issues

# 5. Install component
kailash marketplace install kailash-sso
# - CLI team: Marketplace command works
# - Components team: SSO installs and configures

# 6. Test
# Request to API succeeds

# SUCCESS: End-to-end flow works
```

**Run this test weekly starting Week 8** (as components become available)

---

## Handoff Procedures

### When Your Work Blocks Others

**Example:** DataFlow team completes kailash-dataflow-utils (Week 4)

**Handoff procedure:**
1. **Notify dependent teams:**
   - Post in #repivot-templates: "kailash-dataflow-utils ready"
   - Tag @templates-team

2. **Provide integration guide:**
   - How to install: `pip install kailash-dataflow-utils`
   - How to use: Code examples
   - How to test: Integration test template

3. **Support integration:**
   - Answer questions in Slack
   - Pair programming session if needed
   - Fix bugs discovered during integration

4. **Validate integration:**
```bash
> Use the intermediate-reviewer subagent to validate that dependent team successfully integrated your component
```

---

## Definition of "Done" (Universal)

**A task is done when ALL are true:**
- [ ] Implementation complete (matches specification)
- [ ] Tests comprehensive (80%+ coverage, 3-tier)
- [ ] All tests passing (100% pass rate)
- [ ] Code reviewed and approved
- [ ] Documentation complete and tested
- [ ] Backward compatibility verified (if modifying existing code)
- [ ] Integration tested (if dependent on other teams)
- [ ] Subagent reviews complete (intermediate-reviewer approved)
- [ ] PR merged to main

**NOT done if:**
- ❌ Tests failing
- ❌ Code review pending
- ❌ Documentation incomplete
- ❌ Integration issues
- ❌ Backward compatibility broken

---

## Emergency Protocols

### If Critical Bug Found

**Example:** Backward compatibility broken in Core SDK changes

**Response (within 24 hours):**
1. **Stop all dependent work**
2. **Assess impact** (which users affected?)
3. **Fix immediately** (all hands on deck if needed)
4. **Test fix thoroughly**
5. **Hotfix release**
6. **Post-mortem** (how did this happen, how to prevent)

**Subagent:**
```bash
> Use the ultrathink-analyst subagent to analyze root cause of critical bug and identify systemic improvements to prevent recurrence
```

---

### If Team Falls Behind Schedule

**Example:** Templates team 2 weeks behind

**Response:**
1. **Assess impact** (who's blocked, what's delayed)
2. **Options:**
   - Add resources (hire contractor)
   - Reduce scope (2 templates instead of 3)
   - Delay dependent teams (adjust timeline)
3. **Communicate** (update all teams)
4. **Adjust plan** (revise milestones)

**Subagent:**
```bash
> Use the todo-manager subagent to reassess project timeline and adjust all team schedules based on new constraints
```

---

## Key Principles

### 1. Templates First
All other work supports templates. If templates aren't excellent, repivot fails.

### 2. Test First
No code without tests. TDD is mandatory, not optional.

### 3. Quality Over Speed
Don't rush. Shipping late is better than shipping broken.

### 4. Backward Compatibility Sacred
ZERO tolerance for breaking existing users. If in doubt, don't change.

### 5. Subagents Are Mandatory
Using specialists isn't optional. They prevent mistakes and ensure quality.

### 6. Communication Overcommunicate
When unsure, ask. When blocked, shout. When done, announce.

### 7. User First
Build for IT teams and developers, not for ourselves. Test with real users often.

---

## Success Checklist (Overall)

**Week 24: Ready for beta launch if:**
- [ ] All 3 templates work and tested
- [ ] kailash-dataflow-utils prevents datetime errors
- [ ] DataFlow error messages are helpful
- [ ] Nexus presets make configuration easy
- [ ] Core SDK telemetry and validation working
- [ ] CLI commands all functional
- [ ] 4 marketplace components published (sso, rbac, admin, payments)
- [ ] Integration testing complete (all pieces work together)
- [ ] Documentation complete (IT teams and developers)
- [ ] Beta test with 20 users successful (NPS 35+)
- [ ] Backward compatibility 100% (all existing tests pass)

**If ALL checked: Launch public beta**
**If ANY unchecked: Fix before launch**

---

**This coordination document ensures all teams work in harmony toward the common goal: Making Kailash the best enterprise application platform for IT teams using AI assistants.**

**Follow the subagent workflows, communicate constantly, and ship with quality.**
