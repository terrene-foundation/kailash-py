# No Stubs, TODOs, or Simulated Data

## Scope

These rules apply to ALL production code (non-test files).

## MUST NOT Rules

### 1. No Stubs or Placeholders

Production code MUST NOT contain:

- `TODO`, `FIXME`, `HACK`, `STUB`, `XXX` markers
- `raise NotImplementedError` (implement the method)
- `pass # placeholder` or `pass # stub`
- `return None # not implemented`
- Empty function/method bodies that should have logic

### 2. No Simulated or Fake Data

Production code MUST NOT contain:

- `simulated_data`, `fake_response`, `dummy_value`
- Hardcoded mock responses pretending to be real API calls
- `return {"status": "ok"}` as a placeholder for real logic
- Test fixtures masquerading as production defaults

### 3. No Silent Fallbacks

Production code MUST NOT silently swallow errors:

- `except: pass` (bare except with pass)
- `catch(e) {}` (empty catch block)
- `except Exception: return None` without logging

**Acceptable**: `except: pass` in hooks/cleanup code where failure is expected.

### 4. No Deferred Implementation

When implementing a feature:

- Implement ALL methods fully, not just the happy path
- If an endpoint exists, it must return real data
- If a service is referenced, it must be functional
- Never leave "will implement later" comments

## Enforcement

- **PostToolUse hook**: `validate-workflow.js` detects stub patterns on every file write
- **UserPromptSubmit hook**: Reminds agent of no-stubs policy every turn
- **Red-team agents**: Scan for violations during validation rounds

## Why This Matters

Stubs and TODOs accumulate silently. Each one is a hidden failure point:

- Users encounter `NotImplementedError` in production
- Silent fallbacks mask real bugs
- Simulated data gives false confidence in demos
- TODOs never get done without active tracking

## Exceptions

Test files (`test_*`, `*_test.*`, `*.test.*`, `*.spec.*`, `__tests__/`) are excluded.
Stub exceptions require:

1. Explicit user approval ("skip this for now")
2. A tracked TODO with timeline for completion
