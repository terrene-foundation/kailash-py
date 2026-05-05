# DISCOVERY — Tier-1 conftest stub replaces 36 call-site edits

**Date:** 2026-05-06
**Phase:** /implement
**Status:** Recorded

## Finding

Todo 1.4 anticipated mechanically editing every `create_specialized_agent(...)`
call site lacking explicit `behavior_traits` to add a deterministic
trait list — 36 NEEDS-FIX call sites across 8 files.

The implementation collapsed this to a single new file:
`packages/kailash-kaizen/tests/unit/conftest.py` — an autouse fixture that
monkeypatches `Kaizen._generate_role_based_traits` to return a fixed
`["professional", "reliable", "adaptive"]` list for the duration of any
Tier-1 unit test.

```python
@pytest.fixture(autouse=True)
def _stub_trait_derivation(monkeypatch):
    from kaizen.core.framework import Kaizen
    def _stub(self, role): return ["professional", "reliable", "adaptive"]
    monkeypatch.setattr(Kaizen, "_generate_role_based_traits", _stub)
```

The stub's scope is exactly `tests/unit/` — Tier-2 integration and Tier-3 e2e
tests live below their own conftests and DO NOT inherit it; trait derivation
runs against the real LLM there.

## Why this matters

1. **Cost reduction.** 36 edits → 1 edit. Every Tier-1 test that relies on
   the default-derivation path becomes deterministic without touching the
   test file.

2. **Test resilience.** If a future change adds new `create_specialized_agent`
   call sites in Tier-1 tests, they automatically pick up the stub — no
   maintenance burden.

3. **Tier separation enforced structurally.** Per `rules/testing.md`
   § "3-Tier Testing", Tier 1 may mock; Tier 2 may not. The conftest
   placement (`tests/unit/`) makes the mocking scope match the testing-tier
   boundary mechanically.

4. **One additional surgical edit was still required.** The keyword-pinning
   test `test_specialized_agent_role_based_behavior_traits` at
   `tests/unit/test_kaizen_multi_agent_coordination.py:458` was rewritten
   in-place (not just stubbed) because its assertion explicitly required
   `"thorough" in traits` etc. — the stub's `["professional", "reliable",
"adaptive"]` doesn't contain those strings. Per
   `rules/orphan-detection.md` Rule 4a (stub implementation MUST sweep
   deferral tests in same commit), this rewrite was mandatory regardless of
   the conftest stub.

## Trade-off

The conftest stub means Tier-1 unit tests no longer exercise the actual
`_generate_role_based_traits` implementation — only the surface contract
(method exists, returns `list[str]`, doesn't raise). The actual derivation
logic is exercised in:

- `tests/integration/test_role_to_traits_llm_derivation.py` — Tier-2 (real LLM)
- `tests/integration/test_role_traits_cache_wiring.py` — Tier-2 (cache hit)
- `tests/regression/test_issue_822_behavior_traits_render.py::test_behavior_traits_default_from_role` — Tier-2 (regression)

Total Tier-2 coverage: 6+ tests directly hitting the new derivation path,
plus 2 cache-wiring assertions on `BaseAgent.run` non-invocation. Sufficient
per `rules/facade-manager-detection.md` Rule 1 (Tier-2 test exercises the
wired path against real infrastructure).

## Connection

- `rules/orphan-detection.md` Rule 4 (API change MUST sweep tests in same PR)
  — sweep is structural (conftest), not file-by-file.
- `rules/testing.md` § "3-Tier Testing" — Tier 1 mocks allowed; conftest
  stub is the canonical Tier-1 mocking pattern when an internal method
  becomes externally-side-effecting.
- `01-analysis/02-risks-and-edges.md` Risk 4 (test sweep impact) — disposition
  changed from "audit each of the 8 audit files; for each call site
  categorize and add explicit `behavior_traits`" to "single conftest stub at
  Tier-1 + targeted rewrite of the one keyword-pinning test."
