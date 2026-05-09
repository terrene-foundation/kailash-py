---
name: coc-reference
description: "COC template — five-layer (agents, skills, rules, hooks, commands) structure."
tools:
  - Read
  - Glob
  - Grep
---

# COC Template Implementation Reference

How the COC five-layer architecture is implemented in the Kailash COC template repos. For COC spec/concepts (fault lines, value inversion, autonomous execution), see [co-reference/coc-spec.md](../co-reference/coc-spec.md).

## Implementation Inventory

| CO Layer        | COC Artifact Type  | Count                                | Purpose                         |
| --------------- | ------------------ | ------------------------------------ | ------------------------------- |
| L1 Intent       | Agents             | 30+                                  | Specialized domain experts      |
| L2 Context      | Skills + CLAUDE.md | 28+ dirs, 400+ files                 | Institutional knowledge library |
| L3 Guardrails   | Rules + Hooks      | 9 rules, 9 hooks                     | Deterministic enforcement       |
| L4 Instructions | Commands           | 20 commands                          | Phase-gated workflow            |
| L5 Learning     | Learning pipeline  | observations + digest + codification | Knowledge compounding           |

## Layer 3: Defense in Depth

Critical rules have 5-8 independent enforcement layers:

```
Rule file (soft — AI interprets)
  + Hook script (hard — deterministic, exit code 2 blocks)
    + Anti-amnesia hook (re-injects every message, survives compression)
      + Code review by reviewer
        + Security review by security-reviewer
          + CI pipeline check
```

The anti-amnesia hook (`user-prompt-rules-reminder.js`) is the single most important mechanism — fires on every user message.

## Layer 4: Seven-Phase Workflow

| Phase          | Command      | Quality Gate                 |
| -------------- | ------------ | ---------------------------- |
| Analysis       | `/analyze`   | reviewer                     |
| Planning       | `/todos`     | **Human approval**           |
| Implementation | `/implement` | reviewer + security-reviewer |
| Validation     | `/redteam`   | reviewer                     |
| Knowledge      | `/codify`    | gold-standards-validator     |
| Release        | `/release`   | **Human approval**           |

Evidence-based completion: AI cannot claim "done" without file-and-line proof.

## Layer 5: Observe-Capture-Evolve

```
Observations (JSONL)
  → Pattern analysis (confidence = frequency 40% + success 30% + recency 20% + consistency 10%)
    → Evolution suggestions (Skills ≥0.7, Commands ≥0.6, Agents ≥0.8)
      → Human approval required
```

## Template Repos

- **kailash-coc-claude-py** — Python SDK template (USE)
- **kailash-coc-claude-rs** — Rust SDK template (USE)
- **kailash-coc-claude-rb** — Ruby SDK template (USE)

All synced from loom/ (source of truth) via `/sync`.
