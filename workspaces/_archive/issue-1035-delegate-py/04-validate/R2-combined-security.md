# R2 — Combined Security Audit (from_brief #1125 + delegate #1035) — v2.27.0 pre-release

**Verdict: FINDINGS**

One NEW HIGH on the brief-injection → code-execution axis: the `_DANGEROUS_NODE_TYPES`
denylist is INCOMPLETE. The denylist-completeness re-derivation (the load-bearing R2
check) found ≥5 OTHER registered node types that execute config-supplied code through
`exec`/`eval` and are NOT in the denylist. The CRITICAL-1 fix correctly closed the
PythonCodeNode/AsyncPythonCodeNode path AND correctly placed the gate at the realization
choke point on BOTH surfaces — but it enumerated only two of the eight exec-capable
registered nodes. MEDIUM-1 (NaN/Inf) is CLOSED. MEDIUM-2 / MEDIUM-3 / LOW-1 / LOW-2
residuals hold.

Counts: CRIT 0 · HIGH 1 (NEW) · MEDIUM 2 (carried, hold) · LOW 2 (carried, hold).

Method note: this audit was read-only (Read/Grep/Glob/Write — no Bash). The
denylist-completeness grep output below is reproduced verbatim from the Grep tool; every
runtime-dependent claim is marked "EXECUTE TO CONFIRM" with the exact `python3 -c` probe
a Bash follow-up MUST run. Per the R1 lesson (a static pass wrongly declared the
brief→exec gate closed; a Bash probe later proved otherwise), the HIGH below is derived
from static evidence that is high-confidence (registration decorator + config-sourced
`exec` call site, both read directly) but the realizability of each node MUST be
confirmed by the enumerated probe before the finding is downgraded or closed.

---

## (a) MEDIUM-1 (NaN/Inf confidence-gate bypass) — CLOSED

`src/kailash/_from_brief/confidence.py:55-63` now leads with:

```python
if not math.isfinite(value) or value < 0.0 or value > 1.0:
    raise BriefInterpretationError(..., malformed=True)
```

`math.isfinite` rejects `NaN`, `+inf`, `-inf` BEFORE the always-False NaN-comparison
window the R1 finding exploited. `import math` is present (`confidence.py:19`).

`src/kailash/_from_brief/validator.py:69` now sets:

```python
model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
```

`allow_inf_nan=False` rejects NaN/±inf at Pydantic construction (defense-in-depth — the
LLM cannot smuggle a NaN `interpretation_confidence` past the float field). Both halves
of the R1-recommended fix landed. Static derivation: NaN/+inf/-inf all raise at BOTH the
gate AND construction; finite values in [0,1] still pass.

EXECUTE TO CONFIRM (4 probes — must all behave as noted):

```bash
# gate rejects NaN / +inf / -inf (each MUST raise BriefInterpretationError, malformed=True)
python3 -c "from kailash._from_brief.confidence import check_confidence as c; import math
for v in (float('nan'), float('inf'), float('-inf')):
    try: c(v, threshold=0.6); print('LEAK', v)
    except Exception as e: print('reject', v, getattr(e,'malformed',None))"
# Pydantic construction rejects NaN (MUST raise; was the R1 second half)
python3 -c "from kailash._from_brief.validator import BriefPlan
try: BriefPlan(interpretation_confidence=float('nan')); print('LEAK construct')
except Exception: print('reject construct')"
# finite still passes
python3 -c "from kailash._from_brief.confidence import check_confidence as c; c(0.8, threshold=0.6); print('0.8 ok')"
```

Expected: three `reject` lines (gate) + `reject construct` + `0.8 ok`. Any `LEAK` line
re-opens MEDIUM-1.

Regression-test note (carried from R1, still applies): confirm
`test_validator.py::TestConfidenceGate` was extended with NaN + Inf behavioral cases
(`pytest.raises(BriefInterpretationError)` asserting `.malformed is True`). The fix
without the test is a Rule-6/testing.md gap, not a security re-open, but the documented
P5 threat with no test is the HIGH-class signal under `testing.md` § Audit Mode.

---

