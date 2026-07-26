# Launch Ledger — kaizen mock-upgrade provider-guard fix (2026-07-23)

Branch: `fix/kaizen-mock-upgrade-provider-guard` (off `main`, BUILD repo kailash-py).
Durable per orchestration-launch-ledger MUST-1 (survives compaction). Consult BEFORE spawning; match completions against it.

## What / why

Forest audit (workflow wf_13d00845-93b) found ONE confirmed HIGH bug: a test-harness "mock-upgrade"
(`_generate_intelligent_mock_response` + `is_mock_response` classifier) ran on the PRODUCTION agent
response path in `packages/kailash-kaizen/src/kaizen/core/agents.py` with no provider guard — a real LLM
answer opening "Based on the provided data and context…" could be silently replaced with fabricated
answers ("4"/"Paris"). zero-tolerance Rule 2 + Rule 3. Fix = provider-gate (fire only when provider is
genuinely mock), NOT remove. Blast radius: 1 test file. Not previously tracked.

## Launch ledger

| track                   | agent id                              | status                 | notes                                                                       |
| ----------------------- | ------------------------------------- | ---------------------- | --------------------------------------------------------------------------- |
| implement-fix (initial) | af74a018a9d9bc7c0 (kaizen-specialist) | landed                 | added `_is_mock_provider_active` gate + 35 tests; 74 passed                 |
| redteam R1 reviewer     | a72b7ad773299e453                     | landed                 | CRITICAL: `_signature_workflow` cache/gate desync                           |
| redteam R1 security     | a21f53ab5df46e43d                     | landed                 | CRITICAL cache desync + HIGH WARN-log PII                                   |
| redteam R1 adversarial  | a6f2c026e74cafd34 (pattern-expert)    | landed                 | CRITICAL cache desync + INVEST-NOW execute_cot/react always-mock            |
| fix R1 findings         | af74a018a9d9bc7c0 (resumed)           | IN-FLIGHT (background) | FIX1 cache-invalidate, FIX2 log-hash, FIX3 docstring, FIX4 pattern provider |

## Redteam Round 1 findings (must be resolved before convergence)

- FIX1 CRITICAL — invalidate `_signature_workflow` on update_config/set_signature/reset (dispatch/gate desync + update_config no-op).
- FIX2 HIGH — WARN logs dumped raw inputs/response (PII); hash+length instead, keep mode=fake.
- FIX3 — scope down over-broad test docstring.
- FIX4 HIGH pre-existing — `_execute_with_pattern` (execute_cot/react) never sets provider → always mock-dispatch; add `base_params["provider"]`. Blast-radius-gated (stop if >2 tests break).

## Redteam Round 2 (NOT clean — convergent; root-caused)

- R2 reviewer a5e8cb63ee08b4b2f: FIX1-4 correct+complete; NEW same-class BUG `compile_workflow()` omits provider; pyright L346+ = benign (execute() Union return); pre-existing `test_intelligent_responses_integration.py` 8/12 fail — proven NOT a regression (git-stash A/B).
- R2 security a0d16017a9a685226: cache-desync NOT fully closed — direct `self.config[...]=` bypasses the 3 mutators; recommend threading dispatched provider into gate.
- R2 adversarial a067d5a48328068b2: BREAK A communicate_with/broadcast never set provider (+no gate → raw mock template verbatim); BREAK B env-race mid-call gate≠dispatch; BREAK C direct config mutation bypasses FIX1.
- ROOT CAUSE: (1) gate re-derives provider ≠ dispatched; (2) provider omitted at sibling sites. Structural fix dispatched.

## Round 3 fix (in-flight)

- Part A: thread dispatched provider into `_extract_intelligent_response` + `_apply_intelligent_mock_conversion_to_llm_result` (gate==dispatch by construction).
- Part B: sibling-site sweep — set provider at communicate_with + compile_workflow (+ keep FIX4). security.md Multi-Site Kwarg Plumbing.
- Part C: docstring, _fingerprint_payload try/except, pyright isinstance narrowing, regression tests for config-mutation/communicate_with/compile_workflow.
- Flag: pre-existing integration-test marker (separate class) — follow-up unless trivially registered.

## Round 3 (breaks A/B/C CLOSED — 200-iter stress test 0 desyncs) + new siblings

- FIX5 nexus/base.py:53 WRONG key `llm_provider`→`provider` (always mock even w/ real provider). CONFIRMED.
- FIX6 base_agent.py:621 omits provider when config.llm_provider None → mock (Nexus-deploy reachable). CONFIRMED.
- FIX7 4 more unmarked real-LLM tests (Paris/Jupiter/4/25 collide w/ hardcoded mock). Same file as Part D.
- Round 4 fix (FIX5/6/7) IN-FLIGHT (af74a018a9d9bc7c0 background).

## Agent-surface LLMAgentNode enumeration (for convergence)

- agents.py (6 sites) FIXED; signatures/core.py _create_llm_agent_params FIXED; base_agent.py + nexus/base.py IN-FLIGHT.
- workflow_generator.py:272/422 SAFE (set `provider ... or "openai"`, never mock).
- agents.py:398 Agent.to_workflow() returns config dict — consumer-dependent; FLAG for Round 4 review.

