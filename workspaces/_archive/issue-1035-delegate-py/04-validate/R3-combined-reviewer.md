# R3 Combined Reviewer — from_brief #1125 CRITICAL-2 closure (v2.27.0 pre-release)

**Verdict: `CONVERGED`** — CRITICAL-2 closed, default-deny verified real (not denylist in disguise), no new CRIT/HIGH. One LOW observation + two informational notes recorded below.

Scope: working-tree (uncommitted) fix in `src/kailash/workflow/from_brief.py` inverting the
node-type security model from denylist to a DEFAULT-DENY positive allowlist (`_SAFE_NODE_TYPES`),
plus new test `tests/unit/workflow/test_from_brief_safe_allowlist.py`. Verified by construction with
`python3` (editable kailash resolves to the working tree; kaizen 2.24.1). Probes + verbatim output below.

---

## Environment / provenance

- `python3 -c "import kailash.workflow.from_brief as m; print(m.__file__)"` →
  `/Users/esperie/repos/loom/kailash-py/src/kailash/workflow/from_brief.py` (working tree = file reviewed).
- `kailash.__version__` reports `2.26.2` on branch `release/v2.27.0`. Version anchor lags the branch
  name; out of scope for this security review, flagged for the release-prep step.
- HEAD (prior R2 state) `_registered_node_types()` returned
  `set(NodeRegistry.list_nodes().keys()) - _DANGEROUS_NODE_TYPES` (the proven-unsound denylist).
  Working tree `_safe_node_types()` returns `set(_SAFE_NODE_TYPES) & set(NodeRegistry.list_nodes().keys())`.

---

## PROBE 1 — CRITICAL-2 closed (dangerous nodes RAISE; legit nodes realize)

`_realize(plan_with(nt), _safe_node_types())`:

```
  DataTransformer               registered=True  -> RAISED BriefInterpretationError: ...denylisted because it executes arbitrar
  ConvergenceCheckerNode        registered=True  -> RAISED BriefInterpretationError
  MultiCriteriaConvergenceNode  registered=True  -> RAISED BriefInterpretationError
  WorkflowNode                  registered=True  -> RAISED BriefInterpretationError
  PythonCodeNode                registered=True  -> RAISED BriefInterpretationError
  CSVReaderNode  in_allowed=True  -> OK realized (WorkflowBuilder)
  FilterNode     in_allowed=True  -> OK realized (WorkflowBuilder)
  MergeNode      in_allowed=True  -> OK realized (WorkflowBuilder)
```

Full `workflow_from_brief` path (agent stubbed to emit a `DataTransformer`-with-code plan):

```
DataTransformer-with-code plan -> RAISED: node_type='DataTransformer' is denylisted because it executes arbitrary code (exec)...
legit CSVReader plan           -> OK: WorkflowBuilder
```

All five known code-exec/composition nodes are rejected at the `add_node` choke point; legit nodes pass.

## PROBE 2 — Default-deny is real (NOT a denylist in disguise)

```
_safe_node_types() == (_SAFE_NODE_TYPES & registry): True
total registered: 52 | safe-resolved: 45
registered-but-NOT-in-safe (7): AsyncPythonCodeNode, ConvergenceCheckerNode, DataTransformer,
  EventPublishNode, MultiCriteriaConvergenceNode, PythonCodeNode, WorkflowNode
  (6 in DANGEROUS floor; EventPublishNode is NOT in the floor yet still excluded by default-deny)
EventPublishNode via _realize -> RAISED (not in allowlist)
ZzHypotheticalNewNode (fake registered node) in _safe_node_types(): False
```

The decisive evidence that this is genuine default-deny, not a denylist: a brand-new registered node
(`ZzHypotheticalNewNode`) AND a real registered-but-unvetted node (`EventPublishNode`, NOT in the
floor) are both excluded. A newly-added SDK code-running node is unreachable until a human adds it to
`_SAFE_NODE_TYPES` — the exact failure mode the denylist could not prevent is closed.

## PROBE 3 — Inverse-completeness test is real + revert-sensitive

`tests/unit/workflow/test_from_brief_safe_allowlist.py`: **4 passed in 0.89s.**

