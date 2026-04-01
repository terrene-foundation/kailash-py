---
type: DISCOVERY
date: 2026-03-30
project: kailash
topic: Three CI failure modes discovered during kaizen-agents v0.5.0 release
phase: codify
tags: [ci, release, github-actions]
---

# CI Release Failure Modes

## Discovery

Three CI issues surfaced during the kaizen-agents v0.5.0 release:

1. **publish-pypi.yml**: `gh release create` fails if release already exists (e.g., created manually before CI ran). Fixed: check existence first, upload artifacts to existing release.

2. **deploy-production.yml**: Triggers on ALL `release: [published]` events, not just kaizen-v\* tags. A kaizen-agents release triggered container builds for kailash-kaizen (which has no container). Fixed: added `if` guard on setup job to filter by tag prefix.

3. **project-automation.yml**: Labeler action lacked `pull-requests: write` permission, causing every PR to show a failed check. Pre-existing since the workflow was created. Fixed: added permissions block.

## Impact

All three were pre-existing latent issues that only manifested during this specific release sequence (manual release creation + non-container package tag + PR labeling). PRs #162, #163, #164 fixed all three.
