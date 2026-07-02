---
type: DECISION
date: 2026-07-02
display_id: esperie
---

# DECISION — genericize private-Rust-SDK references across synced COC corpus

## What & why

kailash-py is a PUBLIC repo, and its `.claude/` artifacts sync to (public) USE templates. The prior repo-path correction (PR #1487) had put the private org name `esperie-enterprise/kailash-rs` into synced governance artifacts — a live public leak I introduced. Genericized EVERY private-Rust-SDK-repo reference across 47 files under `.claude/{rules,skills,guides}`:

- Org/repo-target refs → loom-links logical key `build.rs` / `<rust-sdk-repo>` placeholder + "resolve via `loom-links.local.json`" note (`cross-repo.md` MUST-1 pattern).
- Bare `kailash-rs` in prose/Origin → "the Rust SDK" (issue/PR numbers + technical content preserved).
- Also fixed 2 non-kailash-rs org leaks the sweep found: `esperie-enterprise/loom#21` → logical `loom` ref; `orgs/esperie-enterprise` hosted-runner → `<private-org>` placeholder.

## Verification

- 0 `kailash-rs`, 0 `esperie-enterprise/(kailash-rs|loom)`, 0 `orgs/esperie-enterprise` in scope dirs.
- `terrene-foundation/kailash-py` (public, correct) + `terrene-foundation/mint` preserved verbatim.
- Residual bare `esperie` = only operator-identity example tokens + the docker-scrub org-slug ALLOWLIST entry (load-bearing); none leak org/repo. (`esperie` is already the maintainer's PUBLIC self-coordinate.)

## Redteam (MANDATORY self-referential — allowlisted rules touched)

reviewer + security-reviewer + cc-architect (parallel). security = SECURE (leak closed, none introduced). reviewer + cc-architect = MERGE-WITH-FIXES: one collateral edit-tool corruption (4 approximation `~` doubled to `~~` in value-prioritization.md → GFM strikethrough) — FIXED by switching those figures to `≈` (formatter re-doubled `~` on save; `≈` is formatter-safe). `build.rs` logical key confirmed grounded (`artifact-flow.md:43` binds `build.{py,rs,prism}`).

## Scoped-out (accepted deferrals, in proposal for loom)

- Rust crate/binding INTERNAL paths (`crates/kailash-*`, `bindings/kailash-ruby`) left intact — internal governance, lower severity; reviewer confirmed not-a-blocker (Rule 6's own "separate larger audit" note).
- Operator-identity example tokens (`pid-esperie-*`, `journal/NNNN-esperie-*`) — DISTINCT lower-severity class; security-reviewer rated LOW (maintainer's public self-coordinate, no private info). Follow-up, not this task.
- LOOM: add `build.rs` to loom-links schema/example so templatized refs resolve.

## Proposal / anchor

`latest.yaml` amended (GLOBAL; "Gate-1 MUST templatize via `build.rs`, do NOT hardcode the corrected repo"). Anchor advanced to 2026-07-02.
