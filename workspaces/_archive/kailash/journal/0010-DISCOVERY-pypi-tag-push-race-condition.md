---
type: DISCOVERY
date: 2026-03-30
created_at: "2026-03-30T15:50:00Z"
author: agent
session_id: session-6
session_turn: 8
project: kailash
topic: PyPI publish workflow fails silently when multiple tags pushed simultaneously
phase: implement
tags: [ci, pypi, publish, github-actions]
---

# PyPI Tag-Push Race Condition

## Finding

Session 5 claimed 4 packages were released to PyPI, but only kailash-kaizen 2.3.2 actually published. Three packages (kailash 2.3.0, kailash-dataflow 1.3.0, kaizen-agents 0.6.0) had tags created and pushed to GitHub but the `publish-pypi.yml` workflow never triggered for them.

All three tags pointed to the same merge commit (`fd5bea54`) and were likely pushed in a single `git push --tags` operation. GitHub Actions appears to have only triggered the workflow for one of the concurrent tag pushes.

## Evidence

- `pip index versions kailash` showed 2.2.1 (not 2.3.0) despite `v2.3.0` tag existing on remote
- `gh run list --workflow=publish-pypi.yml` showed no runs for `v2.3.0`, `dataflow-v1.3.0`, or `kaizen-agents-v0.6.0` tags
- Manual `workflow_dispatch` runs from session 5 (2026-03-29 12:23) published stale versions (e.g., kaizen-agents 0.4.0 instead of 0.6.0) because main hadn't been updated yet

## Resolution

Re-triggered all 3 publishes via `workflow_dispatch` after confirming main had correct versions. All succeeded.

## Prevention

When releasing multiple packages, push tags one at a time with a brief delay, or use `workflow_dispatch` as the primary publish mechanism rather than relying on tag-triggered workflows.

## For Discussion

1. Given that `workflow_dispatch` builds from HEAD of the specified branch, what happens if another PR merges between dispatch and build — could it publish unintended changes?
2. If GitHub had processed all tag pushes but the publish had failed silently, how would we detect this without manually checking PyPI after every release?
3. Should the release process be changed to push tags individually rather than in batch?
