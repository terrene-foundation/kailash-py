# PROPOSAL — Slim-Core Eager-Import Discipline (delegate verifier defect)

| Field             | Value                                                                                                                                                                                     |
| ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| proposal-id       | `kailash-py/2026-05-25/slim-core-eager-import`                                                                                                                                            |
| target-rule       | `rules/deployment.md` § "Eagerly-Imported Transitive Dependencies"                                                                                                                        |
| target-repo       | `loom/` (Gate-1 ingest → distributes to USE templates via `/sync`)                                                                                                                        |
| origin-journal    | `workspaces/issue-1035-delegate-py/journal/0008-RISK-slim-core-release-defect-and-correction.md`                                                                                          |
| origin-PRs        | #1165 (introduced module-scope `from cryptography.exceptions import InvalidSignature` to silence Pyright); #1167 (lazy crypto import + regression test); releases 2.26.0 → 2.26.1 (patch) |
| originating-issue | #1035 (Delegate substrate; the verifier module is the C1 cryptographic gate that closed the "fake encryption" Round-1 finding)                                                            |
| date              | 2026-05-25                                                                                                                                                                                |
| posture-status    | L5_DELEGATED (per `rules/trust-posture.md`; this proposal is a Gate-1-ready PROPOSAL authored in kailash-py — loom-side edit happens at `/sync` review, NOT in this workspace)            |
| authoring-scope   | kailash-py workspace ONLY — this proposal does NOT edit `loom/.claude/rules/deployment.md`; loom is the splitter that ingests this proposal at Gate-1 and rule edit happens there         |

---

## Summary

PR #1165 (parallel session) moved `from cryptography.exceptions import InvalidSignature` to **module scope** in `src/kailash/delegate/verifier.py` to silence a Pyright `reportPossiblyUnbound` warning on the `InvalidSignature` catch handler inside `Ed25519Verifier.verify`. The delegate package (`kailash.delegate.*`) is **inside the slim-core import closure** — every `from kailash.delegate import …` triggers it at load time. The `cryptography` library is **not a core dependency**; it lives in the `[trust]` and `[server]` extras. Result: 2.26.0 shipped to PyPI with `from kailash.delegate import Ed25519Verifier` (and every transitive import path through `kailash.delegate`) raising `ModuleNotFoundError: No module named 'cryptography'` on bare `pip install kailash`.

The TestPyPI-skip precedent for minor releases let the defect reach PyPI without a clean-venv install ever being performed. 2.26.1 corrected via:

- **Lazy crypto import inside `Ed25519Verifier.__init__`** (`src/kailash/delegate/verifier.py:182-218`) — loud `ModuleNotFoundError` at construction time if the extra is absent; resolved symbols cached on the instance (`self._Ed25519PublicKey`, `self._InvalidSignature`) so `verify()` keeps its NEVER-raises contract; `NullVerifier` (the default) never constructs `Ed25519Verifier`, so slim-core callers never hit the import.
- **Regression test** at `tests/regression/test_issue_1035_delegate_slim_core_import.py` — pins the invariant that `from kailash.delegate import …` succeeds on a venv with no `cryptography` installed.

Two related failure modes were exercised by this incident:

1. The lint-fix path silently widened the slim-core import closure (FM-1).
2. The release-cadence gate (minor releases skip TestPyPI) silently bypassed the only check that would have caught FM-1 (FM-2).

This proposal codifies one MUST clause for each into `loom/.claude/rules/deployment.md` § "Eagerly-Imported Transitive Dependencies", so every downstream BUILD repo inherits the discipline at next `/sync`.

---

## Proposed Clause 1 — Pyright Unbound-Name Fix Discipline

### Clause text (proposed insertion into `rules/deployment.md`)

