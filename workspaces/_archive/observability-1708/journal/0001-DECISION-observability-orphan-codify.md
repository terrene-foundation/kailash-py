---
type: DECISION
date: 2026-07-13
slug: observability-orphan-codify
workspace: observability-1708
---

# DECISION — Codify the #1708 observability learnings into the orphan-audit playbook

## Context

The #1708 enterprise observability program shipped 5 coordinated PyPI releases
(kailash 2.50.0 + nexus 2.12.0 + dataflow 2.16.0 + kaizen 2.30.0 + mcp 0.3.0).
Two failure classes surfaced during the redteam gates + the release-PR CI that
are worth institutional capture — both invisible to per-shard/per-package review,
caught only by a holistic cross-cutting sweep.

## Decision

Codify both into `.claude/skills/16-validation-patterns/orphan-audit-playbook.md`
(the `/redteam` orphan-detection procedure backing `rules/orphan-detection.md`),
NOT a new baseline rule — the skill is where redteam agents consult "how to detect
an orphan", it carries no Rule-10 proximity-band / Trust-Posture-Wiring ceremony,
and `orphan-detection.md` already wires it into `/redteam` + `/codify`.

Three additions:

1. **Detection Protocol step 6** — a metric-registry scrape-reachability sweep.
2. **§9 (new)** — "Metric Instruments Must Reach A Production Scrape/Export
   Surface (Metric-Registry Orphan)": mirroring a metrics-EMISSION pattern is not
   mirroring its scrape WIRING; verify each instrument reaches `generate_latest()`
   / the OTel export end-to-end. Evidence: DataFlow + Kaizen metrics recorded on a
   dedicated `CollectorRegistry` with a zero-caller `render_exposition()` and no
   wired route — invisible to the core server's global-registry scrape.
3. **§4 cross-tree sweep** — parallel per-package agents sweep their own
   `packages/<pkg>/tests/` but miss sibling core-tree `tests/**` that exercise the
   same surface. Evidence: W2's MCP p95/p99 removal left three core-tree assertions
   that reded core Tier-1 CI across all Python versions.

## Alternatives considered

- A new baseline MUST in `observability.md` — rejected: heavier (Rule-10 proximity
  band + 8-field Trust Posture Wiring) for equal enforcement value, since the skill
  already fires at `/redteam`.

## Receipts

- Release: PyPI 5-package bundle + GitHub Releases (v2.50.0 / nexus-v2.12.0 /
  dataflow-v2.16.0 / kaizen-v2.30.0 / mcp-v0.3.0), merge commit `36665977c` (PR #1714).
- Redteam evidence: metric-orphan finding in the final holistic redteam;
  test-sweep regressions caught by the release-PR CI (fixed in commit `2d2f57f3c`).
