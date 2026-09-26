# CSQ 14 continuation — final gates

## Live repair checkpoint — supersedes earlier statuses

Committed source is `a2298eb7f9f3db63392e1d7e7fe6d940bc2c6eff`; this is NOT the final promotion candidate.
New landed repairs include PACT API CI provisioning (33caf1bfe), graph fixture
ownership (8be44bcf5), SignalWait validation (14e916aaf), real DataFlow privacy
assertions (927e8fca1), gateway fixture cleanup (b11496ad4), route/scanner
instrumentation (d1e22be9d), cold namespace configuration (af4b4e506), automatic
runtime diagnostics (9279d92c3), temporary DataFlow connection ownership
(fb7187f36), and isolated TDD fixtures (a2298eb7f).
Runtime diagnostics: 229 strict cases, two scoped independent rounds, unchanged
nonlogging ASTs in five production modules, actual missing-key record/stream
probe, and reached old-frame control (12 hits, 10 failures). Ownership: 25 local
strict cases, original real SQLite cancellation reproduction now propagates
cancellation after disposal, six reached prior-scope failures, independent
PostgreSQL run and two scoped review rounds. Debug timing notices were inventoried;
these receipts do not claim whole-suite warning absence or MySQL coverage.

OPEN source work: single-owner conditional fallback (frozen 3dba43e4, applied
uncommitted), optimized checkpoint replay/completion plumbing (separate follow-on),
and canonical memory database cache identity/SQLite alias handling. A scanner
follow-on (a1ccc979) restricts direct-expression findings to actual logger arguments;
public result dictionaries are not log sinks. Planner fixture warnings are under
review. Active siblings are final2-correctness, final2-security, final2-coverage,
and memory-cache-identity. Preserve their owned overlays.

The a6ff5afe full gates did run and were NOT clean: Linux root 8 failed/3398
passed after API provisioning, DataFlow unit 3 failed/3481 passed, Mac hooks
pytest-check 1 failed/4897 passed. Their identified fixtures/expectations are now
repaired, but those historical runs do not cover the new source. Final full root
and DataFlow suites, every all-files hook including pytest-check, and three
whole-union reviews remain OPEN. Authorized per-commit pytest-check skips remain
tracked here until that complete all-files gate passes. No push has occurred.

D1 promotion approval persists. PR #2229 remote head remains ce4c9de67. Nine
proposed CodeQL dismissals await explicit approval; none was executed. Required
exact-head checks and every previously failing test job must pass before the
separate merge command. Three post-main union/tree-parity reviews remain due.
Preserve five stashes and 52 uncertain refs. No publishing, owner acceptance,
whole-forest completion, Windows runtime or filesystem race-prevention claim.


## Active checkpoint (supersedes historical rows below)

Primary dev: 51fcd96c0; remote promotion still ce4c9de67. D1 approved.
No publishing. Nine CodeQL dismissal approvals pending; five stashes held.

| Repair | State |
| --- | --- |
| SSO privacy | Landed eae68c672, clean sibling drained |
| Initial gateway validation/lifetime | Landed 58c745790, 19 strict passes |
| DataFlow transaction cache | Landed 7615b14eb, clean sibling drained |
| Socket/WebSocket | Landed 21c2fc68e, 107 strict passes, original named tests 68 |
| AsyncNode loop/cancellation ownership | Landed e7c1085b0, 86 strict passes, clean sibling drained |
| Sibling gateway lifetime/auth binding | Landed ec9e5adea, two independent correctness/security rounds |
| Async content failure | Landed a32a24d0a, 52 parent passes; clean sibling drained |
| DataFlow utility/options | Landed 51fcd96c0, combined 83-pass SQLite integration; clean sibling drained |
| Five logging sinks | Landed fcee1a249; merged gateway/logging 38 strict passes; clean sibling drained |
| Runtime compatibility option forwarding | Freeze 569e68f1; 83 strict passes, five reached controls; review active |

Three holistic reviews use final-correctness/security/coverage siblings at
51fcd96c0 plus the exact forwarding overlay; compare their source to the final
merge before banking union evidence. Final root/DataFlow suites, all configured
hooks including pytest-check and exact-head remote checks remain OPEN.

## Historical checkpoints

Current source: 8f77625056e37ffd993d803a3cddd473408e0a08. All implementation siblings are landed and drained.
PR #2229 remains at ce4c9de67 until the next validated consolidated push.

| Lane | Result | State |
| --- | --- | --- |
| ML seed isolation | 237 strict passes | Landed and drained |
| Archive evidence | 52 refs recorded with limits | Landed; uncertain refs retained |
| Dependency/class fixtures | 74 strict passes | Landed |
| R1 authentication | Two clean rounds | Landed and drained |
| D1 unit fixtures | Two clean rounds | Landed and drained |
| D3 caller cleanup | Two clean rounds | Landed and drained |
| D2 ownership | Two clean rounds | Landed and drained |
| R2 early validation | Two clean rounds | Landed and drained |
| Final import scan | 31 strict passes, five mutations | Landed and drained |
| Optional aiohttp guard | 13 strict passes, reached opposite | Landed |
| Finite deadline | 23 strict passes, public-path opposite | Landed and drained |
| Root full regression | Final source rerun | Active on esperie-ai |
| All configured hooks | Includes pytest-check obligation | Pending corrected Mac runner |
| CodeQL provenance | ml_gate_recovery | Read-only investigation |
| CodeQL alert membership | ml_correctness_review | Read-only investigation |
| CodeQL security behavior | archive_checkpoint | Read-only investigation |

The three detached holistic siblings remain for the investigations. Five inherited
stashes and uncertain historical refs are preserved. D1 is already approved;
read exact-head checks separately from merge. Package publishing is not authorized.
