# Cross-Repo Authorization Receipt — #1720 F3 HF chat-routing cross-SDK sibling

cross-repo-authorized: esperie-enterprise/kailash-rs

- **Requester:** user (jack@kailash.ai), in-session turn — verbatim instruction "approved"
  in direct response to the agent's specific ask: "F3's HF chat-routing is a cross-SDK parity
  surface; the Rust SDK has no `huggingface_chat` preset. I won't self-file a cross-repo issue.
  Authorize and I'll draft the scrubbed body (SDK-API-surface only) and file it against the
  Rust SDK BUILD repo."
- **Target repo:** esperie-enterprise/kailash-rs (Rust SDK BUILD repo; private). Slug confirmed
  by the prior #1720 Wave-1b / #1727 authorization receipts in this repo + reference memory
  (`reference_kailash_rs_repo_location.md`); no local resolver at this BUILD checkout to consult.
- **Action:** file ONE `cross-sdk` GitHub issue requesting the Rust four-axis kaizen LLM client
  gain HuggingFace chat-schema routing parity with kailash-py #1720 F3: a `huggingface_chat`
  preset routing to the OpenAI-compatible `/v1/chat/completions` endpoint + a `use_chat_schema`
  routing discriminator so tool + response_format emission is reachable for HuggingFace
  deployments (today only the classic text-generation `/models/{model}` schema is reachable,
  which cannot carry tools or response_format). No code write; one issue only.
- **Timestamp:** 2026-07-16 (session date).
- **Scope:** exactly one issue on esperie-enterprise/kailash-rs; body scoped to the SDK API
  surface only — no consumer/downstream context, internal kailash-py paths, workspace IDs, or
  finding tags (upstream-issue-hygiene.md MUST-2/3). Cross-ref to kailash-py #1720 by bare
  number only.

## Ordering note (honest record)

This receipt lands BEFORE any cross-repo command (repo-scope-discipline User-Authorized
Exception condition 4). READ-only due diligence (duplicate-issue search on kailash-rs) follows
as in-scope, then the scrubbed body is drafted and the issue filed.

## Executed

Filed 2026-07-16 (this session): **esperie-enterprise/kailash-rs#1869** with the `cross-sdk`
label. Body scoped to the SDK API surface only (no consumer/workspace/finding-tag context);
cross-ref to py #1720 by bare number. Duplicate-issue search run first (read-only) — no
existing HF chat-schema-routing issue; the nearby cross-sdk #1853 is a different topic
(openai_chat max_completion_tokens). Verified filed via the returned issue URL.
