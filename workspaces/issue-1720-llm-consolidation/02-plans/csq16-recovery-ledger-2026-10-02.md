# CSQ16 recovery work ledger

User authorization (2026-10-02): finish and clean up CSQ16 worktrees; orchestrate with the other Kailash-Py CLI; use Trestle; run /sweep, maintain ledger and generated burndown, land all valid unlanded repo work to dev and reap without loss. Main promotion/release is separate.

Baseline dev and origin/dev: `cdcaeac6baf63911d1f43ed99542002bdcd361a1`. The original worktrees have committed tip `4df93818243fec527590876c0022f6d1f8cacb5a` plus dirty changes. Ancestry alone does not establish content landing. Original modified/untracked files, binary patches and SHA-256 manifests are preserved locally under the common Git directory in `csq16-recovery-2026-10-02`; originals stay untouched during reconciliation.

## Lane ownership

| Lane | Branch | Task set | Agent roster | State |
| --- | --- | --- | --- | --- |
| Sweep / ledger | fix/csq16-recovery-integration | Sweep, preservation receipts, ledger and generated chart | /root | Fresh sweep landed on dev `3cdb91336`; ledger remains active |
| Core integration | fix/csq16-core-integration | Assemble reviewed Core/access/SQL/dependency work | /root | Candidate branch; final review repairs in progress |
| Native task cleanup | fix/csq16-native-task-drain | Owned concurrent tasks and synchronous worker drain | /root/metadata_recovery | `0846ceb32` + `1316b409b` pass 113 tests on Python 3.11 and 3.13; cancellation-waiter and connection cleanup review findings being repaired |
| Node control boundaries | fix/csq16-node-control-boundaries | Preserve terminal/observer identity through node execution and serialization | /root/runtime_logging | Source-reached 70 failing cases; repaired focused suite 183 passed; commit gates running |
| SQL / resource pool boundaries | fix/csq16-pool-boundaries | Retry/cap ownership and runtime resource-manager diagnostics | /root/schema_recovery | Earlier SQL fixes integrated; new real SQLite peer-loss and runtime log findings being repaired |
| Access predicates | fix/csq16-access-siblings and fix/csq16-core-integration | Canonical DENY failure semantics and built-in identity adapters | /root | `488b7070e` plus root comparison follow-up `dbee067f7`; independent final review pending |
| Independent review | fix/csq16-core-correctness (detached snapshot) | Correctness and security review of frozen candidate | /root/http_diagnostics and cross-lane reviewers | Findings delivered; clean rounds required after repairs |
| Remaining storage / transport | Existing recovery branches | S1–S8 and R4–R12 follow-through | Orchestrator assigns the next bounded shard | Delivered receipts below do not imply all work is complete |
| Independent Kailash-Py CLI | Session `01a0e705-6996-7092-95cd-d751936bcc09` | Separate disjoint repair lane after acknowledgement | User-requested teammate | Instructions queued twice; no acknowledgement or ownership |

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

- Additional isolated workers: `fix/csq16-retry-recovery` owns new R14 overall retry deadline (resource_manager only); `fix/csq16-agentui-recovery` owns R5 middleware lifecycle then R10 Nexus ctor cleanup. Both based on narrowed hook a49ee5eeb, scoped specs/specialists, explicit final report return paths. Root owns shared secure_logging fallback fix separately.

## Current technical receipts (2026-10-03 continuation)

