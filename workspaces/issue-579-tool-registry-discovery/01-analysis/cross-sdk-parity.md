# Cross-SDK Parity — ToolRegistry Discovery Tax In kailash-rs

**Per**: `rules/cross-sdk-inspection.md` MUST Rule 1 ("When an issue is found or fixed in ONE BUILD repo, you MUST inspect the OTHER BUILD repo for the same or equivalent issue.")
**Verified against**: `/Users/esperie/repos/loom/kailash-rs/` working tree, 2026-04-20
**Verdict**: Same gap exists. Cross-SDK issue MUST be filed on `esperie/kailash-rs`.

## 1. Rust-Side Architecture (Verified)

The Rust SDK ships an equivalent two-phase discovery pattern in `kailash-rs/crates/kaizen-agents/src/hydration/`:

| Concern                    | Python                                                           | Rust                                                                                                  |
| -------------------------- | ---------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| Hydrator type              | `kaizen_agents.delegate.tools.hydrator.ToolHydrator` (dataclass) | `kaizen_agents::hydration::ToolHydrator` (trait) + `DefaultToolHydrator` (impl)                       |
| Meta-tool name             | `search_tools`                                                   | `search_tools` (identical)                                                                            |
| Scoring                    | BM25 `k1=1.5, b=0.75` + name-match `+2.0`                        | TF-IDF with stopword list                                                                             |
| Default threshold behavior | Auto-activates when `len(tools) > 30`                            | Auto-activates via `ToolHydratorConfig::default { auto_include_search_tool: true, max_hydrated: 50 }` |
| Max-hydrated cap           | **None** (unbounded `_hydrated_names` set)                       | `max_hydrated: 50` with implicit LRU eviction                                                         |
| Auto-hydrate on search     | Yes (`hydrator.hydrate(found_names)` in executor)                | Yes (`self.hydrator.hydrate(&names)` in `SearchToolsFn::call`)                                        |
| Call-site wiring           | `AgentLoop._setup_hydration` at loop init                        | `hydrate_registry(&mut registry, config)` helper + `Agent/TaodRunner::with_hydrator(...)`             |

Verified paths:

- `/Users/esperie/repos/loom/kailash-rs/crates/kaizen-agents/src/hydration/mod.rs` — `ToolHydrator` trait + `ToolHydratorConfig` + `hydrate_registry` helper
- `/Users/esperie/repos/loom/kailash-rs/crates/kaizen-agents/src/hydration/search.rs` — `DefaultToolHydrator` + TF-IDF index
- `/Users/esperie/repos/loom/kailash-rs/crates/kaizen-agents/src/hydration/meta_tool.rs` — `SearchToolsFn` + `create_search_tools_meta_tool`

## 2. Same Turn-Tax Failure Mode

The Rust loop in `crates/kaizen-agents/src/agent_engine/taod.rs` and `concrete.rs` uses `resolve_tools_for_request(tools, hydrator)` (mod.rs:62) to get the tools parameter for the LLM. When hydration is active, the LLM sees only active + hydrated tools. First-time calls to deferred tools require:

1. LLM emits `search_tools(query)` — one TAOD tick
2. Hydrator indexes the match into `hydrated_tools` (DashSet in `DefaultToolHydrator`)
3. Next TAOD tick: LLM sees hydrated tool, emits real call

This is structurally identical to the Python flow in `loop.py::AgentLoop.run_turn`. **Same 2-turn cost, same 25% overhead in short-budget sub-agent calls.**

## 3. Where Rust Is Slightly Better, And Where It Is Slightly Worse

**Rust better**:

- `max_hydrated: 50` cap prevents `hydrated_tools` from growing unbounded over a long session. Python has no equivalent.
- Stopword filtering in the TF-IDF index reduces false positives from common English words.

**Rust worse**:

- `ToolHydratorConfig::default { auto_include_search_tool: true }` means hydration activates by default regardless of tool count. A Rust user with 10 tools still pays 2 discovery turns for the first tool use, which Python's `threshold: 30` avoids.
- TF-IDF without a name-match boost is slightly noisier than BM25 + `+2.0` boost for short query-to-name matches.

**Net**: Parity-worthy differences but nothing structural. The core "discovery tax" applies to both.

## 4. Mandatory Cross-SDK Disposition

Per `cross-sdk-inspection.md` MUST Rule 1, a GitHub issue on `esperie/kailash-rs` is required with:

- Cross-reference to kailash-py#579
- Label `cross-sdk`
- Reference to the failure-points analysis at this workspace path (relative)
- Rust-specific surface description (paths, trait names, config defaults)

The issue body below is prepared for `gh issue create`.

## 5. Proposed Rust Issue Body

