---
type: CONVERGENCE-STATUS
status: NOT-CONVERGED
round: 2
session: 2026-05-27 (/autonomize + /redteam, combined 2.27.0 pre-release: from_brief #1125 + delegate #1035)
branch: release/v2.27.0
head: 6f536561b (working-tree fixes uncommitted)
verdict: NOT CONVERGED — 1 open CRITICAL (CRITICAL-2) requires a user design decision
---

# /redteam Round 2 — Convergence Status (combined 2.27.0 pre-release)

**NOT CONVERGED.** Round 1's findings are all fixed + independently verified, but Round 2
surfaced a NEW CRITICAL (CRITICAL-2) whose robust fix is a design decision the co-owner must make.

## Round 1 findings — ALL FIXED + verified closed by construction (R2 reviewer: CONVERGED)

Receipts: `R1-combined-reviewer.md`, `R1-combined-security.md`, `R2-combined-reviewer.md`
(reviewer task `a31824a71ff098aff`), `R2-combined-security.md` (security-reviewer task
`a40fc1263983cf7f9`).

| ID          | Finding                                                                                                                                               | Fix                                                                                                                                       | R2 verification                                                                                                            |
| ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| CRITICAL-1  | from_brief workflow allowlist/denylist a structural no-op (`validate_plan` reads top-level `node_type`; `WorkflowPlan` nests them in `plan.nodes[i]`) | `_realize` enforces denylist floor + allowlist at the add_node choke point; `workflow_from_brief` subtracts denylist from caller override | CLOSED — by-construction (PythonCodeNode rejected via `_realize` AND full `workflow_from_brief` w/ stubbed malicious plan) |
| HIGH-1      | SEC-1 "regression" test asserted denylist CONSTANT, not enforcement                                                                                   | 5 behavioral tests (plan-containing-node → raises), revert-sensitive                                                                      | CLOSED                                                                                                                     |
| MED-1 (sec) | NaN confidence-gate bypass (IEEE-754)                                                                                                                 | `math.isfinite` in `check_confidence` + `allow_inf_nan=False` on `BriefPlan`                                                              | CLOSED — both layers reject NaN/±inf                                                                                       |
| MED-2 (rev) | caller `allowed_node_types` override drops denylist                                                                                                   | denylist enforced unconditionally at realizer floor                                                                                       | CLOSED                                                                                                                     |
| MED-1 (rev) | stale `kailash.bootstrap.bootstrap` dotted-path comment                                                                                               | comment corrected                                                                                                                         | CLOSED                                                                                                                     |
| MED-3 (rev) | dispatch.py non-constructible Set-of-Mapping docstring                                                                                                | docstring softened (frozenset-of-frozenset is the real case)                                                                              | CLOSED                                                                                                                     |
| MED-3 (sec) | M1 consume-lock thread caveat undocumented                                                                                                            | inline caveat added at `runtime.py:1066-1075`                                                                                             | CLOSED                                                                                                                     |
| LOW-1 (rev) | silent `except ImportError: pass` on core-submodule warming                                                                                           | WARN-log loop                                                                                                                             | CLOSED                                                                                                                     |

R2 fresh-adversarial: no string-normalization/homoglyph/case bypass; mechanical sweeps clean;
573 passed / 1 skipped / 0 warnings under `-W error`; full collection 18188 / 0 errors.

## NEW — CRITICAL-2: the node-type denylist is structurally unsound (release-blocking)

**The from_brief allowlist = `all registered nodes − {PythonCodeNode, AsyncPythonCodeNode}`.**
At least 8 OTHER registered nodes execute config-supplied code/expressions and are
brief-reachable, so an LLM brief (or prompt injection) can emit one with malicious config and
achieve code execution — bypassing the CRITICAL-1 fix entirely (which only enforces the
incomplete denylist).

Confirmed exec/eval-of-config registered nodes NOT in the denylist:
`DataTransformer` (`exec(config["transformations"])`), `BatchProcessorNode`
(`exec(processing_code)`), `CodeValidationNode` / `WorkflowValidationNode` /
`ValidationTestSuiteExecutorNode` (`exec(config["code"])` — `CodeValidationNode` uses FULL
`__builtins__`, unsandboxed), `LoopNode` / `ConvergenceCheckerNode` /
`MultiCriteriaConvergenceNode` (`eval(config["expression"])`, `__builtins__:{}` — escapable).

**By-construction receipt:** `DataTransformer` (in allowlist: True) realized through the
NOW-FIXED `_realize` gate with code-bearing config → `BYPASS CONFIRMED` (realize-only; payload
not executed).

**Why a literal denylist cannot be the fix (proven):** the dangerous set cannot be reliably
auto-derived. Module-scope AST over-flags safe nodes (`FilterNode`/`Map`/`Sort` share
`processors.py` with `DataTransformer`); class-scope AST under-flags (`PythonCodeNode` execs via
the `CodeExecutor` helper, `python.py:199/495` — class-scope returns False). Any hand-maintained
frozenset drifts as new exec-capable nodes are added.

**Severity:** CRITICAL (same bug class + same precondition as CRITICAL-1 — brief emits node +
malicious config — confirmed by construction). The R2 security-reviewer marked it HIGH pending an
executed probe; the probe is now executed, raising it to CRITICAL-1 parity.

## Disposition — co-owner design decision required (release BLOCKED)

The robust fix is a security-model decision with product-scope implications; surfaced to the
co-owner per `recommendation-quality.md` + `autonomous-execution.md` structural-gate model.
See the session recommendation. CRITICAL-1 fix stands regardless of the chosen model.
