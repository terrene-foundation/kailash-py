---
type: DECISION
slug: cross-repo-authorized-loom-env-models-carveout
created: 2026-06-11T13:05:19Z
---

# Cross-Repo FILING authorized — env-models provider-intrinsic carve-out (esperie-enterprise/loom)

cross-repo-authorized: esperie-enterprise/loom

User-Authorized Exception per `rules/repo-scope-discipline.md`. This kailash-py
BUILD session is authorized to file ONE issue against the loom repo only.

## Five conditions (repo-scope-discipline) — satisfied this session

1. **User-initiated:** genuine user turn requesting the filing.
2. **Explicit + specific:** target repo named (loom → `esperie-enterprise/loom`),
   exact action named (file one issue), exact content drafted + shown before approval.
3. **Confirmed:** agent restated the issue + asked for slug; user approved.
4. **Journaled before acting:** this entry lands BEFORE the `gh issue create` command.
5. **Scoped exactly:** this ONE filing only. No loom reads beyond the existence
   check (`gh repo view esperie-enterprise/loom` → exists, private, issues enabled).
   No further loom writes without a new gate.

## Verbatim user directives

- "please file the loom issue in loom repo. Do we need to /codify?"
- "approved, esperie-enterprise"

## Action

`gh issue create --repo esperie-enterprise/loom` — ONE issue:
add an `env-models.md` carve-out for provider-intrinsic `DEFAULT_<PROVIDER>_MODEL`
named-constant defaults so a future `/redteam` does not re-flag them as hardcoded
model names.

## Scrub (upstream-issue-hygiene Rule 2/3)

Body scoped to the loom rule surface + the kaizen public config API only. No
kailash-py internal paths, no workspace ids, no finding tags. References the
public PRs #1292 / #1294 (already public on the kailash-py repo) as origin context.

## Routing rationale (artifact-flow)

env-models.md is a loom-owned global rule synced to kailash-py; the local copy
MUST NOT be edited (overwritten on next /sync). The carve-out must be authored in
a loom session. A loom issue is the durable hand-off tracker. Full `/codify` not
warranted: no reusable kailash-py-local artifact to extract, single loom-rule edit.

## Result

Filed: esperie-enterprise/loom#485 (https://github.com/esperie-enterprise/loom/issues/485).
