# Stale Remote Branch Cleanup — 2026-05-18

5 stale remote branches verified against PR history + content-vs-main diff.

| Branch                                         | Last commit | PR history                                | Disposition             | Rationale                                                                                                                                                                                                                                       |
| ---------------------------------------------- | ----------- | ----------------------------------------- | ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `debug/issue-1010-phase-a-diagnostics`         | 3 days ago  | no PR                                     | **KEEP**                | Deliberately preserved per `workspaces/issue-1002-aiosqlite-fixture-cleanup/.session-notes:15` — "Debug branches preserved on remote (never merge)"                                                                                             |
| `debug/issue-1010-phase-a-prime-linux`         | 3 days ago  | no PR                                     | **KEEP**                | Same — debug-only, intentional preservation                                                                                                                                                                                                     |
| `fix/dataflow-unit-ci-hang-after-968`          | 5 days ago  | PR #976 CLOSED (not merged)               | **SAFE-DELETE**         | Work superseded; alternate fix shipped via different path. PR closed-not-merged.                                                                                                                                                                |
| `fix/issue-1002-shard4b-remove-setsid-wrapper` | 3 days ago  | PRs #1008, #1015 BOTH CLOSED (not merged) | **SAFE-DELETE**         | Work shipped via PR #1017 per `workspaces/issue-1002-aiosqlite-fixture-cleanup/.session-notes:7`                                                                                                                                                |
| `style/align-pre-commit-sweep`                 | 10 days ago | PR #886 CLOSED (not merged)               | **NEEDS-USER-DECISION** | 33 files modified, 51 ins / 120 del (mostly deletion). Branch contains `tests/unit/rl_bridge/test_registry_population.py` deletions + `test_alignment_diagnostics_unit.py` change. PR closed without merge — was this superseded, or abandoned? |

## Recommended commands (user-gated; orchestrator runs after approval)

```bash
# Safe-delete (2 branches)
git push origin --delete fix/dataflow-unit-ci-hang-after-968
git push origin --delete fix/issue-1002-shard4b-remove-setsid-wrapper

# User-decision (only if user confirms)
# git push origin --delete style/align-pre-commit-sweep

# DO NOT delete (intentional preservation per session-notes)
# debug/issue-1010-phase-a-diagnostics
# debug/issue-1010-phase-a-prime-linux
```

## User gate question

- (a) Delete the 2 SAFE-DELETE branches as above (debug branches preserved)?
- (b) Also delete `style/align-pre-commit-sweep`, OR keep for possible re-pickup?
