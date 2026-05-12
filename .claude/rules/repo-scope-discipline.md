---
priority: 0
scope: baseline
---

# Repo Scope Discipline — Stay In This Repo

See `.claude/guides/rule-extracts/repo-scope-discipline.md` for full BLOCKED-rationalization enumerations, extended DO/DO NOT examples, the orchestration-root exception detail, and origin post-mortem.

The repo whose root is the session's CWD defines the agent's entire scope of action. An agent operating in this repo MUST NOT touch, edit, push to, file issues against, comment on, read source from, or even propose work in any other repository — sibling SDKs, USE templates, upstream authorities (`loom/`, `atelier/`), downstream consumer projects, or any other GitHub repo — under any circumstance from this repo's session. Cross-repo work requires the user to context-switch (open Claude Code in the target repo); the agent does NOT make that switch on the user's behalf.

## MUST NOT

- Run `gh` commands against any repo other than this session's CWD repo, OR read source/specs/tests/session notes from any other repository under `~/repos/` to inform this session

**Why:** Cross-repo `gh` invocations and file reads contaminate the session's framing — recommendations cite paths and primitives that don't exist in the CWD repo, and the user has to mentally untangle which advice applies where.

- Suggest "context-switch to <other repo>", "next-turn pick: <other repo>", "the higher-priority workstream lives in <other repo>", or any equivalent framing that pushes the user toward a different repo. Sweep-style memories ("always check all three repos") are NOT license to cross repo boundaries inside an in-repo session

**Why:** The user opens the repo they want to work on; cross-repo prioritization is theirs to make, not the agent's to surface. Sweep memories apply at the orchestration root (`~/repos/`) ONLY — misapplying them inside a BUILD or USE repo is the originating failure mode this rule blocks.

- Write to, branch in, or modify the working tree of any sibling repository, OR file "upstream" issues against sibling SDKs unless the user is explicitly already filing and asks for body hygiene help

**Why:** Each repo has its own branch protection, ownership, release cadence, and rule set; cross-repo writes blur ownership and ship under rules the destination repo did not consent to. `upstream-issue-hygiene.md` describes BODY hygiene when filing IS happening; this rule blocks RECOMMENDING the filing one layer earlier.

**BLOCKED rationalizations:** "the other repo's issue is more urgent" / "just checking gh issues, not editing" / "the standing memory says check all three repos" / "surfacing isn't acting". Full list in extract.

## Exceptions

NONE for action. Descriptive sibling-repo mentions are OK when purely informational, not prescriptive. The rule does NOT apply at orchestration roots (`~/repos/`, `loom/`) where cross-repo coordination IS the legitimate purpose — `/sync`, `/sync-to-build`, `/inspect`, `/repos` cross repos by design.

Origin: 2026-05-03 — agent in a kailash-rs session surfaced "next-turn pick: kailash-py#803 or kailash-py#781"; user response: "NEVER TOUCH kailash-py or any other repositories! ALWAYS STAY IN YOUR LANE!" See guide for full post-mortem.
