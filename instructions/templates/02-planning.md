# PHASE 2: Planning

> **Usage**: Paste this AFTER Phase 1 artifacts exist in `docs/01-analysis/`
> **Prerequisite**: Human verified Phase 1 artifacts exist
> **Next Phase**: After APPROVED, paste `03-implementation.md`

---

## HUMAN INPUT (Optional Adjustments)

### Additional Constraints (if any since Phase 1)

<!-- Add any new constraints discovered or decided since analysis -->

### Priority Adjustments (if any)

<!-- Override default priority if needed -->

### Worktree Configuration (If Using Parallel Development)

<!-- Check if applicable -->

- [ ] Using parallel worktrees

If using worktrees:

- **Backend Worktree**: (branch name)
- **Web Worktree (React)**: (branch name)
- **App Worktree (Flutter)**: (branch name)

---

## CLAUDE CODE INSTRUCTIONS

### Prerequisite Check

**STOP if Phase 1 artifacts don't exist:**

```
Required: docs/01-analysis/*.md
Required: docs/03-user-flows/*.md (minimum 2 flows, OR explicit N/A with justification)
Required: .claude/agents/project/ (at least one agent)
Required: .claude/skills/project/SKILL.md
```

If these don't exist: **STOP EXECUTION**. Display: "BLOCKED: Phase 1 incomplete. Missing: [list specific files]". Do NOT proceed until resolved.

**Validate Phase 1 agents/skills:**

- Load and test the project-specific agents created in Phase 1
- Verify they can reference docs/01-analysis/ for context
- If agents/skills are incomplete, expand them before proceeding

### Planning Tasks

#### 1. Context Loading

Load and review all Phase 1 artifacts:

- `docs/01-analysis/*` - Analysis outputs
- `docs/03-user-flows/*` - User journey documentation

#### 2. Framework Selection

Using `framework-advisor`:

- Select appropriate Kailash frameworks (Core SDK, DataFlow, Nexus, Kaizen)
- Document selection rationale
- Identify integration points

#### 3. Architecture Planning

Using `requirements-analyst`:

- Break down user scenarios into functional requirements
- Create Architecture Decision Records (ADRs)
- Map requirements to SDK components

Document in: `docs/02-plans/architecture/`

#### 3.5. Test Infrastructure Planning

Using `testing-specialist`:

1. **Design 3-tier test strategy**:
   - Tier 1 (Unit): Mocking allowed, <1s per test
   - Tier 2 (Integration): Real infrastructure, <5s per test
   - Tier 3 (E2E): Real everything, <10s per test

2. **Plan test environment**:
   - Create `tests/utils/test-env` script (up/down/status commands)
   - Docker compose for test databases
   - Test data fixtures

Document in: `docs/02-plans/testing-strategy.md`

#### 4. Todo Creation

Using `todo-manager` and relevant agents:

1. **Create detailed todos** in `todos/active/` for EVERY task required

2. **Each todo must include:**
   - Acceptance criteria (measurable)
   - Dependencies on other todos
   - Risk assessment (HIGH/MEDIUM/LOW)
   - Testing requirements (what tests to write)
   - Estimated effort (1-2 hour chunks)

3. **Link to GitHub issues** via `gh-manager` if project uses GitHub

4. **Create master list** in `todos/active/000-master.md`

#### 5. Session Context Documents

**ALWAYS** create `docs/04-codegen-instructions/` with at minimum:

- `README.md` - Navigation index for all session documents
- `00-session-context.md` - Base context loading document for fresh sessions

**Division of Responsibility:**
- **Phase 2 creates**: Initial structure (`00-session-context.md`, worktree docs)
- **Phase 3 creates**: Session resume docs (`[feature-name].md`) as implementation progresses

**If using parallel development (worktrees)**, also create:

- `01-backend-worktree.md` - Independent backend instructions
- `02-web-worktree.md` - Independent web frontend instructions
- `03-mobile-worktree.md` - Independent mobile app instructions
- `04-integration-guide.md` - How codebases merge

Each instruction must be:

- Independent (copy-paste ready for fresh terminal)
- Reference detailed todos explicitly
- Include context loading section

#### 6. 80/15/5 Classification

For each planned feature/todo, classify:

| Classification       | Criteria                         | Gate                       |
| -------------------- | -------------------------------- | -------------------------- |
| **80% Reusable**     | Agnostic, works for any client   | PROCEED                    |
| **15% Self-Service** | Client-specific but configurable | PROCEED with config design |
| **5% Custom**        | One-off customization            | REQUIRES JUSTIFICATION     |

**GATE**: If custom work exceeds 5% of total effort, this MUST be explicitly justified and approved by human. Include justification in planning summary.

### Output Requirements

Create the following structure:

```
docs/02-plans/
├── README.md                    # Navigation index
├── architecture/
│   ├── ADR-001-framework-selection.md
│   └── [additional ADRs]
└── requirements/
    └── [functional requirements docs]

docs/04-codegen-instructions/    # ALWAYS created
├── README.md                    # Navigation index (required)
├── 00-session-context.md        # Base context for fresh sessions
├── 01-backend-worktree.md       # If using worktrees
├── 02-web-worktree.md           # If using worktrees
├── 03-mobile-worktree.md        # If using worktrees
└── 04-integration-guide.md      # If using worktrees

todos/active/
├── 000-master.md                # Master todo list
├── TODO-001-[feature].md
├── TODO-002-[feature].md
└── [additional todos]
```

---

## APPROVAL GATE (BLOCKING)

Present to human for approval:

### 1. Planning Summary

- Framework selection with rationale
- Architecture overview
- Key ADRs created

### 2. Todo List Overview

- Total number of todos
- Grouped by feature/component
- Estimated total effort

### 3. 80/15/5 Classification

- Percentage breakdown
- Any custom (5%) items requiring justification

### 4. Worktree Instructions (REQUIRED if using parallel development, N/A otherwise)

- Confirmation instructions are ready
- Worktree-specific scope summary

### 5. Artifacts Created

- List all files in docs/02-plans/
- List all files in docs/04-codegen-instructions/ (REQUIRED - always created per line 100)
- List all todos in todos/active/

---

## ⚠️ HARD GATE ⚠️

**Do NOT continue until human has explicitly approved the todo list.**

Human must respond with one of:

- **APPROVED** - Proceed to Phase 3 (Implementation)
- **REVISE: [feedback]** - Make adjustments and re-present
- **ABORT** - Stop work entirely

**Silence is NOT approval.** Wait for explicit response.

---

_Template Version: 2.0_
_Phase: 2 of 4 (Planning)_
