# Burndown register

Frozen source baseline: `3764191aac1fcdf6c91d9071235d10bbee4e5188`. Captured 2026-09-25 with `gh issue list --state open --limit 1000 --json number,title,body,comments,labels,url,createdAt,updatedAt`. The root session baseline supplied the original issue IDs; the capture matches that set. The manifest declares every source.

The GitHub issue page is an issue-level population. The standing forest page is a separate population of coordination obligations; it overlaps the issue page by design. `ALL PAGES` counts register rows, **not distinct defects, releases, or remaining implementation work**. Do not interpret its denominator as an issue count.

Status semantics: `Built-not-walked` means a relevant landed receipt exists and closure-parity verification is owed. It does not mean all acceptance criteria are satisfied. `In progress` includes partial fixes or an assigned active lane. `Blocked on you` identifies an explicit policy/product choice recorded in the issue or handover. Other rows remain `Not started`; census reading alone is not implementation. Nothing in this agent-authored snapshot claims owner signoff.

The GitHub open/closed state and labels are observations, not these acceptance buckets. Preserve frozen IDs even when GitHub closes an issue. Add newly observed IDs only through a declared growth source; append status refreshes for existing IDs after evidence arrives. Only a documented owner acceptance may justify `Signed off`.

Rebuild after committing source updates: `node .claude/bin/burndown-build.mjs --write`, then `--check`. Quote `--quote Open` or another canonical bucket without editing tokens. The sources and manifest must be committed and unmodified before generation.

See [triage dispositions](TRIAGE.md). Historical comment claims were used to propose the next verification task, not as fresh runtime results.
