# kz as COC Runtime: First-Class Five-Layer Architecture

**Date**: 2026-03-21
**Source**: Deep COC mechanics analysis of .claude/ implementation

---

## The Principle

**kz IS the COC runtime.** It is not a CLI that happens to load some COC files. The COC five-layer architecture IS the kz architecture. Every layer maps to a kz subsystem. Every mechanism has a first-class implementation.

---

## How COC Works Today (in Claude Code)

From the mechanics analysis, COC physically executes through:

```
.claude/
├── agents/          → Layer 1: Intent (30 specialized subagents)
├── skills/          → Layer 2: Context (28 progressive knowledge directories)
├── rules/           → Layer 3: Soft guardrails (19 rule files, path-scoped)
├── settings.json    → Layer 3: Hard guardrails (9 hook scripts)
├── commands/        → Layer 4: Instructions (7 phase commands + agent teams)
├── learning/        → Layer 5: Learning (observations, instincts, checkpoints)
└── memory/          → Cross-cutting: auto-memory persistence
```

**The anti-amnesia mechanism** is the most critical: `user-prompt-rules-reminder.js` fires on EVERY user message, injecting rules + workspace state fresh into context. This survives context compression. Without it, COC degrades to vibe coding within 5 turns.

**The enforcement chain**: rules (soft, read by model) + hooks (hard, deterministic) + mandatory agent delegation (intermediate-reviewer, security-reviewer). Three independent enforcement layers. If any two fail, the third catches violations.

**The workspace system**: Not just file storage — it's the execution record. Hooks inspect workspace state (phase, active todos, test results). Commands are workspace-aware (auto-detect, read briefs, write to correct subdirectory).

---

## How kz Implements Each Layer

### Layer 1: Intent → `.kaizen/agents/`

**Mapping**: `.claude/agents/` → `.kaizen/agents/`

```
.kaizen/agents/
├── _guide.md                  # How to define agents (shipped with kz)
├── builtin/                   # Ships with kz (default agent definitions)
│   ├── researcher.md          # Codebase exploration (like CC's Explore)
│   ├── implementer.md         # Code writing with TDD
│   ├── reviewer.md            # Code review (like intermediate-reviewer)
│   ├── security.md            # Security audit
│   └── planner.md             # Task decomposition
├── project/                   # User-created for this project
│   └── [user-defined agents]
└── user/                      # User-global agents (~/.kaizen/agents/)
    └── [user-defined agents]
```

**Agent frontmatter** (same YAML-in-markdown pattern):

```markdown
---
name: researcher
description: Explore codebase, find patterns, read documentation
tools: Read, Glob, Grep, Bash
model: tier-2 # Uses tier system, not hardcoded model name
max_turns: 30
---

You are a codebase researcher. Your job is to...
```

**Progressive disclosure**:

- **Driver**: Built-in agents auto-selected by kz based on task. User never sees agent definitions.
- **Tuner**: User adds project-specific agents in `.kaizen/agents/project/`. They appear alongside built-ins.
- **Mechanic**: User modifies built-in agent behavior by overriding in project directory (project agents take precedence over builtin with same name).

**Subagent spawning**: When kz needs a researcher, it spawns a subagent using the `SpawnAgent` tool with the researcher's system prompt injected. Fresh context, depth-limited.

### Layer 2: Context → `.kaizen/skills/`

**Mapping**: `.claude/skills/` → `.kaizen/skills/`

```
.kaizen/skills/
├── builtin/                   # Ships with kz (minimal set)
│   ├── coc-reference/SKILL.md    # COC methodology
│   └── kailash-reference/SKILL.md # Kailash SDK patterns
├── project/                   # User-created for this project
│   └── [domain-specific skills]
└── user/                      # User-global skills (~/.kaizen/skills/)
    └── [reusable skills]
```

**Progressive disclosure pattern** (from COC analysis):

1. `SKILL.md` — entry point, quick start, feature list
2. Topic files — detailed knowledge, loaded on demand
3. Reference docs — deep material, loaded only when needed

**Loading mechanism**:

- `KAIZEN.md` is ALWAYS loaded (like CLAUDE.md)
- Skills load when: (a) user invokes skill command, (b) agent requests skill, (c) hook injects skill context
- Skills are context — they go into the system prompt, not executed as code