| Shard | Recorded state | Evidence / dependency |
| --- | --- | --- |
| R1 access | Committed `610f1de0a`; documentation correction pending | 223 Trestle tests; two correctness and two static security passes |
| R2 strict runtime | Committed `67fb11f48` | 118 focused tests; full Core hook5162pass; two correctness passes |
| R3 runtime / SQL | SQL `09b70d104`; runtime final integration checking | SQL251 tests; runtime teardown warning is explicit open dependency |
| R4 HTTP lifecycle | Committed `a96673341` | 99 focused tests, four negative controls; independent reviews pending |
| R5 / R10 | Independent lifecycle worker running | AgentUI / Nexus constructor ownership |
| R6 diagnostics / controls | `7c9814a7f`, `b0e9adb5e`, `d4abd70ba` | Followup136tests; shared logging fallback fixed separately by root,31tests |
| R8 / R9 | R8 `c173af79e`; R9 worker running | Trust constraints / PACT owned-store lifetime |
| R14 retry deadline | Independent worker running | New dependency defect; not an omitted original dirty file |
| S1 / Count | S1 `b91f949c2`; identifier followup `c3ace367b` | Count147focused tests; SQL identifier review pending |
| S2 resilience | `3a4f251eb` | 74 focused tests; independent review pending |
| S3 constraints | `e28ca81a7`, `f66689407`, `73b5bea03` | Composition fixed; direct executor sinks still open |
| S4 Redis | Worker running | Isolated real Redis provisioning; no shared service changes |

The separate headless adversarial review returned concrete findings but its final attempt was interrupted by the CLI safety filter. No clean verdict is counted from that process. The permitted follow-up is static review of repaired source and existing test assertions; no retry of the blocked action.

- New disjoint lanes prepared: `fix/csq16-trust-sinks-recovery` owns direct S3 executor restrictions; `fix/csq16-cache-identity-recovery` owns S5 codec/producers/invalidation excluding engine; `fix/csq16-metadata-recovery` owns R13 manifests/lock then R11 categorical interop. All source/spec slices supplied, Trestle mandatory, reports returned via saved final files. Storage owns S7 types, engine and nodes.


## Resumed execution receipt — 2026-10-03

The live dev checkout is clean at `6e3e81119f527130113137af93dfccce7295f734`, which includes the ledger, generated chart and opt-in Trestle hook fixes. Production recovery branches are still awaiting final review/integration; branch commits alone do not establish landing. Main promotion PR #2229 remains separate.

Delivered reports were read, not inferred from process status:

| Lane | Delivered work | Current gate |
| --- | --- | --- |
| R3 runtime | `4d4327f3f`; 195 focused real SQLite/PostgreSQL tests | Union review with SQL dependency |
| R3 SQL | `09b70d104`; 251 tests | Cleanup privacy follow-up resumed; 116 tests passed; manifest floor pending |
| R4 HTTP | `a96673341`; 99 tests | Never-served executor/proxy resource fix remains uncommitted and is being verified |
| R5 / R10 | `b408754b2`, `9e61dd24e`; 70 tests | Shared async_close dependency and independent review; broader MCP registration/runtime warnings remain findings |
| R8 / R9 | `c173af79e`, `310382b9`; 209 and 122 tests | Independent correctness and security rounds |
| R14 retry | `59d0b3d3b`; 195 tests, 18-failure negative control | Independent review |
| S4 Redis | `77b90d273`; 95 tests | Cache identity/invalidation remains a separate open S5 obligation |
| S7a types | `dcafe2a68`; 189 tests | Union review with R2 dependency |

Prior cache-identity, trust-sink and metadata process logs explicitly returned `turn.failed` with `You’ve hit your usage limit`. They are not delivered implementations or clean reviews. The old HTTP/SQL follow-up processes also stopped; their existing partial edits and control scripts are preserved. SQL cleanup controls recorded `source_hits=19 intended_test_failures=16`; the resumed focused suite reports `116 passed`.

Current native ownership: `schema_recovery` owns parser plus schema backend dispatch; `runtime_logging` owns hierarchical executor plus adjacent analyzer diagnostics; `metadata_recovery` owns manifests/lock. Root owns SQL/HTTP interrupted follow-up reconciliation and integration. Each lane uses an existing isolated sibling worktree and unpinned Trestle. No original dirty worktree has been removed.

Coordination message queued to the user-confirmed independent session `01a0e705-6996-7092-95cd-d751936bcc09`, receipt `01a0ff28-653e-7e01-9e29-23d2341c569f`. Message repeats sweep, ledger/chart, zero-loss reaping and Trestle instructions. Queued is not acknowledged; no peer file ownership has been granted.

