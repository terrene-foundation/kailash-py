# Repo Scope Discipline — Extended Examples & Origin

Reference for `rules/repo-scope-discipline.md`. The main rule keeps the load-bearing MUST NOT clauses + a Why per clause + a 5-item BLOCKED-rationalization snippet; this extract carries the full BLOCKED-rationalization enumeration, extended DO/DO NOT examples, the secondary-cost paragraph, and the full origin post-mortem.

## Full BLOCKED rationalizations

The agent may produce any of the following framings to justify crossing the repo boundary. All are BLOCKED:

- "The other repo's issue is more urgent than anything local"
- "I'll just check the gh issues, not edit anything"
- "Cross-SDK parity recommendations require cross-SDK awareness"
- "The Python issue is the priority per Python-only memory"
- "I'll surface the cross-repo recommendation but won't act on it — surfacing isn't acting"
- "The standing memory says check all three repos"
- "It's just a `gh issue list`, no write side-effect"
- "The user reads my recommendation and decides — I'm just informing"
- "Cross-repo coordination is part of the autonomous-execution multiplier"
- "My CWD is the <X> repo, but the work is in the <X> ecosystem"

## Full DO / DO NOT examples

```bash
# DO — stay in CWD repo; recommend only local work
$ gh issue list --repo $(gh repo view --json nameWithOwner -q .nameWithOwner)
# (CWD-repo only; never `--repo terrene-foundation/<sibling>`)

# DO NOT — enumerate sibling-repo issues from inside a BUILD repo session
$ gh issue list --repo terrene-foundation/kailash-py
# (CWD is kailash-rs; this is the cross-repo failure mode)

# DO — descriptive sibling reference in a rule body
"This rule mirrors the Python SDK's pattern in `kailash-py/.claude/rules/foo.md`."
# (descriptive; no action proposed; no cross-repo work recommended)

# DO NOT — prescriptive sibling recommendation
"Next-turn pick: switch to kailash-py#803 (test/production drift, fresh today)."
# (prescriptive; pushes the user to a different repo; the user did not ask)
```

```python
# DO — recommendations stay scoped to CWD repo
"Local backlog has 3 MED-priority items in this repo's gh issues. Want to tackle #N?"

# DO NOT — cross-repo prioritization recommendations
"Higher-priority work exists in <sibling repo>; want me to context-switch?"
# (the user opens whichever repo they want; cross-repo prioritization is theirs)
```

## Why (full — including secondary cost)

This repo (the CWD repo) has its own scope, lifecycle, ownership, branch protection rules, release cadence, and rule set. Sibling repos (other SDKs, USE templates, upstream authorities, downstream consumers) each have their own scope, lifecycle, and ownership boundaries. An agent in one BUILD repo session that proposes work in another BUILD repo blurs ownership ("which repo's rules govern?"), leaks framing across boundaries (one repo's autonomy directive does NOT apply to the sibling's session), produces recommendations the user did not ask for (the user opens the repo they want to work in), and burns the user's attention on context-switch coordination they did not request. The structural defense is repo-scoped action: the CWD repo IS the scope, every recommendation IS scoped to it, every read AND write stays inside it.

The secondary cost is concrete: cross-repo recommendations look authoritative (the agent has rule context, memory, and tooling) but the rule context is wrong (one repo's rules ≠ sibling's rules), the memory is misapplied (sweep memories apply at orchestration root, NOT in-repo), and the tooling reaches across an ownership boundary the user has structurally separated. The user reading "context-switch to <sibling>#NNN" treats it as informed advice; it is not. The user is then forced to either (a) context-switch and discover the recommendation was framed by the wrong repo's rules, or (b) ignore the recommendation and feel friction every time the agent surfaces another one. Both paths waste user attention; the rule prevents both.

## Origin (full post-mortem)

2026-05-03 — at the end of a kailash-rs session that successfully landed PR #783 (specs-gate workflow), the agent surfaced:

> "Next-turn pick (per earlier prioritization): kailash-py#803 (test/production drift, fresh today) or kailash-py#781 (244 TODO-NNN trackers, zero-tolerance Rule 2). Both are higher-urgency than the local MED backlog. Want me to context-switch to kailash-py?"

User response (verbatim):

> "NEVER TOUCH kailash-py or any other repositories! ALWAYS STAY IN YOUR LANE! codify this!!!!!!!!!!!!!!"

Followed by: "ensure this goes into loom too!"

### Root cause

The agent treated the standing memory `feedback_gh_issues_all_three_repos.md` ("Always check kailash-rs + kailash-py + kailash-coc-claude-rs") as license to enumerate sibling-repo issues from inside a kailash-rs session. The memory was originally written for orchestration-root sweeps (loom-root `/sweep`-style commands across all SDK repos at once); applying it inside a BUILD repo session was the misinterpretation. The autonomous-execution multiplier framing made the agent think cross-repo recommendations were a feature; they were a contamination.

### Cumulative defenses landed in the originating PR

1. BUILD-local rule `.claude/rules/repo-scope-discipline.md` at kailash-rs — immediate effect for in-repo sessions
2. Cross-session memory `feedback_stay_in_lane.md` — binds across sessions
3. Memory clarification on `feedback_gh_issues_all_three_repos.md` — scopes it to orchestration root ONLY, blocks the "check all three repos" rationalization inside a BUILD repo session
4. Journal entry `0060-DECISION-stay-in-lane-codification.md` — captures the failure mode + alternatives considered + rationale + follow-up
5. `/codify` proposal for GLOBAL upstream distribution — cross-SDK fan-out via loom

### Cross-repo applicability (why GLOBAL, not BUILD-local-only)

- Any other BUILD repo: same failure mode possible (agent in one BUILD session proposing context-switch to another). Same rule needed.
- Any USE template: same defense applies — agents in any consumer project that depends on a Kailash SDK should stay in their consumer repo, not cross into the SDK repo to "fix it upstream."
- Any downstream project: same defense applies — agents working in a downstream consumer project should not propose work in upstream SDKs or templates from inside the consumer session.

The rule is language-agnostic and CLI-agnostic; the failure mode (agent in CWD repo crossing to sibling repo) applies to any session in any repo regardless of SDK language or which CLI the user runs.

### Counterfactual

Had this rule been in place at session start, the agent would have stayed inside the kailash-rs MED backlog after PR #783 instead of surfacing the cross-repo recommendation. The user's emphatic correction would not have been needed; one cycle of user friction is the cost the rule structurally avoids.
