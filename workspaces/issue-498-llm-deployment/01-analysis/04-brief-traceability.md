# Brief → Spec → Plan Traceability

Every success-criterion bullet in `briefs/01-scope.md` MUST map to a spec section AND a shard section. Unmapped = BLOCKING.

## Brief "Semantic invariants (MUST match Rust per EATP D6)"

| Brief bullet                                                | Rust spec §                     | Python plan shard                                                                                                                                        | Python coverage                                                                                                           |
| ----------------------------------------------------------- | ------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| Preset names list                                           | §3 Presets; §8 Cross-SDK parity | S1+S2 (openai, mock), S3 (anthropic, google, groq, openai_compatible, anthropic_compatible), S4a (bedrock_claude), S5 (vertex_claude), S6 (azure_openai) | 9 presets from brief list; `01-shard-breakdown.md` S1-S6. Parity tests in S9.                                             |
| `from_env()` precedence: URI > selector > legacy            | §5 from_env + §8                | S7 `LlmClient.from_env()`                                                                                                                                | `01-shard-breakdown.md` S7 tests `test_from_env_uri_*`, `test_from_env_selector_*`, `test_from_env_legacy_*`.             |
| `AWS_BEARER_TOKEN_BEDROCK` alone activates `bedrock_claude` | §5.4                            | S4a + S7                                                                                                                                                 | S4a tests `test_from_env_legacy_aws_bearer_activates_bedrock.py`; S7 legacy-tier integration.                             |
| `deployment_preset` log field (NOT credential)              | §7 Observability                | S1+S2 (initial emit path) + every auth shard                                                                                                             | `01-shard-breakdown.md` global invariant "every shard MUST emit `deployment_preset`"; S9 parity test asserts field names. |
| SSRF + DNS-rebinding defense                                | §6.1, §6.6                      | S1+S2 (SSRF `url_safety.check_url`) + S4c (DNS rebinding `SafeDnsResolver` + `LlmHttpClient`)                                                            | S1+S2 unit tests `test_endpoint_rejects_*`; S4c Tier 1 + integration security tests.                                      |

## Brief "Back-compat constraints (MUST hold)"

| Brief bullet                              | Python plan                                                                                                                                                                                                                            |
| ----------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `kailash.LlmClient()` today               | **Python-specific note:** `LlmClient` does NOT exist today (verified in `02-kailash-py-current-state.md` §1). The Python back-compat surface is the provider registry. Python introduces `LlmClient()` ADDITIVELY; zero callers break. |
| `kailash.Agent(config, client)`           | No `Agent(config, client)` API today; what exists is `kaizen/agent.py` + `kaizen/core/agents.py`. Preserved unchanged in S1–S9.                                                                                                        |
| Legacy env-key detection in `from_env()`  | S7 — `LlmClient.from_env()` legacy tier preserves `autoselect_provider()` ordering byte-for-byte. Regression test `test_from_env_legacy_ordering.py`.                                                                                  |
| Zero breaking changes for today's callers | `01-shard-breakdown.md` global invariant: no file under `kaizen/providers/` changes public API signatures; collect-only gate runs every shard.                                                                                         |

## Brief "Shards (mirror of Rust S1–S9)"

| Brief shard                                                  | Python plan location                                                                                                                                                      |
| ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| S1 — Foundation types in `kailash/kaizen/llm/deployment.py`  | `01-shard-breakdown.md` S1+S2 (bundled per Rust session plan). File: `packages/kailash-kaizen/src/kaizen/llm/deployment.py`.                                              |
| S2 — Migrate OpenAI path to preset                           | `01-shard-breakdown.md` S1+S2.                                                                                                                                            |
| S3 — Migrate Anthropic + Google                              | `01-shard-breakdown.md` S3 (extended to cohere, mistral, perplexity, huggingface, ollama, docker, groq, together, fireworks, openrouter, deepseek, lm_studio, llama_cpp). |
| S4 — AWS auth + `LlmDeployment.bedrock_claude(...)` + Tier 2 | `01-shard-breakdown.md` S4a + S4b-i + S4b-ii + S4c (split per invariant budget).                                                                                          |
| S5 — GCP auth + Vertex presets                               | `01-shard-breakdown.md` S5.                                                                                                                                               |
| S6 — Azure auth + `LlmDeployment.azure_openai(...)`          | `01-shard-breakdown.md` S6-i + S6-ii (split per invariant budget).                                                                                                        |
| S7 — `from_env()` richer config                              | `01-shard-breakdown.md` S7.                                                                                                                                               |
| S8 — N/A (Python IS the binding surface)                     | `01-shard-breakdown.md` S8 repurposed for Python ergonomics (plugin presets, sync client). Optional merge into S9.                                                        |
| S9 — Parity test suite vs Rust SDK; docs update              | `01-shard-breakdown.md` S9.                                                                                                                                               |

