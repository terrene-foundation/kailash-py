# COC Ecosystem Inventory

**Date**: 2026-03-11

---

## Overview

| Repo                     | Agents  | Skills (dirs) | Skill Files | Rules  | Commands | Hooks  | Current Sonnet              |
| ------------------------ | ------- | ------------- | ----------- | ------ | -------- | ------ | --------------------------- |
| Terrene Foundation       | 14      | 5             | 5           | 8      | 9        | 8      | 2 (git-release, gh-manager) |
| Kailash Python SDK BUILD | 23      | 28            | ~375        | 11     | 22       | 9      | 1 (git-release)             |
| Kailash Python USE       | 33      | 28            | ~375        | 11     | 22       | 9      | 2 (git-release, gh-manager) |
| Kailash Rust BUILD/USE   | 31      | 30            | ~342        | 11     | 21       | 7      | 2 (git-release, gh-manager) |
| **Total**                | **101** | **91**        | **~1,097**  | **41** | **74**   | **33** | **7**                       |

Currently only **7 out of 101 agents** (6.9%) use Sonnet. Everything else runs on Opus.

---

## 1. Terrene Foundation (Governance KB)

### Agents (14)

| Agent                    | Category              | Current Model |
| ------------------------ | --------------------- | ------------- |
| deep-analyst             | Deep reasoning        | opus          |
| requirements-analyst     | Analysis              | opus          |
| intermediate-reviewer    | Review                | opus          |
| gold-standards-validator | Compliance            | opus          |
| security-reviewer        | Security              | opus          |
| open-source-strategist   | Strategy              | opus          |
| care-expert              | Standards (read-only) | inherit       |
| eatp-expert              | Standards (read-only) | inherit       |
| co-expert                | Standards (read-only) | inherit       |
| coc-expert               | Standards (read-only) | inherit       |
| constitution-expert      | Standards (read-only) | inherit       |
| todo-manager             | Management            | opus          |
| gh-manager               | Management            | sonnet        |
| git-release-specialist   | Management            | sonnet        |

### Skills (5)

26-eatp-reference, 27-care-reference, 28-coc-reference, co-reference, 29-constitution-reference

### Rules (8)

agents, communication, constitution, git, learned-instincts, no-stubs, security, terrene-naming

### Commands (9)

analyze, checkpoint, codify, implement, redteam, start, todos, wrapup, ws

### Hooks (8)

PreToolUse (validate-bash-command), PreCompact, SessionStart, SessionEnd, UserPromptSubmit (rules-reminder), Stop, CI (run-all)

---

## 2. Kailash Python SDK BUILD

### Agents (23)

| Agent                    | Category         | Current Model |
| ------------------------ | ---------------- | ------------- |
| deep-analyst             | Deep reasoning   | opus          |
| requirements-analyst     | Analysis         | opus          |
| intermediate-reviewer    | Review           | opus          |
| gold-standards-validator | Compliance       | opus          |
| security-reviewer        | Security         | opus          |
| pattern-expert           | SDK patterns     | opus          |
| framework-advisor        | Architecture     | opus          |
| testing-specialist       | Testing strategy | opus          |
| tdd-implementer          | TDD              | opus          |
| documentation-validator  | Doc checking     | opus          |
| e2e-runner               | E2E execution    | opus          |
| build-fix                | Build errors     | opus          |
| deployment-specialist    | Deployment       | opus          |
| sdk-navigator            | Discovery        | opus          |
| value-auditor            | Demo audit       | opus          |
| dataflow-specialist      | Framework        | opus          |
| nexus-specialist         | Framework        | opus          |
| kaizen-specialist        | Framework        | opus          |
| mcp-specialist           | Framework        | opus          |
| frontend-developer       | Frontend         | opus          |
| react-specialist         | Frontend         | opus          |
| flutter-specialist       | Frontend         | opus          |
| git-release-specialist   | Management       | sonnet        |

### Skills (28 dirs, ~375 files)

01-core-sdk through 28-coc-reference (full SDK reference library)

### Rules (11)

agents, communication, deployment, e2e-god-mode, env-models, git, learned-instincts, no-stubs, patterns, security, testing

### Commands (22)

ai, analyze, api, checkpoint, codify, db, deploy, design, evolve, i-audit, i-harden, i-polish, implement, learn, redteam, sdk, start, test, todos, validate, wrapup, ws

