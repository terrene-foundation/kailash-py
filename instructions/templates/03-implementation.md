# PHASE 3: Implementation

> **Usage**: Paste this AFTER human has typed "APPROVED" on Phase 2 todo list
> **Prerequisite**: Approved todos exist in `todos/active/`
> **Session Model**: This template is designed to be pasted into FRESH sessions repeatedly
> **Next Phase**: After all todos complete, paste `04-validation.md`

---

## HUMAN INPUT

### Context (Fill for Fresh Sessions)

**Referencing Plans In**: `docs/02-plans/_______________`
**Active Todos In**: `todos/active/`
**Session Resume Doc**: `docs/04-codegen-instructions/_______________` (REQUIRED after first session)

### Environment Confirmation

<!-- Confirm these are ready -->

- [ ] Docker is running (for integration tests)
- [ ] `.env` file is populated with API keys
- [ ] Test database is accessible

### LLM Configuration (For AI Features)

- **Local LLM**: (Ollama model name, if using)
- **Cloud LLM**: (Check .env - assume model names in memory are outdated)
- **Preference**: (Local first, or Cloud for speed?)

### Worktree Identity (If Using Parallel Development)

This session is for:

- [ ] Backend worktree → Follow `docs/04-codegen-instructions/01-backend-worktree.md`
- [ ] Web worktree → Follow `docs/04-codegen-instructions/02-web-worktree.md`
- [ ] Mobile worktree → Follow `docs/04-codegen-instructions/03-mobile-worktree.md`
- [ ] Single repo (no worktrees)

---

## CLAUDE CODE INSTRUCTIONS

### Context Loading (For Fresh Sessions)

**IMPORTANT**: Claude Code sessions are stateless. Each fresh session must:

