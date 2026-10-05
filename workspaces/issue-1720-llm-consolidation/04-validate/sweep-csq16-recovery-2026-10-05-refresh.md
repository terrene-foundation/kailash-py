# CSQ16 recovery: second independent full sweep refresh — 2026-10-05

## Completion status

**Original four-tree acceptance remains 0/4.** The frozen `02-plans/csq16-recovery-register.json` lists CSQ16-PROMOTION, CSQ16-RUNTIME, CSQ16-SOURCE and CSQ16-STORAGE as “In progress”. All original inputs remain custody evidence. Eight bounded technical landings are visible on dev according to `02-plans/csq16-recovery-ledger-2026-10-02.md`; the newest shared launcher landing is `ae4649bffff6f452b8d94c38cecc1e0f2c11a73d`. Documentation checkpoint `6835a323eff1242872ed66cf154000e1476e7d3d` adds no technical landing or original-owner signoff. This report binds that clean checkout; the historical full sweep `bde3a5284` is a baseline, not a current census.

INSERT result-description repair `41a8d94d60a5ca2a899bc3e3d8fd87783b826016` is a committed author candidate, not a dev landing or completed independent gate. This sweep read its handoff and verified all 48 listed artifact hashes against actual files. Existing final Core logs show “151 passed” on Python 3.13.13 and 3.11.15; existing DataFlow Create logs show “8 passed” on each. The ordinary opposite run on old `8443df3e1d605a6a1dcc183d040177187995211c` shows four result-contract failures, not dynamic security proof. Normal commit output records every applicable hook Passed, including Tier 1; it prints no count/minor, so none is inferred. Fresh correctness and separate STATIC review pairs remain required. Old 31-case and earlier 244+11 cohorts remain attached to their own freezes.

Each actual DataFlow log contains fourteen lifecycle diagnostic lines: seven pairs of “Owned cleanup failed: CancelledError” and “AsyncLocalRuntime cleanup failed: CancelledError”. Each also has one expected ignored-create `nodes.create_operation_failed` ERROR. The fourteen lifecycle lines remain a root OPEN obligation; passing result assertions do not certify cleanup. Parent-reported current Core observer union, pooled SQL completion, SQLB/Bulk ownership and peer acknowledgement remain open. No SDK/backend/runtime or dynamic security cases run in this sweep, and no whole-SDK convergence claim follows.

All ten sweeps ran. This checkpoint provides evidence and management guidance; promotion, publishing, issue closure and forest deletion remain outside its action scope.

## ETA to completion

Estimate **at least three autonomous execution cycles**, with no defensible upper bound while cross-shard completion and original-content reconciliation remain open. One cycle covers current bounded Core/INSERT fixes and fresh independent correctness plus STATIC gates; at least one parallel cycle covers peer SQL/storage/consumer obligations and fourteen cleanup diagnostics; at least one cycle reconciles original paths, obtains owner acceptance and verifies the union against original success criteria. Further cycles depend on actual findings, not issue-census size. Existing isolated owners can proceed concurrently. Promotion/release remains a separate gate.

## Prioritized immediate queue

| Priority | Category / severity | Value anchor and evidence | Disposition |
| --- | --- | --- | --- |
| 1 | BUG / HIGH | Original recovery success criteria remain unmet: register rows “In progress”, 0/4 signed off. | Continue existing owners; reconcile all original paths and custody before completion. |
| 1, parallel | BUG / HIGH | Current Core/pool shared completion custody remains open. Canonical ledger says “three remaining public pool completion sites under the new shared-observer union scope”; old-context review pairs do not cover that union. | Preserve Core/peer ownership, receive substantive updated deliveries and fresh union reviews. |
| 1, parallel | BUG / HIGH | Old INSERT source review found `"RETURNING" not in query.upper()` and `if query_type == "INSERT" and not result:`. New cursor-description candidate has 151 Core + 8 Create passes per minor, independent gates pending. | Review exact `41a8d94d` before integration; retain old `8443` OPEN findings without clean-round credit. |
| 1, parallel | BUG / HIGH | Current DataFlow logs say “Owned cleanup failed: CancelledError” and “AsyncLocalRuntime cleanup failed: CancelledError”, fourteen lifecycle lines per minor. | Root owns lifecycle closure; assertion passes do not grant lifecycle acceptance. |
| 2 | BUG / HIGH | #2229 live `CodeQL: FAILURE`, `gh pr checks` exit 1; pinned head unchanged at `4df93818243fec527590876c0022f6d1f8cacb5a`. | Promotion remains blocked and untouched; refresh evidence separately after dev recovery. |
| 2 | INVEST-NOW / MED | Five TAG-FIRST classifier rows have containing local refs. Producer uses `--not --remotes`, while reason says “unreachable from any ref”. Occupancy unknown/in-flight. | Root alone owns later cleanup; KEEP all five and ignored/evidence contents. Use producer's remote-only meaning. |
| 2 | INVEST-NOW / MED | Historical recovery-prefixed reports fall outside auditor discovery. Official opposite controls fire exit 1 vs 0. | New report filename repaired in this ownership; preserve and manually adjudicate originals below. |
| Visibility | INVEST-NOW / HIGH | `packages/kailash-kaizen/src/kaizen/governance/approval_manager.py:579-606` builds notification metadata and logs “Would send notification”; line 602 says “TODO: Implement webhook/email notification”. | Source delivery gap requires scope/claim validation. No executed failure or authorized expansion of recovery implementation is claimed. |