Burndown verification on this continuation returned `burndown --check: block in csq16-recovery-burndown.md is current.` The frozen worktree obligations remain In progress; no owner acceptance is inferred from the delivered commits.


### Continued integration and review findings

- Core union branch `fix/csq16-core-integration` assembled the R1/R2/R3/R6/R14 commits plus dependency recovery. Its first union regression run returned `477 passed`; this is coverage for the named changed regression files, not a whole-repo or backend-parity claim.
- SQL cleanup privacy committed `0ddb53a29`; HTTP terminal resource cleanup committed `fdc8031da` after `95 passed` and three source-reached omission controls. Neither is landed on dev yet.
- Schema dispatch `a76969b00` and canonical engine URL selection `c378f5efc` delivered. Final focused run `305 passed, 4 skipped`; skipped cases need a Redis executable. Original-method control `39 failed, 49 passed` discriminated every selector group. True MySQL schema creation/verification parity remains a separately bounded S1c obligation; preserving fallback policy is not parity proof.
- Dependency recovery `52ddf99b3` updates supported driver/server floors, trust timezone data, ML development HTTP client and Nexus pytest configuration. Root also recovered DataFlow's separate sqlite/dev driver floor in `3d8af3a3e`. Local offline metadata resolution took 126 ms; remote offline resolution had an empty-cache refusal and is not counted as verification. Behavioral old/new dependency controls and normal remote commit hooks passed.
- Retry review found completed operations replayed on final observer failure, unstarted coordination denials counted as attempts, and stale backoff budget after observer work. Follow-up `bcae9ed58` reports `212 passed`; independent final review remains required. Failed-operation observer provenance is a further review question, not yet a reproduced finding.
- Source security review found native async wrappers and the legacy validation decorator reconstructing terminal exceptions. Root fixed them in `9d8ea6f5c`: native control ran `9 failed, 3 passed` before repair; legacy decorator control ran `8 failed, 12 passed`; combined focused green `150 passed`. A first decorator probe imported the shadowing package and failed collection; corrected file-backed legacy loading supplied the actual negative evidence.
- Identifier normalization erased credential delimiters before redaction. Root's URL/JSON credential controls ran `9 failed, 1 passed` before the shared-helper correction; focused corrected suite `78 passed`. Arbitrary unlabeled data embedded in short names remains outside recognized-credential masking claims.
- R1's exported legacy/composition manager and controlled-runtime paths received two static security passes without additional findings. Whole-domain R1 stays open: public EnhancedAccessControlManager omits scope/expiry and allows before later DENY; legacy decorators skip missing identities and execute denied redirects. PACT operating-spec implementation is assigned in `csq16-access-siblings`; a new native PACT spawn was refused by thread capacity, so the existing generic worker loads the verified Read/Write/Edit/Bash specialist specification.
- SQL automatic health/pool/analytics diagnostics still emitted opaque exception text outside the fixed cleanup sinks. DataFlow specialist owns their complete same-file repair. Nexus specialist owns recovered server diagnostic sinks in the existing HTTP tree. Root retains integration and shared terminal/identifier helpers. Reviews with findings remain non-clean.

No additional original worktree has been reaped. Technical branch progress and acceptance remain separate; the frozen generated burndown source is unchanged. Main promotion remains separate from these dev recovery landings.

### Continued review and repair — 2026-10-03, second checkpoint

Dev is `5003a977da051659c231e38136bc706d85a59be2`; production recovery is still staged on isolated integration branches. The following are delivered receipts, not acceptance or landing claims:

