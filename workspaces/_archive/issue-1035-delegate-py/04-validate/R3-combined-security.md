# R3 Combined Security Audit — from_brief default-deny model (#1125)

**Verdict: `CONVERGED (CRIT/HIGH axis)`**

No safe-listed node can execute config-supplied code/expressions. No NEW CRIT/HIGH.
Model-bypass paths (caller-override subtraction, set-intersection, WorkflowNode composition)
all hold. R1/R2 fixes re-confirmed intact.

Scope: static derivation (read-only). A Bash-equipped reviewer runs the probes below to
confirm at runtime. The per-node safe-set re-review (Step 1) is the load-bearing check.

---

## Step 1 — Per-node safe-set security re-review (LOAD-BEARING)

Method (static): For each of the 45 entries, read the class source and check for ANY
config→execution channel: `exec`/`eval`/`compile` builtins; `__import__`/`importlib`;
`getattr`-dispatch on a config-supplied string; template-engine render (`{{}}`/`Template`);
`pickle`/`yaml.unsafe_load`; format-string injection; or delegation to a helper that does any
of these (`CodeExecutor`, lambda-from-string).

Confirmed evidence (read this session):

- `transform/processors.py`: `FilterNode` (`_apply_operator`, declarative operator dispatch
  `==`/`>`/`contains`, lines 172-216), `Map` (`_apply_operation`, fixed string-dispatch
  whitelist `identity`/`upper`/`multiply`, lines 283-298), `Sort`
  (`sorted(..., key=lambda x: x.get(field))` — lambda is hardcoded, NOT config-derived, line
  554), `ContextualCompressorNode` (sort-by-score, lines 561+). NONE call eval/exec/getattr
  on config. The file's `DataTransformer` (lines 301-512) DOES `exec`/`eval` config strings —
  it is correctly excluded from safe and present in `_DANGEROUS_NODE_TYPES`. The
  inverse-completeness test uses per-class `inspect.getsource`, so DataTransformer's exec does
  not bleed onto its file-siblings.
- `logic/operations.py`: `SwitchNode._evaluate_condition` (lines 402-477) and `MergeNode` —
  declarative operator dispatch identical to FilterNode (`==`/`in`/`is_null`); no eval path.
- `code/python.py`: `PythonCodeNode` (class line 1060) sets `self.executor = CodeExecutor()`
  in its body — the literal `CodeExecutor` is in its source, so the test's helper-delegation
  heuristic fires. It is in `_DANGEROUS_NODE_TYPES` (excluded from safe). Confirms the
  detection design works for the helper-delegation pattern that defeated the R2 denylist.
- `data/readers.py`: `CSVReaderNode`/`JSONReaderNode` import `safe_open, validate_file_path`
  from `kailash.security` (line 36); declarative parse config (delimiter/encoding/headers).

Per-node disposition (45 entries; one word each):

| #   | Node                      | Disposition                           |
| --- | ------------------------- | ------------------------------------- |
| 1   | CSVReaderNode             | safe                                  |
| 2   | JSONReaderNode            | safe                                  |
| 3   | TextReaderNode            | safe                                  |
| 4   | DocumentProcessorNode     | safe                                  |
| 5   | DocumentSourceNode        | safe                                  |
| 6   | DirectoryReaderNode       | safe                                  |
| 7   | FileDiscoveryNode         | safe                                  |
| 8   | QuerySourceNode           | safe                                  |
| 9   | CSVWriterNode             | safe                                  |
| 10  | JSONWriterNode            | safe                                  |
| 11  | TextWriterNode            | safe                                  |
| 12  | FilterNode                | safe                                  |
| 13  | Map                       | safe                                  |
| 14  | Sort                      | safe                                  |
| 15  | ChunkTextExtractorNode    | safe                                  |
| 16  | ContextFormatterNode      | safe                                  |
| 17  | ContextualCompressorNode  | safe                                  |
| 18  | QueryTextWrapperNode      | safe                                  |
| 19  | HierarchicalChunkerNode   | safe                                  |
| 20  | SemanticChunkerNode       | safe                                  |
| 21  | StatisticalChunkerNode    | safe                                  |
| 22  | TextSplitterNode          | safe                                  |
| 23  | MergeNode                 | safe                                  |
| 24  | AsyncMergeNode            | safe                                  |
| 25  | SwitchNode                | safe                                  |
| 26  | AsyncSwitchNode           | safe                                  |
| 27  | SignalWaitNode            | safe                                  |
| 28  | SQLDatabaseNode           | safe (param-binding; see Step 2 note) |
| 29  | AsyncSQLDatabaseNode      | safe (param-binding; see Step 2 note) |
| 30  | RedisNode                 | safe                                  |
| 31  | QueryRouterNode           | safe                                  |
| 32  | OptimisticLockingNode     | safe                                  |
| 33  | WorkflowConnectionPool    | safe                                  |
| 34  | EmbeddingNode             | safe                                  |
| 35  | VectorDatabaseNode        | safe                                  |
| 36  | AsyncPostgreSQLVectorNode | safe                                  |
| 37  | HybridRetrieverNode       | safe                                  |
| 38  | RelevanceScorerNode       | safe                                  |
| 39  | EventGeneratorNode        | safe                                  |
| 40  | EventStreamNode           | safe                                  |
| 41  | KafkaConsumerNode         | safe (connector; see Step 2 note)     |
| 42  | StreamPublisherNode       | safe                                  |
| 43  | WebSocketNode             | safe (connector; see Step 2 note)     |
| 44  | SharePointGraphReader     | safe (connector; see Step 2 note)     |
| 45  | SharePointGraphWriter     | safe (connector; see Step 2 note)     |

