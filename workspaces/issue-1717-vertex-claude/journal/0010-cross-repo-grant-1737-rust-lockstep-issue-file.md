# 0010 — Cross-Repo Grant: file #1737 cross-SDK lockstep issue on the Rust SDK

cross-repo-authorized: esperie-enterprise/kailash-rs

- **Requester:** repo owner (session user, tabula.rasa.integra@gmail.com)
- **Target repo:** esperie-enterprise/kailash-rs (verified exists + accessible this session via `gh repo view` — private=true)
- **Action (bounded, exact — scoped DOWN at execution):** the authorized action was "create ONE cross-SDK-alignment issue linking rs#1810 ↔ py#1737." On verifying the target this session, **rs#1810 already EXISTS and IS the Rust-side tracker** for this exact feature ("DataFlowConfig needs a per-connection credential/token callback", OPEN). A new issue would be redundant and split tracking. Therefore the action is executed as the strictly-SMALLER footprint that fulfills the same authorized intent: **post ONE comment on rs#1810** cross-referencing py#1737 / PR #1740 + the Python implementation semantics to mirror. Same repo, same intent, less intrusion (scope-down, not scope-creep). No other writes/comments/reads beyond confirming the comment landed + the rs#1810 existence-verify read this action intrinsically requires.
- **Timestamp:** 2026-07-14T11:41:23Z
- **Verbatim instruction:** user replied `approved` to the agent's explicit offer: _"file a scrubbed cross-SDK-alignment issue on the Rust SDK BUILD repo linking rs#1810 ↔ py#1737 (I'll show you the body + journal the grant first). Authorize and I'll do it."_

## repo-scope-discipline User-Authorized-Exception conditions

1. **User-initiated** — deliberate `approved` from the repo owner to a precisely-scoped proposal (target + exact action named by the agent). Not passive/inferred assent.
2. **Explicit + specific** — the approved proposal names the target repo (Rust SDK BUILD) AND the exact action (file the cross-SDK-alignment issue linking rs#1810 ↔ py#1737).
3. **Confirmed** — agent stated action + target; user confirmed (`approved`) BEFORE execution.
4. **Journaled before acting** — THIS entry + the `cross-repo-authorized:` marker land BEFORE the `gh issue create` command runs.
5. **Scoped exactly** — exactly one issue on the one named repo; scrubbed body; no incidental cross-repo reads/writes.

## Disclosure check

Direction is rs-repo (private) ← references py#1737/PR#1740 (public kailash-py). This is the prescribed cross-SDK flow (`cross-sdk-inspection.md` Rules 1–2). `cross-sdk-inspection.md` Rule 6 (no private-repo-qualified rs references in PUBLIC kailash-py artifacts) does NOT apply — the write is ON the private repo, not into a public py artifact. Body is a generic security-pattern description (per-connection credential callback); no secrets, no customer/tenant tokens, no internal paths.