> A Pyright `reportPossiblyUnbound` / `reportUnboundVariable` fix MUST NOT move an extras-only import to module scope when the containing module is inside the slim-core import closure (any module reachable from `from <package> import …` on bare install — for kailash-py, this includes `kailash.delegate.*`, `kailash.trust.*` core paths, `kailash.runtime.*`, and every other module whose package `__init__.py` does not gate the import behind `try/except ImportError` or a `__getattr__` lazy hook).
>
> Acceptable resolutions, in order of preference:
>
> 1. **Lazy-import at top of the method body** — local binding shadows the unbound warning AND the import happens only when the code path runs. Cheapest fix; preferred when the method runs at most once per call site or once per long-lived object.
> 2. **Cache the imported symbol on the instance in `__init__`** — loud `ModuleNotFoundError` at construction time if the extra is absent; resolved symbols cached on `self` for hot-path methods that need to honor a NEVER-raises contract (e.g. `Verifier.verify()` in `src/kailash/delegate/verifier.py`). The cache pattern is the canonical lazy-import shape for stateful classes inside the slim-core closure.
> 3. **`if TYPE_CHECKING:` guard** — if the import is type-only (used solely in annotations / `cast()` targets / Protocol bounds), the `from __future__ import annotations` + `if TYPE_CHECKING:` block satisfies Pyright without any runtime binding.
>
> **BLOCKED rationalizations:**
>
> - "The lint fix is trivial — one line moved up"
> - "`cryptography` is a common dep; almost every user has it"
> - "The module docstring says it's core"
> - "The extra is declared in `[trust]` and `[server]`, and most installs pull one of them"
> - "The Pyright warning was a false positive; moving the import is the cleanest silence"
> - "Module-scope is more Pythonic / standard-library-ish than lazy-import"
> - "The CI matrix runs against the dev venv with all extras; we'd notice"
> - "We can revert if PyPI users complain"

### DO / DO NOT

```python
# DO — cache on instance in __init__ (canonical pattern for stateful classes in slim-core closure)
# src/kailash/delegate/verifier.py::Ed25519Verifier.__init__ — lines 182-218 of the 2.26.1 fix:
class Ed25519Verifier:
    def __init__(self, directory: "PrincipalDirectory") -> None:
        from kailash.delegate.types import PrincipalDirectory
        if not isinstance(directory, PrincipalDirectory):
            raise TypeError(...)
        # Lazy cryptography import — LOUD failure at construction if the
        # [trust]/[server] extra is absent (slim-core invariant; bare
        # `pip install kailash` does not ship cryptography). Resolving the
        # symbols here (not at module scope) keeps `from kailash.delegate
        # import ...` working on slim-core, and caching them on the
        # instance lets verify() reference them while honouring its
        # NEVER-raises contract.
        try:
            from cryptography.exceptions import InvalidSignature
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                Ed25519PublicKey,
            )
        except ModuleNotFoundError as exc:  # pragma: no cover - extras-gated
            raise ModuleNotFoundError(
                "Ed25519Verifier requires the `cryptography` library, which "
                "ships in the kailash [trust] / [server] extras. Install via "
                "`pip install kailash[trust]` (or bind NullVerifier instead "
                "for the fail-closed default). Underlying error: " + str(exc)
            ) from exc
        self._directory = directory
        self._Ed25519PublicKey = Ed25519PublicKey
        self._InvalidSignature = InvalidSignature

    def verify(self, message, signature, signer_delegate_id) -> bool:
        # ... uses self._Ed25519PublicKey, self._InvalidSignature ...
        try:
            public_key = self._Ed25519PublicKey.from_public_bytes(pk_bytes)
            public_key.verify(bytes(signature), bytes(message))
            return True
        except self._InvalidSignature:
            return False
        except Exception:
            return False

# DO — lazy-import at top of method body (when no long-lived object holds the symbols)
def verify_one_off(message: bytes, signature: bytes, pubkey: bytes) -> bool:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from cryptography.exceptions import InvalidSignature
    try:
        Ed25519PublicKey.from_public_bytes(pubkey).verify(signature, message)
        return True
    except InvalidSignature:
        return False

