# DISCOVERY — Per-package CI path-gating hides pre-existing sibling-package failures until a workflow-touching PR

Date: 2026-07-23. Repo class: BUILD. Author: agent. Phase: codify.
relates_to: (none — process discovery)

## The discovery

A monorepo whose CI jobs are path-gated per sub-package (a kaizen-agents-only change runs only
the kaizen-agents job; the `Test kailash-kaizen` job runs only when kailash-kaizen paths change)
has a blind spot: a pre-existing DETERMINISTIC failure in package B is invisible to every PR that
touches only package A. It stays green-on-main-for-the-PR while being red-if-anyone-ran-it.

Concretely this session: the #1927 fix (kaizen-agents only) merged with 20 green checks — the
`Test kailash-kaizen` job never ran. A dependabot PR bumping a GitHub Action (`.github/workflows`
touched → the FULL matrix fired) then surfaced `test_verify_signatures_validates_delegations`
failing 1/6555 in kailash-kaizen. It had been red on main and NO recent PR's gated matrix ran it.

## Root cause of the sibling failure (a stale-test-from-security-hardening pattern)

The test built an un-subject-bound LEGACY `CapabilityAttestation` and expected `valid=True`.
Security hardening #1912 Wave 3 A1 (`operations/__init__.py::_verify_capability_signature`) later
made legacy caps fail-closed by default (they are transplantable across chains). The #1912 wave
migrated most tests but missed this one — it was authored pre-#1912 (last touched by the monorepo
move) and never re-derived. **The code was correct; the test was stale.** Fix: migrate the test to
a `v1-subject-bound` cap binding the holder chain's `genesis.agent_id`, exactly as the verify side
recomputes it — testing the SECURE path, not opting into `allow_unbound_legacy_capabilities`.

## The two generalizable lessons

1. **Security-hardening waves that flip a default MUST sweep the sibling package's tests, not just
   the home package's.** #1912 lived in `kailash` core / `kailash.trust`; the stale test lived in
   `kailash-kaizen`'s suite (it imports core). A same-package test sweep misses it. This is the
   cross-package instance of `orphan-detection.md` Rule 4 (API removal sweeps its tests) and
   `security.md` Enforcement-Surface Parity applied to the TEST surface.
2. **Path-gated CI needs a periodic full-matrix run** (nightly, or a merge-queue gate) so a
   pre-existing sibling failure surfaces without waiting for an incidental workflow-touching PR.
   Absent that, "green on every PR" and "green if you run the whole matrix" silently diverge.

## For Discussion

1. Is the right structural fix a scheduled nightly full-matrix run, a merge-queue that runs the
   union of affected + sibling jobs, or a `/redteam` lens that greps for cross-package test files
   (a package-B test importing package-A code) whenever package A ships a default-flip? Which has
   the best cost/coverage ratio for a 9-package monorepo?
2. Counterfactual: if CI were NOT path-gated (every PR ran the full matrix), the #1927 PR would
   have surfaced this failure — but at the cost of ~30min × every PR. Is the path-gating
   throughput win worth the hidden-sibling-failure risk, and does the answer change with the
   number of sub-packages?
3. The #1912 migration missed exactly ONE test out of a large suite. Is "a default-flip security
   wave MUST enumerate EVERY test that constructs the affected object across ALL packages" a
   codifiable mechanical sweep (grep the object's constructor across the monorepo), or is the miss
   irreducibly a coverage-completeness judgment?
