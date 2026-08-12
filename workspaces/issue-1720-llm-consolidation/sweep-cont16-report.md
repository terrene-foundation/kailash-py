# /sweep — Management Decision Report (cont-16)

main `f8056b2ca` · **13 PRs merged** · **36 issues open** · 2 PRs open

Every "complete" claim below cites a durable receipt (merged PR / verified issue state), per
`verify-resource-existence.md` MUST-4. No self-attested completion.

---

## 1. Completion status

### Landed this session (13 PRs, receipts = merge commits)

| PR                      | Closes       | What it bought                                                         |
| ----------------------- | ------------ | ---------------------------------------------------------------------- |
| #2064                   | Refs #2025   | **A live full SSRF closed.** `?_url=` redirected the proxy anywhere    |
| #2090                   | (round 2)    | CORS credential parity, C1 charset, docstring-example break            |
| #2066                   | #2060        | **Every OAuth login was failing.** #2035's identity binding now live   |
| #2063                   | #2041        | SecretManager no longer invents an unrecoverable encryption key        |
| #2068                   | #2030, #2022 | Agent I/O off INFO; config errors no longer reported as bad LLM output |
| #2094                   | #2070        | LoggingHook payload disclosure + redaction opt-in silently defeated    |
| #2077                   | #2023        | Per-step sibling-install declarations + lint                           |
| #2080                   | —            | MCP tool auto-registration was dead for every agent                    |
| #2071                   | —            | `#2015` sweep scoped first-party (78,152 → 4,781 files; 379s → 8.3s)   |
| #2061 #2062 #2082 #2093 | —            | Session records                                                        |

**Both CRITICALs from the wave are closed**: #2041 (via #2063) and the SSRF (via #2064).

### Is the product complete and VISIBLE?

**No — and one gap is user-facing.** `#2072` is open: a default `create_gateway()` serves
**anonymous arbitrary workflow execution**, proven under uvicorn on a real socket (the workflow
actually ran). Until task #27 lands, the walking skeleton stands on an unauthenticated default.

### Committed-scope fraction

