# CSQ16 recovery sweep — 2026-10-05

Ten-part capture against dev `816bfcef194bc226b23308b3a13046e9e8e74406`. This is a recovery checkpoint; subsequent worker commits and the two new allocations are identified separately below. User scope remains finish valid unlanded CSQ16 work, land to dev, and reap only after lossless semantic closure. Main promotion is separate.

## Completion status

Five bounded technical lanes are landed and their dedicated task trees/branches are reaped: dependency metadata `8bd3308b5`, scheduler/DLQ ownership `f589e987f`, shared Trestle hook host forwarding `b73042e33`, MCP coroutine compatibility `c7c19675c`, and retained-input ignore parity `6c9ec6d12`. Exact remote ancestry or patch-equivalence, clean worktree checks and private reap receipts support these task-level closures. The last lane's receipt is `reaped-tracked-ignore-receipt.json`; its 30 exact tracked-file exceptions had two correctness and two separate static-security passes plus normal hooks. Ledger/chart checkpoint `816bfcef1` is pushed.

**Zero of four original whole-worktree recovery obligations is complete.** Original dirty trees remain immutable inputs. Prior preservation evidence covers 539 overlapping entries across 202 unique paths; that hash capture was not repeated for this sweep. No fresh preservation equality is asserted here.

Core candidate `1a54a4ede` passed 4,617 cases with three PEP-649 version skips, before the current native admission, tracing and runtime-pool followups. The combined result is not evidence those later drafts are complete. No package release or main promotion occurred.

## ETA to completion

At least three further autonomous cycles, with an unresolved upper bound: finish Core and transaction/tracking producer repairs; verify remaining storage, transport, trust, CI and ML lanes; then reconcile every original path against landed content and reap. New independently reproduced callback, cancellation-order and storage-custody failures remain completion blockers, so focused pass counts do not establish a delivery date.

## Prioritized immediate queue

Every recovery row is anchored to the user's explicit instruction to finish and clean the CSQ16 worktrees.

| Priority | Category / severity | Finding and impact | Disposition |
| --- | --- | --- | --- |
| Immediate | BUG / HIGH | Native task admission, caller Context, nested entry, cross-loop cleanup and first-control publication require coordinated fixes. | Wrapper worker owns async runtime plus the already allocated minimal Local cleanup method; independent review remains open. |
| Immediate | BUG / HIGH | Runtime pool close ownership needs wrapper callback parity and fresh TTL eligibility; direct acquisition/validation unwind remains adjacent open work. | Root owns bounded pool repairs. Six ordinary before-fix cases failed; corrected 199/198-plus-one-skip cohort passed. Fresh independent review and direct-creation followup remain required. |
| Parallel | BUG / HIGH | Tracing callback discovery and restoration failures can lose original errors or leave installed wrappers without retry custody. | Tracing worker owns four files and focused tests; initial and followup commits remain isolated pending convergence. |
| Parallel | BUG / HIGH | Transaction completion consumers can report an unconfirmed or opposite result; tracking run replacement can delete child tasks. | Peer receives disjoint producer/storage shards with exact bases and method ownership. DataFlow consultation and independent review required. |
| Parallel | BUG / HIGH | Fabric cache-policy bypass, audit-store diagnostics, remaining storage/transport/trust/CI/ML original paths are unresolved. | Retain root queue and existing ownership. Do not infer closure from nearby repair commits. |
| Closure | BUG / HIGH | Unreconciled original material would be lost by premature deletion. | Keep originals; prove each obligation represented by landed work or explicit retained evidence before reaping. |
| Process | Audit finding / MED | Lexical production-marker hits include generated templates, abstract extension points and unsupported-operation branches. | Representative bodies inspected; lexical hits are not a repo-wide semantic stub verdict. Full hit capture retained privately. |

## Deferred-quality backlog

The live exact-label `deferred-quality` query returned zero rows. No new deferral was created. The broader live issue census contains 59 open issues, including separately labeled or unlabeled CodeQL tracking entries; zero exact-label rows do not prove all historical deferrals resolved. No issue was closed or dismissed by age.

## Decision points

No new authorization is needed for these in-envelope recovery defects or the user-requested compute policy. Both coordinators retain xhigh; new bounded mechanical children use medium, complex implementation/review children xhigh. Long execution uses Trestle on esperie-ai. Missing tooling must be installed once for all slots; no tooling installation was necessary in this capture. The filesystem-dependent forest audit ran through local Trestle because it must inspect actual local linked worktrees.

