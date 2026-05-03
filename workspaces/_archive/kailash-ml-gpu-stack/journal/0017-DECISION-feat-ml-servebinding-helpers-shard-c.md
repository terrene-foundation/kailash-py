---
type: DECISION
date: 2026-04-20
created_at: 2026-04-20T07:56:32.455Z
author: agent
session_id: 9f1976ea-96de-4ea2-ab97-ab52a17debbb
session_turn: n/a
project: kailash-ml-gpu-stack
topic: define _ServeBinding + _row_count_of helpers for MLEngine predict/serve (shard-C)
phase: implement
tags: [auto-generated, kailash-ml, mlengine, serve, predict, helpers, shard-c]
related_journal: []
---

# DECISION — define \_ServeBinding + \_row_count_of helpers (shard-C)

## Commit

`18a5ec1a6635` — feat(ml): define \_ServeBinding + \_row_count_of helpers (shard-C)

## Body

Completes the helper set referenced by `MLEngine.predict()` / `serve()`:

- `_ServeBinding` dataclass — records channel/uri/invoke/shutdown per bind
- `_noop_shutdown` — default cleanup for in-process bindings
- `_parse_model_uri` — parses `models://name/v<N>` or bare name → (name, ver)
- `_features_to_payload` — normalises dict/list/polars DF to payload mapping
- `_row_count_of` — observability counter for predict log lines
- `_run_onnx_inference` — onnxruntime dispatch for direct channel
- `_run_native_inference` — pickle fallback when ONNX export unavailable

Also fixes the possibly-unbound `channel` name in `serve()`'s partial-failure logging path by introducing `current_channel` tracked across the loop body.

With these helpers in place, `from kailash_ml import MLEngine, PredictionResult, ServeResult` and the 7 MLEngine construction unit tests all pass.

Pre-commit hooks bypassed via `core.hooksPath=/dev/null` to avoid pre-commit auto-stash interaction per `rules/git.md` § "Pre-Commit Hook Workarounds".

## For Discussion

1. **Counterfactual**: The `_run_native_inference` helper provides a pickle fallback when ONNX export is unavailable. Per `specs/ml-engines.md` §6.1 MUST 4, `register()` should raise `OnnxExportError` on ONNX failure rather than silently falling back to pickle. Does the existence of `_run_native_inference` as a fallback in the predict path create an implicit escape hatch that undermines the loud-failure contract at register time?

2. **Data-referenced**: The `_parse_model_uri` helper parses both `models://name/v<N>` and bare name formats. The 7 MLEngine construction unit tests are referenced as passing after this commit. Do any of those tests specifically exercise the URI parsing with the `models://` scheme, or only the bare-name path?

3. **Design**: `_ServeBinding` is a dataclass recording channel/uri/invoke/shutdown per bind. The `_noop_shutdown` default suggests in-process bindings have no cleanup cost. For a long-running serve() loop with multiple bindings, are stale `_ServeBinding` entries (e.g., from a transport that disconnected) purged from the binding list, or do they accumulate until the engine is garbage collected?
