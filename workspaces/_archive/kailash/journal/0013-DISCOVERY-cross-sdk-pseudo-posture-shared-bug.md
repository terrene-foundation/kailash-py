---
type: DISCOVERY
date: 2026-03-31
created_at: 2026-03-31T03:20:00Z
author: agent
session_id: session-7
session_turn: 80
project: kailash
topic: Cross-SDK analysis confirms pseudo posture bug shared between py and rs
phase: implement
tags: [cross-sdk, trust, posture, care, rs-118]
---

# Cross-SDK: "pseudo" Posture Bug Shared Between Python and Rust

## Finding

kailash-rs#117 (get_node nested departments) does NOT exist in kailash-py — Python's `compile_org()` correctly indexes all nodes.

kailash-rs#118 ("pseudo" posture rejected) DOES exist in kailash-py — `TrustPosture("pseudo")` raised ValueError because the enum value was `"pseudo_agent"`, not `"pseudo"`. All other CARE-spec L1-L5 names parsed correctly.

## Fix

Added `_missing_` classmethod to `TrustPosture` enum that maps `"pseudo"` -> `PSEUDO_AGENT`. Also handles case-insensitive input and hyphen/space normalization. Filed as kailash-py#191, fixed in PR #192.

## Broader Insight

The aegis dev team filed py#145-147 against kailash-py but all three were already fixed (BudgetTracker, ShadowEnforcer, intersect_envelopes). None of those matched rs#117/118. Cross-SDK issue triage requires checking both the issue description AND the current codebase state — filed issues may reference stale code.

## For Discussion

- Should cross-SDK issue filing include a "verified against version X.Y.Z" field to prevent stale filings?
- If rs#117 (get_node) is a Rust-only bug due to different compilation logic, does EATP D6 (matching semantics) require the Rust team to match Python's behavior?
- The `_missing_` pattern for enum aliases is clean but non-standard — should we document it as a trust-plane convention?
