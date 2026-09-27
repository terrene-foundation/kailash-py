# Specification-check advisory scope decision

Status: approved by the user on 2026-09-27.

User decision: “Approve separate spec-check cleanup; finish D1 (Recommended)”

This explicitly keeps the 173 documented specification-check advisories outside
D1. It waives no failing test, required CI check, or unresolved source-security
finding. The separate repair plan is `csq16-spec-check-cleanup-plan.md`.
Package publication remains excluded.

The all-files hook on candidate `a35604592eac70584f35acffd23d9ddc4ff615b3`
exited zero but emitted 173 specification-check warnings. This is separate from
Python test warnings and from the already approved advisory type backlog (#73).
The exact records are preserved in `csq15-spec-advisory-records.json`.

| Warning class | Messages | Observed meaning |
| --- | ---: | --- |
| Expired baseline entries | 111 | Still match current checker findings; refreshing the baseline removes only five other resolved entries and clears none of these warnings. |
| No scanned sections | 55 | Existing domain headings do not match the checker's section allowlist; includes navigation-only documents. This is a coverage limitation, not proof that their code is wrong. |
| Lazy export resolution | 7 | The checker compares public aliases with defining modules. Inspected spec citations describe valid public aliases, including an explicit alias-identity assertion. |

The 111 active baseline rows comprise 43 test-path findings, 32 class findings,
24 workspace-citation findings, six method findings, five error-class findings,
and one field finding. These are checker categories, not 111 proven SDK defects.
Examples requiring instrument repair include existing gate error classes omitted
from its configured source roots and environment-variable names treated as class
names. Missing test-path rows need individual source/test reconciliation.

Evidence: `scripts/spec_drift_gate.py:1396-1424` excludes resolved baseline entries
before computing expiry warnings; `scripts/spec_drift_gate.py:2367-2399` compares
lazy-map destinations with cited package paths; `scripts/spec_drift_gate.py:2511-2526`
emits uncovered-section and expiry warnings. The public alias assertion at
`specs/ml-automl.md:583` explicitly compares the two valid import paths.

## Approved boundary

Complete D1 using its existing required-check and failing-test gates, with this
specification-check backlog tracked as a separate repair plan. The user explicitly granted the
exception to the repository zero-tolerance warning rule. It leaves the documented specification-verification gaps open after promotion; it
does not waive any failing test, required CI check, or unresolved source-security
finding. No package publication is included.

The separate plan must repair checker false positives with opposing controls,
reconcile each remaining baseline row against real source/tests, and define
honest coverage for domain-oriented and navigation-only specifications. It must
not suppress all warnings, extend expiry dates, fabricate missing tests, or weaken
SDK behavior to match a diagnostic. Framework-specific changes require their
specialists and a sharded plan within the normal approval boundary.

The alternative considered was resolving this complete specification-check backlog
before D1. That would expand the promotion repair scope across multiple frameworks and the checker;
it needs the same sharded plan and verification, rather than an expiry-date reset.

This is a new, explicit exception separate from the existing #73 type exception.
