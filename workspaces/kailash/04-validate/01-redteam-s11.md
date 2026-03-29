# Red Team Report — Sprint S11

**Date**: 2026-03-29
**Issue**: #159 — Wire ToolCallStart/ToolCallEnd events in Delegate streaming
**Rounds**: R1 → R2 (converged)

## Test Results

- delegate tests: 420 passed (+8 new), 0 failed, 0 regressions
- core unit tests: 3072 passed, 0 failed, 0 regressions

## R1 Findings (fixed in R2)

| #   | Severity  | Finding                                                    | Fix                                                            |
| --- | --------- | ---------------------------------------------------------- | -------------------------------------------------------------- |
| S1  | LOW→FIXED | `str(exc)` in `_run_single` passes raw exception to events | Sanitized: `f"Tool '{name}' failed with {type(exc).__name__}"` |

## R2 Security Findings (3 HIGH — all fixed)

| #   | Severity   | Finding                                                              | Fix                                                         |
| --- | ---------- | -------------------------------------------------------------------- | ----------------------------------------------------------- |
| H1  | HIGH→FIXED | `str(exc)` in `Delegate.run()` ErrorEvent leaks internal details     | `f"Delegate execution failed ({type(exc).__name__})"`       |
| H2  | HIGH→FIXED | `str(exc)` in `PrintRunner.run()` error message leaks to JSON output | `f"Execution failed ({type(exc).__name__})"` + logger added |
| H3  | HIGH→FIXED | `str(exc)` in `hooks.py` HookResult.stderr leaks file paths          | `f"Hook spawn failed ({type(exc).__name__})"`               |

## R2 Medium Findings (accepted)

| #   | Severity     | Finding                                                      | Status                                                                                                                                            |
| --- | ------------ | ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| M1  | MEDIUM       | ToolCallEnd.result passes raw tool output without truncation | ACCEPTED — same data already in conversation.messages; truncation would break model's ability to see tool results                                 |
| M2  | MEDIUM       | Event dataclasses not frozen=True                            | ACCEPTED — events are ephemeral (consumed and GC'd by async generator); freezing would add overhead with no security benefit for streaming events |
| M4  | MEDIUM→FIXED | `run_interactive` `display.show_error(str(exc))`             | `f"Turn failed ({type(exc).__name__})"`                                                                                                           |
| M5  | MEDIUM       | `type(exc).__name__` reveals library names                   | ACCEPTED — exception type names are generic enough; the trade-off between debuggability and minimal information disclosure is reasonable          |

## R2 Edge Case Gap (fixed)

| #   | Finding                                   | Fix                                                                       |
| --- | ----------------------------------------- | ------------------------------------------------------------------------- |
| R1  | Multi-tool-turn (tool→tool→text) untested | Added `test_consecutive_tool_turns_emit_events_for_each_batch` — 8th test |

## R2 Code Quality Findings (from intermediate-reviewer)

| #   | Severity | Finding                                                                                 | Status                                                                                           |
| --- | -------- | --------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| Q1  | MEDIUM   | Unused imports in loop.py (`time`, `AsyncIterator`, `StreamEvent`)                      | PRE-EXISTING — not introduced by S11; keeping diff focused                                       |
| Q2  | MEDIUM   | ToolCallEnd.error inconsistency (normal errors in `.result`, BaseException in `.error`) | ACCEPTED — matches pre-existing tool result behavior; normalizing would be a breaking API change |
| Q3  | LOW      | `_MultiTurnFakeAdapter` silently clamps to last turn                                    | ACCEPTED — simple test helper, explicit error would over-engineer                                |

## R2 Edge Case Findings (from deep-analyst)

All 10 edge cases rated COVERED. R1 gap (multi-tool-turn) was fixed during R2 with `test_consecutive_tool_turns_emit_events_for_each_batch`.

## Convergence

**R2 converged**: 3 agents deployed (security-reviewer, intermediate-reviewer, deep-analyst). 0 CRITICAL, 0 HIGH remaining. 4 HIGH fixed (H1-H3, M4), 1 edge case gap fixed (R1). 420 tests pass, 0 regressions.

## Files Changed (complete list)

### Production

- `delegate/loop.py` — Core wiring + error sanitization in `_run_single` + `run_interactive`
- `delegate/delegate.py` — Type dispatch in `run()` + error sanitization in ErrorEvent
- `delegate/print_mode.py` — isinstance filter + error sanitization + logger
- `delegate/hooks.py` — Error sanitization in HookResult.stderr

### Tests

- `tests/unit/delegate/test_delegate.py` — 8 new tests + test infrastructure
- `tests/unit/delegate/test_loop.py` — isinstance filters + sanitization assertions
