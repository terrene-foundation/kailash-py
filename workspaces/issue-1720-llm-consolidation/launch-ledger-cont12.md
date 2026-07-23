# Launch Ledger — cont-12 (2026-07-22) — F2 deferred-quality reconcile + drive

Durable orchestration ledger per `orchestration-launch-ledger.md` MUST-1. Consult BEFORE every spawn; match every completion against it.

## Objective

User: "continue from last session, /autonomize with as many parallelized workflows as possible and /redteam to convergence."

cont-11 shipped #1918 + #1919 to PyPI (kaizen-agents 0.11.5 / kailash-pact 0.18.0), both live + verified. Board clean (0 open PRs, main @ c54fc9df1). Remaining tracked follow-ups:

- **F1** — cross-SDK #1919 → Rust SDK MCP-governance check. BLOCKED on user cross-repo authorization (private repo; repo-scope-discipline — cannot self-authorize). Surface a SPECIFIC ask (handoff-completion MUST-3).
- **F2** — deferred-quality backlog (all INCREMENTAL last session) + 1 latent print_mode finding. Reconcile-first (wave-loop MUST-7), then execute worthwhile hardening, dispose by-design with rationale.

## F2 items to reconcile (from cont-11 ledger)

| ID                        | Claim                                                                                                                 | Prior disposition                      |
| ------------------------- | --------------------------------------------------------------------------------------------------------------------- | -------------------------------------- |
| DQ-1919-casevariant       | `Tenant_Id`/` tenant_id` case-variant survives literal `!= "tenant_id"` scrub into AUDIT echo only (no decision infl) | INCREMENTAL — optional case-norm scrub |
| DQ-1919-direct-enforcer   | direct enforcer.check_tool_call (bypass middleware) echoes arbitrary metadata to audit                                | INCREMENTAL — pre-existing generic     |
| DQ-1919-warnflood         | DeprecationWarning flood only under caller's own simplefilter("always")                                               | LOW — config not SDK                   |
| DQ-1918-caseprefix        | registry `_MODEL_PREFIX_MAP` startswith case-sensitive (`Claude-`→openai default)                                     | INCREMENTAL — same dest pre/post       |
| LATENT-printmode-maxturns | print_mode.py:56-68 max_turns-override branch rebuilds KzConfig OMITTING base_url+api_key (#1899-class)               | Out-of-scope #1918; decide at wrapup   |

## Wave tracker (durable)

| track           | agent               | branch/scope                                                     | status                                                               |
| --------------- | ------------------- | ---------------------------------------------------------------- | -------------------------------------------------------------------- |
| RECON-pact-1919 | Explore (read-only) | reconcile DQ-1919 casevariant/direct-enforcer/warnflood vs main  | **DONE** — all 3 WONT-FIX                                            |
| RECON-kaizen    | Explore (read-only) | reconcile DQ-1918-caseprefix + LATENT-printmode-maxturns vs main | **DONE** — caseprefix WONT-FIX; printmode STALE (fixed by e586eb30f) |

## RECON VERDICTS (evidence-backed, HEAD c54fc9df1)

**ALL of F2 is WONT-FIX or STALE. No local fix warranted → no release cycle.**

- **DQ-1919-casevariant** — WONT-FIX. Scrub is literal `k != "tenant_id"` (middleware.py:130,217; types.py:476,594); case-variant survives into AUDIT echo ONLY. Decision read doubly inert: `_resolve_effective_tenant` (enforcer.py:152) exact-match `.get("tenant_id")` AND #1919 severed metadata→decision (returns None on that path). Audit echoes ALL client metadata by design.
- **DQ-1919-direct-enforcer** — WONT-FIX. `**(context.metadata or {})` audit splat (enforcer.py:374,460) reachable only by TRUSTED internal callers (middleware is the network boundary + scrubs). No trust-boundary crossing; decision unaffected.
- **DQ-1919-warnflood** — WONT-FIX. Static-message `DeprecationWarning` (enforcer.py:154-163) dedups once-per-site; str-guard; flood requires caller's own `simplefilter("always")`. Config-not-SDK; weaker mode opt-in (default `require_caller_identity=True`, types.py:245).
- **DQ-1918-caseprefix** — WONT-FIX (low-value). `_MODEL_PREFIX_MAP` startswith case-sensitive (registry.py:274); no real caller supplies capitalized prefixes (vendor slugs lowercase). Optional 1-line `model.lower()`; not a bug.
- **LATENT-printmode-maxturns** — STALE / CLOSED. print_mode.py has ONE `KzConfig(...)` (line 57, max_turns branch), copies ALL 12 fields incl `base_url`(L66)+`api_key`(L67), authored by e586eb30f (PR #1922 fold). #1899-class drop closed.

**Disposition:** F2 cleared — record WONT-FIX rationale, do NOT re-queue at /sweep. No code change → no redteam-to-converge (manufacturing a change = recommendation-quality clean-gate violation).

## F1 (cross-SDK) — USER AUTHORIZED "file if found" (AskUserQuestion genuine turn)

Target: Rust SDK (esperie-enterprise/kailash-rs, private). Sequence: /cross-repo-authorize (receipt) → READ-investigate MCP governance tenant surface → if #1919-class gap, draft SCRUBBED issue (upstream-issue-hygiene MUST-2/3) → confirm exact body with user (MUST-1) → file.

| track          | agent                       | branch/scope                                                      | status                                           |
| -------------- | --------------------------- | ----------------------------------------------------------------- | ------------------------------------------------ |
| F1-authorize   | /cross-repo-authorize       | write receipt esperie-enterprise/kailash-rs (committed 249ce99d6) | **DONE**                                         |
| F1-investigate | orchestrator (gh api reads) | Rust SDK eatp MCP governance tenant surface                       | **DONE — NO GAP**                                |
| F1-adversarial | Explore (bg)                | adversarial refutation of "no gap"                                | **DONE — NO GAP (all 5 axes, could not refute)** |

## F1 CONVERGED — NO GAP, NOTHING FILED

Two independent confirmations (orchestrator direct reads + adversarial refutation) agree: no #1919-class gap in the Rust SDK MCP governance. Adversarial adds: real `run_sse` TCP regression tests (`sse_http_transport_trusted_self_asserted_gate_denies_over_network`, `governed_delegate_keys_on_verified_subject_not_params_agent_id`) prove network body-asserted identity cannot spoof; tenant logic lives in eatp `vault/*` but MCP dispatch reaches 0 of it. Finding-class mechanically disproven → NOT running further rounds (recommendation-quality clean-gate). Per user "file if found" → **NO issue filed** (correct; would be noise). Receipt 249ce99d6 = the durable cross-repo audit trail; reads only, no Rust write. F1 CLOSED.

## F1 INVESTIGATION — NO #1919-CLASS GAP IN RUST SDK (evidence, kailash-rs/main)

Rust MCP governance = `crates/eatp/src/mcp/governance.rs` (sibling of Python pact MCP middleware). The #1919 gap CANNOT exist here — different, already-hardened architecture:

1. **Zero tenant concept in the MCP path.** `grep -ci tenant` across eatp mcp module = 0 (governance/mod/tools/resources/jsonrpc). `CallerIdentity` (governance.rs:71) has ONLY `subject` + `issuer` — NO tenant field. No tenant-keyed MCP decision to spoof.
2. **CallerIdentity un-forgeable from client params.** governance.rs:61-63: "intentionally derives no Serialize/Deserialize, so a caller cannot forge one by placing fields in the JSON-RPC params." Subject from an AUTHENTICATED source (verified bearer token) only.
3. **Network transport fail-closes self-asserted identity.** `authorize()` (governance.rs:385+): no-verified + (opt-in OFF or network)→DENY. `run_sse` passes `permit_self_asserted=false` (mod.rs:328, closing prior #1518 redteam HIGH). Regression test `self_asserted_refused_on_network_transport_even_when_granted` (governance.rs:627).
4. **Prior hardening = Rust-side equivalent of #1919.** Comments cite #1498 (out-of-band caller identity) + #1518 (network fail-closed) — structurally predate + prevent the #1919 client-metadata-tenant-spoof class.

**Disposition:** gap NOT found → per user "file if found" → do NOT file. Confirm via adversarial verifier convergence, then close F1 (receipt = audit trail; no cross-repo write).