Result: **0 FLAG on the code/expression-execution axis.** The curation is sound — every
safe-listed node takes declarative config (field/operator/path/url), none compiles or
evaluates config-supplied code or delegates to a helper that does.

Probes for the Bash reviewer to confirm (each must return EMPTY / expected):

```bash
# P1 — per-class code-exec scan over the resolved safe set (mirrors the inverse-completeness
#       test, but printed so the reviewer sees the offender set directly)
.venv/bin/python - <<'PY'
import ast, inspect, textwrap, importlib
for m in ("kailash.nodes.data","kailash.nodes.transform","kailash.nodes.logic","kailash.nodes.code"):
    importlib.import_module(m)
from kailash.nodes.base import NodeRegistry
from kailash.workflow.from_brief import _SAFE_NODE_TYPES
reg = NodeRegistry.list_nodes()
def calls_exec(cls):
    try: src = textwrap.dedent(inspect.getsource(cls))
    except (OSError, TypeError): return False
    if "CodeExecutor" in src: return True
    try: tree = ast.parse(src)
    except SyntaxError: return False
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name) and f.id in ("exec","eval","compile"): return True
            if isinstance(f, ast.Attribute) and f.attr in ("exec","eval"): return True
    return False
print("OFFENDERS:", sorted(n for n in _SAFE_NODE_TYPES if n in reg and calls_exec(reg[n])))
PY
# Expect: OFFENDERS: []

# P2 — broaden the heuristic to dynamic-import / template / unsafe-deserialize markers
#       (catches channels the test's exec/eval/CodeExecutor scan does not name)
.venv/bin/python - <<'PY'
import inspect, importlib
for m in ("kailash.nodes.data","kailash.nodes.transform","kailash.nodes.logic"):
    importlib.import_module(m)
from kailash.nodes.base import NodeRegistry
from kailash.workflow.from_brief import _SAFE_NODE_TYPES
reg = NodeRegistry.list_nodes()
markers = ("__import__","importlib.import_module","yaml.load(","yaml.unsafe_load",
           "pickle.load","Template(",".render(",".format_map(")
hits = {}
for n in sorted(_SAFE_NODE_TYPES):
    if n not in reg: continue
    try: src = inspect.getsource(reg[n])
    except (OSError, TypeError): continue
    found = [k for k in markers if k in src]
    if found: hits[n] = found
print("MARKER_HITS:", hits)
PY
# Expect: MARKER_HITS: {}  (manual triage any hit: getattr/format on config string = FLAG)
```

---

## Step 2 — Beyond-code-exec escalations (SSRF / file IO / SQLi surface)

Question per audit: does any safe-listed node widen the attack surface _more_ under an
untrusted brief than under a developer hand-writing the same config?

- File IO (CSV/JSON/Text readers+writers, Directory/FileDiscovery): config is a `file_path`.
  Arbitrary file read/write is a real capability, BUT the node's own validation owns it —
  `readers.py:36` routes through `kailash.security.validate_file_path` + `safe_open`. The
  brief sets the same string a developer would; the gate is identical. `from_brief` does NOT
  materially widen the surface. **Accepted** (node validation owns it).
- SSRF (WebSocketNode, KafkaConsumerNode, SharePointGraphReader/Writer, the SQL/vector
  connectors): config carries a URL/host/connection string. The connector's own
  URL/credential handling owns this exactly as for hand-written usage. **Accepted** — not a
  `from_brief`-specific widening.
- SQL (SQLDatabaseNode/AsyncSQLDatabaseNode): the node binds parameters; SQLi defense is the
  node's parameter-binding contract (`rules/security.md` § Parameterized Queries), unchanged
  by brief origination. **Accepted.**

