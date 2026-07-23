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

| track                | agent              | branch/scope                                               | status                                                                              |
| -------------------- | ------------------ | ---------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| INV-signature-feasib | Explore (a67b1cd7) | loop.py + adapters/ structured-output feasibility          | in-flight                                                                           |
| INV-inner-agent-arch | Explore (a6c09fd6) | wrapper stack / streaming model / inner_agent compat       | **DONE — REMOVE** (arch-incompatible w/ streaming; core_agent docstring also wrong) |
| INV-consumer-tests   | Explore (ac157d9)  | full signature=/inner_agent= consumer + test + doc surface | in-flight                                                                           |

## Decision so far

- **inner_agent → REMOVE.** run() streams from AgentLoop.run_turn (delegate.py:615), never invokes the wrapper stack; BaseAgent has no streaming interface (batch run/run_async→dict only); honoring it needs a degraded non-streaming branch forfeiting streaming/tool-events/budget/interrupt. adapter=/config=/loop already cover BYO-engine streaming-compatibly. ALSO fix core_agent docstring (:727) — same-class doc bug.
- **signature → PENDING** INV-signature-feasib.

## Disposition — DECIDED (user-ratified via AskUserQuestion 2026-07-23)

**REMOVE BOTH** signature + inner_agent (clean removal, no deprecation shim, per feedback_no_shims; framed as the #1927 bug fix since both were never-worked silent no-ops with zero callers). User selected "Remove both (Recommended)".

## Implementation (branch fix/kaizen-delegate-signature-inner-agent-1927)

- delegate.py: removed `signature`/`inner_agent` params + storage + docstrings + `.signature` property; fixed `core_agent` docstring (was wrongly claiming "user-provided inner_agent"). Runtime-verified: both params ABSENT from Delegate.__init__.
- test_delegate_facade.py: swept 4 param-enumeration tests + removed 2 signature-property tests; ADDED `test_removed_params_rejected` (TypeError guard) + `test_signature_property_removed` + `test_every_init_param_reaches_a_consumer` (structural AST completeness guard — #1927 AC#3). Guard teeth-verified against a synthetic stored-only param.
- CHANGELOG 0.11.7 entry (### Removed). Version bumped atomically: pyproject.toml + __init__.py → 0.11.7.
- 559 delegate unit tests pass; collateral grep clean (no other Delegate signature/inner_agent usage). Full unit suite running (bbejg2pfi).

## Remaining

- Full unit suite green confirm → commit → PR → redteam to convergence → merge → release 0.11.7 (build-repo-release discipline) → uv.lock sync.
- Cross-SDK (cross-sdk-inspection Rule 1): Delegate facade is a Python kaizen-agents construct; assess whether Rust SDK has equivalent no-op params — defer to wrapup (needs cross-repo authz, not self-authorizable).
