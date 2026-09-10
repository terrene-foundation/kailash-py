# #2203 — MCP + A2A protocol drift: wave plan

**Status: APPROVED 2026-09-10. Wave 1 Shard A LANDED (`b6bf4a1ca`).
Shard 1B was landed and then REVERTED (`6e4e652da` → `93323218e`) — it
introduced a cross-agent task read/write. Shard 1-AUTH landed in its place
(`35fc66f01`) and now gates the 1B re-land. Sequence is 1A → 1-AUTH → 1B' → 1C.**

> **Why 1B was reverted, and why an auth shard appeared.** An adversarial review
> executed two attacks against 1B on a live app: `GetTask` had no ownership
> predicate (any caller read any task, including its full message history), and a
> client-supplied `message.taskId` let a caller append to a victim's task and get
> the victim's history back — a confused-deputy against the agent executor, since
> the injected text arrives labelled `ROLE_USER`. Both were introduced by 1B.
>
> A correct ownership check needs a caller identity, and there was none to bind
> to: `A2AAuthenticator.verify_token` had NO call site in the request path, so any
> non-empty bearer string authenticated every protected method — including
> `trust.delegate` and `audit.query`. That hole was PRE-EXISTING and sat under the
> whole A2A surface, not just 1B. Fixing it is 1-AUTH, and it necessarily
> precedes any ownership work.

> **Scope correction, measured at implementation:** 1A's well-known path is **16
> sites across 6 files**, not the 4-across-3 stated below. The original count
> scoped its grep to `src/kailash/trust/a2a/` and missed the integration test (9
> sites) and two docs. Recorded at `#2203#issuecomment-5613952429`. The table
> below is left unedited as the historical record of what was believed.

> **METHOD-SET correction for 1B, measured against the spec before implementing.**
> The 1B row below names `message/send`, `tasks/get`, `SendMessage`, `GetTask` as
> "the 1.0 method set". Those are **two different protocol generations**, and only
> the PascalCase pair is 1.0's. Measured at `a2aproject/A2A` tag `v1.0.1`:
>
> - `docs/specification.md` § "Protocol Requirements": _"**Method Naming:**
>   PascalCase method names matching gRPC conventions (e.g., `SendMessage`,
>   `GetTask`)"_.
> - § "Method Mapping Reference" lists JSON-RPC `SendMessage` / `GetTask`, and
>   puts `POST /message:send` / `GET /tasks/{id}` in the **REST** column. The
>   slash forms are 0.2.x/0.3.x JSON-RPC names, not 1.0's.
> - All eight § 9.4 method sections use PascalCase.
>
> Registering the slash spellings would have advertised 1.0 conformance that the
> 1.0 TCK then fails — the failure mode D-B was ratified to avoid. **1B therefore
> shipped `SendMessage` + `GetTask` only**, and a regression test asserts the
> slash names are NOT registered.
>
> The issue's own text supports this reading (it greps for "`message/send`,
> `tasks/get`, `agent-card.json`, or the 1.0 PascalCase method names" as things
> ABSENT); the error is this plan's transcription of that absent-list as the
> target list. Recorded on #2203.
>
> **Consequence for scope:** v1.0 defines **11** JSON-RPC methods, not 2. 1B
> delivered the 2 the plan budgeted for. The remaining 9 are real, un-planned
> surface — tracked as **1C** below, NOT silently absorbed and NOT dropped.

**Original status line:** `/todos` plan approval is a structural human gate
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

## Wave 1 — A2A → 1.0 (est. 1–2 cycles, 2 shards → **3**, see 1C)

Smaller, independent of MCP, and it retires the 0.2.x surface we currently advertise.
Sequenced first so the conformance-gating wave has at least one conformant surface to
gate against.

**Invariant surface: 4** — path consistency across all 4 sites · agent-card schema
validity · JSON-RPC method-name contract · no 0.2.x path left serving.

**Re-measured after 1B:** the method-name contract turned out to carry three
sub-invariants the count above folded into one — PascalCase method naming,
camelCase field naming, and ProtoJSON enum encoding — each independently
falsifiable and each now pinned by its own test. Still within bound B; recorded
because the original "4" understated it, and 1C inherits all three.