- Failed-attempt observer provenance repaired in `eeb9c565d`, integrated as `a0130bf28`: the original nested-engine control ran four failing cases; the repaired focused suite returned `216 passed`. Non-retriable, backoff, final-attempt and adaptive-strategy observers now retain their provenance. An earlier command used an invalid test path and supplied zero evidence.
- Traceback filename review reproduced recognized credentials surviving path normalization. The source-reached regression returned `1 failed, 13 passed`; `f92bb8517` masks the original filename before path normalization and the focused suite returned `45 passed`. Arbitrary unlabeled data remains outside recognized-credential masking claims.
- Enhanced access manager and legacy decorator follow-up `5a6641f78`, integrated as `8ac87857a`, delivered `149 passed`; original-source replay returned `18 failed, 2 passed`. Independent review is active; these tests do not establish a clean security round.
- Native async review found a terminal failure returning while a sibling could still execute. A dedicated pattern-specialist lane owns registration, cancellation and draining of runtime-owned tasks, including the limits of already-running synchronous workers.
- SQL review read every call in its 109-call logging inventory and returned two open classes: normal cleanup can disconnect a runtime-borrowed pool, and caller-controlled scalar/identity metadata still bypasses the logging boundary. The DataFlow specialist owns both repairs. The existing 66-test reviewer run does not resolve either new finding.
- HTTP diagnostic recovery `2f00287e0` plus `301034823` delivered `44 passed`; old-source disclosure controls failed as intended. HTTP resource/diagnostic work remains separately unlanded.

Fresh read-only census: 59 open issues, no exact-label deferred-quality issues, and one open promotion PR. PR #2229 still names `4df93818243fec527590876c0022f6d1f8cacb5a` and its CodeQL check reports `FAILURE`; it is not merge-ready. The forest report classifies all 22 registrations KEEP, with no automatic deletion applied; it measures 7,598,376 KiB and 222,197,396 KiB free. The four original dirty trees are preserved. The chart's frozen obligations remain unchanged and `burndown --check` reports current.

Repeated the authorized peer coordination instructions (sweep, ledger/chart, Trestle and lossless cleanup) to session `01a0e705-6996-7092-95cd-d751936bcc09`, queue receipt `01a0ff50-bf65-73e2-9456-2b01f8485e91`. No acknowledgement has arrived; no peer ownership or completion is inferred.

Preservation recheck compared every original entry and archive against the saved SHA-256 manifests: all 539 entry hashes and all four archive hashes match. This proves unchanged preserved bytes, not semantic landing. The candidate's second union regression run returned `573 passed`; subsequent ownership/task/predicate changes still require their own final integration checks.

### Cross-layer review checkpoint

- SQL fixes `654020048`, `01a88de94`, `616799396` delivered 101 passing tests and source-reached ownership/privacy/composition controls. The next review reproduced two caller-boundary ownership defects: query/batch retry and adapter-cap eviction each detached a real shared SQLite adapter with two references, after which the peer lost its table. Runtime resource-manager logs also exposed recognized DSN credentials and opaque exception messages. These are active fixes, not deferred work.
- Native task drain `0846ceb32` initially passed the default interpreter but failed seven first-cancellation assertions on Python 3.11. A bounded trace identified the outer `wait_for` child-task bridge. Minimal follow-up `1316b409b` uses same-task `asyncio.timeout`; both Python 3.11 and 3.13 returned `113 passed`. A speculative exception override was removed. Independent follow-up then reproduced cancellation of the cancellation waiter interrupting worker drain, and repeated caller cancellation interrupting context connection cleanup; both remain active findings.
- R1 predicate follow-up `488b7070e` delivered 127 dedicated passes, with original-source replay `80 failed, 47 passed`. Root review found incompatible present-subject comparisons still converted errors into false below checked evaluation. Follow-up `dbee067f7` preserves unchecked/missing-subject behavior and custom operator signatures while propagating checked comparison failures: `15 failed, 127 passed` before repair, `366 passed` on the repaired access suite.
- Cross-layer node review reproduced terminal and observer exceptions becoming `NodeExecutionError`, followed by three executions under an outer retry engine. Python constructor/module diagnostics also retained recognized credential metadata. A dedicated pattern-specialist shard owns the complete transformation/logging boundary sweep, including synchronous bridges and serializers.
- R13 dependencies have no findings in the delivered declaration reviews. The isolated ledger/integration branch now contains dependency commits `1fca7c602` and `3a767416b`; an isolated behavioral/lock check is running before separate landing. This does not declare the runtime/SQL shards clean.