1. **Load context from docs/**
   - Peruse `docs/04-codegen-instructions/` for this worktree/project
   - Reference `docs/02-plans/` for architecture decisions
   - Reference `docs/01-analysis/` for requirements context
   - Reference `docs/03-user-flows/` for user journey acceptance criteria

2. **Check current state**
   - Read `todos/active/000-master.md` for overall status
   - Identify which todos are IN_PROGRESS vs PENDING
   - Continue from where last session left off

3. **Achieve situational awareness before proceeding**

### Implementation Loop

**REPEAT THIS UNTIL ALL `todos/active/` ARE MOVED TO `todos/completed/`**

**ITERATION LIMITS:**
- If same todo fails 3 consecutive times: **STOP and ESCALATE to human**
- If all todos blocked by dependencies: **STOP and report blockers**
- Do NOT continue looping indefinitely

#### Step 1: Select Next Todo

Using `todo-manager`:

- Identify next priority todo from `000-master.md`
- Mark as IN_PROGRESS
- Review acceptance criteria and dependencies

#### Step 2: Consult Framework Specialists

Before implementation, consult appropriate specialists:

- **Backend/Database**: `dataflow-specialist`, `nexus-specialist`
- **AI Features**: `kaizen-specialist`
- **Frontend React**: `react-specialist`, `uiux-designer`
- **Frontend Flutter**: `flutter-specialist`, `uiux-designer`
- **MCP Integration**: `mcp-specialist`

Follow procedural directives from specialists.

#### Step 3: Test-First Implementation

Using `tdd-implementer`:

1. Write tests FIRST based on acceptance criteria
2. Implement minimum code to pass tests
3. Refactor while tests remain green

#### Step 4: Testing Discipline

Using `testing-specialist`:

**CRITICAL RULES:**

- No tests can be skipped (ensure Docker is running)
- Do NOT rewrite tests just to pass - check infrastructure first
- Tests must reflect user intent and expectations
- NO stubs, hardcodes, simulations, naive fallbacks without informative logs

**Before Integration/E2E tests:**

```bash
./tests/utils/test-env up && ./tests/utils/test-env status
```

NEVER run pytest directly for integration/E2E without verifying test-env is up.

**For AI/LLM Features:**

- If tests are too slow with local LLMs, switch to OpenAI (check .env)
- Before declaring test failure, check:
  1. Structured outputs are coded properly
  2. LLM agentic pipelines are coded properly
  3. Only after exhausting I/O and pipeline errors, try larger model
- Utilize LLM capabilities - NO naive NLP (keywords, regex)
- Web check model names in .env before declaring them invalid

**All tests must pass at 100% before closing todo.**

#### Step 5: Verification with Evidence

Every task must be verified with EVIDENCE before closing:

- Test output showing pass
- Screenshot/log showing feature works
- Documentation updated

#### Step 6: Update Todos

Using `todo-manager`:

- Mark todo as COMPLETED with evidence
- Move to `todos/completed/` with completion date
- Update `000-master.md`
- Sync to GitHub via `gh-manager` if applicable

#### Step 7: Documentation

At end of each phase/feature, write docs to `docs/00-developers/`:

- Use sequential naming: 00-, 01-, etc.
- Focus on: essence, intent, "what it is", "how to use it"
- NOT: status, progress, reports, irrelevant information

#### Step 8: Expand Agents & Skills (EVERY TODO - Critical for Self-Sustainability)

**After EACH todo completion, expand project-specific agents and skills:**

1. **Update `.claude/agents/project/`**
   - Add new agents for patterns discovered during this todo
   - Update existing agents with new capabilities
   - Ensure agents reference updated documentation

2. **Update `.claude/skills/project/`**
   - Add implementation patterns from this todo to skills
   - Document decisions and rationale
   - Reference `docs/00-developers/` for detailed context

**This is part of the loop** - incremental expansion captures knowledge as you go, not just at the end.

**Goal**: By Phase 4, agents/skills should be comprehensive enough to work WITHOUT these instruction templates.

---

**END OF IMPLEMENTATION LOOP** - Repeat Steps 1-8 for each todo until all complete.

---

### Session Resume Document Creation

If this is a multi-session implementation:

1. **Before ending session**, create/update session resume doc:

   ```markdown
   # Session Resume: [Feature/Worktree Name]

   ## Context Loading

   Peruse this document and reference linked docs for situational awareness.
   Check todos/active/ for current state. Then proceed with implementation.

   ## Current State

   - Completed: [list todos completed this session]
   - In Progress: [current todo]
   - Next Up: [next todos in priority order]

   ## Key Decisions This Session

   - [Decision 1 with rationale]
   - [Decision 2 with rationale]

   ## References

   - Architecture: docs/02-plans/architecture/
   - Requirements: docs/01-analysis/
   - Todos: todos/active/000-master.md
   ```

2. **Save to** `docs/04-codegen-instructions/[feature-name].md`

### Worktree Synchronization (If Using Parallel Development)

Using `git-release-specialist`:

1. **Progressive Sync to Main**
   - Order: Backend → Web → App
   - Each worktree syncs to main branch progressively

2. **Conflict Resolution**
   - Do NOT blindly adopt theirs/ours
   - Check for unique codebases between versions
   - Integrate properly, do not overwrite

3. **Verification**
   - All worktrees on same commit
   - If conflicts remain, STOP and ensure integration is complete

---

## PROGRESS CHECK

At any point, human can ask for status. Provide:

1. **Completed Todos**: List with evidence
2. **Current Todo**: What's in progress, blockers if any
3. **Remaining Todos**: Count and estimate
4. **Test Status**: Pass/fail summary
5. **Artifacts Created**: List of docs/code created

---

## PHASE 3 COMPLETE

When ALL todos in `todos/active/` have been moved to `todos/completed/`:

1. **Verify all tests pass** (100%, no skips)
2. **Verify documentation is complete** in `docs/00-developers/`
3. **Create final session resume doc** for future reference
4. **Present completion summary to human**

Human will paste `04-validation.md` to proceed.

---

## SPAM PATTERN

**This template is designed to be pasted into FRESH SESSIONS repeatedly.**

For each new session:

1. Paste this template
2. Fill in Context section
3. Claude loads context and continues from current state
4. Repeat until all todos complete

This pattern:

- Each iteration is a fresh session (no accumulated errors)
- The instruction document provides consistent context
- Progress is tracked via todo completion (externalized state)
- Human can pause, resume, or adjust between iterations

---

_Template Version: 2.0_
_Phase: 3 of 4 (Implementation)_
