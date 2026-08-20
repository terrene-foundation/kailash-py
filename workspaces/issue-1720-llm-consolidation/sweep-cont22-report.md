# /sweep — Management Decision Report (cont-22)

main `a4149f284` · 0 open PRs · **47 open issues** · 1 new since cont-21 · 1 closed by fix

Every "complete" claim cites a durable receipt. No self-attested completion.

---

## 1. Completion status

| item | receipt |
| --- | --- |
| #2201 four ollama stacks converged | merged `a4149f284` (PR #2202), issue auto-closed |
| cont-21 close-out (sweep + notes) | merged `9f461c673` (PR #2200) |
| loom Gate-2 sync repaired + landed | merged `b44c65b27` (PR #2198) |

**Verified on main after merge** — the invariant the ollama issue was about:

```
11436 kailash_ollama_models    11437 kailash_ollama_models
11435 kailash_ollama_models    11435 kailash_ollama_models
```

One volume across all four stacks; 11434 free for a native `ollama serve`.

### Is the product complete and visible?

**No — and #2203 moves the answer further away, correctly.** Two protocol surfaces
we advertise are pinned to superseded revisions, and the MCP gap is architectural
rather than a version bump (§ 3). That is newly-visible scope, not regression.

---

## 2. ETA to completion — in autonomous cycles

**~6–9 cycles**, up from cont-21's 4–6. The increase is entirely #2203.

| bucket | items | est. cycles |
| --- | --- | --- |
| **#2203 MCP → Modern revision** (architectural; see § 3) | 1 | **2–4** |
| **#2203 A2A → 1.0 line** (path rename + method set + card derivation) | 1 | **1–2** |
| **#2203 conformance suites wired into CI, gated per-requirement** | 1 | 1 |
| Sweep-5 spec orphans + coverage gaps (52 + 18, ML-concentrated) | 70 | 2–3 |
| Un-gated HTTP surfaces (#2141, #2142) | 2 | 0.75 |
| #2166 / #2194 — blocked on authz-schema decisions | 2 | 1 after decision |
| Correctness set (#2138, #2151, #2153, #2162, #2163, #2172, #2175) | 7 | 1 |
| Docs/claim accuracy (#2168, #2170, #2171, #2173) | 4 | 0.5 |

---

## 3. Prioritized immediate queue

Value anchor: the co-owner's directive this block — *"get all the new gh issues in,
esp a2a and mcp that we want to prioritize."*

### 1. #2203 — MCP + A2A protocol drift (HIGHEST, per co-owner)

**Re-derived against main; every in-repo claim holds**, with one scoping correction.

**MCP is two revisions behind and the gap is architectural, not a version string.**
Measured in `src/kailash/trust/mcp/`:

```
server/discover   -> 0    (a MUST in 2026-07-28)
resultType        -> 0    (required on every result in 2026-07-28)
initialize        -> 21   (the Legacy handshake the Modern revision removes)
ping              -> 5    (removed in 2026-07-28)
```

`server.py:74` declares `("2025-06-18", "2025-03-26", "2024-11-05")`. The server is
Legacy by construction — built around `initialize`, with no `server/discover` and no
`resultType`. The spec's own compatibility matrix rates Modern client → Legacy server
as **"Fails."** So this is not additive: a client that dropped legacy support cannot
talk to us at all.

**A2A serves the 0.2.x well-known path.** `/.well-known/agent.json` is current;
1.0 serves `/.well-known/agent-card.json`. **Correction to the issue:** that path
appears in **4 files**, not the single `service.py:175` cited — also `service.py:11`
(docstring), `models.py:84`, `agent_card.py:209`. A rename touches all four.

The 1.0 method set is absent: `message/send`, `tasks/get`, `agent-card.json`,
`SendMessage`, `GetTask` all return 0 hits, against a control (`jsonrpc` → 23)
confirming the grep works on that tree.

### 2. Sweep-5 orphan corpus — 52 orphans / 18 coverage gaps

Unchanged from cont-21 (85 specs, 162 symbols), consistent with no spec or symbol
changes merging since. ML-concentrated: `ml-feature-store` (8/1), `ml-tracking` (7/3),
`ml-engines-v2` (6/1), `ml-registry` (5/0).

### 3. #2141 / #2142 un-gated HTTP surfaces — #2141 blocked on a decision, not on work.

### 4. loom#1826 — filed upstream, awaiting loom. Nothing for this repo to do.

---

## 4. Sweep results

**Sweep 4** — enumerated unfiltered; `--no-merged` used only as a ranker. 3 non-main
remote refs: `docs/notes-cont18-execution` and `fix/2070-logging-hook-redaction-defeat`
(both believed superseded, neither re-verified). 169 local branches, 1 worktree.

**Sweep 5** — repo-level-specs mode, option (a) run over all 85 specs:
`symbols=162 orphans=52 coverage_gaps=18 stubs=0`. Identical to cont-21.
**The `--all` invocation still reports `specs=0 … OK` on this repo** — it scans
`workspaces/*/specs`, which is empty here. Never cite that sentinel.

**Sweep-N** — deferred-quality backlog **empty**; no revisit gates fire.

**Closure step 2** — `threshold=3 runs=43 keys=0 escalations=0`.

---

## 5. Decision points

**D-A (NEW, gates #2203 MCP) — which MCP revision do we target?**
*Option Modern (`2026-07-28`):* conformant with current clients; per-request version
metadata, `server/discover`, `resultType`. Cost: an architectural change to a server
built on `initialize`, 2–4 cycles. *Option Legacy-latest (`2025-11-25`):* one revision
forward, keeps the handshake, ~1 cycle — but still "Fails" against a Modern client, so
it buys currency without buying interop. **Recommend Modern**, precisely because the
compatibility matrix makes Legacy a dead end rather than a slower path.

**D-B (NEW, gates #2203 A2A) — which A2A line, 1.0 or 0.3?**
*1.0:* stable TCK pinned to a released spec commit, so "passes the TCK" and "conforms
to the release" are the same claim. *0.3:* TCK is beta (`0.3.0.beta5`) with a spec
baseline snapshotted from `main` before `v0.3.0` was tagged — the two claims come
apart. **Recommend 1.0.** Con, stated: 1.0 is a larger jump from our 0.2.x surface.

**D-C (NEW) — the TCK is not black-box.** Its `SUT_REQUIREMENTS.md` needs the system
under test to recognise `messageId` prefixes, i.e. a test-only mode in production code.
*Recommend* gating that mode behind an env flag that fails closed, and reviewing it as
a security surface rather than test scaffolding.

**D1 — #2141 `--auth` semantics** (+ whether it goes through a kailash-ml release).
Unchanged; spec §8.3 cannot settle it — two of its claims are false against the code.

**D2 — #2166 / #2194 authz schema.** No per-principal identity exists to derive an
actor from. Unchanged.

**D3 — `mcp_channel.py:961`** `len(registry) >= 0` can never report unhealthy.
Note this is adjacent to #2203 but distinct: a health check, not a protocol revision.

**D4 — Sweep-5 orphan corpus.** Recommend a scoped first pass on `ml-feature-store` +
`ml-tracking` (15 orphans, 4 gaps) to measure the spec-over-promised vs source-missing
ratio before committing to all 70.

**D5 — 169 local branches.** Unchanged: leave, audit separately.

---

## 6. Recommendation

1. **Ratify D-A and D-B** — #2203 is the co-owner's stated priority and both halves
   are blocked on a target-revision decision, not on implementation capacity.
2. **Wire both conformance suites into CI gated per-requirement by name**, not on
   absence of failures. Both suites skip capability-gated tests, and to a
   failure-counting gate a skip and a pass are the same colour — the same
   non-discriminating-instrument shape this workspace has hit repeatedly.
3. **Do not quote the A2A `compliance_badge`.** It is emitted by running the tool
   against your own endpoint and is conferred by nobody.
4. D1/D2 remain blocked on you; nothing else is.

**Pattern from this block:** #2203 is the same class the last three blocks kept
surfacing, one layer out — a version string that asserts a capability the
architecture does not have, and a conformance score that would read green off
skipped tests. The fix in both cases is to gate on named requirements rather than
on the absence of red.
