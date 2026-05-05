# Design Options

## Constraint summary

1. `Kaizen.create_specialized_agent` is sync — cannot turn into `async def` without
   breaking every existing caller (per `rules/patterns.md` Paired Public Surface
   rule).
2. `agent.behavior_traits` is `List[str]` — public contract, MUST NOT change
   shape.
3. Trait derivation MUST be LLM-first per `agent-reasoning.md` Rule 1 (no
   keyword fallback, no dispatch table, no embedding-similarity classification).
4. Cache is per-Kaizen-instance keyed by role string (per user direction).
5. Determinism via temperature=0 + cache (per user direction).
6. User-supplied `behavior_traits` in config still bypasses derivation (existing
   escape hatch — preserves deterministic / test-friendly path).

## Options considered

### Option A — Sync Signature + sync `BaseAgent.run()` inside the existing method (RECOMMENDED)

Define a `RoleToTraitsSignature(Signature)` with `role: str` input and
`traits: list[str]` output. Construct a one-shot `BaseAgent` configured with
`temperature=0` and the Kaizen instance's default model; invoke `agent.run(role=...)`
synchronously; cache the result on `self._trait_cache: dict[str, list[str]]`.

```python
class _RoleToTraitsSignature(Signature):
    role: str = InputField(description="Agent role description (free-form natural language)")
    traits: list[str] = OutputField(
        description="3-5 behavioral traits the agent should embody, "
                    "as adjectives or short descriptors (e.g. analytical, "
                    "decisive, methodical). Output a list of strings.",
    )

def _generate_role_based_traits(self, role: str) -> List[str]:
    cache_key = role.strip().lower()
    if cache_key in self._trait_cache:
        return self._trait_cache[cache_key]

    trait_agent = BaseAgent(
        signature=_RoleToTraitsSignature,
        config={"model": self._default_model, "temperature": 0},
    )
    result = trait_agent.run(role=role)
    traits = list(result.traits) if result.traits else ["professional", "reliable", "adaptive"]
    self._trait_cache[cache_key] = traits
    return traits
```

**Pros:**

- Sync inside sync — no caller breakage.
- Cache on Kaizen instance — first call per role hits LLM, subsequent identical
  roles return instantly.
- Temperature=0 + cache → deterministic per (instance, role).
- Single LLM call per novel role per instance — bounded cost.
- Backwards-compatible: shape preserved; user-supplied traits still skip the LLM.

**Cons / open considerations:**

- **First-time latency.** First `create_specialized_agent("X", "novel role", {})`
  blocks on an LLM round-trip. For most apps this is fine (agent creation is a
  setup-time concern). Document in spec.
- **Network failure mode.** If the LLM call raises (no API key, network error,
  rate limit), the trait derivation fails and `create_specialized_agent` raises.
  This is honest — Rule 1 forbids deterministic fallback to a keyword classifier.
  The escape hatch is the same as it has always been: pass `behavior_traits` in
  config to skip derivation.
- **Cache key normalization.** `role.strip().lower()` dedupes trivial variants
  ("Research Analyst" vs " research analyst "). Not aggressive enough to merge
  semantic synonyms ("investigator" vs "researcher") — that is correct: the
  LLM derives traits per role; only EXACT-match (post-normalization) hits cache.
- **Empty / unparseable LLM output.** If the LLM returns an empty list, fall back
  to the same default-trait list users get today (`["professional", "reliable",
"adaptive"]`). This is NOT a Rule 1 violation — it is the
  empty-output guard, identical to the existing default branch's behavior.

### Option B — Fully async, break the calling method

Make `create_specialized_agent` async, use `await trait_agent.run_async(role=...)`.

**Rejected**: every existing caller (production + tests) breaks. Acceptance
criterion #3 ("no breaking change") forbids this.

### Option C — Companion async method

Keep `create_specialized_agent` sync (calling existing keyword classifier) and
add `create_specialized_agent_async` that uses LLM-first derivation.

**Rejected**: doubles the public API surface, leaves the Rule 1 violation in
the sync path, exact "both shapes" anti-pattern called out in
`rules/patterns.md` Paired Public Surface rule.

### Option D — Pre-derive at Kaizen init for a hardcoded role taxonomy

Build a fixed role taxonomy at Kaizen instance startup, derive traits for each
known role once, cache eagerly.

**Rejected**: still hardcoded classification (which roles exist) — moves the Rule 1
violation up one level. Also fails on novel roles users invent.

### Option E — Inject a trait-derivation Signature class as a Kaizen constructor arg

Let the user inject their own `RoleToTraitsSignature` subclass at Kaizen init.

**Rejected for THIS issue**: user-injection is a reasonable extensibility hook
(config-time DI), but it is a new feature outside the issue's scope. Out-of-scope
per brief. Could be a follow-up.

## Recommendation: Option A

The single design point left to verify with kaizen-specialist patterns is the
exact `BaseAgent` construction shape — do we instantiate a stand-alone
`BaseAgent`, or is there an existing one-shot Signature → completion primitive
on Kaizen that's lighter? See `02-plans/01-architecture.md` for the wiring detail.
