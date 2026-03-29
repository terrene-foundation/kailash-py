# CO Setup Architecture

## The Five Component Types

Every CO setup consists of five component types. Each maps to a specific CO layer.

```
┌─────────────────────────────────────────────────────────────┐
│                    YOUR NATURAL LANGUAGE                     │
│              "Build X" / "Analyze Y" / "Draft Z"            │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  COMMANDS (.claude/commands/)                    [CO L4]     │
│  Structured workflows with approval gates                   │
│  /analyze → /todos → /implement → /redteam → /codify        │
│  Plus: /ws, /wrapup, /checkpoint                            │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  SKILLS (.claude/skills/)                        [CO L2]     │
│  Distilled domain knowledge — the institutional handbook    │
│  Progressive disclosure: index → quick-ref → deep reference │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  AGENTS (.claude/agents/)                        [CO L1]     │
│  Specialized sub-processes with domain expertise            │
│  Deep knowledge + procedural directives                     │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  HOOKS (scripts/hooks/ + .claude/settings.json)  [CO L3]     │
│  Deterministic enforcement outside the AI's context         │
│  Anti-amnesia, validation, session lifecycle                │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  RULES (.claude/rules/)                          [CO L3]     │
│  Soft enforcement — constraints the AI reads and follows    │
│  Agents, security, git, no-stubs, learned-instincts         │
└─────────────────────────────────────────────────────────────┘
```

**Layer 5 (Learning)** spans all components — the `/codify` command captures patterns, the learning system logs observations, and instincts evolve into rules.

## Shared vs Project-Specific

### Always Shared (identical across all repos)

| Component | Files                                   | Purpose                                                            |
| --------- | --------------------------------------- | ------------------------------------------------------------------ |
| Commands  | `ws.md`, `wrapup.md`, `checkpoint.md`   | Utility — workspace status, session notes, learning checkpoints    |
| Commands  | `implement.md`, `codify.md`, `todos.md` | Core workflow — shared structure with project-specific agent teams |
| Rules     | `git.md`                                | Git workflow conventions                                           |
| Rules     | `learned-instincts.md`                  | Auto-generated from observations                                   |
| Guides    | `claude-code/`                          | How Claude Code works                                              |
| Guides    | `co-setup/`                             | This guide                                                         |

### Always Project-Specific

| Component                 | Why                                                                         |
| ------------------------- | --------------------------------------------------------------------------- |
| Commands: `start.md`      | Different orientation (product vs governance vs research)                   |
| Commands: `analyze.md`    | Different research frameworks (product-market fit vs governance precedents) |
| Commands: `redteam.md`    | Different testing (user flows vs adversarial governance vs security audit)  |
| Skills: `project/`        | Domain knowledge specific to the codebase/project                           |
| Agents: `project/`        | Specialists for the specific codebase/project                               |
| Hooks: `session-start.js` | Project type detection and context loading                                  |
| Hooks: `session-end.js`   | Project-specific metrics and state persistence                              |
| Rules: `security.md`      | Different security concerns (code vs documents)                             |

### Archetype-Specific

| Component | Coding Repos                                                                                         | Governance/Non-Coding                                                                                                           |
| --------- | ---------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Commands  | `deploy.md`, `test.md`, `api.md`, `db.md`, `sdk.md`, `ai.md`, `design.md`                            | `arxiv.md`, `publish.md`, `governance-layer.md`, `co-domain.md`                                                                 |
| Agents    | `tdd-implementer`, `testing-specialist`, `value-auditor`, `build-fix`, `framework-advisor`           | `constitution-expert`, `governance-layer-expert`, `publication-expert`, `care-platform-architect`                               |
| Agents    | `dataflow-specialist`, `nexus-specialist`, `kaizen-specialist`, `mcp-specialist`                     | `care-implementation-expert`, `co-domain-expert`                                                                                |
| Agents    | `uiux-designer`, `react-specialist`, `flutter-specialist`, `frontend-developer`, `ai-ux-designer`    | —                                                                                                                               |
| Skills    | SDK-specific (01-25)                                                                                 | Standards reference (26-34)                                                                                                     |
| Rules     | `no-stubs.md` (strict MUST), `agents.md` (MANDATORY), `testing.md`, `patterns.md`, `e2e-god-mode.md` | `no-stubs.md` (soft RECOMMENDED), `agents.md` (RECOMMENDED), `constitution.md`, `publication-quality.md`, `arxiv-submission.md` |
| Hooks     | `validate-workflow.js`, `validate-deployment.js`                                                     | `validate-arxiv-content.js`, `validate-publication-content.js`                                                                  |

### Shared Across Both Archetypes

| Component | Files                                                                                                                                      |
| --------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| Agents    | `deep-analyst`, `requirements-analyst`, `intermediate-reviewer`, `gold-standards-validator`, `security-reviewer`, `open-source-strategist` |
| Agents    | `care-expert`, `eatp-expert`, `co-expert`, `coc-expert`                                                                                    |
| Agents    | `todo-manager`, `gh-manager`, `git-release-specialist`                                                                                     |
| Hooks     | `validate-bash-command.js`, `user-prompt-rules-reminder.js`, `pre-compact.js`                                                              |
| Rules     | `git.md`, `learned-instincts.md`                                                                                                           |

## Component Interaction Model

```
Request: "Create a user registration API"

1. COMMAND PHASE
   └── User runs /implement (or just asks)
   └── Command loads workspace context and picks next todo

2. SKILL PHASE
   └── Agent reads relevant skills (DataFlow, Nexus)
   └── Gets: patterns, gotchas, canonical approaches

3. AGENT PHASE
   └── Claude delegates to specialists
   └── Gets: deep expertise, validated patterns

4. WRITING PHASE
   └── Claude writes code/docs
   └── HOOK FIRES: validate-workflow.js checks output
   └── RULE APPLIED: no-stubs.md prevents placeholders

5. REVIEW PHASE
   └── Claude delegates to intermediate-reviewer
   └── RULE APPLIED: agents.md requires code review

6. COMMIT PHASE
   └── Claude delegates to security-reviewer
   └── Only after passing: offers to commit
```

## The Information Hierarchy

```
         ┌─────────────┐
         │  Commands   │  ← Quick access, workflow structure (10-50 lines)
         └──────┬──────┘
                │
         ┌──────▼──────┐
         │   Skills    │  ← Distilled knowledge, patterns (50-250 lines)
         └──────┬──────┘
                │
         ┌──────▼──────┐
         │   Agents    │  ← Deep expertise, procedural (100-300 lines)
         └──────┬──────┘
                │
         ┌──────▼──────┐
         │ Full Docs   │  ← Complete reference (unlimited)
         └─────────────┘
```

Each level loads only what's needed. For simple tasks, skills are enough. For complex tasks, agents are consulted. Full documentation is referenced only when necessary.
