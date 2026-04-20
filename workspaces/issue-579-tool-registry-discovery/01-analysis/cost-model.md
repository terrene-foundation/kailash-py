# Cost Model — ToolRegistry Discovery Tax

**Source issue**: kailash-py#579 claim of "2 of N turns lost per Delegate request" and "25% overhead"
**Goal**: Quantify the claim with concrete math; enumerate remediation options with cost/benefit for each

## 1. Turn-Budget Arithmetic

Let `T` = effective turn budget per Delegate request. Let `D` = number of deferred-tool discoveries the LLM needs across the request. The "useful work" turn count is the count of inner turns that emit either real tool calls on non-meta tools OR final text.

### Baseline (no hydration, below threshold)

```
useful_turns = T
discovery_turns = 0
overhead_ratio = 0
```

### Current design (hydration active, D discoveries needed)

Each discovery costs **at minimum** 1 turn for `search_tools`. In the single-turn escape path (loop.py:682 `get_executor_force`), the LLM may batch `search_tools(...)` and the intended real tool in the SAME tool_calls batch — but in practice the LLM rarely does this because the real tool isn't in the `tools=` parameter yet, so it doesn't know the tool's name / argument schema. So the realistic cost:

```
discovery_turns = D           # one search_tools call per distinct discovery
useful_turns    = T − D       # turns remaining for real work
overhead_ratio  = D / T
```

For `D=1, T=4`: overhead 25%. **This is the claim in issue #579.**

For `D=1, T=8`: overhead 12.5%.
For `D=2, T=8`: overhead 25%.
For `D=1, T=50` (default kz interactive): overhead 2%.
For `D=3, T=5` (small sub-agent): overhead 60% — and the sub-agent has 2 turns for actual work.

### Worst-case (LLM guesses wrong then searches)

If the LLM tries a base tool first, gets an error, THEN calls `search_tools`, the cost is 2 discovery turns per needed tool:

```
discovery_turns = 2D
overhead_ratio  = 2D / T       # 50% at D=1, T=4
```

This is not hypothetical. Section 6c / 6d in `failure-points.md` shows BM25 relevance blind spots make this common for ambiguous queries.

## 2. Verifying the 25% Claim

| Scenario                                                     | D   | T   | useful | tax | overhead  |
| ------------------------------------------------------------ | --- | --- | ------ | --- | --------- |
| Delegate("summarize file, then post to slack"), no hydration | 0   | 4   | 4      | 0   | 0%        |
| Same request, `slack_post` is deferred                       | 1   | 4   | 3      | 1   | **25%** ✓ |
| Delegate hits hydrator blind spot, retries                   | 2   | 4   | 2      | 2   | **50%**   |
| Sub-agent with 3 distinct deferred tools                     | 3   | 6   | 3      | 3   | **50%**   |
| Long interactive session                                     | 1   | 50  | 49     | 1   | 2%        |

The 25% figure is accurate for the **common case** of a Delegate sub-agent with a small turn budget (4–8) needing one deferred tool. It understates worst-case.

## 3. Token Cost Model

Every discovery turn is a full chat-completion round with the base-tool schemas AND the `search_tools` description in the prompt. Using OpenAI's default pricing model:

- Base-tool schemas (7 tools × ~150 tokens per schema) ≈ 1.05k tokens
- `search_tools` meta-tool schema ≈ 120 tokens
- Conversation so far: grows linearly with turns
- `search_tools` response (10 hydrated tools × ~120 tokens each) ≈ 1.2k tokens

A single discovery turn writes ≈ 1.2k tokens of "tool-listing" payload into the conversation that subsequent turns re-send. This amortizes into the whole session: a 10-turn session with 1 discovery pays the 1.2k token cost 9 times in re-sent context.

## 4. Remediation Options

### Option 1 — Pre-hydrate From User Input (Framework-Level Indexing)

