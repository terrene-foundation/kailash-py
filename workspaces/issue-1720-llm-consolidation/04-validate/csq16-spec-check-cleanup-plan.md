# Separate specification-check cleanup plan

Status: tracked outside D1 by explicit user approval on 2026-09-27. This is the
cleanup scope and acceptance register; implementation is a separate workstream.

Approval: “Approve separate spec-check cleanup; finish D1 (Recommended)”.
The exception applies only to the 173 messages recorded in
`csq15-spec-advisory-records.json`. It does not waive failing tests, required CI,
unresolved source-security findings, or package-release prerequisites.

## Evidence and scope

Use `csq15-spec-drift-triage.json` for all classified rows and opposing controls.
There are 111 active expired baseline rows (97 distinct identities), five resolved
baseline entries, 55 section-coverage warnings, and seven public-alias warnings.
These are diagnostic findings; they are not 111 proven SDK defects.

| Shard | Work | Budget and verification |
| --- | --- | --- |
| Detector semantics | Distinguish public lazy exports from defining-module claims; classify non-class tokens and external references; include the existing gate error definitions; reconcile promised smoke sections. | At most 500 load-bearing lines, eight invariants, four call hops. Add actual contrary fixtures for every changed detector and retain wrong-module/absent-target failures. |
| Baseline reconciliation | Archive exactly five resolved entries through the documented refresh flow. Reconcile 43 test-path rows, 24 citation rows, two explicitly future rows, and six owned API rows against source and real tests. | Split by domain before implementation; each slice must stay within 15k relevant source lines and eight invariants. Existing assertions need semantic successors, not renamed empty files. |
| Coverage contract | Classify all 55 documents into domain assertions and navigation-only material; make scanning coverage explicit and consistent with spec authority. | Separate independent domain slices. No blanket warning downgrade or unsupported “fully scanned” claim. |
| Convergence | Run the full checker without stale grace, relevant real suites, and independent correctness/security review twice after fixes. | Report both coverage and findings; excluded surfaces remain explicit. |

## Acceptance register

- Every one of the 111 active baseline rows has an evidence-backed disposition.
- All seven public-alias cases are accepted for the right reason, while wrong
  qualified modules and absent targets still fail reached controls.
- Every document in the 55-row coverage inventory has an explicit scan contract.
- The five resolved baseline entries are archived without extending expiry dates.
- Source/spec claim corrections cite the actual source ranges; test-path repairs
  preserve behavior assertions. Missing implementation is fixed when confirmed.
- No blanket suppression, fabricated tests, silent skip, or SDK change made only
  to satisfy a misclassified diagnostic.
- Framework-specific work consults the relevant specialist with inline specs.
- Any slice exceeding the stated limits is sharded before implementation.

D1 may complete independently once its own test, security and exact-head CI gates
pass. Completing D1 does not close this cleanup plan.
