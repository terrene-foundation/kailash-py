---
type: RISK
date: 2026-04-01
created_at: 2026-04-01T14:05:00+08:00
author: co-authored
session_turn: 75
project: kailash-align
topic: Previous kailash-rs analysis was superficial — missed 179-todo native Rust ML training roadmap
phase: analyze
tags: [cross-sdk, kailash-rs, risk, analysis-quality, correction]
---

# Superficial kailash-rs Analysis Risk

## Finding

The initial kailash-rs gap analysis (doc 11, first version) characterized kailash-rs as "inference-only via ONNX/Tract/Candle" and recommended "training stays in Python." This was:

1. **Technically accurate for v3.6.4** (no training code exists today)
2. **Strategically wrong** — kailash-rs has a 179-todo, 17-crate roadmap for full native Rust ML training, including gradient boosting engines targeting LightGBM-competitive performance

The analysis read README files instead of source code, and missed the `workspaces/kailash-ml-crate/` workspace entirely on first pass. This led to incorrect framing in the synthesis and kailash-rs workspace brief.

## Impact

- The `kailash-align-serving` workspace brief incorrectly states "Training happens in Python (kailash-align)" for ALL ML — this is only true for LLM alignment, not classical ML
- The synthesis document's "kailash-rs gap" section was misleading
- kailash-rs team could have received incorrect guidance to skip native training

## Correction Applied

Document 11 rewritten with:

- Full source code audit (2,866 lines across 12 .rs files)
- 179-todo roadmap documented
- Correct framing: LLM alignment = Python training + Rust serving; Classical ML = native Rust training (planned)
- kailash-align-serving brief remains correct for its scope (LLM serving only)

## Root Cause

Research agents used `grep` for keywords instead of reading actual source code and workspace planning documents. The `workspaces/kailash-ml-crate/briefs/01-architecture-decisions.md` (8 locked decisions) was never read in the first pass.

## Prevention

For cross-SDK analysis, ALWAYS:

1. Read ALL workspace briefs and plans, not just crate source
2. Check `todos/active/` for roadmap scope
3. Read architecture decision records, not just current implementation

## For Discussion

1. Should the kailash-align-serving brief be updated to clarify it's LLM-only, or is that already clear from context?
2. Does the 179-todo kailash-rs ML roadmap change the kailash-py ML strategy? (No — both implement independently per EATP D6, but the Rust roadmap is more ambitious with native implementations vs Python's sklearn wrappers.)
3. At what point does the Rust kailash-ml become the "reference implementation" that Python kailash-ml should align TO, rather than vice versa?
