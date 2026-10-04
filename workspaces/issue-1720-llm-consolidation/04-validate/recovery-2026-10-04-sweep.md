# CSQ16 recovery sweep — 2026-10-04

Original ten-part capture against dev `fc9b638c7157a79a011d9d9eaf1a763c1db4ea60`. The execution addendum below does not refresh that capture. The user-authorized objective remains lossless recovery, verified dev landing and removal of recovered CSQ16 worktrees. Main promotion is separate.

## Completion status

Two technical lanes are landed and reaped: dependency metadata (`8bd3308b5`) and scheduler/DLQ SQLite ownership (`f589e987f`). Their remote ancestry/patch-equivalence and private preservation receipts are recorded in the canonical ledger. Ledger and generated burndown are pushed through `fc9b638c7`. **Zero of the four frozen original-worktree obligations is complete.** All four remain in progress; technical repair commits do not count as completed originals.

The preservation recheck compared all 539 original file entries and four archive hashes with intake manifests: all matched. Those entries overlap across 202 unique paths. Original dirty counts remain 154, 86, 199 and 100. Core, storage, transport, trust, CI and ML recovery remains open.

## ETA to completion

At least three further autonomous cycles; upper bound remains unresolved. Basis: complete Core repair/review/landing, parallel remaining storage/transport/CI/ML recovery, then semantic reconciliation of every original path and lossless reaping. Adversarial review is still reproducing new completion-blocking paths, so focused test totals cannot establish a completion date.

## Prioritized immediate queue

Every recovery priority is anchored to the user's request to finish and clean the CSQ16 worktrees.

| Priority | Category and severity | Finding and implication | Disposition |
| --- | --- | --- | --- |
| Immediate | BUG / HIGH | Core callback ownership, masking, lifecycle and runtime finalization defects can lose controls, expose protected output or abandon resources. | Active disjoint repair lanes; two clean independent correctness/security rounds required before landing. |
| Parallel | BUG / HIGH | DataFlow cache identity/invalidation and transaction publication remain under the allocated second CLI; other original storage restrictions/schema/backend ownership shards remain open. | Preserve peer ownership, receive actual handoff evidence, verify and integrate. Branch activity is not delivery. |
| Parallel | BUG / HIGH | Transport, trust sinks, CI/MCP and ML original changes remain unlanded. | Continue bounded specialist-backed recovery after dependent Core surfaces stabilize. |
| Closure | BUG / HIGH | Deleting original dirty trees now would discard unreconciled material. | Keep all originals and prove each path represented by landed work or separately preserved evidence before removal. |
| Process | Audit finding / MED | Lexical production-marker hits include abstract methods, generated user templates, unsupported operations and optimization comments. A match does not establish a semantic stub. | Read representative hits; retain full captured hit list for semantic adjudication. No repo-wide stub-free claim. |

## Deferred-quality backlog

Fresh exact-label `deferred-quality` query returned no rows. No quality deferral was created. The general queue has 59 open issues, including CodeQL tracking issues without that label; an empty exact-label result does not erase those issues or prove all prior deferrals resolved. No issue was closed from this census.

## Decision points

No new authorization is needed for the reproduced recovery defects. Promotion PR #2229 remains open at stale head `4df93818243fec527590876c0022f6d1f8cacb5a` with CodeQL failure. Promoting would reduce the release gap but use stale review/CI evidence; retaining it preserves validation discipline while leaving the gap visible. Recommendation: complete authorized dev recovery and refresh promotion evidence separately. Do not merge the stale PR.

The broader 59-issue census is not an approval to implement every unrelated issue during this recovery. Its rows remain visible in the live issue tracker; this report does not claim they are closeable, all CSQ16-related, or semantically adjudicated from titles.

## Recommendation

Continue the active parallel repairs, collect delivered evidence, converge independent reviews, land valid work to dev, then remove only proven recovered task trees and branches. Keep the frozen chart population unchanged until whole-original obligations are actually complete.

## Ten-sweep evidence and limits