Applicable issue bodies read include #2107 finalizer parity, #2211 async SQL cache replacement custody and #2075 warn-mode DDL pool cap. Their open state/title alone does not establish an unrepaired current defect. #2242 ordering/migration shim, #2234 forest timeout and #2039 isort-mode reports remain reported claims without fresh source/behavior closure here. This completed size-bearing forest invocation does not satisfy #2234's unattended-hook criteria. Other issue intake remains visible in complete body/label capture. No closure or age-based dismissal occurs.

## Deferred-quality backlog

The exact current-repo `deferred-quality` query returned `[]` at exit 0. No matching after-milestone or on-demand item exists in this capture; no aged-label revisit applies and no new deferral is created. This does not erase CodeQL tracking #2181, #2178, #2146, #2127, #2044 or reachability question #2173. Their recorded safety/false-positive arguments are historical issue-body claims, not fresh security assurance. Four-condition validity and release-specialist signoff are not re-certified here.

No BUG is recategorized INCREMENTAL. Any future incremental defer requires blocking-safety note, user value anchor, full-fix criteria and `after-milestone:<name>` or `on-demand` trigger; closure/renewal requires its user gate.

## Decision points

1. **Finish current recovery before promotion.** Reviewed bounded integration advances authorized recovery but requires shared-custody validation across owners. Retaining the PR avoids red/stale evidence but leaves dev/main divergence. Recommendation: parallel in-envelope repairs and exact-candidate gates, then original-content acceptance and fresh promotion checks. No release/scope expansion is inferred.
2. **Preserve forest candidates until occupancy resolves.** Reaping could recover measured space but risks active/ignored evidence. KEEP preserves custody but retains disk use. Recommendation: KEEP all five plus every active original/author/peer/review/observer/sweep tree. Root reassesses only after archives, occupancy confirmation and preservation proof.
3. **Restore fresh-report discovery without rewriting history.** Canonical `sweep-*` prefix restores new-report reachability; changing shared discovery source would exceed this owner. Preserving originals retains evidence but needs manual review. Recommendation implemented here: canonical new filename, originals unchanged, actual historical keys adjudicated below. Root owns any future tool proposal.
4. **Keep unrelated source gaps visible.** Approval notification investigation may reveal a public-contract gap; executing/fixing it expands this bounded shard. Source-only visibility preserves ownership but leaves semantic claims unresolved. Recommendation: INVEST-NOW for co-owner direction, without harmless-quality recategorization or unauthorized implementation.

## Recommendation

Continue existing autonomous recovery with independent correctness and adversarial STATIC evidence on exact candidates. Preserve original/active trees, obtain actual peer acknowledgements, resolve lifecycle diagnostics/shared custody, then reconcile original criteria. Archive this report, raw captures and receipt before root-led deletion. Keep main, #2229 and publishing untouched.

New portable long source analyses use `trestle run --os linux -- <command>`: an OS filter retaining automatic host/slot arbitration. Earlier admitted sweep captures actually ran on esperie-ai without the filter and remain valid for their recorded runs. Unfiltered automatic arbitration can select Mac under CPU pressure and is not a Linux guarantee. Parent corrected shared rg 14.1 installation receipt: installation used a host pin, so installation credit is valid but automatic-placement credit is not. This sweep installed nothing and pinned no host. Actual-local refs, configured GH auth, forest and ledger operations used canonical `--local --repo` execution.

