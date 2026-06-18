# R2 Combined Reviewer — v2.27.0 (from_brief #1125 + delegate #1035)

CONVERGED — 0 CRIT / 0 HIGH. All 5 R1 findings verified closed by construction; no new CRIT/HIGH introduced by the fixes.

Round: 2 (independent re-verification of R1 fixes + fresh adversarial)
Branch: release/v2.27.0 (working tree, uncommitted)
Interpreter: .venv/bin/python 3.13.7; kaizen 2.24.1; editable kailash
Method: Bash verify-by-construction (R1's static-only pass missed a no-op; every claim below is backed by a run).

---

## R1 findings — closure verification

### CRITICAL-1 (allowlist no-op on workflow surface) — CLOSED

`_realize` (src/kailash/workflow/from_brief.py:492-559) now enforces, in the per-node loop BEFORE `builder.add_node` (line 555): (a) unconditional `_DANGEROUS_NODE_TYPES` denylist floor (lines 538-544), (b) `validate_node_type(spec["node_type"], allowed_node_types)` (line 548). `_registered_node_types()` subtracts the denylist (line 329); `workflow_from_brief` subtracts it from caller-supplied allowlists too (line 642).

Verification — `_realize` path (build a WorkflowPlan whose plan.nodes contains a code-exec node, confirm RAISES):

```
=== CRITICAL-1: _realize(plan with PythonCodeNode, registered) ===
RESULT: RAISED BriefInterpretationError; unknown_value='PythonCodeNode'
=== AsyncPythonCodeNode ===
RESULT: RAISED; unknown_value='AsyncPythonCodeNode'
=== Legitimate node CSVReaderNode realizes ===
RESULT: realized OK; nodes=['n']
=== Hallucinated unknown node ===
RESULT: RAISED; unknown_value='TotallyFakeInjectedNode'
```

Verification — full `workflow_from_brief` path (agent stubbed to emit a malicious PythonCodeNode plan with real `os.system` code, confirms `_realize` is the choke point even when the LLM hallucinates past the augmented-brief allowlist):

```
=== FULL PATH: LLM emits PythonCodeNode despite allowlist in brief ===
RESULT: RAISED BriefInterpretationError; unknown_value='PythonCodeNode'
=== FULL PATH: legitimate plan realizes end-to-end ===
RESULT: realized OK; nodes=['r']
```

### MEDIUM-2 (caller allowlist re-admits denylisted node) — CLOSED

Denylist enforced unconditionally (independent of `allowed_node_types`); caller override cannot re-admit.

```
=== MEDIUM-2: caller allowlist {'PythonCodeNode'} cannot re-admit ===  (_realize path)
RESULT: RAISED; unknown_value='PythonCodeNode'
=== FULL PATH: caller passes allowed_node_types={'PythonCodeNode','CSVReaderNode'} ===
RESULT: RAISED; unknown_value='PythonCodeNode'
```

### HIGH-1 (test checked constant, not enforcement) — CLOSED

The 4 named tests in tests/unit/workflow/test_from_brief_realizer.py are real behavioral assertions (construct a plan via `coerce_plan`, assert `_realize` raises with `exc.value.unknown_value == dangerous`). The prior constant-only test (`test_workflow_from_brief_denylist_constant_excludes_code_nodes`, line 350) is explicitly re-labeled a data-structure check with behavioral enforcement delegated to the new tests.

Run (6 cases after parametrization):

```
tests/unit/workflow/test_from_brief_realizer.py
::test_realize_rejects_denylisted_code_execution_node[PythonCodeNode]
::test_realize_rejects_denylisted_code_execution_node[AsyncPythonCodeNode]
::test_realize_denylist_is_a_floor_caller_override_cannot_readmit[PythonCodeNode]
::test_realize_denylist_is_a_floor_caller_override_cannot_readmit[AsyncPythonCodeNode]
::test_realize_rejects_hallucinated_unknown_node
::test_realize_accepts_legitimate_registered_node
6 passed, 22 deselected in 0.51s
```

Revert-sensitivity (proven by construction, not reasoning): a pre-fix realizer (per-node loop calling `add_node` WITHOUT the denylist/allowlist gate), given a VALID `config={"code": "result = 1"}`:

```
PRE-FIX: PythonCodeNode REALIZED OK nodes=['n']  -> exec node would ship on revert
CURRENT fix: RAISED BriefInterpretationError uv='PythonCodeNode' (catches it BEFORE add_node)
```

The pre-fix path realizes the exec node; the current fix raises before `add_node`. The tests assert `pytest.raises(BriefInterpretationError)` and `WorkflowValidationError` is not a `BriefInterpretationError` subclass, so reverting the fix flips these tests from pass to fail/error. Confirmed revert-sensitive.

### MED-1 (stale bootstrap comment) — CLOSED

src/kailash/**init**.py comment now correctly states the dotted form `kailash.bootstrap.bootstrap` is NOT reachable. Comment matches runtime:

```
import kailash; kailash.bootstrap.bootstrap   -> AttributeError: 'function' object has no attribute 'bootstrap'
from kailash.bootstrap import bootstrap        -> import OK, callable: True
kailash.bootstrap                              -> type: function, callable: True
```

### MED-3 (dispatch docstring) — CLOSED

src/kailash/delegate/dispatch.py `_check_payload_depth` docstring (lines ~120-132) now states Set-of-Mapping is non-constructible and frozenset-of-frozenset is the real case. Both claims verified by construction:

```
set-of-Mapping:        TypeError: unhashable type: 'dict'  (matches "not constructible")
frozenset-of-frozenset: RAISED DispatchValidationError at depth 32 (Set branch DOES walk nested frozensets)
```

### LOW-1 (silent swallow) — CLOSED

The `_registered_node_types()` warming loop now WARN-logs core-submodule ImportError (from_brief.py:314-318) instead of `except ImportError: pass`. No bare silent swallow remains:

```
314:        except ImportError as exc:
315:            logger.warning(  ...
```

---

## Fresh adversarial (NEW issues from the fixes) — none found

### String-normalization bypass — no bypass

All variants of a denylisted name rejected (the allowlist uses exact-name membership `name not in allowed` in src/kailash/\_from_brief/allowlist.py:51 — no `.lower()`/`.strip()`/normalization, so variant strings are simply not registered names and are rejected as unknown):

```
'pythoncodenode'        -> rejected (allowlist)
'PYTHONCODENODE'        -> rejected
' PythonCodeNode'       -> rejected   (leading ws)
'PythonCodeNode '       -> rejected   (trailing ws)
'PythonCodeNode\t'      -> rejected
'PythonCodeNode\n'      -> rejected
'PythonCodeNode​'  -> rejected   (zero-width space)
'PythonCodeNodе'        -> rejected   (cyrillic homoglyph)
''                      -> rejected   (caught earlier by _coerce_node_spec malformed=True)
'python_code_node'      -> rejected
```

### Registry alias-smuggle — no path

The NodeRegistry maps exactly two registered NAMES to PythonCode-class types (`PythonCodeNode`, `AsyncPythonCodeNode`), and both names ARE denylisted. No registered name whose class is a code-exec node exists outside the denylist; none such is present in the returned allowlist:

```
registered names whose class is *PythonCode*: [('AsyncPythonCodeNode','AsyncPythonCodeNode'),('PythonCodeNode','PythonCodeNode')]
alias-smuggle candidates (class dangerous but NAME not denylisted): []
...AND present in _registered_node_types() allowlist: []
```

An attacker cannot smuggle a dangerous node under a name the registry resolves to PythonCodeNode — the registry uses exact names and the denylist subtracts by the exact registered key.

### Mechanical sweeps on changed files — clean

Files swept: from_brief.py, **init**.py, dispatch.py, delegate/runtime.py, \_from_brief/confidence.py, \_from_brief/validator.py.

```
bare except: / except Exception: pass     -> (none)
raw eval/exec/shell=True/subprocess        -> (none in code; only docstring/comment refs to PythonCodeNode's exec)
TODO/FIXME/HACK/XXX/NotImplementedError    -> (none non-abstract)
hardcoded secrets / model strings          -> (none)
```

### Full test sweep — green, zero warnings under -W error

```
.venv/bin/python -m pytest \
  tests/unit/workflow/test_from_brief_realizer.py \
  tests/unit/_from_brief/ tests/regression/from_brief/ \
  tests/unit/delegate/ tests/regression/test_issue_1035_delegate_*.py -W error -q
573 passed, 1 skipped in 4.83s
```

The single skip is pre-existing and documented (tests/unit/delegate/test_audit_engine.py:576 — S7 cross-SDK byte-parity vendoring gap; names the gap, pins the assertion shape, greppable). Acceptable per test-skip-discipline; not introduced by these fixes. All 5 prescribed paths resolved to non-empty collections (28 / 75 / 1 / 445 / 25 tests; glob expanded to 4 real files).

---

## Notes for the record (non-findings)

- Empty-string `node_type` is rejected by `_coerce_node_spec` (malformed=True) BEFORE reaching the denylist/allowlist gate — defense-in-depth ordering is correct; the node never reaches `add_node` regardless.
- `validate_node_type` exact-name semantics are the structural reason no normalization bypass exists; if a future refactor adds case-folding/trimming to the allowlist membership it would re-open the variant surface — worth a structural-invariant note but NOT a finding today (current code is exact-match).
