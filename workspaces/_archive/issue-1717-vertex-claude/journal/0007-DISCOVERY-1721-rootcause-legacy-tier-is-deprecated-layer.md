---
type: DISCOVERY
date: 2026-07-14
author: agent
project: issue-1717-vertex-claude
topic: "#1721 root-cause — the legacy from_env tier is a DEPRECATED migration layer in BOTH SDKs; divergence is inside it; fix = retire, not reconcile"
phase: redteam
tags: [cross-sdk, "1721", "1720", from-env, four-axis, root-cause, deprecation]
relates_to: 0006-cross-repo-grant-1721-rust-read-rootcause
---

# #1721 root-cause — read receipt + finding

Cross-repo READ executed under grant journal/0006 (`cross-repo-authorized:
esperie-enterprise/kailash-rs`), read-only, scoped to the LLM env-config surface.

## Both SDKs share ONE intended-canonical design (verified this session)

Python `from_env.py` (module docstring + `resolve_env_deployment`) and Rust
`crates/kailash-kaizen/src/llm/client.rs::from_env` (`client.rs:397-411`,
`424`) implement the IDENTICAL three-tier precedence:

1. **URI tier** — `KAILASH_LLM_DEPLOYMENT` (per-scheme grammar: bedrock/vertex/
   azure/openai-compat).
2. **Selector tier** — `KAILASH_LLM_PROVIDER` = a preset name, resolved through
   the cross-SDK preset registry.
3. **Legacy tier** — per-provider API-key auto-detect, EXPLICITLY documented as
   preserving "today's `autoselect_provider()` ordering" (Python) / a
   `push_legacy_dep!` macro loop (Rust). BOTH emit the SAME migration warning
   `llm_client.migration.legacy_and_deployment_both_configured` when a legacy
   key coexists with a deployment-tier signal; the deployment path wins.

## The #1721 divergence lives ENTIRELY in the deprecated tier

The Azure-vs-6-provider / order divergence (journal/0005: Python 5 keys w/Azure;
Rust 10 keys w/o Azure) is a property of tier 3 ONLY. Tiers 1-2 (URI + preset
selector) are the canonical surface and are aligned in SHAPE across both SDKs;
the preset-registry drift (42-vs-24) was already reconciled on main (commit
`54ed7e297`).

## Root-cause finding

Reconciling the two divergent legacy key-lists (the earlier "accept divergence"
OR "align the lists" dispositions) is **polishing a surface both SDKs intend to
retire.** The optimal root-cause fix:

1. **Freeze the canonical surface as the sole cross-SDK contract** — URI grammar
   - preset registry byte-identical across SDKs (guarded by the cross_sdk_parity
     fixtures). This is the real invariant #1721's parity tests should assert.
2. **Deprecate the legacy per-key auto-detect tier in BOTH SDKs** — emit a
   `DeprecationWarning` / WARN on legacy-ALONE resolution (today the warning
   fires only when legacy + deployment coexist), pointing users at
   `KAILASH_LLM_PROVIDER=<preset>`. One-minor-cycle deprecation per
   `zero-tolerance.md` Rule 6a (removing Azure auto-detect is a breaking change
   for Azure-env-only users → needs the shim cycle).
3. **Retire the legacy tier** after the cycle. The Azure/6-provider divergence
   dissolves — there is nothing to reconcile once the tier is gone.

## #1721 IS a symptom of #1720

#1720 ("retire the legacy providers/llm layer onto four-axis") OWNS this. The
from_env legacy-tier deprecation is a coherent SUB-workstream of #1720 — and it
can proceed INDEPENDENTLY of #1720's harder chat()-path four-axis parity work
(tools/structured-output/multimodal), because the from_env URI/selector path is
already complete: a bare-`OPENAI_API_KEY` user migrates by setting
`KAILASH_LLM_PROVIDER=openai`.

## For Discussion

1. Should the legacy-tier deprecation land as its own cross-SDK lockstep pair
   (py + rs deprecation warnings same cycle), folded under #1720?
2. Does any real user depend on bare-key auto-detect such that the migration
   docs must call out the `KAILASH_LLM_PROVIDER=<preset>` path prominently?