### Actual ten-sweep outputs

Captures on 2026-10-05 bind checkout HEAD `6835a323eff1242872ed66cf154000e1476e7d3d`. All complete argv/stdout/stderr/exit artifacts accompany the machine receipt; totals below are fresh captures, not remembered values.

| Sweep | Actual output | Scope and open limits |
| --- | --- | --- |
| 1: active todos | Recursive active Markdown inventory: no matches after milestone-tracker exclusion. | No matching frontmatter/body to read; ledger/register still carry open recovery. |
| 2: pending journals | Pending Markdown inventory: no matches. | No matching body to promote/discard; not recovery-completion evidence. |
| 3: issues | 59 open issues with complete bodies/comments/labels, all titles/labels read; applicable scope bodies inspected. Limit 1000. | Current repo only; no title-only closure, stale dismissal or broad new authorization. |
| 4: PRs/refs | One non-draft PR #2229, head pinned twice unchanged; CodeQL FAILURE, checks exit 1. Unfiltered 112 refs: 108 local heads + four remote-tracking refs. | All ref rows read; no-merged is ranker only. Forest disposition belongs to Sweep 6. |
| 5: specs/source | Workspace spec dirs absent; root specs 85; existing tool present. Actual `specs --json`: 160 symbols, 0 orphans/coverage gaps/stubs. | Repo-level citation/AST/import-shaped checks only. Free-prose semantics/backend/cancellation/shared ownership remain outside v1. |
| 6: forest/ledgers | All 131 registrations: ZERO-LOSS 0, TAG-FIRST 5, KEEP 126, scope all, applied false. Size 31,426,012 KiB; unknown/partial 0; free 136,294,440 KiB; median 194,806 KiB; derived headroom 699. Aggregate reports all open workspace IDs reflected at root. | Management KEEP all five unknown/in-flight candidates. Both actual local ledger bodies/IDs read, not mtime only. Checkout mtimes do not prove content freshness. |
| 7: hygiene | Initial clean checkout; `origin/main...HEAD` = `0 460`, `origin/dev...HEAD` = `0 0`. First-parent count 292. Production lexical scan 212 matching lines. | Distinct counters answer distinct questions. Full marker hits + representative source read, not whole-tree stub-free verdict. Report is sole owned new change. |
| 8: release | Mechanically selected latest plain stable root tag `v2.65.0`; shippable history 146 commits, current diff 136 paths. | Root/package src/manifests/locks only, docs excluded. Nonempty shippable diff establishes unreleased work, not readiness/version parity. Older broader count incomparable. |
| 9: ecosystem | Declared `coc-build`, resolver absent; actual structural sentinel exit 0. | BUILD clone structural N/A; no other repo reads or guessed targets. |
| 10: quality/closure | Exact label empty; auditor exit 0: 43 reports, zero keys/escalations/suppressions. Actual repeated-verdict and filename controls fired. | Old recovery names excluded; manual historical review below. Green only covers discovered lexical vocabulary, not all history/obligations. |

<!-- sweep-redteam:v1:REPO-LEVEL specs_root=specs -->
<!-- sweep-redteam:v1:OK specs=85 symbols=160 orphans=0 coverage_gaps=0 stubs=0 -->
<!-- worktree-reap:v1:scope=all total=131 zero_loss=0 tag_first=5 keep=126 applied=false size_kb=31426012 size_unknown=0 free_kb=136294440 headroom_trees=699 -->
<!-- sweep-ecosystem:v1:N/A reason=resolver-module-absent -->
<!-- unadjudicated-escalation:v1 threshold=3 runs=43 keys=0 escalations=0 suppressed=0 -->

Forest comment is rendered from official JSON producer fields; JSON mode itself emits no comment. It records report-only classification, not removal. Repo-level marker records inspected precondition; OK spec sentinel is actual stdout.

### Reached opposite controls and source limits

