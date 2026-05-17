# Recommendation — Option 1 (Pre-Hydrate From User Input) + Option 4 (Batch-Discovery Prompt Update)

**Decision**: Ship Option 1 as the primary fix. Stack Option 4 as a cheap additional win in the same PR. Defer Option 3 (ranker verb-boost) to a follow-up if telemetry shows residual worst-case overhead. Reject Option 2 (turn-budget split) — it hides cost rather than removing it.

**Framework framing** (per `rules/framework-first.md`): Every change expressed in Kaizen primitives.

- `ToolHydrator` → unchanged public surface; internal `pre_hydrate_from_query(query: str, top_k: int = 5) -> None` helper added.
- `AgentLoop` → calls `pre_hydrate_from_query` once in `run_turn` before the first `_stream_completion`; no new facade.
- `Delegate` → no API change. Existing `max_turns` parameter preserves its contract.
- `BaseAgent` → unaffected (does not use hydrator).
- `Signature` → unaffected (signatures describe LLM reasoning; pre-hydration is data-retrieval, not reasoning).

## 1. Why Option 1 Is The Correct Lowest-Risk Net-Positive

### Aligns with SDK primitives the codebase already ships

`ToolHydrator.search(query, top_n=K)` exists today (`hydrator.py:305`). It is exercised end-to-end via `search_tools` every time the LLM asks a question. The same BM25 scoring, the same `_hydrated_names` mutation path, the same `load_tools` pre-indexed corpus — all stay identical. The NEW code is a single call site that invokes those primitives with the user's input instead of the LLM's interpretation of the user's input.

### Eliminates the load-bearing cost class

The 25% overhead in issue #579 IS the two-turn discovery tax. Option 1 collapses it to zero for the common case where BM25 has a good match on the user's literal input. The LLM on turn 1 already sees both base tools AND candidate tools — it emits the real call on turn 1 and returns text on turn 2. Net: 2 useful turns where the current design uses 2 discovery + 1 useful = 3.

### Preserves every load-bearing invariant

- **LLM-first reasoning** (`agent-reasoning.md` MUST 1): The framework runs a BM25 retrieval. It does NOT decide whether the LLM should use the hydrated tools, which one to pick, or how to call them. The LLM reasons over a superset of its current visible tool set. This is semantically identical to a RAG retrieval step — allowed under Permitted Exception 6 of `agent-reasoning.md`.
- **Tools as dumb endpoints** (MUST 2): Pre-hydration does not change tool semantics.
- **Signatures describe, code does not decide** (MUST 3): No signature change; no code path decides agent behavior.
- **`search_tools` remains available**: Multi-hop discovery still works (LLM can emit `search_tools("something the pre-hydrate missed")` on any subsequent turn).
- **Single-turn escape hatch** (loop.py:682): Unaffected; the `get_executor_force()` path still lets the LLM batch discoveries with real tools mid-turn.

### Meets `rules/autonomous-execution.md` capacity budget

- Load-bearing logic: ≤100 LOC Python + ≤100 LOC Rust per shard. Well under 500 LOC cap.
- Invariants to hold: 5 (LLM-first, dumb endpoints, signature purity, escape-hatch preservation, cross-SDK parity). Within the 5–10 cap.
- Call-graph hops: 3 (Delegate.run → AgentLoop.run_turn → hydrator.search → hydrator.hydrate). Within the 3–4 cap.
- Describable in 3 sentences: "Before the first LLM call of each turn, run hydrator.search on the user input. Add the top-K matches to the active set. The LLM now sees the relevant tools on turn 1 instead of turn 2."

### Has an executable feedback loop

- Tier 1 unit test: `ToolHydrator.pre_hydrate_from_query("deploy to kubernetes", top_k=5)` mutates `_hydrated_names` to include `kubernetes_deploy`.
- Tier 2 integration test: Delegate with 40 tools where `slack_post` is deferred. Feed `user_message = "send a slack message"`. Assert turn 1 completes with the real `slack_post` call, not `search_tools`. (`rules/orphan-detection.md` MUST 2 — Tier 2 through the facade.)
- Regression test against the BM25 blind spot from `failure-points.md` §6d: "read the metrics" with `read_file` (base) and `metrics_query` (deferred); assert both are visible to the LLM on turn 1.

### Cross-SDK parity is natural