## Follow-up issues to FILE (post-convergence, same repo kailash-py; cross-SDK inspect Rust kaizen):

- ISSUE A (verify-first): nodes/rag/*.py — 8/10 files reference LLMAgentNode extensively w/ provider-keys=0 (advanced/agentic/conversational/evaluation/graph/multimodal/query_processing/similarity); router.py+workflows.py DO set it. Whole advanced-RAG surface may mock-dispatch. VERIFY then fix (own plan, exceeds shard).
- ISSUE B (ROOT CAUSE, strategic): llm_agent.py:370 LLMAgentNode provider `default="mock"` — every omission silently mock-dispatches. Propose fail-loud/require-provider default. HIGH blast radius (breaks intended-mock tests) → own plan + user decision.
- INCREMENTAL follow-ups (from R2/R3): dead code _execute_direct_cot/react (orphan); signature.parameters={provider} silent override; _current_execution_inputs concurrency; model/provider-mismatch in env-detect.

## Convergence round (1 converged, 2 found gaps) → Round 5 fix

- Reviewer: CONVERGED (Agent surface exhaustively covered except to_node_config orphan).
- Security a0584ee9c652aa83d: BLOCKING FIX8 — deployment_cache.py:52-86 create_cache_key hashes raw config.llm_provider (None when unset) → provider-blind; cached mock workflow served after keys arrive (FIX5/6 exposed this). +e2e test file same vacuous-mark class.
- Pattern-expert a0f52428503fd51bb: FIX9 — agents.py:392 to_node_config() omits provider → mock. Public orphan (0 callers). Same class.
- Round 5 fix: FIX8 (cache key resolved-provider) + FIX9 (to_node_config setdefault provider) + FIX10 (e2e test marks) + FIX11 (dedup nexus/base.py comment) + FINAL exhaustive re-sweep for any other provider-blind cache/serialization. IN-FLIGHT.

## Round 6 (final convergence) — 3 reviewers converged on ONE deeper break

- FIX8 (cache key) correct at its layer BUT defeated by workflow MEMOIZATION: BaseAgent.to_workflow() (base_agent.py:587/624, invalidated only by cleanup()) + Agent.compile_workflow() (_is_compiled/_workflow, invalidated only by update_config/set_signature/reset) hold a stale provider on ambient-ENV change. Reproduced end-to-end through deploy_as_api incl. clear_deployment_cache — still serves mock. My env-dependent-resolution fix EXPOSED this.
- FIX9 to_node_config CONFIRMED closed.
- Siblings (lower risk, follow-up): caching_mixin._make_cache_key provider-blind (TTL 300s, opt-in OFF default); caching_enabled/batch_processing_enabled flag-name mismatch; DeploymentCache key omits system_prompt/temperature (cross-agent collision).
- Round 7 fix: FIX12 BaseAgent.to_workflow memo-invalidate-on-provider-drift; FIX13 Agent.compile_workflow same; FIX14 scope FIX8 docstring honestly. HARD STOP: if Round 8 finds another core-surface layer → escalate ISSUE B (fail-loud default) to user.

## Next steps

1. Await af74a018a9d9bc7c0 (background) → verify fixes + full test receipts.
2. Redteam Round 2 (need 2 consecutive clean rounds on BUG+INVEST-NOW). R1 was NOT clean.
3. If FIX4 was split out → file follow-up issue on kailash-py (this repo).
4. On convergence: PR → merge → BUILD-repo release (kaizen-agents/kailash-kaizen version bump), surface release decision to user.
5. Cross-SDK inspection (cross-sdk-inspection Rule 1): does the Rust SDK kaizen have an equivalent mock-upgrade-on-production-path? FLAG for verify (repo-scope: do not read rs; surface as candidate).

## POST-RELEASE STATE (2026-07-24)
- ✅ kaizen 2.41.0 SHIPPED: PR #1944 merged (main 2bd8ec7f4); PyPI 2.41.0 LIVE; clean-venv import verified.
- Tracking issue #1943 (main bug) CLOSED by #1944.
- Follow-ups FILED: #1946 (RAG provider sweep — part 1), #1947 (LLMAgentNode fail-loud default — root cause, gated on #1946 + test sweep), #1948 (minor: caching_mixin/flag-name/workflow_generator/cache-key/pre-existing nexus e2e fails).

## IN-FLIGHT background agents (launch ledger)
| track | agent | branch/worktree | status |
| --- | --- | --- | --- |
| #1945 release-record docs | af2f634fe188cfe4d (release-specialist) | docs/release-record-kaizen-2.41.0 (main checkout) | finishing (CI) |
| #1946 RAG provider sweep | ac94a0197f465f248 (kaizen-specialist) | worktree .kailash-py-wt/rag-provider-sweep, branch fix/1946-rag-provider-sweep | implementing (verify-first + ~29 sites + tests + 2.42.0 bump) |

## Next: RAG sweep → redteam to convergence → release 2.42.0 → test sweep + fail-loud (#1947).
