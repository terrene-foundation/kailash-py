---
type: DISCOVERY
date: 2026-06-22
author: agent
project: cross-sdk-audit
topic: Three cross-SDK serialization disciplines distilled from the 2.43.x canonical-encoder + NaN/Inf work — the next session inherits them as rules, not session-notes memory
phase: codify
tags:
  [
    cross-sdk,
    serialization,
    nan-inf,
    canonical-encoder,
    byte-determinism,
    integrity-manifest,
  ]
relates_to: 0019-DECISION-codify-since-last-codification-2026-06-22
---

# DISCOVERY — Cross-SDK serialization has three distinct, separately-codifiable disciplines

The 2.43.x trust-plane work surfaced that "make the signing bytes cross-SDK-safe" is NOT one
concern but THREE orthogonal ones, each with its own failure mode and its own structural defense.
Prior sessions held these only in `.session-notes` "Traps"; they are now rules the next session
loads automatically.

## 1. The serialization axis of NaN/Inf is distinct from the value-comparison axis

The codebase already guarded NaN on the VALUE axis (`math.isfinite()` on cost/constraint fields,
so `NaN < limit` can't silently pass a budget check). The 2.43.1 sweep found a SECOND axis: a
`json.dumps` over a SIGNED pre-image without `allow_nan=False` emits `NaN`/`Infinity` literals
that Python signs but Rust `serde_json` rejects on parse — breaking cross-SDK re-verification
even though no comparison is ever fooled. The two axes need two separate guards; closing one
leaves the other open. (→ `trust-plane-security.md` clause 8.)

## 2. "Should we switch this encoder?" is decided by EMPIRICAL byte-diff, not reasoning

The audit byte-diffed all 97 `default=str` sites against the conformant `canonical_scalars` rather
than reasoning about them — and the empirical result split them three ways: byte-NEUTRAL (the
`to_dict()` layer already normalizes → safe to switch single-SDK, e.g. `envelope_hash`),
byte-CHANGING + cross-SDK-contracted (witness family, envelope HMAC, audit chain → lockstep only,
pin current bytes as a tripwire), and no-cross-SDK-contract (local dedup/memo hashes → leave).
The decisive lesson: a canonical signing encoder is a byte-for-byte cross-SDK contract, and "I
reasoned the types are equivalent" is exactly how each of those sites was almost switched py-only.
(→ `cross-sdk-inspection.md` Rule 4b.)

## 3. An integrity manifest is a second artifact that drifts independently of the vector

PR #1411 shipped the CORRECT canonical vector fix but omitted re-pinning `PACT_VECTORS.sha256` →
red CI that a "converged (2 clean passes)" redteam missed because no round ran `shasum -c`. The
manifest and the vector are two files under one contract; changing one without the other either
reds CI (best case) or silently no-ops the integrity check. The durable defense is two-fold: re-pin
in the SAME commit, AND a redteam integrity-manifest-sweep lens that enumerates every `*.sha256`.
(→ `cross-sdk-inspection.md` Rule 4c.)

## Cross-cutting meta-lesson (already codified 2026-06-19, reinforced here)

All three surfaced during redteam rounds where a prior round had declared "converged." The
recurring remedy — every reviewer/lens must return a `ran`/evidence signal, errored/empty ≠ clean,
and a convergence claim must cite a durable receipt + cross-check remote CI — is the
2026-06-19 `agents.md` redteam-dispatch clause + `verify-resource-existence.md` MUST-4. The three
new serialization rules are the WHAT; that clause is the HOW the WHAT keeps getting found.
