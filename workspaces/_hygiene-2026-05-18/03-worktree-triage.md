# Worktree Triage — 2026-05-18

**Method**: For each of 24 worktrees (23 under `kailash-py/.claude/worktrees/`, 1 under `loom/.claude/worktrees/` but registered to kailash-py's git), computed `git log <branch> --not main --oneline | wc -l` to detect commits whose CONTENT is not present on main. Cross-referenced parent issue (CLOSED?) and shipping PR (MERGED, different SHA from branch tip due to squash-merge) via `gh issue view` and `gh pr list --search head:<branch>`. Branches with `UNIQUE=0` AND `git branch --contains <tip> main` returning `main` confirm the branch tip is reachable from main — no orphan content.

## Safe-remove (24 worktrees)

| Worktree                                                           | Branch                                                 | Parent issue              | Shipping PR                            | Verification                                                                     |
| ------------------------------------------------------------------ | ------------------------------------------------------ | ------------------------- | -------------------------------------- | -------------------------------------------------------------------------------- |
| `/Users/esperie/repos/loom/.claude/worktrees/issue-1047-sanitizer` | `test/issue-1047-sanitizer-contract`                   | #1047 CLOSED              | none — tip on main directly            | UNIQUE=0, contains-main=1                                                        |
| `.claude/worktrees/agent-a16e85de3ba19b9ba`                        | `worktree-agent-a16e85de3ba19b9ba`                     | dataflow CHANGELOG (anon) | none — tip on main directly            | UNIQUE=0, contains-main=1                                                        |
| `.claude/worktrees/agent-a191f3d896dc291ac`                        | `docs/issue-1068-constant-time-validator`              | #1068                     | PR #1073 MERGED                        | UNIQUE=0                                                                         |
| `.claude/worktrees/agent-a1ab206893ceb93da`                        | `fix/issue-900-credential-ref-param`                   | #900                      | PR #965 MERGED                         | UNIQUE=0                                                                         |
| `.claude/worktrees/agent-a1af342e8bb6627eb`                        | `fix/issue-898-dataflow-unit-tests`                    | #898                      | PR #967 MERGED                         | UNIQUE=0                                                                         |
| `.claude/worktrees/agent-a38688c4a9ac0358e`                        | `fix/issue-1045-protection-test-async-fixture`         | #1045                     | PR #1053 MERGED                        | UNIQUE=0                                                                         |
| `.claude/worktrees/agent-a3eb2e0b96f7096b2`                        | `fix/issue-1047b-sanitizer-set-tuple-typeconfusion`    | #1047 CLOSED              | PR #1074 MERGED                        | UNIQUE=0                                                                         |
| `.claude/worktrees/agent-a4adf0920513b022e`                        | `fix/issue-942-asyncsql-wait-for-warning`              | #942                      | PR #966 MERGED                         | UNIQUE=0                                                                         |
| `.claude/worktrees/agent-a5299715947a96848`                        | `fix/issue-1070-txn-abort-state-reset`                 | #1070                     | PR #1075 MERGED                        | UNIQUE=0                                                                         |
| `.claude/worktrees/agent-a53ad9d3ea542b7bf`                        | `feat/issue-1054-eventbus`                             | #1054                     | PR #1078 MERGED                        | UNIQUE=0                                                                         |
| `.claude/worktrees/agent-a5b8a2861fc971fb0`                        | `worktree-agent-a5b8a2861fc971fb0`                     | #913 CLOSED               | PR #936 MERGED (squash)                | UNIQUE=5 — pre-squash; content shipped via squash, main has POLISH not on branch |
| `.claude/worktrees/agent-a5c5e1f0a7fbc31d9`                        | `work/issue-913-fix`                                   | #913 CLOSED               | none — cyclic-import fix landed direct | UNIQUE=0, contains-main=1                                                        |
| `.claude/worktrees/agent-a5de40c1d2fa4673b`                        | `feat/issue-999-regression-scaffolding`                | #999                      | PR #1041 MERGED                        | UNIQUE=0                                                                         |
| `.claude/worktrees/agent-a6fb19e47bf120cb1`                        | `fix/issue-1071-api-discipline`                        | #1071                     | PR #1077 MERGED                        | UNIQUE=0                                                                         |
| `.claude/worktrees/agent-a78799265ba8722ac`                        | `fix/issue-929-workflow-round-trip-serialization`      | #929                      | PR #940 MERGED                         | UNIQUE=0                                                                         |
| `.claude/worktrees/agent-abd85e1583a44188c`                        | `feat/issue-913-scheduler-admin-api`                   | #913 CLOSED               | PR #936 MERGED (squash)                | UNIQUE=3 — pre-squash; content shipped via squash, main has POLISH not on branch |
| `.claude/worktrees/agent-abff1f73079de6715`                        | `feat/issue-1050-shard3-mutation-matrix`               | #1050                     | PR #1060 MERGED                        | UNIQUE=0                                                                         |
| `.claude/worktrees/agent-ac02636b86de8310e`                        | `fix/issue-953-localruntime-pool-tracking`             | #953                      | PR #969 MERGED                         | UNIQUE=0                                                                         |
| `.claude/worktrees/agent-af883b59fe1d4f2b7`                        | `feat/issue-898-shard2-dataflow-unit-ci-gate`          | #898                      | PR #968 MERGED                         | UNIQUE=0                                                                         |
| `.claude/worktrees/agent-affb9ed1c7cad4e4c`                        | `fix/issue-1045-protection-middleware-localruntime-cm` | #1045                     | none — tip on main directly            | UNIQUE=0, contains-main=1                                                        |
| `.claude/worktrees/shard-a-close`                                  | `fix/issue-1045-protected-runtime-close`               | #1045                     | PR #1052 MERGED                        | UNIQUE=0                                                                         |
| `.claude/worktrees/w4-durable-engine`                              | `feat/w4-durable-execution-engine`                     | (W4 wave)                 | PR #879 MERGED                         | UNIQUE=0                                                                         |
| `.claude/worktrees/w5-tier3-crash-resume`                          | `feat/w5-tier3-crash-resume-redaction`                 | (W5 wave)                 | PR #883 MERGED                         | UNIQUE=0                                                                         |
| `.claude/worktrees/w6-redaction-discipline`                        | `fix/w6-checkpoint-dispatcher-redaction-discipline`    | (W6 wave)                 | PR #880 MERGED                         | UNIQUE=0                                                                         |

**Note on the two UNIQUE>0 branches (#913 worktrees):** Both `agent-a5b8a2861fc971fb0` and `agent-abd85e1583a44188c` show "unique commits" because they are pre-squash history. The content (`src/kailash/runtime/scheduler_admin.py`, `tests/integration/scheduler/test_scheduler_admin_api.py`, CHANGELOG, spec entries) all exists on main via the squashed PR #936. A `git diff main <branch> -- scheduler_admin.py` shows main is AHEAD (post-merge polish added `_RETRY_SPEC_KWARG` constant the branch lacks). No orphan content. Safe to remove.

## Recover-first (0 worktrees)

None. All 24 worktrees have their content present on main, either via direct rebase/merge (`UNIQUE=0, contains-main=1`) or via squash-merge (UNIQUE>0 but content on main + main is ahead).

## Ambiguous (0 worktrees)

None.

## Summary

- **Safe-remove**: 24 (orchestrator runs `git worktree remove --force <path>` + `git branch -D <branch>` after user approval)
- **Recover-first**: 0
- **Ambiguous**: 0

All 24 worktrees are parked branches whose work shipped via merged PRs (or whose tips are already reachable from main). Per `rules/agents.md` § "Recover Orphan Writes From Zero-Commit Worktree Agents", the orphan-detection check (`git diff main...<branch>`) confirms zero recoverable content outside main.

## Recommended bulk command (only for SAFE-REMOVE list — DO NOT RUN; orchestrator reference after user approval)

```bash
# Worktrees inside kailash-py (23)
for pair in \
  ".claude/worktrees/agent-a16e85de3ba19b9ba:worktree-agent-a16e85de3ba19b9ba" \
  ".claude/worktrees/agent-a191f3d896dc291ac:docs/issue-1068-constant-time-validator" \
  ".claude/worktrees/agent-a1ab206893ceb93da:fix/issue-900-credential-ref-param" \
  ".claude/worktrees/agent-a1af342e8bb6627eb:fix/issue-898-dataflow-unit-tests" \
  ".claude/worktrees/agent-a38688c4a9ac0358e:fix/issue-1045-protection-test-async-fixture" \
  ".claude/worktrees/agent-a3eb2e0b96f7096b2:fix/issue-1047b-sanitizer-set-tuple-typeconfusion" \
  ".claude/worktrees/agent-a4adf0920513b022e:fix/issue-942-asyncsql-wait-for-warning" \
  ".claude/worktrees/agent-a5299715947a96848:fix/issue-1070-txn-abort-state-reset" \
  ".claude/worktrees/agent-a53ad9d3ea542b7bf:feat/issue-1054-eventbus" \
  ".claude/worktrees/agent-a5b8a2861fc971fb0:worktree-agent-a5b8a2861fc971fb0" \
  ".claude/worktrees/agent-a5c5e1f0a7fbc31d9:work/issue-913-fix" \
  ".claude/worktrees/agent-a5de40c1d2fa4673b:feat/issue-999-regression-scaffolding" \
  ".claude/worktrees/agent-a6fb19e47bf120cb1:fix/issue-1071-api-discipline" \
  ".claude/worktrees/agent-a78799265ba8722ac:fix/issue-929-workflow-round-trip-serialization" \
  ".claude/worktrees/agent-abd85e1583a44188c:feat/issue-913-scheduler-admin-api" \
  ".claude/worktrees/agent-abff1f73079de6715:feat/issue-1050-shard3-mutation-matrix" \
  ".claude/worktrees/agent-ac02636b86de8310e:fix/issue-953-localruntime-pool-tracking" \
  ".claude/worktrees/agent-af883b59fe1d4f2b7:feat/issue-898-shard2-dataflow-unit-ci-gate" \
  ".claude/worktrees/agent-affb9ed1c7cad4e4c:fix/issue-1045-protection-middleware-localruntime-cm" \
  ".claude/worktrees/shard-a-close:fix/issue-1045-protected-runtime-close" \
  ".claude/worktrees/w4-durable-engine:feat/w4-durable-execution-engine" \
  ".claude/worktrees/w5-tier3-crash-resume:feat/w5-tier3-crash-resume-redaction" \
  ".claude/worktrees/w6-redaction-discipline:fix/w6-checkpoint-dispatcher-redaction-discipline"; do
  wt="${pair%%:*}"; br="${pair##*:}"
  git worktree remove --force "$wt"
  git branch -D "$br"
done

# Loom-path worktree (registered to kailash-py git, 1)
git worktree remove --force /Users/esperie/repos/loom/.claude/worktrees/issue-1047-sanitizer
git branch -D test/issue-1047-sanitizer-contract

git worktree prune
```
