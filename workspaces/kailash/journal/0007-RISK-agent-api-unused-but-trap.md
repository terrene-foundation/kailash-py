---
type: RISK
date: 2026-03-30
project: kailash
topic: Agent API has zero adoption but remains a trap for new users following docs
phase: analyze
tags: [kaizen, agent-api, delegate, risk, red-team]
---

# Risk: Agent API is Unused but Remains a Trap

## Finding

Red team of the engine deficiency analysis revealed that **zero downstream projects** use the broken Agent API. All consumers use Delegate, GovernedSupervisor, or BaseAgent directly:

- kaizen-cli-py: Delegate + GovernedSupervisor
- Arbor: Delegate (via \_KaizenCompatMixin shim, now deprecated)
- Pact: GovernedSupervisor
- ImpactVerse: Delegate (after discovering Agent was broken)
- TPC Treasury, Aegis, Aerith, Aether: BaseAgent or Delegate

## Why This Is Still a Risk

The Agent API is documented in `patterns.md` (6 lines) and accepts tools silently. A new user following the quick-start path will:

1. Find `Agent(model="gpt-4", tools=[...])` in patterns.md
2. Deploy it
3. Believe it works (BUG-2 fabricates success)
4. Discover tools don't work only when testing real behavior
5. Lose trust in the SDK

## Impact on Priority

This finding changes the priority from "P0 fix bugs" to "P0 decide Agent's future."
The bugs have zero production impact today, but the COC teaching path
actively routes new users toward either BaseAgent (60-line overhead) or
Agent (broken). Both are wrong — Delegate (2 lines, works) should be first.

## Recommendation

Deprecate Agent API (Option B). The code structure strongly favors this:

- Delegate already handles all Agent use cases correctly
- GovernedSupervisor composes with Delegate patterns, not Agent
- Agent is 760 lines of broken code duplicating working Delegate functionality