### Layer 3: Guardrails → `.kaizen/rules/` + `.kaizen/hooks/`

**Mapping**: `.claude/rules/` → `.kaizen/rules/`, `scripts/hooks/` → `.kaizen/hooks/`

```
.kaizen/rules/
├── builtin/                   # Ships with kz (safety-critical, cannot be disabled)
│   ├── security.md            # No hardcoded secrets, input validation
│   └── destructive-commands.md # Blocked commands list
├── project/                   # User-created for this project
│   └── [project-specific rules]
└── user/                      # User-global rules (~/.kaizen/rules/)
    └── [personal coding standards]

.kaizen/hooks/
├── builtin/                   # Ships with kz (safety-critical)
│   ├── anti-amnesia.py        # Injects rules every turn (CRITICAL)
│   ├── destructive-guard.py   # Blocks rm -rf, force push, etc.
│   └── session-bookend.py     # SessionStart + SessionEnd logging
├── project/                   # User-created hooks
│   └── [custom enforcement]
└── user/                      # User-global hooks
    └── [personal guards]
```

**The anti-amnesia hook** (most critical mechanism):

```python
# .kaizen/hooks/builtin/anti-amnesia.py
# Fires on EVERY UserPromptSubmit
# Injects: active rules summary + workspace state + learned instincts
# This is the PRIMARY way rules survive context compression
```

**Rule scoping** (from COC analysis):

```markdown
---
name: sql-safety
scope: ["src/db/**", "src/infrastructure/**"]
---

# Only loaded when editing files matching scope patterns
```

**Progressive disclosure**:

- **Driver**: Built-in rules and hooks active by default. User never touches them.
- **Tuner**: User adds project rules in `.kaizen/rules/project/`. Adds project hooks in `.kaizen/hooks/project/`.
- **Mechanic**: User can extend (but NOT disable) safety-critical built-in rules. Can add middleware to the pipeline.

**Safety-critical distinction**:

```toml
# .kaizen/settings.toml

# User CAN disable these (configurable):
[middleware]
budget_checker = false          # Subscription user, doesn't need it
token_estimator = false         # Trusts the model's own limits
cost_display = false            # Doesn't want cost in output

# User CANNOT disable these without explicit safety override:
[middleware]
destructive_command_guard = false  # ERROR: requires safety_override
tool_permission_checker = false    # ERROR: requires safety_override
kaizen_md_trust = false            # ERROR: requires safety_override

# Explicit override (mechanic-level):
[middleware.overrides]
safety_override = "I accept full responsibility for disabling safety guards"
destructive_command_guard = false  # NOW allowed
```

### Layer 4: Instructions → `.kaizen/commands/` + workspaces

**Mapping**: `.claude/commands/` → `.kaizen/commands/`

```
.kaizen/commands/
├── builtin/                   # Ships with kz
│   ├── analyze.md             # Phase 01: Research + red team
│   ├── todos.md               # Phase 02: Task breakdown (structural gate)
│   ├── implement.md           # Phase 03: TDD + review
│   ├── redteam.md             # Phase 04: Validation
│   ├── codify.md              # Phase 05: Knowledge capture (structural gate)
│   ├── ws.md                  # Workspace status
│   └── wrapup.md              # Session notes
├── project/                   # User-created commands
│   └── [domain workflows]
└── user/                      # User-global commands
    └── [personal workflows]
```

**Workspace system** (from COC analysis):

```
workspaces/
├── _template/                 # Copy to start new workspace
│   ├── briefs/                # User writes here (ONLY user input surface)
│   ├── 01-analysis/           # Agent output: research
│   ├── 02-plans/              # Agent output: plans
│   ├── 03-user-flows/         # Agent output: user storyboards
│   ├── 04-validate/           # Agent output: red team results
│   └── todos/                 # Task tracking (active/, completed/)
└── my-project/                # Active workspace
```

**Progressive disclosure**:

- **Driver**: Uses built-in commands (`/analyze`, `/implement`). Workspaces auto-detected.
- **Tuner**: Creates custom commands for domain-specific workflows. Customizes workspace structure.
- **Mechanic**: Defines agent teams in command frontmatter. Defines quality gates. Writes workspace-aware hooks.