**Mechanism**: Before the first LLM call of `run_turn(user_message)`, the framework runs the existing `hydrator.search(user_message, top_n=K)` once and adds results to `_hydrated_names`. The LLM sees both base tools AND the top-K relevance matches for its FIRST completion.

**Invariants held**:

- LLM-first reasoning (MUST 1): The framework is NOT classifying user intent; it is retrieving candidate tools via BM25. This is data-retrieval, not decision-making — same slot RAG occupies.
- Tools remain dumb endpoints (MUST 2): No change.
- `search_tools` remains available: Multi-hop follow-up discoveries still work the same way.
- Base-tool set stays small: Pre-hydration adds K≈5 entries on top of base, ~12 total — still within context budget.

**Failure modes**:

- False-positive pre-hydration: if BM25 picks the wrong tools, the LLM sees them but can ignore them. Downside is token waste per turn, not wrong behavior.
- `_hydrated_names` grows faster — must add LRU cap (the Rust `max_hydrated: 50` behavior).

**Implementation scope**: ~80 LOC Python + ~100 LOC Rust. Hooks into `AgentLoop.run_turn` before line 475. Single shard.

**Invariant test**: `hydrator.search` is called with user input before the first `_stream_completion()`; `_hydrated_names` is non-empty on the first turn iff relevance scores > threshold.

**Risk**: LOW. Uses existing primitives; degrades gracefully (if BM25 returns nothing, LLM still can call `search_tools`).

**Expected overhead reduction**: From 25% → 0% in the common case (D=1, T=4). Worst-case (BM25 blind spot) still falls back to the current path.

### Option 2 — Turn-Budget Split

**Mechanism**: Delegate recognizes that the first 2 turns of every session are for discovery, and allocates them from a SEPARATE budget. Advertise `discovery_turns=2` and `work_turns=T`; total cap = `discovery_turns + work_turns`.

**Invariants held**: All. No semantic change to the loop.

**Failure modes**:

- Hides the cost instead of removing it. Still pays discovery tax, just makes it invisible to budget-conscious users.
- Breaks budget predictability: caller sets `max_turns=10` and gets 12.
- Doesn't address worst-case (BM25 miss + retry) which needs 4+ turns.

**Implementation scope**: ~50 LOC, mostly in `config/loader.py` + `delegate.py` + a renamed `_effective_max_turns` property. Single shard.

**Risk**: LOW technical risk, MEDIUM API risk — changes contract of `max_turns` which callers rely on.

**Expected overhead reduction**: Zero on wall-clock or token cost; only cosmetic on the "turns used" metric. **Does not solve the underlying problem.**

### Option 3 — Ranker Verb-Boost

**Mechanism**: Extend BM25 scoring in `hydrator.py::_bm25_score` to boost tools whose names contain common verb-like tokens (search, fetch, list, create, update, delete, deploy, publish, send, query, run, execute). Add a synonym map ("post" → "publish", "call" → "execute").

**Invariants held**: All. LLM-first is preserved; this only improves ranking quality of the dumb data endpoint.

**Failure modes**:

- Curated verb list is an implicit classifier (brittle). `agent-reasoning.md` MUST 4 is subtle here — pre-ranking is not pre-classification because the ranker doesn't DECIDE, it orders. But the verb-boost weights ARE a form of domain bias.
- Addresses section 6d but not 6a/6b/6c. The tax still exists; only the hit rate improves.

**Implementation scope**: ~40 LOC. Single shard, localized to hydrator.py.

**Risk**: LOW — local change, unit-testable.

**Expected overhead reduction**: Reduces worst-case (50% → 25%) by cutting retry rate, but does NOT reduce common case (25% → 25%).

### Option 4 — Batch Discovery (LLM Batches `search_tools` + real tool)

**Mechanism**: Update the `search_tools` description (search.py:35) to explicitly instruct the LLM: "If you know the tool's name already, emit the tool call AND `search_tools(query=...)` in the SAME tool_calls batch. The framework will hydrate the result before your next call." Combined with the existing `get_executor_force()` path (loop.py:683), this lets the LLM save one turn when it has a good guess.

