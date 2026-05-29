---
topic: canonical-build-targets
promoted_by:
  display_id: example-operator
  verified_id: pending # populated by coc-append.js on signed promotion
signed: false # set to true by coc-append.js when the attribution signature lands
proposal_ref: workspaces/multi-operator-coc/02-plans/01-architecture.md#section-7-3
promoted_at: 2026-05-22
superseded_by: null
body_anchor: pending # SHA-256 of the body (between `---\n` blocks) — set by coc-append.js
---

# Canonical build targets

We build for three SDK targets — Python, Rust, and Prism. Every shared
artifact ships through the loom-emit variant overlay system to all three.

| Target | BUILD repo logical key | USE-template logical key |
| ------ | ---------------------- | ------------------------ |
| Python | `build.py`             | `use-template.claude-py` |
| Rust   | `build.rs`             | `use-template.claude-rs` |
| Prism  | `build.prism`          | (no USE template yet)    |

Cross-repo path resolution MUST go through
`bin/lib/loom-links.mjs::resolveRepo(<logical-key>)` per
`rules/cross-repo.md` MUST-1. The logical keys above are the contract; the
on-disk paths are operator-local.

This file is illustrative — it is the example team-memory fact shipped
with the directory layout. Real promotions land via /codify per the
README in this directory.

## Origin

2026-05-22 — F14 M7 Shard E example fact, illustrating the split-rule
layout and signed-attribution frontmatter.