```
Cross-SDK alignment: this is the Rust equivalent of terrene-foundation/kailash-py#579
(feat(kaizen): ToolRegistry search_tools discovery tax — 2 of N turns lost per
Delegate request).

## Problem

When a Rust Kaizen agent is configured with a ToolHydrator (default:
auto_include_search_tool=true), the LLM must emit a `search_tools(query)` call
before it can use any tool outside the always-active set. This adds a two-TAOD-tick
discovery tax on every distinct tool discovery.

For short-budget sub-agents (max_turns=4) needing one deferred tool, this is 25%
overhead. For sub-agents needing three deferred tools with max_turns=6, it is 50%.

## Python reference (kailash-py#579)

Same failure mode, same architecture. Four remediation options analysed there;
the recommendation is Option 1 (pre-hydrate from user input). Cross-SDK parity
requires the Rust SDK to land the equivalent.

## Rust surface

- crates/kaizen-agents/src/hydration/mod.rs — ToolHydrator trait + ToolHydratorConfig
- crates/kaizen-agents/src/hydration/search.rs — DefaultToolHydrator + TF-IDF index
- crates/kaizen-agents/src/hydration/meta_tool.rs — SearchToolsFn

## Proposed fix (Rust parity with kailash-py#579 Option 1)

Add a `ToolHydrator::pre_hydrate_from_query(&self, query: &str, top_k: usize)`
method (trait method + default impl that calls `self.search(query, top_k)` then
`self.hydrate(&names)`). Invoke it from the agent engine immediately before the
first `resolve_tools_for_request` call of each Agent::run() invocation, with the
user input as the query.

Invariants held:
- LLM-first reasoning (no code classification; retrieval only)
- Dumb-endpoint tools (unchanged)
- search_tools meta-tool remains available for multi-hop discovery
- max_hydrated LRU cap remains enforced

Expected overhead reduction: 25% → 0% in common case; 50% → 25% in worst case.

## Structural API divergence note (cross-sdk-inspection.md MUST 3a)

If Python lands a `ToolHydrator.pre_hydrate_from_query(query, top_k)` helper
and Rust does not, the EATP D6 semantic parity promise breaks — a user porting
a Python Delegate to Rust gets different discovery behavior. Rust MUST either:

1. Ship the same helper with the same default behavior, OR
2. Document the intentional divergence with a pinning test that asserts the
   Rust behavior remains tool-count-threshold-based (no pre-hydration).

Option 1 is recommended for semantic parity.

## Related

- kailash-py analysis: workspaces/issue-579-tool-registry-discovery/01-analysis/
  (failure-points, cost-model, recommendation, this parity file)
```

## 6. gh CLI Command (Pending Execution By Parent Agent)

The analyst sub-agent environment does not expose a Bash tool, so the `gh` invocation must be run by the parent orchestrator (or the user). A ready-to-paste command with the issue body pre-rendered at `/tmp/issue-579-rust-body.md` is below:

```bash
gh issue create --repo esperie/kailash-rs \
  --title "feat(kaizen): ToolRegistry search_tools discovery tax (cross-SDK of kailash-py#579)" \
  --label "cross-sdk" \
  --body-file /tmp/issue-579-rust-body.md
```

Once executed, the URL it prints MUST be:

- Added to this file (Section 8 below) under "Issue URL"
- Cross-commented on terrene-foundation/kailash-py#579 via `gh issue comment 579 --repo terrene-foundation/kailash-py --body "Cross-SDK issue filed: <URL>"`

If the parent cannot reach `esperie/kailash-rs` (org permissions, alternate fork), the fallback target is `terrene-foundation/kailash-rs` — same body content, same label.

## 7. Structural Invariant Test (Python Side)

Per `cross-sdk-inspection.md` MUST Rule 3a, whenever a cross-SDK issue is filed, the originating SDK SHOULD add a structural invariant test that locks the behavior both sides agree on. For this issue, the invariant is:

```python
def test_tool_hydrator_has_pre_hydrate_method_invariant():
    """Cross-SDK contract: Python ToolHydrator MUST expose pre_hydrate_from_query
    once the fix lands. If this method name or signature diverges from the Rust
    sibling, re-audit kailash-rs#<RUST_ISSUE>."""
    from kaizen_agents.delegate.tools.hydrator import ToolHydrator
    import inspect
    if hasattr(ToolHydrator, "pre_hydrate_from_query"):
        sig = inspect.signature(ToolHydrator.pre_hydrate_from_query)
        params = [p for n, p in sig.parameters.items() if n != "self"]
        assert [p.name for p in params] == ["query", "top_k"], (
            f"pre_hydrate_from_query signature drifted: {sig}"
        )
```

This test lives in the SAME PR as the eventual fix. Present in this analysis for reference only; no source change required at analysis phase.

## 8. Filing Record

Per `cross-sdk-inspection.md` MUST Rule 2, the Rust issue body MUST carry:

- [x] Link to the originating issue: kailash-py#579
- [x] Tag: `cross-sdk` label (pre-declared in the `gh issue create --label` flag)
- [x] Note: "Cross-SDK alignment: this is the Rust equivalent of..."

All three conditions satisfied in the drafted body at `/tmp/issue-579-rust-body.md`.

**Issue URL**: _pending_ — to be filled in by the parent orchestrator after running the `gh issue create` command in Section 6. Draft body ready at `/tmp/issue-579-rust-body.md`.
