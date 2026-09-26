# CSQ 14 continuation — final gates

## Live repair checkpoint — supersedes earlier statuses

Final source candidate is `15960d9478e327389413e3765e4284801b16fa8b`. Runtime controls/timer ownership,
constructor/runtime-input separation, real DataFlow transactions/cache handling,
gateway per-app authentication/resource ownership and canonical path checks are landed.
Automatic Core/DataFlow, MFA and Python exception diagnostics omit payload values;
public exception/result contracts and explicit caller-authored logging are preserved.
All substantive repair shards have two delivered scoped review rounds, reached
negative controls and retained test evidence. The latest selections include 281
runtime, 381 configuration, 403 MFA, 110 security/path and 42 Python cases. These
overlap and must not be added as a unique coverage total. Ten macOS resource-limit
skips do not cover those Linux paths. No filesystem race prevention or Windows
runtime claim is made. Completed implementation siblings are drained.

Three final reviewers will assess the full promotion union and repair interfaces
at this source; final root/DataFlow suites and every configured all-files hook,
including pytest-check, remain OPEN. Historical greens do not cover this candidate.
D1 promotion approval persists. PR #2229 remains at `ce4c9de67` until those gates pass.
Nine proposed CodeQL dismissals await explicit approval; none was executed.
Exact-head required checks and previously failing jobs must succeed before a
separate merge operation. Three post-main union/tree-parity reviews remain due.
Five stashes and 52 uncertain historical refs remain held. Package publishing,
owner acceptance and whole-forest completion are not authorized or claimed.


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
