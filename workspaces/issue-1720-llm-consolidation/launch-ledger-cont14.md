# Launch Ledger — cont-14 (2026-07-22) — #1927 Delegate signature/inner_agent design shard

Durable orchestration ledger per `orchestration-launch-ledger.md` MUST-1. Consult BEFORE every spawn; match every completion against it.

## Objective

User: "continue from last session, /autonomize with as many parallelized workflows as possible and /redteam to convergence."

Forest has ONE real item: **#1927** (F3) — `Delegate(signature=…)` / `Delegate(inner_agent=…)` documented-but-silent-no-op (bug-labeled, independently confirmed cont-13 R2). Design shard now prioritized via /autonomize.

Ground truth at start (verified live): main @ `dd0064479`, 0 open PRs, #1927 the only open issue. Both no-ops CONFIRMED at HEAD:
- `inner_agent` (delegate.py:367→383 stored, never read; L458 always builds `_LoopAgent`)
- `signature` (delegate.py:356→380 stored + getter L735; `_LoopAgent.__init__` L203 hardcodes `_DelegateSignature()`; `run()` L615 streams raw text from `self._loop`, bypassing BaseAgent signature path)

Consumer surface (grep): only delegate.py references the Delegate-specific params; NO codebase caller passes `signature=`/`inner_agent=` to a Delegate. Deprecation surface is bounded.

## Wave tracker (durable)

| track                | agent                       | branch/scope                                              | status |
| -------------------- | --------------------------- | -------------------------------------------------------- | ------ |
| INV-signature-feasib | Explore (investigation)     | loop.py + adapters/ structured-output feasibility        | spawned |
| INV-inner-agent-arch | Explore (investigation)     | wrapper stack / streaming model / inner_agent compat     | spawned |
| INV-consumer-tests   | Explore (investigation)     | full signature=/inner_agent= consumer + test + doc surface | spawned |

## Disposition (to be decided post-investigation, per /autonomize)

Issue #1927 recommends: signature→WIRE, inner_agent→REMOVE(deprecation). Validate against architecture evidence before committing.
