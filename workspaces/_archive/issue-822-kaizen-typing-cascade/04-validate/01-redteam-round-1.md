# Red Team Round 1 — Issue #822 Architecture Plan

**Workspace:** `workspaces/issue-822-kaizen-typing-cascade/`
**Reviewer:** analyst (red team)
**Date:** 2026-05-05
**Verdict:** APPROVE_WITH_REVISIONS

---

## Dimension 1 — Cluster A vs Cluster B reconciliation (LOW)

**FINDING:** Reconciliation in `02-plans/01-architecture.md:42-46` is mechanically correct.

Verified: `framework.py:1283-1343` — `Kaizen.config` returns `KaizenConfig` (raw dataclass, no `.get`) ONLY when `_config_was_object` is True (explicit-`KaizenConfig(...)` construction path); otherwise returns `ConfigWrapper(dict)` which has `.get`. At `agents.py:455-459`, the `hasattr(self.kaizen.config, "get")` guard returns False on the explicit-KaizenConfig path → gate flips False → signature-required raise NEVER fires for explicit-`KaizenConfig` callers. Cluster A's "real bug" framing (#9) and Cluster B's "wrapper has .get, hasattr is correct" framing are BOTH true under different construction paths. Plan's reconciliation language ("broken ONLY for explicit-KaizenConfig callers") is accurate.

---

## Dimension 2 — Shard sizing (MEDIUM)

**FINDING:** Shard 2 LOC accounting is loose; total is closer to ~310 LOC, still within budget.

Verified line ranges:

- `expose_as_mcp_server` `agents.py:2369-2467` (~99 LOC)
- `expose_as_mcp_tool` `agents.py:2469-~2614` (~145 LOC; plan says ~74)
- `connect_to_mcp_servers` `agents.py:2778-~2899` (~121 LOC; plan says ~120)
- `call_mcp_tool` `agents.py:~2900-2914` (~15 LOC; plan says ~60 — overstated)
- `_discover_servers` `agents.py:2937-2965` (~29 LOC)
- `discover_mcp_tools` external branch `framework.py:1512-1531` (~20 LOC)
- `mcp_registry` property `framework.py:1345-~1355` (~11 LOC)

Sum: ~440 LOC of deletions (not 250). Plus test deletions across ≥5 test files (`test_agents_comprehensive.py`, `test_mcp_integration_missing.py`, `test_agent_execution_patterns_e2e.py`, `tests/unit/test_*discover_mcp*`, `scripts/comprehensive_implementation_tester.py`) plus CHANGELOG entry plus `__all__` reconciliation in `kaizen/core/agents.py` if exported. Still fits Rule 1 (deletion-heavy boilerplate per `autonomous-execution.md` § 2 — "Boilerplate scales ~5× further") but plan should restate as "~440 LOC deletion + test sweep" not "~250 LOC".

**RECOMMENDED AMENDMENT** to `01-architecture.md:18`: change "LOC: ~250" → "LOC: ~440 deletions + test sweep" and at `:240`: "LOC: ~250" → "LOC: ~440".

---

## Dimension 3 — Hidden orphan callers / migration targets (HIGH)

**FINDING:** Plan's CHANGELOG migration text (`01-architecture.md:204-209`) cites `kailash-mcp` and `kaizen.mcp.catalog_server.MemoryRegistry` as migration targets WITHOUT verifying these exist or are usable.

Concerns:

1. **`kailash-mcp` package** — Cluster C did not verify this is a published, importable package. If it does not exist or is empty, the migration text is a phantom citation per `rules/spec-accuracy.md` Rule 1 (every CHANGELOG file/path/symbol MUST resolve). The plan must include a verification step before `/implement`.
2. **`kaizen.mcp.catalog_server.MemoryRegistry`** — Cluster C 02-cluster line citing this as Registry alternative was not re-verified by the architecture plan. CHANGELOG copy at `01-architecture.md:206-209` advertises it as the migration path.
3. **`kaizen.__init__.py:16-20`** exports `Agent` from `kaizen_agents` (async Agent) when installed, falls back to `kaizen.core.agents.Agent` (CoreAgent) otherwise. The 5 deleted methods live on CoreAgent. If `kaizen-agents` is installed (the typical case), `kaizen.Agent` users **never see** these methods at all — public-API removal severity is LOWER than plan claims for that user segment, and HIGHER (full break) for users on CoreAgent fallback. Plan's Shard 2 "Recommendation: 2.19.0 minor bump" reasoning at `:308-309` does not engage this asymmetry.

**RECOMMENDED AMENDMENT** to `01-architecture.md`:

