# 0021 — DECISION: PR #1675 promotional-spam disposition (external, non-security)

**Date:** 2026-07-11 · **Type:** DECISION · **Phase:** 05-codify · **Posture:** L5_DELEGATED

## Decision

Disposed of PR #1675 ("feat: add JMT x402 Agent Tools"), an unsolicited promotional PR from an
external account. Owner **closed** it, **blocked** the account, and **filed a GitHub spam report**.
Assessed as **promotional spam, NOT a security compromise** — evidence below. Basis for decline:
**Absolute Directive #0 — Foundation Independence / No Commercial Coupling** (a paid commercial
crypto-payment service listing has no place in the Foundation SDK's public README).

## Evidence (verified this session, per evidence-first-claims MUST-2)

- **Scope:** full diff = `README.md (+2/-0)` only — a single promotional markdown line advertising
  "25 paid x402 endpoints … $0.001–$0.15/call USDC" linking to an external commercial worker service.
  **No** `.github/workflows/`, CI, code, or hook files touched (the `pull_request_target` secret-exfil
  vector was specifically checked — absent).
- **Access:** author `jmthomasofficial` permission = `read` (the public-repo default, NOT a grant);
  **0 write access, 0 commits on `main`**. No unauthorized access occurred.
- **Reachability:** merge state was `BLOCKED` by branch protection — never mergeable without maintainer
  review. The defense worked as designed.
- **Final state:** `gh pr view 1675` → `state=CLOSED, closedAt=2026-07-11T13:02:14Z`.

## Assessment — not a hack

An external PR against a public repo is the normal open-source contribution mechanism; _opening_ ≠
_merging_. The change was inert (markdown link, nothing executable), the repo's protections held, and
nothing requires remediation or rotation. This is the bulk "x402 agent tools" listing-spam pattern
pointed at a popular Foundation repo — annoying, harmless to the codebase.

## Precedent + escalation trigger (per knowledge-cascade-routing MUST-1)

Single instance → this repo-local receipt is the right weight. **If the pattern recurs** across
Foundation public repos, escalate to a cascade-valuable COC rule for external-promotional-PR
disposition (close + block + report; assess-as-non-security-with-evidence). Not codified as a rule now
(one instance does not warrant a baseline rule).

## Also this session

- Cleaned 6 superseded `journal/.pending/` auto-capture stubs — each a receipt of a commit already
  promoted to `0010`–`0019` (gitignored session-local staging; "promote OR delete" → deleted).
- Post-v2.48.0 codify wave remains 6× converged + landed (`0013`–`0020`); no re-pass this session
  (its own `0020` receipt directs stopping same-scope re-passes). Board is now clear of ours.
