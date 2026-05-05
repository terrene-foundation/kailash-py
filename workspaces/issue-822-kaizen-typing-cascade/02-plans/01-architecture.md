# Architecture Plan — Issue #822 (kaizen Optional/None typing cascade)

**Workspace:** `workspaces/issue-822-kaizen-typing-cascade/`
**Issue:** [#822](https://github.com/terrene-foundation/kailash-py/issues/822) `fix(kaizen): resolve Optional/None pyright warnings`
**Status:** `/analyze` complete (red-team Round 1 revisions applied); awaiting human gate at `/todos`.

## TL;DR

Three parallel deep-dive agents verified the brief and surfaced findings the brief
under-counted by an order of magnitude in two of three clusters. Issue #822 is
**not a 4-line fix** — it's three structurally distinct workstreams that the brief
collapsed into one bullet. The recommended ship plan is **two shards** with one
optional follow-up.

| Shard        | Scope                                                                                             | LOC                     | Bug-class severity                                                       |
| ------------ | ------------------------------------------------------------------------------------------------- | ----------------------- | ------------------------------------------------------------------------ |
| **Shard 1**  | Lying-types + None-guards + Agent DECLARE + behavior_traits dead branch + 1 real bug fix          | ~140                    | LOW (pyright) → MEDIUM (real `signature_programming_enabled` gate fixed) |
| **Shard 2**  | Orphan deletion: dead `..mcp.registry` / `AutoDiscovery` / `MCPConnection` paths + 5 dead methods | ~440 (incl. test sweep) | MEDIUM (Rule 2 fake-integration on CoreAgent surface)                    |
| **Optional** | `Kaizen.config` property return-type widening (separate refactor)                                 | ~10                     | LOW (pyright only)                                                       |

**Total**: ~580 LOC + Tier-2 regression tests + CHANGELOG entry into existing
`[Unreleased]` block. Both shards fit `rules/autonomous-execution.md` Rule 1
(deletion-heavy boilerplate; single conceptual change per shard; ≤5–10 invariants).

**Blast radius note (Shard 2):** the 5 dead MCP methods live on `kaizen.core.agents.Agent`
(CoreAgent). Per `kaizen/__init__.py:15-20`, the canonical user surface
`kaizen.Agent` is `kaizen_agents.Agent` (when kaizen-agents is installed —
the documented path) which does NOT have these methods. Deletion only affects
users who explicitly import `from kaizen.core.agents import Agent`.

The release surface is **kailash-kaizen** appended to existing `[Unreleased]`
(currently `__version__ = "2.18.2"`; pre-existing entries already justify a
minor bump to 2.19.0).

## Brief Corrections

Per `rules/agents.md` MUST § Parallel Brief-Claim Verification:

| Brief claim                                                | Mechanical ground truth                                                          | Delta                            |
| ---------------------------------------------------------- | -------------------------------------------------------------------------------- | -------------------------------- |
| `kaizen/__init__.py`: 2 sites (127, 155)                   | 0e / 3w — confirms 2 sites + 1 extra param at :127                               | match                            |
| `kaizen/core/framework.py`: 4e / 6w                        | **4e / 21w** — 21 warnings, brief listed 6                                       | +15 warnings under-counted       |
| `kaizen/core/agents.py`: "extends into"                    | **3e / 12w** — full diagnostic set (lying-types + missing imports + Agent attrs) | brief named the file, not scope  |
| 4 lying-type sites                                         | **6 lying-type sites** (4 brief + 2 in agents.py at :307, :413)                  | +2 omitted from brief            |
| Cascade is "additional issues in framework.py + agents.py" | Cascade includes 5 NEVER_EXISTED imports (orphans predating PR #75)              | bug class is broader than typing |

**Brief omissions (high impact):**

- The `agents.py:459` `KaizenConfig.get` site: documented `signature_programming_enabled`
  gate is silently a no-op against `KaizenConfig` dataclass instances (the explicit-config
  path) because the dataclass has no `.get` method and the `hasattr` guard at line 458
  flips the gate to False. Tests pass dicts which mask the gap. This is a real Rule 3
  silent-fallback violation in a documented public-API gate.
- The `framework.py:537–540` `behavior_traits` dead branch: the `hasattr(agent,
"behavior_traits")` guard is structurally always False because the value is stored
  in `agent.config["behavior_traits"]`, not as an attribute. The role-based-prompt
  trait-rendering branch is unreachable.
- The 5 NEVER_EXISTED imports (`..mcp.registry::get_global_registry`, `..mcp::AutoDiscovery`,
  `..mcp::MCPConnection`) are inside `try/except ImportError` blocks that ALWAYS fail
  in production — `Agent.expose_as_mcp_server`, `Agent.expose_as_mcp_tool`,
  `Agent.connect_to_mcp_servers`, `Agent.call_mcp_tool`, `Agent._discover_servers`, and
  `Kaizen.discover_mcp_tools` external-discovery branch + `Kaizen.mcp_registry`
  property never produced a real connection. This is `rules/zero-tolerance.md` Rule 2
  fake-integration on documented public API.

## Cluster Findings (Detailed Reports)

- **`01-analysis/01-cluster-a-lying-types.md`** — 6 TYPE FIX + 7 GUARD FIX + 1 real bug
- **`01-analysis/02-cluster-b-agent-model.md`** — Agent class shape + DECLARE protocol
- **`01-analysis/03-cluster-c-imports-orphans.md`** — orphan-import lineage (PR #75 red herring)

## Shard 1 — Type Safety + None-Guards + Agent DECLARE + behavior_traits Fix

**Scope (combined Cluster A + Cluster B):**

### Cluster A fixes (~50 LOC)

1. **6 TYPE FIX sites** — `param: T = None` → `param: Optional[T] = None`:
   - `kaizen/__init__.py:127` (`name`, `config`)
   - `kaizen/__init__.py:155` (`explicit_config`)
   - `kaizen/core/framework.py:341, 344` (`agent_id`, `name`)
   - `kaizen/core/agents.py:307` (`parameters`)
2. **7 GUARD FIX sites** — typed `RuntimeError` per `rules/zero-tolerance.md` Rule 3a:
   - `agents.py:266` (`logger.handlers[0].formatter.formatTime`) — replace with
     `datetime.utcnow().isoformat()` (the existing block is functionally pointless)
   - `framework.py:882, 945` (`self._coordination_engine.create_coordination_workflow` /
     `.extract_coordination_results`) — typed `RuntimeError` if None
   - `framework.py:1077, 1097` (`self._signature_parser.parse` / `.validate`) — typed guard
     after `_ensure_signatures_loaded()`
   - `framework.py:1188, 1258` (`reportOptionalCall` errors) — typed guard before invocation
3. **1 REAL BUG FIX** — `agents.py:458–459`:
   ```python
   # Replace:
   and hasattr(self.kaizen.config, "get")
   and self.kaizen.config.get("signature_programming_enabled", False) == True
   # With:
   and getattr(self.kaizen.config, "signature_programming_enabled",
       self.kaizen.config.get("signature_programming_enabled", False)
       if hasattr(self.kaizen.config, "get") else False) == True
   ```
   Or cleaner — split into a helper that reads from either `KaizenConfig` dataclass
   OR `ConfigWrapper(dict)` shape. **Tier-2 regression test required**: signature-
   programming gate fires correctly against an explicit `KaizenConfig` instance.

### Cluster B fixes (~85 LOC)

4. **DECLARE class-body annotations** for the 5 Agent attrs that are dynamically
   attached (per `rules/orphan-detection.md` § "Removed = Deleted" inverse — DECLARE
   if the attach pattern is real public API):
   ```python
   # agents.py inside class Agent:
   role: Optional[str] = None
   expertise: Optional[str] = None
   capabilities: Optional[List[str]] = None
   behavior_traits: Optional[List[str]] = None
   authority_level: Optional[str] = None
   ```
   Per Cluster B § 2: `create_specialized_agent` / `create_agent_team` are reachable
   public API with ≥20 test callsites. Dynamic-attach is real.
5. **DECLARE `_generate_role_based_prompt`** as a Method (refactor lambda → method)
   on `Agent`, OR keep dynamic-attach and add `Callable[..., str]` annotation. Lambda
   form makes type narrowing harder; recommend method form.
6. **`AgentTeam` typing — suppress at attach-site, do NOT extend the class.**
   `kaizen-agents/.../patterns/core/teams.py:48-55` raises `DeprecationWarning`
   in `__init__` directing users to `OrchestrationRuntime`. Adding new typed
   class-body kwargs to a deprecated class is wrong. Instead, at
   `framework.py:824, 825` (where `team.conflict_resolution` and
   `team.performance_optimization` are dynamically attached), add:
   ```python
   team.conflict_resolution = …  # type: ignore[attr-defined]  # AgentTeam deprecated; see kaizen.orchestration.runtime
   team.performance_optimization = …  # type: ignore[attr-defined]
   ```
   No cross-package edit; no kaizen-agents release coordination needed.
7. **`behavior_traits` dead branch fix** at `framework.py:495`:
   ```python
   agent.behavior_traits = specialized_config.get("behavior_traits", [])
   ```
   Plus Tier-2 regression test asserting the rendered prompt at `_generate_role_based_prompt`
   contains the trait words. Currently unreachable per Cluster B Caveat.
8. **Add `Signature` to `TYPE_CHECKING` block** at `framework.py:12` (single line):
   ```python
   if TYPE_CHECKING:
       from kaizen.signatures import Signature
   ```
   Closes the `framework.py:1053` `reportUndefinedVariable`.
9. **Add return annotation to `Agent.execute`** at `agents.py:375`:
   ```python
   def execute(self, workflow=None, **kwargs) -> Union[Dict[str, Any], Tuple[Dict[str, Any], str]]:
   ```
   Plus narrowing at `agents.py:2287` call site (`assert isinstance(round_result, dict)`).
   Closes the `__getitem__` slice/str cascade.

### Acceptance gates (Shard 1)

All gates run from the sub-package: `cd packages/kailash-kaizen && uv run …`
(repo-root `.venv` has a stale `kailash` install that breaks `pytest --collect-only`).

- [ ] `uv run pyright src/kaizen/__init__.py` → 0e / 0w
- [ ] `uv run pyright src/kaizen/core/framework.py` → 0e / **<5w** (residual orphan-import warnings live in Shard 2)
- [ ] `uv run pyright src/kaizen/core/agents.py` → 0e / **<5w** (same)
- [ ] All existing tests pass (`uv run pytest tests/`)
- [ ] **NEW Tier-2 regression**: `tests/regression/test_issue_822_signature_programming_gate.py` — explicit `KaizenConfig(signature_programming_enabled=True)` raises `ValueError("Agent must have a signature for structured execution")` from `Agent._execute_direct_llm`.
- [ ] **NEW Tier-2 regression**: `tests/regression/test_issue_822_signature_programming_typo_path.py` — `kaizen.configure(signature_programming_enabld=True)` (typo) does NOT enable the gate. Canonical key gates correctly. Closes the same Rule 3 silent-fallback bug class on the dict-config path.
- [ ] **NEW Tier-2 regression**: `tests/regression/test_issue_822_behavior_traits_render.py` — `create_specialized_agent(name=..., behavior_traits=["analytical", "thorough"])` produces a prompt containing both traits.
- [ ] **NEW behavioral regression bundle**: `tests/regression/test_issue_822_optional_call_guards.py` — parametrized over the 7 GUARD FIX sites; each invokes the site under None-state and asserts a typed `RuntimeError` with actionable message (not bare `AttributeError`).

### Why one shard

LOC: ~140. Invariants held simultaneously: (a) signature-programming gate semantics;
(b) Agent class dynamic-attach contract; (c) behavior_traits round-trip; (d) None
narrowing on coordination_engine + signature_parser; (e) executor return-type
discriminated union. **5 invariants** ≤ Rule 1's ≤5–10 ceiling. Pyright is the live
feedback loop (Rule 3 multiplier applies).

## Shard 2 — Orphan-Import Deletion (Rule 2 Fake-Integration Cleanup)

**Scope (Cluster C):**

The 5 NEVER_EXISTED imports gate 5 dead methods on `Agent` + 1 dead branch + 1
dead property on `Kaizen`. All 6 surfaces have been broken since `b553104c` (the
original `apps/`→`packages/` move) — they have NEVER produced a real connection
in production.

**Blast radius:** All deleted methods live on `kaizen.core.agents.Agent`
(CoreAgent). Per `kaizen/__init__.py:15-20`, the canonical user surface
`kaizen.Agent` resolves to `kaizen_agents.Agent` (when `kaizen-agents` is
installed — the documented ADR-020 path) which DOES NOT have these methods.
Deletion only affects users who explicitly do `from kaizen.core.agents import
Agent` (or hit the ImportError fallback because they did not install
`kaizen-agents`). Most documented usage is unaffected.

The disposition options are:

### Option A — Delete with CHANGELOG migration entry (recommended)

Per `rules/zero-tolerance.md` Rule 2 (no fake integration) and Rule 6a (deprecation
cycle for public-API removal):

| Method                                  | Range                  | LOC      |
| --------------------------------------- | ---------------------- | -------- |
| `Agent.expose_as_mcp_server`            | agents.py 2370–2467    | 99       |
| `Agent.expose_as_mcp_tool`              | agents.py 2540–2614    | 75       |
| `Agent.connect_to_mcp_servers`          | agents.py 2780–2900    | 121      |
| `Agent.call_mcp_tool`                   | agents.py 2900–2920    | 20       |
| `Agent._discover_servers`               | agents.py 2937–2965    | 29       |
| `Kaizen.discover_mcp_tools` ext branch  | framework.py 1512–1531 | 20       |
| `Kaizen.mcp_registry`                   | framework.py 1349–1360 | 11       |
| **Source deletions**                    |                        | **~375** |
| Test deletions (per § Test sweep below) |                        | **~65**  |
| **TOTAL**                               |                        | **~440** |

`Signature is not defined` at `framework.py:1053` is HANDLED by Shard 1's
TYPE_CHECKING block — out of Shard 2 scope.

**Test sweep — precise (per `rules/orphan-detection.md` Rule 4):**

Per reviewer Round 1: do NOT whole-file-delete. Surviving tests outnumber
deleted-surface tests in two of three files.

- `tests/unit/test_agents_comprehensive.py` — **45 tests total; delete 6** that
  reference deleted surface: `test_expose_as_mcp_server`, `test_expose_as_mcp_tool`,
  `test_connect_to_mcp_servers`, `test_get_mcp_tool_registry`, `test_execute_mcp_tool`,
  `test_call_mcp_tool`. Preserve the remaining 39.
- `tests/unit/test_mcp_integration_missing.py` — **16/16 tests reference deleted
  surface; whole-file delete.**
- `tests/e2e/test_agent_execution_patterns_e2e.py` — **17 tests total; delete 2**:
  `test_agent_with_mcp_tools_e2e`, `test_mcp_server_exposure_e2e`. Preserve the
  remaining 15.
- 13+ `discover_mcp_tools` test refs across `tests/unit/` — preserve local-tools
  path coverage; delete only the external-discovery branches that test the
  removed `external=True` parameter.
- `scripts/comprehensive_implementation_tester.py:571` (`mcp_registry`) — delete the line.

**CHANGELOG entry — append to existing `[Unreleased]` block** (per reviewer M4):

`packages/kailash-kaizen/CHANGELOG.md` already has an `[Unreleased]` accumulator
with 5+ minor-bump-shaped entries; current `__version__ = "2.18.2"`. Do NOT
create a fresh `[2.19.0]` block — append to `[Unreleased]`. The existing entries
already justify the minor bump.

```markdown
## [Unreleased]

### Removed (BREAKING) — issue #822

The following methods on `kaizen.core.agents.Agent` (CoreAgent) were documented
public surface but never produced a real connection — every call attempted to
import `..mcp.registry::get_global_registry`, `..mcp::AutoDiscovery`, or
`..mcp::MCPConnection`, none of which existed at any commit in this package's
history. The methods returned `None`, `[]`, or error dicts via broad
`except Exception:` swallows, and have been deleted:

- `Agent.expose_as_mcp_server` — migrate to `kailash-mcp` package
- `Agent.expose_as_mcp_tool` — migrate to `kailash-mcp` package
- `Agent.connect_to_mcp_servers` — use `kaizen.mcp.catalog_server.MemoryRegistry`
  directly (`packages/kailash-kaizen/src/kaizen/mcp/catalog_server/registry.py:43`)
- `Agent.call_mcp_tool` — same migration target
- `Kaizen.discover_mcp_tools(external=True, ...)` — external-discovery removed;
  local-tools path unchanged
- `Kaizen.mcp_registry` property — always returned `None`; use
  `kaizen.mcp.catalog_server.MemoryRegistry` directly

**Migration impact is scoped to direct CoreAgent imports.** Per
`kaizen/__init__.py:15-20`, the canonical user surface `kaizen.Agent` resolves
to `kaizen_agents.Agent` (when `kaizen-agents` is installed — the documented
ADR-020 path) which never had these methods.

These methods have been broken since the original `apps/`→`packages/` move
(`b553104c`). The deletion makes the non-functionality explicit instead of
hiding it behind broad exception swallows.
```

**Cross-SDK note** (`rules/cross-sdk-inspection.md` Rule 1): kailash-rs may have a
parallel orphan pattern from its own structural splits. Inspection of kailash-rs is
out-of-lane for this session (`rules/repo-scope-discipline.md`); flag for follow-up
issue against esperie/kailash-rs documenting the same audit pattern.

### Option B — Replace with NotImplementedError (less optimal)

Replace the 6 dead methods' bodies with `raise NotImplementedError("MCP external
discovery is not implemented in kailash-kaizen; use kailash-mcp package or
kaizen.mcp.catalog_server.MemoryRegistry directly.")`. Per `rules/zero-tolerance.md`
Rule 2 this is still a fake API surface — the methods are documented as working but
ALWAYS raise. NOT recommended; included for completeness so the user can choose.

### Acceptance gates (Shard 2)

All gates run from the sub-package: `cd packages/kailash-kaizen && uv run …`
(repo-root `.venv` has a stale `kailash` install that breaks `pytest --collect-only`).

- [ ] `grep -rn "from \.\.mcp\.registry\|from \.\.mcp import AutoDiscovery\|from \.\.mcp import MCPConnection" src/` → empty
- [ ] `grep -rn "expose_as_mcp_server\|expose_as_mcp_tool\|connect_to_mcp_servers\|call_mcp_tool\|_discover_servers\|mcp_registry" src/` → empty
- [ ] `uv run pytest tests/ --collect-only` → exit 0 (no orphan-import collection failures)
- [ ] `uv run pyright src/kaizen/core/framework.py` → 0e / 0w
- [ ] `uv run pyright src/kaizen/core/agents.py` → 0e / 0w
- [ ] CHANGELOG entry appended to existing `[Unreleased]` block at `packages/kailash-kaizen/CHANGELOG.md`
- [ ] **NEW LOC invariant test** at `tests/regression/test_issue_822_loc_invariant.py` per `rules/refactor-invariants.md` Rule 1 — `agents.py` line count post-deletion + 10-15% margin (verify post-deletion line count BEFORE writing the threshold; do NOT hand-type a round number)
- [ ] Cross-SDK follow-up issue filed against `esperie/kailash-rs` per Rule 1 (HUMAN-GATED per `rules/upstream-issue-hygiene.md`)

### Why one shard

LOC: ~440 (375 source + ~65 test sweep — deletion-heavy boilerplate).
Invariants: (a) every test that imports a deleted symbol is also deleted; (b)
surviving tests in mixed files are preserved; (c) `__all__` consistency; (d)
`pytest --collect-only` green; (e) LOC invariant test lands same commit. **5
invariants** = Rule 1's ≤5–10 ceiling. Mechanical deletion + per-test co-deletion.
Single conceptual change: "delete the fake-MCP-integration surface."

## Optional Shard 3 — Kaizen.config Property Return Typing

**Out of #822 scope; file as follow-up if pyright still complains after Shard 1 + 2.**

`Kaizen.config` (`framework.py:1283`) returns either `KaizenConfig` (dataclass) OR
`ConfigWrapper(dict)` based on `_config_was_object`. Pyright sees the inferred return
type as one or the other. If the Shard 1 fix at `agents.py:459` widens via
`getattr(...)` over the union, pyright's union-narrowing should already be satisfied.
If residual warnings remain, add explicit return-type annotation
`-> Union[KaizenConfig, ConfigWrapper]` and update Cluster B's KaizenConfig narrowing.

LOC: ~10. Defer until Shard 1 + Shard 2 pyright runs reveal whether this is needed.

## Cross-Cutting Concerns

### `rules/orphan-detection.md` Rule 1 — Manager-shape audit

Per audit-mode protocol: `Kaizen` exposes `mcp_registry` (returns `None`),
`coordination_engine` (`*Engine`), `signature_parser` (`*Parser`), `agent_manager`
(`*Manager`). Each MUST have a Tier-2 wiring test per Rule 2. **Out of scope for
#822** but flag as follow-up — orphan-detection sweep is `/redteam`-mode work.

### `rules/refactor-invariants.md` Rule 1 — LOC invariant

Shard 2 deletes ~375 LOC from `agents.py`. MUST land an invariant test in same
commit. The threshold MUST be derived from the post-deletion line count + 10–15%
margin per Rule 1 — DO NOT hand-type a round number. After running Shard 2,
measure the resulting `agents.py` length and write the threshold as
`<measured> + 15%`.

```python
@pytest.mark.regression
def test_agents_py_loc_invariant_after_822():
    """Guard: after #822 orphan deletion, agents.py stays below the post-deletion threshold."""
    path = Path("packages/kailash-kaizen/src/kaizen/core/agents.py")
    line_count = len(path.read_text().splitlines())
    # Threshold = post-deletion LOC + 15% margin. Update by measurement, not by guess.
    THRESHOLD = <to-be-measured-during-implement>  # MUST land filled in
    assert line_count <= THRESHOLD, (
        f"agents.py has {line_count} lines (post-#822 limit: {THRESHOLD}). "
        f"If MCP orphan methods were re-introduced, check git log for unexpected growth."
    )
```

### `rules/agents.md` MUST — Specialist consultation

Both shards touch agent-framework public API. Per the framework→specialist
binding in `rules/framework-first.md`, the implementer MUST consult
**kaizen-specialist** before edits to `kaizen/core/agents.py` and
`kaizen/core/framework.py`. No `kaizen-agents` source edit is needed (per H3
revision — AgentTeam dynamism is suppressed at the attach-site, not declared).

### `rules/dependencies.md` BLOCKED — `# type: ignore[import-not-found]`

Cluster C Path A ("just silence pyright") is BLOCKED by `rules/dependencies.md`
BLOCKED Anti-Patterns: `import redis  # type: ignore[import]` is named explicitly.
This forecloses Cluster C Path A — only deletion is valid.

### `rules/build-repo-release-discipline.md` — release scope enumeration

At session-end (after Shard 1 + Shard 2 merge), `/release` MUST enumerate
EVERY BUILD package's `main` vs PyPI version per Rule 3 and sweep every stale
sibling (Rule 1). The closing release session is responsible for the full
enumeration, NOT just `kailash-kaizen`. Block this in working memory at
`/implement` start.

## Open Questions for Human (gate at `/todos`)

1. **Shard 2 disposition: delete vs NotImplementedError?** Per `rules/zero-tolerance.md`
   Rules 2 + 6, deletion is correct. Per Rule 6a, public-API removal nominally
   needs a deprecation cycle — but the BLOCKED-rationalization list does not
   carve out "never functioned." Both options are plan-interpretation, not
   rule-text. **Recommendation: delete + CHANGELOG entry into `[Unreleased]`.**
   Alternative: replace bodies with typed `NotImplementedError("kaizen-mcp or
kaizen.mcp.catalog_server.MemoryRegistry — see CHANGELOG")` — converts silent
   to loud failure but still ships fake-API surface (Rule 2 violation).
2. **Release surface: 2.18.3 patch vs 2.19.0 minor?** `[Unreleased]` already
   accumulates 5+ minor-bump-shaped entries; Shard 2 adds BREAKING removals.
   **Recommendation: 2.19.0 minor.**
3. **Cross-SDK follow-up against `esperie/kailash-rs`** — file the parallel
   orphan-pattern audit issue per `rules/cross-sdk-inspection.md` Rule 1?
   HUMAN-GATED per `rules/upstream-issue-hygiene.md`. **Awaiting decision.**
4. **`_generate_role_based_traits` keyword-matching follow-up** —
   `framework.py:505-528` matches `role_lower` substrings to derive default
   behavior traits (`rules/agent-reasoning.md` Rule 1 BLOCKED pattern). Out of
   scope for #822 (the behavior_traits assignment fix in Shard 1 does not touch
   this method). **Recommendation: file separate issue** for LLM-first rewrite
   (use `Signature` to derive traits from role description).

## Spec Updates (per `rules/specs-authority.md`)

`specs/kaizen-core.md` is the authority for `Kaizen.create_agent`, Agent class,
and `signature_programming_enabled`. Per `rules/spec-accuracy.md` Rule 5,
spec edits LAG code — the spec extensions land WITH `/implement` at first-instance,
NOT pre-implementation. See `02-plans/02-spec-traceability.md` for the full
brief→spec map and the post-implement edit list.

No new spec file is needed.

## Recommended Ship Order

1. **Shard 1** (Cluster A + B fixes) — most callers benefit, no API removal,
   single shard, pyright closes ~25 of 36 warnings.
2. **Shard 2** (Cluster C deletion) — completes pyright closure; ships in same
   minor release with CHANGELOG entry into `[Unreleased]`.
3. **Optional Shard 3** — only if pyright remains noisy after 1 + 2.

Both shards land in `packages/kailash-kaizen/`. Single release: kailash-kaizen 2.19.0.

## Risk Assessment

- **Shard 1 risk: LOW.** Mechanical type fixes + typed guards. The `signature_programming_enabled` real-bug fix has narrow blast radius (only fires when user passes explicit `KaizenConfig` with the flag set). Tier-2 regressions for the canonical-key + typo-key paths catch drift.
- **Shard 2 risk: LOW–MEDIUM.** Public-API removal scoped to `kaizen.core.agents.Agent` (CoreAgent). Most users get `kaizen_agents.Agent` via `kaizen/__init__.py:15-20` and never see the deletion. Mitigated by: (a) the API never worked, (b) CHANGELOG entry, (c) per-test sweep (Rule 4), (d) collect-only gate (Rule 5), (e) LOC invariant (Rule 1).
- **Cross-package coordination: NONE.** Per H3 revision, AgentTeam typing is suppressed at attach-site; no kaizen-agents edit; no kaizen-agents release coordination.

## References

- `briefs/01-issue-822.md` — verbatim issue body + verified baseline counts
- `01-analysis/01-cluster-a-lying-types.md`
- `01-analysis/02-cluster-b-agent-model.md`
- `01-analysis/03-cluster-c-imports-orphans.md`
- `journal/0001-DISCOVERY-brief-undercounts-typing-cascade-by-3.5x.md` (to be written)
- `journal/0002-DISCOVERY-mcp-orphans-predate-pr-75.md` (to be written)
- `journal/0003-DISCOVERY-signature-programming-gate-silent-noop.md` (to be written)
