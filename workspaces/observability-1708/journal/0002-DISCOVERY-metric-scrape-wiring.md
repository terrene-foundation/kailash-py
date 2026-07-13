---
type: DISCOVERY
date: 2026-07-13
slug: metric-scrape-wiring
workspace: observability-1708
---

# DISCOVERY — "Emission ≠ scrape wiring" is the orphan pattern at the metrics layer

## The pattern (inherit this)

When N parallel agents each add a metric across N packages by MIRRORING a
reference implementation, they reliably copy the EMISSION (the `Histogram` /
`Counter` object + the `.observe()`/`.inc()` call) but NOT the SCRAPE WIRING (the
registry the server actually reads + the route that exposes it). The result is a
metric that records on every call and is scraped never — the Phase-5.11
"beautifully-implemented orphan" at the metrics layer.

In #1708, two of four sub-package agents (DataFlow, Kaizen) mirrored the fabric
`CollectorRegistry` + `render_exposition()` pattern but omitted its
`get_metrics_route()` — so the metric lived on a dedicated registry the core
server's `generate_latest()` (which reads the GLOBAL `prometheus_client.REGISTRY`)
structurally could not see. `render_exposition()` had ZERO production callers.

## Why per-shard review missed it

Every per-shard test asserted the instrument RECORDED (build the metric, call it,
read it back off its own registry) — never that a SERVER SCRAPED it. The orphan is
invisible until you trace emission → registry → exposition → endpoint end-to-end.
Only the holistic post-multi-wave redteam (one reviewer scoped to "does each metric
reach a scrape surface?") caught it.

## The two structural defenses (now in the orphan-audit playbook §9 + step 6)

1. **Register on the surface the unified `/metrics` already folds** — for
   prometheus_client, the default `REGISTRY` that `generate_latest()` reads; the
   `connection_metrics.py::_get_acquire_wait_histogram` lazy-singleton-with-adopt-guard
   is the reference. A dedicated registry is legitimate ONLY when paired with a wired
   route + a Tier-2 endpoint-scrape test.
2. **Cross-tree test sweep** — a per-package API change must `grep` BOTH
   `packages/<pkg>/tests/` AND the core-tree `tests/**`; the package agent's venv is
   green while the core Tier-1 CI reds (the W2 MCP p95/p99 removal).

## Generalization

This is `facade-manager-detection.md` / orphan-detection §1 one layer down: the same
"built + exposed + imported, but the hot path never invokes it" shape, applied to a
metric instead of a manager. The redteam lens that catches it is "trace the wiring to
a real consumer end-to-end", not "confirm the object exists".
