---
type: AUTHORIZATION
date: 2026-06-08
author: human
project: issue-1258-canonical-encoder-parity
topic: cross-repo authorization to file 1 cross-SDK alignment issue on esperie-enterprise/kailash-rs
phase: codify
tags:
  [
    cross-sdk,
    repo-scope-discipline,
    user-authorized-exception,
    mcp,
    canonical-json,
  ]
---

cross-repo-authorized: esperie-enterprise/kailash-rs

# AUTHORIZATION — User authorized cross-SDK MCP canonical-bytes filing on kailash-rs

Per `repo-scope-discipline.md` § User-Authorized Exception, all five conditions met:

1. **User-initiated** — genuine user turn; verbatim instruction: "i allow you to
   file cross-repo".
2. **Explicit + specific** — target repo `esperie-enterprise/kailash-rs` (user
   selected it via the confirmation question over the two candidates
   `esperie-enterprise/kailash-rs` upstream vs `rrps-mtu/kailash-rs` seed); exact
   action: file ONE cross-SDK alignment issue.
3. **Confirmed** — agent presented the full drafted issue body AND asked the user
   to pick the target; user confirmed **`esperie-enterprise/kailash-rs`** BEFORE
   any execution.
4. **Journaled before acting** — this entry + the marker line above land BEFORE
   the `gh issue create --repo esperie-enterprise/kailash-rs` command runs.
5. **Scoped exactly** — only the ONE named issue against only that repo; no
   incidental reads of kailash-rs source, no scope creep.

## Existence check (verify-resource-existence.md MUST-1/2)

- `terrene-foundation/kailash-rs` → live `gh repo view` returns "Could not
  resolve to a Repository" (does NOT exist under that name). The prior session's
  F26 "no GH kailash-rs" referred to this non-existent path.
- `esperie-enterprise/kailash-rs` → exists, PRIVATE, issues enabled (confirmed
  via live `gh repo view --json`).
- `rrps-mtu/kailash-rs` → exists, PRIVATE, issues enabled; described as a verbatim
  seed tracking the `esperie-enterprise/kailash-rs` upstream. User chose upstream.

## Bounded action

File 1 issue on `esperie-enterprise/kailash-rs`, framed as a cross-SDK ALIGNMENT
request (I have NOT read kailash-rs source — per repo-scope-discipline I do NOT
inspect the sibling; the issue asks the rs maintainers to vendor the canonical
fixture and add the parity test). Body scrubbed per `upstream-issue-hygiene.md`
MUST-2/3: SDK-API surface only, cross-ref to public kailash-py #1258 / PR #1281,
no workspace paths / finding tags (no "F29") / consumer context.

Issue: vendor `mcp-messages-canonical.json` + assert serde_json byte-parity for
the 4 MCP wire encoders (JsonRpcError / JsonRpcRequest / JsonRpcResponse /
McpToolInfo). Acceptance: vendor the byte-identical fixture; test iterates every
vector for canonical-bytes + SHA-256 equality; assert raw-UTF-8 (no `\uXXXX`) +
NFC≠NFD distinctness. Python equivalent: kailash-py #1258 / PR #1281.
