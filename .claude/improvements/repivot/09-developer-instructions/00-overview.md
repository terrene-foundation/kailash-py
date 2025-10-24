# Developer Instructions: Overview

**Purpose:** Assign specific tasks to each development team with clear procedures

---

## Team Structure

### Core SDK Team
**Responsibility:** Runtime enhancements, CLI, telemetry
**Lead:** TBD
**Size:** 1-2 developers
**Timeline:** Weeks 9-12 (after templates complete)

### DataFlow Team
**Responsibility:** Validation helpers, error messages, Quick Mode hooks
**Lead:** TBD
**Size:** 1 developer
**Timeline:** Weeks 3-8 (parallel with templates)

### Nexus Team
**Responsibility:** Configuration presets, enhanced errors, Quick Mode integration
**Lead:** TBD
**Size:** 1 developer
**Timeline:** Weeks 5-8 (parallel with DataFlow)

### Kaizen Team
**Responsibility:** None (no changes needed), marketplace wrapper components later
**Lead:** TBD
**Size:** 0 initially, 1 developer in Phase 3
**Timeline:** Phase 3 (Months 13+)

### Templates Team
**Responsibility:** Build 3 AI-optimized templates
**Lead:** TBD
**Size:** 1-2 developers
**Timeline:** Weeks 1-8 (first priority)

### Components Team
**Responsibility:** Build 5 official marketplace components
**Lead:** TBD
**Size:** 1-2 developers
**Timeline:** Weeks 13-22 (after templates and Quick Mode complete)

### CLI Team
**Responsibility:** Build kailash CLI commands
**Lead:** TBD (can be same as Core SDK team)
**Size:** 1 developer
**Timeline:** Weeks 9-14 (after templates design finalized)

---

## Coordination

### Dependencies

```
Templates Team (Weeks 1-8)
       ↓ (Templates define patterns)
DataFlow Team (Weeks 3-8) ∥ Nexus Team (Weeks 5-8)
       ↓ (Validation and presets ready)
CLI Team (Weeks 9-14) ∥ Core SDK Team (Weeks 9-12)
       ↓ (Quick Mode infrastructure ready)
Components Team (Weeks 13-22)
       ↓ (All infrastructure in place)
Integration Testing (Weeks 23-24)
```

### Weekly Sync

**All teams:** 30-minute standup
- What shipped last week
- What's shipping this week
- Blockers or dependencies

**Templates team leads:** They define patterns others implement

---

## Subagent Workflow Protocol

### Phase 1: Analysis (Before Writing Code)

**For ALL teams, ALWAYS start with:**

```
1. requirements-analyst
   → Break down your specific tasks into subtasks
   → Create ADR (Architecture Decision Record)
   → Identify dependencies on other teams

2. sdk-navigator
   → Find existing patterns in SDK
   → Locate relevant code
   → Understand current implementation

3. framework-advisor (if applicable)
   → Determine if change affects Core SDK, DataFlow, Nexus
   → Identify integration points
   → Recommend approach

4. {framework}-specialist (specific to your team)
   → dataflow-specialist for DataFlow team
   → nexus-specialist for Nexus team
   → pattern-expert for Core SDK team
   → Get framework-specific guidance
```

### Phase 2: Planning (Before First Line)

```
5. todo-manager
   → Create detailed task breakdown
   → Estimate effort for each task
   → Identify milestones

6. ultrathink-analyst
   → Analyze complexity and failure points
   → Identify edge cases
   → Plan error handling

7. intermediate-reviewer
   → Review task breakdown
   → Validate approach before coding
   → Ensure alignment with repivot goals
```

### Phase 3: Implementation (TDD Approach)

```
8. tdd-implementer
   → Write tests FIRST for each component
   → Implement to pass tests
   → Refactor for quality

9. {framework}-specialist (ongoing consultation)
   → Consult on framework-specific patterns
   → Validate implementation approach
   → Review complex sections

10. intermediate-reviewer (after each component)
    → Review completed component
    → Ensure quality standards met
    → Validate integration points
```

### Phase 4: Validation (Before PR)

```
11. gold-standards-validator
    → Check compliance with Kailash standards
    → Validate absolute imports
    → Check error handling patterns

12. testing-specialist
    → Verify 3-tier testing complete
    → Validate NO MOCKING policy (Tier 2-3)
    → Check test coverage (80%+ target)

13. documentation-validator
    → Test all code examples
    → Ensure docs are accurate
    → Validate CLAUDE.md instructions

14. intermediate-reviewer (final)
    → Final review before PR
    → Ensure all requirements met
    → Check integration with other teams' work
```

### Phase 5: Release (Before Merging)

```
15. git-release-specialist
    → Run pre-commit checks
    → Validate PR workflow
    → Ensure proper versioning

16. deployment-specialist (if deployment changes)
    → Validate Docker configurations
    → Check Kubernetes manifests
    → Ensure deployment docs updated
```

---

## Code Review Process

### Every PR Must:

1. **Pass automated checks:**
   - ✅ All tests passing (pytest)
   - ✅ Linting passing (black, isort, ruff)
   - ✅ Type checking (mypy)
   - ✅ Security scanning

2. **Have manual review:**
   - ✅ Code review by tech lead
   - ✅ gold-standards-validator subagent review
   - ✅ Documentation review

3. **Meet quality standards:**
   - ✅ 80%+ test coverage
   - ✅ All public APIs documented
   - ✅ CLAUDE.md updated (if applicable)
   - ✅ Backward compatibility verified

---

## Communication Channels

### Daily Updates (Async)

**Slack/Discord channel:** #repivot-dev
- What you shipped today
- What you're working on tomorrow
- Blockers or questions

### Weekly Sync (Synchronous)

**30-minute call:** All teams
- Progress review
- Demo completed work
- Coordinate dependencies
- Adjust priorities

### Ad-Hoc Communication

**When needed:**
- DM for quick questions
- Tag in PR for review
- Slack thread for design discussions

---

## Next Steps

Read your team-specific instructions:

1. **Core SDK Team** → `01-core-sdk-instructions.md`
2. **DataFlow Team** → `02-dataflow-instructions.md`
3. **Nexus Team** → `03-nexus-instructions.md`
4. **Kaizen Team** → `04-kaizen-instructions.md`
5. **Templates Team** → `05-templates-instructions.md`
6. **Components Team** → `06-components-instructions.md`
7. **CLI Team** → `07-cli-instructions.md`

---

**Each team's document includes:**
- Required reading (which docs to review)
- Specific tasks (what to build)
- Subagent workflow (which specialists, when)
- Testing requirements
- Success criteria
- Coordination points with other teams
