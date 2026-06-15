# 0001 — DISCOVERY: brief corrections from parallel verification

**Phase**: /analyze · **Date**: 2026-06-15 · **Issue**: #1316

Four parallel deep-dive agents (`rules/agents.md` § Parallel Brief-Claim Verification, ≥3
clusters) re-derived every brief claim from source. Four material corrections — recorded
here and in `02-plans/01-architecture.md` § "Brief corrections" as the gate before /todos.

1. **Cross-SDK direction inverted (favorable).** kailash-py is the CANONICAL AUTHOR of
   `tests/test-vectors/eatp08-alg-id-canonical.json:7`; kailash-rs vendors it. V6/V7 byte-pins
   derived here — no cross-repo dependency blocks any shard. (Brief framed parity as a
   blocker.)
2. **Compatible-Legacy logging is NOT greenfield.** Two `logger.info` acceptance lines
   already ship (`algorithm_id.py:488-498`, `:611-621`). §7.1 reduces to INFO→WARN +
   consolidation. (Brief claimed none exists — FALSE.)
3. **`monotonic-upgrade-violation` is unimplemented** — only a forward-reference docstring
   (`algorithm_id.py:197-198`). V6 sub-case (i) is a new record-consumer enforcer (cross-file),
   not a vector. Promoted to its own shard (Shard 3) carrying the one open spec question.
4. **D2c trusted-verifier-key config must be built** (no existing config; pattern
   `MultiSigPolicy.signer_public_keys`, `multi_sig.py:170`). Crypto primitives ready
   (`crypto.py:170`/`:225`). D2c caller blast radius is mechanical (0 production
   `D2dWitness` constructions; 5 consumers forward `witness=` unchanged). Invariant count
   confirmed ~5.

**Net effect on plan**: still ~2 sessions, 4 shards. Shard 3 (monotonic enforcer) is the
only shard needing spec §4.5/§4.6 before sizing; Shards 1/2/4 are fully scoped and
spec-quoted via the issue body. Detail: `01-analysis/01-verification-findings.md`.
