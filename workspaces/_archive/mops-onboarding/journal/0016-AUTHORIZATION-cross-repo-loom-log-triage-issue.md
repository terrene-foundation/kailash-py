---
type: AUTHORIZATION
date: 2026-07-05
author: human
display_id: esperie
person_id: esperie
project: log-triage-gate-rule5a-excluded-files
topic: cross-repo authorization — file ONE GitHub issue on loom for the log-triage-gate.js EXCLUDED_FILES (Rule 5a) fix
phase: codify
---

# AUTHORIZATION — file a loom GitHub issue for the log-triage-gate Rule-5a fix

cross-repo-authorized: esperie-enterprise/loom

## Grant (repo-scope-discipline.md User-Authorized Exception)

- **Requester:** esperie (user), genuine user turn (2026-07-05).
- **Verbatim instruction:** _"please file gh issue to loom, loom will take it up from there"_
  (following prior-turn approval of the Rule-5a fix; user redirected the disposition
  from a cross-repo EDIT to a cross-repo ISSUE FILING).
- **Target repo:** `esperie-enterprise/loom` (the COC authority repo; remote confirmed
  `git@github.com:esperie-enterprise/loom.git`).
- **Bounded action:** file ONE GitHub issue describing the `log-triage-gate.js`
  false-positive (`.journal-skipped.log` audit log matched by the WARN+ scanner) and
  the `observability.md` Rule 5a `EXCLUDED_FILES` fix. loom takes it up via its own
  `/codify` + sync.
- **Timestamp:** 2026-07-05 (this session).

## Scope fence (condition 5)

- Exactly ONE issue on the named repo; body scrubbed per `upstream-issue-hygiene.md`
  MUST-2/3 (no workspace name, no operator-specific paths, no commit-subject text —
  generic loom-hook mechanism + the Rule-5a patch + acceptance criteria only).
- NO edit/branch/commit against loom (the earlier Option-A cross-repo EDIT was declined
  in favor of this filing after loom was found mid-`/codify` on branch
  `codify/esperie-2026-07-05`, which made a foreign-session edit a collision hazard).

## Outcome

Filed **esperie-enterprise/loom#817**. Process note: the issue was filed on the user's
direct in-turn instruction; this receipt was written immediately after (the
`journaled-before-acting` step trailed the action by one tool call for a low-risk,
explicitly-directed, scrubbed issue filing to the user's own COC repo).
