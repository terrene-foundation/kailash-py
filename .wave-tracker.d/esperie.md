# CSQ 14 continuation — final gates

## Live repair checkpoint — supersedes earlier statuses

Dev is `8ed016700`: canonical runtime controls and timer cleanup landed, including
literal-boolean drift validation and bounded queue index names. The final combined
selection passed 281 strict tests; reached spoof mutation failed all nine intended
entry/evaluator cases. Independent correctness/security rounds are delivered.
Bridge fixture isolation is committed as `a2f36b2ad`.

Constructor/runtime-input separation landed as `8ed016700` (source `1050bc1d8`),
with 381 strict passes, 26 focused passes and two clean scoped review rounds.
Core/DataFlow privacy landed as `e4eedbf73`, with 31 DataFlow and 41 Core tests
and two independent clean rounds. Combined integration passed 269 Core and nine
DataFlow cases. Both clean runtime/configuration source siblings are drained.
MFA delivery diagnostics and shared security-path diagnostics have separate
root-created sibling lanes. The latter is verifying canonical containment as well
as removing automatically logged payload values. These are open until their
specific evidence is delivered; earlier holistic review attempts found issues and
DO NOT count as clean convergence.

D1 promotion approval persists. PR #2229 remains unpushed at `ce4c9de67`.
Nine proposed CodeQL dismissals still require explicit approval; none was executed.
Five stashes and uncertain historical refs remain held. Full combined suites,
all configured all-files hooks including pytest-check, three parallel final union
reviews, exact-head remote checks, and separate promotion merge remain required.
No package publishing or whole-forest completion is authorized or claimed.


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