## Brief "Success criteria (verbatim from #498)"

| Success bullet                                                                            | Python plan coverage                                                                                                                                                                                                                                                                                 |
| ----------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [ ] Foundation types land in `kailash/kaizen/llm/deployment.py`                           | **S1+S2** creates `deployment.py` at `packages/kailash-kaizen/src/kaizen/llm/deployment.py`. Files listed in `01-shard-breakdown.md` S1+S2 "Files to create".                                                                                                                                        |
| [ ] OpenAI, Anthropic, Google paths migrated to preset-backed impl                        | **S1+S2** (OpenAI) + **S3** (Anthropic, Google). Adapters in `kaizen/providers/llm/*.py` become thin delegators.                                                                                                                                                                                     |
| [ ] Bedrock-Claude, Vertex-Claude, Azure OpenAI presets functional with real Tier 2 tests | **S4a** (Bedrock-Claude + Tier 2), **S5** (Vertex-Claude + Tier 2 gated on `GOOGLE_APPLICATION_CREDENTIALS`), **S6** (Azure OpenAI + Tier 2 gated on `AZURE_OPENAI_RESOURCE`). Tier 2 files under `tests/integration/llm/`.                                                                          |
| [ ] `from_env()` URI parser + legacy fallback                                             | **S7** — `LlmClient.from_env()` full precedence, URI parser in `kaizen/llm/from_env.py`, legacy fallback preserves `autoselect_provider()`.                                                                                                                                                          |
| [ ] Parity test suite vs Rust SDK (preset names, env precedence, observability shape)     | **S9** — `tests/cross_sdk_parity/test_preset_names_match_rust.py`, `test_from_env_precedence_matches_rust.py`, `test_observability_field_names_match_rust.py`, `test_error_taxonomy_matches_rust.py`. Shared fixture files imported from a cross-repo source.                                        |
| [ ] Existing `LlmClient()` callers continue to work unchanged                             | **No today-callers exist** (`02-kailash-py-current-state.md` §1). Criterion reinterpreted as: every caller of `kaizen.providers.registry.*` + `kaizen.config.providers.*` continues unchanged. Global invariant in `01-shard-breakdown.md`; enforced by `pytest --collect-only -q` gate every shard. |

## References (local) traced

| Brief reference  | Verified                                                                                                                                                                                                             |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Rust design spec | `/Users/esperie/repos/loom/kailash-rs/specs/llm-deployments.md` (724 lines; read in `01-rust-spec-synthesis.md`).                                                                                                    |
| Rust ADR         | `/Users/esperie/repos/loom/kailash-rs/workspaces/use-feedback-triage/02-plans/02-adrs/ADR-0001-llm-deployment-abstraction.md` (217 lines; read and adapted in `02-plans/02-adr-0001-llm-deployment-abstraction.md`). |
| Rust BUILD issue | kailash-rs#406 — cross-referenced in Python ADR § Cross-SDK.                                                                                                                                                         |
| Reporter chain   | kailash-coc-claude-rs#52 — cross-referenced in Python ADR.                                                                                                                                                           |

## Unmapped = BLOCKING

**None identified.** Every brief bullet maps to at least one spec section + one shard.

One interpretive note for the user: the brief's "Existing `LlmClient()` callers continue to work unchanged" was written against the Rust shape (where `LlmClient` exists today). Python has no `LlmClient` today; we've reinterpreted the criterion as preserving the actual Python back-compat surface (provider registry). This is an execution-gate clarification, not a scope cut — if the user intends something different, flag at `/todos` approval.

## Notes

- `specs/_index.md` will gain an `llm-deployments.md` entry at **S9** (same session as the cross-SDK parity suite + migration guide). `specs/llm-deployments.md` will mirror the Rust spec's structure, with Python-specific notes.
- Loom rules authored in Rust S9 (`rules/llm-deployment-coverage.md`, `rules/llm-auth-strategy-hygiene.md`, `rules/observability.md` extension "Mask HTTP Auth Headers") apply cross-SDK — if a Python-specific variant section is needed, it lands at S9.