Promotion PR #2229 remains open at stale head `4df93818243fec527590876c0022f6d1f8cacb5a`; its live CodeQL check is FAILURE. The first-parent promotion gap is 266 commits, distinct from the ordinary reachability divergence of `0 434`. Promotion would reduce divergence but stale checks do not validate the current recovery candidate. Recommendation: preserve the authorized dev recovery scope and refresh promotion evidence separately; do not merge this stale PR.

The 59-issue census is visibility, not a new authorization to implement every unrelated issue. No correctness review is substituted for security review, and all current security verdicts remain static-only where specified.

## Recommendation

Continue the active disjoint repairs and peer work, collect actual delivered results, converge reviews, land verified candidates, and then reap proven task trees. Keep the original acceptance chart at zero completed until whole-original obligations are met. Existing user authorization covers that sequence; no new gate is introduced by this report.

## Ten-sweep evidence and limits

| Sweep | Fresh result | Scope and interpretation |
| --- | --- | --- |
| 1 — todos | No active Markdown todo files matched. | Recovery obligations remain in the canonical ledger; not completion proof. |
| 2 — journal | No pending Markdown entries matched. | No promotion/discard action from this census. |
| 3 — issues | 59 open issues captured with bodies and labels; titles/labels read. | Current repository only; no title-only closeability claims. |
| 4 — PRs and refs | One open PR; 70 local/remote-tracking refs enumerated unfiltered. | Read the actual branch rows, including the four original d1 branches, peer branches and root integration branches. Reachability alone never authorizes deletion. |
| 5 — specs | Trestle check: 85 specs, 160 extracted symbols, zero reported orphans/coverage gaps/stubs, exit 0. | Citation-shaped MUST-symbol/AST instrument only. Paired current controls produced present-symbol exit 0 and missing-symbol orphan/exit 1. Excludes free-prose semantics, runtime behavior and actual backend conformance. |
| 6 — forest | 69 registrations, all KEEP; report-only, no audit deletions. | Measured before the two later root-created peer allocations. No stale session notes over 30 days. Forest ledger aggregation reports all open workspace IDs represented at root; not status-freshness proof. |
| 7 — process | Shared dev checkout clean; source marker hits captured and representative bodies read. | No repo-wide stub-free claim; abstract store methods and generated migration bodies are distinguished from callable stubs. |
| 8 — release | Mechanically selected stable tag `v2.65.0`; 126 shippable-path commits since it. | Unreleased work exists; no publishing/readiness claim. |
| 9 — ecosystem | Resolver absent in declared coc-build repository. | Structural N/A; no other repository read. |
| 10 — deferred quality | Exact-label live query empty. | No new deferral; general issue history remains separate. |

<!-- sweep-redteam:v1:REPO-LEVEL specs_root=specs -->
<!-- sweep-redteam:v1:OK specs=85 symbols=160 orphans=0 coverage_gaps=0 stubs=0 -->
<!-- worktree-reap:v1:scope=all total=69 zero_loss=0 tag_first=0 keep=69 applied=false size_kb=18708040 size_unknown=0 free_kb=192123968 headroom_trees=990 -->
<!-- sweep-ecosystem:v1:N/A reason=resolver-module-absent -->
<!-- unadjudicated-escalation:v1 threshold=3 runs=43 keys=0 escalations=0 suppressed=0 -->

Forest size was exactly 18,708,040 KiB, free space 192,123,968 KiB, with no unknown or partial measurements. The derived 990-tree headroom is free space divided by median linked-tree size, not a concurrency or safety recommendation. All 69 classifications were KEEP at capture; no pending worker tree is deleted by inference.

## Subsequent peer allocation receipt

The peer's dated durable handoff now explicitly acknowledges the earlier Express find-one/count and tracking allocation plus the esperie-ai policy. It delivers transaction candidate `f286a73bb`, Express author series through `711127920`, and tracking manager series through `6a20895a8`, with security/producer findings still open. The Express current matrix is 311 passes per interpreter; correctness is separately clean and security remained pending at handoff. Transaction source review found unconfirmed outcome reporting; tracking's real SQLite control observed a persisted child task disappear after the parent run was saved. Neither is marked converged.

Root subsequently created `fix/csq16-tracking-storage-durability` at `6a20895a8a1642dc76d0c6fc535ae8c5a6d57bdc` and `fix/csq16-transaction-outcome-parity` at `f286a73bbb6e0db8bd1640e4681be23c26564705`, raising registrations by two after the forest capture. Queue receipt `01a107c4-b7f9-7130-9241-8d9955da7e01` carries exact isolated paths, bases, file/method ownership, inline specs and acceptance criteria. These new expansions are queued, not yet acknowledged in this report. Root retains SQL execute/stream/disconnect integration, canonical ledger/chart, dev landing and reap decisions.
