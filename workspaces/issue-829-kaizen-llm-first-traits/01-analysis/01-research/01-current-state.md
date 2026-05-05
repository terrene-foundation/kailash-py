# Current State — `_generate_role_based_traits`

## Source location

`packages/kailash-kaizen/src/kaizen/core/framework.py:513-536`

```python
def _generate_role_based_traits(self, role: str) -> List[str]:
    """Generate behavior traits based on agent role."""
    role_lower = role.lower()

    # Research-focused roles
    if any(word in role_lower for word in ["research", "analyze", "study"]):
        return ["thorough", "analytical", "evidence_based", "methodical"]

    # Creative roles
    elif any(word in role_lower for word in ["creative", "design", "innovative"]):
        return ["innovative", "divergent", "imaginative", "flexible"]

    # Leadership/coordination roles
    elif any(word in role_lower for word in ["lead", "manage", "coordinate", "moderate"]):
        return ["decisive", "communicative", "collaborative", "strategic"]

    # Technical roles
    elif any(word in role_lower for word in ["technical", "develop", "engineer"]):
        return ["precise", "logical", "systematic", "detail_oriented"]

    # Default traits
    return ["professional", "reliable", "adaptive"]
```

Five hardcoded buckets + a default. Direct violation of `agent-reasoning.md` Rule 1
("hardcoded classification of agent input" is BLOCKED).

## Call sites

Single call site:

`framework.py:488` inside `Kaizen.create_specialized_agent`:

```python
# Add role-based behavior traits if not present
if "behavior_traits" not in specialized_config:
    specialized_config["behavior_traits"] = self._generate_role_based_traits(role)
```

Two-line escape hatch — when the user passes `behavior_traits` in `config`, derivation
is skipped entirely. This is the pre-existing path for deterministic / explicit traits
and we preserve it.

## Calling-method async-ness

`Kaizen.create_specialized_agent` is **synchronous** (`def`, not `async def` —
`framework.py:439`). Per `rules/patterns.md` "Paired Public Surface — Consistent
Async-ness", we cannot mix sync entry / async dependency without breaking callers.
The replacement MUST work inside a sync method.

## Downstream consumption

`framework.py:545-547` reads `agent.behavior_traits` to render into the system
prompt:

```python
if hasattr(agent, "behavior_traits") and agent.behavior_traits:
    traits = ", ".join(agent.behavior_traits)
    role_context += f"Your approach should be {traits}. "
```

Contract: `agent.behavior_traits` is a `List[str]`. The new derivation MUST return
the same shape — no breaking change to downstream consumers.

## Test coverage that touches `behavior_traits`

```
packages/kailash-kaizen/tests/unit/test_kaizen_multi_agent_coordination.py
packages/kailash-kaizen/tests/unit/test_integration_test_infrastructure.py
packages/kailash-kaizen/tests/unit/test_kaizen_core_feature_completion.py
packages/kailash-kaizen/tests/integration/test_kaizen_core_feature_integration.py
packages/kailash-kaizen/tests/integration/test_enterprise_methods_integration.py
packages/kailash-kaizen/tests/integration/test_integration_test_fixes_validation.py
packages/kailash-kaizen/tests/regression/test_issue_822_behavior_traits_render.py
packages/kailash-kaizen/tests/e2e/test_real_kaizen_e2e.py
packages/kailash-kaizen/tests/e2e/test_kaizen_multi_agent_e2e.py
```

The two cases that MUST change:

1. `tests/regression/test_issue_822_behavior_traits_render.py:67-91`
   (`test_behavior_traits_default_from_role`) explicitly pins the CURRENT
   keyword-matched output (`["analytical", "thorough", "evidence_based",
"methodical"]`) for the role `"research analyst"`. The docstring already calls
   out the Rule 1 violation and notes the test "pins the CURRENT behavior so the
   trait-rendering chain remains exercised." Under LLM derivation, this exact
   assertion will fail nondeterministically. **Replace** with a shape-only
   assertion (per acceptance criterion #2: "trait list contains LLM-derived
   traits — assertion on shape, not exact contents").

2. Tier-1 unit tests that call `create_specialized_agent` without supplying
   `behavior_traits` will start hitting the LLM — they need EITHER an explicit
   `behavior_traits=...` config to skip derivation, OR migration to Tier 2.
   Decision lives in the plan: prefer the explicit-traits config in unit tests
   (cheaper, deterministic) and add a NEW Tier 2 test for the LLM derivation path.

## Specs in scope

- `specs/kaizen-core.md` — primary update target (Agent class section per acceptance
  criterion #4).
- `specs/kaizen-signatures.md` — no edit needed; we use existing `Signature` /
  `InputField` / `OutputField` primitives without altering the signature contract.

## Existing public surface for the LLM-first replacement

`kaizen/__init__.py:241-242` re-exports `Signature`, `InputField`, `OutputField`.
The Signature → `BaseAgent.run()` pattern is the canonical Kaizen primitive for
LLM-driven classification (see `rules/agent-reasoning.md` Rule 3 example).
