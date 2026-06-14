---
type: DISCOVERY
slug: canonical-json-encoder-ambiguity
created: 2026-06-14T03:30:00Z
---

# Two non-interchangeable canonical-JSON encoders — the cross-SDK byte-parity hazard

Independently surfaced by the cluster-C (`01-analysis/02-`) and cluster-E
(`01-analysis/03-`) deep-dives during `/analyze` for EATP-12 (#1312).

## Finding

kailash-py ships **two** RFC-8785/JCS-ish canonical-JSON encoders that are
**not interchangeable**:

- **delegate family** — `canonical_json_dumps` (`src/kailash/trust/_json.py:149`):
  `ensure_ascii=False`, raw UTF-8. Matches RFC 8785 / JCS and Rust `serde_json`.
- **signing family** — `serialize_for_signing` (`src/kailash/trust/signing/crypto.py:225`):
  `ensure_ascii=True`, `\uXXXX`-escaped. Deliberately distinct (issue #1258).

The EATP-12 N12-CB-01 commitment + N12-CB-04(d) KCV pre-images cite
`canonical_json_dumps` (RFC 8785 / JCS → raw UTF-8).

## Why it's a trap

Every §12 Appendix B golden fixture is **ASCII-only**, so BOTH encoders
reproduce the published hex byte-identically. Cluster E verified §12.2
(`f325754c…d9405c`) and §12.3 KCV (`00051364b85b0a43`) regenerate via
`serialize_for_signing` — but that PASS is vacuous for the byte-parity
question, because a non-ASCII `vault_id` is where the two encoders diverge,
and the golden fixture never exercises it.

## Disposition (feeds shard C1)

1. Commitment + KCV MUST use the **delegate-family `ensure_ascii=False`**
   encoder, per the spec's explicit `canonical_json_dumps` / RFC-8785
   citation and for cross-SDK parity with Rust `serde_json`.
2. Add a **non-ASCII sentinel vector** (a `vault_id` carrying a non-ASCII
   codepoint) to the Tier-1 byte-pin set — the only way to lock the encoder
   choice, since §12 cannot.
3. The non-ASCII pre-image MUST be reconciled with kailash-rs before either
   SDK releases vault binding (cross-SDK coordination gate; separate grant).

Recorded as brief-correction #1 in `02-plans/01-architecture-and-waves.md`.