Spec falsifier was a missing citation/symbol, coverage or stub finding. Actual present `kailash.nodes.data.async_sql.SQLiteAdapter`: one symbol, zero orphans, exit 0. Actual missing `kailash.nodes.data.async_sql.CSQ16SweepMissingSymbol`: one orphan, exit 1, “ast.walk found no ClassDef/FunctionDef/Assign named 'CSQ16SweepMissingSymbol' in 4 candidate file(s)”. All 85 spec hashes unchanged before/after. Implementation and CLI inspected before invocation. Module/file citations can establish presence only; import-shaped Tier 2 coverage is not executed wiring; semantic drift is outside v1.

Marker falsifier for no lexical hits is a matching line; 212 occurred. Positive stdin returned `1:TODO known positive control`, exit 0; clean stdin returned expected no-match rg exit 1. Source examples distinguish abstract MCP formatter `utils/formatters.py:13-21`, callback-only transport `transports.py:1397-1403`, unsupported request/response receive `channels/mcp/http.py:138-144` and read-only override `source_adapter.py:306-321` from notification body above. Token counts do not decide semantic completeness; literal XXX hits are retained.

Stable selector accepted `v2.65.0` and rejected `v2.66.0-rc1`, `kailash-v2.66.0`, `v2.66.0extra`. It proves anchored selection, not package readiness.

Ledger falsifier was a stranded workspace ID. Official Node temporary fixture returned exit 1: “open workspace-ledger ID \"CSQ16-MISSING\" … absent from root ledger — workspace→root no-vanish (issue #669)”; matching IDs returned exit 0, strandedCount 0. Actual root F1/F13/F14/FC/F23/F24 stay visible as local records. Cross-repo/blocked entries confer no authority outside this clone. Workspace notes include older open records; fresh checkout mtime is not content age.

Official escalation repeated-verdict fixture returned exit 1, runs 3, keys 1, escalation 1. Identical content with recovery-prefixed filenames returned exit 0, runs 0. Actual sentinels:

```text
<!-- unadjudicated-escalation:v1 threshold=3 runs=3 keys=1 escalations=1 suppressed=0 -->
<!-- unadjudicated-escalation:v1 threshold=3 runs=0 keys=0 escalations=0 suppressed=0 -->
```

These official Node auditor fixtures execute no SDK/security scenarios. Discovery at `.claude/bin/unadjudicated-escalation.mjs:345-358` uses workspace `/^sweep.*\.md$/i` and root `/^SWEEP.*\.md$/`. Fresh report follows it; originals remain unchanged.

### TAG-FIRST candidate custody proof

| Tree | Captured/current unchanged HEAD | KiB | Cherry absent/equivalent | Containing local ref | Disposition |
| --- | --- | ---: | --- | --- | --- |
| csq16-async-python-controls | `31e913046bfde493da2f8bc1514ac4de4818a759` | 448876 | 72 + / 0 - | fix/csq16-wrapper-handler-followup | KEEP: unknown/in-flight occupancy; 8,886 ignored status entries including venv/caches. |
| csq16-cache-parser-correctness | `523c0c2a19b44bb673697023869f5786978e0685` | 192460 | 24 + / 2 - | fix/csq16-cache-memory-parser | KEEP: reviewer occupancy unconfirmed. |
| csq16-cache-parser-security | `523c0c2a19b44bb673697023869f5786978e0685` | 192460 | 24 + / 2 - | fix/csq16-cache-memory-parser | KEEP: reviewer occupancy unconfirmed. |
| csq16-storage-durability-correctness | `5a4896cd37516ce196fe8b5915329d3a0c5659ad` | 194048 | 98 + / 3 - | fix/csq16-tracking-storage-durability | KEEP: reviewer occupancy unconfirmed. |
| csq16-storage-durability-static-security | `5a4896cd37516ce196fe8b5915329d3a0c5659ad` | 194048 | 98 + / 3 - | fix/csq16-tracking-storage-durability | KEEP: reviewer occupancy unconfirmed. |

All heads read before/after matched captured SHAs. Actual `git merge-base --is-ancestor <HEAD> origin/dev` exit 1 for each proves non-ancestry, not failed execution. Actual `git cherry origin/dev <HEAD>` hits include absent and equivalent non-merge patches and were read; merges are excluded by that producer. Neither ancestry nor patch equivalence proves occupancy or ignored-content preservation.

