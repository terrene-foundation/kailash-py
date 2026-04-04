# Red Team Findings — Fabric Engine (Round 2)

## CRITICAL

### C1/C2: #245 and #248 root causes confirmed at exact lines

- serving.py:227-235 returns data:None for virtual products — confirmed
- runtime.py:162-163 skips pre-warming in dev_mode — confirmed

## HIGH

### H1: #252 scope is 4-5x underestimated

Plan says ~25 lines. Reality: `database_type` is an `@abstractmethod` with 121 references across 21 files, 15 concrete implementations. Deprecation shim on `@property @abstractmethod` is non-trivial. True scope: ~80-120 lines across 15+ files.

**Resolution**: Move #252 out of PR 5A into its own PR 5D. Keep PR 5A focused on the two critical bugs only.

### H2: PipelineExecutor missing drain() method

`runtime.py:219` calls `self._pipeline.drain()` in shutdown but catches AttributeError because the method doesn't exist. Graceful shutdown doesn't wait for in-flight pipelines.

**Resolution**: Add `drain()` to PR 5B alongside cache control methods.

### H3: #251 DataFlow(database_url=None) already accepted at construction

`core/engine.py:74-77` — database_url is already Optional[str] = None. Only fails when DB operations attempted. Implementer must track whether models are registered and skip DB init conditionally.

**Resolution**: Note in plan — fix is conditional skip, not constructor change.

### H4: PR 4C → PR 5A dependency is session-safe but fragile

PR 4C in Session 3, PR 5A in Session 1 — ordering is fine. But if PR 5A slips, PR 4C is blocked.

**Resolution**: Make explicit in session notes.

## MEDIUM

### M1: #245 batch handler also affected

`serving.py:262-276` has the same virtual product bug in the batch path. Fix must cover both single and batch handlers. Add ~10 lines to estimate.

### M2: #250 cross-package testing needed

Zero MCP references in fabric module. kailash-mcp must be importable for integration tests. Estimate reasonable but testing may need optional import guards.

### M3: source_adapter.py already outputs "source_type" key

At `source_adapter.py:412`, health check outputs `"source_type": self.database_type`. The output key is already correct — only the property name is wrong. This reinforces #252 as DX/cosmetic, not functional.

## NOTED

- No overlap between #242-#244 and #245-#252 confirmed
- Track 5 PR grouping sound (with #252 extracted)
- Existing fabric test coverage is minimal — test estimates are minimums
