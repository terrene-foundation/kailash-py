# Risks & Edge Cases

## Risk 1 — LLM unavailable at agent-creation time

**Failure mode:** No `OPENAI_API_KEY` set, or network error, or rate-limit on the
configured provider. `_generate_role_based_traits` raises mid-`create_specialized_agent`.

**Disposition:** Honest failure. Per `rules/agent-reasoning.md` Rule 1, a
deterministic fallback to the keyword classifier is BLOCKED. The user has two
escape hatches:

1. Pass `behavior_traits` in `config` — derivation is skipped (line 487 `if "behavior_traits" not in specialized_config`).
2. Configure a working LLM provider via `.env` (the canonical Kaizen setup).

The error message MUST cite both escape hatches so the user can act:

```
RuntimeError: trait derivation failed for role 'X' — pass behavior_traits=...
in config to skip derivation, or verify .env has a working LLM provider key.
Underlying: <original error>
```

## Risk 2 — Empty / malformed LLM output

**Failure mode:** LLM returns an empty string, or comma-separated output that
parses to zero traits.

**Disposition:** Fall back to the same default trait list users get today
(`["professional", "reliable", "adaptive"]`). This is NOT a Rule 1 violation — it
is the empty-output guard, identical in spirit to the existing default branch's
behavior. Log at WARN with the role and the malformed output (per
`rules/observability.md` Rule 8 — schema-revealing field names at DEBUG; role
strings are user-supplied free-form text, not schema, so WARN is fine here).

## Risk 3 — Cache pollution across instances

**Failure mode:** Two `Kaizen()` instances in the same process derive different
traits for the same role (e.g., one configured with gpt-4, the other with
gpt-4o-mini, returning slightly different lists).

**Disposition:** ACCEPTED. Cache is per-instance (per user direction). Cross-instance
consistency is out of scope for this issue. Users who need it can pass
`behavior_traits` explicitly OR construct one shared `Kaizen` instance.

## Risk 4 — Test sweep impact (8 files reference `behavior_traits`)

**Failure mode:** Existing Tier-1 unit tests that call `create_specialized_agent`
without supplying `behavior_traits` start hitting the LLM. Tests become slow,
nondeterministic, and require API keys.

**Disposition:** Audit each of the 8 test files; for each `create_specialized_agent`
call, EITHER add an explicit `behavior_traits=[...]` to the config (preferred for
unit tests — fast, deterministic, no LLM), OR migrate the test to Tier 2 with a
real LLM. Add ONE new Tier-2 test specifically exercising the LLM-derivation path
(per acceptance criterion #2). One-shard sweep per `rules/orphan-detection.md`
Rule 4 (API change MUST sweep tests in same PR).

## Risk 5 — `test_issue_822_behavior_traits_render.py:67-91` regression test

**Failure mode:** The existing #822 regression test at line 88 asserts:

```python
assert any(t in agent.behavior_traits for t in ["analytical", "thorough", "evidence_based", "methodical"])
```

This passes ONLY because the CURRENT keyword classifier returns those exact
strings for `role="research analyst"`. The docstring (line 73-77) explicitly
acknowledges this pins the Rule-1-violating behavior pending fix.

**Disposition:** Replace the exact-string assertion with a shape-only assertion
matching acceptance criterion #2:

```python
assert isinstance(agent.behavior_traits, list)
assert len(agent.behavior_traits) > 0
assert all(isinstance(t, str) and t.strip() for t in agent.behavior_traits)
```

Update the docstring to remove the Rule-1-violation note. Move the test to Tier 2
(it now requires a real LLM).

## Risk 6 — Spec drift (`specs/kaizen-core.md`)

**Failure mode:** Acceptance criterion #4 mandates spec update at "specs/kaizen-core.md
§ Agent class". If the spec is updated BEFORE code lands, we ship a phantom citation
(spec describes LLM derivation; code still does keyword matching) violating
`rules/spec-accuracy.md` Rule 5 ("Spec content describes ONLY behavior shipped on
main").

**Disposition:** Spec edit lands in the SAME PR as the code change, not before.
Same-commit pairing per `rules/specs-authority.md` Rule 5.

## Risk 7 — Cross-SDK parity (kailash-rs)

**Failure mode:** kailash-rs may have an analogous role-based trait derivation in
its Kaizen binding. Per `rules/cross-sdk-inspection.md` Rule 1, when an issue is
fixed in one BUILD repo, MUST inspect the other.

**Disposition:** Cross-SDK inspection is OUT OF LANE for this kailash-py session
per `rules/repo-scope-discipline.md`. File a follow-up todo (mirroring the #822
todo 3.3 disposition pattern) for a future kailash-rs session. Do NOT file the
issue from this session.

## Edge case — Role string normalization

Cache key is `role.strip().lower()`. Two trivial-variant roles map to the same
cache slot:

- `"Research Analyst"` → `"research analyst"`
- `" research analyst "` → `"research analyst"`
- `"research analyst"` → `"research analyst"`

Aggressive semantic merging (e.g., `"investigator"` → `"researcher"`) is
deliberately NOT done — that is the LLM's job, and each distinct role string
gets its own derivation. Document the normalization rule in
`specs/kaizen-core.md` so users understand cache behavior.

## Edge case — Concurrent `create_specialized_agent` calls for same role

Two threads / async tasks call `create_specialized_agent("a1", "X", {})` and
`create_specialized_agent("a2", "X", {})` simultaneously. Both miss the cache;
both fire LLM calls; both write to `self._trait_cache[<key>]`.

**Disposition:** Race is benign — temperature=0 means both derivations produce
the same output, and the dict `setdefault`-equivalent write is idempotent. The
extra LLM call is wasteful but not incorrect. If contention becomes a real cost,
add a per-key lock in a follow-up. Document the trade-off in the spec.
