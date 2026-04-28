---
priority: 0
scope: baseline
---

# Zero-Tolerance Rules

See `.claude/guides/rule-extracts/zero-tolerance.md` for extended BLOCKED-pattern examples and Phase 5 audit evidence.

## Scope

ALL sessions, ALL agents, ALL code, ALL phases. ABSOLUTE and NON-NEGOTIABLE.

## Rule 1: Pre-Existing Failures, Warnings, And Notices MUST Be Resolved Immediately

If you found it, you own it. Fix it in THIS run — do not report, log, or defer.

**Applies to** ("found it" includes, with equal weight):

- Test failures, build errors, type errors
- Compiler / linter warnings, deprecation notices
- WARN/ERROR in workspace logs since previous gate
- Runtime warnings (`DeprecationWarning`, `ResourceWarning`, `RuntimeWarning`)
- Peer-dependency / missing-module / version-resolution warnings

A warning is not "less broken" than an error. It is an error the framework chose to keep running through.

**Process:** diagnose root cause → fix → regression test → verify (`pytest` or project test cmd) → commit.

**BLOCKED responses:**

- "Pre-existing issue, not introduced in this session"
- "Outside the scope of this change"
- "Known issue for future resolution"
- "Reporting this for future attention"
- "Warning, non-fatal — proceeding"
- "Deprecation warning, will address later"
- "Notice only, not blocking"
- ANY acknowledgement/logging/documentation without an actual fix

**Why:** Deferring creates a ratchet — every session inherits more failures; codebase degrades faster than any single session can fix. Warnings are the leading indicator: today's `DeprecationWarning` is next quarter's "it stopped working when we upgraded".

**Mechanism:** The log-triage protocol in `rules/observability.md` Rule 5 has concrete scan commands. If `observability.md` isn't loaded (config-file edits), MUST still scan most recent test runner + build output for WARN+ entries before reporting any gate complete.

**Exceptions:** User explicitly says "skip this"; OR upstream third-party deprecation unresolvable in this session → pinned version + documented reason OR upstream issue link OR todo with explicit owner. Silent dismissal still BLOCKED.

### Rule 1a: Scanner-Surface Symmetry

Findings reported by a security scanner on a PR scan MUST be treated identically to findings on a main scan. "This also exists on main, therefore not introduced here" is BLOCKED.

```python
# DO — fix the finding in this PR regardless of main's state
logger.info("redis.connect", url=mask_url(redis_url))
# DO NOT — "same alert on main, out of scope"
logger.info("redis.connect", url=redis_url)  # still leaks
```

**BLOCKED responses:** "Pre-existing on main, out of scope" / "CodeQL only flags PR diffs" / "Will be addressed when main re-scans" / "Same alert ID upstream" / "Main branch baseline suppresses it".

