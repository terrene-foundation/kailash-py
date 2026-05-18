---
type: DISCOVERY
date: 2026-05-18
created_at: 2026-05-18T00:00:00Z
author: agent
session_id: analyze-1091
session_turn: 1
project: issue-1091-split-version
topic: The kailash 2.22.0 PyPI-vs-source split-version incident does not reproduce
phase: analyze
tags:
  [
    analyze,
    deployment,
    version-consistency,
    verify-resource-existence,
    incident-disproven,
  ]
---

# DISCOVERY — the 2.22.0 "split-version trap" does not reproduce

## What was checked

Issue #1091 was filed (2026-05-18) to codify a `deployment.md` rule for
post-publish PyPI-vs-source `__version__` verification. Its motivating
evidence was a prior session's `.session-notes` line: "hit the split-version
trap LIVE (kailash 2.22.0 PyPI≠source)". #1091's acceptance criterion 1
explicitly flagged this as an unconfirmed lead.

`/analyze` ran the verification (see `01-analysis/01-incident-verification.md`).

## Finding

Every kailash 2.22.0 / 2.22.1 version anchor is consistent:

- git tag `v2.22.0` — `__init__.py` and `pyproject.toml` both `2.22.0`
- PyPI `kailash==2.22.0` — clean-venv `import kailash; __version__` → `'2.22.0'`; dist metadata → `2.22.0`
- `2.22.1` release commit `abaea66a3` bumped both anchors atomically

There is no PyPI-vs-source mismatch. The `.session-notes` lead did not
survive a live runtime check.

## Why this is the institutional lesson

This is a textbook `verify-resource-existence.md` MUST-2 case: a session-notes
claim (operator memory) described an INTENT/recollection, not runtime state.
The one-command live check (`pip install kailash==2.22.0` in a clean venv +
`import`) disproved it in under a minute. The codify candidate that would
have been authored on faith — a `deployment.md` rule with a fabricated Origin
— was blocked by running the existence check FIRST, exactly as #1091's own
acceptance criterion 1 mandated.

## Disposition

Per `verify-resource-existence.md` MUST-3 (existence check negative → default
is delete-or-stub, not provision) and `rule-authoring.md` Rule 6 (Origin must
cite a real incident): recommend closing #1091. The residual hypothetical
(no post-publish check on production PyPI / patch releases) is already spanned
by `zero-tolerance.md` Rule 5 + `deployment.md` § TestPyPI Validation. Closure
needs a user gate per `value-prioritization.md` MUST-4 — #1091 carries a
user-directed value-anchor.

## For Discussion

1. Counterfactual: if `/analyze` had skipped the clean-venv check and trusted
   the `.session-notes` lead, a `deployment.md` rule would have shipped with
   an Origin line citing an incident that never happened — how many other
   `.session-notes` "LIVE evidence" leads across the forest ledger are
   similarly unverified?
2. The prior session genuinely believed it hit a split-version trap. What did
   it actually observe — a transient working-tree state during 2.22.1 release
   prep (pyproject bumped, `__init__.py` not yet)? If so, that is normal
   release-prep mid-state, not an incident — should `/wrapup` distinguish
   "observed a transient" from "hit a bug" when writing evidence lines?
3. Is the residual gap (no post-publish `__version__` check on production
   PyPI patch releases) worth a rule on its own merits, or does authoring it
   without an incident violate the "don't design for hypotheticals" discipline?