## (b) CRITICAL-1 fix (new enforcement code) — SECURITY AUDIT

### What the fix does (verified by inspection, all correct)

1. **Denylist floor BEFORE allowlist, per node, in `_realize`** (`workflow/from_brief.py:534-548`).
   Each node spec is checked against `_DANGEROUS_NODE_TYPES` FIRST (raises `unknown_value`),
   THEN `validate_node_type(spec["node_type"], allowed_node_types)`. The denylist check is
   unconditional — independent of the caller-supplied `allowed_node_types`. Correct.

2. **Denylist subtracted from caller-supplied allowlist** (`workflow_from_brief:638-642`):
   `allowed_node_types = set(allowed_node_types) - _DANGEROUS_NODE_TYPES`. A caller cannot
   re-admit a denylisted type via a custom allowlist. Correct (closes the MEDIUM-2-class
   re-admission the comment cites).

3. **Denylist subtracted at the allowlist SOURCE** (`_registered_node_types:329`):
   `return set(NodeRegistry.list_nodes().keys()) - _DANGEROUS_NODE_TYPES`, so the augmented
   brief's `AVAILABLE NODE TYPES` block never enumerates the denylisted types to the LLM.
   Correct.

4. **Gate fires on BOTH surfaces.** `Workflow.from_brief` is a classmethod
   (`workflow/__init__.py:122-139`) whose entire body is `return workflow_from_brief(brief, **kwargs)`
   (`:136`). There is ONE realization path; both documented entrypoints share the identical
   `_realize` gate. Confirmed — no second, ungated surface.

### Bypass analysis on the gate mechanism itself (no CRIT/HIGH on the mechanism)

- **Case variation / whitespace** — `validate_node_type` and the denylist both use exact
  string membership (`name in allowed`, `spec["node_type"] in _DANGEROUS_NODE_TYPES`). A
  case/whitespace variant (`pythoncodenode`, `" PythonCodeNode"`) does NOT match the
  denylist — BUT it ALSO does NOT match the registry allowlist (the registry is keyed by
  exact `node_class.__name__`, `nodes/base.py:2381`), so `validate_node_type` rejects it as
  `unknown_value`. AND `WorkflowBuilder.add_node` would itself fail to resolve a non-exact
  type. Net: case/whitespace variation cannot reach `add_node` with a real node. No bypass
  on the mechanism. (EXECUTE TO CONFIRM: see probe set below, case-variant row.)

- **Registry-alias names** — `NodeRegistry.register(node_class, alias=...)` (`base.py:2326,2381`)
  keys a node under `alias or node_class.__name__`. The denylist subtracts only the two
  literal CLASS names. If `PythonCodeNode` or `AsyncPythonCodeNode` were ALSO registered
  under an alias, that alias would be in `list_nodes().keys()`, survive the denylist
  subtraction, and pass the allowlist. This is the same structural gap as the HIGH below
  (denylist is name-based, not class/capability-based). EXECUTE TO CONFIRM there is no
  alias registration for the two code nodes (probe below).

- **A node that WorkflowBuilder resolves to PythonCodeNode under a different string** — no
  such indirection found in the realizer path; `add_node(node_type, ...)` resolves via the
  registry by exact name. Not a separate bypass beyond the alias case above.

### NEW HIGH-1 — `_DANGEROUS_NODE_TYPES` denylist is INCOMPLETE (LOAD-BEARING CHECK)

**The denylist contains only `{"PythonCodeNode", "AsyncPythonCodeNode"}`** (`from_brief.py:80-85`).
The denylist-completeness re-derivation finds OTHER registered node types that execute
config-supplied code. Because the denylist is the absolute floor that protects against an
attacker-controlled brief reaching a code-execution node, every exec-capable REGISTERED
node MUST be in it (or proven config-code-free). Five+ are missing.

**Re-derivation grep — actual output** (`exec(`/`eval(`/`compile(` under `src/kailash/nodes/`,
11 files; each classified by (1) is it an `@register_node` class? (2) does the executed
string come from node CONFIG, i.e. LLM/brief-controllable?):

