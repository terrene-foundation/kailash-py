# Orchestration Launch-Ledger — post-#1947 provider-integrity follow-up forest

Wave 1 (single value-coherent milestone: close the post-#1947 provider-integrity
follow-up forest; 3 independent, file-disjoint, low-invariant shards). Cumulative
invariant surface ≤10 base → one wave per wave-loop MUST-1. No version bump inside
any shard (orchestrator owns the single post-merge bump + release).

| track | issue | agent    | agent_id          | branch                            | files (disjoint)                                                                  | status                                                                                                                                                                        |
| ----- | ----- | -------- | ----------------- | --------------------------------- | --------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A     | #1952 | kaizen-A | a74c2141a82115014 | fix/1952-keyless-mock-fail-loud   | _provider_env.py, agents.py, embedding_generator.py, conftest; +reasoning.py fold | R1 core CLEAN (A-rev+A-sec); reasoning.py same-class fold @63388e031 (orchestrator — kaizen-A hit session-limit) + doc-drift; 78 passed → R2 verify                           |
| B     | #1953 | kaizen-B | abecbbb54f3f8d731 | fix/1953-synthesis-error-masking  | nodes/ai/iterative_llm_agent.py (_phase_synthesis)                                | **CONVERGED** @35a30afef (4 commits: core + L1109/L433/L616 sanitize folds + WARN); R1/R2/R3 exhaustive, all sites dispositioned                                              |
| C     | #1948 | kaizen-C | a10975f8114dc887e | fix/1948-provider-minor-followups | caching mixin, workflow_generator.py, deployment cache                            | **CONVERGED** @48e2ef348 (3 commits: base + item4 effective-prompt fix + docstring); R1 items1-3+temp, R2 item-4 clean (also fixed str(signature) memory-addr cache-miss bug) |

