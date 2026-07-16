# Cross-Repo Authorization Receipt — #1720 Wave-1b redteam cross-SDK siblings

cross-repo-authorized: esperie-enterprise/kailash-rs

- **Requester:** user (jack@kailash.ai), in-session turn — verbatim instruction "approved"
  in direct response to the agent's specific ask: "Authorize the cross-SDK filings on
  kailash-rs (the critical embed bug + the per-request-key guard) — say the word and I'll
  draft scrubbed bodies, journal the grant, and file."
- **Target repo:** esperie-enterprise/kailash-rs (Rust SDK BUILD repo; private). Slug
  confirmed by `gh repo view` this session (isPrivate=true) + the prior #1720 / #1727
  authorization receipts in this repo + reference memory
  (`reference_kailash_rs_repo_location.md`); no local resolver at loom root to consult.
- **Action:** file TWO `cross-sdk` GitHub issues, each requesting the Rust four-axis kaizen
  LLM client inspect for the same defect class surfaced by the kailash-py Wave-1b holistic
  `/redteam`:
  1. **embed URL model-substitution** — the four-axis `embed()` path for a `/models/{model}`
     wire (HuggingFace-style feature-extraction) must thread the resolved model into the
     URL builder; otherwise the `{model}` placeholder never resolves and every embed call
     fails.
  2. **per-request api_key override header-injection guard** — the BYOK per-request api_key
     override must be fail-closed-validated (reject control chars incl CR/LF/NUL/DEL +
     non-ASCII) BEFORE installation into an HTTP header value.
     No code write; two issues only.
- **Timestamp:** 2026-07-16 (session date).
- **Scope:** exactly two issues on esperie-enterprise/kailash-rs; each body scoped to the
  SDK API surface only — no consumer/downstream context, internal kailash-py paths, workspace
  IDs, or finding tags (upstream-issue-hygiene.md MUST-2/3). Cross-ref to kailash-py #1720 by
  bare number only.

## Ordering note (honest record)

This receipt lands BEFORE any cross-repo command (repo-scope-discipline User-Authorized
Exception condition 4). READ-only due diligence (duplicate-issue search on kailash-rs)
follows as in-scope, then the two scrubbed bodies are drafted and the two issues filed.

## Executed

Filed 2026-07-16 (this session), both with the `cross-sdk` label, bodies scoped to the SDK
API surface only (no consumer/workspace/finding-tag context), cross-ref to py #1720 by bare
number:

- **esperie-enterprise/kailash-rs#1860** — four-axis `embed()` must thread the resolved model
  into the `/models/{model}` URL (HIGH).
- **esperie-enterprise/kailash-rs#1861** — per-request `api_key` override must reject
  control/non-ASCII chars before header install (MEDIUM).

Loop closed — both downstream actions EXECUTED, not left as local notes (handoff-completion.md
MUST-1). Duplicate-check (READ) ran first: no pre-existing rs issue for either class.