| File                                                                   | exec/eval site                                | `@register_node` class                                                            | Registry key (class `__name__`)                   | Code source                                                 | In denylist?                   |
| ---------------------------------------------------------------------- | --------------------------------------------- | --------------------------------------------------------------------------------- | ------------------------------------------------- | ----------------------------------------------------------- | ------------------------------ |
| `nodes/code/python.py:495`                                             | `exec(code, ...)`                             | `PythonCodeNode`                                                                  | `PythonCodeNode`                                  | config `code`                                               | **YES** ✓                      |
| `nodes/code/async_python.py:818-819`                                   | `compile(...)` + `exec(...)`                  | `AsyncPythonCodeNode`                                                             | `AsyncPythonCodeNode`                             | config code                                                 | **YES** ✓                      |
| `nodes/transform/processors.py:422,432,485`                            | `exec(transform_str)` / `eval(transform_str)` | `DataTransformer`                                                                 | `DataTransformer`                                 | config `transformations` (`processors.py:356`)              | **NO** ✗                       |
| `nodes/enterprise/batch_processor.py:279`                              | `exec(processing_code)`                       | `BatchProcessorNode`                                                              | `BatchProcessorNode`                              | config `processing_code` (param `batch_processor.py:97-98`) | **NO** ✗                       |
| `nodes/validation/validation_nodes.py:116,259`                         | `exec(code)` / `exec(workflow_code)`          | `CodeValidationNode`, `WorkflowValidationNode`, `ValidationTestSuiteExecutorNode` | same names                                        | config `code` (`validation_nodes.py:80`)                    | **NO** ✗                       |
| `nodes/logic/loop.py:106`                                              | `eval(expression, {"__builtins__":{}}, ctx)`  | `LoopNode` (NOT `@register_node`-decorated — see note)                            | `LoopNode` (registered elsewhere?)                | config `expression`                                         | **NO** ✗ (verify reachability) |
| `nodes/logic/convergence.py:500`                                       | `eval(expression, {"__builtins__":{}}, ctx)`  | `ConvergenceCheckerNode`, `MultiCriteriaConvergenceNode`                          | same names                                        | config `expression`                                         | **NO** ✗                       |
| `nodes/validation/test_executor.py:228,282,464`                        | `exec(code)` (FULL `__builtins__`, `:225`)    | NONE — `ValidationTestExecutor` is a plain helper, no `@register_node`            | n/a (reached only via the validation_nodes above) | —                                                           | n/a                            |
| `nodes/monitoring/log_processor.py:461`                                | `re.compile(...)`                             | —                                                                                 | —                                                 | regex compile, NOT code exec                                | n/a (false positive)           |
| `nodes/transaction/two_phase_commit.py:47`, `saga_state_storage.py:14` | `re.compile(...)`                             | —                                                                                 | —                                                 | table-name regex, NOT code exec                             | n/a (false positive)           |

