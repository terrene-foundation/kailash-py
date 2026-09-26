# CSQ 14 continuation — final gates

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
