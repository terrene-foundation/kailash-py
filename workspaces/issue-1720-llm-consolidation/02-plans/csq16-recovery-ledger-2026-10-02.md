# CSQ16 recovery work ledger

User authorization (2026-10-02): finish and clean up CSQ16 worktrees; orchestrate with the other Kailash-Py CLI; use Trestle; run /sweep, maintain ledger and generated burndown, land all valid unlanded repo work to dev and reap without loss. Main promotion/release is separate.

Baseline dev and origin/dev: `cdcaeac6baf63911d1f43ed99542002bdcd361a1`. The original worktrees have committed tip `4df93818243fec527590876c0022f6d1f8cacb5a` plus dirty changes. Ancestry alone does not establish content landing. Original modified/untracked files, binary patches and SHA-256 manifests are preserved locally under the common Git directory in `csq16-recovery-2026-10-02`; originals stay untouched during reconciliation.

## Lane ownership

| Lane | Branch | Task set | Agent roster | State |
| --- | --- | --- | --- | --- |
| Sweep | chore/csq16-recovery-sweep | All sweep surfaces, refs, forest, deferred-quality, release inventory | /root/recovery_sweep (running) | Read-only inventory; report-only writes |
| Runtime | chore/csq16-recovery-runtime-audit | Core, runtime, API, CI and non-DataFlow dirty variants; bounded repair decomposition | /root/runtime_recovery_audit (running) | Read-only audit; no source mutation |
| Storage | chore/csq16-recovery-storage-audit | DataFlow engine, adapters, caching and tests across all original trees | /root/storage_recovery_audit (running) | Read-only audit; no source mutation |
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