Of the 22 original outstanding issues, **11 closed in prior sessions + 5 more this session**
(#2041 #2060 #2030 #2022 #2070). The remainder plus **19 newly-filed, evidence-backed issues**
constitute the current backlog. The issue count rose 23 → 36; **that is discovery, not drift** —
each new item carries a measurement.

---

## 2. ETA to completion — in autonomous cycles

**To a complete + visible product: ~4–6 sessions** for the BUG + INVEST-NOW set.

| Bucket                                                     | Items | Est. cycles |
| ---------------------------------------------------------- | ----- | ----------- |
| #2072 fail-closed middleware (task #27)                    | 1     | 1           |
| CI-can't-run chain (#2078 → #2081/#2079/#2002)             | 4     | 1.5–2       |
| Key-generation class (#2083, #2092)                        | 2     | 0.5         |
| Auth/actor (#2047, #2088, #2089, #2040)                    | 4     | 1           |
| Remaining BUGs (#2052 #2056 #2057 #2069 #2086 #2000 #2010) | 7     | 1–1.5       |

Basis: single-shard items at ~0.25 cycle; #2078 is the long pole because the runner cannot
complete Tier-2 at all, so it is diagnose-then-fix rather than fix.

---

## 3. Prioritized immediate queue (BUG + INVEST-NOW, value-ranked)

Value-anchor for the whole queue: the co-owner's standing directive in this session —
_"burn down the buckets"_ — plus the two explicit approvals recorded below (fail-closed auth;
land-verified-value-then-gate). Ranked by user-facing exposure.

1. **#2072 — anonymous arbitrary workflow execution** (task #27, approved fail-closed).
   _Implication:_ a default deployment executes attacker-chosen workflows. Highest exposure open.
2. **#2083 — JWT HS256 signing secret auto-generated.**
   _Implication:_ tokens die at restart; replica A's tokens rejected by replica B. Announced at INFO.
3. **#2092 — kaizen AES-256-GCM key auto-generated, entirely silently.**
   _Implication:_ unrecoverable data after restart, with nothing in the logs.
4. **#2078 — Tier-2: 232 CI failures from thread/fd exhaustion.**
   _Implication:_ blocks #2038's merge-gate AND #2002. The keystone of the CI chain.
5. **#2084 — four observability subsystems advertised, none implemented.**
   _Implication:_ `enable_audit=True` records nothing; the banner printed fake endpoints.
6. **#2047 — MFA has no actor concept.**
   _Implication:_ the (now-live) audit trail records _what_ and _whose_, never _by whom_.
7. **#2074 — 855 kaizen tests in no CI invocation** · **#2002** — root regression likewise.
8. **#2086 #2069 #2088 #2089 #2040 #2052 #2056 #2057 #2000 #2010 #2011 #2044 #2039** — remainder.

---

## 4. Deferred-quality backlog — ALL SIX ARE INVALID DEFERS

`gh issue list --label deferred-quality` → **#2011 #2017 #2018 #2019 #2020 #2021**.

Per skill §3, a valid defer carries four sections: blocking-safety note, value-anchor,
acceptance criteria, revisit trigger. **Spot-check measured 1–2 keyword matches, not 4 sections.**
None carries a value-anchor citing a user-anchored source.

**Consequence (`product-completion-first.md` MUST-2):** these are silent deferrals, which is
BLOCKED — not valid deferred-quality items. All six are **≥2 sessions old**, so
`value-prioritization.md` MUST-3's "still wanted?" gate fires on every one.

**This is the second consecutive sweep to find them invalid.** They were flagged in the prior
session and nothing changed — which is precisely the decay pattern the label exists to prevent.

**Disposition required per item — user-gated, no auto-close** (`value-prioritization.md` MUST-4).

---

## 5. Decision points for the co-owner

**D1 — #2073 (observability flags): raise, or wire the manager that exists?**
The lane found `ObservabilityManager`/`TracingManager` DO exist with `BaseAgent.enable_observability()`
wired to them; `smart_defaults` imported a _different_, nonexistent set.
_Pro raise-now:_ honest immediately, reversible, forecloses nothing. _Con:_ BREAKING across two
public constructors, and if wiring is feasible we ship a break then reverse it.
_Pro wiring:_ non-breaking AND delivers the feature. _Con:_ feasibility unverified — return types
differ, handler methods absent on both.
**Recommendation:** spend ~0.5 cycle establishing wiring feasibility BEFORE landing #2073. If
feasible, wire; if not, land the raise. **#2073 stays held meanwhile.**

**D2 — the six invalid deferred-quality items.**
_Recommendation:_ re-triage as ordinary BUGs (they are channel/MCP lifecycle defects: #2018–#2021
are real shutdown-correctness bugs), rank them into the normal queue, and **retire the
deferred-quality label** on them rather than re-authoring four sections for items nobody has
picked up in two sessions. _Con:_ loses the explicit revisit trigger. _Pro:_ stops laundering
real bugs through a label that has now failed its own validity test twice.

**D3 — #2031 (draft codify PR).**
Carries two pre-existing gating questions (baseline-vs-path-scoped; ships with no probe set,
which `coc-artifact-eval-coverage.md` MUST-1 requires). Untouched this session.
_Recommendation:_ close it or resolve the two questions in a dedicated cycle; it has been open
across multiple sessions as a draft.

---

## 6. Recommendation — next steps, for ratification

1. **Task #27** (#2072 fail-closed middleware) — approved, unblocked, highest exposure. Start here.
2. **#2078** — the CI keystone. Until it lands, "CI is green" carries no information about Tier-2
   or the regression suites, and #2002/#2038/#2081/#2079 all stay blocked behind it.
3. **D1** — 0.5 cycle on wiring feasibility, then land #2073 one way or the other.
4. **D2** — re-triage the six; stop calling them deferred-quality.
5. **The key-generation class (#2083, #2092)** — both are small, both are on default paths, and
   the class has now produced three instances via three different generators. Sweep by SHAPE.
