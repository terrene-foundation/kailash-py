# /sweep — Management Decision Report (cont-21)

main `b44c65b27` · **6 PRs merged this block** · **0 open PRs** · 46 open issues ·
2 issues filed upstream to loom

Every "complete" claim below cites a durable receipt. No self-attested completion.

---

## 1. Completion status

### The COC artifact update landed, and the defect it carried did not

The 2026-08-19 loom Gate-2 distribution is in, with its path-mapping defect repaired
rather than merged as delivered.

| item | receipt |
| --- | --- |
| #2192 mounted-subapp auth tristate | merged `c23836a17` |
| #2123 loom Gate-2 sync (2026-08-13) | merged `6fb3f5d0f` |
| #2195 #2189 sweep fixes + deadline flake | merged `257113226` |
| #2196 / #2197 session notes | merged `8293d7e28` / `15caf73ee` |
| #2198 loom Gate-2 sync (2026-08-19), repaired | merged `b44c65b27` |

**Post-merge invariant verified on main, in the direction that can fail:**

```
files at top-level codex/ or gemini/:  0
installed .codex: 477   .gemini: 476
.codex/skills/wrapup/SKILL.md   PRESENT
.gemini/skills/wrapup/SKILL.md  PRESENT
```

### Is the product complete and visible?

**The delivery surface is healthy; the correctness backlog is larger than it looked.**
Sweep 5 was run properly for the first time on this repo shape and surfaced 52 spec
orphans + 18 coverage gaps that the tool's own `--all` path reports as clean (§ 4).

---

## 2. ETA to completion — in autonomous cycles

**~4–6 cycles**, up from cont-20's 3–4. The increase is not regression; it is the
Sweep-5 corpus becoming visible for the first time.

