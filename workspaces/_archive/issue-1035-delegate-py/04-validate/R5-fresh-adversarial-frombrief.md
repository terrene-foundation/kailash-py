# R5 — Fresh Adversarial Security Review: from_brief (#1125) untrusted-brief → workflow surface

**Verdict: CONVERGED** (0 CRIT / 0 HIGH / 0 new MEDIUM after genuine adversarial effort)

Scope: kailash-py v2.27.0 pre-release, branch `release/v2.27.0`. Surface:
`src/kailash/workflow/from_brief.py`, `src/kailash/bootstrap.py`,
`src/kailash/_from_brief/{validator,confidence,scrubber,allowlist}.py`.
Method: re-derived from scratch; prior-round findings re-verified independently, not trusted.

---

## Step 1 — Dangerous-node set re-derivation from scratch (load-bearing)

Enumerated the process-global `NodeRegistry` two ways and scanned each class + full MRO
source for config-supplied code-load vectors (`exec`/`eval`/`compile`,
`importlib.import_module`/`__import__`, dynamic `getattr(obj,<cfg>)(...)`,
`pickle/marshal/dill/cloudpickle.loads`, unsafe `yaml.load`, `subprocess`/`os.system`,
jinja templating).

### Minimal warm (the 4 submodules `_safe_node_types()` warms) — 52 registered nodes

```
=== NODES WITH CODE-LOAD VECTOR (5) ===
  AsyncPythonCodeNode      denylisted   compile,exec,import_module,subprocess
  ConvergenceCheckerNode   denylisted   eval
  DataTransformer          denylisted   eval,exec,import_module
  PythonCodeNode           denylisted   import_module,subprocess
  SharePointGraphReader    denylisted   import_module
SAFE-LIST x FLAGGED OVERLAP: NONE
```

### Full warm (all 144 node submodules recursively imported) — 129 registered nodes

```
=== FULL: NODES WITH CODE-LOAD VECTOR (12) ===
  APIHealthCheckNode       blocked-by-default-deny   subprocess
  AsyncPythonCodeNode      denylisted                compile,exec,import_module,subprocess
  BatchProcessorNode       denylisted                eval,exec,import_module,jinja
  CodeValidationNode       denylisted                exec
  ConvergenceCheckerNode   denylisted                eval
  DataTransformer          denylisted                eval,exec,import_module
  LogProcessorNode         blocked-by-default-deny   compile
  PythonCodeNode           denylisted                import_module,subprocess
  RESTClientNode           blocked-by-default-deny   jinja
  SharePointGraphReader    denylisted                import_module
  TransactionMetricsNode   blocked-by-default-deny   jinja
  WorkflowValidationNode   denylisted                exec
SAFE-LIST x FLAGGED OVERLAP: NONE
```

Disposition of every code-load-flagged node:

- **8 on the `_DANGEROUS_NODE_TYPES` denylist floor** (PythonCodeNode, AsyncPythonCodeNode,
  DataTransformer, ConvergenceCheckerNode, BatchProcessorNode, CodeValidationNode,
  WorkflowValidationNode, SharePointGraphReader).
- **4 flagged but on neither list** (APIHealthCheckNode, LogProcessorNode, RESTClientNode,
  TransactionMetricsNode) — blocked by DEFAULT-DENY (not in `_SAFE_NODE_TYPES`), verified
  rejected in Bypass 3 below. These are HTTP-client / metrics nodes whose flags are
  subprocess-in-healthcheck / jinja-in-templating, not brief-reachable.
- **0 on `_SAFE_NODE_TYPES`.** The overlap is empty under both the minimal and full warm.

**`SharePointGraphReader` / `SharePointGraphWriter`: confirmed EXCLUDED from the safe list
AND present on the denylist floor.** The prior-round MEDIUM (device_code_callback →
`importlib.import_module`) is closed: Reader is AST-flagged + denylisted; Writer shares the
device-code auth module and is denylisted (its vector is not in its own class source, so the
scanner does not auto-flag it — it is covered by the floor + the disjointness test, which is
the correct defense for AST-invisible vectors). `WorkflowNode` (sub-workflow composition
bypass) and `MultiCriteriaConvergenceNode` are likewise denylisted though AST-invisible.

