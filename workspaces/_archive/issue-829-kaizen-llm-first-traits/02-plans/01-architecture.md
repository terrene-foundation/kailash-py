# Architecture Plan — Issue #829

## Goal

Replace `Kaizen._generate_role_based_traits` keyword-matching classifier with an
LLM-first Signature-driven derivation, satisfying `rules/agent-reasoning.md`
Rule 1 while preserving the existing `agent.behavior_traits: list[str]` contract.

## Approach (Option A from `01-analysis/01-research/02-design-options.md`)

### Step 1 — Define the trait-derivation Signature

New module: `packages/kailash-kaizen/src/kaizen/core/_role_traits_signature.py`

```python
from kaizen.signatures import InputField, OutputField, Signature


class RoleToTraitsSignature(Signature):
    """LLM-first derivation of behavioral traits from an agent role description."""

    role: str = InputField(
        description="Agent role description (free-form natural language). "
                    "Examples: 'data analyst', 'creative copywriter', "
                    'machine learning researcher", "compliance auditor".'
    )
    traits_csv: str = OutputField(
        description="Comma-separated list of 3 to 5 behavioral traits this "
                    "agent should embody. Each trait is one to three words, "
                    "lowercase, snake_case if multi-word "
                    "(e.g., 'analytical, evidence_based, methodical'). "
                    "Output ONLY the traits, comma-separated, no prose."
    )
```

`traits_csv: str` — declared as a string output (no `list[str]` Signature support
verified in current Kaizen primitives). Parse to `list[str]` after the call.

### Step 2 — Replace `_generate_role_based_traits` body

`packages/kailash-kaizen/src/kaizen/core/framework.py:513-536`

```python
def _generate_role_based_traits(self, role: str) -> List[str]:
    """LLM-first derivation of behavior traits from agent role.

    Cached per Kaizen instance keyed by normalized role (strip + lower).
    Temperature=0 + cache → deterministic per (instance, role) pair.

    Falls back to a default trait list ONLY when the LLM returns empty
    output (NOT when it returns content that maps to a different bucket).
    Failures (no API key, network error) propagate per
    rules/agent-reasoning.md Rule 1 — no deterministic fallback.

    Pass behavior_traits in config to skip derivation entirely.
    """
    cache_key = role.strip().lower()
    cached = self._trait_cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        agent = BaseAgent(
            signature=RoleToTraitsSignature,
            config={
                "model": self._default_model,  # resolves from .env per env-models.md
                "temperature": 0,
            },
        )
        result = agent.run(role=role)
    except Exception as e:
        raise RuntimeError(
            f"trait derivation failed for role {role!r} — pass "
            f"behavior_traits=[...] in config to skip derivation, or verify "
            f".env has a working LLM provider key. Underlying: {e}"
        ) from e

    traits_csv = (result or {}).get("traits_csv", "")
    parsed = [t.strip() for t in traits_csv.split(",") if t.strip()]

    if not parsed:
        logger.warning(
            "kaizen.trait_derivation.empty_output",
            role=role,
            raw_output=traits_csv,
        )
        parsed = ["professional", "reliable", "adaptive"]

    self._trait_cache[cache_key] = parsed
    return parsed
```

### Step 3 — Add cache + default-model attribute on Kaizen instance

`Kaizen.__init__` additions (preserving sync init):

```python
self._trait_cache: Dict[str, List[str]] = {}
# self._default_model already exists (resolves from .env per env-models.md)
```

### Step 4 — Test sweep

Per `rules/orphan-detection.md` Rule 4, the API change sweeps tests in the SAME PR:

1. `tests/regression/test_issue_822_behavior_traits_render.py:67-91` —
   `test_behavior_traits_default_from_role`: replace exact-string assertion with
   shape-only assertion. Update docstring (remove Rule-1-violation note). Move
   to Tier 2 if Tier-1 pyproject excludes LLM tests.

2. Audit the other 8 files referencing `behavior_traits`. For each
   `create_specialized_agent(..., config={})` (no traits) call: add explicit
   `behavior_traits=[...]` to config. Tier-1 tests stay deterministic.

