# #2203 — MCP + A2A protocol drift: wave plan

**Status: AWAITING APPROVAL.** `/todos` plan approval is a structural human gate
(`autonomous-execution.md` § Structural vs Execution Gates). No shard starts on this
document alone.

Decisions ratified 2026-08-21 and recorded durably at
`#2203#issuecomment-5363864384`: **D-A Modern (`2026-07-28`)**, **D-B A2A 1.0**,
**D-C env-gated fail-closed TCK hook**.

## Why this is three waves, not one

`wave-loop.md` MUST-1 binds on BOTH axes. The value axis alone would let the whole issue
run as one wave (it is one co-owner priority); bound B — the cumulative load-bearing
invariant surface — is what forces the split. MCP-Modern and A2A-1.0 share no invariants
and no call graph, and the conformance gating cannot be written until both surfaces exist.

Re-measured on main before planning, not carried from the report:

```
grep -rc "server/discover\|resultType" src/kailash/trust/mcp/   → no non-zero counts
grep -rln "well-known/agent"          src/kailash/trust/a2a/    → 3 files (4 sites)
```

The MCP Modern surface is entirely absent, which is what makes Wave 2 architectural.

---

## Wave 1 — A2A → 1.0  (est. 1–2 cycles, 2 shards)

Smaller, independent of MCP, and it retires the 0.2.x surface we currently advertise.
Sequenced first so the conformance-gating wave has at least one conformant surface to
gate against.

**Invariant surface: 4** — path consistency across all 4 sites · agent-card schema
validity · JSON-RPC method-name contract · no 0.2.x path left serving.

| shard | scope | budget notes |
| --- | --- | --- |
| **1A** | Well-known path `/.well-known/agent.json` → `/.well-known/agent-card.json` across all FOUR sites (`service.py:175` endpoint, `service.py:11` docstring, `models.py:84`, `agent_card.py:209`), plus card derivation to the 1.0 shape. | Small LOC, but 4 sites in 3 files — the trap directive 3 names. Renaming only the endpoint leaves three stale references. |
| **1B** | The 1.0 method set: `message/send`, `tasks/get`, `SendMessage`, `GetTask`. All currently 0 hits (control: `jsonrpc` → 23). | Net-new surface; load-bearing logic, well under 500 LOC. |

**Open question for 1A, to settle at implementation:** whether the 0.2.x path keeps serving
during a deprecation window. `feedback_no_shims` says remove shims immediately rather than
carrying deprecation timelines — so the default here is a hard cutover, but this is a
published protocol surface, so flagging it rather than assuming.

---

## Wave 2 — MCP → Modern (`2026-07-28`)  (est. 2–4 cycles, 4 shards)

Architectural. The server is Legacy by construction — built around `initialize`, with no
`server/discover` and no `resultType`. This is NOT a version-string bump and must not be
sharded as one.

**Invariant surface: 7** — version negotiation correctness · per-request version metadata ·
`resultType` present on EVERY result · `server/discover` completeness · no `initialize`
path left reachable · no `ping` path left reachable · error-taxonomy preservation across
the handshake removal.

That is at the top of bound B's base ceiling (5–10), which is why it is 4 shards and not 2.

| shard | scope | budget notes |
| --- | --- | --- |
| **2A** | Version negotiation + per-request version metadata. Replaces the `server.py:74` tuple `("2025-06-18","2025-03-26","2024-11-05")`. | Foundation — 2B/2C/2D all depend on it. Sequential, not parallel. |
| **2B** | `server/discover` surface (a MUST in 2026-07-28; currently absent). | Net-new. |
| **2C** | `resultType` on every result (required on every result; currently absent). | Touches every result-producing path — the broadest shard. Watch the 500-LOC load-bearing ceiling; split if it exceeds. |
| **2D** | Retire `initialize` (21 refs) and `ping` (5 refs). | Deletion shard, LAST — removing the handshake before 2A–2C land would leave no working path. |

**2A → (2B ‖ 2C) → 2D.** Only 2B and 2C are parallelizable; 2A gates them and 2D follows.

---

## Wave 3 — Conformance gating + the TCK hook  (est. 1 cycle, 2 shards)

**Invariant surface: 3** — the TCK hook fails closed when unset · per-requirement gating
by name · no skip counted as a pass.

| shard | scope | budget notes |
| --- | --- | --- |
| **3A** | D-C: `messageId`-prefix recognition behind an env flag defaulting **OFF** and failing closed. Reviewed as a security surface — `security.md` § Secure-Default For A New Security Feature applies, and per `agents.md` § "Correctness-Review-Clean Is Not Security-Clean" this needs BOTH a correctness reviewer AND an adversarial security-reviewer before it converges. | Production code that changes behaviour on attacker-influenceable input. |
| **3B** | Wire both conformance suites into CI, **gated per-requirement by name — never on absence of failures.** Both suites skip capability-gated tests, and to a failure-counting gate a skip and a pass are the same colour. | This is the same non-discriminating-instrument shape this workspace has hit repeatedly (`instrument-discipline.md` MUST-1). A green count is not the gate; named requirements are. |

**Standing constraint:** do not quote the A2A `compliance_badge` anywhere. It is emitted by
running the tool against your own endpoint and is conferred by nobody.

---

## What this plan deliberately does not do

- **Does not bundle `TrackerMCPServer`** (`ml-tracking.md` §11.1 MUST, unimplemented — one of
  the 22 surviving sweep-5 orphans). It is an MCP surface, so building it before Wave 2
  lands would build against the revision we are replacing. It waits on Wave 2, and the
  session notes carry that hold.
- **Does not fold in #2206** (the dataflow #1548 residual durability window). Different bug
  class, not jointly revert-safe with protocol work.
- **Does not start implementation.** Approval gate first.