Design call (A/#1952): keyless → fail-loud (return None → #1947 node gate), NOT silent "mock";
explicit provider="mock" preserved. Least-breaking test-harness path chosen by specialist.

Merge order: A → B → C (sequential admin-merge to main after per-shard redteam convergence),
then holistic redteam, then single version bump 2.43.0 → 2.44.0 (minor: #1952 behavior change) + release.

## ALL 3 SHARDS CONVERGED — PRs open, CI running (as of this write)

- A #1956 (fix/1952 @63388e031) — Fixes #1952. CI running (0 fail).
- B #1957 (fix/1953 @35a30afef) — Fixes #1953. CI running (0 fail).
- C #1958 (fix/1948 @48e2ef348) — Fixes #1948. CI running (0 fail).
  A↔C interaction verified safe (C's caching_mixin str()-coerces None; workflow_generator None→node gate; C tests use source-grep not runtime keyless=='mock').
  NEXT: CI green per PR (pin head SHA, read-then-merge separate cmds per git.md) → admin-merge A→B→C →
  holistic redteam on merged main (agents.md §Holistic) → bump 2.43.0→2.44.0 + CHANGELOG on release/v2.44.0 branch → /release.
  Known CI trap (session notes): kaizen FAST-tier "0 selected/8328 deselected" transient on pull_request → re-run, not a code issue.

## Follow-up issues FILED (executed, not implied)

- #1959 Nexus lifecycle (5 pre-existing test_end_to_end_nexus.py failures; C item-5 disposition).
- #1960 error_sanitizer.py redaction gaps (AWS keys, uppercase-hex, Azure endpoint).
- #1961 federated.py:728 raw RAG query cache key logged at INFO.
- STILL PENDING (needs USER cross-repo authorization — repo-scope-discipline): file the Rust-SDK cross-SDK equivalent of #1952 keyless-mock (A-rev flagged; do NOT self-authorize).

## Redteam findings ledger

- B-sec (R1): CLEAN on fix's own surfaces (error/WARN/error_type sanitized via sanitize_provider_error).
  Pre-existing (not regressions): (i) MED — degraded_synthesis inherits raw str(e) from iterative_llm_agent.py:1109
  (MCP fallback stores raw exc in output); SAME-CLASS + 1-line fix (mirror line 1046) → FOLD into B before merge.
  (ii) MED/LOW — error_sanitizer.py regex gaps (AWS keys, uppercase-hex) → separate hardening follow-up issue.
- B fold applied: L1109 (degraded_synthesis) + synthesis WARN parity + L433 (iteration store) all sanitized & committed.
- B R2 found L433 sibling (folded); B R3 CONVERGED: L616 folded (last asymmetry); L491/511/906/910/979/983 proven
  safe-by-construction (base LLMAgentNode sanitizes at return llm_agent.py:1271 + raise :2557) → NO separate audit needed.
- A landed: None-return design, KAIZEN_ALLOW_KEYLESS_MOCK opt-in, embedding fail-loud; 3 unit failures proven pre-existing perf/env.
- C item-4 fixed @c1a79ffaf (path a: key on agent._generate_system_prompt() effective prompt); ALSO fixed 2nd pre-existing bug (str(signature) memory-address repr → cache never hit → signature.to_dict()); real-agent tests; 115 passed → C R2 verify.

## Follow-up issues to FILE (handoff-completion — must execute, not imply)

- Nexus lifecycle: 5 pre-existing test_end_to_end_nexus.py failures (byte-identical on base 4614126bc), separate bug class.
- error_sanitizer.py hardening: AWS-key + uppercase-hex + Azure-endpoint redaction gaps (pre-existing, all sanitized surfaces).
- federated.py:728 logs a raw RAG query cache key at INFO (pre-existing, unrelated to #1948; observability Rule 8).
- ~~iterative_llm_agent error-return sanitization audit~~ — DROPPED: B-r3 proved L491/511/906/910/979/983 safe-by-construction (base-node boundary sanitize); L616 folded into B. No separate issue warranted.
- CROSS-SDK (#1952): Rust SDK likely has the equivalent keyless-mock residual — needs cross-repo authorization to file (repo-scope-discipline); surface to user.
- base_agent.py:601 stale inline comment ("# required; else defaults to mock") — behavior correct, optional 1-line truth-up.

## Wave R holistic redteam (2026-07-25, post-merge on main 6aaacf17)

Union diff: 4614126bc..6aaacf17 (A d5d135052 + B f3439c7c + C 6aaacf17), 14 files all
packages/kailash-kaizen, +1093/-56. Materialized: 04-validate/wave-r-union.diff.

| track           | agent             | scope                                                                        | status    |
| --------------- | ----------------- | ---------------------------------------------------------------------------- | --------- |
| holistic-rev    | reviewer          | union diff: correctness + mechanical AST/grep sweep + cross-shard invariants | in-flight |
| holistic-sec    | security-reviewer | union diff: provider error sanitization, keyless fail-loud, no secret leaks  | in-flight |
| holistic-parity | reviewer(parity)  | closure-parity: 3 issues' AC → delivered code; ledger findings landed        | in-flight |

Wave F recon: agent wavef-recon in-flight (maps #1959/#1960/#1961 → package+still-present).

## Wave F recon result + release strategy (2026-07-25)

Recon (agent wavef-recon, read-only vs main 6aaacf17):

- #1960 error_sanitizer.py — ALL 4 redaction gaps STILL PRESENT (AWS AKIA, 40-char b64 secret,
  uppercase-hex [line 35 is [a-f0-9] lowercase-only], Azure endpoint). INVEST-NOW/security. kaizen.
- #1959 test_end_to_end_nexus.py — 5 failures STILL REPRODUCE (~4 invariants): redeploy dedup
  (deployment.py register no deregister-first; reuse catalog_server:88 pattern), health-status
  ('stopped' — fixture never .start()s app), session datetime (session_manager naive datetime.now),
  session-edge (missing raise). BUG. kaizen integrations/nexus (+ kailash-nexus 2.14.0 health).
- #1961 federated.py:728 — ALREADY EFFECTIVELY MITIGATED: cache_key = sha256(query)[:8] (line 726),
  NOT raw query. Issue premise stale. Residual cosmetic (label "query:" logs a hash). → 1-line touch
  (INFO→DEBUG + reword) + close-with-receipt. NOT a full fix (verify-resource-existence MUST-3).

RELEASE STRATEGY: 2.44.0 = Wave R (provider-integrity #1952/#1953/#1948, converged+merged, releases
after holistic redteam). 2.45.0 = Wave F (follow-up hardening #1960/#1959/#1961). Decoupled — coherent
narratives, Wave R not blocked on unstarted #1959, smaller per-release blast radius.

Wave F shards (file-disjoint, orchestrator owns the single 2.45.0 bump — shards do NOT bump versions):

| shard | issue | files                                          | agent           | status    |
| ----- | ----- | ---------------------------------------------- | --------------- | --------- |
| F1    | #1959 | integrations/nexus/* + test                    | wavef-1959 (bg) | in-flight |
| F2    | #1960 | nodes/ai/error_sanitizer.py + regression tests | (pending slot)  | queued    |
| F3    | #1961 | nodes/rag/federated.py (cosmetic + close)      | (pending slot)  | queued    |

## Wave F progress (2026-07-25)

- F3 #1961 DONE inline (premise stale → cosmetic): PR #1963 (fix/1961-federated-cache-log).
  INFO→DEBUG + label reword + safety comment. federated.py:726 key already sha256[:8].
- F1 #1959: agent wavef-1959 in-flight (worktree).
- F2 #1960: launching now (agent wavef-1960, worktree).
- PR #1962 (authz receipt) CI running.

## Holistic redteam verdicts (2026-07-25) + Wave-R a2a completion

- holistic-rev (correctness): CLEAN, no BUG. Cross-shard None guarded at every consumer.
  INCREMENTAL: str(e) parity fold @iterative_llm_agent.py:511/911/915/984/988 (couldn't prove leak).
- holistic-parity (closure): 44/44 regression PASS (.venv interp; pyenv-stale errored run=zero-evidence, re-ran).
  All 3 ACs delivered, drop correct. FINDING BUG(LOW-MED): a2a.py A2AAgentNode retains
  kwargs.get("provider","mock") shape #1952 removed — 8 sites (1675/1676/1699/1701/1717/1830/1831/1833).
  Not user-visible today (#1947 gates primary path L1691) but same-class residual + AC "every site".
- holistic-sec: idle w/o report → ZERO evidence per evidence-gate; re-queried, awaiting verdict.

Wave-R a2a fix (agent waver-a2a, worktree): behavior-preserving "mock"→None + None-in-skip-discriminator

- keyless-A2A regression test. Rides 2.44.0. Per autonomous-execution MUST-4 (same-class within-budget).

## Wave F2 done + security verdict + str(e) fold (2026-07-25)

- holistic-sec: CLEAN on BUG/INVEST-NOW. Corrected ledger mechanism: str(e) sites safe via
  llm_agent.py:2557 raise RuntimeError(sanitized) (NOT the 1271 return, which is unreachable —
  default _on_error_hook re-raises at 694). ONE INCREMENTAL: iterative_llm_agent.py:911/915/984/988
  bare str(e), safe only via 2557, no local sanitize (future-refactor hazard). Cache keys/keyless/
  secret-in-log all CLEAN.
- BOTH reviewers flagged the str(e) fold → fixing now (Wave-R completion, rides 2.44.0):
  agent waver-strfold, iterative_llm_agent.py 911/915/984/988 → error_msg=sanitize_provider_error(e,"LLM").
- F2 #1960 DONE → PR #1964 (fix/1960-sanitizer-redaction-gaps): AWS AKIA + 40-char b64 + uppercase-hex
  - Azure endpoint; 21 tests. Deliberate broad over-redaction (documented). → 2.45.0.
- CROSS-SDK (#1960): sanitizer redaction gaps LIKELY in Rust SDK (shared trust-plane arch, copy-forward
  pattern). NEEDS USER AUTHORIZATION to file (repo-scope-discipline) — SURFACE, do not self-authorize.

## CRITICAL SEQUENCING (2026-07-25) — do not lose across context boundary

2.44.0 = Wave R ONLY (#1952/#1953/#1948 + a2a completion PR#1965 + strfold fold). Wave-F PRs
(#1963 #1961, #1964 #1960, and #1959's forthcoming PR) MUST NOT merge to main until AFTER
2.44.0 is tagged (kaizen-v2.44.0) — else they leak into the 2.44.0 release. Order:

1. Merge Wave-R completions #1965 (a2a) + strfold-PR (after CI).
2. Round-2 holistic redteam on merged main (a2a + strfold) → 2nd clean round → convergence.
3. Cut 2.44.0: bump pyproject+**init** + CHANGELOG on release/v2.44.0-kaizen → PR → merge → tag → /release.
4. THEN merge Wave-F PRs → Wave-F holistic redteam (incl security-reviewer for #1964 redaction) → 2.45.0.

PR ledger: #1965 a2a (WAVE R, CI pending) | strfold (WAVE R, agent running) |
#1963 #1961 (WAVE F, CI green, HOLD) | #1964 #1960 (WAVE F, CI pending, HOLD) | #1959 (WAVE F, agent running).
a2a.py pre-existing pyright issues (377/383/389 coroutine-await, 3114+ None-subscript) — NOT introduced
by #1952 fix; candidate follow-up, out of release scope.

## Wave F1 #1959 done → PR #1967 (WAVE F, HOLD until 2.44.0 tagged) — REDTEAM FLAGS

- Fixes all 5 test_end_to_end_nexus.py failures. Spans 3 PACKAGES: kaizen (session_manager,
  deployment), kailash core (src/kailash/servers/workflow_server.py deregister_workflow),
  kailash-nexus (core.py Nexus.deregister + start(blocking=False)). → 2.45.0 needs multi-pkg version.
- ⚠ REDTEAM-SCRUTINIZE: ActivityTimestamp(datetime) subclass — a datetime that also answers `> 0`
  via POSIX seconds, introduced to satisfy e2e `channel_activity["api"] > 0` while keeping
  Dict[str,datetime] (30 tests lock datetime). Agent flagged as unusual; alt = fix the test's
  `>0` assertion. Wave-F redteam MUST challenge: is contorting the production type to satisfy a
  possibly-wrong test assertion correct, or should the test change?
- Pre-existing (NOT #1959, distinct class): 3 kailash-nexus unit failures on main 6aaacf17
  (test_special_characters_in_name pydantic AnyUrl; 2 FastMCP tool-registry KeyError). Follow-up.
- Cross-SDK flag: Rust SDK Nexus binding needs equiv deregister + non-blocking-start (needs user auth).

## Wave-R Round-2 redteam (2026-07-25, merged main 814b45e2)

Both completions MERGED: a2a #1965 (428f34d64), strfold #1966 (814b45e2). Union now 17 files +1428/-70.
Round-2 reviewers (verify completions + fresh full-union sweep, converge on BUG+INVEST-NOW):
| agent | scope | status |
| r2-correctness | a2a behavior-preserve + strfold fold + mechanical silent-mock/str(e) sweep | in-flight |
| r2-security | strfold hazard-closed + a2a no-leak + secret-in-log sweep | in-flight |
| r2-closure | run full Wave-R regression suite on merged main + grep-confirm completions delivered | in-flight |
Round-1: 1 BUG (a2a, fixed) + 1 INCREMENTAL (strfold, fixed) + INCREMENTALs (dispositioned). If R2 clean
→ convergence (R1 findings resolved + R2 clean full-sweep). CHANGELOG 2.44.0 drafted, commit after R2 clean.

## Round-2 verdicts (partial)

- r2-security: CLEAN on BUG/INVEST-NOW. strfold correct + test genuinely proves it; a2a None-path
  no leak; ConfigurationError names env-var IDENTIFIERS only (no values). ONE INCREMENTAL:
  iterative_llm_agent.py:511 outer run() catch-all stores raw str(e) — same defense-in-depth class
  as strfold, one level UP (outermost handler). Safe today (upstream sanitize at 2557 + inner
  handlers). DECISION-PENDING: fold :511 as terminal completion (harmless — sanitize is no-op on
  control-flow text; :511 is outermost so folding TERMINATES the class) vs defer. Awaiting r2-corr/r2-closure to batch.

## Round-2 r2-correctness verdict — :511 RESOLVED (no fold)

- r2-correctness: CLEAN, no BUG/INVEST-NOW. a2a + strfold both VERIFIED CORRECT + behavior-preserving
  (traced all 3 a2a cases; no AttributeError; both _phase_execution blocks folded; 8 regression passed).
- :511 REFUTED as a gap: r2-correctness traced reachability — NO raw provider credential can reach the
  run() catch-all (all LLM dispatch in inner trys sanitized at 432 / pre-sanitized SynthesisError;
  only _adapt_strategy/_calculate_resource_usage/dict-builders reach 511 = zero credential surface).
  → DO NOT fold :511 (defends unreachable path + cosmetic double-prefix). r2-security's categorical
  concern superseded by r2-correctness's concrete trace (evidence-first: traced > asserted).
- 2 PRE-EXISTING INCREMENTAL siblings (unchanged modules, NOT introduced, do NOT block 2.44.0) → FILE follow-ups:
  (a) ai_nodes.py:1547-1563 MultiProviderNode raw str(e)→WARN log + result[error] = #1953-class leak;
  needs kaizen-WIDE #1953-parity sanitize sweep (new shard, exceeds single-fix budget → follow-up issue).
  (b) a2a.py:1865 except Exception: pass silent-swallow, no observability log (INCREMENTAL).
  Round-2 CLEAN on BUG/INVEST-NOW (2 of 3 reviewers in; awaiting r2-closure regression confirm).

## 2.44.0 RELEASE (2026-07-25) — user-authorized "publish now (direct tag)"

- Converged Wave R: 2 redteam rounds + mechanical sweep, 52/52 regression, all reviewers CLEAN.
- Release-prep PR #1968 (version 2.43→2.44 + CHANGELOG) MERGED 1e08f37f.
- README version-pin fix PR #1969 (readme=PyPI long-desc; 2.43→2.44) MERGED — main b799778c.
- Tag kaizen-v2.44.0 pushed @b799778c → publish-pypi.yml run 30143302771 (queued, OIDC).
- NEXT: workflow success → clean-venv installability verify (uv pip install --refresh kailash-kaizen==2.44.0 + import).
- Release scope: kaizen ONLY (all siblings main==pypi, no drift).

## 2.44.0 RELEASED + VERIFIED (2026-07-25) ✅ WAVE R COMPLETE

- publish-pypi run 30143302771: Build✓ PyPI✓ GitHub-Release✓ (TestPyPI skipped for tag flow).
- PyPI has kailash_kaizen-2.44.0-py3-none-any.whl. Clean-venv verify: **version**==2.44.0,
  all fixed surfaces import, keyless detect_provider_from_env()->None (SMOKE PASS, #1952 closed live).

## WAVE F kickoff (2026-07-25) — 2.44.0 tagged, Wave-F PRs now unblocked

Held PRs to merge (2.45.0): #1963 (#1961 log), #1964 (#1960 redaction/security), #1967 (#1959 lifecycle).
#1967 spans 3 pkgs (kaizen+core+nexus) + carries the ActivityTimestamp design flag (redteam MUST challenge).

## Wave F progress (2026-07-25)

- #1963 (#1961 log) MERGED 4a2a346a. #1964 (#1960 redaction) MERGED a3dc6194. → 2.45.0.
- #1967 (#1959 lifecycle, 3-pkg, ActivityTimestamp flag): adversarial design review (agent
  wavef-1967-design) BEFORE merge — adjudicate ActivityTimestamp subclass vs change-the-test-assertion.
- Follow-up issues FILED (executed): #1970 ai_nodes #1953-parity sanitize sweep (security),
  #1971 DataFlow 63-char PG identifier BUG, #1972 nexus 3 pre-existing MCP/FastMCP failures,
  #1973 a2a.py pre-existing hardening (coroutine-await + except:pass).
- CROSS-SDK flags NEEDING USER AUTH (surface, not self-authorize): (a) #1960 sanitizer redaction
  gaps likely in Rust SDK; (b) #1959 Nexus deregister+non-blocking-start lifecycle in Rust SDK.
- 2.45.0 = multi-package (kaizen + kailash core + kailash-nexus, per #1967's 3-pkg span) — needs
  core+nexus version bumps (build-repo-release-discipline Rule 5) at release-prep.

## #1967 design review VERDICT (2026-07-25): option (b) — DELETE ActivityTimestamp

- wavef-1967-design: DESIGN-INCORRECT (not just unusual). Dispositive: ActivityTimestamp produced
  in-memory (session_manager.py:140) but storage.py:202 deserializes PLAIN datetime → after any
  persist→reload (SQLite default store!) `channel_activity["api"] > 0` raises TypeError AGAIN. Fix
  doesn't hold for real persisted sessions. Also `> 0` is VACUOUS (timestamp ~1.7e9 always >0; tests
  nothing beyond key-presence which KeyError already enforces). Same file uses correct idiom at L499-500.
- FIX (agent wavef-1967-fix, on fix/1959-nexus-lifecycle branch → updates PR #1967):
  (1) test L189-190 `>0` → `assert "api"/"mcp" in session.channel_activity`; (2) DELETE ActivityTimestamp
  class (session_manager.py ~14-58); (3) revert L140 → datetime.now(); (4) purge all refs.
- Lifecycle additions (Nexus.deregister idempotent+logged; workflow_server.deregister_workflow symmetric
  route-match; start(blocking=False) honest readiness) — CLEAN, KEEP. Review found rest production-quality.
- NEXT: fix lands → merge #1967 → holistic Wave-F redteam (all 3) → 2.45.0 multi-pkg (kaizen+core+nexus).

## 2.45.0 MULTI-PACKAGE release scope (2026-07-25) — coordinated 3-pkg release

#1967 (#1959) touches 3 pkgs → each needs its own bump + release + tag:

- kailash CORE 2.61.0 → 2.62.0 (new WorkflowServer.deregister_workflow). tag: v2.62.0.
- kailash-nexus 2.14.0 → 2.15.0 (new Nexus.deregister + start(blocking=False)). tag: nexus-v2.15.0.
- kailash-kaizen 2.44.0 → 2.45.0 (#1959/#1960/#1961). tag: kaizen-v2.45.0. MUST bump `kailash>=` pin
  to 2.62.0 (kaizen redeploy fix calls the new core/nexus lifecycle methods; else fails on clean install).
  Dependency coupling: kaizen 2.45.0 requires core 2.62.0 (deregister_workflow) + nexus 2.15.0 (deregister/start).
  Release order: core v2.62.0 → nexus-v2.15.0 → kaizen-v2.45.0 (deps publish before dependents).
  Each: version bump (pyproject+**init** atomic) + CHANGELOG + README pin + tag. Human auth gate before publish.

## Wave-F holistic redteam (2026-07-25, merged main 80141836)

All 3 Wave-F PRs merged: #1963(#1961) 4a2a346a, #1964(#1960) a3dc6194, #1967(#1959) 80141836.
Union b799778c..80141836: 8 files +483/-12 (kaizen 6, nexus 1, core 1).
Reviewers (converge on BUG+INVEST-NOW):

- wf-security: #1960 redaction regexes (ReDoS, over/under-redaction, broad 40-char pattern) + secret-in-log
  - #1959 lifecycle security (non-blocking-start health honesty, deregister authz). PRIMARY (not yet sec-reviewed).
- wf-correctness: #1959 lifecycle (deregister idempotency/symmetric route-match, non-blocking readiness),
  option-b test-fix meaningfulness, #1960/#1961 functional, cross-shard + mechanical sweep.
- wf-closure: run all Wave-F regression+integration on merged main (.venv); confirm #1959/#1960/#1961 closeable;
  separate pre-existing (#1970-#1973) from NEW regressions.
  Design review already: #1967 ActivityTimestamp → option-b applied; lifecycle additions found clean.
  NEXT: converge → 2.45.0 multi-pkg (core v2.62.0 → nexus-v2.15.0 → kaizen-v2.45.0, coordinated pins) → human auth gate.

## Wave-F redteam: wf-security verdict (partial)

- #1960 redaction CLEAN — no BUG/INVEST-NOW. ReDoS-free (all single-char-class), 4 gap classes closed,
  broad 40-char over-redaction sound+idempotent, Azure/base64 boundary both-redact. Secret-in-log sweep
  CLEAN across all Wave-F modules (federated DEBUG hash, nexus deregister logs exc-not-secret, workflow_server
  DEBUG, session_manager echoes user_id identifier only, start logs count only).
- INCREMENTAL (deferrable, OUTSIDE the module's LLM-provider threat model → follow-up, NOT 2.45.0 blocker):
  (1) non-http conn-string creds (postgres://user:pass@, redis/mongo/mysql) slip _URL_WITH_AUTH (https?-anchored);
  one-line scheme-broaden `(\w+://)[^@\s]+:[^@\s]+@`. (2) Slack tokens + bare (non-Bearer) JWTs slip.
  (3) suggest a >40-char URL negative-vector test. (4) deregister authz: internal-only today, no channel
  binding = no exposure; docstring-note if ever wired. → FILE a sanitizer-pattern-coverage follow-up.
  Waiting on wf-correctness + wf-closure.

## Wave-F redteam: wf-closure verdict

- ALL 3 DELIVERED + GREEN + CLOSEABLE. Regression: test_issue_1960 + test_end_to_end_nexus 37 passed;
  session_workflows + session_storage 30 passed (.venv). #1960 4 patterns present; #1959 deregister on all
  3 surfaces + ActivityTimestamp GONE (grep exit 1); #1961 DEBUG (zero INFO cache log).
- Nexus siblings: 143 passed, 1 FAILED = test_special_characters_in_name (pydantic AnyUrl, PRE-EXISTING,
  tracked #1972, NOT a Wave-F regression — #1959 never touched the workflow:// URI construction).
- #1959/#1960/#1961 all CLOSEABLE. 2 of 3 reviewers clean on BUG/INVEST-NOW. Awaiting wf-correctness.

## Wave-F redteam: wf-correctness verdict — 2 BUGs in #1959 (NOT converged)

- BUG-1 (MED): Nexus.deregister leaves stale MCP resource — _deregister_workflow_mcp probes
  _resources/_resource_manager but real MCPServer stores in _resource_registry (kailash-mcp server.py:2053);
  workflow:// resource never dropped → redeploy "Resource already exists" WARN. Undermines #1959's redeploy
  idempotency + contradicts "removed from all channels" contract. Fix: pop workflow://{name} from _resource_registry.
- BUG-2 (LOW-MED): start(blocking=False) emits spurious ERROR "Failed to register... already registered" on the
  DOCUMENTED register-first flow (e2e fixture registers AFTER start → missed it). transport.start re-registers
  eager-registered workflows. Fix: idempotent transport registration (pre-check/skip, DEBUG not ERROR).
- Both same-class (#1959 lifecycle), within budget → FIX IN-SESSION (autonomous-execution MUST-4), NOT file.
  Agent wf-1959-bugfix (worktree) → PR fix/1959-nexus-lifecycle-bugs + regression tests the e2e missed.
- Rest CLEAN: #1959 remainder (idempotent deregister, symmetric route-match, honest readiness, option-b test
  MEANINGFUL), #1960 21/21, #1961, cross-shard (BUG-1 propagates to kaizen deploy_as_mcp redeploy), zero-tol sweep.
- Deferrable sanitizer-pattern gaps (conn strings/Slack/JWT/long-URL vector) → FILED #1974.
- CONVERGENCE PENDING: BUG fix lands → Round-2 Wave-F verify (BUG-1/2 closed + no new) → 2.45.0 multi-pkg.

## #1959 BUG fix → PR #1975 + Round-2 verify (2026-07-25)

- wf-1959-bugfix: BOTH BUGs fixed (PR #1975, nexus core.py + http.py + 2 regression test files).
  Root-cause DEEPER than flagged: register writes 4 stores (tool: _tool_registry + _mcp._tool_manager._tools;
  resource: _resource_registry + _mcp._resource_manager._resources); pre-#1959 deregister cleared only 2 tool
  dicts + probed non-existent attrs → resource AND FastMCP-tool leaked. Fix pops ALL 4 (guarded fallbacks).
  BUG-2: HTTPTransport.start pre-checks gateway workflows dict, skips already-registered at DEBUG (HTTP only —
  cli/mcp/websocket confirmed fine). 3 regression tests fail-first→pass. Pre-existing failures proved on base
  (#1972 AnyUrl class + kailash_ml-extra-absent env nit) — NOT introduced.
- Round-2 verify: agent wf-1975-verify — adversarially confirm 4-store symmetry vs register side + BUG-2 + no new.
- CONVERGENCE: wf-1975-verify clean + #1975 CI green → merge → Wave-F converged → 2.45.0 multi-pkg.

## 2.45.0 MULTI-PACKAGE RELEASED + VERIFIED (2026-07-25) ✅ WAVE F COMPLETE

User-authorized "publish now (direct tags)". Release-prep PR #1976 MERGED ba3cc199.
Tags pushed in dep order: v2.62.0 (core) → nexus-v2.15.0 → kaizen-v2.45.0. All 3 publish-pypi runs SUCCESS.
Clean-venv verify (compose install): kailash 2.62.0 + WorkflowServer.deregister_workflow ✓;
nexus 2.15.0 + Nexus.deregister + start(blocking=) ✓; kaizen 2.45.0 + error_sanitizer AWS-key redaction
live smoke (AKIA...→[REDACTED]) ✓. Follow-ups filed: #1970-#1974.
NEXT: cross-SDK filings (#1960 + #1959 Rust equivalents) — user authorized "file both"; needs
/cross-repo-authorize receipt (cross-repo write) + scrubbed SDK-API-surface-only bodies.

## SESSION COMPLETE (2026-07-25) — both release waves shipped

- 2.44.0 (Wave R provider integrity): RELEASED + verified. #1952/#1953/#1948 + a2a + strfold completions.
- 2.45.0 (Wave F follow-up hardening, 3 pkgs): RELEASED + verified. core 2.62.0 + nexus 2.15.0 + kaizen 2.45.0.
  #1959 (Nexus lifecycle, +2 BUG fixes) / #1960 (redaction) / #1961 (log).
- Follow-ups FILED: #1970 (ai_nodes sanitize sweep), #1971 (DataFlow 63-char id), #1972 (nexus MCP fails),
  #1973 (a2a hardening), #1974 (sanitizer pattern coverage).
- Cross-SDK FILED (user-authorized, receipt + reciprocal refs): rs#2131 (↔#1960), rs#2132 (↔#1959).
  Receipt PR #1977. Authz receipt in .claude/cross-repo-authz/.
- Both releases went through the human authorization gate (user approved each PyPI publish).

## SESSION 2026-07-25b — hooks repair + forest drain (/autonomize + /redteam-to-convergence)

### Wave declaration (wave-loop.md MUST-1)

- **Wave 1 — hook/settings repair** (HIGH; user-stated brief, 3 invariants). COMPLETE.
- **Wave 2 — parallel ground-truth recon** (3 independent read-only audits; ~0 write invariants).
- **Wave 3+ — value-ranked fix waves** derived from Wave-2 findings (declared at the G1→G5 gate).

### Wave 1 — COMPLETE (inline, no agents)

| item                                                | finding                                                                                                                                                                                                                                                  | disposition                                                                                                                                           |
| --------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| SessionStart startup hook error + `cjs/loader:1478` | `settings.json` registered `.claude/hooks/coc-drift-warn.js`; file deleted by loom Gate-2 sync 717c0f6e3, SUBSUMED by `multi-operator-sessionstart.js` (F13 closure). settings.json is BUILD-owned/PRESERVED across syncs → registration never followed. | registration repointed to `multi-operator-sessionstart.js` (fail-open, coordination-OFF passthrough, clone-safe — NOT one of the 6 enforcement hooks) |
| `Write(...)`/`NotebookEdit(...)` permission warning | CC ≥2.1.210: file permission checks match ONLY `Edit(path)`/`Read(path)`; `Write(path)`/`NotebookEdit(path)`/`Glob(path)` are parsed but never matched. `Edit(path)` covers all file-editing tools.                                                      | 7 redundant `Write(...)` deny entries removed; `Edit(...)` coverage retained (no enforcement loss)                                                    |

### Wave 2 — launch ledger (orchestration-launch-ledger.md MUST-1)

| track                                     | agent                | branch      | status    |
| ----------------------------------------- | -------------------- | ----------- | --------- |
| loom-sync incorporation audit             | w2-loom-sync         | (read-only) | in-flight |
| F1–F5 backlog ground-truth reconciliation | w2-backlog-reconcile | (read-only) | in-flight |
| freshness/pins/release-drift verification | w2-freshness         | (read-only) | in-flight |

### Wave 1 — LANDED (PR #1978, merged 5e1ae832f)

- Root cause: `settings.json` registered `.claude/hooks/coc-drift-warn.js`, deleted by loom Gate-2 sync
  717c0f6e3 (SUBSUMED into `multi-operator-sessionstart.js`, F13 closure). settings.json is BUILD-owned +
  PRESERVED verbatim across every loom sync → the registration never followed the deletion.
  Reported issues 1 ("SessionStart: startup hook error") and 3 (`cjs/loader:1478`) were ONE defect —
  1478 is the top frame of that MODULE_NOT_FOUND stack. Non-blocking, hence long-lived.
- SECOND-ORDER IMPACT (worse than the error): the working-tree COC-drift warning that
  `rules/coc-sync-landing.md` MUST-1 structurally depends on had silently not fired since that sync.
- Issue 2: CC >=2.1.210 matches file-perm rules on `Edit(path)`/`Read(path)` ONLY; `Write(path)` /
  `NotebookEdit(path)` / `Glob(path)` parsed-but-never-matched. The 7 `Write(.claude/learning/...)` deny
  entries were ALREADY INERT dead config → removal cannot reduce enforcement (strictly unchanged).
- CI: attempt-1 red was a CANCELLATION (both jobs conclusion=cancelled within 1s, all substantive steps
  green, only teardown/post failed) — NOT a test failure. Re-ran → attempt=2 conclusion=success on both.
  Merged on pinned head 5c670e0fc (READ step separate from MERGE per git.md).
- Post-merge verify on main: 17/17 registered hooks resolve; 0 unmatched perm rules; SessionStart chain
  (session-start / posture-gate / multi-operator-sessionstart) all exit 0 clean.
- OPEN (operator-local, gitignored, NOT a repo artifact): 119/135 `.venv/bin` console scripts carry stale
  shebangs pointing at the pre-move path `/Users/esperie/repos/loom/kailash-py` (repo since moved to the
  canonical sublayout `~/repos/kailash/build/kailash-py`). `.venv/bin/python` itself is a valid symlink;
  `.venv/bin/pre-commit` fails "bad interpreter". Workaround in use: `.venv/bin/python -m <module>`.
  Candidate cause of the `[SDK-PINS] Could not read installed packages` warning. Fix: `uv venv && uv sync`.

### Wave 2 — agents completed, reports being collected

### Wave 2 — FINDINGS (all 3 agents reported; load-bearing claims re-verified by orchestrator)

**w2-loom-sync — the hook defect is a CLASS of 19, not 1.**

- `node .claude/bin/validate-emit.mjs --check settings-hook-registration` → `19 pass / 18 fail — 18 blocking`,
  `/sync is BLOCKED`. VERIFIED by orchestrator (re-ran independently).
- ROOT CAUSE of the class: settings.json is BUILD-owned + PRESERVED verbatim across every loom Gate-2 sync →
  loom can SHIP a hook but never WIRE it, and when loom DELETES one the registration stays. 18 accumulated.
- `analyze-completeness-guard.js`: block-severity, rule-mandated (`analyze-output-completeness.md:60`),
  **9/9 fixtures pass incl. the block branch** (orchestrator re-ran) — shipped INERT.
- FALSE "SHIPPED + REGISTERED" claim: `artifact-flow.md:53` re `cross-ecosystem-disclosure-guard.js`;
  grep of settings.json = 0 occurrences. Rule asserts something false about this repo.
- 4 genuine dangling xrefs (all VERIFIED ABSENT by orchestrator): `hooks/coc-drift-warn.js` (residue of Wave 1),
  `bin/lib/loom-links.mjs` (**highest impact** — `cross-repo.md` MUST-1 mandates routing through a resolver that
  does not exist here; its CONFIG `loom-links.local.json` DOES ship, so the rule reads as satisfiable),
  `bin/check-sync-freshness.mjs` (`/sweep` instructs running it), `hooks/lib/o1-citation-check.js`.
- `.claude/VERSION` upstream block ~1 month / 11 syncs stale (last touched 2026-06-27, loom_sha 9755c2d;
  syncs continued to 2026-07-22 / 08cb86fb48eb). Sync did NOT stop — VERSION bumping did.
- Hook MATCHERS still need `Write|NotebookEdit` spelled out (only PERMISSION rules unified in CC 2.1.210).
  `NotebookEdit` was missing from ALL edit matchers → 8 registered hooks never fired on notebook edits.

**w2-freshness — startup warnings largely false; one real unwatched risk.**

- FRESHNESS x2 + "FIX BEFORE RELEASE" = FALSE POSITIVE. align/ml re-export from `_version.py`
  (`__init__.py:8` / `:49`); `session-start.js:442` regex matches LITERALS only. Adding literals would
  CREATE a second drifting version location — do NOT "fix" that way.
- SDK-PINS x5 = REAL staleness, EVERY NUMBER WRONG (`session-start.js:599` reads the stale VERSION snapshot,
  not `packages/*/pyproject.toml`). +2 SILENTLY MISSED (dataflow, kaizen) — extras bracket evades `pinRegex`
  L514. kaizen pinned `>=2.7.5` vs ACTUAL 2.45.0.
- "Could not read installed packages" = FALSE POSITIVE; cause is `No module named pip` (uv venvs ship no pip),
  NOT the shebangs (`execFileSync` runs the binary, no shebang resolution). Its remedy tells the operator to
  destroy a healthy venv for a cause that isn't real.
- RELEASE-DRIFT x3 = counts accurate, NONE release-worthy (chore/test-only; nothing in any wheel).
- **UNWATCHED REAL RISK (no hook covers it):** editable installs LAG on-disk sources — kaizen 2.31.2 vs 2.45.0,
  pact 0.14.3 vs 0.18.0, mcp 0.2.15 vs 0.4.3, nexus 2.12.0 vs 2.15.0, dataflow 2.16.0 vs 2.19.1.
  **Tests in this venv may not be exercising current sub-package source.** Same root cause as 114/135 stale
  `.venv/bin` shebangs (repo moved to canonical sublayout). Fix: `uv venv --clear && uv sync`.

**w2-backlog-reconcile — MUST-7 reconciliation changed what 3 of the 5 items ARE.**

| #     | verdict                       | reconciliation correction                                                                                                                                                                                                                             | shard                                                        |
| ----- | ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| #1973 | STILL-REAL, **RANK 1**        | `calculate_match_score` calls `async def` UNAWAITED on live path `a2a.py:3510` → `TypeError` on EVERY A2A agent-selection call. Feature 100% broken. Proven at runtime. Carried NO value-anchor + hedged "likely" — under-investigated, not low-value | fits 1 (enumerate async fan-out first)                       |
| #1970 | STILL-REAL, RANK 2            | issue's file path AND class name BOTH WRONG — `MultiProviderNode` exists nowhere; real owner `KaizenAIModelNode` (`ai_nodes.py:1498`), path has no `/ai/`. Line range exact                                                                           | **DECOMPOSE** — 497 sites/123 files/**55 load-bearing**      |
| #1971 | STILL-REAL, RANK 3            | 3 corrections: **kaizen** not dataflow file; **SQLite** path raising the **Postgres** 63-char limit (SQLite limit is 128); wrong-DIALECT-selection, not over-long-identifier generation                                                               | fits 1 (split off truncation/hashing)                        |
| #1974 | STILL-REAL (gaps 1-2), RANK 4 | AC-3 premise CONTRADICTED — over-redaction ALREADY intentional+documented (`error_sanitizer.py:42-54`); a test written to AC-3 as worded FAILS on landing                                                                                             | fits 1, cheapest — deliberately NOT promoted for being cheap |
| #1972 | PARTIALLY SUPERSEDED, RANK 5  | 2 of 3 are STALE TESTS asserting behavior production DELIBERATELY BLOCKS (`nexus/core.py:1512-1515`); bare `MagicMock` auto-satisfies the decorator branch. **Fixing the product to green them RE-INTRODUCES the defect**                             | fits 1 (test port, not product fix)                          |

- Cross-cutting, in no issue: test-postgres :5433 rejects ALL credentials (blocks Tier-3 on #1971);
  stale `__pycache__` renders tracebacks against the non-existent pre-move path.

### Wave 3 — IN FLIGHT (branch fix/wire-shipped-but-inert-hooks)

| track                                                                  | agent                  | status                                  |
| ---------------------------------------------------------------------- | ---------------------- | --------------------------------------- |
| wire 3 safe hooks + NotebookEdit on all edit matchers                  | (orchestrator, inline) | DONE — validator 19→22 pass, 18→15 fail |
| `@settings-registration:` markers for remaining 15                     | w3-markers             | in-flight                               |
| session-start.js: freshness re-export + pip→importlib + pins-from-disk | w3-sessionstart-fix    | in-flight                               |

### Wave 4 — QUEUED (value-ranked, post-hooks)

1. #1973 a2a unawaited-coroutine (RANK 1 — only provably-100%-broken shipped feature)
2. #1970 Shard A (KaizenAIModelNode site + regression) then Shard B+ (55 dict-writing sites)
3. #1971 dialect-selection fix
4. #1974 sanitizer patterns (pairs with #1970 — same class/module family)
5. #1972 test port (NOT a product fix)

### Awaiting user decision

- (a) wire `settings-hook-registration` validator into CI? (stops recurrence; `/sync` reds until all dispositioned)
- (b) rebuild venv (`uv venv --clear && uv sync`)? fixes 114 dead shebangs + stale editable installs
- (c) kailash-ml release owed? `build-repo-release-discipline.md` Rule 1a says CHANGELOG touch ⇒ release;
  the touch was a 1-line scrub of a HISTORICAL entry changing no wheel byte. Orchestrator read: no release owed.

### Wave 3 — CLOSED (hook-registration class fully dispositioned)

`validate-emit --check settings-hook-registration`: **18 blocking → 0 blocking; 19 pass → 37 pass / 0 fail.**
`/sync` UNBLOCKED. Disposition of all 19:

- **REGISTERED (4)** in committed settings.json: `analyze-completeness-guard` (PreToolUse `Skill`; block-severity,
  9/9 fixtures, was INERT), `cross-ecosystem-disclosure-guard` (PreToolUse `Edit|Write|NotebookEdit`; makes
  `artifact-flow.md:53`'s SHIPPED+REGISTERED claim TRUE; 86ms passthrough verified on hot path),
  `wrapup-after-landing` (PostToolUse Bash; advisory FIRED correctly on a `gh pr merge` probe),
  `session-notes-incorporation-guard` (PostToolUse Bash; registered NOT marked — its own header REJECTS a
  coordination dependency to work in the single-operator default; no block/deny path anywhere in file).
- **MARKED (14)** `@settings-registration:` header markers, header-comment only, all pass `node --check`.
  6 coordination-ENFORCEMENT hooks deliberately NOT registered (would ARM on any forker's `/enroll`).
- **REPOINTED (1)**: `coc-drift-warn` → `multi-operator-sessionstart` (PR #1978, merged 5e1ae832f).
- `NotebookEdit` added to ALL edit matchers (was missing everywhere → 8 registered hooks never fired on
  notebook edits). NOTE: hook MATCHERS still need the multi-tool form; only PERMISSION rules unified in 2.1.210.
- Agent honesty notes (kept as-is): w3-markers self-corrected an `operator-gate.js` claim the source did NOT
  settle → marker now says UNVERIFIED with the conflicting doc-comment quoted; and flagged that the
  "belongs in settings.local.json" line in 8 markers is a forward-looking recommendation, not source-provable.
- Accepted: `auto-format.js` (the repo's own hook) reformatted 4 pre-existing regions of
  `emit-artifact-activation.js` — semantically identical; reverting would fight the hook.

### session-start.js — 3 of 4 fixed, 1 REGRESSION bounced back

FIXED + orchestrator-verified: FRESHNESS false positives GONE ("All package versions consistent");
all 7 pin numbers now match verified ACTUALs; dataflow + kaizen newly VISIBLE; "Could not read installed
packages" GONE.
**REGRESSION FOUND BY ORCHESTRATOR (redteam of the fix):** new line "7 kailash packages installed at or
above their pin" is FALSE REASSURANCE —

```
kailash-ml     metadata=2.2.2   IMPORT-FAIL (ModuleNotFoundError)
kailash-align  metadata=0.7.2   IMPORT-FAIL (ModuleNotFoundError)
```

`importlib.metadata` reads `.dist-info`, which SURVIVES a broken editable pointer. Old code cried wolf;
new code reassures wrongly on exactly the 2 broken packages — worse, because it hides a condition that
silently invalidates test results. Sent back with required output shape (surface metadata-present-but-
import-fails LOUDLY) + fail-open + time-budget constraints.

### CORRECTION to a Wave-2 finding (orchestrator re-verified; relayed correction to user)

w2-freshness claimed "editable installs lag their sources → tests may not be exercising current sub-package
source." **That is WRONG for 6 of 8 packages.** All resolve to live SOURCE with CURRENT `__version__`
(kailash 2.62.0 / kaizen 2.45.0 / nexus 2.15.0 / dataflow 2.19.1 / pact 0.18.0 / mcp 0.4.3); only the DIST
METADATA lags (version baked into the `.pth` filename at install time). Tests DO exercise current source.
**But the same probe found something worse:** `kailash-ml` + `kailash-align` do not import AT ALL —
`_editable_impl_*.pth` point at the pre-move `/Users/esperie/repos/loom/kailash-py/...` which does not exist:

```
packages/kailash-ml/tests → 99 tests collected, 180 errors in 24.81s
!!!! Interrupted: 180 errors during collection !!!!
```

Those two suites CANNOT EXECUTE. `_editable_impl_kailash_pact.pth` points at the CORRECT new path (pact was
reinstalled post-move; ml/align never were). This upgrades the venv rebuild from housekeeping to a blocker.

### Wave 4 — launch ledger (orchestration-launch-ledger.md MUST-1)

| track                                                | agent               | branch                             | status    |
| ---------------------------------------------------- | ------------------- | ---------------------------------- | --------- |
| #1973 a2a unawaited-coroutine + except:pass (RANK 1) | w4-a2a-1973         | (working tree; orchestrator lands) | in-flight |
| session-start.js false-reassurance regression fix    | w3-sessionstart-fix | (working tree)                     | in-flight |

### Disclosure observation (verified, LOW severity, not acted on)

`.session-notes.d/esperie.md`, `.session-notes.shared.md`, `.session-notes.migrated` are TRACKED in this
PUBLIC repo. Identity exposure is marginal — git history already carries the author on every commit. The
open question is whether session NARRATIVE belongs on a public record. Flagged to user, no action taken.

## SESSION 2026-07-25c — forest drain (/autonomize + max parallelization + /redteam-to-convergence)

### Wave declaration (wave-loop.md MUST-1)

- **Wave 5 — forest drain**, ONE value-ranked milestone-group: the 5 remaining reconciled forest items
  (F6/#1981, F1/#1970 A+B, F5/#1974, F2/#1971, F3/#1972). Decomposed into 6 shards over DISJOINT file
  ownership across 3 packages. Cumulative load-bearing-invariant surface ≈ 8 (bound-B ≤10 base; live
  pytest feedback loop present in every shard → the MUST-3 multiplier is available but not needed).
  Single value-coherent group (drain the reconciled follow-up forest) → one-wave declaration is correct
  per the serial carve-out; its terminal G1 redteam IS the wave gate.
- **Wave 6 — G1 holistic redteam to convergence** across the union of Wave-5 shards (agents.md § Holistic
  Post-Multi-Wave Redteam), ≥3 parallel reviewers, 2 consecutive clean rounds on BUG + INVEST-NOW.

### MUST-7 reconciliation (wave-loop.md) — done BEFORE dispatch, not on the backlog's say-so

All 5 items re-read live (`gh issue view`) + re-grepped on disk this session. Session-B's reconciliation
verdicts HOLD and were injected into each shard prompt as explicit corrections:

- **#1970** — `MultiProviderNode` exists nowhere; real owner `KaizenAIModelNode` at
  `packages/kailash-kaizen/src/kaizen/nodes/ai_nodes.py:1498` (issue's path has a spurious `/ai/`).
  Leak sites confirmed at `:1545` (WARN log), `:1554` (`primary_error`), `:1557`+`:1563` (`error`).
- **#1971** — dialect classes live at `packages/kailash-dataflow/src/dataflow/adapters/dialect.py`
  (PG 63 `:91` / MySQL 64 `:192` / SQLite 128 `:289`) AND a second live copy at `src/kailash/db/dialect.py`
  (`:419`/`:496`/`:600`). NEW this session: the kaizen `postgres_db` fixture
  (`tests/e2e/providers/test_multi_database_e2e.py:59-78`) targets `:5433` — which rejects all
  credentials — and **silently falls back to SQLite at `:77-78`**. So BOTH "backends" are SQLite; that is
  how a `sqlite://` URL raises a PostgreSQL-limit error. Confirms wrong-DIALECT-SELECTION, not over-long-id.
  (`packages/kailash-dataflow/build/lib/` is a STALE duplicate source tree — edits there are inert.)
- **#1974** — AC-3 premise still contradicted by `error_sanitizer.py:42-54`; source is authoritative.
- **#1972** — still a test port; product guard at `nexus/core.py:1512-1515` must NOT be relaxed.
- **#1981** — HIGH, own shard, 4 ACs incl. cross-provider matrix.

### Wave 5 — launch ledger (orchestration-launch-ledger.md MUST-1)

| shard | item                               | agent                      | file ownership (DISJOINT)                                                                   | status    |
| ----- | ---------------------------------- | -------------------------- | ------------------------------------------------------------------------------------------- | --------- |
| S1    | #1981 A2A structured output (HIGH) | w5-1981-structured-output  | kaizen `llm/reasoning.py` + `nodes/ai/a2a.py` (ranking region)                              | in-flight |
| S2    | #1970-A sanitize sweep             | w5-1970a-sanitize-nodes    | kaizen `nodes/**` (− `error_sanitizer.py`, − `a2a.py`) + `providers/**`                     | in-flight |
| S3    | #1970-B sanitize sweep             | w5-1970b-sanitize-rest     | kaizen src MINUS `nodes/**`, `providers/**`, `llm/reasoning.py`, `backends/**`, `memory/**` | in-flight |
| S4    | #1974 sanitizer patterns           | w5-1974-sanitizer-patterns | kaizen `nodes/ai/error_sanitizer.py` + its tests                                            | in-flight |
| S5    | #1971 dialect selection            | w5-1971-dialect            | `packages/kailash-dataflow/src/**`, `src/kailash/db/**`, kaizen `backends/**`+`memory/**`   | in-flight |
| S6    | #1972 nexus test port              | w5-1972-nexus-tests        | `packages/kailash-nexus/**`                                                                 | in-flight |

**Orchestration constraints injected into every shard prompt** (governed-throughput.md MUST-1/2 — curated
minimal slices, NOT full corpus): NO git operations (orchestrator lands all); explicit file-ownership
allowlist + "STOP and report if your fix needs a file outside it"; `.venv/bin/python -m pytest` ONLY
(bare python dies at conftest `ImportError: Node`); clear `__pycache__` before kaizen/nexus tests;
`.env` `OPENAI_API_KEY` is live-401, Anthropic works, never hardcode model strings; fail-first-verified
regression tests; evidence-first reporting (quote command output or `file:line`, an errored run is ZERO
evidence); zero-tolerance (no stubs, no silent fallbacks, fix pre-existing failures in touched code);
plus a per-shard `SELF_REDTEAM` section adversarially attacking its own fix.

Dispatch was throttle-aware per `worktree-isolation.md` Rule 4: cold-start batch of 3 (S1/S2/S4), then
batch 2 (S5/S6/S3). No synchronized-throttle signal observed. Shards run in the SHARED working tree
(not `isolation: "worktree"`) deliberately — the repo `.venv` carries editable installs pointing at the
MAIN checkout, so a worktree-isolated shard's pytest would exercise main's source, not its own edits,
destroying the feedback loop that `autonomous-execution.md` MUST-3 credits with the 3-5x multiplier.
Disjoint file ownership + centralized git is the isolation mechanism instead.

### NEW DEFECT CLASS FOUND MID-FLIGHT — "test asserts against an imagined API"

Surfaced by orchestrator monitoring of live pyright diagnostics, NOT by any shard's self-check. Two
independent shards authored regression tests importing classes/methods that **do not exist anywhere in
the repo**. This is worse than a missing test: it passes review as coverage while exercising nothing,
and inflates the apparent completeness of a security sweep.

| shard | fabricated symbol                                                 | ground truth                                                                                                               |
| ----- | ----------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| S2    | `SelfCorrectiveRAGNode` (+ method `_execute_rag`)                 | real class is `SelfCorrect**ing**RAGNode` (`nodes/rag/advanced.py:331`); `def _execute_rag` has **zero** matches repo-wide |
| S3    | `MultiRoundAgent`, `CommunicatingAgent` from `kaizen.core.agents` | module exposes only `Agent` / `AgentManager` / `EnvModelMissing`; neither class is defined anywhere, under any module      |

**Structural response — a reusable gate now exists:**
`workspaces/issue-1720-llm-consolidation/04-validate/verify-shard-symbols.py`. AST-extracts every
in-scope `from X import Y` from a test file and resolves each symbol via `importlib` (ground truth, not
grep; no test execution). Exit 0 = all resolved. First run caught S3's two symbols immediately after
catching S2's by hand. Both shards were sent evidence-backed corrections and instructed to re-verify
EVERY IN-scope site in their classification tables and to run the gate before reporting.

`orphan-detection.md` Rule 5 already makes `pytest --collect-only` a merge gate; this script is the
finer-grained form (an ImportError of ONE symbol inside a `from ... import a, b, c` is easier to read
here than in a collection traceback), and it runs without executing test bodies.

**NEAR-MISS worth recording (evidence-first discipline paid off):** pyright transiently reported
`"sanitize_provider_error" is not defined` at `ai_nodes.py:1551/:1568`. Before messaging S2 I checked
the file — it IS imported at `ai_nodes.py:19`; the diagnostic was a mid-edit read that cleared on the
next pass. Had I relayed it, I would have sent a shard chasing a non-existent bug. **A live diagnostic
against a file another agent is actively editing is a SNAPSHOT, not a finding — confirm against the
file before acting** (`evidence-first-claims.md` MUST-1/3).

**Pre-existing-vs-introduced pyright noise — method for the redteam, do NOT assume.** `reasoning.py`
(S1) shows `InputField`/`OutputField` "incompatible with declared type" errors, and `a2a.py` shows 8
errors. Both are CONSISTENT with pre-existing baselines (the Signature-field idiom always trips pyright;
session-B notes record a2a.py at 8 errors post-#1980, and the reasoning.py errors merely shifted +50
lines as S1 inserted code above them). CONSISTENT-WITH is not PROOF. The working tree is dirty and
cannot be stashed (agents live), so the redteam MUST establish introduced-vs-pre-existing by
**diff-hunk intersection** — run pyright per modified file and check whether each flagged line falls
inside that shard's `git diff` hunks — rather than by a clean-tree baseline.

### S4 RE-DISPATCHED — orchestrator dispatch error (agents.md tool-inventory MUST)

S4 (#1974) was dispatched to **`security-reviewer`, which is READ-ONLY** (Read/Grep/Glob — no Edit, no
Bash). `agents.md` § "Verify Specialist Tool Inventory Before Implementation Delegation" names
`security-reviewer` explicitly in the read-only set that MUST NOT receive implementation work. The
pre-launch check is O(1); this cost a full shard launch. The defensive `STOP IMMEDIATELY and report
BLOCKED: read-only toolset` line in the prompt worked exactly as intended — the agent halted having
edited nothing, and returned usable read-only groundwork instead of a half-applied change.
**Re-dispatched to `kaizen-specialist`** (Edit + Bash + the kaizen domain binding per
`framework-first.md`), carrying the groundwork forward so none of it is re-derived.

### #1974 — the issue's OWN proposed fix does not close one of the issue's OWN examples

Machine-verified by the orchestrator against 5 DSN vectors before re-dispatch:

| candidate regex                                                | `redis://:hunter2@cache:6379`              |
| -------------------------------------------------------------- | ------------------------------------------ |
| issue's proposal `(\w+://)[^@\s]+:[^@\s]+@`                    | **LEAK — unchanged**                       |
| RFC-3986 scheme `([A-Za-z][A-Za-z0-9+.-]*://)[^@\s]+:[^@\s]+@` | **LEAK — unchanged**                       |
| empty-userinfo `([A-Za-z][A-Za-z0-9+.-]*://)[^@\s]*:[^@\s]+@`  | `redis://[REDACTED]:[REDACTED]@cache:6379` |

Root cause: `[^@\s]+` requires a NON-EMPTY username, but `redis://:pass@host` conventionally has none —
and `redis://:pass@` is named verbatim in #1974's own gap-1 text. Implementing the issue literally
would have shipped a fix that misses one of its three stated cases. The `*`-vs-`+` distinction is the
whole fix. **Reinforces `wave-loop.md` MUST-7: reconcile a backlog item against ground truth before
implementing it — including the remediation the issue proposes, not just its premise.**

**REFUTED (recorded so it is not re-raised):** the blocked S4 flagged that `(\w+://)` misses
`postgresql+asyncpg://` because `\w` excludes `+`. It does not — `re.search` is UNANCHORED, so it
matches at `asyncpg://` and `re.sub` preserves the `postgresql+` prefix outside the match span
(`postgresql+asyncpg://u:s3cret@h/db` → `postgresql+asyncpg://[REDACTED]:[REDACTED]@h/db`). Adopting
the RFC-3986 scheme class is defensible for intent/readability but closes NO leak; it must not be
presented as a gap fix. An agent-reported finding is a hypothesis until the orchestrator re-runs it —
this one was wrong, and the vector matrix that refuted it is what found the real defect.

## WAVE 5 TERMINATED BY USAGE LIMIT — all 6 shards died mid-flight (2026-07-25)

All six Wave-5 agents returned `idleReason: failed / "You've hit your session limit"` within ~9 minutes
of each other. **NOT a code failure and NOT a throttle-concurrency signal** (`worktree-isolation.md`
Rule 4's falsifiable signal is `not your usage limit`; this was the opposite). Operator swapped
accounts; the orchestrator continued. Only S1 reported before dying (a blocked-on-ownership handoff).

**Work was NOT lost** — shards edit the SHARED tree, so 42 modified source files + 4 new test files
survived. Post-death tree sanity, verified: `py_compile` clean on every modified file (0 syntax
failures) and all four core packages import at current versions (kailash 2.62.0 / kaizen 2.45.0 /
dataflow 2.19.1 / nexus 2.15.0). **This is the payoff of the shared-tree decision over
`isolation: "worktree"`** — a worktree wave dying mid-flight would have left 6 orphan checkouts to
recover per `worktree-isolation.md` Rule 3's recovery protocol.

### Ground-truth test state established BEFORE any further edits

`120 passed / 4 failed / 1 skipped` across the Wave-5 affected suites. Notably the two shards that had
authored FABRICATED symbols had already self-corrected before dying — `test_issue_1970*` and
`test_issue_1970b*` both pass. The 4 failures were real and are now all resolved (below).

### Orchestrator inline fixes — the 4 failures

**(1) `test_embed_error_routes_through_sanitizer` — a genuine cross-shard regression.**
S2 hoisted `sanitize_provider_error` from a FUNCTION-LOCAL import (`embedding_generator.py:785`, inside
the except block) to MODULE scope (`:9`). The test patches the SOURCE module
(`sanitizer_mod.sanitize_provider_error`); a function-local import re-reads that attribute at call time
and picks the patch up, but a module-level `from X import Y` binds the name at import time, so the
patch no longer intercepts and the REAL sanitizer ran. Fix: retarget the patch to the CONSUMING module
(`embedding_mod`) — the canonical "patch where it is USED, not where it is DEFINED" idiom, and the more
robust target because it keeps intercepting regardless of the consuming module's import style.
**TEETH VERIFIED, not assumed:** replaced the sanitize call with `str(e)` → test FAILED
(`Regex pattern did not match ... 'wire failed at http://[REDACTED]...'`) → restored → 11 passed.
A retargeted test that no longer catches its original bug is worse than a red one.

**(2)(3)(4) The three `TestReasoningHelpersDoNotReportDegradedAsOk` tests.** #1981 supersedes exactly
the RETURN half of #1973's contract (`0.0` returned → `ReasoningDegradedError` raised). Updated the
three bodies to `pytest.raises(ReasoningDegradedError)` and rewrote the class docstring's
"score contract is unchanged" paragraph. **The OBSERVABILITY assertions — degraded-WARN fired with the
underlying error, and result NOT cached — were left untouched; they are this class's teeth.** Result:
`124 passed / 1 skipped / 0 failed`.

### #1981 IS INCOMPLETE — S1's fix is DEFEATED on 3 paths and CRASHES a 4th

S1 enumerated callers but missed an entire package. `packages/kaizen-agents/` has 4 call sites, and
**zero handling of `ReasoningDegradedError` anywhere in that package** (verified: grep returns nothing):

| site                                       | behavior with the raise                                                                                              | verdict                                                                             |
| ------------------------------------------ | -------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| `patterns/llm_routing.py:126` `_score_one` | **NO try/except at all** — propagates uncaught out of `select_best()` (`:107`, a ranking loop) and `score()` (`:82`) | **REGRESSION — new crash on a public ranking API that previously returned a float** |
| `patterns/_reasoning_bridge.py:~79`        | `except Exception` → `return 0.0`                                                                                    | fix NEUTRALIZED (not a regression — it returned 0.0 before too, now with a WARN)    |
| `patterns/runtime.py:~675`                 | `except Exception` → `return 0.0`                                                                                    | fix NEUTRALIZED                                                                     |
| `patterns/registry.py:~478`                | `except Exception` → `score = 0.0`                                                                                   | fix NEUTRALIZED                                                                     |

The typed degradation signal is caught by a generic handler and converted straight back into the
fabricated zero #1981 exists to eliminate — `zero-tolerance.md` Rule 3 error-hiding, and precisely the
"indistinguishable from a genuine no-match, ranking degrades to arbitrary order" failure the issue
describes. The bridges' documented intent ("one LLM failure must not sink a whole selection round") is
LEGITIMATE; the defect is that they conflate "this judge failed" with "this candidate scores 0.0".
**The correct shape already exists in-repo** — `a2a.py:3612-3673` catches per-candidate, keeps ranking
with candidates that scored, and re-raises ONLY when EVERY candidate degraded. Wave 6 shard A mirrors
that pattern into kaizen-agents (3479-test suite → before/after required).

### Wave 6 — launch ledger (orchestration-launch-ledger.md MUST-1)

| shard | task                                                                         | agent                  | status    |
| ----- | ---------------------------------------------------------------------------- | ---------------------- | --------- |
| A     | #1981 completion across `packages/kaizen-agents/` (4 sites, mirror a2a.py)   | w6-1981-kaizen-agents  | in-flight |
| B     | #1971 dialect — assess dead shard's partial work, finish, verify             | w6-1971-dialect-finish | in-flight |
| C     | #1972 nexus — assess partial work, port tests, teeth-prove, verify           | w6-1972-nexus-finish   | in-flight |
| D     | #1974 sanitizer patterns (3rd attempt; groundwork + both findings folded in) | w6-1974-sanitizer      | in-flight |

Every Wave-6 prompt carries a **`PRIOR_WORK_ASSESSMENT` step 0** — the dead shards' partial edits are in
the tree and UNVERIFIED, so each agent must read `git diff` on its own surface and state a
keep/extend/replace disposition with evidence rather than assuming the prior work is correct.

### FULL-KAIZEN SWEEP — the targeted suites were NOT enough

`pytest packages/kailash-kaizen/tests/{unit,regression}` → **6099 passed / 10 failed / 67 skipped**.
The targeted Wave-5 suites were all green at the time; these 10 were only visible on the wide run.
**`pytest.ini:83` sets `--maxfail=10`, so that run HALTED EARLY and its "10 failed" is a FLOOR, not a
total** — re-run with `--maxfail=200` to get the true count. A capped run reporting N failures is not
evidence that N is all of them.

Introduced-vs-pre-existing was established by **diff-hunk intersection** (the method this ledger
mandated above), NOT by assumption — the tree is dirty and cannot be stashed while agents are live.

**(1) `test_streaming_executor::test_error_event_on_agent_error` — INTRODUCED by the S3 sweep.**
S3 changed `ErrorEvent(message=str(e))` → `message=sanitize_provider_error(e, "Agent execution")`.
The change is CORRECT and in scope (the event stream crosses a process boundary to a consumer, so a
provider exception can ship a credential); the test asserting the raw string is what needed updating.
Updated it to assert the exact sanitized form — verified by executing the sanitizer rather than
guessing its format string:
`sanitize_provider_error(ValueError("Test error"), "Agent execution")` → `'Agent execution error (ValueError): Test error'`.
**Added a NEW companion test** proving the sanitize is load-bearing rather than decorative:
`ValueError("connect failed: postgres://admin:hunter2@db:5432/x")` → asserts `hunter2` is ABSENT and
`[REDACTED]` present in `ErrorEvent.message`. 27 passed. This UPGRADES the test rather than merely
accommodating the change — the accommodate-only path would have left the routing unguarded.

**(2) `test_ollama_vision_provider` (8 tests) — INTRODUCED by the S2 sweep, and REVERTED as scope creep.**
S2 replaced the `is_available` body — a `TODO: Implement actual health check` stub returning
`self.base_url is not None` — with a REAL `httpx.Client().get(f"{base_url}/api/tags")` probe. The 8
tests mock the extraction calls but never mocked `/api/tags`, so RESPX raised
`AllMockedAssertionError: ... not mocked!`, the probe failed, and extraction died with
"Ollama not available".
**Disposition: REVERTED the behavior change, KEPT the sanitization.** Reasons: (a) #1970 is a
credential-sanitize sweep, not a stub-implementation sweep — implementing a stub is a different change
class riding along inside a security PR; (b) it adds a synchronous network call to a sync
provider-SELECTION path (`ProviderManager._get_selection_chain`), a real latency/behavior change;
(c) **standing user disposition (2026-06-26): the ~33 production TODO markers are LEAVE-AS-BASELINE**
— opportunistically fixing one contradicts that call. The now-dead `HEALTH_CHECK_TIMEOUT_SECONDS`
constant was removed too. `is_available` is byte-identical to main again; the file's remaining diff is
purely #1970 sanitization. 25 passed.
**Surfaced, not silently dropped:** `is_available` returning `True` whenever `base_url` is set IS a
latent defect (a selection path can pick a dead Ollama). It is pre-existing, user-dispositioned
baseline, and wants its own issue + test updates — not a silent ride-along.

**(3) `test_metrics_overhead_is_minimal` — AMBIENT, not introduced.** `metrics_collector.py` is
untouched by any shard (`git status` confirms), and the test passes **3/3 in isolation**; it only
trips under full-suite load (46.82% vs a 40% cap). Note it is an ABSOLUTE wall-clock-derived threshold,
the exact ratcheting anti-pattern `testing.md` § "Complexity Bounds Use Self-Normalizing Ratios"
blocks — so it MUST NOT be "fixed" by raising the cap. Out of scope for this wave; flagged.

### UNCAPPED RE-RUN — the true kaizen number

`--maxfail=200` → **12,026 passed / 1 failed / 173 skipped** (987s).

The capped run's "6099 passed / 10 failed" was an ARTEFACT of `pytest.ini --maxfail=10` aborting the
session partway: it had not yet reached ~6,000 further tests. **A truncated run's pass count is as
misleading as its failure count** — reporting 6099 as the denominator would have understated coverage
by half. Both fixes above are confirmed by the delta: the 8 ollama failures and the streaming failure
are gone, and the metrics-overhead test passed on this run (consistent with its load-sensitivity).

The single remaining failure is `test_enterprise_memory_system::test_system_throughput_benchmark`
("Read throughput 815 ops/sec is below 1000 ops/sec"). **AMBIENT, not introduced** — the file is
untouched by any shard (`git status`), and it passes **3/3 in isolation**. It is the SAME defect class
as the metrics-overhead test: an ABSOLUTE throughput threshold that only trips under full-suite load,
which `testing.md` § "Complexity Bounds Use Self-Normalizing Ratios" names as the ratcheting
anti-pattern. Two independent instances of that class in one suite is itself worth a follow-up (convert
both to self-normalizing ratios); NOT fixed here — raising either cap is explicitly BLOCKED.

**Kaizen verdict: clean.** 12,026 passing; zero shard-attributable failures.

### CORE SDK — a verification gap the orchestrator closed

`pytest tests/unit` → **4,792 passed / 4 skipped / 0 failed** (26.8s).

**Why this run was needed and nearly missed:** S5 modified `src/kailash/db/dialect.py` — the CORE SDK,
not a sub-package. Every Wave-6 shard runs only its OWN package's suite (`kaizen-agents`,
`kailash-dataflow`, `kailash-nexus`), and the kaizen sweep covers `packages/kailash-kaizen` only. So
the core-SDK surface a shard had edited was inside NO agent's verification scope. Delegating
per-package verification leaves the shared core uncovered unless the orchestrator runs it explicitly —
**the union of the shards' test runs is NOT the union of the shards' blast radius.**

### Verified-clean baseline before Wave-6 reports land

| surface                                    | result                  | who verified            |
| ------------------------------------------ | ----------------------- | ----------------------- |
| `packages/kailash-kaizen` unit+regression  | 12,026 pass / 1 ambient | orchestrator (uncapped) |
| `src/kailash` core unit                    | 4,792 pass / 0 fail     | orchestrator            |
| `packages/kailash-dataflow`                | pending                 | Wave-6 shard B          |
| `packages/kailash-nexus`                   | pending                 | Wave-6 shard C          |
| `packages/kaizen-agents` (3,479 collected) | pending                 | Wave-6 shard A          |

### #1974 LANDED + ORCHESTRATOR-VERIFIED — and the ORCHESTRATOR'S OWN INSTRUCTION WAS WRONG

83 passed (new `test_issue_1974_sanitizer_pattern_gaps.py` + the 1960 / 1953 / 1720-b1 blast radius).
Closed: any-RFC-3986-scheme DSNs (incl. `postgresql+asyncpg://`, `mongodb+srv://`), the
`redis://:pass@` empty-userinfo case, Slack `xox[baprse]-`, bare 3-segment JWTs, GitHub
`ghp_`/`github_pat_`, Stripe `sk_live_`/`rk_test_`.

**The shard DEVIATED from the orchestrator's prescribed pattern and was RIGHT to.** I specified the
userinfo class `[^@\s]`; it shipped `[^\s]`. Verified head-to-head on the same vectors:

| vector                                         | `[^@\s]` (what I prescribed)                                         | `[^\s]` (what shipped)    |
| ---------------------------------------------- | -------------------------------------------------------------------- | ------------------------- |
| `postgres://user:p@ssw0rd@host/db`             | `…[REDACTED]:[REDACTED]@ssw0rd@host/db` — **partial password LEAKS** | fully redacted            |
| `postgres://ad@corp.com:pw@host/db`            | **NO MATCH — whole credential leaks**                                | fully redacted            |
| `https://example.com:8080/r?url=user@host.com` | over-redacted                                                        | over-redacted (IDENTICAL) |

RFC 3986 requires `@` inside userinfo to be percent-encoded, but real DSN passwords and
email-shaped usernames carry a literal one constantly. My narrow class stops at the FIRST `@`,
so it under-redacts — the strictly worse failure per this module's own documented posture.
**An orchestrator instruction is a hypothesis too.** I caught the shard's earlier claims by re-running
them; this time re-running caught MY error. The rule is symmetric: verify the instruction, not just
the response.

**Not a regression (checked, not assumed):** the over-redaction of a legitimate URL carrying a port AND
an `@` in a query param is IDENTICAL under both classes — inherited from the original
`(https?://)[^@\s]+:[^@\s]+@`, not introduced by #1974. It matches the documented
over-redact-beats-under-redact posture. Left as-is; noted.

**ReDoS bound verified, not taken on faith.** The shard added `{0,256}` bounds citing quadratic
backtracking on colon-dense non-matching input. Measured on `http://` + `"a:"*n`:
4,007 B → 0.68 ms; 16,007 B → 1.51 ms; 64,007 B → 4.38 ms. 16× input → ~6.4× time: sub-quadratic, bound
holds. This matters because the sanitizer runs on an error path an attacker can influence (a provider
echoing back user input).

### #1972 LANDED + ORCHESTRATOR-VERIFIED — and it carries a BREAKING public-API change

Shard-claimed and independently re-run by the orchestrator: **1,880 passed / 1 skipped / 0 failed**
(nexus unit+regression). Hygiene claims verified, not accepted: 7 changed files ALL inside
`packages/kailash-nexus/`; **zero** `TEETH` markers left in the tree; version anchors deliberately
UNTOUCHED (`pyproject.toml` + `__init__.py` stay 2.15.0 — the bump is the release step's).

**The reconciliation held.** 2 of 3 were stale tests asserting a mock-only surface: they wrote to
`_mcp_server._tools`, a dict that exists ONLY on the FastMCP fallback shim and is invisible to the
JSON-RPC handlers, which iterate `_tool_registry`. So pre-guard, **no workflow was ever really
registered as an MCP tool** — the old tests passed solely because they injected `MagicMock(_tools={})`.
Ported to assert the REAL registry AND that `tools/list` actually advertises the tool. Teeth proven by
removing each guard and capturing the failure, then restoring.

**⚠ BREAKING — needs a human product call before release.** `Nexus.register()` now runs
`validate_workflow_name` (it was the ONLY registration surface that skipped it; `_execute_workflow` and
`_register_handler_workflow` already ran it, so a name could register "successfully" then HTTP-400 on
every execute forever). The charset moved from a shell-metacharacter BLOCKLIST to the SEP-986 MCP
allowlist `[A-Za-z0-9_-.]`. Orchestrator-verified rejection set — **broader than the report's framing**:

```
ACCEPT  'my_workflow'      'my-workflow.v2'
REJECT  'my workflow' (space)   'a&b'   'order#1'   'wf(1)'   'café'  ← NON-ASCII now rejected
```

Non-ASCII names are the under-advertised half: any downstream consumer using accented or CJK workflow
names breaks on upgrade. The fix is RIGHT (the register/execute asymmetry is the worse defect, and
unicode silently percent-encodes so the `workflow://` resource stops round-tripping) — but this is a
**minor bump, not a patch**, and the disposition is the user's, not the agent's or mine.

**Beyond scope, same bug class (kept):** the silent-registration-failure path now raises instead of
logging a warning and returning while `register()` printed "✅ registered successfully"; an orphan
`_create_mock_mcp_server()` (a mock server living in PRODUCTION `core.py`, zero callers) removed per
`zero-tolerance.md` Rule 2; a pre-existing order-dependent regression test fixed after being proven
failing at **pure HEAD** (its `_leaked_runtimes()` did an unscoped `gc.get_objects()` sweep, making it a
whole-PROCESS leak detector that any earlier test holding a runtime would fail — rescoped to a
before/after delta, teeth-proven).

**OPEN CONTRADICTION (recorded, not resolved):** the guard docstring states direct `_tools` writes are
BLOCKED, yet the fallback branch still performs one — currently unreachable for every server type in
this repo, but the contradiction is a public-behavior call, deliberately left for a human.

### #1981 + #1971 LANDED — Wave 6 complete, all 5 forest items closed

**#1981** (`kaizen-agents`, 21 pass on its regression suite). All four sites mirror the `a2a.py`
reference: `llm_routing.score()` propagates with a WARN (single query, no round to sink);
`select_best()` EXCLUDES degraded candidates from the ranking and raises only when EVERY candidate
degrades; `_reasoning_bridge` / `runtime` / `registry` each catch `ReasoningDegradedError` BEFORE the
generic `except Exception` that previously converted it straight back to a fabricated `0.0`.
**Bonus find, arguably the wave's best:** `packages/kaizen-agents/conftest.py` carried only HALF the
cost guard — the provider-secret scrub but NOT the `requires_real_llm` marker gate. Tests needing a
live judge therefore RAN, against a scrubbed credential, and "passed" through whatever fallback their
subject offered. That is the #1981 fake-pass shape living in the test harness itself.

**#1971** (19 pass / 4 skip on its own file; dataflow 4,430 pass / 17 fail — all MySQL credential
rejection). Canonical `POSTGRES/MYSQL/SQLITE_MAX_IDENTIFIER_LENGTH` promoted to
`src/kailash/db/dialect.py` as single source of truth, with the DataFlow hierarchy importing rather
than restating, so the two live dialect hierarchies can no longer drift on the value that decides
whether an identifier is legal. Same-class extra: `normalize_identifier` fitting for GENERATED index
names (`idx_{table}_{cols}` overflowed the PG-63 budget by construction, so the recommendation engine
raised for exactly the tables most needing an index).
**HONEST LIMITATION:** #1971's Tier-2/3 real-Postgres leg CANNOT be validated in this environment —
MySQL :3306 and Postgres :5433 both refuse credentials. SQLite + unit-level dialect logic are
verified; the Postgres path is NOT, and must not be reported as though it were.

### ORCHESTRATOR ERROR — a transient mid-write tree read as a finding

I reported to the user that shard B had "destroyed its own source work": `git status` showed its five
source files unmodified and `git diff` came back EMPTY, leaving only an orphan test that broke
collection. **That was WRONG.** The agent was still alive and mid-write; minutes later all five files
were present and its tests passed. I had already applied the "a live diagnostic against a file another
agent is editing is a SNAPSHOT, not a finding" lesson to pyright — and then failed to apply it to
`git status` / `git diff`, which are exactly as snapshot-shaped. Caught before acting (I was about to
relocate the test file), but stated to the user as fact first.
**Generalized rule: on a tree with live agents, NO read is a finding until it is re-confirmed after
the writer goes idle.** This is the same class as `zero-tolerance.md` Rule 1c (post-context-boundary
claims are structurally unfalsifiable) applied to concurrent writers rather than context boundaries.

### ORCHESTRATOR-INDUCED TEST NOISE (own it)

Several "failures" triaged this session — `sqlite3: disk I/O error` in kaizen-agents state_manager,
and both ABSOLUTE-threshold perf tests — correlate with the orchestrator running multiple full suites
CONCURRENTLY alongside four live agents. The nexus shard independently reported the same
(`test_real_world_startup` red under sibling load, clean on re-run). Heavy suites are now serialized.
A perf assertion measured under self-inflicted load is not evidence of a regression.

### Wave 7 — holistic redteam ROUND 1 (agents.md § Holistic Post-Multi-Wave Redteam)

Union scope materialized to `04-validate/wave56-union.diff` (8,529 lines; 70 files +2336/−387 plus 6
new test files inlined) — required because `security-reviewer` is READ-ONLY and would otherwise halt
at the diff it cannot fetch (`agents.md` § read-only reviewer materialization).

| reviewer | agent                              | lens                                                                                             |
| -------- | ---------------------------------- | ------------------------------------------------------------------------------------------------ |
| 1        | rt1-correctness (`reviewer`)       | per-issue AC satisfaction + sweep completeness + **the orchestrator's OWN 4 edits**              |
| 2        | rt1-security (`security-reviewer`) | credential shapes that still escape; mask-at-one-surface-only; register() allowlist as a control |
| 3        | rt1-teeth (`testing-specialist`)   | closure-parity: remove each fix, prove a test fails, restore                                     |

Each prompt carries the ALREADY-CAUGHT defect list (fabricated symbols, the detached monkeypatch, the
stub scope-creep) so round 1 hunts what was MISSED rather than re-finding what was already fixed, plus
the environment traps (`--maxfail=10` truncation, unreachable DBs, `.venv/bin/python`) and the
evidence gate (errored/empty = ZERO evidence, never a clean round).

### ROUND 1 — SECURITY LENS REPORTED. NOT CLEAN. 2 HIGH confirmed by orchestrator.

**Process note:** `rt1-security` first went idle with NO report — per `agents.md` § Redteam Dispatch
that is ZERO evidence and CANNOT be scored a clean round. Resumed it from its transcript (cheaper than
re-running the lens) and it returned a complete report. **This is the SECOND agent this session to go
idle without delivering** (`w6-1974-sanitizer` was the first, verified from the tree instead).
A silent-idle agent must never be counted as a pass.

**HIGH-1 — `observability/trace_exporter.py:375-385` + `:427-437` — INTRODUCED (partial coverage).**
ORCHESTRATOR-CONFIRMED by reading the source. The wave sanitized the RAISED message but left
`logger.exception(...)` on the SAME `exc` ten lines above raw. `logger.exception` emits `exc_info`,
whose traceback's final line is the unmodified `str(exc)`. The sanitizer sits inside
`if self._raise_on_error:` — which is `False` by default at ALL THREE constructors (`:303`, `:542`,
`:563`). **So the DEFAULT configuration logs the raw provider exception.** The wave's own comment at
`:387-389` names the threat verbatim ("its exception can echo the ingest token"). The sanitizer was
added only to the branch that is off by default — a fix that cannot fire for the normal user.
The wave fixed this EXACT shape at five siblings (`judges/_judge.py:667` explicitly drops `exc_info`
for this reason; also `tools/native/task_tool.py:252`, `strategies/multi_cycle.py:489`,
`nodes/ai/llm_agent.py:1265`/`:2547`) — so the correct pattern is established in-repo and this site
simply missed it. Violates `observability.md` MUST Rule 6.3 (mask at EVERY surface).

**HIGH-2 — `llm/reasoning.py:609-617` + `:729-737` — sweep gap in a function this wave rewrote.**
ORCHESTRATOR-CONFIRMED. TWO leak surfaces per site: `logger.exception(...)` (raw traceback) AND an
explicit `extra={"error": str(exc)}` (raw field). `agent.run(...)` at `:606`/`:722` IS the provider
dispatch — the seam sanitized everywhere else in this wave. #1981 rewrote the `.degraded` WARN 15
lines BELOW each of these in this same wave and left the `.error` sibling untouched. Per
`security.md` § Multi-Site Kwarg Plumbing (every call site, same PR) + `zero-tolerance.md` Rule 1
this is a sweep gap, NOT a deferrable pre-existing.

**MEDIUM-2 is a `verify-claims-before-write` violation in a CHANGELOG.** #1972's CHANGELOG asserts
"`register()` was the only registration surface that skipped it" — but `nexus/registry.py:102`
(`HandlerRegistry.register_workflow`, PUBLICLY exported at `nexus/__init__.py:64`) and
`nexus/transports/http.py:346` also write without validating. The durable claim is false as written
and MUST be corrected before it ships (`security.md` § Enforcement-Surface Parity: a new fail-closed
dimension lands at EVERY independent validation surface in the same PR).

**MEDIUM-3 — the `{0,256}` ReDoS bound created a coverage hole AND its comment's rationale is wrong.**
The comment claims "a longer opaque secret is claimed by the 40-char contiguous-run rule above" —
FALSE for any long secret containing `-`, `_`, or `.` (all outside `[A-Za-z0-9/+]`, so they break the
run). A >256-char hyphenated DSN password escapes entirely; the pre-#1974 unbounded `[^@\s]+` did not
have this hole. Realistic instance: a Cloud SQL IAM OAuth token as DSN password. The bound itself is
sound and MUST stay — the comment overstates residual coverage and a coarse `://[^\s]*@` fallthrough
is wanted.

Also: MEDIUM-1 (`web.py:127` `HTTPError` branch unsanitized while a NEW comment claims both handlers
are covered — `HTTPError` subclasses `URLError` so it never reaches the sanitized handler; sibling
`tools/api.py:248` DOES sanitize the same shape), LOW-1 (allowlist permits a LEADING `-`, so `--force`
is a legal workflow name while the docstring claims CLI-argument safety), LOW-3 (`core.py:1745` logs
`workflow_{name}` but registration uses `{name}`), LOW-5 (module-scope `kaizen.nodes.ai` imports added
in `providers/` — a layering inversion the same wave deliberately avoided elsewhere with lazy imports).

**The lens also tried to FALSIFY the orchestrator's own prior conclusions and could not** — it
independently re-derived that `[^@\s]` leaks the tail of `postgres://user:p@ssw0rd-x@db/app` and fails
to match `postgres://ad@corp.example.com:s3cret@db/app` at all, confirming the `[^\s]` deviation was
correct. Adversarial confirmation of a prior finding is worth more than agreement.

**ESCAPES still open (in stated threat model):** query-string credentials (`?api_key=`, `?token=`,
`?sig=`) — NO rule matches a query parameter, yet FOUR comments this wave added name that exact vector;
`Authorization: Basic <base64>` (only `Bearer` is covered); Azure SAS signatures (percent-encoding
fragments the 40-char run); short vendor-less keys.

**Fixes deliberately DEFERRED until the other two reviewers go idle** — `reasoning.py` is precisely
what `rt1-teeth` must mutate to teeth-prove #1981, and editing into its proof window risks it
restoring over a security fix I would then believe had landed. Recording first, applying after.

### ROUND-1 FINDINGS FIXED (all HIGH + MEDIUM). Restore verified FIRST.

**Restore gate passed BEFORE any edit.** `rt1-teeth` went idle with no report (THIRD silent-idle this
session). Rather than trust a `RESTORE_PROOF` it never sent, the union diff was regenerated and
compared byte-for-byte against the pre-redteam snapshot: **8,529 lines both sides, IDENTICAL** — every
teeth-proof edit reverted. The pre-dispatch artifact was what made this mechanical rather than a
judgment call; capturing it before the redteam was worth more than any agent's self-attestation.

| finding                                | fix                                                                                                                               | teeth                                                                                                                                                             |
| -------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| HIGH-1 trace_exporter default-path log | `logger.exception` → `logger.error` + sanitized `error` field, both sites; import hoisted; raise reuses `sanitized`               | reverted → test FAILED with the DSN visible in BOTH `error` and the `exc_info` traceback → restored                                                               |
| HIGH-2 reasoning `.error` ×2           | same conversion; raw `str(exc)` → `sanitize_provider_error(...)`                                                                  | reverted → FAILED. **Key detail: the `error` field was STILL sanitized and the TRACEBACK alone leaked** — proving the exc_info half is independently load-bearing |
| MED-1 web.py `HTTPError`               | sanitized; comment corrected ("both" → ALL THREE) + notes `HTTPError` SUBCLASSES `URLError` so it never reaches the sanitized arm | covered by existing web tests                                                                                                                                     |
| MED-2 nexus surface parity             | `HandlerRegistry.register_workflow` now validates before mutating; **false CHANGELOG claim corrected**                            | behavioural: rejects `bad name`/`a&b`, no leftover state                                                                                                          |
| MED-3 >256 userinfo hole               | new `_URL_WITH_AUTH_OVERFLOW` + wrong rationale corrected in-comment                                                              | 272-char hyphenated pw: leaked → redacted                                                                                                                         |

New regression file `tests/regression/test_issue_1970_log_surface_parity.py` (3 tests) pins the LOG
surface. **The pre-existing test for that site passed `raise_on_error=True` — exercising the branch
that was already safe. That is precisely why a 12,026-test green suite hid a default-path leak: the
test and the defect were on different branches.**

### ORCHESTRATOR INTRODUCED A ReDoS WHILE FIXING A LEAK — caught, fixed, pinned

The first `_URL_WITH_AUTH_OVERFLOW` used `[^\s@]*:[^\s@]*@`. Reasoning at the time: "each run is
terminated by the very character the pattern must reach next, so there is no blowup." **WRONG** — the
first run can match `:`, so it retries every interior colon against every suffix. Measured:
**4 KB → 59 ms, 16 KB → 923 ms, 64 KB → 14,797 ms** (quadratic) on an error path an attacker can
influence. Fixed by excluding `:` from the FIRST run (`[^\s@:]*:[^\s@]*@`), making the split point
deterministic: **64 KB → 5.16 ms**, linear. Pinned by a new self-normalising 8×-ratio test, and the
comment now says explicitly "Do NOT simplify this back to `[^\s@]*`".

**The shard's OWN test would have caught it.** `test_url_auth_scan_is_linear_not_quadratic` asserts an
8×-step ratio < 25; the broken version measured ~252×. A test written by an agent I had spent the
session second-guessing was the standing guard against the orchestrator's error. Adversarial review
runs in both directions.

### Round 1 verdict: NOT CLEAN → convergence requires round 2 (then a clean round 3)

Per `commands/redteam.md` § Convergence Criteria (2 consecutive clean rounds on BUG + INVEST-NOW),
round 1 found 2 HIGH + 3 MEDIUM, all now fixed. Round 2 must re-review the UNION **including these
orchestrator fixes**, which are themselves unreviewed code — one of which was a ReDoS.

**Deferred (INCREMENTAL, non-blocking, carried to `/sweep`):** LOW-1 allowlist permits a LEADING `-`
so `--force` is a legal workflow name while the docstring claims CLI-arg safety (narrow the claim OR
reject leading `-`); LOW-3 `core.py:1745` logs `workflow_{name}` but registers `{name}`; LOW-5 the
`providers/ → nodes.ai` module-scope layering inversion (import cost only — the crash class was
checked and does NOT reproduce, `aiohttp` is a hard dep). Plus the still-open ESCAPES: query-string
credentials (`?api_key=`/`?token=`/`?sig=`) — NO rule matches a query parameter today though four
comments added this wave name that vector — `Authorization: Basic`, and Azure SAS signatures.

### ROUND 2 — IN FLIGHT. All three lenses re-dispatched; TWO were never covered in round 1.

**Silent-idle is now systematic, not incidental: FIVE occurrences this session**
(`w6-1974`, `rt1-security`, `rt1-teeth` ×2, `rt1-correctness`, `rt2-security`). An agent completes and
returns no final payload. **Working remedy: resume via message — it recovered `rt1-security`'s FULL
report (the one that found both HIGHs) at no re-run cost.** Only re-dispatch a lens after a resume
also comes back empty. Standing consequence: of round 1's three lenses only SECURITY ever reported, so
**correctness and teeth were never covered** — round 2 treats both as never-run rather than as passes.
Scoring a silent-idle as clean would have manufactured a convergence that never happened.

| lens        | agent           | note                                                                                                                                                                     |
| ----------- | --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| teeth       | rt2-teeth       | round-1 lens NEVER covered; prioritised on the 4 fixes not yet teeth-proven (#1971 selection, #1972 register()+ported FastMCP, #1974 vendor rules, #1981 raise contract) |
| security    | rt2-security    | verify the 5 round-1 fixes + hunt past the known-open escapes                                                                                                            |
| correctness | rt2-correctness | round-1 lens NEVER covered                                                                                                                                               |

**Every round-2 prompt targets the ORCHESTRATOR's own round-1 fixes as PRIORITY** — six unreviewed
changes, one of which was already a self-inflicted ReDoS. The sharpest question was handed to the
security lens precisely because I am the wrong person to answer it: does `_URL_WITH_AUTH_OVERFLOW`'s
`:`-exclusion (added for linearity) create a MISS on a URL whose first `:` after `://` is not the
user/pass separator? And do the bounded + overflow rules compose safely in sequence?

**RESTORE VERIFICATION — the byte-comparison baseline is now INVALID and a structural check replaces
it.** `wave56-union.diff` predates the round-1 fixes, and mutation had already begun before a fresh
snapshot could be taken, so a diff-of-diffs would now report my OWN fixes as drift. Restore is instead
asserted structurally once every agent is idle:

1. `nexus/registry.py` → `validate_workflow_name(name)` UNCOMMENTED (rt2-teeth currently has it
   commented behind a `# TEETHPROBE` marker — expected, mid-proof, MUST NOT be reverted by hand)
2. `trace_exporter.py` → 0 `logger.exception(` CALL sites (comment text mentions it — grep must be
   anchored `^\s*`), 2 `logger.error(`
3. `llm/reasoning.py` → 2 `raise ReasoningDegradedError`, 0 `logger.exception(` calls
4. `error_sanitizer.py` → `_URL_WITH_AUTH_OVERFLOW` defined AND `.sub`-applied
5. `web.py` → HTTPError arm sanitized · 6. `embedding_generator.py` → sanitized at the raise site
   **Marker grep MUST cover `TEETHPROBE` as well as `TEETH-TEMP`/`TEETH-CHECK`** — round 2's agent chose a
   different marker string than round 1's, so a grep pinned to the old string would have reported a clean
   tree over a live probe.

**Suite results taken DURING round 2 are VOID.** The kaizen run kicked off before rt2-teeth began
mutating overlaps it and is measuring deliberately-broken source; discarded rather than reported.
Re-run all suites only after every agent is idle. This is the third instance of the same lesson this
session (pyright mid-edit, `git status` mid-write, now pytest mid-mutation): **on a tree with live
writers, no measurement is evidence until re-taken after they stop.**

### `rt2-security` RESUME ALSO CAME BACK EMPTY → orchestrator answered its own questions empirically

The resume remedy failed for the first time (`rt2-security` idled twice). Rather than burn a third
dispatch, the two questions were answered by EXECUTION — they were empirical all along, and the
orchestrator wrote the regex, so the honest move was to test it, not to re-ask:

**Q2 — do the bounded + overflow rules COMPOSE safely?** YES. The overflow rule DOES re-match the
bounded rule's own output (`scheme://[REDACTED]:[REDACTED]@…` contains a `:`), but the substitution is
IDEMPOTENT — identical bytes out. Verified by feeding sanitized output back through. No corruption.

**Q1 — does the `:`-exclusion create a MISS?** NO, for its target class. RFC 3986 makes the FIRST `:`
in userinfo the separator (a username cannot carry a raw `:`), so `postgres://user:pa:ss:word@h/db`
and a 300-char password with embedded colons are both still fully claimed.

**Q1b — but the question surfaced a DIFFERENT, REAL gap neither redteam lens found:**
`scheme://<token>@host` — userinfo with **NO password half**. BOTH user:pass rules require a literal
`:`, so a bare token in the USERNAME position matched NEITHER. Verified leak:
`https://s3cretT0kenValue@api.example.com/v1` → unredacted. This is the standard git-over-HTTPS-with-PAT
shape and the token-as-basic-auth-username shape. Only tokens carrying a recognised VENDOR PREFIX were
caught incidentally by `_CREDENTIAL_PATTERNS` (which is why `ghp_…@github.com` looked fine and masked
the class). **PRE-EXISTING** — the original `https?://[^@\s]+:[^@\s]+@` required the colon too.

Closed by `_URL_WITH_USERINFO_ONLY = ([A-Za-z][A-Za-z0-9+.-]*://)[^\s@:/]+@`, applied LAST.

- `/` excluded from the userinfo class so a PATH segment is never mistaken for userinfo:
  `https://example.com/@handle` and `git://host/user@thing` pass through untouched (verified).
- Ordering is load-bearing and pinned by a test: the user:pass rules rewrite to
  `…[REDACTED]:[REDACTED]@` which CONTAINS a `:` and is therefore invisible to this no-colon rule. If
  the order were inverted the user/pass split would collapse to a single `[REDACTED]`.
- 119 sanitizer tests pass; 3 new parametrized test groups pin the gap, the path-segment
  non-over-redaction, and the ordering guard.

**Method note worth keeping:** two independent adversarial reviewers looked at this module and neither
found the no-colon shape. It surfaced only from trying to FALSIFY a specific claim about my own code
("does excluding `:` create a miss?") with executable vectors. Targeted falsification of a named claim
beat general review — and the orchestrator asking the question of ITSELF, with a runnable test, was
what closed it.

### ROUND 2 — CORRECTNESS LENS REPORTED (after resume). NOT CLEAN. Found MORE than round 1.

The resume remedy worked again (2 of 3 recoveries succeeded overall). The report was the strongest of
the session: it MEASURED closure-parity with a read-only in-process harness (no tree mutation),
CORRECTED its own earlier idempotence claim ("that was a string-split bug in my probe"), and flagged
which findings were discovered through a live `rt2-teeth` probe vs durable. Self-correction inside a
review is worth more than confidence.

**C1 — MY OWN FIX WAS UNPROTECTED.** `HandlerRegistry.register_workflow` validation shipped with ZERO
test coverage: with the check removed the FULL nexus suite still passed `1880 passed, 1 skipped`, and
the surface accepted `'my workflow'`, `'a&b'`, `'naïve'`, and `'a/b'` (a path separator). I had
verified the fix BEHAVIOURALLY at the time and stopped there — a behavioural check proves the code
works TODAY; only a test keeps it working. **Fixed:** 9 new tests in
`tests/regression/test_issue_1972_registration_surface_parity.py`.

**C2 — MY ACCEPTED BREAKING CHANGE CAUSED A REAL REGRESSION.** `_auto_discover_workflows`
(`core.py:3982`) calls `self.register(...)` with NO try/except, and discovery derives names from
FILENAMES (`file_path.stem`). Since #1972 tightened `register()`, ONE legal file — `sales
report.workflow.py`, `étude_workflow.py`, `v1(final)_workflow.py` — now raises out of the loop, so
every OTHER discovered workflow silently fails to register and `Nexus.start()` aborts. Previously all
registered. **This is the second-order cost of a tightening nobody traced to its callers.** Fixed:
catch `ValueError` per file, WARN with the offending name + remediation, `continue`. Teeth-proven
(swapped the caught type → `ValueError` escaped → test failed → restored).

**C3 — the kaizen CHANGELOG asserted the OPPOSITE of the shipped code.** `[Unreleased]` still read
_"The `0.0` return contract is unchanged … #1981 … is NOT fixed here"_ while the tree ships the raise.
A BREAKING change to two exported helpers had NO entry, and a standing entry DENIED it. #1970, #1974
and the `ErrorEvent.message` format change were also unrecorded. **This is the SECOND false-CHANGELOG
of this wave** (nexus was the first) — durable artifacts drift from code by default, and the drift is
invisible to every test. Rewritten with the BREAKING section, caller-update note, and migration line.

**H0 — my new `_URL_WITH_USERINFO_ONLY` misses a `/`-bearing token.** Verified:
`https://AbCd+9/xYz123456789@api.example.com/v1` is NOT redacted (base64's alphabet includes `/`,
which the userinfo class excludes). **Dispositioned as an ACCEPTED RESIDUAL, documented in-source with
the reasoning** rather than "fixed": RFC 3986 ends the authority at the first `/`, so a `/` before the
`@` puts the `@` in the PATH — admitting `/` would redact `https://example.com/some/path/@handle`
(common, credential-free) to catch a malformed shape, and 40+ contiguous `[A-Za-z0-9/+]` is already
claimed by the AWS rule. The comment names the correct future fix (a LENGTH-ANCHORED companion), so
the next reader does not widen the class.

### STILL OPEN after round 2 — the #1970 sweep is NARROWER than it appears

| id              | gap                                                                                                                                                                         | status                                               |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| H1              | `nodes/ai/a2a.py` — 4 raw `str(exc)` provider-exception logs (`:1920/:2285/:2418/:2629`); `grep -c sanitize_provider_error` = **0** in a file this wave opened for #1981    | OPEN                                                 |
| H2              | `packages/kaizen-agents` essentially UNSWEPT — 8 sites incl. two `runtime_adapters` using `logger.exception` (the exact traceback-defeat mechanism)                         | OPEN                                                 |
| H3              | `rag/similarity.py:682` missed while sibling `rag/advanced.py` got 7 sanitize calls                                                                                         | OPEN                                                 |
| H4              | **No mechanical completeness invariant** — the sweep test is 7 hand-picked shapes, so H1/H2/H3 and every future site are invisible to CI                                    | OPEN — the structural gap that lets the others exist |
| M1              | `trace_exporter` now loses the stack trace on its only firing surface (sanitize `traceback.format_exc()` instead)                                                           | OPEN                                                 |
| M2              | `test_issue_1720_b1:156` still patches `sanitizer_mod`; works ONLY because `base_agent.py` imports function-locally — one hoist detaches it, the exact bug already hit once | OPEN                                                 |
| M3/M4/M5, L1-L4 | residual hardcoded 63/128; empty DataFlow `[Unreleased]`; alert_manager Slack bypass; dead ollama handler+false comment; examples calling now-raising APIs                  | OPEN                                                 |

**Honest convergence position: NOT CLOSE.** Round 2 found MORE than round 1, and H4 explains why —
without a mechanical completeness invariant the sweep's true coverage is unknown, so each review round
finds another hand-missed site. Rounds will keep finding them until the invariant exists.

### H4 CLOSED AS A MEASUREMENT — the enumerator exists, and it validates against hand-findings

`04-validate/find-unsanitized-provider-errors.py` — AST sweep for `except … as <v>:` handlers that
render `<v>` into a **log call**, a **dict literal value**, or a **raise**, without routing through
`sanitize_provider_error`. Provider-adjacency is REPORTED, not assumed: HIGH only when the enclosing
try-body calls something provider-shaped; everything else is LOW, because blanket-sanitizing a local
error destroys diagnostics and is its own defect (`zero-tolerance.md` Rule 3).

**Validation — it independently reproduces every hand-found gap, to the line:**

- `nodes/ai/a2a.py` → flags `:1920 :2285 :2418 :2629`, **exactly** the four the correctness lens named
  by hand (H1), each `dict['error'] + dict['error_type'] + log.warning` via `.run()` (the real
  `LLMAgentNode` dispatch).
- `nodes/rag/similarity.py` → flags `:682`, **exactly** H3's site, plus 6 structural siblings.
- `kaizen_agents/` → flags `patterns/state_manager.py` ×6 and the adapter surfaces (H2).

Two independent methods — a human-style review and a mechanical enumeration — converging on the same
lines is the strongest evidence available that both are correct.

**Reported honestly as an UPPER BOUND, not a leak count: HIGH=178 / LOW=287.** The `PROVIDER_CALL_HINTS`
list includes generic names (`get`, `run`, `call`, `send`), so `.get()` hits conflate `dict.get()` with
an HTTP GET — visible directly in the output (`similarity.py`'s 7 are all `.get()`; a2a's confirmed 4
are all `.run()`). **178 is the candidate set to triage, NOT 178 leaks.** Stating it as a leak count
would be exactly the fabricated-precision failure this ledger has been guarding against all session.
Next step for whoever picks this up: tighten the hint list (or resolve the receiver type) so `.get()`
splits into HTTP-vs-dict, then pin the surviving set as a CI ratchet that fails when it GROWS.

**Why this was the right last move rather than fixing more sites:** the wave added ~120 sanitize calls
by hand and three separate review passes each still found more. The binding constraint was never
effort — it was that nobody could answer "is it complete?". Now that question is mechanical, and the
remaining work is a bounded triage list instead of an unbounded review loop.

### ROUND 2 — TEETH LENS FINALLY REPORTED (3rd resume). Found 2 defects 3 prior passes missed.

The lens that failed to deliver three times produced the round's most valuable output on the final
resume. It MEASURED all three items previously only structurally-teethed, and independently
re-derived the `HandlerRegistry` gap before confirming my 9-test fix closed it (`7 failed, 2 passed`
after the fix, vs `1880 passed` / zero teeth before). **Persisting through three silent-idles was
worth more than re-dispatching**; the resume remedy is now 3-for-4 overall.

Measured teeth (all restored clean): **#1981** raise contract → reverting both raise sites gives
`16 failed`; **#1971** dialect selection → teethed in BOTH directions (removing the fit helper `2
failed`; re-hardcoding `postgresql` — the original bug shape — `5 failed`, with one test failing on
BOTH inversions, the correct shape for a selection test); **#1972** ported FastMCP tests → reverting
the raise gives `2 failed: DID NOT RAISE`.

**HIGH — ReDoS #2, INTRODUCED by the wave (the #1974 shard's scheme broadening, which I reviewed and
accepted).** `(https?://)` → `([A-Za-z][A-Za-z0-9+.-]*://)` traded a FIXED LITERAL (O(1) fail per
start position) for an unbounded greedy run. On input with a long alphanumeric run and NO `://`,
orchestrator-verified: 4 KB 7.9 ms / 16 KB 112 ms / **64 KB 1773 ms**, against 0.015 ms pre-wave.
Fixed by bounding the scheme `[A-Za-z0-9+.-]{0,31}://` in ALL THREE URL rules → 64 KB **0.11 ms**,
with exact correctness parity re-verified on all 8 prior vectors and no new over-redaction.
**The critical insight: `test_url_auth_scan_is_linear_not_quadratic` CANNOT catch it** — its input
`"http://" + "a:"*n` CONTAINS `://`, so the scheme matches immediately and never backtracks. A
linearity test is only as good as the shape of its input; this one was structurally blind to a
regression in the very pattern it guards. New test uses input with NO scheme at all.
(Possessive `*+` does NOT help — the backtracking is over START POSITIONS, not inside the group.)

**CRITICAL — the web.py `HTTPError` sanitize I added in round 1 had ZERO teeth.** Reverting it left
the whole suite green while `HTTP Error 401: Unauthorized for postgres://admin:hunter2@…` leaked.
Two independent blind spots: the sweep test raises a PLAIN exception (landing in the generic
`except Exception` arm, never the `HTTPError` arm), and the structural test only greps the file for
the string `sanitize_provider_error`, which the OTHER TWO arms already satisfy. A grep-based
"structural" test proves a string exists, not that the branch under test routes through it.

### ORCHESTRATOR NEAR-MISS ×2 IN ONE TEST — the vacuous-test class, self-inflicted

Writing the web.py teeth test, I shipped it broken TWICE and only caught it by checking the skip count:

1. **It SKIPPED.** I patched `web.urlopen`; the module calls `urllib_request.urlopen`. My own
   `pytest.skip("not patchable in this build")` guard swallowed the mismatch and reported a SKIP —
   coverage-shaped, zero coverage. **The guard I wrote to be defensive is what hid the defect.**
   Removed entirely: a guard that converts "my test is wrong" into "environment differs" is strictly
   worse than a loud failure.
2. **It then failed on a coroutine.** `fetch_url` is async; unawaited, every assertion would have
   passed vacuously against a coroutine object. Added an `isinstance(result, dict)` assert so the
   shape is pinned, not assumed.
   Both are the exact class this wave kept finding in shard-written tests. **The `-rs` skip-report flag
   is what surfaced #1** — a green count alone would have concealed it. Run `-rs` on any new test file.

### FINAL VERIFIED STATE (clean tree, post-all-fixes)

nexus **1,889 / 0 failed** · kaizen **12,041 / 0 failed** · core **4,792 / 0 failed** ·
dataflow 4,430 / 17 (all MySQL credential-rejection, infra) · kaizen-agents 3,391 / 23 (env, disk I/O
under load). Sanitizer + log-surface suites **119 passed, 0 skipped**. Zero probe markers.

**NOT CONVERGED — and the evidence now says why.** Six defects surfaced AFTER the wave declared done
(3 credential leaks, 2 ReDoS, 1 functional regression, plus 2 CHANGELOGs contradicting shipped code);
five of six were invisible to a 12,041-test green suite. Every genuinely NEW lens found more, and the
teeth lens — the last to report — found two that three prior passes missed. Round 3 should be a
DIFFERENT lens, not a repeat: the marginal value came from new perspectives and from targeted
falsification of named claims, never from re-running a lens that already passed.

### THE ROUND-1 LENS REPORTED ~6 HOURS LATE — and found the session's only COMMIT-BLOCKER

`rt1-correctness` surfaced long after its round was closed. Resumed with the CLOSED-list attached and
an explicit "reply 'all superseded'" option, so a stale review could not re-report fixed work as open.
It dropped everything superseded and returned 8 live findings — **validating the late-resume over
writing the lens off.** A stale reviewer with a scoped ask is still worth reading.

**S5 — FIXED — CI-BLOCKING, and the only defect this session that would have stopped a commit dead.**
`black --check` on the 75 wave-touched files: **9 would reformat**. `.pre-commit-config.yaml:7-12` runs
black, so the very first `git commit` fails. Proven INTRODUCED, not pre-existing: the same files from
`git show HEAD:` pass black cleanly (verified on a 3-file sample). Cause is mechanical and uniform —
the #1970 import inserted with no blank line before `logger = …`. Fixed by running the repo's OWN
formatter over the wave files; re-verified `75 files would be left unchanged`, kaizen imports, 101
sanitizer/log-surface tests green. **Repo-wide black reports 61 files — that number is NOT the signal;
52 are pre-existing. Scoping the check to the wave's own files is what separated introduced from
ambient**, exactly as with every other finding this session.

**Recorded, NOT fixed — the highest-value items for whoever continues (all reviewer-verified with
reproductions; re-verify before acting):**

| id          | severity | finding                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| ----------- | -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| NEW-1       | CRITICAL | `src/kailash/db/dialect.py` — `_validate_identifier(max_length=128)` defaults to the **SQLite** limit and **21 call sites pass nothing** (AST-enumerated; 0 pass it). `PostgresDialect.upsert()` ACCEPTS a 100-char identifier while its own `quote_identifier()` REJECTS it — two validators on the same object disagree, and `upsert()` interpolates the bare name into SQL. **This is #1971's exact bug sitting in the file the wave designated the single source of truth.** One-line fix per call site                                                                                    |
| NEW-2       | HIGH     | `connection_parser.py:342-349` — `_detect_database_type` raises on an unknown scheme and the enclosing `except Exception:` swallows it and returns `"sqlite"`, the LOOSEST budget. `postgres+asyncpg://`, `postgres+psycopg2://`, `mariadb://` (ordinary SQLAlchemy DSNs) get 128 instead of 63/64 → generated names exceed the real server limit and PostgreSQL truncates server-side at 63, aliasing two models onto one table. **Fails OPEN, silently, with only a `logger.debug`** — the exact collision #1971 exists to prevent. Also `staging_utilities.py:449` truncates with NO digest |
| S1          | HIGH     | `kaizen/llm/errors.py:68-93` — a SECOND credential scrubber guarding `ProviderError.body_snippet` (fed the FULL provider body at `client.py:888,:1432`, `http_client.py:469`) that never learned #1974. Leaks **all 8** shapes error_sanitizer redacts (slack/ghp/stripe/pg/redis/hex-upper/aws40/pplx). Its docstring claims it "mirrors" error_sanitizer — false. Zero test coverage                                                                                                                                                                                                         |
| S3          | HIGH     | `a2a.py` `run()` has **0** `try:` statements while its docstring promises "errors returned in result dictionary". `ReasoningDegradedError` now escapes `run()`, aborting the workflow instead of returning `{"success": False}` — a #1981 second-order break                                                                                                                                                                                                                                                                                                                                   |
| S4          | MED-HIGH | 8 sites `raise <sanitized> from e` — the sanitized message is clean but `__cause__` still carries the raw credential into any rendered traceback. `test_issue_1970_log_surface_parity.py` does not cover `__cause__`                                                                                                                                                                                                                                                                                                                                                                           |
| S2/S6/S7/S8 | MED      | `fallback.py:91` `to_dict()` leaks raw (5 lines from a sanitized sibling) · the #1970 sweep file autouse-skips when `DEFAULT_LLM_MODEL` is unset → **14 skipped, green, in CI** (`.env` is gitignored) · two #1981 consumers unhandled (`runtime.py:992` aborts AFTER mutating state) · nexus `register()` raises 42 lines after registry insert, leaving half-registered state that contradicts its own stated intent                                                                                                                                                                         |

**Session total: SEVEN defects surfaced after the wave declared done** (3 credential leaks, 2 ReDoS,
1 functional regression, 1 commit-blocker), plus 2 CHANGELOGs contradicting shipped code — and the
list above is what a single additional lens found on top. **Every new lens found more; no re-run of a
passed lens found anything.** That is the empirical case for the scoping recommendation: land the
verified work, then run the remainder invariant-first rather than review-first.