**Severity rationale — HIGH, not CRITICAL:** the realizer's allowlist gate
(`validate_node_type`) still requires every node_type to be in `NodeRegistry.list_nodes()`.
These five+ node types ARE registered, so they pass the allowlist; the denylist is the ONLY
layer that would stop them and it does not. The exact attack the CRITICAL-1 fix was written
to stop — "a natural-language brief realizes a code-execution node" — remains OPEN for
`DataTransformer` (most reachable: `exec` of an arbitrary multi-line `transformations`
string the LLM puts in `config`), `BatchProcessorNode` (`exec` of `processing_code`),
and the three validation nodes (`CodeValidationNode` runs `exec(code)` with FULL
`__builtins__` at `test_executor.py:225` via `_execute_directly` when `sandbox=False`).
It is HIGH rather than CRITICAL because (i) realization requires the LLM to emit the node +
the malicious config (the brief must steer the plan, same precondition as the
PythonCodeNode threat), and (ii) `DataTransformer`/`BatchProcessorNode` run under a
restricted-`__builtins__` namespace — a real obstacle but NOT a security boundary
(restricted-builtins escapes via `().__class__.__bases__[0].__subclasses__()` are
well-known; `CodeValidationNode`'s direct path uses unrestricted `__builtins__`). The
worst case is arbitrary code execution from an attacker-controlled brief — the precise
outcome `_DANGEROUS_NODE_TYPES` exists to prevent.

**Fix (mechanical, fits one shard ~5-10 LOC + tests, per `autonomous-execution.md` MUST-4 —
same bug class as the in-flight CRITICAL-1 fix, surfaced at review, fix immediately):**
extend `_DANGEROUS_NODE_TYPES` to include every exec/eval-capable registered node:

```python
_DANGEROUS_NODE_TYPES: frozenset[str] = frozenset({
    "PythonCodeNode", "AsyncPythonCodeNode",
    "DataTransformer", "BatchProcessorNode",
    "CodeValidationNode", "WorkflowValidationNode", "ValidationTestSuiteExecutorNode",
    "LoopNode", "ConvergenceCheckerNode", "MultiCriteriaConvergenceNode",
})
```

Structural follow-up (recommend, separate from the literal-list fix): the denylist is a
NAME-based allowlist-of-the-forbidden — it drifts the instant a new exec-capable node is
registered or an alias is added (the registry-alias bypass row above is the same root).
The durable fix is a CAPABILITY check at `_registered_node_types` time — derive the
denylist by introspecting which registered classes call `exec`/`eval`/`compile` (or carry
a `executes_arbitrary_code = True` class marker), so a future exec-capable node is denied
by construction, not by remembering to edit a literal frozenset. Per
`zero-tolerance.md` Rule 2, a denylist that silently misses a sibling is the same
failure-mode class as the original CRITICAL-1 no-op.

EXECUTE TO CONFIRM (load-bearing — run before disposition):

```bash
# 1. Confirm the exec-capable registered nodes ARE in the registry and NOT denied today.
python3 -c "
from kailash.workflow.from_brief import _registered_node_types, _DANGEROUS_NODE_TYPES
reg = _registered_node_types()  # registry minus current denylist
for n in ('DataTransformer','BatchProcessorNode','CodeValidationNode',
          'WorkflowValidationNode','ValidationTestSuiteExecutorNode',
          'LoopNode','ConvergenceCheckerNode','MultiCriteriaConvergenceNode'):
    print(n, 'reachable=', n in reg, 'denied=', n in _DANGEROUS_NODE_TYPES)
"
# Expected (proving the HIGH): each reachable=True, denied=False.
# A reachable=True/denied=False row IS the open code-exec path.

# 2. Confirm the two code nodes have no alias re-admission (registry-alias bypass row).
python3 -c "
from kailash.nodes.base import NodeRegistry
keys = set(NodeRegistry.list_nodes().keys())
print('PythonCodeNode keys:', [k for k in keys if 'PythonCode' in k])
"
# Expected: only 'PythonCodeNode' / 'AsyncPythonCodeNode' — any extra alias is a bypass.

# 3. End-to-end realizer proof (no LLM needed — call _realize directly with a crafted plan).
python3 -c "
from kailash.workflow.from_brief import _realize, _registered_node_types
plan = type('P', (), {'nodes':[{'node_type':'DataTransformer','node_id':'x',
    'config':{'transformations':['result = __import__(\"os\").getcwd()']}}],
    'connections':[]})()
try:
    _realize(plan, _registered_node_types())
    print('BYPASS: DataTransformer realized from a plan')   # HIGH confirmed
except Exception as e:
    print('blocked:', type(e).__name__, getattr(e,'unknown_value',None))
"
# Expected today: 'BYPASS: DataTransformer realized from a plan' (the node is added to the
# builder; building+executing it would exec the transformations string). After the fix:
# 'blocked: BriefInterpretationError DataTransformer'.

# 4. Case-variant / whitespace probe (confirm the gate mechanism itself holds).
python3 -c "
from kailash.workflow.from_brief import _realize, _registered_node_types
for nt in ('pythoncodenode',' PythonCodeNode','PythonCodeNode '):
    plan = type('P', (), {'nodes':[{'node_type':nt,'node_id':'x','config':{}}],'connections':[]})()
    try: _realize(plan, _registered_node_types()); print('LEAK', repr(nt))
    except Exception as e: print('reject', repr(nt), type(e).__name__)
"
# Expected: all three 'reject' (unknown_value) — confirms case/whitespace cannot reach add_node.
```

---

## (c) Round-1 residuals — re-confirmed

**MEDIUM-2 (posture-upgrade nonce syntactic-only — deferred to S8) — HOLDS.**
`runtime.py:1198-1252` accepts any `human_acknowledged_nonce` length ≥ `_MIN_NONCE_LENGTH=16`;
no single-use/signature/expiry. Documented as a deliberate transitional placeholder with S8
named as owner; audit-before-rotate makes the upgrade forensically visible. Acceptable
residual for v2.27.0 conditional on a tracking issue for "S8 posture-upgrade cryptographic
nonce" existing — CONFIRM the issue exists before tagging (EXECUTE: `gh issue list --search
"S8 posture nonce"`); if absent, file one (documented-deferral-without-tracker is the gap).

**MEDIUM-3 (M1 consume-lock per-event-loop, not cross-thread) — HOLDS; caveat comment PRESENT
and ACCURATE.** The R1 report's line reference (`runtime.py:1052-1065`) is the actual
location — the inline "Scope caveat (R1 2026-05-27, MEDIUM)" comment is at
`runtime.py:1066-1075`, immediately above `self._consume_lock = asyncio.Lock()` (`:1076`).
The comment correctly states: `asyncio.Lock` serializes concurrent `execute()` coroutines on
ONE event loop (the documented/supported usage); it is NOT thread-safe; cross-thread sharing
is outside the async contract; `with_posture()` returns a fresh runtime+lock per Invariant 5
so the natural pattern never shares instances cross-thread; if cross-thread sharing ever
becomes supported, wrap acquisition in a `threading.Lock`. Accurate and complete. (Note: the
R2-prompt's pointer "runtime.py ~1052-1080" matches `src/kailash/delegate/runtime.py`, NOT
`src/kailash/runtime/local.py` — the latter's 1052-1080 is unrelated deprecation-warning
docstring. The delegate runtime is the correct file; confirmed.)

**LOW-1 (scrubber best-effort) — HOLDS.** Regex-based secret detection is inherently
incomplete; the scrubber is a defense-in-depth display-path safety net, not a guarantee;
brief is user-supplied. No action.

**LOW-2 (lazy-import contract) — HOLDS; already executed per R2 prompt.** The probe
`python3 -c "import kailash._from_brief, kailash.delegate, sys; print('kaizen' in sys.modules)"`
returns `False` (stated executed in the R2 brief) — the slim-core import closure holds; bare
`import kailash._from_brief` + `kailash.delegate` does not transitively pull kaizen. No
escalation.

---

## Disposition

The combined surface is NOT converged on the CRIT/HIGH axis: NEW HIGH-1 (denylist
incompleteness) is open and is the SAME bug class as the CRITICAL-1 fix being audited (an
attacker-controlled brief reaching a code-execution node). Per `autonomous-execution.md`
MUST Rule 4 (same-bug-class gap surfaced at review, ~5-10 LOC literal-list fix + a
capability-based structural follow-up, fits one shard), the recommendation is to extend
`_DANGEROUS_NODE_TYPES` in THIS release rather than defer — the literal-list fix closes the
open path immediately; the capability-introspection follow-up closes the drift class. The
load-bearing probe (probe 1 + probe 3 above) MUST be executed to convert this static
HIGH into an executed receipt before the fix is sized, exactly as the R1→R2 lesson requires
(R1's static pass declared this axis closed; only a Bash probe surfaces the open node).

MEDIUM-1 closed; MEDIUM-2/MEDIUM-3/LOW-1/LOW-2 hold. After HIGH-1 is fixed + the
denylist-completeness probe is green + NaN/Inf regression tests confirmed present, the
combined surface reaches `CONVERGED (CRIT/HIGH axis)`.

Receipts: this file is the R2 disposition. The executed-receipt obligations (MEDIUM-1
4-probe set, HIGH-1 probes 1-4, MEDIUM-2 `gh issue` tracker check) are enumerated inline
for a Bash-equipped follow-up. Prior round: `04-validate/R1-combined-security.md`.