**Invariants held**: All.

**Failure modes**:

- LLM compliance: whether the LLM actually batches depends on the model. GPT-4-class models batch reliably; older / smaller models do not.
- Doesn't help when the LLM doesn't know the tool name (which is WHY it's searching).
- Addresses section 6a partially: when the LLM does batch, T-cost drops to 1 from 2.

**Implementation scope**: ~20 LOC (prompt-engineering change + test). Single shard.

**Risk**: VERY LOW — no architectural change.

**Expected overhead reduction**: Common case with GPT-4 → 12% (one turn saved when batched, zero saved when not). With smaller models → no change.

### Option 5 (synthesized) — Combined: Pre-hydrate + Max-Hydrated Cap + Rust Parity

**Mechanism**:

- Port Rust's `max_hydrated: 50` LRU cap to Python (cross-SDK parity).
- Add Option 1 pre-hydration with a small K (e.g., 5) on `run_turn` entry.
- Leave `search_tools` in place for multi-hop discovery (it's still useful when the pre-hydration misses).
- Optionally layer Option 4's prompt update as a cheap additional win.

**Invariants held**: All. Each individual mechanism preserves the invariants; the composition does too.

**Failure modes**: Superset of Option 1 + Rust parity work.

**Implementation scope**: ~150 LOC Python + ~150 LOC Rust. Single shard each; can parallelize per `rules/agents.md` § Worktree Isolation.

**Risk**: LOW. Uses existing primitives; falls back to current path on pre-hydration miss.

**Expected overhead reduction**: Common case 25% → 0% (from Option 1). Worst case 50% → 25% (from max-hydrated cap preventing context bloat). Plus cross-SDK semantic parity.

## 5. Comparison Table

| Option                    | Common-case overhead | Worst-case overhead | Invariants at risk    | LOC            | Cross-SDK parity work |
| ------------------------- | -------------------- | ------------------- | --------------------- | -------------- | --------------------- |
| Current                   | 25%                  | 50%+                | —                     | 0              | —                     |
| 1. Pre-hydrate            | 0%                   | 25%                 | None                  | 80 Py + 100 Rs | Yes                   |
| 2. Budget split           | 25% (hidden)         | 50% (hidden)        | Caller contract       | 50             | Minor                 |
| 3. Verb-boost             | 25%                  | 25%                 | Data-classifier creep | 40             | Yes                   |
| 4. Batch discovery        | 12%                  | 25%                 | None                  | 20             | Yes                   |
| **5. Combined (1+cap+4)** | **0%**               | **12–25%**          | **None**              | **200**        | **Yes (full)**        |

## 6. Selection Criteria

Per `rules/autonomous-execution.md` § "Feedback Loops Multiply Capacity": Option 1 has an executable feedback loop (BM25 scoring test + Tier 2 Delegate integration test). Option 2 has no feedback loop — it just renames a budget. Option 3 has a feedback loop but small gain. Option 4 is trivial and stackable.

Per `rules/orphan-detection.md` MUST 1 + `rules/facade-manager-detection.md` MUST 1: Option 1 extends an existing wired manager (`ToolHydrator`). It does NOT introduce a new facade — the entry point is the same `AgentLoop.run_turn`. The wiring call site (loop.py ~470) is the production hot path.

Per `rules/cross-sdk-inspection.md` MUST 1: all options require cross-SDK parity. Option 1 is cleanest because both SDKs already have the `hydrator.search(query)` primitive ready for reuse.

## 7. Recommendation

Lowest-risk net-positive: **Option 1 (pre-hydrate from user input)** as the primary fix. It eliminates the common-case 25% overhead while holding every invariant. Option 4 (batch-discovery prompt update) stacks on top at near-zero cost. Option 3 (verb-boost) is an incremental ranker improvement to queue up if residual worst-case overhead matters. Option 2 is not recommended — it cosmeticallly hides the cost rather than removing it.

Detailed recommendation rationale in `recommendation.md`.
