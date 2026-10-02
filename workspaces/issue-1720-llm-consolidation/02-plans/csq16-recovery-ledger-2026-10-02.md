# CSQ16 recovery work ledger

User authorization (2026-10-02): finish and clean up CSQ16 worktrees; orchestrate with the other Kailash-Py CLI; use Trestle; run /sweep, maintain ledger and generated burndown, land all valid unlanded repo work to dev and reap without loss. Main promotion/release is separate.

Baseline dev and origin/dev: `cdcaeac6baf63911d1f43ed99542002bdcd361a1`. The original worktrees have committed tip `4df93818243fec527590876c0022f6d1f8cacb5a` plus dirty changes. Ancestry alone does not establish content landing. Original modified/untracked files, binary patches and SHA-256 manifests are preserved locally under the common Git directory in `csq16-recovery-2026-10-02`; originals stay untouched during reconciliation.

## Lane ownership

| Lane | Branch | Task set | Agent roster | State |
| --- | --- | --- | --- | --- |
| Sweep | fix/csq16-runtime-recovery | All sweep surfaces, refs, forest, deferred-quality, release inventory | /root/recovery_sweep (running) | Sweep delivered; now owns R6 node/logging recovery |
| Runtime | fix/csq16-access-recovery | Core, runtime, API, CI and non-DataFlow dirty variants; bounded repair decomposition | /root (implementation), /root/runtime_recovery_audit (review) | R1 access recovery tests running |
| Storage | fix/csq16-storage-recovery | DataFlow engine, adapters, caching and tests across all original trees | /root/storage_recovery_audit (running) | S1 committed b91f949c2; S2 tested, awaiting hook routing |
| Integration | fix/csq16-recovery-integration | Preservation, union assembly, ledger, generated chart, review, dev landing and zero-loss reaping | /root (running) | Owns ledger and burndown sources |
| Independent Kailash-Py CLI | Pending current return address | Separate disjoint repair lane after acknowledgement | User-requested teammate (address pending) | No ownership granted until confirmed |

## Source preservation and recovery queue

| Stable ID | Original worktree | Branch | State | Acceptance evidence required |
| CSQ16-PROMOTION | csq16-promotion-verification | fix/d1-trust-log-hygiene | In progress | Every dirty path reconciled to landed behavior or justified supersession; reviewed tests; bare worktree removal |
| CSQ16-RUNTIME | csq16-runtime-ci | fix/d1-runtime-ci-validation | In progress | Same; retain unique rule-metadata and deny-precedence changes |
| CSQ16-SOURCE | csq16-source-integration | fix/d1-source-gate-closure | In progress | Same; integration source is a candidate, never a blanket winner |
| CSQ16-STORAGE | csq16-storage-ci | fix/d1-storage-ci-path | In progress | Same; preserve unique adapter/cache/schema changes |

## Execution contract

- Long commands use `trestle run -- <command>` with tracked-ignore preflight, no default host pins or ad-hoc SSH. Exit 114 is unknown; 116 means no run. Pipeline status must preserve actual test failures.
- Each implementation shard has explicit file ownership, relevant inline specs, a specialist and bounded invariants; fix root causes within the authorized scope.
- Correctness and adversarial security review require actual evidence, two consecutive clean rounds, then holistic union review when multiple implementation waves land.
- Land finished lanes into dev; do not convert old PR greens into current-head clearance.
- Never force-remove a dirty worktree or discard an untracked file. Reap only after content preservation/landing and occupancy checks.
- Separate generated acceptance buckets from technical landing evidence. A merge is not owner signoff.

## Activity

- 2026-10-02: fetched origin, pinned matching dev/origin/dev; preserved original dirty sources; launched independent sweep, runtime and storage audits.
- 2026-10-02: Trestle status returned shared arbiter occupancy; host selection remains automatic.
- 2026-10-02: runtime audit identified mutually unique deltas; wholesale selection of one original tree would lose changes.

- 2026-10-02: sweep delivered with Trestle root-spec structural receipt; semantic/runtime conformance stays open. Reports copied into integration lane.
- 2026-10-02: message with full user scope/Trestle requirement queued to last known independent Kailash-Py session; current address and acknowledgement pending.
- 2026-10-02: runtime specialist consultation reproduced role-revocation cache inconsistency and ALLOW masking mismatch. R1 repairs both; focused Trestle tests running.
- 2026-10-02: S1 owns schema inspector temporary adapter cleanup and narrow Count plumbing; R6 owns shared diagnostic formatter and node/tracking users. No overlapping writers.

## Bounded recovery plan

Runtime audit proposes R1 access, R2 strict runtime, R3 SQLite ownership, R4 HTTP lifecycle, R5 Agent UI cancellation, R6 diagnostic helpers/nodes, R7 webhook/channel diagnostics, R8 trust constraints, R9 governance stores, R10 Nexus initialization, R11 ML conversion, R12 CI/MCP infrastructure, R13 dependency reconciliation. Overlapping runtime files stay with one owner in sequential shards; API/server overlaps likewise. Storage audit proposes S1 schema ownership, S2 resilience, S3 trust constraints, S4 Redis lifecycle, S5 approved cache identity redesign, S6 write invalidation, S7 types/utilities, S8 adapters. Each active shard is bounded; original trees remain immutable recovery inputs. New same-class bugs discovered during review are fixed in their owning shard with evidence.

- Commit execution: root owns an opt-in `KAILASH_TRESTLE_TESTS=1` route in the existing interpreter wrapper; only pytest invocations offload, with unchanged argv and exit status. No hook bypass. R6 and S2 hold commits until routing verified.

- R6: 132 Trestle passes; two post-fix correctness source rounds clean. S2: 64 regression plus 10 compatibility passes with deadline-removal negative. Independent headless read-only security lane `csq16-access-security` owns a frozen union of R1/R6/S1/S2 for adversarial review; root owns its snapshot and cleanup. No security-clean claim yet.

- Additional independent headless workers dispatched: `fix/csq16-sql-recovery` owns R3 async_sql + owner regressions; `fix/csq16-http-recovery` owns R4 async_close/APIChannel/WorkflowAPI/server lifecycle. Both use orchestrator-created sibling trees at committed hook base 026af686e, specialist specs and Trestle; final report files are the explicit return path. Runtime lane excludes SQL node; root excludes R4 files.

- Technical receipts: S1 `b91f949c2` (145 SQLite-focused passes, backend exclusions explicit), S2 `3a4f251eb` (74 focused passes), R6 `7c9814a7f` (132 focused passes). R6 security traceback finding remains open; S3 `e28ca81a7` has semantic-policy follow-up underway. None yet declared converged.
- Durable hook routing committed as `026af686e`; earlier temporary unstaged routing was stashed by pre-commit, so S2/R6 mandatory hooks were local. Their focused tests ran Trestle. Subsequent lanes cherry-pick durable routing and set opt-in env.
- R2: 118 focused Trestle passes, two correctness rounds clean. R1 plus R2: 223 Trestle passes after tenant/mask/custom-predicate fixes; security rereview pending.
- Reaped empty setup refs `chore/csq16-recovery-runtime-audit`, `chore/csq16-recovery-storage-audit`, `chore/csq16-recovery-sweep`: each exactly equals dev SHA and has no registered worktree. Original dirty worktrees untouched.

- Independent `fix/csq16-trust-recovery` worker owns R8 constraints/governance policy then R9 PACT store ownership, with separate bounded commits, explicit PACT/infrastructure consultation and Trestle. Root owns landing/reaping and report receipt.
