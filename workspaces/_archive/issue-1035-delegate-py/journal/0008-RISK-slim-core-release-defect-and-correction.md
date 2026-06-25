---
type: RISK
status: promoted
source_commit: d5e02209469626124fe96b4b62a919fbab2426de
session: 2026-05-24/25 (/autonomize + /redteam-to-convergence + /release)
---

# RISK — `/redteam` convergence + slim-core release defect (2.26.0 → 2.26.1)

## Convergence arc (#1035 delegate substrate)

Round 1 (3 parallel agents): 6 CRITICAL + 5 HIGH. Fix-wave (3 parallel worktree
shards X/Y/Z): all CRIT/HIGH closed. Round 2 (closure-parity) + Round 3
(fresh-adversarial): 2 consecutive clean rounds = CONVERGED. Shipped via PR
#1164 + #1165 (R1 reconciliation). Durable receipt: `04-validate/08-convergence.md`.

## RISK — the release defect (the institutional lesson)

**What happened:** 2.26.0 published to PyPI with `kailash.delegate.verifier`
eager-importing `cryptography` at **module scope**. The delegate package is
inside the slim-core import closure, and `cryptography` lives in the
`[trust]`/`[server]` extras (NOT core deps). Result: `pip install kailash`
(bare) → `from kailash.delegate import ...` → `ModuleNotFoundError: cryptography`.
The documented #1035 import line was broken on every bare install.

**Why it slipped:**

1. Shard Y added `verifier.py` with a module-scope crypto import + a comment
   wrongly asserting "cryptography is a core kailash dependency." It is not.
2. PR #1165 (parallel session) MOVED the import to module scope specifically
   to fix a Pyright "InvalidSignature possibly unbound" warning — trading the
   slim-core invariant for the lint fix, without noticing the trade.
3. **TestPyPI was skipped** (minor-release precedent + human approval). The
   defect would have surfaced pre-publish on a TestPyPI clean-venv install.
4. The build-repo-release Rule 2 clean-venv gate caught it — but POST-publish,
   so 2.26.0 was already immutable on PyPI.

**The fix (2.26.1):** lazy-import cryptography inside `Ed25519Verifier.__init__`
(loud `ModuleNotFoundError` at construction if the extra is absent — the
established "loud failure at call site" pattern; matches the #1154 lazy-`filelock`
precedent that defends slim-core). `NullVerifier` (default) needs no crypto.
Behavioral regression tests (`tests/regression/test_issue_1035_delegate_slim_core_import.py`,
subprocess + `sys.modules` introspection, not source-grep) pin the invariant.
2.26.0 yanked (maintainer web-UI action).

## Lessons for next session / /codify candidates

1. **The slim-core import closure is a defended invariant** (pyproject.toml
   dependencies comment + #1154). Any new module under `src/kailash/` that an
   eager `import kailash.<x>` reaches MUST NOT module-scope-import an extras-only
   third-party lib. `deployment.md` § "Eagerly-Imported Transitive Dependencies"
   already covers this — but the delegate slim-core closure is a SPECIFIC trap
   (delegate is eager-reachable yet crypto-needing).
2. **A Pyright "possibly-unbound" fix that moves an import to module scope can
   silently break slim-core.** The correct pattern: lazy-import at the top of
   the method (local-scope binding) OR cache on the instance in `__init__`.
3. **TestPyPI skip cost is real for slim-core/import-shape changes.** The
   minor-release TestPyPI-skip precedent is fine for behavior changes covered
   by the matrix, but a NEW eager-import in the slim-core closure is exactly
   the class TestPyPI's clean-venv install would catch pre-publish. Consider:
   "new module in slim-core closure" → do NOT skip TestPyPI.

## Tracked non-blocking follow-ups (from convergence)

M1 `_consumed` TOCTOU · M3 payload-depth container-subclass · M4 unsalted
`_tenant_id_hash` · M5 `advance_lifecycle` orphan (awaiting `Delegate.compose()`
composer) · L1-L3 · `verifier=None` opt-in advisory (future major: flip
fail-closed) · cross-impl byte-match deferred per `cross-sdk-inspection.md`
Rule 4 (pending rs Ed25519 library confirmation).
