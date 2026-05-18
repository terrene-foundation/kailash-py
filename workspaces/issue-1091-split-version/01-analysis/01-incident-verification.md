# Issue #1091 — Verification of the "kailash 2.22.0 PyPI≠source" Incident

/ analyze, 2026-05-18. Acceptance criterion 1 of #1091: "verify the 2.22.0
PyPI≠source incident — the `.session-notes` claim is the lead, not yet
independently confirmed; confirm the actual mismatch before authoring the
rule."

## Verdict: the incident does NOT reproduce. No split-version mismatch exists.

## Evidence (live runtime checks, not documentation)

| Surface                                       | Check                                               | Result                                                             |
| --------------------------------------------- | --------------------------------------------------- | ------------------------------------------------------------------ |
| Git tag `v2.22.0` → `src/kailash/__init__.py` | `git show v2.22.0:...`                              | `__version__ = "2.22.0"`                                           |
| Git tag `v2.22.0` → `pyproject.toml`          | `git show v2.22.0:...`                              | `version = "2.22.0"`                                               |
| PyPI `kailash==2.22.0` wheel — dist metadata  | `importlib.metadata.version` in clean venv          | `2.22.0`                                                           |
| PyPI `kailash==2.22.0` — runtime import       | `import kailash; kailash.__version__` in clean venv | `'2.22.0'`                                                         |
| `2.22.1` release commit `abaea66a3`           | `git show`                                          | bumped `__init__.py` AND `pyproject.toml` atomically in one commit |
| `v2.22.0..v2.22.1` history                    | `git log --oneline`                                 | no version-anchor-only commit; no mid-release split state          |

Every kailash version anchor for 2.22.0 and 2.22.1 — git tag, source
`__init__.py`, `pyproject.toml`, PyPI wheel metadata, and the installed
package's runtime `__version__` — is consistent. There is no PyPI-vs-source
mismatch.

## What 2.22.1 actually was

`abaea66a3` "release: kailash 2.22.0 → 2.22.1 + kailash-dataflow 2.9.18 →
2.9.19" was a normal patch release carrying the #1083 follow-up
(`TransactionScope.execute_raw` write-protection, commit `ea2d9ad84`). Not a
version-mismatch fix. The prior session's `.session-notes` "split-version
trap LIVE" line was a lead that does not survive verification — exactly the
contingency #1091's own acceptance criterion 1 anticipated.

## Disposition (per verify-resource-existence.md MUST-3)

The existence check returns NEGATIVE. The rule #1091 proposed (post-publish
PyPI-vs-source `__version__` verification for every release) targets an
incident that does not exist.

Residual hypothetical: `deployment.md` § TestPyPI Validation runs a
post-install `__version__` check only for TestPyPI on major/minor releases —
production PyPI and patch releases have no post-publish version check. This
is a defense-in-depth gap, but no incident proves it ever bit anyone, and
`zero-tolerance.md` Rule 5 already mandates atomic version-anchor updates
(which `abaea66a3` demonstrably honored).

Authoring a new rule with a disproven Origin violates `rule-authoring.md`
Rule 6 (Origin must cite a real motivating incident) and `spec-accuracy.md`
(no phantom citations). Recommendation: close #1091 — motivating evidence
disproven; existing coverage (zero-tolerance Rule 5 + the TestPyPI check)
adequately spans the space. User gate required per `value-prioritization.md`
MUST-4 (#1091 carries a user-directed value-anchor).
