---
type: DISCOVERY
date: 2026-07-02
display_id: esperie
---

# DISCOVERY — public artifacts silently accrue private-repo disclosure

## Pattern (inherit next session)

**Public-published artifacts leak the private sibling SDK over time.** The public, PyPI-published `CHANGELOG.md` had accumulated **27** references to the private `esperie-enterprise/kailash-rs` — org names, versions, issue numbers, crate paths, even internal architecture ("axum + tokio") — one cross-SDK parity note at a time across many releases. Each looked harmless; the aggregate is a standing disclosure + a Foundation-Independence (Directive 0) violation. README (the PyPI long_description) carried 3 more. Now codified as `cross-sdk-inspection.md` Rule 6.

**Cross-repo target resolution: trust reference-memory + `settings.local.json`, NOT rule-doc examples or issue bodies.** I recommended filing at `terrene-foundation/kailash-rs` (nonexistent) because both the rule's own examples AND issue #1483's body carried that wrong path — while my persisted `reference-kailash-rs-repo-location` memory already said the real repo is the private `esperie-enterprise/kailash-rs`. The synced doc was wrong; the memory was right; I trusted the doc. Memory updated with a CRITICAL "do not trust rule-doc/issue-body for this path" warning.

**specs drive both SDKs (EATP D6).** Neither SDK drives the other. A cross-SDK issue is a TRANSPARENCY signal to maintain spec parity, not a command. Filing on the sibling repo requires the repo-scope-discipline User-Authorized Exception: journaled `cross-repo-authorized:` receipt BEFORE any command touches the sibling — I ran pre-flight reads before the receipt this session and the hook correctly halted me; corrected by landing the receipt (0006) first.

## Process lessons

- `grep pattern file | head -1 && echo X` fires the echo unconditionally (`head` always exits 0) — a false-positive detector I used to (wrongly) conclude a file was allowlisted. Use `grep -q` and check its exit, not a piped `head && echo`.
- A private seed-org token (`rrps-mtu`) from memory leaked into the very rule meant to prevent leaks; redteam caught it. Private scan tokens belong in gitignored operator-local config, never a synced rule.
