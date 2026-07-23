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

- delegate.py: removed `signature`/`inner_agent` params + storage + docstrings + `.signature` property; fixed `core_agent` docstring (was wrongly claiming "user-provided inner_agent"). Runtime-verified: both params ABSENT from Delegate.**init**.
- test_delegate_facade.py: swept 4 param-enumeration tests + removed 2 signature-property tests; ADDED `test_removed_params_rejected` (TypeError guard) + `test_signature_property_removed` + `test_every_init_param_reaches_a_consumer` (structural AST completeness guard — #1927 AC#3). Guard teeth-verified against a synthetic stored-only param.
- CHANGELOG 0.11.7 entry (### Removed). Version bumped atomically: pyproject.toml + **init**.py → 0.11.7.
- 559 delegate unit tests pass; collateral grep clean (no other Delegate signature/inner_agent usage). Full unit suite running (bbejg2pfi).

## Redteam wave (durable — orchestration-launch-ledger MUST-1)

Commit c35df4cd8 (branch fix/kaizen-delegate-signature-inner-agent-1927). Diff materialized: redteam-cont14-diff.patch.

| track          | agent                        | scope                                                                 | status                                                                                                                                                    |
| -------------- | ---------------------------- | --------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| RT-reviewer R1 | reviewer (ad1c7d35)          | removal correctness / completeness / test quality / CHANGELOG+version | **DONE — CLEAN** (no BUG/INVEST-NOW; mutation-tested the AST guard; version consistency verified 4 locations; 2 INCREMENTAL notes)                        |
| RT-security R1 | security-reviewer (a7d55f0e) | security implications of removal + diff scrub                         | **DONE — SECURITY-NEUTRAL, 0 findings** (govt/envelope/is_mock gates intact; no secret exposure; AST guard trusted-input; CHANGELOG clean; genuinely ran) |
| RT-reviewer R2 | reviewer (ad68db4d)          | confirm hardened guard (AnnAssign) + re-confirm removal/version       | **DONE — CLEAN** (reproduced guard vs 6 synthetic cases, no false pos/neg; orphan-grep clean; version 0.11.7 all anchors; no new warnings; genuinely ran) |

**CONVERGENCE REACHED** — 2 consecutive clean rounds on BUG/INVEST-NOW (R1 reviewer+security, R2 reviewer); all 3 reviewers genuinely ran (evidence gate). Deferred INCREMENTAL (value-anchored, NOT blocking): AST guard tuple-target-store edge (`self._x, self._y = x, y` escapes `_is_pure_self_store`) — value-anchor = maximal future-proofing of the #1927 tripwire; NOT present in real Delegate.**init**, theoretical only; diminishing returns to chase further.

## Round 1 → round 2 delta

R1 CLEAN both reviewers (both genuinely ran — evidence gate satisfied). INCREMENTAL note #2 (AST guard didn't handle AnnAssign/transform-RHS stores) FIXED in warm context: added `_is_pure_self_store` helper + AnnAssign branch (commit 14392da83, test-only). Hardened guard mutation-verified to catch AnnAssign-stored no-op. INCREMENTAL note #1 (Rule-6a deprecation tension) = no action (reviewer + security-reviewer both agree hard removal is the correct Rule-6a exception for a never-worked zero-caller param). Production/security surface byte-identical since R1 → security not re-run (test-only delta).

## Remaining

- Full unit suite green confirm → commit → PR → redteam to convergence → merge → release 0.11.7 (build-repo-release discipline) → uv.lock sync.
- Cross-SDK (cross-sdk-inspection Rule 1): Delegate facade is a Python kaizen-agents construct; assess whether Rust SDK has equivalent no-op params — defer to wrapup (needs cross-repo authz, not self-authorizable).
