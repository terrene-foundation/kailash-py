# Release: 2026-03-19 — Tool Agent Support

## Packages Released

| Package          | Version | Tag             | PyPI      |
| ---------------- | ------- | --------------- | --------- |
| eatp             | 0.2.0   | eatp-v0.2.0     | Published |
| kailash-kaizen   | 1.3.0   | kaizen-v1.3.0   | Published |
| kailash-dataflow | 1.0.1   | dataflow-v1.0.1 | Published |

## Packages NOT Released (no functional changes)

| Package       | Version | Reason          |
| ------------- | ------- | --------------- |
| kailash       | 1.0.0   | CI-only changes |
| kailash-nexus | 1.4.2   | Formatting only |
| trust-plane   | 0.2.1   | Formatting only |

## Workspace

`workspaces/tool-agent-support/` — 4 milestones, 24 TODOs, red team R2 converged.

## Verification

- CI publish: 3/3 success
- PyPI install: `pip install eatp==0.2.0 kailash-kaizen==1.3.0 kailash-dataflow==1.0.1` verified
- GitHub releases: auto-created by CI
- Docs deployment: success
- COC template: dependency pins updated in kailash-coc-claude-py

## Test Results

- EATP: 2854 passed
- Kaizen: 203 passed
- DataFlow: 75 passed
- Total: 3132 passed, 0 regressions

## Cross-Repo Updates

- kailash-coc-claude-py: dependency pins bumped
- kailash-coc-claude-rs: dependency pin bumped (kailash-enterprise>=2.9.1)
- kailash-rs: issue #38 filed (CostTracker float precision)