All 43 declared `_SAFE_NODE_TYPES` resolve to real registered nodes (0 missing).

## Step 2 — Bypass attempts (by construction)

```
Bypass 1 override allowlist + PythonCodeNode  -> blocked (unknown_value='PythonCodeNode')
   (denylist floor subtracted unconditionally even from caller-supplied allowed_node_types)
Bypass 2 case/space/tab/Cyrillic-homoglyph    -> NOT registered (exact-match registry);
   add_node/build raises "Node '<variant>' not found"; cannot resolve to real PythonCodeNode.
   An attacker brief cannot inject a variant INTO the allowlist (allowlist = registry ∩ safe-list).
Bypass 3 registered-but-not-safe-listed       -> all blocked (RESTClientNode, APIHealthCheckNode,
   LogProcessorNode, HTTPRequestNode → unknown_value)
Bypass 4 every denylisted node via default    -> all 12 blocked
Bypass 5 floor subtraction in entrypoint      -> {PythonCodeNode,DataTransformer,WorkflowNode}
   removed; dangerous-remaining = ∅
```

**bootstrap() path re-derived, not assumed:** `kailash.bootstrap()` does NOT realize nodes.
It returns a frozen `BootstrapConfig` of 4 strings (`db_url`, `llm_model`, `runtime`,
`deployment_target`). `runtime`/`deployment_target` are gated by closed enum allowlists
(`ALLOWED_RUNTIMES`, `ALLOWED_DEPLOYMENT_TARGETS`); `profile` is gated pre-LLM. No `add_node`
choke point exists, so the node-execution threat surface is `workflow_from_brief` only.

## Step 3 — Confidence / scrubber

- NaN/+inf/−inf rejected at BOTH layers: pydantic `allow_inf_nan=False` (ValidationError at
  construction) AND `check_confidence` `math.isfinite` (malformed=True). Out-of-range
  (−0.5/1.5/2.0) rejected. Full dict→coerce_plan→validate_plan path blocks NaN.
- Scrubber: URL userinfo, `sk-` keys, kv `password=`/`api_key=`, Bearer, AWS, GitHub PAT,
  null-byte URL (`mysql://user:%00bypass@host`), 64KB length cap — all redacted/enforced, no leak.

## Step 4 — Test integrity

```
459 passed in 5.15s   (-W error → zero warnings)
459 tests collected   (--collect-only exit 0)
```

Test guard `tests/unit/workflow/test_from_brief_safe_allowlist.py`: AST-based
`_class_calls_code_exec` (full-MRO walk) + disjointness test + every-safe-node-registered test

- no-safe-node-executes-config-code test. Mechanical inverse-completeness net is present.

## Step 5 — Mechanical sweeps on the diff surface (v2.26.2..HEAD)

- bare-except / eval / exec / shell / pickle / yaml.load: **NONE** (sole `exec(` hit is a comment).
- stubs / TODO / FIXME / NotImplementedError / fake* / simulated*: **NONE**.
- inline DDL: **NONE**.
- secret-in-log (raw brief / raw_keys / password in logger): **NONE** (llm_returned logs
  `field_count` only, at DEBUG, per SEC-6).

---

## Conclusion

The DEFAULT-DENY positive allowlist (`registry ∩ _SAFE_NODE_TYPES`) + the unconditional
`_DANGEROUS_NODE_TYPES` floor (subtracted from caller overrides AND re-checked first at the
`add_node` choke point) is sound. No safe-listed node carries a config-supplied code-load
vector under either a minimal (52-node) or full (129-node) registry warm. SharePoint
Reader+Writer are excluded and denylisted. Case/whitespace/homoglyph node_type variants are
not registered (exact-match registry) and cannot be injected into the allowlist by a brief.
The bootstrap() path realizes no nodes. Confidence NaN/inf and the credential scrubber hold.
**CONVERGED.**