Classifier reason says “clean but DETACHED and unreachable from any ref — tag before removing”; source `.claude/bin/worktree-reap.mjs:403-417` computes unpushed with `rev-list HEAD --not --remotes`. Containing refs above refute the all-ref interpretation. Preserve its remote-only producer meaning. No ZERO-LOSS row exists. All original d1 trees, authors/peer lanes, current Core observer, INSERT/result-description/review trees and sweep sibling remain KEEP under active recovery regardless of classifier/ancestry. No tag/archive/delete action is performed by this sweep.

### Historical manual adjudication

Five original recovery-prefixed reports were read using official exported lexical extractor plus relevant context lines. Each had zero recognized verdict hits, zero fenced skipped hits, and no live/malformed disposition. This answers recognized keys in these five actual contents only. Their root-spec checks have actual OK sentinels, so filename exclusion does not imply a missing mechanical supplement. Semantic open recovery obligations remain in immediate queue.

- `recovery-2026-10-02-sweep.md` — SHA256 `79ffd8f32b5445166b218b21a9c4028e760c10c56d95df15ce365d0c1ef331ee`; recognized hits 0; original unchanged.
- `recovery-2026-10-03-sweep.md` — SHA256 `a8df615b4fcb68247626408b228488143867d40294e5375f2418b7c99f232c95`; recognized hits 0; original unchanged.
- `recovery-2026-10-04-sweep.md` — SHA256 `592825bc791b5e8e2b0caacb824b901f5f566005dc1449bf0d3d4b47ec3ce496`; recognized hits 0; original unchanged.
- `recovery-2026-10-05-sweep-refresh.md` — SHA256 `b86609b9e324e309c4a0443d10bae5483b5654267b63339b619da8919cc14579`; recognized hits 0; original unchanged.
- `recovery-2026-10-05-sweep.md` — SHA256 `000fe9fee993bee41b47e81b1a1d018e3644a880e2fc1359848d63176b81e270`; recognized hits 0; original unchanged.

October 2 records “0/4 certified”; October 3 retains “CodeQL FAILURE”; October 4 says recovery “remains open”; October 5 retains native/runtime custody; earlier October 5 refresh leaves descriptor exhaustion and SQL/peer obligations open. These are actual historical dispositions, not rerun backend findings. Old totals are not current counts.

### Complete issue intake and evidence bank

All 59 title/label rows below are visibility. Detailed bodies/comments remain in complete capture. Outside discussed scope, current correctness/closure/new implementation is not adjudicated.