3. NEW `tests/integration/test_role_to_traits_llm_derivation.py` — Tier-2
   integration test exercising LLM derivation against a real provider for two
   roles ("machine learning researcher" and "data analyst"). Asserts SHAPE
   only (per acceptance criterion #2): `list[str]`, non-empty, lowercase string
   members.

4. NEW `tests/integration/test_role_traits_cache_wiring.py` — Tier-2 test that
   calls `create_specialized_agent` twice with the same role, asserts the second
   call does NOT re-invoke the LLM (via timing or call-count assertion against a
   spy on `BaseAgent.run`).

### Step 5 — Spec update (`specs/kaizen-core.md` § Agent class)

Same-commit pairing per `rules/specs-authority.md` Rule 5. Update the Agent
class section to document:

- `agent.behavior_traits: list[str]` derivation contract (LLM-first via
  `RoleToTraitsSignature`)
- Per-instance cache keyed by `role.strip().lower()`
- Determinism via `temperature=0` + cache
- Failure mode: raises `RuntimeError` if LLM unavailable; user can pass
  `behavior_traits` in config to skip derivation
- Concurrent-call race is benign (idempotent cache write, deterministic output)

NO split-state framing — describe what ships in the same PR, full stop. Per
`rules/spec-accuracy.md` Rule 1, every cited symbol resolves at merge time.

## Sharding

Single shard per `rules/autonomous-execution.md`:

- LOC: ~50 lines (Signature module + framework method body + cache init)
- Invariants: 4 (sync surface preserved, list[str] shape, cache keying,
  Rule-1 compliance)
- Call-graph hops: 1 (framework.py → BaseAgent.run → provider)
- Feedback loop: pytest unit + integration (real LLM)
- Describable in 3 sentences: "Replace `_generate_role_based_traits` body with
  Signature-driven LLM call. Cache results on `self._trait_cache`. Sweep 8 test
  files + add 2 Tier-2 tests + update spec/CHANGELOG."

Single shard. No parallel worktrees needed.

## Out of scope

- Sibling hardcoded methods elsewhere in `framework.py` (per brief).
- User-injectable Signature (deferred — Option E in design-options).
- Cross-instance / cross-process cache (per user direction).
- Cross-SDK kailash-rs audit (out-of-lane per `rules/repo-scope-discipline.md`).
  File a deferred follow-up todo, mirroring the #822 todo 3.3 disposition.

## Brief traceability

| Acceptance criterion (issue #829)                                                  | Plan step       |
| ---------------------------------------------------------------------------------- | --------------- |
| `_generate_role_based_traits` replaced with `Signature`-driven derivation          | Steps 1, 2      |
| Tier-2 test: role "machine learning researcher" → trait list (shape, not contents) | Step 4 #3       |
| Tier-2 test: existing default-trait callers continue to work — no shape break      | Steps 3, 4 #1–2 |
| Spec updated at `specs/kaizen-core.md` § Agent class                               | Step 5          |

## Open questions for the user

1. **Spec section name.** `specs/kaizen-core.md` has an existing § for the
   Agent class — is that the intended target, or should the trait-derivation
   contract live in `specs/kaizen-signatures.md`? My read: `kaizen-core.md` is
   correct (the trait derivation is a Kaizen-instance behavior, not a Signature-
   library concern). Confirm or redirect.

2. **CHANGELOG entry version.** This is a `kaizen-kaizen 2.19.x` patch (post-
   2.19.0). Confirm 2.19.1 (no API change, behavior change) vs 2.20.0 (the LLM
   call changes failure mode from silent default to raise — arguably minor bump).
   My read: 2.20.0 (behavior change is observable enough to warrant a minor).

3. **Cross-SDK follow-up todo creation.** Same pattern as #822 todo 3.3 — file
   a deferred local todo (gitignored), do NOT file an issue against
   `esperie/kailash-rs` from this session. Confirm this is the intended pattern.
