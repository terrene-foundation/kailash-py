# Full Demo Audit — Combined Technical + Value QA

Orchestrates a complete demo audit in two phases: technical QA (does it work?) followed by value QA (does it sell?). Run this before any enterprise demo to catch both broken functionality and broken narrative.

## When to Use

- Before any scheduled demo or investor meeting
- After deploying to staging with new features
- After seeding demo data
- As a final gate before marking a sprint "demo-ready"

## Orchestration Pattern

### Phase 1: Technical Foundation (e2e-runner)

Verify the product works. No point auditing the value story if pages crash.

**Launch as**: Task with `subagent_type: "e2e-runner"`

**Prompt template**:

```
Run a technical QA sweep of the Agentic OS demo on [URL].

Login: [email] / [password]

For each page in the demo flow, verify:
1. Page loads without errors (check console)
2. All interactive elements are clickable
3. Navigation links go to correct destinations
4. Data loads (API calls succeed, no 500s)
5. No JavaScript errors in console

Demo flow pages (in order):
- /login → /enterprise-app (home)
- /organization-builder
- /shadow-agents → click View Details on an agent
- /trust → click "Establish Trust" → verify navigation → back → click "View Audit Trail" → verify navigation
- /knowledge
- /directives
- /bridges
- /users → click dropdown on a user → verify View Agent navigation
- /dashboard
- /govern/compliance
- /govern/audit-trail
- /metrics
- /settings
- /roles
- /policies
- /billing
- /agentic/inbox
- /agentic/sessions
- /api-keys

Output a pass/fail table:
| Page | Loads | Console Errors | Links Work | Data Present |
```

**Success criteria**: All pages load, 0 console errors, all navigation links work.

**If Phase 1 fails**: Fix technical issues before proceeding to Phase 2. Value audit on a broken product wastes time.

### Phase 2: Value Audit (value-auditor)

Evaluate the story the working product tells.

**Launch as**: Task with `subagent_type: "general-purpose"` referencing the value-auditor agent

**Prompt template**:

```
You are the value-auditor agent. Read your full methodology from:
- .claude/agents/value-auditor.md (agent identity and Five Questions)
- .claude/skills/24-value-audit/value-audit-methodology.md (evaluation framework)
- .claude/skills/24-value-audit/demo-readiness-checklist.md (pass/fail criteria)
- .claude/skills/24-value-audit/value-flow-patterns.md (flow patterns and anti-patterns)

Run a complete value audit on [URL] using Playwright MCP.

Login: [email] / [password]

Follow the 5-phase audit methodology:
1. First Impression (home page gut reaction)
2. Value Chain Walk (trace Design → Deploy → Work → Oversight)
3. Skeptical Deep Dive (interrogate top 3 value pages)
4. Cross-Cutting Analysis (systemic patterns)
5. Verdict (executive summary + severity table)

Output the full Value Audit Report to:
workspaces/axis/04-storyboard-audit/[filename].md
```

### Phase 3: Combined Report

After both phases complete, synthesize into a single demo readiness verdict.

**Template**:

```markdown
# Demo Readiness Report

**Date**: [date]
**Environment**: [URL]
**Verdict**: [READY | CONDITIONAL | NOT READY]

## Technical QA Summary

- Pages tested: [N]
- Pages passing: [N]
- Console errors: [N]
- Broken navigation: [list or "none"]
- **Technical verdict**: [PASS | FAIL]

## Value Audit Summary

- Executive finding: [one sentence]
- Critical issues: [N]
- High issues: [N]
- Highest-impact fix: [description]
- **Value verdict**: [COMPELLING | ADEQUATE | NOT READY]

## Combined Verdict

[READY]: Technical PASS + Value COMPELLING or ADEQUATE
[CONDITIONAL]: Technical PASS + Value NOT READY (demo possible with caveats)
[NOT READY]: Technical FAIL (fix before demoing)

## Priority Fixes Before Demo

1. [highest impact fix from either phase]
2. [second highest]
3. [third highest]
```

## MCP Access Note

**IMPORTANT**: The `value-auditor` and `e2e-runner` subagent types do NOT have Playwright MCP tool access. MCP tools (`browser_navigate`, `browser_snapshot`, etc.) are only available in the main conversation context.

**Workarounds**:

1. **Run from main context** (recommended) — Drive the audit directly from the main conversation using Playwright MCP tools, applying the value-auditor methodology manually.
2. **Use `general-purpose` subagent** — Launch with `subagent_type: "general-purpose"` which has access to all tools including MCP. Include the value-auditor identity and methodology in the prompt.
3. **Script approach** — The subagent can write a Playwright Node.js script via Bash, execute it, and analyze the captured output. Slower but works without MCP tools.

## Parallel vs Sequential

- **Phase 1 and Phase 2 MUST be sequential** — no point value-auditing a broken product
- **Within Phase 1**, page checks can run in parallel (batch navigate + snapshot)
- **Within Phase 2**, the audit is inherently sequential (follows the value flow)

## Quick Launch Commands

### Full audit (both phases):

```
Run a full demo audit on app.example.com.
Phase 1: Technical sweep with e2e-runner (all 26 pages, console errors, navigation).
Phase 2: Value audit with value-auditor (Five Questions, value flows, narrative coherence).
Login: ceo@tpc-test.com / [password]
Output reports to workspaces/axis/04-storyboard-audit/
```

### Value-only audit (skip technical):

```
Run a value audit on app.example.com using the value-auditor methodology.
Assume technical QA already passed.
Login: ceo@tpc-test.com / [password]
```

### Technical-only audit (skip value):

```
Run a technical QA sweep of app.example.com.
Check all 26 pages for console errors, broken links, and data loading.
Login: ceo@tpc-test.com / [password]
```

### Quick readiness check (checklist only):

```
Run the demo readiness checklist from .claude/skills/24-value-audit/demo-readiness-checklist.md
against app.example.com. Pass/fail only, no detailed audit.
Login: ceo@tpc-test.com / [password]
```