### Hooks (9)

PreToolUse (validate-bash), PostToolUse (validate-workflow, validate-deployment, auto-format), SessionStart, SessionEnd, PreCompact, UserPromptSubmit, Stop

---

## 3. Kailash Python USE Template

### Agents (33)

Same 23 as Python SDK BUILD, plus:

| Agent               | Category              | Current Model |
| ------------------- | --------------------- | ------------- |
| uiux-designer       | Frontend/design       | opus          |
| ai-ux-designer      | AI interaction design | opus          |
| care-expert         | Standards (read-only) | inherit       |
| eatp-expert         | Standards (read-only) | inherit       |
| coc-expert          | Standards (read-only) | inherit       |
| todo-manager        | Management            | opus          |
| gh-manager          | Management            | sonnet        |
| + all 23 from BUILD | (same)                | (same)        |

### Skills (28 dirs, ~375 files)

Same as Python SDK BUILD + 26-eatp-reference, 27-care-reference, 28-coc-reference

### Rules (11), Commands (22), Hooks (9)

Same structure as Python SDK BUILD

---

## 4. Kailash Rust BUILD/USE Template

### Agents (31)

| Agent                    | Category              | Current Model |
| ------------------------ | --------------------- | ------------- |
| deep-analyst             | Deep reasoning        | opus          |
| requirements-analyst     | Analysis              | opus          |
| intermediate-reviewer    | Review                | opus          |
| gold-standards-validator | Compliance            | opus          |
| security-reviewer        | Security              | opus          |
| pattern-expert           | SDK patterns          | opus          |
| framework-advisor        | Architecture          | opus          |
| testing-specialist       | Testing strategy      | opus          |
| tdd-implementer          | TDD                   | opus          |
| documentation-validator  | Doc checking          | opus          |
| e2e-runner               | E2E execution         | opus          |
| build-fix                | Build errors          | opus          |
| deployment-specialist    | Deployment            | opus          |
| sdk-navigator            | Discovery             | opus          |
| value-auditor            | Demo audit            | opus          |
| dataflow-specialist      | Framework             | opus          |
| nexus-specialist         | Framework             | opus          |
| kaizen-specialist        | Framework             | opus          |
| mcp-specialist           | Framework             | opus          |
| frontend-developer       | Frontend              | opus          |
| react-specialist         | Frontend              | opus          |
| flutter-specialist       | Frontend              | opus          |
| uiux-designer            | Frontend/design       | opus          |
| ai-ux-designer           | AI interaction design | opus          |
| care-expert              | Standards (read-only) | inherit       |
| eatp-expert              | Standards (read-only) | inherit       |
| coc-expert               | Standards (read-only) | inherit       |
| todo-manager             | Management            | opus          |
| gh-manager               | Management            | sonnet        |
| git-release-specialist   | Management            | sonnet        |
| + remaining agents       | (various)             | opus          |

### Skills (30 dirs, ~342 files)

Full SDK reference library + standards references + Python bindings skill

### Rules (11), Commands (21), Hooks (7)

Similar structure to Python SDK BUILD (7 hooks vs 9 — fewer PostToolUse hooks)

---

## Agent Categories Across All Repos

| Category                      | Count | Description                                                              |
| ----------------------------- | ----- | ------------------------------------------------------------------------ |
| Deep reasoning / analysis     | 8     | deep-analyst, requirements-analyst, framework-advisor, pattern-expert    |
| Review / quality              | 12    | intermediate-reviewer, gold-standards-validator, documentation-validator |
| Security                      | 4     | security-reviewer                                                        |
| Testing                       | 12    | testing-specialist, tdd-implementer, e2e-runner                          |
| Standards experts (read-only) | 18    | care/eatp/co/coc/constitution experts                                    |
| Framework specialists         | 16    | dataflow/nexus/kaizen/mcp specialists                                    |
| Frontend                      | 20    | frontend-dev, react, flutter, uiux, ai-ux designers                      |
| Management                    | 12    | git-release, gh-manager, todo-manager                                    |
| Build/deploy                  | 8     | build-fix, deployment-specialist                                         |
| Strategy                      | 1     | open-source-strategist                                                   |
| Navigation                    | 4     | sdk-navigator                                                            |
| Audit                         | 4     | value-auditor                                                            |
