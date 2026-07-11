---
priority: 0
scope: baseline
---

# Handoff Completion — A Downstream-Required Action Is Delivered Or Surfaced, Never Implied-Done

When a session's work is only complete once a DOWNSTREAM action happens — a cross-repo issue or PR that MUST be filed, an upstream handoff that MUST become a real artifact, an external notification that MUST be sent — the work is NOT done until that action is either EXECUTED (with the authorization it needs) or EXPLICITLY surfaced to the human as a PENDING action naming the exact target + action + authorization required. Writing a local note (a handoff doc, a `.session-notes` line, a "prepared" summary) and leaving the actual downstream action implied — or referencing a downstream artifact as if it exists when it was never created — is the **prepared ≠ delivered** failure: it silently transfers the completion burden to the human, who neither agreed to it nor can see the gap, and it rots into never-done.

## MUST Rules

### 1. A Downstream-Required Action Is Executed Or Explicitly Surfaced As Pending — Never Left Implied-Done

If completing a deliverable REQUIRES an action on another repo / an external surface (file an issue, open a cross-repo PR, send a handoff), the session MUST either (a) EXECUTE it this session (a cross-repo write requires ALL FIVE `repo-scope-discipline.md` User-Authorized-Exception conditions — user-initiated, explicit+specific, confirmed, journaled-before-acting, scoped-exactly — never self-authorization), or (b) surface it AT THE MOMENT THE DELIVERABLE IS CLAIMED DONE (and again at wrap-up) as an EXPLICIT pending action: the exact target, the exact action, and the specific authorization or input it is waiting on. Leaving it as a local artifact ("handoff prepared", "notes for the Rust SDK") with no executed action and no explicit pending-surface is BLOCKED. "The next session / the human will pick it up from the notes" is not a handoff — it is an abandonment.

```markdown
# DO — either execute, or surface the exact pending action

Executed: filed the BH5 mirror issue on the Rust SDK BUILD repo (#1732).
— OR —
PENDING (needs your authorization): file a BH5 mirror issue on the Rust SDK
BUILD repo. I cannot self-authorize a cross-repo write; authorize and I file
it now (scrubbed body shown first).

# DO NOT — leave a local note and treat the loop as closed

"Handoff prepared at workspaces/.../rs-1732-circuit-breaker.md; the Rust SDK
mirror remains the cross-SDK lockstep." # no issue filed, nothing asked — # the human is silently on the hook
```

**BLOCKED rationalizations:**

- "The handoff doc captures it; someone will file it"
- "I referenced the tracker; the rs side will see it"
- "The notes say it's pending; that's surfacing it"
- "It needs authorization, so leaving a note is the safe default"
- "The next session will pick it up from the session notes"
- "I added it to the workspace todos / backlog; the next /implement will action it"
- "It's tracked in a local issue draft, that's good enough"

**Why:** A local note is invisible on the surface that actually needs the action (the other repo); nobody downstream is watching the note, so "prepared" becomes "never done" and the human discovers the gap only by asking. Executing it, or naming it as an explicit pending action with its authorization requirement, is the only disposition that closes the loop.

### 2. A Downstream Artifact Is Referenced As Existing ONLY After It Is Created Or Verified This Session

A cross-repo issue/PR number, an external tracker, or a "mirror" artifact MUST NOT be referenced as if it EXISTS (in a comment, CHANGELOG, close message, handoff, or session notes) unless it was CREATED this session OR its existence was VERIFIED this session (e.g. `gh issue view <n> --repo <r>`). Carrying a downstream reference forward from prior-session prose, memory, or another issue's comment and stating it as current fact is BLOCKED — the cross-repo sibling of `verify-claims-before-write.md`.

```markdown
# DO — verify before referencing, or mark it unverified

Verified rs#1732 open (filed this session). / "rs#1714" — unverified; check before citing.

# DO NOT — reference an unverified cross-repo artifact as current fact

"the remaining lockstep is tracked in rs#1714" # never verified; rs#1714 was # actually a DIFFERENT primitive
```

**BLOCKED rationalizations:**

- "The tracker number is in my notes, it's fine to cite it"
- "The prior session established rs#NNNN as the tracker"
- "It's the same primitive, the number is close enough"
- "I referenced it last time, it must still be open"
- "`gh issue view` is an extra step; the reference is obviously right"

**Why:** An unverified downstream reference stated as fact misdirects every reader who trusts it, and hides that the artifact was never created — the exact shape that let a "prepared" handoff look done. One `gh issue view` before citing is the whole cost.

### 3. When The Action Needs Authorization, ASK Specifically — Never Leave The Gap For The Human To Infer

When the downstream action requires human authorization (`repo-scope-discipline.md` cross-repo write, `upstream-issue-hygiene.md` MUST-1 upstream filing), the session MUST make a SPECIFIC ask — restating the exact target repo + exact action — so the human answers yes/no on a concrete request. Leaving a local note and expecting the human to notice the gap, infer the action, and drive it is BLOCKED. The requirement to get authorization is NOT a licence to stop at a note; it is a requirement to ASK.

```markdown
# DO — specific, concrete authorization request

"To close the cross-SDK loop I need to file an issue on <target repo>. Authorize
and I'll draft the scrubbed body, journal the grant, and file it. (y/N)"

# DO NOT — treat "needs authorization" as permission to stop at a note

"Filing the mirror needs a cross-repo grant, so I've left the handoff in the
workspace." # never asked; the human must now discover and drive it
```

