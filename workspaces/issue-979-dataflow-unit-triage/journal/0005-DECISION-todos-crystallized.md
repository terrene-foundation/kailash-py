# 0005 DECISION — Todos Crystallized for OPTION-C′

Date: 2026-05-13
Phase: /todos
Issue: #979
User decision: OPTION-C′ (approved verbatim "proceed" 2026-05-13)

## Decision

User selected OPTION-C′ at the post-/redteam discussion gate. The
converged plan in `02-plans/02-amendments-v2-post-redteam-r1r2.md`
is crystallized into 7 shard todos under
`todos/active/00-INDEX.md` through `07-S6-gate-defenses-alignment.md`.

## Why OPTION-C′

Per `rules/value-prioritization.md` MUST-5 (brief is primary
anchor; code-health secondary):

- OPTION-A would ship ~14 shards over ~7-10 sessions, with 55% of
  the additional scope being pre-existing-gap discoveries that
  don't serve the brief's 7 ACs.
- OPTION-B fails AC#2 (no S-EV owner) and AC#6 (S2b/c/d
  violations linger) — verified by R2 OPTION-C feasibility
  adversary.
- OPTION-C′ delivers all 7 ACs in Workstream-A (7 shards, ~3-5
  sessions) AND files Workstream-B as 5 value-anchored GH issues
  AND keeps Workstream-C (sanitizer contract tests) as a separate
  platform issue.

## Convergence receipts

- 3 redteam rounds executed: R1 (3 agents), R2 (2 agents), R3 (1
  agent). R3 converged with all 6 amendment-v2 items VERIFIED and
  zero new CRIT/HIGH. See `journal/0004`.
- Todos red-team confirmed completeness: agent
  `ab29e2bcc4ab30148` verdict "READY-FOR-HUMAN-GATE" with zero
  blocking gaps. Dependency graph correct; capacity within budget
  for all 7 shards; cross-shard ambiguity explicitly disambiguated
  in S5a (defers to S2a) and S4 (takes precedence over Workstream-B
  for 3 overlapping files).

## Trade-off acknowledgment (per recommendation-quality MUST-3)

OPTION-C′ trades a single integrated workstream for two coordinated
workstreams. Costs:

- ~30% session overhead vs OPTION-A's single pass (two `/wrapup`s,
  two `/redteam` rounds, two `/codify` rounds).
- Workstream-B can decay if not picked up within 2 sessions per
  `rules/value-prioritization.md` MUST-3. Mitigation: file 5 GH
  issues at A-merge time with value-anchors already drafted in
  `todos/active/00-INDEX.md` lines 40-46.
- HIGH-B fabric tier-1 security loss requires the
  `test_fabric_smoke_invariants.py` placeholder in S6 to land
  cleanly. If it slips, fabric ships with weaker tier-1 signal
  until B compensates.

Benefits:

- Brief AC#1-#7 deliverable in ~3-5 sessions.
- Reviewer audit cost stays small (single workspace, ~7 shards).
- The 5 Workstream-B items survive `/clear` via explicit
  value-anchors citing `briefs/00-brief.md:48-53`.

## Forest-vs-trees (per /todos workflow step 5)

`todos/active/00-INDEX.md` § "Forest-vs-trees check" surfaces the
value-ranked top-3 candidate workstreams. Recommendation
(Workstream-A — re-land the gate) is the HIGHEST-value candidate
AND fits the capacity budget. NO fittability-pick-over-higher-value
ambiguity exists — Workstream-A is both highest-value AND
budget-fit.

## Risk register

| Risk                                                 | Disposition / mitigation                                                                                                                            |
| ---------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| S-EV exceeds 200 LOC if root-cause needs schema work | Decomposition caveat embedded in 03-S-EV-dataflow-events.md                                                                                         |
| S4 exceeds 300 LOC                                   | Decomposition fallback into S4a (MOVE) + S4b (audit) in 05-S4                                                                                       |
| Parallel-wave conflict on overlapping files          | S4 takes precedence over Workstream-B for 3 cross-listed files (`test_count_node.py`, `test_architecture_validation.py`, `test_lazy_connection.py`) |
| Workstream-B decay                                   | File GH issues at A-merge with value-anchors                                                                                                        |
| HIGH-B fabric tier-1 loss                            | DEFENSE-3 placeholder in S6 §C; mandatory not optional                                                                                              |
| PR #968 cherry-pick conflict                         | S6 rebuilds workflow from scratch using `test-pact` template + PR #968 as reference                                                                 |

## Human gate status

Surfaced at next user turn. Approval required for:

1. The 7-shard Workstream-A list and dependency graph
2. Workstream-B deferral with value-anchors (5 GH issues at
   A-merge time, NOT auto-implementation)
3. Workstream-C separation as a distinct platform issue
   (sanitizer contract tier-1 tests)