| Issue | Title | Labels |
| --- | --- | --- |
| #2000 | Core: PythonCodeNode first execution costs ~9-11s — security.py eagerly imports torch/sklearn, failing nexus e2e test_concurrent_requests 3/3 | (none) |
| #2010 | kaizen: stale E2E passes description= to BaseAgent.__init__, which does not accept it | (none) |
| #2039 | chore: isort mode disagreement (--files vs --all-files) — cause UNKNOWN, three hypotheses excluded; src_paths half closed by 2cf40a17b | (none) |
| #2044 | codeql: py/clear-text-logging-sensitive-data persists at 3 redacted sites — the query does not model fingerprint_secret as a sanitizer | (none) |
| #2052 | fix(dataflow): schema-introspected column defaults are bound as literal SQL text on CREATE | (none) |
| #2056 | Nexus MCP resources fail to register when official FastMCP is importable (URI template mismatch) | (none) |
| #2075 | DataFlow pool leak on auto_migrate='warn' DDL-failure path: pool_count()=9 exceeds cap of 5 | bug |
| #2086 | MCPMixin.expose_as_mcp_server cannot register any auto-generated tool when standalone fastmcp is importable | bug |
| #2107 | kailash: ten __del__ finalizers call close() inside try/except Exception: pass (logging-lock deadlock class) | bug |
| #2109 | MEDIUM: the audit trail drops records under load and corrupts under concurrency (durability, from #2084) | (none) |
| #2110 | MEDIUM: the audit trail is unbounded, unrotated, and lands relative to CWD (from #2084) | (none) |
| #2116 | PR #2098 follow-ups: assertion precision, type-confusion branch, and two silently-ignored inputs | area/quality, type/bug |
| #2117 | CheckpointEncryptor.hash_key_for_verification is an unsalted SHA-256 over a fixed-salt KDF output | type/bug, security |
| #2127 | codeql: defer py/clear-text-logging-sensitive-data — mfa_config name heuristic reaches the MFA opt-out WARN through a **kwargs splat | security |
| #2135 | kailash-align has no GPU-hardware test coverage — test-gpu job removed in #2076 until real tests exist | bug |
| #2138 | RotatingCredentialNode drives CredentialManagerNode through four operations that do not exist — rotation never fires | (none) |
| #2141 | kailash-ml: dashboard serves an unauthenticated DELETE /api/runs/{run_id}, and --auth unlocks a 0.0.0.0 bind while installing nothing | security |
| #2142 | kailash-kaizen: two un-gated HTTP surfaces (MetricsEndpoint binds 0.0.0.0; monitoring dashboard app + websocket serve anonymously) | security |
| #2146 | codeql: defer py/weak-sensitive-data-hashing — SHA-256 over CSPRNG-generated API keys in api_keys.py | (none) |
| #2153 | kaizen SSRF guard permits CGNAT (100.64.0.0/10) while nexus blocks it — decide the posture | bug, security |
| #2158 | A bare `git stash -u` / `git stash pop` pair can pop ANOTHER session's stash when the tree is clean | bug |
| #2166 | MiddlewareAccessControlManager.check_session_access can never succeed — PermissionCheckNode declares none of the kwargs it passes | (none) |
| #2168 | Design: check_url performs a live DNS lookup during Endpoint construction | (none) |
| #2170 | kaizen/llm/url_safety.py documents its URL tag as "non-reversible" when it is not (Rule 3e) | (none) |
| #2171 | Nexus rate-limit middleware fingerprints a client IP with an unkeyed hash — the privacy it claims does not hold | (none) |
| #2172 | trust/constraints/commerce.py:150 interpolates a caller-supplied beneficiary id into a log line unsanitized | (none) |
| #2173 | security.py sanitize_input: does context="python_exec" output reach an HTML sink? (CodeQL 131-134 bad-tag-filter) | (none) |
| #2178 | codeql: defer py/clear-text-logging-sensitive-data — http.py masked-log sites (PR #2176) | (none) |
| #2180 | CI: kailash-kaizen tests/integration/ (131 files) is invoked by no workflow — the #2074 bug class, third instance | (none) |
| #2181 | codeql: defer 11474 / 11484 / 11485 — three FALSE POSITIVES from the open-HIGH triage (url_credentials, gateway/security) | (none) |
| #2189 | Defect class worth sweeping for: an absence rendered as a success | (none) |
| #2194 | Governance API actor fields are caller-asserted: granted_by / created_by come from the request body, and there is no per-principal identity to derive them from | (none) |
| #2199 | loom Gate-2 delivers the CLI emitter's STAGING layout verbatim: codex/ + gemini/ land at repo root instead of .codex/ + .gemini/ | (none) |
| #2203 | MCP and A2A: both protocol surfaces are pinned to superseded spec revisions; official conformance suites now exist | (none) |
| #2206 | fix(dataflow): #1548 async lazy-DDL durability fix has a residual window — uncommitted table still invisible to a second connection | (none) |
| #2210 | db.express.bulk_upsert fails at exactly 1000 rows on SQLite (undocumented limit, no auto-chunking) | (none) |
| #2211 | _get_or_create_async_sql_node evicts the cached AsyncSQLDatabaseNode on event-loop change without closing it | (none) |
| #2212 | AsyncSingleShotStrategy calls its own @deprecated pre_execute/post_execute on every run, with no supported opt-out | (none) |
| #2220 | kaizen: #2069's fix covers only the keyless path — an unknown model still routes silently to OpenAI when a key is set (live in published 2.46.0) | security |
| #2222 | MiddlewareAccessControlManager: all three access-check methods pass kwargs AccessDecision rejects — TypeError on every call (distinct from #2166) | bug, security |
| #2225 | DelegationRecord.capabilities_delegated advertises capabilities every enforcement surface denies (raw allowlist, un-intersected, blocked-unsubtracted) | security |
| #2226 | GovernanceEngine hands out LIVE mutable internals: a read-only caller can escalate its own envelope permanently | (none) |
| #2227 | Two public routes reach the raw agent/engine without touching any governance proxy (L3GovernedAgent.innermost, PactEngine.governance_callback) | (none) |
| #2230 | HIGH: RESTClientNode.async_run returns data=None on every call; AsyncRESTClientNode cannot be constructed at all | bug |
| #2231 | MED: sync REST pagination residuals — auth_* dropped on follow-up pages, single-slot cursor dedup, unmasked exception sink | bug |
| #2232 | REST pagination guard: two residuals the adversarial review left open (DNS rebinding, parser differential) | bug |
| #2233 | kaizen.agent.Agent silently swallows audit_log_path into **kwargs — user gets a different audit file than they asked for | (none) |
| #2234 | worktree-reap.mjs times out on its default path — the forest-safety guard has been failing silently | (none) |
| #2235 | ParallelBatchStrategy is a stub: execute/execute_batch ignore the agent and return fabricated text | (none) |
| #2236 | Delegate: the documented entry point Delegate.run never consults the ConstraintEnvelope, and Delegate.loop reaches LLM egress | (none) |
| #2237 | _ProtectedInnerProxy allowlists 'config', handing a live mutable raw-agent object across the containment boundary | (none) |
| #2242 | DataFlow: Express string `order_by` silently discarded (2.20.1 and 2.12.0), and the #1051 teardown fix reached only one of two identical cursor shims | (none) |
| #2243 | kaizen.llm: SafeDnsResolver refuses loopback, so ollama_preset (localhost:11434) is unusable (2.45.0, 2.46.1) | (none) |
| #2244 | Nexus binds 0.0.0.0 unconditionally; no bind-host option (loopback-only deployments are network-exposed) | (none) |
| #2245 | CycleConfig.iteration_safety_factor reaches no runtime path — the advertised multiplier never applies | (none) |
| #2246 | ExpressionCondition.evaluate() returns True (terminate) on evaluation failure — indistinguishable from a satisfied condition | (none) |
| #2247 | Seven documented workflow.connect(..., cycle_config=...) calls raise TypeError — connect() does not accept the argument | (none) |
| #2250 | MCP: agree an interoperable wire contract for tool refusals, tool failures and overload (JSON-RPC codes, `data.reason`, `isError`, retry/replay) | (none) |
| #2252 | Cross-SDK parity: monitor outcome semantics + L3 agent factory executable ownership | (none) |

