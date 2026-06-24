# FNEW-5 — provider-intrinsic default-model constants (2026-06-11)

Closes the last open **code** item from the FNEW wave (receipt 22 § "Out-of-class
dispositions"). FNEW-6 remains blocked on infra (live Redis/providers; Tier-2
NO-MOCKING cannot be driven green in this environment).

## Design decision (user-gated)

User selected **Path B** (non-breaking): keep the provider-intrinsic defaults,
promote to documented named constants, refresh stale ones. Rejected Path A
(raise/env-only) because it breaks `auto_detect_provider()` zero-config for every
caller without a per-provider model env. Receipt: AskUserQuestion this session,
"Keep provider-intrinsic defaults (non-breaking)".

## What shipped (working tree — uncommitted, BUILD repo, commit stays with user)

| File                                                                     | Change                                                                                                                                                                                                                                                                                                                                                 |
| ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `src/kaizen/config/providers.py`                                         | 9 inline `default_model = "..."` literals → documented module-level `DEFAULT_<PROVIDER>_MODEL` constants + env-models carve-out header (provider-intrinsic / env-overridable / NOT chained to `KAIZEN_DEFAULT_MODEL`). Stale anthropic default `claude-3-haiku-20240307` → `claude-haiku-4-5` (+ docstring).                                           |
| `src/kaizen/providers/document/openai_vision_provider.py`                | Carve-out comment above existing `DEFAULT_MODEL` named constant.                                                                                                                                                                                                                                                                                       |
| `tests/regression/test_issue_fnew5_provider_intrinsic_defaults.py` (NEW) | 40 tests: 9 providers × 4 contracts (default resolution / env-override precedence / arg precedence / **KAIZEN_DEFAULT_MODEL non-leak**) + value pins + anthropic-refresh guard + embedding-default guard + vision-default pin.                                                                                                                         |
| `tests/unit/config/test_providers_azure_docker.py`                       | **Zero-tolerance Rule 1 (R1 INFO closure):** 6 legacy `AZURE_AI_INFERENCE_*` setenv sites → canonical `AZURE_ENDPOINT`/`AZURE_API_KEY` (cleared the intentional `DeprecationWarning` noise); added dedicated `test_legacy_env_vars_emit_deprecation_warning` (`pytest.warns`, +coverage); hardened "missing-credential" tests to clear all 3 variants. |

Anthropic refresh verified real (not fabricated): `claude-haiku-4-5` is mapped in
`llm/grammar/vertex.py:100` + `llm/grammar/bedrock.py:89` and used in 8 src sites.

## Redteam round history (durable receipts)

| Round | Agent (task ID)                                   | Verdict                            | Notes                                                                                                                                                                                                                                                                    |
| ----- | ------------------------------------------------- | ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| R1    | reviewer `a7675ba8183e9e67c`                      | **CLEAN**                          | 7 mechanical sweeps + 5 judgment checks pass; 40 tests lock every contract; carve-out rationale accurate; no in-scope stale default missed.                                                                                                                              |
| R1    | security-reviewer `a9f5f6cc73522faba`             | **CLEAN**                          | Credential handling / SSRF guard / `__repr__` redaction / `provider_config_to_dict` exclusion byte-identical; test keys are placeholders; model-string is opaque data (no injection surface).                                                                            |
| R1    | kaizen-specialist `a5fe9c287ac69d673` (Bash+Read) | **CONVERGED-CLEAN** (FNEW-5 scope) | Closure-parity table: every scoped site covered, excluded sites (`token_counter.py`, `capabilities.py`) untouched, zero-config preserved, no mismatch-chaining. Surfaced 1 **pre-existing** INFO (Azure deprecation warnings) — proved pre-existing via stash-and-rerun. |
| R2    | mechanical (this session)                         | **CLEAN**                          | Azure INFO fixed (all 6 sites). Full surface `193 passed` under `-W error`, **0 warnings / 0 failures**; ruff clean across all 4 files; FNEW-5 test `40 passed`.                                                                                                         |

## Convergence

- **0 CRITICAL / 0 HIGH / 0 MEDIUM / 0 LOW** across all R1 agents.
- R1 (3-agent) FNEW-5 CLEAN + R2 mechanical CLEAN = 2 consecutive clean passes.
- R1 INFO (Azure warnings) closed per zero-tolerance Rule 1 + log-triage gate
  (observability Rule 5): **Fixed** — `-W error` proves 0 warnings.
- New module has new tests (40, importing the changed module). Posture L5_DELEGATED.

## Verification commands (re-derivable)

```bash
# FNEW-5 surface, full config, regression — 0 warnings under -W error
.venv/bin/python -m pytest \
  packages/kailash-kaizen/tests/unit/config/ \
  packages/kailash-kaizen/tests/unit/nodes/ai/test_google_provider.py \
  packages/kailash-kaizen/tests/unit/nodes/ai/test_perplexity_provider.py \
  packages/kailash-kaizen/tests/regression/test_issue_fnew4_env_model_defaults.py \
  packages/kailash-kaizen/tests/regression/test_issue_fnew5_provider_intrinsic_defaults.py \
  packages/kailash-kaizen/tests/regression/test_issue_255_provider_config_dual_purpose.py \
  -q -p no:randomly -W error          # → 193 passed

# No inline default_model literal remains; no getter chains KAIZEN_DEFAULT_MODEL
grep -nE 'default_model\s*=\s*"' packages/kailash-kaizen/src/kaizen/config/providers.py  # → empty
grep -n 'KAIZEN_DEFAULT_MODEL' packages/kailash-kaizen/src/kaizen/config/providers.py     # → comment only
```

## Outstanding after FNEW-5

- **FNEW-6** — never-gated integration tiers (Redis/provider live infra). Blocked
  on infra-up env; Tier-2 NO-MOCKING. Value-anchor: zero-tolerance Rule 1 backlog.
- **Loom follow-up** — the env-models carve-out for provider-intrinsic defaults is
  documented in-code here but the `env-models.md` rule (synced) does not yet carve
  it out; a future `/redteam` could re-flag `DEFAULT_<P>_MODEL` literals. Recommend
  a loom `/codify` to add the provider-specific-getter carve-out to `env-models.md`.
- Commit/PR/release stay with the user (BUILD repo). This wave is ready for the
  commit gate.
