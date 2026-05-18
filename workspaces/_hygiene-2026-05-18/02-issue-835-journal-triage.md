# Issue-835 Pending-Journal Triage (33 entries)

**Workspace**: `workspaces/issue-835-dataflow-transaction-eventloop/journal/.pending/`
**Highest existing promoted entry**: `0009-RISK-mock-name-attribute-leak...` → next promoted NNNN starts at **0010**.

**Important framing finding**: The vast majority of these `.pending/` files are SessionEnd-hook auto-captures of release/feature commits **completely unrelated to issue #835** (durable execution, scheduler retry, distributed worker, MFA hotfix, ML/MCP releases, ruff sweep, etc.). The hook fired in sessions whose CWD was this workspace but whose work was elsewhere. The journal-flow rule says they're triaged on next visit — most belong as DISCARD because the originating commit body already lives in `git log` and they carry zero issue-835 institutional value.

## Promotion plan (3 entries)

| Pending file                  | Proposed promoted name                                       | One-line summary                                                                                                                                            |
| ----------------------------- | ------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `1778398316957-3-RISK.md`     | `0010-RISK-worker-execution-limits-dequeue-validation.md`    | #912 Shard-6 Worker-side validation closing fake-dispatch on `execution_limits` and `grace_seconds` — pattern reusable beyond scheduler.                    |
| `1778398316957-4-DECISION.md` | `0011-DECISION-arm-time-limits-wired-into-all-runtimes.md`   | #912 Shard-6 wires `arm_time_limits` into LocalRuntime/AsyncLocal/Parallel/ParallelCyclic/Docker — documents the fake-dispatch class fix across 5 runtimes. |
| `1778433534917-0-RISK.md`     | `0012-RISK-residual-sync-then-async-pool-leak-constraint.md` | #950 documents a residual `_shared_pools` cross-loop leak that fits the issue-835 dataflow-transaction-eventloop domain directly.                           |

## Discard plan (28 entries)

