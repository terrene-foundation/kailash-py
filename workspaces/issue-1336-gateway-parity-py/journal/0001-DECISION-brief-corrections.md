# 0001 — DECISION: #1336 brief corrections from parallel verification

**Date:** 2026-06-16
**Gate:** `agents.md` MUST — parallel brief-claim verification on a ≥3-issue brief
(5 clusters) BEFORE `/todos`. Five background general-purpose agents, one per
cluster, each independently re-grepped/imported kailash 2.35.0 source.

## Corrections recorded (verdicts)

- Cluster 1 (rate-limit): **ALREADY-PRESENT** — complete in `nexus.auth` +
  `kailash.trust.rate_limit`. Issue claim "confirmed gap" is FALSE. Residue:
  preset auto-wiring stub `nexus/presets.py:181`.
- Cluster 2 (exception→HTTP envelope): **GAP-REAL** — no registration hook,
  no canonical envelope.
- Cluster 3 (per-request metrics): **GAP-REAL (narrow)** — recording middleware
  absent; registry + Prometheus exporter already support it.
- Cluster 4 (CSP/security headers): **ALREADY-PRESENT** in
  `nexus/middleware/security_headers.py`. Issue misattributed surface to
  `kailash.gateway/security.py` (secrets). Residue: preset CSP passthrough.
- Cluster 5 (session store): **PARTIAL** — mutation present; sliding-TTL unwired
  for `expires_at` mode; remaining-TTL accessor absent.

## Net scope

3 real-but-narrow gaps (clusters 2, 3, 5) + 2 preset-wiring stubs (clusters 1, 4).
All HTTP-middleware work is **Nexus-domain** → nexus-specialist. Session-TTL is
core `kailash.channels`.

Full evidence: `01-analysis/00-brief-claim-verification.md`.
