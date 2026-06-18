# History Reconciliation — What Actually Landed vs What Didn't

The brief in `briefs/00-brief.md` and #979 itself both reference
PR #976 as if its fixes are present on main. They are NOT. This
file corrects the chronology before /todos so the plan does not
double-apply fixes or assume preconditions that don't hold.

## Timeline (verified via `gh pr view`)

| PR / SHA | Branch                                        | mergedAt                | Effect on main                                                                 |
| -------- | --------------------------------------------- | ----------------------- | ------------------------------------------------------------------------------ |
| PR #967  | (predecessor — fixed 12 unit fails)           | merged                  | 42 unit test fixes (`c64b18a2`)                                                |
| PR #968  | `feat/issue-898-shard2-dataflow-unit-ci-gate` | merged 2026-05-12       | Added `test-dataflow` job to unified-ci.yml                                    |
| PR #976  | `fix/dataflow-unit-ci-hang-after-968`         | **NULL — NEVER MERGED** | Closed without merging; commit `65009cc8` exists on the branch but not on main |
| PR #977  | `revert/968-dataflow-unit-ci-gate`            | merged 2026-05-12       | Reverted PR #968                                                               |
| PR #978  | `release/v2.21.0`                             | merged 2026-05-13       | Released 2.21.0 (orthogonal)                                                   |

## What this means for the plan

1. **PR #976's three fixes are NOT on main:**
   - `_fresh_db_url()` helper at 10 sites in `test_example_gallery.py` — NOT THERE
   - `pytest.importorskip("aiomysql")` in `test_mysql_adapter.py` — verify (may or may not be there from a separate PR)
   - `pytest.importorskip("redis")` in `test_auto_detection.py` — verify
   - `timeout = 120 / timeout_method = thread` in `pytest.ini` — NOT THERE

2. **Acceptance criteria interpretation:**
   - AC#1 (move test_example_gallery.py) — apply directly; no
     prior partial fix to reconcile.
   - AC#2 (fix test_dataflow_events.py 4+ failures) — verify
     these still reproduce; per Layer E findings the file is
     pure-Python and collects clean. Likely a no-op after
     verification.
   - AC#3-#5 (fabric, ImpactReporter, DB drivers) — apply directly.
   - AC#6 (clean pytest run in <2 min) — gate metric;
     unchanged.
   - AC#7 (re-apply PR #968) — explicit; one shard.

3. **Verification environment is critical.** PR #976's debug log
   describes failures observed in the CI environment (clean
   `[dev]`-only install). The local dev venv has `[fabric]`
   installed and won't reproduce Layer C. Every shard's
   verification MUST run in a fresh venv:
   ```bash
   python -m venv /tmp/dataflow-tier1 --clear
   /tmp/dataflow-tier1/bin/pip install -e packages/kailash-dataflow[dev]
   /tmp/dataflow-tier1/bin/pip install -e .  # root kailash editable per deployment.md
   /tmp/dataflow-tier1/bin/pytest packages/kailash-dataflow/tests/unit --collect-only
   ```
   This is the canonical CI tier-1 environment.