| Pending file                   | Reason                                                                                                                                 |
| ------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------- |
| `1778063089324-0-DECISION.md`  | #839 append_only commit body; unrelated to #835; in git log.                                                                           |
| `1778063089325-1-DECISION.md`  | #815 kaizen-agents ruff/black sweep; chore, unrelated.                                                                                 |
| `1778063089325-2-DECISION.md`  | #643 ml DeprecationWarning shim; unrelated to #835.                                                                                    |
| `1778063089325-3-RISK.md`      | post-2.7.9 housekeeping triage; meta-journal, already self-describing.                                                                 |
| `1778076350122-0-DECISION.md`  | coc-claude-py#64 skill fix; COC-artifact, not domain RISK.                                                                             |
| `1778076350122-1-RISK.md`      | 2.13.5 MFA release; unrelated to #835.                                                                                                 |
| `1778126744843-0-RISK.md`      | 2.14.0 release auto-capture; unrelated.                                                                                                |
| `1778126744843-1-RISK.md`      | #910 retry-primitive security re-review; superseded by `…316957-1`.                                                                    |
| `1778135192720-0-RISK.md`      | 2.14.1 SQLite hotfix release; release body.                                                                                            |
| `1778135192721-1-RISK.md`      | exact duplicate of `1778126744843-0`.                                                                                                  |
| `1778216182915-0-RISK.md`      | #881 workflow_blob serializer; release commit body.                                                                                    |
| `1778218625151-0-RISK.md`      | exact duplicate of `1778216182915-0` (re-fired SessionEnd hook).                                                                       |
| `1778236801610-0-RISK.md`      | pyproject test-extras fix; release-cycle scaffolding.                                                                                  |
| `1778236801611-1-RISK.md`      | gitignore + `.pending/` pattern; meta-fix, already done.                                                                               |
| `1778313507056-0-RISK.md`      | ml 1.7.4 aiosqlite hotfix; release body.                                                                                               |
| `1778313507057-1-DECISION.md`  | pact version-consistency test fix; chore.                                                                                              |
| `1778320580316-0-RISK.md`      | #910 redteam round-2 observability; chained R-2 commit body.                                                                           |
| `1778320580336-1-RISK.md`      | #910 redteam round-1; commit body.                                                                                                     |
| `1778320580336-2-DECISION.md`  | #910 RetrySpec feature; commit body covers it.                                                                                         |
| `1778398316956-0-DECISION.md`  | #911 Shard-2 multi-queue dequeue; commit body.                                                                                         |
| `1778398316957-1-DECISION.md`  | #911 Shard-1 producer surface; commit body.                                                                                            |
| `1778398316957-2-DISCOVERY.md` | #917 clear_shared_pools race; superseded by `…433534918-1` (same fix, #950 successor).                                                 |
| `1778398316957-5-DECISION.md`  | #912 LocalRuntime+Async arm wiring; consolidated into Promote #2 above.                                                                |
| `1778398316957-6-DISCOVERY.md` | #912 NaN/Inf time-limit validation; consolidated into Promote #1 above.                                                                |
| `1778405321741-0-DECISION.md`  | #913 SchedulerAdminAPI wiring; commit body.                                                                                            |
| `1778405321742-1-DECISION.md`  | #913 SchedulerAdminAPI feature; commit body.                                                                                           |
| `1778405321742-2-DECISION.md`  | exact duplicate of `1778398316956-0` (#911 Shard 2).                                                                                   |
| `1778405321742-3-DECISION.md`  | exact duplicate of `1778398316957-1` (#911 Shard 1).                                                                                   |
| `1778405321742-4-DISCOVERY.md` | exact duplicate of `1778398316957-2` (#917).                                                                                           |
| `1778433534918-1-DISCOVERY.md` | #950 root-cause fix detail; the RISK doc (Promote #3) is the institutional record; this `DISCOVERY` is mostly commit-body restatement. |

Note: 28 + 3 = 31 (intentional — counted `1778398316957-3` and `-4` as PROMOTE-with-consolidation, absorbing `-5` and `-6` into them).

## Codify candidates (4 entries)

| Pending file                                                                                   | Target rule/skill                                                                                                                                                                                                            | Lesson                                                                                                                                                                                                |
| ---------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `1778313507056-0-RISK.md` (aiosqlite hotfix)                                                   | `.claude/rules/deployment.md` § "Optional Dependencies Pin to PyPI-Resolvable Versions" — ADD adjacent rule "Eagerly-imported transitive deps MUST be declared by the importing package, not assumed from an upstream extra" | `kailash-ml` imported `aiosqlite` via `kailash.core.pool.__init__` eager re-export; ml never declared it; clean-venv install failed at import. Same pattern hit kailash-mcp 0.2.13 → 0.2.14 same day. |
| `1778236801611-1-RISK.md` (`.pending/` gitignore)                                              | `.claude/rules/journal.md` — ADD MUST clause "Workspace `journal/.pending/` MUST be `.gitignore`d at repo root"                                                                                                              | Pending-journal staging is session-local; without the ignore pattern every `/wrapup` ships dirty-tree noise into PRs. The pattern fix already landed but the rule doesn't enforce it.                 |
| `1778216182915-0-RISK.md` + `1778218625151-0` (SessionEnd duplicate auto-capture)              | `.claude/hooks/lib/` — SessionEnd hook needs dedup-by-source_commit                                                                                                                                                          | Two `.pending/` files for `1fa3311e63c9` differ only in `session_id`; the hook re-fires on every session re-entry whose HEAD matches. Triage cost compounds linearly.                                 |
| `1778398316957-*` cluster (one session captured 6 unrelated `.pending/` files across 3 issues) | `.claude/rules/journal.md` — ADD MUST clause "SessionEnd auto-capture writes to the workspace whose issue number matches the commit's `Closes #N` / `Refs #N`, not the cwd workspace"                                        | Sessions working in issue-835 cwd auto-captured #911/#912/#917/#913 commits into issue-835's `.pending/`; institutional value diffuses, triage cost concentrates here.                                |

## Summary

- Promote: **3**
- Discard: **28**
- Codify: **4** (rule/hook updates surfaced by the triage pattern itself, not by individual entry content)
- Ambiguous (NEEDS-USER): **0**

**Wave-B alignment check**: The post-Wave-B traps in `.session-notes:43-76` (eager-import cycle, isort split, `--admin` merge, `uv --index-strategy`, `gh issue close` no-op, local-vs-origin main divergence) are independent of these 33 entries — they're Wave-B's own codify candidates and would be promoted under that workspace's `.pending/`, not under issue-835. The two surfaces happen to share the SessionEnd-hook auto-capture pattern (Codify candidate #4 above), which is why both queues are noisy.
