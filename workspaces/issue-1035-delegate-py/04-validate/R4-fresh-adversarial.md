# R4 — Fresh-Eyes Adversarial Review (v2.27.0 pre-release)

**Verdict: FINDINGS** — 1 MEDIUM (not CRIT/HIGH). One genuine allowlist-curation
gap surfaced in `from_brief`; everything else re-derived clean. The headline
CRITICAL threat (untrusted brief → unconditional arbitrary code execution) is
**NOT** present.

Reviewer: fresh-eyes, re-derived from scratch (did not trust prior R1–R3 rounds).
Date: 2026-05-27. Branch: `release/v2.27.0`. Surface: `git diff v2.26.2..HEAD -- src/`
(from_brief #1125 + delegate #1035 + bootstrap.py).

---

## Test integrity (clean)

```
.venv/bin/python -m pytest tests/unit/workflow/ tests/unit/_from_brief/ \
  tests/regression/from_brief/ tests/unit/delegate/ \
  tests/regression/test_issue_1035_delegate_*.py tests/unit/test_bootstrap_realizer.py -W error -q
→ 928 passed, 1 skipped in 6.78s  (zero warnings under -W error)
```

- `pytest --collect-only -q` over the same dirs → **exit 0**.
- The 1 skip is honest + greppable: `tests/unit/delegate/test_audit_engine.py:576`
  — S7 cross-SDK byte-parity test, deferred pending vendored kailash-rs reference
  vectors per `cross-sdk-inspection.md` Rule 4 (assertion shape pinned in the skip
  reason so the gap is greppable). Acceptable per test-skip-discipline.

---

## FINDING 1 — MEDIUM: `SharePointGraphReader` is brief-reachable AND has a config-driven dynamic-import-and-call surface the safe-allowlist curation missed

**File:** `src/kailash/nodes/data/sharepoint_graph.py:436-446` (the node) +
`src/kailash/workflow/from_brief.py:153` (safe-listed) +
`tests/unit/workflow/test_from_brief_safe_allowlist.py:39-84` (the inverse-completeness
test that does NOT catch it).

**Claim under test:** the `from_brief` module docstring
(`workflow/from_brief.py:85-93`) asserts every `_SAFE_NODE_TYPES` member "verified
to take DECLARATIVE config (field/operator/path), never config-supplied code or
expressions," backstopped by the `test_no_safe_node_executes_config_code`
inverse-completeness test. This claim is **false** for `SharePointGraphReader`.

**By-construction repro:**

`SharePointGraphReader` is on the default safe allowlist (`from_brief.py:153`) and
resolves brief-reachable (`_safe_node_types()` returns it). It declares a `str`
config param `device_code_callback`. When realized + executed:

```
brief → LLM emits SharePointGraphReader node, config = {
    auth_method: "device_code", tenant_id: "...", client_id: "...",
    device_code_callback: "<attacker.module>.<func>"
}
→ workflow.build() → runtime.execute() → SharePointGraphReader.run(**config)
→ auth_method=="device_code" → _authenticate_device_code(...)        # line 745-758
→ app.initiate_device_flow(...)                                       # live MS call
→ if "user_code" in flow:                                            # line 436
      module_name, func_name = device_code_callback.rsplit(".", 1)   # line 441
      module = importlib.import_module(module_name)  # ← executes module-level code  # line 442
      callback_func = getattr(module, func_name)                     # line 443
      callback_func(flow)                                            # line 444
```

`importlib.import_module(<config-string>)` executes the top-level code of any
importable module (verified by construction — `import_module` of an attacker-named
module resolves + runs its module body). This is config-driven code execution on a
node the design intended to be "declarative-only."

**Why the inverse-completeness test misses it:** `_class_calls_code_exec` (test
file lines 39-84) walks the MRO looking for `exec`/`eval`/`compile` Name/Attribute
`ast.Call`s + the literal string `CodeExecutor`. The dynamic-import mechanism
(`importlib.import_module` + `getattr` + call) is NONE of those, so the test returns
`False` and PASSES while the node IS config-code-exec-capable. Confirmed by running
the test's own detection function against the class: `_class_calls_code_exec(SharePointGraphReader)
→ False`. The test's docstring even enumerates "KNOWN ACCEPTED GAPS" — but the
import-and-call mechanism is not among them; it is an unanticipated mechanism class.

**Why MEDIUM, not CRITICAL/HIGH (honest severity):** exploitation is gated, unlike
the unconditional `exec` of `PythonCodeNode`:

1. The `import_module` fires only inside `_authenticate_device_code`, reached only when
   `auth_method=="device_code"` AND after a **live** `app.initiate_device_flow()`
   call to Microsoft's login endpoint succeeds (`"user_code" in flow`), which needs a
   reachable network + a usable brief-supplied `client_id`/`tenant_id`.
2. The block is wrapped in `try/except Exception: pass` (line 445-446) — but
   `import_module`'s module-level side effects fire regardless of the later catch.
3. The attacker module must be importable on the victim's `sys.path` (or the attacker
   must already control a module name that does something on import).

It is NOT unconditional ACE. But it IS a clear violation of the allowlist-curation
invariant the design relies on: a brief-reachable "safe" node has a config-string →
dynamic-import-and-call path, and the mechanical backstop test does not detect it.

**Recommended disposition (smallest structural fix):** add `SharePointGraphReader`
(and, defensively, `SharePointGraphWriter` — same module, same auth pattern; its
`device_code_callback` was not in its class body but the auth helper is shared
in the module) to `_DANGEROUS_NODE_TYPES`, OR remove `SharePointGraphReader` from
`_SAFE_NODE_TYPES`. AND extend the inverse-completeness test
(`_source_calls_code_exec`) to also flag `importlib.import_module` / `__import__`
called with a non-literal arg, closing the mechanism-class gap so the next
SDK node with this shape is caught mechanically. Only `SharePointGraphReader`
exhibits this among the 45 registered safe nodes (swept all safe nodes — sole hit).

---

## What was attacked and re-derived clean

**Headline threat (brief → ACE):** traced every path from `workflow_from_brief` /
`Workflow.from_brief` / `bootstrap` to node realization.

- Default-deny positive allowlist (`_SAFE_NODE_TYPES`) IS enforced at the realization
  choke point (`_realize` lines 634-657): every `plan.nodes[i]["node_type"]` is checked
  against `_DANGEROUS_NODE_TYPES` (unconditional floor, first) then `validate_node_type`
  against the resolved safe set. `validate_plan`'s top-level node-type gate is a no-op
  for the per-node shape; the realizer is the real boundary and it enforces both gates.
- Enumerated all 65 registered nodes: every node whose **own class body** calls
  `exec`/`eval`/`compile` (`PythonCodeNode`, `AsyncPythonCodeNode`, `DataTransformer`,
  `ConvergenceCheckerNode`, `MultiCriteriaConvergenceNode`, `WorkflowNode`) is denylisted
  AND excluded from the resolved safe set. Safe/dangerous sets are disjoint.
- Safe-listed `FilterNode`/`Map`/`Sort` use hardcoded `if/elif` operator dispatch
  tables, NOT eval — genuinely declarative. The `eval`/`compile` module-level grep hits
  on `transform.processors` are sibling classes (`DataTransformer`), not the safe classes.
- `getattr` hits in safe nodes are all hardcoded string literals (`getattr(self,"id")`),
  NOT config-driven dispatch — EXCEPT the SharePointGraphReader finding above.

**Bypass attempts:**

- Caller `allowed_node_types=` override → `_DANGEROUS_NODE_TYPES` subtracted from the
  caller set (`from_brief.py:744`) AND re-checked unconditionally in `_realize` (line 640).
  Cannot re-admit a denylisted node.
- node_type normalization: exact-string membership; no case/whitespace fold that would
  let `"pythoncodenode"` slip past (the registry keys are exact, allowlist is exact).
- Confidence gate (NaN/inf): closed two ways — `BriefPlan.model_config` has
  `allow_inf_nan=False` (pydantic rejects at construction) AND `check_confidence` uses
  `math.isfinite` (`confidence.py:58`). NaN/±inf → `malformed=True`.

**bootstrap.py (724 LOC, fresh audit):** structurally CANNOT reach a code-exec node —
`bootstrap()` builds NO nodes and NO workflow. It returns a frozen 4-field
`BootstrapConfig` (db_url, llm_model, runtime, deployment_target). There is no
node-type allowlist because there are no nodes; the relevant gates ARE present and
correct: profile allowlist gate fires kaizen-free BEFORE the LLM call
(`bootstrap.py:629`), enum allowlists for runtime + deployment_target
(`bootstrap.py:696-710`), scrub_brief pre-LLM (line 649), confidence gate via
`validate_plan` (line 689). `db_url` is passed through verbatim (documented), but it is
returned config, never executed. No weaker/parallel allowlist path exists.

**delegate (#1035) fresh probe:** M1/M3/M4 hardening holds.

- Token forgery: `Ed25519Verifier` does real `cryptography` Ed25519 verify
  (`verifier.py:286-291`); `NullVerifier` fail-closed default rejects everything;
  verifier never raises (boolean-only, fail-closed at every step).
- Cascade grant: `grant_proof` cryptographically verified BEFORE registry mutation
  (`trust.py:791-799`, Step 3.5 before Step 4); `granted_at_resolved` reused so the
  verified bytes are byte-identical to the emitted GrantMoment's (`trust.py:828-834`).
- Tenant isolation: `TenantScope` is a typed 2-variant union (Global is explicit, never
  implicit `None`); tenant-first check fires FIRST in `cascade_child` (line 722).
- M4 tenant-hash salt: eager module-import init (`trust.py:143`) — the lazy
  check-and-set race is closed; HMAC-SHA-256 salted, per-process, never logged.
- Legacy connector defaults raise typed `_legacy_unsupported` (NotImplementedError)
  rather than returning empty-crypto envelopes (closes #1177/#1178) — correct
  zero-tolerance Rule 3a guards, not stubs.
- Replay note (NOT a new finding): grant_canonical carries no nonce, but `granted_at`
  is in the signed payload, so a proof only validates for its original timestamp;
  chain-composition is the documented deferred B7 reduced-shape area.

**Mechanical sweeps across the diff surface (all clean):**

- bare-except / `except: pass`: none in the diff surface.
- `eval(`/`exec(`/`compile(`/`shell=True`: all hits are `re.compile(...)` (regex) or a
  comment — no eval/exec on untrusted paths in the new code.
- stubs: the 3 `NotImplementedError` hits in `delegate/dispatch.py` are an abstract
  method (`:631 # pragma: no cover (abstract)`) and the `_legacy_unsupported` typed
  guard (`:757`); the trust.py one is a comment. None are stubs.
- inline DDL: none.
- credential scrubber: SEC-1..SEC-8 corpus present (URL+userinfo, sk-, Bearer, AWS,
  GitHub, Google, Slack, JWT, Stripe, Twilio, kv-pairs), pre-encode pass for raw `@`
  in passwords, 64KB length cap fail-loud, mask sentinel distinct from success shape.
  No gap surfaced on a fresh read.

---

## Receipts

- Test run: `928 passed, 1 skipped` under `-W error` (command above, reproducible).
- Registry enumeration + safe/dangerous disjointness + inverse-completeness-test
  bypass: all produced by live `python3` introspection against the editable install
  during this session (commands in the session transcript).
- Finding 1 reachability proven by construction: `import_module(<attacker-name>)`
  resolves + runs an attacker-named module's top-level code via the exact
  `rsplit`/`import_module`/`getattr` path at `sharepoint_graph.py:441-443`.