**Why:** "Same on main" is the institutional ratchet that defers fixes forever. Rule 1 covers this in spirit; an explicit scanner-surface clause closes the rationalization gap. See guide for `__all__` / `__getattr__` second-instance variant (PR #506).

### Rule 1b: Scanner Deferral Requires Tracking Issue + Runtime-Safety Proof

Rule 1a mandates that scanner findings MUST be fixed, not dismissed. A LEGITIMATE deferral disposition exists for findings that are provably runtime-safe AND require architectural refactor out of release-scope — but ONLY if all four conditions are met. Missing any one of them, the "deferral" IS silent dismissal under a different name and is BLOCKED.

Required conditions (ALL four):

1. **Runtime-safety proof** — the finding is verified safe (e.g., every cyclic import is `TYPE_CHECKING`-guarded; the "unsafe" path is unreachable at runtime). Verification is a PR comment citing the guard lines.
2. **Tracking issue** — filed against the repo with title `codeql: defer <rule-id> — <short-context>`, body including acceptance criteria for the full fix.
3. **Release PR body link** — the tracking issue is linked from the release PR's body with explicit "deferred, safe per #<issue>" language.
4. **Release-specialist agreement** — release-specialist confirms the deferral in review OR user explicitly overrides with "full fix".

```markdown
# DO — release PR body documents the deferred findings

## CodeQL findings

- 23 fixed directly (wrong-arguments, undefined-export, uninitialized-locals, warnings)
- 17 deferred (py/unsafe-cyclic-import) — all TYPE_CHECKING-guarded per #612;
  release-specialist approved deferral.

# DO NOT — dismiss without any of the four conditions

## CodeQL findings

- Some deferred (pre-existing, not my concern)
```

**BLOCKED rationalizations:**

- "The finding is obviously safe, we don't need a tracking issue"
- "Release-specialist didn't flag it, that's implicit approval"
- "We'll file the issue after merge"
- "The PR body is the tracking record; a separate issue is bureaucracy"
- "Verified by reading the code counts as the runtime-safety proof without writing it down"

**Why:** Without written runtime-safety proof + tracking issue + release PR link + release-specialist signoff, a "deferred" finding is indistinguishable from a silent dismissal — nothing forces the follow-up and nothing surfaces the backlog. The four conditions are the structural defense: verification is the grep-able claim; the tracking issue is the workstream; the release PR link is the audit trail; the release-specialist signoff is the human gate. Rule 1a blocks dismissal; Rule 1b documents the ONLY legitimate path to defer.

Origin: PR #611 release cycle (2026-04-23) — 17 `py/unsafe-cyclic-import` findings deferred via issue #612 after ml-specialist verified all cycles are TYPE_CHECKING-guarded; 23 other CodeQL errors fixed in the release PR.

## Rule 2: No Stubs, Placeholders, Or Deferred Implementation

Production code MUST NOT contain:

- `TODO`, `FIXME`, `HACK`, `STUB`, `XXX` markers
- `raise NotImplementedError`
- `pass # placeholder`, empty function bodies
- `return None # not implemented`

**No simulated/fake data:** `simulated_data`, `fake_response`, `dummy_value`, hardcoded mock responses, placeholder dicts. **Frontend mock is a stub too:** `MOCK_*`, `FAKE_*`, `DUMMY_*`, `SAMPLE_*` constants; `generate*()` / `mock*()` producing synthetic display data; `Math.random()` for UI.

**Why:** Frontend mock data is invisible to Python detection but has the same effect — users see fake data presented as real.

**Extended BLOCKED patterns** (Phase 5 audit + kailash-ml-audit W33b) — see guide for full code examples:

- **Fake encryption** — class stores `encryption_key` but `set()` writes plaintext. Audit trail shows "encrypted"; disk shows plaintext.
- **Fake transaction** — `@contextmanager` named `transaction` that commits after every statement (no BEGIN/COMMIT/rollback).
- **Fake health** — `/health` returns 200 without probing DB/Redis. Orchestrators make routing decisions on lies.
- **Fake classification / redaction** — `@classify(REDACT)` stored but never enforced on read. Documented security control ships as no-op.
- **Fake tenant isolation** — `multi_tenant=True` flag with cache key missing `tenant_id` dimension.
- **Fake integration via missing handoff field** — frozen dataclass on pipeline's critical path omits the field the NEXT primitive needs. Each primitive's unit tests pass (each constructs its own fixture); the advertised 3-line pipeline breaks on every fresh install. Fix: add missing field; populate at every return site; add Tier-2 E2E regression (see `rules/testing.md` § End-to-End Pipeline Regression). Evidence: kailash-ml W33b `TrainingResult(frozen=True)` without `trainable`; `km.register` raised `ValueError` on fresh install.
- **Fake metrics** — silent no-op counters because `prometheus_client` missing + no startup warning. Dashboards empty while operators believe they're reporting.

## Rule 3: No Silent Fallbacks Or Error Hiding

- `except: pass` (bare except + pass) — BLOCKED
- `catch(e) {}` (empty catch) — BLOCKED
- `except Exception: return None` without logging — BLOCKED

**Why:** Silent error swallowing hides bugs until they cascade into data corruption or production outages with no stack trace to diagnose.

**Acceptable:** `except: pass` in hooks/cleanup where failure is expected.

### Rule 3a: Typed Delegate Guards For None Backing Objects

Any delegate method forwarding to a lazily-assigned backing object MUST guard with a typed error before access. Allowing `AttributeError` to propagate from `None.method()` is BLOCKED.

```python
# DO — typed guard with actionable message
class JWTMiddleware:
    def _require_validator(self) -> JWTValidator:
        if self._validator is None:
            raise RuntimeError(
                "JWTMiddleware._validator is None — construct via __init__ or "
                "assign mw._validator = JWTValidator(mw.config) in test setup"
            )
        return self._validator

# DO NOT — raw delegation, opaque AttributeError
class JWTMiddleware:
    def create_access_token(self, *a, **kw):
        return self._validator.create_access_token(*a, **kw)
        # AttributeError: 'NoneType' object has no attribute 'create_access_token'
```

**Why:** Opaque `AttributeError` blocks N tests at once with no actionable message; typed guard turns the failure into a one-line fix instruction.

## Rule 4: No Workarounds For Core SDK Issues

This is a BUILD repo. You have the source. Fix bugs directly.

**Why:** Workarounds create parallel implementations that diverge from the SDK, doubling maintenance cost and masking the root bug.

**BLOCKED:** Naive re-implementations, post-processing, downgrading.

## Rule 5: Version Consistency On Release

ALL version locations updated atomically:

1. `pyproject.toml` → `version = "X.Y.Z"`
2. `src/{package}/__init__.py` → `__version__ = "X.Y.Z"`

**Why:** Split version states cause `pip install kailash==X.Y.Z` to install a package whose `__version__` reports a different number, breaking version-gated logic.

## Rule 6: Implement Fully

- ALL methods, not just the happy path
- If endpoint exists, it returns real data
- If service is referenced, it is functional
- Never leave "will implement later" comments
- If you cannot implement: ask the user what it should do, then do it. If user says "remove it," delete the function.

**Test files excluded:** `test_*`, `*_test.*`, `*.test.*`, `*.spec.*`, `__tests__/`

**Why:** Half-implemented features present working UI with broken backend — users trust outputs that are silently incomplete or wrong.

**Iterative TODOs:** Permitted when actively tracked (workspace todos, issue-linked).

Origin: `workspaces/arbor-upstream-fixes/.session-notes` (2026-04-12) + DataFlow 2.0 Phase 5 audit + kailash-ml-audit 2026-04-23 W33b. See guide for full BLOCKED-pattern code examples + audit evidence.