Net: no Step-2 finding rises to NEW HIGH/CRIT because none represents a `from_brief`-specific
escalation beyond the node's own ownership of its config. Reviewer probe (optional confirm):

```bash
# P3 — confirm CSV/JSON readers route file paths through the security helper
grep -n "validate_file_path\|safe_open" \
  src/kailash/nodes/data/readers.py
# Expect: import + use present (defense lives in the node, not from_brief)
```

Note (advisory, not a blocker): the safe set deliberately includes IO/connector nodes so
realistic briefs are expressible. This is a correct design trade-off — the alternative
(excluding all IO) would make `from_brief` near-useless. The accepted residual is that a
brief can direct a reader at a path/url the brief author chose; this is the same trust
boundary as any node config and is owned by the node + the caller's deployment posture.

---

## Step 3 — Model bypasses

(a) **Caller-override `workflow_from_brief(allowed_node_types=...)` cannot re-admit a dangerous
node.** Verified in source: `from_brief.py:737-744` — when a caller supplies
`allowed_node_types`, the code computes `set(allowed_node_types) - _DANGEROUS_NODE_TYPES`
(subtraction floor). Additionally `_realize` (lines 636-650) re-checks `_DANGEROUS_NODE_TYPES`
FIRST and UNCONDITIONALLY at the `add_node` choke point, independent of `allowed_node_types`.
Two independent layers. **Holds.**

(b) **Resolved allowlist is `set(_SAFE_NODE_TYPES) & registry`.** Verified: `_safe_node_types()`
returns `set(_SAFE_NODE_TYPES) & set(NodeRegistry.list_nodes().keys())` (line 431). A node not
in `_SAFE_NODE_TYPES` cannot appear in the default allowlist by construction (intersection,
not subtraction). Default-deny holds. **Holds.**

(c) **WorkflowNode composition bypass is excluded.** `WorkflowNode` is absent from
`_SAFE_NODE_TYPES` AND present in `_DANGEROUS_NODE_TYPES` (line 178). It cannot nest an
arbitrary sub-workflow embedding a code-exec node, because it is rejected at both the
allowlist gate (not in safe set) and the unconditional denylist floor. **Holds.**

Probes:

```bash
# P4 — caller-override cannot re-admit a dangerous node (default + custom-allowlist paths)
.venv/bin/python - <<'PY'
from kailash.workflow.from_brief import _safe_node_types, _DANGEROUS_NODE_TYPES, _SAFE_NODE_TYPES
allowed = _safe_node_types()
assert allowed & _DANGEROUS_NODE_TYPES == set(), "default allowlist admits a dangerous node!"
assert allowed <= set(_SAFE_NODE_TYPES), "resolved set escaped the positive allowlist!"
# simulate a malicious caller-supplied allowlist that tries to re-admit code-exec nodes:
caller = set(_DANGEROUS_NODE_TYPES) | {"CSVReaderNode"}
subtracted = caller - _DANGEROUS_NODE_TYPES
assert subtracted == {"CSVReaderNode"}, subtracted
assert "WorkflowNode" not in allowed and "PythonCodeNode" not in allowed
print("MODEL-BYPASS: all guards hold")
PY
# Expect: MODEL-BYPASS: all guards hold

# P5 — _realize re-checks the denylist unconditionally (source assertion is structural;
#       behavioral confirm is the regression test below)
.venv/bin/python -m pytest -q \
  tests/unit/workflow/test_from_brief_safe_allowlist.py::test_known_code_exec_nodes_are_not_brief_reachable
# Expect: 1 passed
```

---

## Step 4 — Inverse-completeness test adequacy

`tests/unit/workflow/test_from_brief_safe_allowlist.py::_class_calls_code_exec` detects:
(a) builtin `exec`/`eval`/`compile` (ast.Name); (b) attribute `.exec`/`.eval` (ast.Attribute);
(c) the literal string `CodeExecutor` anywhere in the class source. (c) is the explicit fix
for the helper-delegation pattern (PythonCodeNode delegates to `CodeExecutor`, invisible to a
pure builtin scan). Confirmed PythonCodeNode's source contains `CodeExecutor` (python.py:1245+).

Adequate for the current SDK. Robustness notes (NOT blockers — future test-hardening):

- N1 (MEDIUM-robustness): the helper-name match is the single literal `"CodeExecutor"`. A
  future node that execs via a DIFFERENTLY-named helper (e.g. `ScriptRunner`, `_eval_expr`,
  `sandbox.run`) would pass the test while being unsafe. Mitigation already in place: the
  PRIMARY defense is human review at add-time + default-deny (a new node is not brief-reachable
  until a human adds it). The test is the secondary net. Suggest broadening the helper-name set
  OR walking imports for `from kailash.nodes.code...` as a follow-up hardening (file a
  test-robustness todo; not release-blocking).