| Sweep | Fresh result | Interpretation |
| --- | --- | --- |
| 1 — todos | No active Markdown todo files matched. | Recovery obligations remain in the canonical ledger; this is not completion proof. |
| 2 — journal | No pending Markdown entries matched. | No promotion/discard action needed from this census. |
| 3 — issues | 59 open issues read with labels and bodies captured. | Current repository only; no automatic closure or stale-age dismissal. |
| 4 — PRs and refs | One open PR; 46 local/remote-tracking refs enumerated unfiltered. | First-parent main-to-dev gap 254; ordinary main/HEAD reachability divergence `0 422`. These are distinct measures. |
| 5 — specs | Trestle structural check: 85 specs, 160 extracted symbols, zero reported orphans/coverage gaps/stubs; exit 0. | Citation-shaped MUST-symbol/AST instrument only; excludes free-prose semantics and runtime/backend conformance. Known-present/known-absent controls remain in the intake controls artifact. |
| 6 — forest | 35 registrations, all KEEP; report-only, no deletions. No session notes older than 30 days. | Active and unlanded work preserved, including the unrelated temporary build tree. Aggregate forest-ledger ID inclusion passed; that does not establish status freshness. |
| 7 — process | Shared dev checkout clean; marker hits captured and inspected. | Generated migration/node templates and abstract APIs are distinguishable from callable production stubs. Remaining semantic questions are not passed by the lexical census. |
| 8 — release | Mechanically selected stable tag `v2.65.0`; 126 shippable-path commits since that tag. | Unreleased Core changes exist; no package publication/readiness claim. |
| 9 — ecosystem | Resolver absent in this declared BUILD repo. | Structural N/A; no other repository was read. |
| 10 — deferred quality | Exact-label query empty. | No new deferral; unlabeled issue history remains separate. |

<!-- sweep-redteam:v1:REPO-LEVEL specs_root=specs -->
<!-- sweep-redteam:v1:OK specs=85 symbols=160 orphans=0 coverage_gaps=0 stubs=0 -->
<!-- worktree-reap:v1:scope=all total=35 zero_loss=0 tag_first=0 keep=35 applied=false size_kb=11536180 size_unknown=0 free_kb=220493300 headroom_trees=1130 -->
<!-- sweep-ecosystem:v1:N/A reason=resolver-module-absent -->
<!-- unadjudicated-escalation:v1 threshold=3 runs=43 keys=0 escalations=0 suppressed=0 -->

Forest storage measured exactly 11,536,180 KiB, with 220,493,300 KiB free and no unknown/partial tree sizes. The estimated 1,130-tree headroom is free space divided by median linked-tree size, not a safe concurrency limit. The audit classified every registration KEEP at capture; it did not authorize deletion of currently active review trees.

Trestle reported tracked-but-ignored repository artifacts, matching the previously recorded disclosure of snapshot behavior. Long commands used automatic host arbitration with mirror/cache reaping disabled. No passing result is attributed to queued, interrupted, import-failed or missing-path test attempts.


## Execution addendum — later 2026-10-04 checkpoint

**Completion is unchanged:** dependencies and scheduler/DLQ are the only landed/reaped technical lanes. All original-worktree obligations remain in progress. The latest Core integration is `e790470eb`, while the most recent 95-file union (`3424 passed, 3 skipped`) ran at the earlier `f82e205e7` snapshot. It cannot clear the newer integrations. The [canonical ledger](../02-plans/csq16-recovery-ledger-2026-10-02.md#latest-integration-and-preservation-checkpoint--2026-10-04) records each scoped positive/negative receipt and review boundary.

**ETA:** a minimum of three further autonomous cycles remains a planning lower bound, not a delivery promise: finish active repairs and fresh independent reviews, verify and land the combined candidates, then reconcile original paths and reap safely. Newly reproduced ownership and error-ordering failures keep the upper bound unresolved.

**Immediate queue:** finish SQL owner-phase and first-error ordering repairs; independently review audit persistence and preserve the bounded Local chronology verdict; complete independent review of SQL policy retry/batch changes (120 passes on each interpreter; 58 failures/24 passes on preceding methods; a separate public batch-gate mutation is still running). In parallel, the peer's committed typed callers `92f0b4790` await transaction prerequisites and combined checks; the Express allocation has queue acceptance under receipt `01a10726`, with recipient acknowledgement and delivery pending. Native-awaitable `09c1628f4` has two clean correctness and two distinct security rounds only for its bounded surface. Local chronology `805e45825` separately has two clean correctness and two source-only security rounds; these do not cover root audit `d214d030c`.

**Deferred quality:** no new deferral is recorded. The original exact-label query and 59-issue census were not rerun for this addendum; neither is represented as a fresh tracker observation.

**Preservation:** the supplied later capture reports all original file/archive hashes unchanged (539 overlapping entries; 202 established unique paths). Its report-only forest has 52 KEEP registrations at the older Core `18eb6c636` capture, not a new current total. [Portable capture receipt](csq16-checkpoint-capture-2026-10-04.json) preserves that distinction. No deletion is authorized by the capture.

**Decision and recommendation:** no new permission is needed for these authorized bounded repairs. Continue disjoint work and corrected-source verification, then land valid work before any reap. This preserves recoverability while leaving the cleanup backlog visible. Keep main promotion separate and do not substitute focused test totals for whole-original acceptance.

The next isolated candidate is `04b432a63`; a 106-file union is in progress. SQL policy review is now scoped clean after the reached public-batch-gate control (three failures/one unaffected pass). Local error-classification repair and an additional SQL owner-phase review remain active, so the broader Core gate is still open. This continuation changes no original acceptance counts.