| shard            | scope                                                                                                                                                                                                                                | budget notes                                                                                                              |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------- |
| **1A** ✅ LANDED | Well-known path `/.well-known/agent.json` → `/.well-known/agent-card.json` across all FOUR sites (`service.py:175` endpoint, `service.py:11` docstring, `models.py:84`, `agent_card.py:209`), plus card derivation to the 1.0 shape. | Small LOC, but 4 sites in 3 files — the trap directive 3 names. Renaming only the endpoint leaves three stale references. |
| **1-AUTH** ✅ LANDED | Verify bearer tokens in the request path; hand handlers a verified `CallerIdentity` instead of a raw string; fail closed when no verifier is configured; pin token audience to this agent. | PRE-EXISTING hole, not 1B's, but it GATES 1B — ownership is unenforceable without an identity. BREAKING: `MethodHandler`'s second arg changed type. |
| **1B'** (re-land) | `SendMessage` + `GetTask`, PascalCase per the correction above, PLUS: `owner_id` on `Task` enforced in BOTH `GetTask` and the existing-task branch of `SendMessage`; server-derived `role`; the 12 correctness findings from the reverted attempt (chief among them `historyLength > len(history)` returning `hl − n` messages via a negative slice, and an unknown client-supplied `taskId` creating a task instead of raising `TaskNotFoundError` — three spec MUSTs in § 3.4.2). | Blocked on 1-AUTH. The reverted code is recoverable from `6e4e652da`; do NOT re-apply it wholesale — it carries the IDOR. |
| **1C** | The remaining **9** v1.0 JSON-RPC methods: `SendStreamingMessage`, `ListTasks`, `CancelTask`, `SubscribeToTask`, `GetExtendedAgentCard`, and the four `*TaskPushNotificationConfig` methods. | NOT in the original plan — surfaced by the 1B method-set correction. Two are **streaming** (SSE), a different transport concern from 1B's request/response pair, so this is very likely ≥2 shards. Size it at `/todos` before starting; do not treat it as a tail of 1B. |

**Open question for 1A, to settle at implementation:** whether the 0.2.x path keeps serving
during a deprecation window. `feedback_no_shims` says remove shims immediately rather than
carrying deprecation timelines — so the default here is a hard cutover, but this is a
published protocol surface, so flagging it rather than assuming.

---

## Wave 2 — MCP → Modern (`2026-07-28`) (est. 2–4 cycles, 4 shards)

Architectural. The server is Legacy by construction — built around `initialize`, with no
`server/discover` and no `resultType`. This is NOT a version-string bump and must not be
sharded as one.

**Invariant surface: 7** — version negotiation correctness · per-request version metadata ·
`resultType` present on EVERY result · `server/discover` completeness · no `initialize`
path left reachable · no `ping` path left reachable · error-taxonomy preservation across
the handshake removal.

That is at the top of bound B's base ceiling (5–10), which is why it is 4 shards and not 2.

| shard  | scope                                                                                                                             | budget notes                                                                                                           |
| ------ | --------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| **2A** | Version negotiation + per-request version metadata. Replaces the `server.py:74` tuple `("2025-06-18","2025-03-26","2024-11-05")`. | Foundation — 2B/2C/2D all depend on it. Sequential, not parallel.                                                      |
| **2B** | `server/discover` surface (a MUST in 2026-07-28; currently absent).                                                               | Net-new.                                                                                                               |
| **2C** | `resultType` on every result (required on every result; currently absent).                                                        | Touches every result-producing path — the broadest shard. Watch the 500-LOC load-bearing ceiling; split if it exceeds. |
| **2D** | Retire `initialize` (21 refs) and `ping` (5 refs).                                                                                | Deletion shard, LAST — removing the handshake before 2A–2C land would leave no working path.                           |

**2A → (2B ‖ 2C) → 2D.** Only 2B and 2C are parallelizable; 2A gates them and 2D follows.

---

## Wave 3 — Conformance gating + the TCK hook (est. 1 cycle, 2 shards)

**Invariant surface: 3** — the TCK hook fails closed when unset · per-requirement gating
by name · no skip counted as a pass.

| shard  | scope                                                                                                                                                                                                                                                                                                                                                                     | budget notes                                                                                                                                                                       |
| ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **3A** | D-C: `messageId`-prefix recognition behind an env flag defaulting **OFF** and failing closed. Reviewed as a security surface — `security.md` § Secure-Default For A New Security Feature applies, and per `agents.md` § "Correctness-Review-Clean Is Not Security-Clean" this needs BOTH a correctness reviewer AND an adversarial security-reviewer before it converges. | Production code that changes behaviour on attacker-influenceable input.                                                                                                            |
| **3B** | Wire both conformance suites into CI, **gated per-requirement by name — never on absence of failures.** Both suites skip capability-gated tests, and to a failure-counting gate a skip and a pass are the same colour.                                                                                                                                                    | This is the same non-discriminating-instrument shape this workspace has hit repeatedly (`instrument-discipline.md` MUST-1). A green count is not the gate; named requirements are. |

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