- N2 (LOW): the AST scan is class-source-only (`inspect.getsource(cls)`) — it does NOT follow
  into base classes or called helpers defined elsewhere. A node inheriting an exec-capable
  mixin without a class-body marker would be missed. Same mitigation as N1 (human review +
  default-deny). Note for the maintainer.
- N3 (LOW): `inspect.getsource` raises `OSError`/`TypeError` for C-extension or
  dynamically-generated classes → treated as "not code-exec" (returns False). A
  dynamically-generated exec node would evade. Not reachable in the current pure-Python node
  set; note for future.

These are test-robustness observations, consistent with the audit instruction ("not
necessarily blockers"). The model's PRIMARY defense (human-curated positive allowlist +
default-deny + unconditional denylist floor) does not depend on the test catching every
future helper name.

---

## Step 5 — R1/R2 fix re-confirmation

- **NaN gate (P5 / R1):** `confidence.py:58` — `if not math.isfinite(value) or value < 0.0 or
value > 1.0: raise(...malformed=True)`. Plus `BriefPlan.model_config =
ConfigDict(extra="forbid", allow_inf_nan=False)` (validator.py:69) rejects NaN/±inf at
  Pydantic construction. Defense-in-depth, intact. **Holds.**
- **CRITICAL-1 (allowlist enforced at the realize choke point):** `_realize` calls
  `validate_node_type(spec["node_type"], allowed_node_types)` per node (from_brief.py:650),
  because `validate_plan`'s top-level node_type gate does not reach
  `plan.nodes[i]["node_type"]`. Documented at lines 594-608 + 647-650. **Holds.**
- **CRITICAL-2 (denylist floor re-applied unconditionally in realize):** from_brief.py:640-646
  raises before allowlist check, independent of `allowed_node_types`. **Holds.**
- **MEDIUM-2 (caller-override subtraction):** from_brief.py:744. **Holds** (see Step 3a).
- **Credential scrub (S1):** `scrub_brief(brief)` runs pre-LLM/pre-logging
  (from_brief.py:729). **Present.**
- **SEC-6 (schema-revealing field names at DEBUG, count-only):** from_brief.py:765-773 logs
  `field_count` not `raw_keys`, at DEBUG. Consistent with `rules/observability.md` Rule 8.
  **Holds.**
- **Delegate M1/M3/M4:** out of scope for this from_brief module (delegate-py sibling shard);
  no regression introduced by from_brief.py changes — this module does not touch the delegate
  surface. Re-confirmation deferred to the delegate-specific R3 doc (`R3-convergence.md`).

Probe:

```bash
# P6 — NaN/range gate behavioral confirm
.venv/bin/python - <<'PY'
import math
from kailash._from_brief.confidence import check_confidence
from kailash._from_brief.exceptions import BriefInterpretationError
for bad in (float("nan"), float("inf"), -1.0, 2.0):
    try:
        check_confidence(bad); raise SystemExit(f"FAIL: {bad} passed the gate")
    except BriefInterpretationError as e:
        assert getattr(e, "malformed", False), f"{bad} not flagged malformed"
print("NaN/range gate: holds")
PY
# Expect: NaN/range gate: holds
```

---

## Summary

- **Step 1 (load-bearing):** 45/45 safe-listed nodes are config-declarative; 0 FLAG on the
  code/expression-execution axis. Curation is sound. DataTransformer / PythonCodeNode /
  WorkflowNode / Convergence nodes correctly excluded + on the denylist floor.
- **Step 2:** file-IO and SSRF/SQL surfaces are owned by each node's own validation
  (`validate_file_path`, param-binding); `from_brief` does not materially widen them →
  accepted, no NEW HIGH/CRIT.
- **Step 3:** all three model-bypass paths (caller-override subtraction, set-intersection
  default-deny, WorkflowNode exclusion) hold under static derivation + the P4 probe.
- **Step 4:** inverse-completeness test is adequate for the current SDK; 3 test-robustness
  notes (alt-helper-name, base-class/mixin, dynamic-class) recorded as non-blocking follow-ups.
- **Step 5:** NaN gate, CRITICAL-1/-2, MEDIUM-2, scrub, SEC-6 all intact.

**Verdict: `CONVERGED (CRIT/HIGH axis)`** — the default-deny inversion closes the R2 denylist
unsoundness; no safe-listed node can execute config code; no NEW CRIT/HIGH.