### Layer 5: Learning → `.kaizen/learning/`

**Mapping**: `.claude/learning/` → `.kaizen/learning/`

```
.kaizen/learning/
├── observations/              # Per-session observations (auto-captured)
├── instincts/                 # High-confidence patterns
├── checkpoints/               # Periodic state snapshots
└── evolved/                   # Graduated to skills/agents/rules
    ├── agents/
    ├── skills/
    └── rules/
```

**Auto-capture**: PostToolUse hook logs patterns (file types, tool success/failure, common operations). SessionEnd analyzes patterns and forms instincts. Next session reads instincts via anti-amnesia hook.

**Progressive disclosure**:

- **Driver**: Learning happens automatically. Next session is smarter.
- **Tuner**: `/memory` command to review and manage learned patterns.
- **Mechanic**: Custom learning pipelines, pattern extractors, skill generators.

---

## The Configurable Middleware Pipeline

The agent loop is NOT a fixed sequence. It's a **configurable pipeline** where every component is a middleware that can be enabled, disabled, or replaced.

```python
# Default pipeline (all middleware active)
DEFAULT_PIPELINE = [
    # Session lifecycle
    SessionStartMiddleware,          # Always: init session, load config
    KaizenMdLoader,                  # Always: load project instructions
    AntiAmnesiaInjector,             # Always: inject rules every turn

    # Pre-model
    HookDispatcher("UserPromptSubmit"),  # Always: user hooks
    HookDispatcher("PreModel"),          # Always: pre-model hooks
    TokenEstimator,                      # Default ON, disable for subscription
    BudgetPreChecker,                    # Default ON, disable for subscription

    # Model call
    StreamingLLMCall,                    # Core: cannot be disabled

    # Post-model
    HookDispatcher("PostModel"),         # Always: post-model hooks
    CostRecorder,                        # Default ON

    # Tool execution (per tool call)
    HookDispatcher("PreToolUse"),        # Always: tool hooks
    ToolPermissionChecker,               # Safety-critical: requires override to disable
    EnvelopeChecker,                     # Active when PACT config present
    DestructiveCommandGuard,             # Safety-critical: requires override to disable
    ToolExecutor,                        # Core: cannot be disabled
    ToolResultTruncator,                 # Default ON, configurable threshold
    HookDispatcher("PostToolUse"),       # Always: post-tool hooks

    # Turn completion
    TurnPersister,                       # Always: save to session JSONL
    LearningObserver,                    # Default ON: log patterns
    HookDispatcher("PostTurn"),          # Always: post-turn hooks
]
```

**Middleware categories**:

| Category                | Can Disable?                            | Examples                                                            |
| ----------------------- | --------------------------------------- | ------------------------------------------------------------------- |
| **Core**                | No — required for operation             | StreamingLLMCall, ToolExecutor, SessionStart                        |
| **Safety-Critical**     | Only with explicit safety override      | ToolPermissionChecker, DestructiveCommandGuard, KaizenMdTrust       |
| **Hook Infrastructure** | No — hooks themselves decide what to do | HookDispatcher (all events)                                         |
| **Configurable**        | Yes — via settings.toml or KAIZEN.md    | BudgetPreChecker, TokenEstimator, CostRecorder, ToolResultTruncator |
| **Conditional**         | Auto-enabled when config present        | EnvelopeChecker (needs PACT config), LearningObserver               |
| **Custom**              | User-added via .kaizen/middleware/      | AuditMiddleware, ComplianceMiddleware, etc.                         |

**Configuration in KAIZEN.md**:

```markdown
# KAIZEN.md

## Model

model: claude-sonnet-4-6
fallback_model: ollama/llama3 # Use local when cloud unavailable

## Middleware

budget_checker: false # Subscription plan
cost_display: true # Show cost per turn
tool_result_truncation: 8000 # Tokens (default)

## Agents

default_reviewer: builtin/reviewer
default_security: builtin/security

## Rules

additional_rules:

- .kaizen/rules/project/no-console-log.md
- .kaizen/rules/project/api-conventions.md
```

---