Rust already has `DefaultToolHydrator::search` and `::hydrate` with the exact same semantics. The Rust equivalent is a ~100 LOC addition to `crates/kaizen-agents/src/hydration/` + a call site in the Rust agent loop (`delegate_engine.rs` or equivalent). Cross-SDK semantic parity (`rules/cross-sdk-inspection.md` EATP D6) is the bar; both SDKs get the same method name and the same behavior.

## 2. Why Not Option 2 (Turn-Budget Split)

Option 2 adds `discovery_turns` and `work_turns` as separate parameters. This:

- Does not reduce token cost, wall-clock cost, or discovery latency
- Hides the 2-turn tax behind a renamed counter
- Changes the `max_turns` contract in a way every caller has to re-reason about
- Doesn't fix the worst case (BM25 miss + retry)

It is a cosmetic fix that trades one problem (visible overhead) for a worse problem (invisible overhead). Blocked.

## 3. Why Not Option 3 (Verb-Boost) as Primary Fix

Option 3 improves BM25 ranking quality by weighting verb-like tokens. This:

- Does NOT eliminate the 2-turn tax in the common case
- Only reduces hit rate in the worst case
- Introduces a curated verb list that is a form of domain classification (subtle MUST 4 violation in `agent-reasoning.md` — pre-ranking bias IS a weak classifier, even if not a hard one)

It is a useful increment AFTER Option 1 ships, but not a substitute for it.

## 4. Why Stack Option 4

Option 4 is 20 LOC of prompt engineering. It costs nothing to include and captures a secondary 12% win on GPT-4-class models that already batch tool calls. Include in the same PR as Option 1; ship or drop based on integration-test outcomes. No architectural commitment.

## 5. Open Questions For `/todos` Phase

1. **Top-K value**: K=5 is a guess. Telemetry from the existing `logger.info("search_tools query=%r found=%d hydrated=%d", ...)` (search.py:110) can inform. For an initial ship, K=5 matches the Rust `ToolHydratorConfig.max_hydrated: 50` intent proportionally.
2. **Relevance threshold**: Should we only pre-hydrate when `score > threshold`, or always pre-hydrate top-K regardless? Empirically test both.
3. **Index staleness on dynamic registries**: Current `_build_search_index` runs once in `load_tools`. If a tool is registered after hydrator init, the pre-hydrate path misses it. Separate issue, likely a follow-up.
4. **Rust `max_hydrated` port to Python**: Ship as part of this PR or separately? Recommend part of this PR for cross-SDK parity since we're already touching the file.

## 6. Proposed Phase Plan

- **Phase 1 (single shard, this PR)**: Option 1 pre-hydrate + Option 4 prompt update. Python + Rust parallel worktrees per `rules/agents.md` § Worktree Isolation. One agent = Python shard, one agent = Rust shard, orchestrator designates the Python agent as version owner for `pyproject.toml` per rules/agents.md § Parallel-Worktree Package Ownership.
- **Phase 2 (optional, if telemetry warrants)**: Option 3 verb-boost + max-hydrated LRU cap port to Python.
- **Phase 3 (defer)**: Dynamic-registry index refresh.

Each phase single-session, feedback-loop-present, within capacity bands.

## 7. Risks That Would Change The Recommendation

- **If BM25 proves consistently wrong on typical queries**: Option 1 provides no benefit and Option 3 (verb-boost) becomes primary.
- **If the LLM reliably batches `search_tools + real_tool` on the models we care about**: Option 4 alone gives 50% of Option 1's benefit at 10% of the cost — might be enough.
- **If cross-SDK parity with Rust's `max_hydrated` cap surfaces as a HIGH finding in `/redteam`**: That cap-port could become the primary fix and pre-hydrate slips to Phase 2.

None of these risks currently apply based on the code review in `failure-points.md`.

## 8. Consequences (ADR-style)

### Positive

- Common-case discovery tax eliminated (25% → 0%)
- Worst-case cost reduced (50% → 25%)
- Cross-SDK semantic parity preserved
- Uses existing primitives — no new facade, no new orphan risk
- Single-shard work on each SDK — parallelizable per `autonomous-execution.md`

### Negative

- Token cost per turn increases slightly (≈600 tokens of hydrated tool schemas that the LLM may not use). This is the price of eager retrieval and is amortized over session length.
- Pre-hydration correctness depends on BM25 quality for the user's actual input — an input/corpus mismatch that wasn't a failure mode before now affects turn 1 as well as turn N.

### Neutral

- The mental model shifts: "The framework sees the user's input" becomes explicit. This is actually clearer than the current "the framework sees only the LLM's interpretation of the user's input."