# DO NOT — move the extras-only import to module scope to silence Pyright
# src/kailash/delegate/verifier.py — THE 2.26.0 DEFECT:
from cryptography.exceptions import InvalidSignature  # ← BLOCKED: slim-core module
# (every `from kailash.delegate import …` on bare `pip install kailash`
#  now raises `ModuleNotFoundError: No module named 'cryptography'`)

class Ed25519Verifier:
    def verify(self, message, signature, signer_delegate_id) -> bool:
        try:
            public_key.verify(signature, message)
            return True
        except InvalidSignature:  # Pyright happy; PyPI users broken
            return False
```

### Why (anchored at journal/0008)

The slim-core invariant is the **import boundary**, not the runtime call boundary. A module-scope import of an extras-only library inside the slim-core closure breaks `from <package> import …` on every bare-install user the moment the package's `__init__.py` is loaded — with **no runtime signal** until the user's first import attempt fails. The defect is invisible to:

- The lint fix that introduces it (Pyright is happy)
- Local dev (all extras installed in the workspace `.venv`)
- The integration test matrix (CI venvs install `[dev]` which transitively pulls `cryptography`)
- Code review (the line moves up by 10 lines, looks like a trivial style change)

It is **only** visible to (a) a clean-venv install with no extras (the regression test in PR #1167 + the TestPyPI gate in Clause 2 below), and (b) the first downstream user on a bare install. The lazy-import-with-cache pattern in `src/kailash/delegate/verifier.py::Ed25519Verifier.__init__` is the canonical structural fix: the import is deferred to the construction site of a class that, by design, is never constructed on slim-core (the `NullVerifier` default short-circuits before `Ed25519Verifier.__init__` runs). Slim-core callers never pay the import cost; extras-installed callers get a loud `ModuleNotFoundError` at construction time if the extra is somehow absent, NOT a silent runtime failure five call layers deep.

Sibling rule: this clause is the slim-core-closure-specific extension of `rules/dependencies.md` § "Declared = Imported" MUST Rule 3 (`__init__.py` Module-Scope Imports Honor The Manifest). That rule covers package-level cross-sibling proxy imports; this clause covers in-package extras-only imports that the package's OWN manifest declares as optional.

---

## Proposed Clause 2 — TestPyPI Gate For Slim-Core Import-Shape Changes

### Clause text (proposed insertion into `rules/deployment.md`)

> Any release whose diff adds a NEW eager-importable module under the slim-core import closure — OR changes an existing slim-core module's module-scope import set to add a new top-level `import` / `from X import Y` of a package declared in `[<extra>]` rather than core `dependencies` — MUST be published to TestPyPI first and verified via clean-venv install on the bare-extras matrix BEFORE the corresponding PyPI release.
>
> The clean-venv check MUST execute, at minimum:
>
> ```bash
> python -m venv /tmp/slim-core-check && /tmp/slim-core-check/bin/pip install \
>     -i https://test.pypi.org/simple/ \
>     --extra-index-url https://pypi.org/simple/ \
>     "kailash==<X.Y.Z>"
> /tmp/slim-core-check/bin/python -c "from kailash.delegate import *"
> /tmp/slim-core-check/bin/python -c "from kailash.trust import *"
> /tmp/slim-core-check/bin/python -c "from kailash.runtime import *"
> # ...one line per top-level slim-core import path the release touches
> ```
>
> The minor-release TestPyPI-skip precedent is reserved for **behavior-only changes covered by the integration matrix** (logic changes inside an already-importable module that the existing test suite exercises end-to-end). A new eager-importable module — OR a new module-scope extras-only import in an existing slim-core module — is **by definition** not covered by the integration matrix, because the integration matrix runs against the dev venv with all extras installed, where the import always succeeds.
>
> **BLOCKED rationalizations:**
>
> - "We changed imports but no new module landed" (a previously-conditional or in-method extras import moved to module scope IS a new eager-import in the slim-core closure — the import edge is what matters, not the file count)
> - "The CI matrix covers it" (the matrix runs with extras; clean-venv is the ONLY surface that catches this class)
> - "Minor releases historically skip TestPyPI" (the skip is for behavior-only diffs; an import-shape change voids the skip)
> - "The clean-venv check adds 15 minutes to the release cadence"
> - "We'll catch it in the next release if a user reports it" (silent breakage of `pip install kailash` is a Zero-Tolerance Rule 1 incident, not a deferral candidate)
> - "Pyright / mypy / pre-commit covers it" (none of them have a slim-core import closure model)
> - "The release was already cut; we can't re-do TestPyPI now"

### DO / DO NOT

```bash
# DO — release pre-flight that includes the slim-core clean-venv check
# 1. Build + upload to TestPyPI
python -m build && twine upload -r testpypi dist/kailash-2.26.0*