**BLOCKED rationalizations:**

- "It needs authorization, so leaving a note is the safe default"
- "I can't self-authorize a cross-repo write, so I've done all I can"
- "The user has a standing 'I authorize you', a specific ask is redundant"
- "Asking again is nagging; the note documents what's needed"
- "Surfacing the requirement in notes IS the ask"

**Why:** "It needed authorization" is the most plausible-sounding rationalization for the prepared ≠ delivered failure — it sounds disciplined while doing nothing. The discipline is to gate the ACTION behind a specific ask, not to substitute a local note for the ask. A blanket standing grant ("i already authorize you") still does not satisfy `repo-scope-discipline.md`'s per-action confirm-and-journal, so the specific ask is still required.

## MUST NOT

- Report a deliverable "done" / "handed off" / "prepared" when a required downstream action was neither executed nor explicitly surfaced as pending-with-authorization

**Why:** This is the originating failure mode — "prepared" reads as "delivered" and the uncompleted cross-repo action silently becomes the human's undocumented burden.

- Reference a cross-repo issue / PR / tracker as existing without creating or verifying it this session

**Why:** An unverified downstream reference is an unfalsifiable claim that hides a never-created artifact.

## Trust Posture Wiring

- **Severity:** `halt-and-report` at gate-review (reviewer at `/redteam` + cc-architect at `/codify` + the `/wrapup` review confirm any "handoff"/"prepared"/"mirror" language in session notes / PR bodies / issue comments is backed by either an executed downstream action OR an explicit pending-action-with-authorization surface); `advisory` at the hook layer (a lexical "handoff prepared"-without-executed-action scan is judgment-bearing per `hook-output-discipline.md` MUST-2 and cannot carry `block`).
- **Grace period:** 7 days from rule landing (2026-07-11 → 2026-07-18).
- **Cumulative posture impact:** same-class violations (a downstream-required action left implied-done in a local note; a cross-repo artifact referenced as existing without creation/verification) contribute to `trust-posture.md` MUST-4 cumulative-window math (3× same-rule in 30d → drop 1 posture; 5× total in 30d → drop 1 posture).
- **Regression-within-grace:** any same-class violation within the 7-day grace window routes through the GENERIC `regression_within_grace` emergency trigger per `trust-posture.md` MUST-4 (1× = drop 1 posture) — no dedicated per-clause trigger key (a handoff-completion property is review-layer-only judgment; the universal `regression_within_grace` trigger already covers it).
- **Receipt requirement:** SessionStart soft-gate `[ack: handoff-completion]` IFF `posture.json::pending_verification` includes this rule_id.
- **Detection mechanism:** Phase 1 (manual, gate-review) — reviewer at `/redteam` + cc-architect at `/codify` + the `/wrapup` self-check inspect session notes / PR descriptions / issue comments for "handoff" / "prepared" / "mirror" / cross-repo-tracker references, and confirm each is backed by an executed action (a filed issue/PR URL, a verified issue number) OR an explicit pending-action surface naming target + action + authorization. Phase 2 (deferred per `trust-posture.md` § Two-Phase Rollout) — an advisory `Stop`/`PostToolUse` detector for "handoff prepared" / "mirror tracked in <ref>" without an adjacent executed-or-pending-surface, paired with the review layer per `probe-driven-verification.md` MUST-4; audit fixtures at `.claude/audit-fixtures/handoff-completion/` per `cc-artifacts.md` Rule 9.
- **Violation scope:** MUST-1 (implied-done downstream action) + MUST-2 (unverified downstream-artifact reference) + MUST-3 (needs-authorization treated as licence to stop at a note).
- **Origin:** See § Origin.

## Origin

2026-07-11 — co-owner-directed origination. The BH5 session prepared a local Rust-SDK handoff doc, referenced `rs#1714` as the BH5 lockstep tracker (it was actually the BH3 tracker), and reported the cross-SDK mirror as "handoff prepared" without filing any issue on the Rust SDK repo — leaving the completion for the human to infer and drive. Verbatim directive: _"i already authorize you, if you don't specifically ask for it and just leave your notes locally and expect it to be magically done at kailash-rs or expect me to fill in the gaps for you, that's very irresponsible! please codify this unacceptable behavior and NEVER LET IT HAPPEN AGAIN!"_ Correction executed the same session: filed rs#1732 (the BH5 circuit-breaker cross-SDK parity issue), corrected the `rs#1714` misreference on py #1510, and codified this rule. Grant: `journal/0010`; receipt: `journal/0011`. Sibling of `build-repo-release-discipline.md` ("done means released, not merged") one layer out to cross-repo handoffs; MUST-2 (unverified cross-repo reference) pairs with `verify-claims-before-write.md` MUST-2 and `verify-resource-existence.md` MUST-2 (a cross-repo issue number is a resource-existence claim). Two loom-canonical follow-ups — whether MUST-2 relocates to the path-scoped `verify-claims-before-write.md`, and whether this rule joins the `self-referential-codify.md` Rule 2 allowlist (MUST-2 fires on codify-class output) — are flagged for loom Gate-1 in the codify redteam amendment (`journal/0012`).
