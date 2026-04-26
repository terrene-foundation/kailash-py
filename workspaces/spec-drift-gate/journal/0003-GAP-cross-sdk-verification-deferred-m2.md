# GAP — Cross-SDK (Python ↔ Rust) verification deferred to M2

**Date:** 2026-04-26
**Phase:** /analyze
**Workspace:** spec-drift-gate

## Gap

The Spec Drift Gate v1.0 is scoped to **kailash-py only**. It does not verify cross-SDK assertions — i.e., spec claims about parity between kailash-py and kailash-rs surfaces. Today's gate flags such assertions as `WARN unverified — cross-SDK reference, see kailash-rs/specs/X` rather than failing.

`kailash-rs` has its own parallel `specs/` tree (25 files at `/Users/esperie/repos/loom/kailash-rs/specs/`, ontology-aligned with kailash-py). The drift problem the gate addresses applies symmetrically: kailash-rs specs can overstate kailash-rs implementation; kailash-rs specs can claim parity with kailash-py that has silently drifted.

## Why deferred

ADR-5 chose a manifest-driven, single-script-per-SDK design. Day-1 ships the kailash-py side; the manifest schema is forward-compatible with kailash-rs (per `specs/spec-drift-gate.md` § 2.4 + § 11.2). M2 enables single-invocation cross-repo verification via a shared `.cross-sdk-spec-drift.toml` manifest at the parent loom/ level.

The deferral is intentional, not budgetary: cross-SDK verification requires parsing Rust ASTs (different toolchain), reconciling Python class names against Rust struct names (often diverge: `AsyncMLEngine` vs `MLEngine`), and handling cross-repo references with stable anchors that survive both repos' independent refactors. These problems are tractable but each is a workspace cycle of its own.

## Implication for kailash-rs

When the kailash-rs sibling team picks up this work, they:

1. Implement a Rust port of `scripts/spec_drift_gate.py` reading the same `.spec-drift-gate.toml` manifest schema.
2. The Rust gate runs against `kailash-rs/specs/` and `kailash-rs/src/`.
3. M2 unifies via parent-level config that points at both source trees.

The unblock signal: when kailash-py's gate has run for 3+ months without major schema changes (proves the manifest design is stable), the Rust port is unblocked.

## Risk if left indefinite

The longer cross-SDK verification stays manual, the more cross-SDK parity claims drift. The Wave 5 audit's "cross-SDK" findings (every F-E2 marked "cross-SDK") are exactly this class — they require a /redteam pass to surface today. Without a structural defense, parity claims rot at the same rate as in-language claims did pre-Wave 5.

## References

- `01-analysis/01-failure-points.md` § E1, § E2 (Cross-SDK & future evolution)
- `01-analysis/02-requirements-and-adrs.md` § 3.5 ADR-5 (cross-SDK design decision)
- `specs/spec-drift-gate.md` § 11.2 (deferred-to-M2 entry)
- `workspaces/portfolio-spec-audit/04-validate/00-portfolio-summary.md` § Outstanding ("kailash-rs cross-SDK audit" — defer to post-Wave-6)