Receipt includes complete outer/nested actual command argv, exit, stdout/stderr and immutable hashes. Artifact stdout hashes:

| Capture | Exit | Complete stdout SHA256 |
| --- | ---: | --- |
| inventory | 0 | `73c4b44b7b8d627bb3f8b981ec06dca24ff42e64b7ae8e235b3497f7d746d857` |
| github-refs | 0 | `02b9a6c83e3df5e088c6994fdd852d4cad40ec221a44d8d8f067edb1429a254b` |
| forest | 0 | `2d36f1dec147dde6f6d300fb79690b4f6c227242fe570bc30c58f7b39a0eadee` |
| source | 0 | `50c273b621a648bc6703bc3613f8f2a6ad3bee032bc82550dd9a5b753917c064` |
| ledgers-escalation | 0 | `16028e760339769597c997526c05145f3f7c656a0d3048e86ee71094c8feee97` |
| forest-proof | 0 | `889c3ecb3c18f3424d72f75aaf2504e94dddb8d92cf770a3e35b69e938942765` |
| escalation-controls | 0 | `81fd210f7ce76f225b27df9d930c853496fa1f07203e808c47ca9e4e7d61f630` |
| historical-adjudication | 0 | `462d8da0372b2f5612f4c0ae4146956b124eb7dcb7a39bcc0bdcc1a2cf69a9ee` |


One attempted local precommit-routing source read returned no source: PreToolUse reported “hook child timed out after 4000ms”. It earns zero evidence, was not retried, and no hook/policy was bypassed. Report is delivered for root's normal commit/land; no report commit/push, source repair, ledger change, tag/reap, issue closure or install is claimed. All sweep jobs drained. Raw evidence/report copy remain outside this worktree before any future root-led deletion.

Final reachability capture after writing this report: official discovery returned new_report_discovered: true, no emitted verdict hits, exit 0. The actual full auditor then included this report and returned exit 0 with:

<!-- unadjudicated-escalation:v1 threshold=3 runs=44 keys=0 escalations=0 suppressed=0 -->

This 44-report output includes the fresh working-tree report; the earlier 43-report output above is the immutable pre-write capture. Historical recovery-prefixed originals remain outside discovery and manually reviewed above. No all-history guarantee follows.
