---
type: DISCOVERY
date: 2026-05-18
created_at: 2026-05-18T00:00:00Z
author: agent
session_id: codify-1086
session_turn: 1
project: _hygiene-2026-05-18
topic: SessionEnd auto-capture routes by CWD, not by the commit's issue — a structural noise generator
phase: codify
tags: [sessionend-hook, journal-hygiene, institutional-knowledge, root-cause]
---

# DISCOVERY — the SessionEnd-hook CWD-routing failure is structural, not incidental

## What the triage surfaced

`workspaces/_hygiene-2026-05-18/02-issue-835-journal-triage.md` triaged 33
`.pending/` journal entries that had accumulated under
`workspaces/issue-835-dataflow-transaction-eventloop/`. 28 of 33 were
discarded as auto-captures of commits unrelated to issue #835 — durable
execution, scheduler retry, distributed worker, MFA hotfix, ML/MCP releases.

The root cause is NOT "agents were sloppy." It is structural: the SessionEnd
hook auto-captures each commit's body into **whatever workspace was the
session CWD**, regardless of the commit's own `Closes #N` / `Refs #N`
trailer. A session whose CWD happened to be the issue-835 workspace, doing
work that closed #911/#912/#917, wrote all of that work's `.pending/` entries
into issue-835.

## Why this is the institutional lesson for the next session

Two distinct failure modes compound here, and they map to two distinct fixes:

1. **Misrouting** (issue #1086 candidate 4): value belongs to the issue a
   commit closes; CWD-routing files it under an unrelated issue. Fix: route
   by the commit's `Closes/Refs #N` trailer; commits with no trailer go to a
   shared `_unrouted/` staging area.
2. **Re-firing / duplication** (issue #1086 candidate 3): the hook re-fires on
   every session re-entry whose HEAD matches a commit, producing near-
   identical `.pending/` files differing only in `session_id`. Fix:
   dedup-by-source_commit.

Both are hook-code changes. Candidate 4's rule clause (now in `journal.md`)
is the _contract_; candidates 3+4 the hook _implements_.

## The compounding cost

Triage cost is linear in noise volume and concentrates entirely in whichever
workspace was unlucky enough to be the CWD. issue-835 paid the triage cost
for six other issues' commits. Without the routing fix, every long-lived
workspace becomes a noise sink for its neighbours — and the institutional
value those commits earned is filed where nobody will look for it.

## Paired hygiene fact

`.pending/` is session-local staging, not curated journal. It MUST be
gitignored at the repo root (`**/journal/.pending/`) — issue #1086
candidate 2, now a `journal.md` MUST clause. The pattern fix already landed
in kailash-py's `.gitignore:205`; the rule makes it durable for every
consumer repo that runs the SessionEnd hook.

## For Discussion

1. Counterfactual: if the SessionEnd hook had always routed by issue trailer,
   would the issue-835 `.pending/` directory have held 5 entries instead of
   33 — i.e. is misrouting the _whole_ noise source, or does re-firing
   (candidate 3) generate noise even under correct routing?
2. The `_unrouted/` staging area is the catch-all for trailer-less commits.
   What triages `_unrouted/`, and on what cadence — does it need an owner, or
   does it become the new issue-835?
3. The triage report itself carried an internal inconsistency ("6 files
   across 3 issues" then listed 4). If the source evidence for a codify is
   imprecise, what is the gate that catches it before the imprecision
   propagates into a rule clause — here, the reviewer agent caught it; is
   that reliable enough, or should brief-claim verification be mandatory for
   every codify, not just `/analyze`?
