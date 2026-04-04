# Zero-Tolerance Rules

## Scope

ALL sessions, ALL agents, ALL code, ALL phases. ABSOLUTE and NON-NEGOTIABLE.

## Rule 1: Pre-Existing Failures MUST Be Resolved Immediately

If you found it, you own it. Fix it in THIS run — do not report, log, or defer.

1. Diagnose root cause
2. Implement the fix
3. Write a regression test
4. Verify with `pytest`
5. Include in current or dedicated commit

**BLOCKED responses:**

- "Pre-existing issue, not introduced in this session"
- "Outside the scope of this change"
- "Known issue for future resolution"
- "Reporting this for future attention"
- ANY acknowledgement, logging, or documentation without an actual fix

**Exception:** User explicitly says "skip this issue."

## Rule 2: No Stubs, Placeholders, or Deferred Implementation

Production code MUST NOT contain:

- `TODO`, `FIXME`, `HACK`, `STUB`, `XXX` markers
- `raise NotImplementedError`
- `pass # placeholder`, empty function bodies
- `return None # not implemented`

**No simulated/fake data:**

- `simulated_data`, `fake_response`, `dummy_value`
- Hardcoded mock responses pretending to be real API calls
- `return {"status": "ok"}` as placeholder for real logic

**Frontend mock data is a stub:**

- `MOCK_*`, `FAKE_*`, `DUMMY_*`, `SAMPLE_*` constants
- `generate*()` / `mock*()` functions producing synthetic data
- `Math.random()` used for display data

**Why:** Frontend mock data is invisible to Python detection but has the same effect — users see fake data presented as real.

## Rule 3: No Silent Fallbacks or Error Hiding

- `except: pass` (bare except with pass) — BLOCKED
- `catch(e) {}` (empty catch) — BLOCKED
- `except Exception: return None` without logging — BLOCKED

**Acceptable:** `except: pass` in hooks/cleanup where failure is expected.

## Rule 4: No Workarounds for Core SDK Issues

This is a BUILD repo. You have the source. Fix bugs directly.

**BLOCKED:** Naive re-implementations, post-processing, downgrading.

## Rule 5: Version Consistency on Release

ALL version locations updated atomically:

1. `pyproject.toml` → `version = "X.Y.Z"`
2. `src/{package}/__init__.py` → `__version__ = "X.Y.Z"`

## Rule 6: Implement Fully

- ALL methods, not just the happy path
- If an endpoint exists, it returns real data
- If a service is referenced, it is functional
- Never leave "will implement later" comments
- If you cannot implement: ask the user what it should do, then do it. If user says "remove it," delete the function.

**Test files excluded:** `test_*`, `*_test.*`, `*.test.*`, `*.spec.*`, `__tests__/`

**Iterative TODOs:** Permitted when actively tracked.