No original tree is deletion-ready. Frozen review snapshots retain their exact heads while active; implementation uses separate sibling trees. All newer failures above reset the affected review scope's clean-round count.


### Dependency landing and first recovered lane reaped — 2026-10-03

Dependency recovery is landed and pushed on dev at `8bd3308b5`. The reviewed lane contains `1fca7c602`, `3a767416b` and `4fa4d4a48`: supported SQLite/Uvicorn floors, timezone data, supported package test clients and Nexus pytest configuration. Two independent correctness/dependency-security rounds checked all six TestClient-owning packages, all nine version/Python support anchors, lock metadata and registry artifact integrity. The final manifest-derived request reported `CORRECTED_NEXUS_CLIENT_PASSED 1.7.0 2.13.1`; the pinned missing-client control fails. The normal commit hooks passed. Only Uvicorn and its required httptools resolution changed; the final three package-client declarations changed metadata only.

The task-owned `csq16-metadata-recovery` worktree and branch were reaped after clean-status, exact-ref and remote patch-equivalence checks. Its single commit `52ddf99b3` is equivalent to the pushed dependency commit. Ignored local environment/operator files were copied and hash-verified in private Git recovery storage before normal worktree removal; their contents are not committed. The four original dirty CSQ16 trees remain preserved and none is deletion-ready. This is one completed technical lane, not completion of any frozen whole-worktree obligation.

Native repeated-cancellation repair `540f79b93` delivered 134 passing tests on both Python 3.11 and 3.13, with an original-source control of 16 failing and three passing cases. It is integrated into the Core candidate as `8a546ff60`, awaiting independent review. Node execution-control/metadata repair delivered 183 passes and 70 original-source failures; independent review is active. Pool/shared-adapter repair reports 231 scoped passes; its caller review reproduced skipped lifecycle shutdown after a pool or monitor failure, and the bounded independent-stage correction is included in that lane. These production candidates are not yet landed.

Live runs API before and after the dependency push returned the same latest historical run IDs, headed by `34586101469` on `9955e793d`; no new dependency-landing run was observed in that read. This is a pinned observation, not an inference from workflow trigger text. Main and promotion PR #2229 remain untouched.


### SQLite landing and current runtime review — 2026-10-03

Scheduler/DLQ recovery is landed and pushed to dev at `f589e987f45274d7363b747f71c78e2c0f4c2c5e`. Commits `04c6ee0b5` and `1994a3458` close scheduler bootstrap connections on both outcomes, commit before live sidecar permission checks, and make DLQ connection cleanup and closed-state tracking accurate. Five original-source failures discriminated the fix; the corrected focused suite returned 37 passes. Two independent correctness rounds and two static security rounds completed; the security reviewer did not run tests. Real SQLite lifecycle probes ran in the correctness review. The documented path contract assumes a trusted path lifetime and makes no concurrent path-replacement claim.

The task-owned `csq16-scheduler-dlq-cleanup` worktree and branch were removed after clean status and remote ancestry proof. Only the generated Ruff cache was ignored. The private Git recovery receipt records the exact ref, remote tip and deletion prerequisites. Two technical lanes are now landed and reaped: dependencies and scheduler/DLQ. None of the four frozen whole-original-worktree obligations is complete; all four original dirty trees remain untouched.

The Core candidate at `186e52b0a` passed 1,630 tests across 57 selected files under Trestle. Fresh independent absolute-source reviews nevertheless found public node descriptor discovery suppressing marked callback errors, and disposal callers swallowing execution controls or skipping later resource cleanup. Those are active bounded corrections in separate sibling trees; this suite is not a convergence claim. Authorization review found no new issue in canonical/Hybrid/Enhanced precedence, checked masking, clearance normalization and custom predicate signatures, but only one fresh pass has completed.