- Add a pre-`/implement` verification gate enumerating: `pip show kailash-mcp` returns metadata; `python -c "from kaizen.mcp.catalog_server import MemoryRegistry"` succeeds. If either fails, REWORK CHANGELOG to remove the phantom citation per Rule 1.
- Amend §"Why one shard" of Shard 2 to acknowledge Agent-fallback asymmetry: "When `kaizen-agents` is installed, `kaizen.Agent` resolves to `kaizen_agents.Agent` and the deleted CoreAgent methods are not user-visible. The breakage surface is users on CoreAgent fallback (no `kaizen-agents` install)."

---

## Dimension 4 — Public-API removal severity / Rule 6a applicability (MEDIUM)

**FINDING:** Plan's "no deprecation cycle because never worked" argument at `:302-306` is correct in principle but `rules/zero-tolerance.md` Rule 6a does not encode this exception. Rule 6a BLOCKED-rationalizations list explicitly names "The removed API was rarely used" and "Spec §X never documented the parameter" as BLOCKED — it does NOT exempt "never functioned."

Reading Rule 6a carefully: "Public-API removal MUST land with a `DeprecationWarning` shim covering at least one minor cycle." The rule text grants no exception for "never worked." The plan's argument that Rule 2 (no fake integration) supersedes is reasonable but is the **plan's interpretation**, not the rule's text.

**Verified:** No occurrences of `expose_as_mcp_server`, `connect_to_mcp_servers`, `mcp_registry`, etc. in any `kailash-kaizen/src/**/__init__.py`'s `__all__` list — symbols are reachable via attribute access on `Agent`/`Kaizen` only, not exported.

**RECOMMENDED AMENDMENT** to `01-architecture.md` Open Questions §1 (line 302):

- Add explicit human-gate question: "Rule 6a text does not exempt 'never functioned' APIs. Approve hard-removal in 2.19.0 with the runtime-evidence justification documented in CHANGELOG (`from ..mcp.registry import get_global_registry` always failed, `mcp_registry` property always returned `None`), OR ship a `DeprecationWarning` shim in 2.19.0 + remove in 2.20.0?" — surfacing the rule-vs-plan tension so the human gate decides explicitly per `rules/communication.md` ("Frame Decisions as Impact").

---

## Dimension 5 — `signature_programming_enabled` gate fix correctness (MEDIUM)

**FINDING:** Plan's proposed fix at `01-architecture.md:84-93` has correctness gaps:

1. The `getattr(self.kaizen.config, "signature_programming_enabled", ...)` form first checks the dataclass attribute. `KaizenConfig` MUST declare `signature_programming_enabled` as a field; if missing or typo'd, `getattr` returns the fallback (ConfigWrapper.get which returns False). Plan does not verify `KaizenConfig` has this exact field name.
2. **Config-refresh semantics:** The gate reads `self.kaizen.config` at every `_execute_direct_llm` invocation. If user calls `kaizen.configure(signature_programming_enabled=True)` AFTER `Agent()` construction, the gate fires correctly because the property is read fresh — but plan does not document this is intentional vs accidental behavior.
3. **Typo'd dict keys:** A user passing `{"signature_programing_enabled": True}` (typo) gets silent False — same failure mode as before. Plan does not propose declaring the canonical key set or warning on unknown keys (Rule 3c kwarg-consumption sibling).
4. **`KaizenConfig` without flag set:** `getattr(..., False)` correctly returns False; this is the documented "feature off" state. OK.

**RECOMMENDED AMENDMENT** to `01-architecture.md:84-93`:

- Verify `KaizenConfig.signature_programming_enabled` field exists (`grep signature_programming_enabled packages/kailash-kaizen/src/kaizen/core/config.py`). If absent, add the field declaration in same shard.
- Add Tier-2 regression for typo'd-key path: assert that an unknown key in a dict-config does NOT silently flip the gate, OR document that the gate IS False on unknown keys (current behavior).

---

## Dimension 6 — Cross-package `AgentTeam` edit (HIGH)

**FINDING:** `packages/kaizen-agents/src/kaizen_agents/patterns/core/teams.py` — verified file exists at the cited path. AT&T BUT `AgentTeam.__init__` raises `DeprecationWarning` (lines 48-55) directing users to `kaizen.orchestration.runtime.OrchestrationRuntime`. Plan proposes adding `conflict_resolution: str = "collaborative"` and `performance_optimization: bool = False` parameters to a deprecated class.

This is a meaningful design tension:

- Adding new typed kwargs to a deprecated class **extends** its public surface, which conflicts with deprecation discipline.
- The dynamic-attach pattern at `framework.py:824-825` may itself be the orphan that should be removed (alongside the deprecated class), not declared.

Additionally: `kaizen-agents` ships independently with its own version + PyPI release (`rules/build-repo-release-discipline.md` § 1). Plan's Shard 1 cross-package edit triggers a `kaizen-agents` release in the same session per § 1, which the plan does not enumerate. Plan §"Open Question 4" at line 314-318 says "in-lane" but does not address sibling-package release coordination.

