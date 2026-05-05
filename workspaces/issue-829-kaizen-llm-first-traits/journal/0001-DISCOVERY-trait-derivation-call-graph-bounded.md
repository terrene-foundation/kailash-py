# DISCOVERY — Trait derivation has exactly one call site, sync-bounded

**Date:** 2026-05-06
**Phase:** /analyze
**Status:** Recorded

## Finding

`Kaizen._generate_role_based_traits` has exactly ONE call site across the entire
`packages/kailash-kaizen/` source tree:

```
packages/kailash-kaizen/src/kaizen/core/framework.py:488
    specialized_config["behavior_traits"] = self._generate_role_based_traits(role)
```

It is invoked inside `Kaizen.create_specialized_agent` only when the user did
NOT supply `behavior_traits` in `config`. The user-supplied path (line 487
`if "behavior_traits" not in specialized_config`) is the existing escape hatch
and remains untouched by this fix.

## Why this matters

Three implications for the implementation:

1. **Blast radius is small.** A single-call-site fix means there's no risk of
   "different invocations expect different shapes." We change one method body;
   the contract is `(role: str) -> list[str]`.

2. **The escape hatch survives.** Users / tests that pass explicit
   `behavior_traits=[...]` continue to bypass derivation entirely. Tier-1 unit
   tests can stay deterministic and fast by always passing explicit traits;
   only NEW Tier-2 tests need to exercise the LLM path.

3. **`create_specialized_agent` MUST stay sync.** This binds the implementation
   to `BaseAgent.run()` (sync) over `BaseAgent.run_async()`. Per
   `rules/patterns.md` "Paired Public Surface — Consistent Async-ness", a sync
   surface that internally calls `asyncio.run()` is BLOCKED — the sync-on-sync
   pairing is the only correct shape.

## Connection to #822

This fix is the carry-forward from `workspaces/issue-822-kaizen-typing-cascade/
todos/completed/3.4-llm-first-traits-followup-issue.md` (filed 2026-05-05 as
issue #829). The #822 regression test
`tests/regression/test_issue_822_behavior_traits_render.py:67-91` already
documents the Rule-1 violation in its docstring and pins the CURRENT
keyword-classifier output. That test's exact-string assertion will fail under
LLM derivation and is one of the in-scope sweeps.

## Connection to existing Kaizen primitives

The fix wires onto existing infrastructure with zero new public API surface:

- `kaizen.signatures.Signature` — already exported (`kaizen/__init__.py:241-242`).
- `kaizen.core.BaseAgent.run()` — sync (`base_agent.py:302`), returns
  `Dict[str, Any]`. Async variant exists at line 314.
- Existing Signature examples in `kaizen/agent_types.py:82-132` use string
  outputs; no example declares `list[str]`. The implementation declares
  `traits_csv: str = OutputField(...)` and parses post-call to avoid unverified
  structured-output territory.