Root reproduced public context cancellation dropping a child's cleanup control: ten negative cases failed and four ordinary/cancellation controls passed. The corrected focused runtime suite returned 175 passes on both Python 3.11 and 3.13. Node discovery commit `381bbda2d` reports 364 passes on both Python 3.11 and the default interpreter; its final original-source control returned 31 failures and five passes. Pool disposal corrections are independently owned and not yet delivered. Corrections reset clean-round counts for changed surfaces and their transitive consumers.

The original preservation census contains 539 overlapping entries across four trees and 202 unique paths. Byte equality with a candidate is not semantic closure or proof of landing. The frozen generated burndown continues to show four in-progress original obligations, rather than treating intermediate repair commits as completed originals. Remaining storage, transport, trust, CI and ML shards remain in the bounded queue above. Main and PR #2229 are untouched.


### Expanded runtime union — 2026-10-03

Dev/origin-dev are `4c817d0bc`: the SQLite landing receipt and regenerated chart are pushed. A fresh read enumerated 25 registered worktrees (including the main checkout), 59 open issues, no exact-label deferred-quality issues, and the unchanged promotion PR #2229 at `4df938182` with CodeQL `FAILURE`. Dirty originals still have 154, 86, 199 and 100 entries respectively. These are read-time counts, not a reap verdict.

Core candidate receipts now include child cancellation `508335a52`, node discovery `6be00bbdf`, resource utility cleanup `d83e76e3e`, pool disposal `ea569536e` and annotation callbacks `cd32954e8`. The expanded union returned 1,903 passes and eight failures. Seven failures named unavailable Python database driver modules; the same affected selection with PostgreSQL/MySQL extras returned 44 passes, including the live PostgreSQL loop-ownership case. The remaining cleanup test expected a duplicate adapter-disposal diagnostic; the owner verified real disconnect already completed before the raised failure and is correcting the test to assert one disposal and its two actual diagnostics.

Utility cleanup original-source controls returned 34 failures and 11 passes. The corrected 45-case utility matrix and focused runtime checks returned 125 passes on Python 3.13; Python 3.11 returned 60 passes with one separately marked live PostgreSQL test skipped because its service was unavailable. This proves named SQLite/component behavior, not general backend parity. First cancellation identity, later resource drainage, retired capacity, primary-error precedence and safe diagnostic records are covered.

Fresh node reviews remain non-clean: real nested-engine probes confirmed annotation metadata errors being swallowed/replayed, and the node owner is closing constructor/module metadata siblings. The independent static security review also identified runtime input-name and restricted-import concerns; the implementation owner reproduced them on real SDK calls and is correcting both async and sync import namespaces. Pool ownership probes confirmed two public shutdown paths returning before background cleanup finished during repeated caller cancellation; a bounded follow-up now awaits owned task completion and distinguishes intentional task cancellation from the caller's request. None of these follow-ups is recorded as converged until independent corrected-snapshot reviews complete.

The four original worktree obligations remain in progress. No additional original or unlanded task tree was deleted. Trestle queueing is reported as no execution until admission; no queued command supplies a passing result.


### Independent CLI allocation and remaining Core findings — 2026-10-04

The second CLI explicitly acknowledged availability as session `01a0e77e-87be-7cc0-9f2f-1b84d5cf709d`. Its isolated branch `fix/csq16-cache-invalidation-repair` starts at storage candidate `c378f5efcff8624ad4f161457cc3bbe21d06a1ef`. Allocation receipt `01a10656-15a7-7392-b91f-089165cbb7bd` assigns the typed cache-key identity and memory/Redis invalidation shards, including transaction publication boundaries, DataFlow specialist consultation, Trestle verification and two independent clean correctness/security rounds. Availability is acknowledged; acceptance of this exact allocation and its implementation results are pending. The peer owns cache implementation, associated tests and `specs/dataflow-cache.md` section 6; the root retains this canonical ledger, chart, dev integration and reap decisions. The four dirty originals remain read-only inputs.