**RECOMMENDED AMENDMENT** to `01-architecture.md`:

- Add a §"Cross-package release coordination" subsection: explicitly enumerate `kaizen-agents` in the release scope for Shard 1, verifying `main vs PyPI` per `build-repo-release-discipline.md` § 3.
- Reframe AgentTeam edit as one of: (a) extend the deprecated class with new kwargs (plan's current proposal — ship a `# pylint: disable` for "extending deprecated"), OR (b) leave AgentTeam unchanged and instead suppress pyright at `framework.py:824-825` (the cross-package attach site) since the class is deprecated anyway, OR (c) move the dynamic-attach into `OrchestrationRuntime` migration scope (out of #822). Recommend (b) given the deprecation context.

---

## Dimension 7 — Missing rules / cross-cutting (MEDIUM)

Findings against rules not addressed by plan:

1. **`rules/agent-reasoning.md` Rule 1 (LLM-First):** `_generate_role_based_traits` at `framework.py:505-528` is a 23-line if-else chain with `any(word in role_lower for word in [...])` keyword matching to assign behavior traits. The brief did not flag this; the plan's `behavior_traits` round-trip fix (Shard 1, item 7) preserves this anti-pattern. This violates `rules/agent-reasoning.md` ABSOLUTE RULE BLOCKED list. **HIGH severity** if the user requires LLM-first compliance; plan should at minimum file a follow-up issue.

2. **`rules/specs-authority.md` Rule 5b/5c:** Plan's spec-traceability doc says "All brief requirements map to existing `specs/kaizen-core.md` sections" but does NOT verify the citations resolve (the plan claims line 426 / 442 references). I did not run that grep; plan should include the verification command output per `spec-accuracy.md` Rule 1.

3. **`rules/orphan-detection.md` Rule 6 (`__all__` consistency):** Plan does not check whether `kaizen/core/agents.py` has `__all__` (it appears not to, since none of these symbols appear in any `__init__.py::__all__` per my Dim-4 verification). If `Agent` itself is exposed via `kaizen/__init__.py:16-20` to fallback users, the deletion is below-`__all__` surgery — fine, but plan should grep all `__init__.py` for `discover_mcp_tools|mcp_registry|expose_as_mcp` and document the empty result as evidence Rule 6a is not implicated.

4. **`rules/refactor-invariants.md` Rule 1:** Plan correctly mentions LOC invariant at `01-architecture.md:269-283`. GOOD. But the threshold "3000 LOC" is hand-typed; plan should compute the post-deletion line count and use post-deletion + 10-15% margin per the rule.

5. **`rules/upstream-issue-hygiene.md`:** Plan §Cross-SDK note at `:215-218` proposes filing an issue against `esperie/kailash-rs`. The "esperie/" org reference is correct per `cross-sdk-inspection.md` examples, but plan must NOT auto-file; Open Question 3 at `:310-313` correctly defers to human gate. GOOD.

6. **`rules/dependencies.md` § Declared = Imported:** Plan does not check that the deleted methods' import block was the ONLY consumer of `kaizen.mcp.registry/AutoDiscovery/MCPConnection` symbols. If any other module (perhaps `kaizen-agents`) also tries these imports, deletion in `kaizen-kaizen` does not reach those siblings. Plan needs a `grep -rn 'mcp.registry\|AutoDiscovery\|MCPConnection' packages/` sweep to confirm scope.

---

## Verdict

**APPROVE_WITH_REVISIONS** — at the `/todos` gate.

Architecture plan is sound on the central technical claims (lying-types, Agent class shape, `signature_programming_enabled` real bug, orphan-method disposition). The reconciliation between Cluster A and Cluster B is mechanically verified. Both shards fit the autonomous-execution.md Rule 1 budget.

Required revisions before `/todos`:

1. **Dim 3 HIGH** — add pre-`/implement` verification gate for `kailash-mcp` and `kaizen.mcp.catalog_server.MemoryRegistry`; document Agent fallback asymmetry.
2. **Dim 6 HIGH** — surface `kaizen-agents` release coordination; reframe AgentTeam edit choice.
3. **Dim 7 #1 MEDIUM** — file follow-up issue for `_generate_role_based_traits` LLM-first violation OR include in shard 1 scope.

Recommended (not blocking):

- Dim 2 LOC restated (~440 not ~250).
- Dim 4 frame Rule 6a interpretation as explicit human gate question.
- Dim 5 verify `KaizenConfig.signature_programming_enabled` field exists.
- Dim 7 #4 compute post-deletion LOC threshold from real number.

No findings rise to BLOCK. Plan's structure (two shards + optional follow-up) is correct; revisions are amendments to the prose surface, not the shard decomposition.
