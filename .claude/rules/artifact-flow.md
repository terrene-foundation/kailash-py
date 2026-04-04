---
paths:
  - ".claude/**"
  - "sync-manifest.yaml"
  - "**/VERSION"
  - "*.md"
---

# Artifact Flow Rules

## Authority Chain

- **atelier/** — CC + CO authority (methodology, base rules, guides)
- **loom/** — COC authority (SDK agents, specialists, variant system)

```
atelier/ → /sync-to-coc → loom/ → /sync → USE templates
BUILD repos → /codify → proposal → loom/ → /sync → USE templates

❌ loom/ edits CC/CO independently (drifts from atelier/)
❌ BUILD repos sync directly to templates (bypasses loom/)
```

## BUILD Repo Rules

- `/codify` writes to BUILD repo's `.claude/` for immediate local use + creates `.claude/.proposals/latest.yaml`
- BUILD repo does NOT sync to any other repo directly
- Downstream repos: `/codify` stays local only, no proposal manifest

## /sync Is the Only Outbound Path

Only `/sync` at loom/ may write to template repos. No other command or manual process.

## Human Classifies Every Change

Inbound changes from BUILD repos classified by human as:

- **Global** → `.claude/{type}/{file}` (all targets)
- **Variant** → `.claude/variants/{lang}/{type}/{file}` (one target)
- **Skip** → not upstreamed

Automated suggestions permitted; automated placement is not.

## Variant Overlay Semantics

- **Replacement**: variant exists + global exists → variant wins
- **Addition**: variant exists, no global → added
- **Global only**: no variant → global used as-is

## MUST NOT

- Sync directly between BUILD repos (kailash-py ↔ kailash-rs) — all paths through loom/
- Edit template repos directly — rebuilt entirely by `/sync`
- Auto-classify global vs variant without human approval