Core candidate `b765b60ce47d880a703916a6c3d2ad6da6472179` includes checked authorization descriptors `e329513be` and transaction cleanup `b765b60ce`, along with the intervening pool, input namespace, annotation and fallback-close corrections. Authorization checks returned 455 passes on each of Python 3.11 and 3.13; source controls include 12 failures/32 passes plus nine sibling failures/three passes. Transaction cleanup returned 233 focused passes on each interpreter and 200 dedicated cases; corrected source controls returned 107 failures/89 passes. The earlier negative run containing invalid protocol fixtures is not counted. These are repair receipts, not independent convergence.

Independent review still identifies active Core work: wrapper signature/doc/type discovery, lifecycle hooks and resource-limit monitoring, and ResourceRegistry cancellation/awaitable/descriptor handling. Separate owned workers repair the wrapper and lifecycle surfaces while the root owns the registry. A streaming-finalization concern is awaiting a confirming probe; it is not asserted as an established defect. A read-only infrastructure consultation confirmed whole-drain ownership, callback context preservation and single invocation as required invariants. Fresh corrected-snapshot correctness and adversarial security rounds remain required before Core landing.

Two previously completed technical lanes remain landed and reaped. The frozen whole-original obligations remain four in progress; no additional original tree has been removed. An unrelated detached temporary build worktree observed in the live forest is preserved outside this task's ownership.


### Adversarial Core checkpoint — 2026-10-04

Dev remains `811828ee9`. Core integration now includes registry snapshot drainage `c4accf3a5`, wrapper introspection `823d8e9ea`, lifecycle/monitor controls `17ccbabb8` and `5edb6e1e7`, and SQL streaming ownership `08ba82f35`. Wrapper source controls returned 15 failures/21 passes; fixed Python 3.14 returned 140 passes, and Python 3.11/3.13 each returned 137 passes with three explicitly version-specific PEP-649 cases skipped. Streaming controls returned 73 failures/nine passes after correcting invalid protocol fixtures; the fixed selection returned 349 passes on each interpreter. PostgreSQL/MySQL protocol tests do not establish live backend coverage.

The independent adversarial review is **not clean**. Actual SDK probes reproduced five issues: failed masking predicates exposed the protected field on legacy and composed authorization paths; a declared node-ID descriptor failure selected the decorator's class-name fallback; re-registering a factory during creation abandoned one SQLite connection; cancelling health evaluation abandoned a worker's returned coroutine; and built-in health callbacks swallowed execution controls and retained exception payloads. These are active bounded repairs, not deferred work. Separate authorization and health implementation lanes have explicit disjoint ownership and specialist context.

Registry follow-up retains the name lock across factory replacement and owns health callback completion before disposal. Its actual prior-source control returned three failures/46 passes; fixed tests returned 310 passes on Python 3.13 and 3.11. One fresh correctness round is clean; independent security re-review remains required. An intermediate run was interrupted after a fixture waited for cleanup before releasing the health callback; it supplies no passing evidence. The corrected fixture schedules cleanup concurrently and verifies the resource stays alive until the callback completes.

A separate cancellation-token probe reproduced three failures where a cancellation subclass's `args` descriptor replaced the original control. Native exception-argument access now passes 223 focused checks on each interpreter. Lifecycle transition work reports 95 passes on Python 3.13 and 94 passes plus one unavailable-stdlib-feature skip on Python 3.11; its final normal commit and integration are pending. LocalRuntime per-node finalization is undergoing a distinct real-resource probe; no verdict is yet banked.

The cache peer's tree shows active implementation, including `05153e953`; no completed handoff has been read. Queue acceptance is not delivery and branch activity is not a review receipt. The canonical frozen burndown still records all four original worktree obligations in progress. Two earlier technical lanes remain landed/reaped; no original tree or newly unlanded implementation branch has been deleted. Main and promotion PR #2229 remain untouched. This checkpoint does not claim a new complete ten-part sweep or whole-Core convergence.