Revert-sensitivity (in-memory set mutation, source untouched — re-ran the test's exact scoring body):

```
+ DataTransformer        -> offenders=['DataTransformer']        -> test would FAIL (revert-sensitive)
+ ConvergenceCheckerNode -> offenders=['ConvergenceCheckerNode'] -> test would FAIL (revert-sensitive)
+ PythonCodeNode         -> offenders=['PythonCodeNode']         -> test would FAIL (revert-sensitive)
+ WorkflowNode           -> offenders=[]                         -> test would STILL PASS  (gap — see LOW-1)
```

`test_no_safe_node_executes_config_code` is revert-sensitive for AST-detectable code-exec nodes
(`exec`/`eval`/`compile`/`CodeExecutor` reference). It is NOT sensitive to `WorkflowNode`
(composition bypass — its class source contains no `exec`/`eval`/`CodeExecutor`). See LOW-1; the gap
is mitigated by two independent layers (verified below), so it is not CRIT/HIGH.

## PROBE 4 — Safe-set curation spot-check (independent AST scan)

10 of the 45 members AST-scanned independently of the test helper — zero call `exec`/`eval`/`compile`
or reference `CodeExecutor`:

```
CSVReaderNode False | FilterNode False | Map False | Sort False | MergeNode False |
SwitchNode False | SQLDatabaseNode False | EmbeddingNode False | HierarchicalChunkerNode False | RedisNode False
```

No new finding. (All 45 are also covered mechanically by `test_no_safe_node_executes_config_code`,
which passed.)

## PROBE 5 — Regression + collection gate

```
python3 -m pytest tests/unit/workflow/ tests/unit/_from_brief/ tests/regression/from_brief/ \
  tests/unit/delegate/ tests/regression/test_issue_1035_delegate_*.py -W error -q
  => 900 passed, 1 skipped in 10.07s   (zero warnings under -W error)

pytest --collect-only -q (same paths) => exit 0, 901 tests collected
```

The 1 skip: `tests/unit/delegate/test_audit_engine.py:576` — documented cross-SDK byte-parity
vectors gap (delegate #1035; pinned-shape skip per `cross-sdk-inspection.md` Rule 4). Not
from_brief-related; not a security regression.

## PROBE 6 — Fresh adversarial sweep on the changed code

Mechanical sweeps on `from_brief.py`: no bare `except:` / `except: pass`; no `eval`/`exec`/`compile`/
`subprocess`/`os.system`/`shell=True`/`__import__` calls (one match is a comment at line 638); no
`TODO`/`FIXME`/`STUB`/`NotImplementedError`; no secrets/hardcoded models; no `print()`. The only
`.lower()` (line 468) is on the **model** string for provider inference, not on `node_type` — no
case-fold bypass surface on the allowlist.

Bypass-vector probes (all closed):

```
BYPASS A  caller-override allowed_node_types={PythonCodeNode,...} via entrypoint  -> RAISED (floor)
BYPASS A2 direct _realize(plan, allowed={dangerous}) for 4 nodes                  -> RAISED (floor) all 4
BYPASS B  node_type case/whitespace variants (pythoncodenode, PYTHONCODENODE,
          'PythonCodeNode ', 'CSVReaderNode\t', csvreadernode)                    -> RAISED all 5
```

- **Caller-override**: the unconditional `_DANGEROUS_NODE_TYPES` floor is enforced FIRST in `_realize`
  (and subtracted from any caller-supplied allowlist in the entrypoint), so a custom
  `allowed_node_types=` cannot re-admit a known code-exec node.
- **Case/normalization**: matching is exact-string against a case-sensitive registry; `pythoncodenode`
  ∉ registry (canonical `PythonCodeNode` ∈ registry), so a variant cannot resolve to a real dangerous
  node and is rejected by the allowlist gate regardless.
- **Augmented-brief listing**: advertises only `sorted(_safe_node_types())` (45 names); zero dangerous
  names leak to the LLM-facing vocabulary.
- Duplicate-`node_id` guard (`seen_ids`) survives in `_realize`.

---

## New findings

### LOW-1 — Inverse-completeness AST scan does not catch composition-bypass nodes (`WorkflowNode`)

`test_no_safe_node_executes_config_code` scans each safe-listed class's own source for
`exec`/`eval`/`compile`/`CodeExecutor`. `WorkflowNode` executes arbitrary code by NESTING a
sub-workflow (which could embed `PythonCodeNode`), not by a direct code-exec call in its own source —
so if a future edit added `WorkflowNode` (or any future composition-style node) to `_SAFE_NODE_TYPES`,
that single test would still pass (PROBE 3).

**Mitigated by two independent layers — verified by construction, so this stays LOW, not HIGH:**

1. Runtime floor: `_realize(plan, _safe_node_types() | {"WorkflowNode"})` still RAISES, because
   `WorkflowNode` is in the unconditional `_DANGEROUS_NODE_TYPES` floor (verified).
2. Disjointness test: `test_safe_allowlist_disjoint_from_denylist_floor` would FAIL the moment
   `WorkflowNode` (or any current floor member) is added to `_SAFE_NODE_TYPES` —
   `(_SAFE ∪ {WorkflowNode}) & _DANGEROUS = {WorkflowNode}` ≠ ∅ (verified).

Residual risk is narrow: a NEW composition/code-exec node that is BOTH AST-undetectable AND absent
from the floor. Default-deny already excludes it from brief-reachability (PROBE 2), so the only way it
becomes a hazard is a human explicitly adding it to `_SAFE_NODE_TYPES` without floor coverage — exactly
the human-review gate the model relies on. Optional hardening (defer-able, NOT release-blocking): add a
composition-class assertion to the inverse-completeness test (e.g. flag any safe member whose source
constructs a `WorkflowBuilder` / nests `WorkflowNode`), so the AST scan covers the composition vector
the floor currently backstops alone.

### INFO-1 — Floor entries unregistered in the warm-set are still listed (by design)

`BatchProcessorNode`, `CodeValidationNode`, `WorkflowValidationNode`, `ValidationTestSuiteExecutorNode`
are in `_DANGEROUS_NODE_TYPES` but not registered after the 4-submodule warm. This is intentional
defense-in-depth — the `NodeRegistry` is process-global and these may register via other imports; the
floor lists them so they're blocked if present. Matches the source comment. No action.

### INFO-2 — Warm-set surfaces 52 of the SDK's 140+ nodes

`_safe_node_types()` resolves 45/52 registered nodes after warming `data`/`transform`/`logic`/`code`.
AI/RAG/other nodes register via other imports and are not advertised, which is correct under
default-deny (only vetted-and-registered nodes are reachable). All 45 safe-set members are registered
(0 unregistered), so the LLM-facing list never advertises an unrealizable type. No action.

---

## Disposition

CRITICAL-2 (R2) is structurally closed: the code-execution boundary is now default-deny, proven real
against a hypothetical new node and a real unvetted registered node, with the dangerous-floor enforced
unconditionally at the realization choke point against both the caller-override and case-variant
vectors. The inverse-completeness test is real and revert-sensitive for AST-detectable code-exec; the
one composition-bypass gap (LOW-1) is double-mitigated and not release-blocking. Regression suite is
green (900 passed / 1 documented skip, zero warnings under `-W error`); collection gate exits 0.
No new CRIT/HIGH. **CONVERGED.**
