# CSQ 14 continuation — final gates

## Live repair checkpoint — supersedes earlier statuses

Committed source is `07ee23ffee758a74ec42abd2bdc90c3aba57e062`; final promotion gates remain OPEN.
Runtime automatic diagnostics (9279d92c3), temporary connection ownership
(fb7187f36), memory cache/connection identities (48a36aef8), single-owner
conditional fallback (74c330005), and durable conditional state (ec01c3b87)
are landed with two scoped independent rounds and reached negative controls.
Fixtures now preserve actual gateway lifetimes, native graph ordering, import
security, and real SQLite rollback while asserting safe automatic diagnostics.
The final conformance fixture commit is 07ee23ffe. Runtime state receipts include
349 author, 166 independent, 229 parent integration and 21 final focused passes;
DataFlow memory/address receipts include 134 author, 114 independent and 39
revised parent passes. These overlapping totals are not unique coverage counts.
Real Redis cache isolation and real SQLite tenant-separated replay were exercised.

ONE source shard remains: shared SQLite address parsing and cache identity
across sync/async adapters, registry, migrations, DDL and connection producers.
Author archive_checkpoint works in root-created sibling csq14-sqlite-address-parity,
branch fix/csq14-sqlite-address-parity at cb92f3261 with memory39ce as borrowed base.
Core correctness and security specialists consult/review independently. Public
spec defines standard three-slash relative and four-slash absolute URLs; retain
legacy two-slash relative compatibility and native URI options. A shared helper
must preserve driver options and distinguish disk versus memdb VFS databases in
cache identity. Actual disk/memdb rows differed while a draft key collided; this
finding is OPEN until the frozen correction and reached controls pass. Generic
Rust-pinned key encoders stay byte-identical. Caller cache namespaces may change
to close this isolation defect; no persistent data migration is intended.

The a6ff5afe full gates ran and were NOT clean: Linux root 8 failed/3398 passed,
DataFlow unit 3 failed/3481 passed, Mac hook pytest-check 1 failed/4897 passed.
Those identified defects/fixtures are repaired, but those runs do not cover the
current source. Final full root/DataFlow suites, all configured all-files hooks
including pytest-check, and three whole-union reviews must run after the final
shard converges. Authorized interim pytest-check skips remain tracked here until
that full hook gate passes. No push has occurred; PR #2229 remains ce4c9de67.
D1 promotion approval persists. Exact-head required checks and all previously
failing test jobs must pass before a separate merge command. Three post-main
union/tree-parity reviews remain due, then drain only clean landed siblings.

All nine CodeQL false-positive dismissals (11595,11596,11466,11467,10866,5153,
131,133,6082) were explicitly approved, executed and independently re-read as
dismissed on 2026-09-26. The receipt is
`04-validate/csq14-codeql-disposition-receipt.json`; no approval remains pending
for these IDs. CodeQL and other promotion checks were not waived.
Preserve five stashes and 52 uncertain historical refs. No package publishing,
owner acceptance, whole-forest completion, Windows runtime or filesystem race
prevention claim. Existing final2/memory review overlays remain held until
source parity is proven and their owned contents are safely drained.


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
