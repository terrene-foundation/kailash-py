# #1947 Launch Ledger (durable — survives compaction)

Branch: `fix/1947-llm-agent-fail-loud-provider` — **PR #1951** (base main).
Commits: `809388c8e` (base node fail-loud), `8144ea5d3` (IterativeLLMAgentNode subclass fix), `df4bc4c3b` (docstrings). All pushed.

## What landed

- `llm_agent.py`: provider default "mock"→None; `run()` raises ConfigurationError when None.
- `iterative_llm_agent.py`: guard at top of run() (subclass swallowed the base guard → success=True template); dropped 2 silent `provider="openai"`.
- Docstrings (framework.py ×2, agents.py ×1): show explicit provider.
- Regression test: base + iterative subclass (7 tests). 1 iterative unit test made provider explicit.

## Verification (direct, runtime)

- Base LLMAgentNode: no-provider → ConfigurationError; explicit mock works. Unit oracle: 1289 pass 0 provider-regressions.
- IterativeLLMAgentNode: no-provider → ConfigurationError (was success=True template); explicit mock works. Iterative unit files: 18 pass.
- A2AAgentNode: no-provider → ConfigurationError (fails loud). Only 2 real LLMAgentNode subclasses exist.
- Non-unit 18 fails ALL pre-existing (stash-proven; real-API key + memory flake).
- CI FAST-tier "0 selected" on first PR run = TRANSIENT FLAKE (same commit passed on push; re-run green; local selects 6776/8328).

## Redteam

- **Round 1** (reviewer aa204d…, security a211a8…, kaizen a6c709…): reviewer found HIGH IterativeLLMAgentNode swallow (runtime-confirmed) → FIXED. security found HIGH `detect_provider_from_env`→"mock" residual → #1952. kaizen: MINOR bump 2.42→2.43, ConfigurationError correct, 3 docstrings LOW → FIXED. All in-scope BUG/INVEST-NOW resolved.
- **Round 2** DONE (both lenses): both independently found ONE in-scope item — the `iterative_llm_agent.py:1760` `provider="openai"` twin my replace_all missed (16 vs 20 space indent) + commit over-claim → FIXED in `d8c70bcfa`. Both confirmed class functionally CLOSED (mutation test: revert guard → regression test FAILS). Finding B (synthesis masks resolved-provider runtime failure as success=True) → **#1953** (distinct class).
- **Round 3** DONE: **BOTH lenses CONVERGED** — no new in-scope BUG/INVEST-NOW; mutation-tested (revert guard → regression test FAILS); reviewer found a 4th family member `SelfOrganizingAgentNode(A2AAgentNode)` — also fails loud. One LOW (A2A closure inheritance-only + unpinned) → CLOSED via family-pin tests (`c5fb050f4`).

## CONVERGED (7 reviews / 3 rounds)

Silent-mock (fabricated-content-as-real) class CLOSED on the omitted-provider axis for the whole LLMAgentNode family: LLMAgentNode + IterativeLLMAgentNode (own guards) + A2AAgentNode + SelfOrganizingAgentNode (inherited guard, now pinned). Explicit provider="mock" preserved. All findings resolved or tracked (#1952 deferred residuals, #1953 runtime-error-masking).

Commits (5): 809388c8e, 8144ea5d3, df4bc4c3b, d8c70bcfa, c5fb050f4 — all pushed. PR #1951.

Commits now: 809388c8e, 8144ea5d3, df4bc4c3b, d8c70bcfa (all pushed).
Issues filed: #1952 (deferred residuals), #1953 (runtime-error-masking, distinct class).

## Deferred (tracked — NOT this shard)

- **#1952** filed: (a) `detect_provider_from_env()`→"mock" keyless fallback (HIGH, Agent/RAG surface, 30+ sites); (b) EmbeddingGeneratorNode silent-mock (MED). Both exceed #1947 shard (own prod-audit + test sweep). Value-anchor: fully closes fabricated-content integrity class.

## Next

- Collect round-2 verdicts → if clean, that's 1 clean round (round 1 was NOT clean). Need 2 consecutive clean → run round 3 if round 2 clean.
- Verify new-commit CI green (kaizen FAST flake watch).
- On convergence + green CI: admin-merge PR #1951, then /release (kaizen MINOR 2.42.0→2.43.0; CHANGELOG behavior-change/migration note; feedback_build_repo_release).
- Cross-SDK (cross-sdk-inspection MUST-1): Rust SDK equivalent node mock-default check — HUMAN-GATED cross-repo filing; surface as PENDING (handoff-completion), do NOT self-file.
