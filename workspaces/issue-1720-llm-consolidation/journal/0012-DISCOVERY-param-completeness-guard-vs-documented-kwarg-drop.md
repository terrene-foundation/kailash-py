# DISCOVERY — An AST param-completeness guard is the structural defense for the documented-kwarg-drop class

Date: 2026-07-23. Repo class: BUILD. Author: agent. Phase: codify.
relates_to: (none — new pattern)

## The discovery

`zero-tolerance.md` Rule 3c ("Documented Kwargs Accepted But Unused") states the PRINCIPLE —
a documented public kwarg with zero effect on the body is the silent-fallback mode at the API
surface. But a principle is not a tripwire: the SAME class recurred THREE times on ONE
constructor (`kaizen_agents.Delegate.__init__`) before it was structurally closed —
`base_url`/`api_key` (#1899), `temperature`/`max_tokens` (#1926), `signature`/`inner_agent`
(#1927). Each fix closed one instance; none prevented the next.

The structural defense is a **per-constructor AST completeness guard** (landed in
`test_delegate_facade.py::test_every_init_param_reaches_a_consumer`): parse the constructor's
own source (`inspect.getsource` + `ast.parse`), and for every parameter assert it is READ in a
Load context somewhere OTHER than its own `self._x = x` storage line. A parameter whose only
use is being stored to an attribute — the exact documented-kwarg-drop shape — fails loudly.
It is a STRUCTURAL probe (no LLM, no regex over prose), so it is deterministic and CI-cheap.

## Why "read beyond storage" is the load-bearing predicate

The discriminator is `loads[param] > store_only[param]`. `self._x = x` increments BOTH the
Load count (the RHS `x`) and the store-only count, so a pure-stored param nets equal and is
flagged; any additional Load — passed to a callee (`KzConfig(api_key=api_key)`), tested in a
branch (`if temperature is not None`), or transformed — tips it over and clears. This makes
the guard self-maintaining: a genuinely-wired param passes automatically, a no-op param fails
automatically, with no per-param allowlist to drift.

## The negative-pole lesson (echoes 0010)

Per 0010's meta-lesson (a fix-pattern guard must prove its NEGATIVE pole, not just the
positive), the guard was mutation-tested against synthetic stored-only params — bare `Assign`
(`self._x = x`) AND annotated `AnnAssign` (`self._x: T = x`) — and confirmed to flag both while
passing the real constructor. The `AnnAssign` branch was added after an adversarial reviewer
noted the first draft only handled bare `Assign`: the same "first codification mandates only
the positive pole" tendency 0010 identified. Transform-on-store RHS (`self._x = x or default`)
is deliberately NOT flagged — the transform IS consumption.

## For Discussion

1. The guard is per-constructor (one test per facade). Is a generalized reviewer-lens or a
   reusable test-factory (`assert_all_params_consumed(SomeClass.__init__)`) worth extracting to
   a validation-patterns skill so any multi-param facade SDK-wide inherits it, or does the
   per-facade explicit test better survive refactors than a factory that hides the assertion?
2. Counterfactual: had the #1899 fix shipped this guard, #1926 and #1927 would have been caught
   at authoring time (the guard would have failed the moment the param was added stored-only).
   Does that argue every documented-kwarg fix MUST land its class's structural guard in the same
   PR (generalizing `autonomous-execution.md` fix-immediately-same-class), rather than fixing the
   instance and leaving the class open?
3. Cross-SDK: the Rust SDK's equivalent facade (if any) has the same class exposure. Is a
   language-neutral "every documented constructor param reaches a consumer" invariant a
   cross-SDK conformance lens, or is the AST-walk too Python-shaped to port to a `syn`-based
   Rust equivalent cheaply?