# 2. Clean-venv install from TestPyPI, no extras
python -m venv /tmp/slim-core-check
/tmp/slim-core-check/bin/pip install \
    -i https://test.pypi.org/simple/ \
    --extra-index-url https://pypi.org/simple/ \
    "kailash==2.26.0"

# 3. Probe every slim-core import path the diff touched
/tmp/slim-core-check/bin/python -c "from kailash.delegate import Ed25519Verifier, NullVerifier, Verifier"
# → expect: succeeds silently
# → if 2.26.0 had landed pre-fix: ModuleNotFoundError: No module named 'cryptography'

# 4. Only after exit-0 on all probes: publish to PyPI
twine upload dist/kailash-2.26.0*

# DO NOT — minor release shortcut that skips TestPyPI on import-shape change
# 2.26.0 actual release path (the defect):
python -m build && twine upload dist/kailash-2.26.0*
# (TestPyPI skipped per "minor release" precedent; the import-shape change
#  was treated as a behavior-only diff; defect reached PyPI; reverted in 2.26.1)
```

### Why (anchored at journal/0008)

The integration test matrix is structurally blind to slim-core import failures because the matrix venvs install `[dev]` (or any extras superset). The ONLY surface that exercises the bare-install import closure is a clean venv with zero extras. TestPyPI exists precisely to host this kind of pre-publish probe, and the minor-release-skip precedent was authored under an implicit assumption that minor releases don't change import shapes — an assumption the PR #1165 lint-fix path falsifies.

The 2.26.0 → 2.26.1 corrective cycle cost: one full release re-cut (version bump, CHANGELOG update, tag, release-PR), one cross-CLI synchronization (the patch had to land in every wheel matrix job), and one user-facing apology in the release notes. The TestPyPI probe in Clause 2 would have caught FM-1 in ~5 minutes, before the 2.26.0 tag existed. The clause is the structural defense that converts "we noticed import-shape changes when they happened" (institutional memory, drift-prone) into "the release gate refuses the publish until the clean-venv probe is green" (structural, drift-proof).

Sibling rule: this clause is the release-side extension of `rules/zero-tolerance.md` Rule 5 (Version Consistency On Release) — Rule 5 enforces atomic version-string updates; this clause enforces atomic slim-core-import-closure verification. Both are pre-publish structural gates; both are the kind of check that, when skipped, silently breaks `pip install <package>` for every downstream user until a hotfix lands.

---

## Trust Posture Wiring

- **Severity:** `halt-and-report` at `/release` gate. The release-specialist's pre-publish checklist MUST fail-closed when (a) the clean-venv probe is missing for a release touching the slim-core import closure, OR (b) a `grep` of the diff for `^from [^.]` / `^import [^.]` on files inside the slim-core closure surfaces a new top-level import of a package not declared in core `dependencies`.
- **Cumulative downgrade:** per `rules/trust-posture.md` MUST Rule 4 — each landing of either failure class (lint-fix-moved-extras-to-module-scope inside slim-core, OR import-shape-change-release without TestPyPI) counts as a same-class violation against the cumulative-5x-in-30-days emergency-downgrade math. Add `slim_core_eager_import_violation` to the emergency-trigger list (1× = drop 1 posture).
- **Grace period:** 14 days from the rule landing in `loom/.claude/rules/deployment.md` and distributing through `/sync` to kailash-py. The 14-day grace allows in-flight PRs that pre-date the rule to land without retroactive violation; any PR opened after the grace expires that introduces a same-class import is BLOCKED at gate-review.
- **Detection mechanism (two layers):**
  1. **release-specialist pre-publish clean-venv check** (Clause 2 gate) — the release-specialist agent runs the TestPyPI clean-venv probe enumerated in Clause 2's DO block for every release whose diff touches any module under the slim-core import closure. Exit-0 across all probes is required before `twine upload` to PyPI. This is the load-bearing structural gate.
  2. **Grep for module-scope extras imports in new-module diff** (Clause 1 gate) — mechanical sweep at PR review time, runnable in O(seconds):
     ```bash
     # Enumerate slim-core import closure modules touched by this diff
     git diff --name-only main...HEAD -- 'src/kailash/**/*.py' | while read f; do
       grep -HnE '^(from [a-z_]+|import [a-z_]+)' "$f" \
         | grep -vE '^[^:]+:[0-9]+:(from|import) (kailash|typing|__future__|os|sys|logging|warnings|functools|dataclasses|enum|inspect|json|hashlib|hmac|secrets|uuid|datetime|pathlib|collections|abc|asyncio|threading|contextlib|copy|re|io|time|math)\b'
     done | grep -vE 'cryptography|pydantic|fastapi|starlette|sqlalchemy|asyncpg|aiosqlite|redis|httpx'  # ← extras flagged
     ```
     A non-empty result on a file inside the slim-core closure is a Clause 1 violation. This is the secondary advisory gate; load-bearing detection is the release-specialist's clean-venv probe.
- **Receipt requirement:** `/release` SessionStart MUST require `[ack: slim-core-eager-import]` in the agent's first response IF `posture.json::pending_verification` includes this rule_id (set at land-time, cleared after grace).

---

## Cross-References

- **`rules/deployment.md` § "Eagerly-Imported Transitive Dependencies"** — the existing rule this proposal extends. The existing rule names the failure pattern (eager-imported transitive dependency breaks bare install); these clauses add the lint-fix path that introduces it (Clause 1) and the release-gate that catches it (Clause 2). The existing rule's prose stays; these clauses land as new MUST subsections inside the same section header.
- **`rules/zero-tolerance.md` Rule 4** (No Workarounds for Core SDK Issues) — this proposal is itself the application of Rule 4: rather than working around the Pyright warning by moving the import (the workaround that caused the defect), the fix attacks the root contract (slim-core invariant) and pins it with a regression test. The proposal codifies the discipline that prevents the workaround pattern from recurring.
- **`rules/dependencies.md` § "Declared = Imported"** MUST Rule 3 (`__init__.py` Module-Scope Imports Honor The Manifest) — sibling rule covering cross-sibling-package proxy imports inside `__init__.py`. This proposal extends the same structural defense to in-package extras-only imports inside the slim-core closure. The two rules together close the full "import that breaks on bare install" failure class: Rule 3 covers `from <sibling-package> import …` patterns; this proposal covers `from <extras-only-library> import …` patterns.
- **`tests/regression/test_issue_1035_delegate_slim_core_import.py`** — the live regression test pinning the invariant. The test imports `kailash.delegate` on a venv with no `cryptography` installed and asserts the import succeeds; if PR #1165's defect ever re-lands, this test fails immediately, BEFORE the release CI matrix reaches the clean-venv probe. Both Clause 1's lazy-import pattern AND Clause 2's TestPyPI gate are belt-and-suspenders defenses around this single load-bearing test. The test stays in `tests/regression/` (CI default path per `rules/refactor-invariants.md` Rule 2).
- **`src/kailash/delegate/verifier.py::Ed25519Verifier.__init__`** (lines 182-218 of the 2.26.1 fix) — the canonical implementation of Clause 1's "cache the imported symbol on the instance in `__init__`" resolution. Every future slim-core class that needs an extras-only library MUST follow this shape (try/except `ModuleNotFoundError` with a typed error message naming the install command + the fail-closed default, resolved symbols cached on `self`).

---

## Bootstrap-Circularity Disposition

This proposal targets `loom/.claude/rules/deployment.md`. Per `rules/self-referential-codify.md` MUST Rule 2 (positive allowlist of self-referential surfaces), the self-referential surface includes:

- Commands (`codify.md`, `sync.md`, `sync-to-build.md`, `redteam.md`, `sweep.md`, `wrapup.md`)
- Skills under `32-trust-posture/**`, `spec-compliance/**`, `command-authoring/**`, `skill-authoring/**`, `hook-authoring/**`, `sweep/**`
- Rules under a specific allowlist (`trust-posture`, `cc-artifacts`, `coc-sync-landing`, `artifact-flow`, `recommendation-quality`, `value-prioritization`, `autonomous-execution`, `agents`, `sweep-completeness`, `rule-authoring`, `variant-authoring`, `cross-cli-parity`, `specs-authority`, `spec-accuracy`, `probe-driven-verification`, `hook-output-discipline`, `verify-resource-existence`, `time-pressure-discipline`, `repo-scope-discipline`, `self-referential-codify`)
- Hooks under `.claude/hooks/lib/`
- Bin under `.claude/bin/`
- Audit fixtures under `.claude/audit-fixtures/`
- Management agents under `.claude/agents/management/`

`deployment.md` is **NOT** in the self-referential-codify allowlist. It governs SDK release discipline (the "B" side of the codify/release dual — release happens AFTER codify, and `deployment.md` is the rulebook for the release half). It does NOT govern codify-class behavior (proposal generation, rule authoring, allowlist maintenance, hook authoring, sync mechanics).

Therefore this proposal **does NOT trigger** the multi-agent redteam-with-tests gate that `self-referential-codify.md` MUST Rule 1 mandates for self-referential surfaces. Normal codify-discipline applies:

- `rules/cc-artifacts.md` Rule 6 (every `/codify` deploys cc-architect) — applies as the standard single-specialist proposal review at Gate-1.
- L5_DELEGATED posture default applies — per `.claude/skills/32-trust-posture/redteam-integration.md`, Round 1 is OPTIONAL at L5. The Gate-1 reviewer at loom may invoke the multi-agent team if the proposal's surface widens (e.g. if a co-owner directs the proposal to ALSO touch a self-referential-allowlist rule), but is NOT required to.

If the loom Gate-1 reviewer subsequently determines this proposal should ALSO carry a same-class clause for a self-referential-allowlist rule (e.g. extending `rules/autonomous-execution.md` § Per-Session Capacity Budget with a "release-time clean-venv probe is a structural gate, not a shardable budget" footnote), THAT extension would trigger the multi-agent gate — but the extension is out of scope for THIS proposal as authored.

---

## Provenance & Receipts

- **Originating brief:** the user directive in this session — "Author a codify-proposal markdown for the kailash-py slim-core eager-import lesson surfaced in `journal/0008-RISK-slim-core-release-defect-and-correction.md`".
- **Originating journal entry:** `workspaces/issue-1035-delegate-py/journal/0008-RISK-slim-core-release-defect-and-correction.md` (the full incident post-mortem; FM-1 + FM-2 enumeration; PR #1165 → #1167 chain; 2.26.0 → 2.26.1 release cycle).
- **Originating fix:** PR #1167 → commit landed 2.26.1 to PyPI. The fix's structural component is `src/kailash/delegate/verifier.py::Ed25519Verifier.__init__` lines 182-218 (lazy crypto import with instance-cached symbols); the regression component is `tests/regression/test_issue_1035_delegate_slim_core_import.py`.
- **Authoring date:** 2026-05-25.
- **Authoring scope:** kailash-py workspace ONLY. This proposal does NOT edit any `.py` file, any rule, any hook, any command. It is a Gate-1-ready PROPOSAL written into the workspace's `05-codify/` directory for the loom-side splitter to ingest at the next `/sync` cycle.