## The Complete .kaizen/ Directory Structure

```
.kaizen/
├── settings.toml              # Configuration (permissions, middleware, providers)
├── agents/
│   ├── builtin/               # Ships with kz (5 core agents)
│   ├── project/               # User project agents
│   └── user/                  # User global agents (~/.kaizen/agents/)
├── skills/
│   ├── builtin/               # Ships with kz (COC + Kailash reference)
│   ├── project/               # User project skills
│   └── user/                  # User global skills
├── rules/
│   ├── builtin/               # Ships with kz (safety rules, cannot disable)
│   ├── project/               # User project rules
│   └── user/                  # User global rules
├── hooks/
│   ├── builtin/               # Ships with kz (anti-amnesia, guards)
│   ├── project/               # User project hooks
│   └── user/                  # User global hooks
├── commands/
│   ├── builtin/               # Ships with kz (7 phase commands)
│   ├── project/               # User project commands
│   └── user/                  # User global commands
├── learning/
│   ├── observations/          # Auto-captured patterns
│   ├── instincts/             # High-confidence patterns
│   └── checkpoints/           # State snapshots
├── middleware/
│   └── [custom middleware modules]
└── sessions/
    └── [session transcripts]
```

**Three-tier precedence** (matching Claude Code's model):

1. **Builtin** (ships with kz) — always loaded, safety-critical cannot be overridden
2. **Project** (`.kaizen/` in project root) — project-specific customizations
3. **User** (`~/.kaizen/`) — personal preferences, cross-project

Project overrides user. Builtin safety cannot be overridden (without explicit safety_override).

---

## Mapping: Claude Code COC → kz COC

| Claude Code                       | kz                                                    | Notes                       |
| --------------------------------- | ----------------------------------------------------- | --------------------------- |
| `.claude/agents/*.md`             | `.kaizen/agents/{builtin,project,user}/*.md`          | Three-tier instead of flat  |
| `.claude/skills/NN-name/SKILL.md` | `.kaizen/skills/{builtin,project,user}/name/SKILL.md` | Same progressive disclosure |
| `.claude/rules/*.md`              | `.kaizen/rules/{builtin,project,user}/*.md`           | Same path-scoped loading    |
| `settings.json` hooks config      | `.kaizen/settings.toml` + `.kaizen/hooks/`            | TOML instead of JSON        |
| `scripts/hooks/*.js`              | `.kaizen/hooks/{builtin,project,user}/*.py`           | Python instead of JS        |
| `.claude/commands/*.md`           | `.kaizen/commands/{builtin,project,user}/*.md`        | Same markdown+frontmatter   |
| `.claude/learning/`               | `.kaizen/learning/`                                   | Same observation pipeline   |
| `.claude/memory/`                 | `.kaizen/memory/`                                     | Same auto-memory            |
| `CLAUDE.md`                       | `KAIZEN.md`                                           | Same hierarchical loading   |
| `workspaces/`                     | `workspaces/`                                         | Same structure              |
| `user-prompt-rules-reminder.js`   | `.kaizen/hooks/builtin/anti-amnesia.py`               | THE critical mechanism      |

---

## What kz Adds That Claude Code Cannot

| Capability                       | Claude Code                       | kz                                              |
| -------------------------------- | --------------------------------- | ----------------------------------------------- |
| **Model-agnostic agents**        | Claude only                       | Any provider (Claude, OpenAI, Gemini, Ollama)   |
| **Per-agent model selection**    | Limited (`model:` in frontmatter) | Full tier system with fallback chains           |
| **Configurable middleware**      | Fixed pipeline                    | Pluggable middleware, disable/add/replace       |
| **PACT governance**              | None                              | 5-dimensional envelope per agent                |
| **Three-tier customization**     | Flat directory                    | builtin/project/user precedence                 |
| **Safety override transparency** | Opaque binary decisions           | Explicit `safety_override` with acknowledgment  |
| **Local model support**          | None                              | Ollama first-class (zero cost, offline)         |
| **Cross-model sessions**         | Cannot switch mid-session         | Switch model mid-session, context preserved     |
| **Custom middleware**            | Cannot modify pipeline            | `.kaizen/middleware/` for enterprise extensions |
