---
type: DECISION
date: 2026-07-15
author: human
display_id: esperie
person_id: esperie
project: sdk-backlog
topic: cross-repo authorization — file ONE cross-SDK parity issue on kailash-rs mirroring kailash-py #1712 (MCP fail-closed spawn allowlist + protocolVersion negotiation)
phase: codify
---

# AUTHORIZATION — cross-SDK filing on kailash-rs for the #1712 MCP spawn-safety class

cross-repo-authorized: esperie-enterprise/kailash-rs

## Grant (repo-scope-discipline.md User-Authorized Exception — all 5 conditions)

- **Requester:** esperie (user), genuine user turn (2026-07-15).
- **Verbatim instruction:** _"approved cross repo filing"_ — approving the agent-proposed
  #1712 cross-SDK MCP mirror (fail-closed local-server spawn allowlist + protocolVersion
  negotiation) surfaced in the prior turn's final report.
- **Target repo:** `esperie-enterprise/kailash-rs` (private; the Rust SDK — per the
  `reference_kailash_rs_repo_location` memory, NOT `terrene-foundation/kailash-rs`;
  resolver key `build.rs`).
- **Bounded action (FILE-only):** open ONE cross-SDK GitHub issue on
  `esperie-enterprise/kailash-rs` asking the Rust-SDK MCP surface to verify/apply the
  equivalent of kailash-py #1712 — a fail-closed local-server spawn allowlist (reject
  unlisted commands by default at EVERY spawn surface) + genuine protocolVersion
  negotiation (echo a supported requested version, else newest; not a hardcoded string),
  per the MCP 2025-11-25 local-server spawn-safety + lifecycle requirements. Per
  `cross-sdk-inspection.md` Rule 1-2: `cross-sdk` label + cross-reference to
  kailash-py #1712. Satisfies `upstream-issue-hygiene.md` MUST-1's same-session human gate.
- **Timestamp:** 2026-07-15 (this session).

## Scope fence (condition 5 — exactly the named action, nothing more)

- NO READ inspection of kailash-rs source was authorized this turn → the issue is a
  cross-SDK PARITY REQUEST (the rs maintainer inspects their own repo); the agent files it
  WITHOUT reading rs source. Only filing-preconditions run against the target: a
  `gh repo view` existence check (verify-resource-existence.md MUST-1) + a `gh issue list`
  dedup search.
- FILE is exactly ONE cross-SDK issue on the named repo; body scrubbed per
  `upstream-issue-hygiene.md` MUST-2/3 (no workspace/session/finding-tag/internal-path
  context; five-section minimal shape; references only the public kailash-py #1712).
- NO writes/branches/edits to kailash-rs source; NO further cross-repo action.

## Executed (2026-07-15)

- Existence check: `gh repo view esperie-enterprise/kailash-rs` → exists (private). ✓
- Dedup: no existing spawn-allowlist / protocolVersion issue (the two `cross-sdk`
  MCP issues found — #1247 byte-parity, #1566 tenant-isolation — are unrelated). ✓
- **Filed: esperie-enterprise/kailash-rs#1833** — "cross-sdk: fail-closed MCP
  local-server spawn allowlist + protocolVersion negotiation (parity with
  kailash-py #1712)", `cross-sdk` label, body scrubbed + cross-referencing the
  public kailash-py #1712. Grant loop closed; no further cross-repo action.