| bucket | items | est. cycles |
| --- | --- | --- |
| Sweep-5 spec orphans + coverage gaps (52 + 18, ML-concentrated) | 70 findings | 2–3 |
| Un-gated HTTP surfaces (#2141, #2142) | 2 | 0.75 |
| #2194 governance actor provenance — needs schema decision | 1 | 0.5 after decision |
| #2166 `check_session_access` — needs authz schema | 1 | 0.5 after decision |
| Correctness set (#2138, #2151, #2153, #2162, #2163, #2172, #2175) | 7 | 1 |
| Docs/claim accuracy (#2168, #2170, #2171, #2173) | 4 | 0.5 |

---

## 3. Prioritized immediate queue

Value anchor: the co-owner's directives this block — *"resolve the gaps at root cause"*,
*"I dont want to waste cycles"* — i.e. fix causes, not symptoms, and do not re-pay for
the same discovery twice.

1. **Sweep-5 orphan corpus (52 orphans / 18 coverage gaps).** Highest yield and newly
   visible. Concentrated in ML specs: `ml-feature-store` (8/1), `ml-tracking` (7/3),
   `ml-engines-v2` (6/1), `ml-registry` (5/0). An orphan is a spec promising a symbol
   the source does not have — the `orphan-detection.md` § 1 class.
2. **#2141 / #2142 un-gated HTTP surfaces.** #2141 is blocked on the `--auth` semantics
   decision (§ 5 D1), not on implementation.
3. **loom#1826** — filed upstream, awaiting loom. Nothing for this repo to do.
   (A second filing, loom#1827, was withdrawn the same session: it duplicated loom's already
   shipped T4 fix and repeated an over-claim loom had already narrowed. Recorded in the notes
   as a trap rather than quietly deleted.)
4. **#2199** — local tracker for the Gate-2 defect; closes when a clean re-emit verifies.

---

## 4. Sweep results

**Sweep 4 — branch enumeration (unfiltered; `--no-merged` used only as a ranker).**
4 remote refs, of which 2 survive `--no-merged`; the 1 the filter would have hidden is a
candidate, not a non-finding. No `worktree-agent-*` harness orphans. Remaining non-main
remote refs: `docs/notes-cont18-execution` (superseded), `fix/2070-logging-hook-redaction-defeat`
(superseded by #2101). **169 local branches**, 1 worktree (the main checkout).

**Sweep 5 — repo-level-specs mode, option (a) genuinely run.**
`spec_count=0` (no `workspaces/*/specs`) AND `specs/` exists → repo-level mode.
`spec-corpus-conformance.mjs` is absent here, but `tools/sweep-redteam.py` accepts a
repo-level spec path, so option (a) was runnable and was run over all 85 specs:

```
spec files scanned : 85 / 85
MUST symbols found : 162
orphans            : 52
coverage_gaps      : 18
stubs              : 0
```

**Tooling finding, and it is the reason this was never seen before:** invoking the tool
as documented — `tools/sweep-redteam.py --all` — returns
`<!-- sweep-redteam:v1:OK specs=0 symbols=0 orphans=0 coverage_gaps=0 stubs=0 -->` on
this repo, because `--all` scans `workspaces/*/specs/**/*.md`, which is empty here. A
`specs=0 ... OK` sentinel is a **vacuous green**: it reports the same value whether the
corpus is clean or unexamined. That is the § 6a failure mode wearing the tool's own OK
sentinel, and it is why the 52 orphans sat unreported.

**Sweep-N — deferred-quality backlog: EMPTY.** `gh issue list --label deferred-quality`
returns nothing; no revisit gates fire.

**Closure step 2 — unadjudicated-escalation:** `threshold=3 runs=43 keys=0 escalations=0`.
No standing `manual-supplement-required` streak.

---

## 5. Decision points

**D1 — #2141: what does `--auth` mean?** Recommend making it a require-authentication
switch wired to the shared `resolve_server_auth` helper. *Pro:* it is the only reading
under which the CLI's own refusal message is true, and it reuses the gate 8 core servers
already use. *Con, real:* dependency floor rises `kailash>=2.31.0` → `>=2.63.0`; it
changes behaviour on a released CLI (`--host 0.0.0.0 --auth x` currently serves openly
and would then refuse without a credential); and it needs a kailash-ml release to reach
users. Spec §8.3 cannot settle it — two of its claims are false against the code.

**D2 — #2194: governance API actor schema.** No per-principal identity exists to derive
a grantor from (`verify_token` returns the constant `"authenticated"`). Three options in
the issue. *Recommendation: you specify; guessing ships a wrong authz check.*

**D3 — `mcp_channel.py:961`.** `len(registry) >= 0` can never report unhealthy; siblings
use `> 0`. *Pro of fixing:* removes a check that cannot discriminate. *Con:* a tools-only
MCP channel would start reporting unhealthy, which may be correct for that channel.

**D4 (NEW) — the Sweep-5 orphan corpus.** 52 orphans + 18 coverage gaps, ML-concentrated.
*Pro of taking it now:* it is the largest correctness surface open and newly measured.
*Con:* an orphan can mean either "source is missing the symbol" or "spec over-promised" —
the tool cannot adjudicate which, so each needs a judgment call. Recommend a scoped first
pass on `ml-feature-store` + `ml-tracking` (15 orphans, 4 gaps) to establish the ratio
before committing to all 70.

**D5 — 169 local branches** (carried from cont-20 D3, unchanged). Recommend: leave;
audit as a separately scoped task.

---

## 6. Recommendation

1. **Ratify D1 and D2** — both are blocked on a schema decision, not on work.
2. **Take D4's scoped first pass** (`ml-feature-store` + `ml-tracking`) to measure the
   spec-over-promised vs source-missing ratio before sizing the rest.
3. **Watch the next loom sync** for the Gate-2 regression: on the next sync branch,
   `git ls-tree -r --name-only <branch> -- codex gemini` must be empty. Checking that
   `.codex/` is populated will NOT catch it — it was populated throughout the incident.

**The pattern worth carrying from this block:** three separate things reported success
without having measured anything — a Gate-2 sync that "delivered" 38 artifacts to paths
no CLI reads, a `--all` sweep that returned OK over zero specs, and a rule governing
push-time that can never load at push time. Each was individually plausible and each
required asking the same question: *what result would this produce if the thing it
checks were false?*
