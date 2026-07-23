# Launch Ledger — cont-15 (F-TESTHYG checkpoint-dir fix)

Durable record of background agents spawned this session (orchestration-launch-ledger MUST-1).
Self-launched; match completion notifications against this table before reacting.

## Task

F-TESTHYG (reconciled from the orphaned cont-14 deferral): `BaseAutonomousAgent.__init__`
created `./checkpoints/` in the caller's cwd unconditionally on construction. Fix = lazy dir
creation (moved `mkdir` from `__init__` into `_save_checkpoint`). User approved "action it now".

## Change set (implemented + verified, pre-redteam)

- `packages/kaizen-agents/src/kaizen_agents/agents/autonomous/base.py` — removed eager `mkdir`
  from `__init__`; added lazy `mkdir` in `_save_checkpoint` (first-write).
- `packages/kaizen-agents/tests/regression/test_checkpoint_dir_no_cwd_litter.py` — NEW, 3
  behavioral regression tests. All pass; 44 autonomous unit tests pass; 3478 collect clean; 0 WARN+.
- Runtime walk confirmed: construct → no dir; first `_save_checkpoint` → dir + file created.

## Background agents (redteam round 1)

| agent             | scope                                 | status    |
| ----------------- | ------------------------------------- | --------- |
| reviewer          | correctness / missed consumers of dir | in-flight |
| security-reviewer | error-hiding / path / posture         | in-flight |

## Release target (staged, NOT yet cut — awaits redteam convergence)

kaizen-agents 0.11.7 → **0.11.8** (patch, `### Fixed`). Anchors: pyproject.toml + **init**.py.

## Residual for owner (surfaced, not actioned)

Running codex/claude_code autonomous agents still default checkpoints to `./checkpoints` in the
user's cwd (documented default-location; lazy-mkdir fixes only the construct-time litter). Changing
the default location is a documented-behavior change — owner decision, not made unilaterally.
