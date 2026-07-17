# #1720 creds-in-logs sweep — convergence receipt (2026-07-17)

Redteam-to-convergence over the creds-in-logs class (MED-1 sibling of kaizen 2.34.0).

## Rounds (task IDs)
- Round 1 classify: w12fiw5rf — 216 sites swept, 86 flagged, 11 confirmed
- Round 2 sibling-sweep: w98zpn87z — fixes held; +4 confirmed (tool-exec, agent.py, azure.py sibling, ai_behavior)
- Round 3 convergence: ww9b9ryqo — +azure_backends (6) + cohere
- Round 4 convergence: wt0l5txr3 — +openai_vision + alert_manager webhook
- Round 5 convergence: wvq8bxx30 — +iterative_llm_agent, workflow_generator, agent_loop, base_agent (MCP class)
- Round 6 convergence: wo9znu7ch — **CONVERGED** (verify-all-fixes 0/0, residual-exc-info 0/0, residual-return-metric 0/0)

## Evidence
- 22 source files, 85 sanitize/mask sites, 8 behavioral regression tests (test_issue_1720_creds_in_logs_sweep.py).
- Exhaustive grep across all 54 credential-bearing modules → zero remaining raw-exception logs.
- Helpers: sanitize_provider_error (existing), _mask_redis_url (new, rate_limiter), _mask_webhook_url (new, alert_manager — webhook tokens live in URL path, not covered by provider sanitizer).

## Cross-SDK (pending, needs authorization)
The Rust SDK four-axis LLM client + provider error handlers very likely carry the same creds-in-logs class
(exc_info on provider exceptions, MCP transport URL in logs). Per cross-sdk-inspection Rule 1 this warrants a
`cross-sdk` issue on the Rust SDK BUILD repo — requires the five repo-scope-discipline conditions + user authorization.

## Pre-existing (NOT this PR — confirmed failing on clean HEAD)
8 unrelated failures: ollama_model_manager vision-setup, ollama_availability, example_validation gallery docs.
Outside the CI gate (2.34.0 released green with them). Separate shard.
