# CSQ16 recovery sweep — 2026-10-02

Scope: this repository only, read-only census at `origin/dev` = `cdcaeac6baf63911d1f43ed99542002bdcd361a1`. This is an intake report, not a completion or deletion receipt. The user authorized finishing and landing all unlanded branches/worktrees into `dev`, updating the ledger and burndown, and safely reaping completed trees. Orchestrator owns mutations, ledger, and burndown; this lane owns evidence only.

## 1. Completion status

**Recovery is not complete: 0 of the four original CSQ16 worktrees are deletion-ready.** All committed tips are already ancestral to `origin/dev`, but every tree contains uncommitted differences. This snapshot establishes the starting denominator; it makes no claim about recovery work performed after capture.

| Milestone | State | Receipt / exact observation |
| --- | --- | --- |
| Original committed tips landed in dev | 4/4, ancestry only | `git merge-base --is-ancestor HEAD origin/dev` returns 0 in each; `git rev-list --left-right --count origin/dev...HEAD` prints `20 0`; original tip `4df93818243fec527590876c0022f6d1f8cacb5a` |
| Dirty contents recovered and validated | 0/4 certified | Content comparison below: zero exact dirty-file matches with dev; validity/supersession requires domain review |
| Original trees safely reaped | 0/4 | Report-only forest audit: `zero_loss=0`, `tag_first=0`, `keep=8`, `applied=false` |
| Mechanical root-spec sweep | Ran, bounded green | Trestle footer `exit=0 command wall=207.7s`; 85 specs / 160 extracted MUST symbols / zero reported structural findings |
| Product promotion / release | Not completed by this lane | PR #2229 old head `4df938182`, CodeQL `FAILURE`; 244 first-parent dev commits beyond main |

### Original dirty tree census

| Worktree label | Branch | Dirty entries | Differing files present in dev | Paths absent from dev | Exact dev matches |
| --- | --- | ---: | ---: | ---: | ---: |
| `csq16-promotion-verification` | `fix/d1-trust-log-hygiene` | 154 | 109 | 45 | 0 |
| `csq16-runtime-ci` | `fix/d1-runtime-ci-validation` | 86 | 66 | 20 | 0 |
| `csq16-source-integration` | `fix/d1-source-gate-closure` | 199 | 141 | 58 | 0 |
| `csq16-storage-ci` | `fix/d1-storage-ci-path` | 100 | 67 | 33 | 0 |

539 is a count of tree/path entries, not unique files or independent fixes. Multiple trees contain variants of the same path. Byte inequality demonstrates outstanding comparison work; it does not establish that the dirty version should replace dev. No dirty content was removed, restored, or overwritten by this lane.

## 2. ETA to completion

Planning estimate: **3–6 autonomous cycles**, revised after the domain audit lanes return. Basis: one parallel inventory/reconciliation cycle; one or two recovery/validation cycles across domain shards; one or two correctness/security review rounds with fixes if needed; less than one landing/reaping closure cycle. This estimates CSQ16 recovery only. It excludes owner-gated main promotion, package publication, and unrelated issue backlog. A reliable percentage of valid code recovered is unavailable until conflicting variants are adjudicated.

## 3. Prioritized immediate queue

All recovery priorities are anchored to the current user directive: “Finish and clean up the CSQ16 worktrees” and “land all unlanded branches/worktrees and reap (delete) them.”

| Finding | Category / severity | Location | Disposition and implication | Evidence |
| --- | --- | --- | --- | --- |
| R1: dirty contents are not durably landed | BUG / HIGH | Four original CSQ16 trees | FIX-NOW within recovery: preserve first, compare by domain, validate, land, then reap | `154`, `86`, `199`, `100` dirty entries; all `KEEP` |
| R2: overlapping variants need one integration owner | INVEST-NOW / HIGH | Shared Core/DataFlow/spec/test paths | FIX-NOW: owner assigns disjoint file sets and reconciles variants before combining | `src/kailash/nodes/data/async_sql.py`, `packages/kailash-dataflow/src/dataflow/core/nodes.py`, and `specs/core-runtime.md` occur in multiple tree statuses |
| R3: held promotion is stale and red | BUG / HIGH | PR #2229 | Retain outside dev-drain until promotion is explicitly authorized and head/checks reconciled; do not merge red | Live head `4df938182`; CodeQL `FAILURE`; dev `cdcaeac6b`; 244 first-parent promotion gap |
| R4: historical notes do not describe current forest | BUG / MED | Workspace `.session-notes` | Orchestrator updates ledger/burndown against this census, then refreshes after landing | Notes claim “Primary checkout only”; census observes eight registrations, including four old dirty trees and three active audit lanes |

Suggested independent recovery shards (assignment belongs to orchestrator): runtime/lifecycle and associated Core tests; DataFlow adapter/cache/schema/Express changes; infrastructure/workflow wiring and package metadata; trust/logging/transport security changes. Shared helpers, shared specs, and dependency files need explicit single ownership. Preserve root-cause behavior and same-class fixes rather than merely removing failing assertions. Each implementation shard must stay within the project’s invariant and reasoning budgets.

Open-issue titles are reported claims, not fresh verified defects. Several have durable dev landing references and must not be blindly reimplemented merely because GitHub still says OPEN: #2220 (`0037373f7`), #2222 (`59efc6f7b`), #2225 (`a1e7b5c48`, `c8c632624`), #2226/#2227 (`1d2092e56` and later containment work), #2210 (`d4c51a41d2`), #2107 (`769d75100`, `4f7f47994`), #2230/#2231 (`613468d4d`, `81acadbee`). These are closure-review candidates, not closure declarations; inspect residuals and main promotion status before closing.

## 4. Deferred-quality backlog

The live exact-label query returned `[]` for `deferred-quality`; no items exist under `after-milestone:*` or `on-demand` in that label. No issues carry the exact `deferred` label either.

**This does not mean all deferrals are absent.** Five open issues track scanner deferrals/persistent findings (#2181, #2178, #2146, #2127, #2044); a sixth (#2173) is the unresolved scanner reachability question. The first four and #2044 bodies contain prior runtime-safety or false-positive arguments; those arguments are historical claims, not revalidated security assurances. #2173 asks whether `python_exec` output reaches an HTML sink and remains a reachability question. None is automatically approved as an INCREMENTAL deferral by an empty label query. The recovery security lane must reconcile overlapping sinks with its actual changes and retain the existing issue references.

No new deferred-quality item was created. This lane made no issue closure, label, or tracker mutations.

## 5. Decision points

1. **Recover by domain, not by copying one whole tree.** Whole-tree copying is faster to start but can overwrite distinct fixes and reintroduce older states; domain reconciliation preserves competing fixes but requires explicit ownership. Recommend domain reconciliation, already inside the user-authorized recovery scope.
2. **Keep main promotion separate from dev recovery.** Promotion would reduce production divergence but the existing PR is both stale and red. Completing dev recovery first gives one current promotion candidate but extends the production gap. Recommend finish dev recovery, then obtain the required promotion decision; no main merge was performed.
3. **Do not expand this recovery into every open issue.** The sweep found 59 open issues, including already-landed work and unrelated product/design topics. Broad redispatch would duplicate work and obscure the four-tree target; bounded recovery leaves independent backlog visible. Recommend finish actual unlanded contents and same-class gaps discovered during validation, while reporting independent backlog below.

## 6. Recommendation

Use the inventory and content manifests to preserve all four dirty trees, assign disjoint recovery shards, validate with Trestle, obtain two genuine clean correctness/security review rounds where applicable, land valid work into dev, and only then reap each original tree with an explicit no-loss disposition. Refresh the forest census and root work ledger/burndown after every landing. Do not interpret this report’s structural green as runtime or security convergence.

## Sweep execution receipts and bounds

| Sweep | Ran signal / findings | Bound |
| --- | --- | --- |
| 1 — active todos | Enumerated `workspaces/*/todos/active/*.md`, excluding milestone trackers: 0 | Applies to this snapshot’s tracked workspace layout; no stale active item to classify |
| 2 — pending journal | Enumerated `workspaces/*/journal/.pending/*.md`: 0 | No entries promoted or discarded |
| 3 — GitHub issues | Current-repo `gh issue list --state open --limit 500`: exit 0, 59 rows including bodies/comments | Reported claims; no mass assertion of defects or closure |
| 4 — refs and PRs | Unfiltered `git for-each-ref refs/heads refs/remotes/origin`; one open PR (#2229) | Existing local remote-tracking refs, no fetch mutation; dev SHA matched primary checkout |
| 5 — specs | `trestle run -- python3 tools/sweep-redteam.py --json specs`: command exit 0 | Explicit root specs; AST symbol checks and lexical integration import evidence only, not semantic/runtime conformance |
| 6 — forest/ledger | `worktree-reap.mjs --json`: exit 0, scope all, report-only; aggregate validator exit 0 | No reaping; active new audit trees are intentionally KEEP |
| 7 — process | Primary checkout clean at capture; audit branch `origin/main...HEAD` = `0 396`; production marker scan run | Lexical markers are triage, not proof of stubs; see note below |
| 8 — release | Latest stable plain tag mechanically selected = `v2.65.0`, commit `4a98750d8`; 124 shippable-history commits and 123 changed source paths to audit HEAD | Core-tag baseline; package-specific publishing/release state not inferred |
| 9 — ecosystem | Resolver-module-absent sentinel; `.claude/VERSION` type `coc-build` | Structurally N/A in this BUILD repo; no cross-repo reads |
| 10 — deferred quality | Exact-label query exit 0, `[]` | Does not cover unlabeled scanner-deferral trackers |

Root-spec tool receipt:

<!-- sweep-redteam:v1:REPO-LEVEL specs_root=specs -->
<!-- sweep-redteam:v1:OK specs=85 symbols=160 orphans=0 coverage_gaps=0 stubs=0 -->

The tool’s existing `WorkflowBuilder` control returned no orphan; absent `CSQ16KnownAbsentControl` returned `orphan` with evidence `ast.walk found no ClassDef/FunctionDef/Assign named 'CSQ16KnownAbsentControl' in 3 candidate file(s)`. This proves discrimination for symbol presence here. It does not prove semantic drift detection (explicitly excluded by tool v1), runtime integration coverage, or arbitrary prose contracts. Full behavioral conformance remains with the domain recovery/review lanes.

Ancestry controls: `HEAD` ancestor of itself returned 0; `origin/dev` ancestor of `origin/main` returned 1. Thus the original-branch ancestry measurement can distinguish unlanded committed history. It cannot inspect uncommitted files, which are independently compared in the content manifest.

Trestle preflight enumerated 30 tracked-but-ignored paths (locks, pyright config, test-env manager, and archived artifacts). The engine emitted the same 30-path warning. No `.env` filename was among that list. The arbiter selected the host; this lane did not pin a host or use direct SSH. The cold-mirror run reported `exit=0 command wall=207.7s`. No full test suite was run in this inventory lane.

Forest: **4,724,896 KiB** total, exact measured (not lower bound); free **108,782,832 KiB**; median linked tree **221,756 KiB**; estimated headroom **490 trees**. Zero unknown/partial sizes. The JSON producer does not emit a text sentinel with `--json`; the following is a transcription of its returned fields, not a claim of application:

<!-- worktree-reap:v1:scope=all total=8 zero_loss=0 tag_first=0 keep=8 applied=false size_kb=4724896 size_unknown=0 free_kb=108782832 headroom_trees=490 -->

Aggregate ledger output: `OK forest-ledger aggregation: 1 workspace ledger(s); all open IDs reflected in root (.session-notes.shared.md)`. This verifies row-ID inclusion only, not freshness of each status. Root ledger retains F1/F13/F14/FC/F23/F24 references that involve other repositories; they were read as in-repo records only and were not investigated across repo boundaries. Workspace notes last committed `51ee62662` on 2026-09-12; the fresh checkout’s file mtimes must not be confused with actual content age.

Production marker scan read actual hits. For example `events.py:210` says `TODO: Replace with BatchProcessorNode for production use` inside a deprecated compatibility class; `bulk_operations.py:269` says `TODO: Implement COPY FROM for maximum performance` before a real multi-row INSERT implementation; `deadlock_detector.py:919` says `TODO: Send alerts or take automatic resolution actions`. These do not establish an empty implementation by themselves. Historical sweep-2026-08-06 records the marker baseline as `do-not-requeue (standing)`. No new marker was introduced in this report lane, and it does not reopen those baseline topics as speculative recovery work.

Version anchors agree: root `pyproject.toml:7` and `src/kailash/__init__.py:116` both `2.65.0`. Source changes since the latest stable tag exist, so this report does not claim release readiness or no unreleased code.

<!-- sweep-ecosystem:v1:N/A reason=resolver-module-absent -->
<!-- unadjudicated-escalation:v1 threshold=3 runs=43 keys=0 escalations=0 suppressed=0 -->

The escalation tool returned exit 0 with `reports scanned: 43` and `no unadjudicated verdict rows found`. No manual-supplement exemption was needed: root specs were passed explicitly to the structural tool.

### Unfiltered branch inventory

```text
refs/heads/chore/csq16-recovery-runtime-audit cdcaeac6baf63911d1f43ed99542002bdcd361a1
refs/heads/chore/csq16-recovery-storage-audit cdcaeac6baf63911d1f43ed99542002bdcd361a1
refs/heads/chore/csq16-recovery-sweep cdcaeac6baf63911d1f43ed99542002bdcd361a1
refs/heads/dev cdcaeac6baf63911d1f43ed99542002bdcd361a1 refs/remotes/origin/dev
refs/heads/fix/d1-runtime-ci-validation 4df93818243fec527590876c0022f6d1f8cacb5a
refs/heads/fix/d1-source-gate-closure 4df93818243fec527590876c0022f6d1f8cacb5a
refs/heads/fix/d1-storage-ci-path 4df93818243fec527590876c0022f6d1f8cacb5a
refs/heads/fix/d1-trust-log-hygiene 4df93818243fec527590876c0022f6d1f8cacb5a
refs/heads/main 50f98afe403a468bb478462182b73ebc4e0287d1 refs/remotes/origin/main
refs/remotes/origin/HEAD 50f98afe403a468bb478462182b73ebc4e0287d1
refs/remotes/origin/dev cdcaeac6baf63911d1f43ed99542002bdcd361a1
refs/remotes/origin/main 50f98afe403a468bb478462182b73ebc4e0287d1
refs/remotes/origin/promote/2026-09-11-cont30 4df93818243fec527590876c0022f6d1f8cacb5a
```

### Complete open-issue intake (reported claims, not independently reproduced)

All items remain open; no stale item was auto-closed. Default disposition is closure-review when landing evidence exists, otherwise queued for scope/claim validation against the issue’s own user report. This is not authorization to start every item during four-tree recovery.

| Issue | Title | Intake disposition |
| --- | --- | --- |
| #2252 | Cross-SDK parity: monitor outcome semantics + L3 agent factory executable ownership | Queued claim validation; issue is value anchor |
| #2250 | MCP: agree an interoperable wire contract for tool refusals, tool failures and overload (JSON-RPC codes, `data.reason`, `isError`, retry/replay) | Queued claim validation; issue is value anchor |
| #2247 | Seven documented workflow.connect(..., cycle_config=...) calls raise TypeError — connect() does not accept the argument | Queued claim validation; issue is value anchor |
| #2246 | ExpressionCondition.evaluate() returns True (terminate) on evaluation failure — indistinguishable from a satisfied condition | Queued claim validation; issue is value anchor |
| #2245 | CycleConfig.iteration_safety_factor reaches no runtime path — the advertised multiplier never applies | Queued claim validation; issue is value anchor |
| #2244 | Nexus binds 0.0.0.0 unconditionally; no bind-host option (loopback-only deployments are network-exposed) | Queued claim validation; issue is value anchor |
| #2243 | kaizen.llm: SafeDnsResolver refuses loopback, so ollama_preset (localhost:11434) is unusable (2.45.0, 2.46.1) | Queued claim validation; issue is value anchor |
| #2242 | DataFlow: Express string `order_by` silently discarded (2.20.1 and 2.12.0), and the #1051 teardown fix reached only one of two identical cursor shims | Queued claim validation; issue is value anchor |
| #2237 | _ProtectedInnerProxy allowlists 'config', handing a live mutable raw-agent object across the containment boundary | Queued claim validation; issue is value anchor |
| #2236 | Delegate: the documented entry point Delegate.run never consults the ConstraintEnvelope, and Delegate.loop reaches LLM egress | Queued claim validation; issue is value anchor |
| #2235 | ParallelBatchStrategy is a stub: execute/execute_batch ignore the agent and return fabricated text | Queued claim validation; issue is value anchor |
| #2234 | worktree-reap.mjs times out on its default path — the forest-safety guard has been failing silently | Queued claim validation; issue is value anchor |
| #2233 | kaizen.agent.Agent silently swallows audit_log_path into **kwargs — user gets a different audit file than they asked for | Queued claim validation; issue is value anchor |
| #2232 | REST pagination guard: two residuals the adversarial review left open (DNS rebinding, parser differential) | Queued claim validation; issue is value anchor |
| #2231 | MED: sync REST pagination residuals — auth_* dropped on follow-up pages, single-slot cursor dedup, unmasked exception sink | Closure-review: dev landing exists; validate residuals/promotion |
| #2230 | HIGH: RESTClientNode.async_run returns data=None on every call; AsyncRESTClientNode cannot be constructed at all | Closure-review: dev landing exists; validate residuals/promotion |
| #2227 | Two public routes reach the raw agent/engine without touching any governance proxy (L3GovernedAgent.innermost, PactEngine.governance_callback) | Closure-review: dev landing exists; validate residuals/promotion |
| #2226 | GovernanceEngine hands out LIVE mutable internals: a read-only caller can escalate its own envelope permanently | Closure-review: dev landing exists; validate residuals/promotion |
| #2225 | DelegationRecord.capabilities_delegated advertises capabilities every enforcement surface denies (raw allowlist, un-intersected, blocked-unsubtracted) | Closure-review: dev landing exists; validate residuals/promotion |
| #2222 | MiddlewareAccessControlManager: all three access-check methods pass kwargs AccessDecision rejects — TypeError on every call (distinct from #2166) | Closure-review: dev landing exists; validate residuals/promotion |
| #2220 | kaizen: #2069's fix covers only the keyless path — an unknown model still routes silently to OpenAI when a key is set (live in published 2.46.0) | Closure-review: dev landing exists; validate residuals/promotion |
| #2212 | AsyncSingleShotStrategy calls its own @deprecated pre_execute/post_execute on every run, with no supported opt-out | Queued claim validation; issue is value anchor |
| #2211 | _get_or_create_async_sql_node evicts the cached AsyncSQLDatabaseNode on event-loop change without closing it | Closure-review: dev landing exists; validate residuals/promotion |
| #2210 | db.express.bulk_upsert fails at exactly 1000 rows on SQLite (undocumented limit, no auto-chunking) | Closure-review: dev landing exists; validate residuals/promotion |
| #2206 | fix(dataflow): #1548 async lazy-DDL durability fix has a residual window — uncommitted table still invisible to a second connection | Queued claim validation; issue is value anchor |
| #2203 | MCP and A2A: both protocol surfaces are pinned to superseded spec revisions; official conformance suites now exist | Queued claim validation; issue is value anchor |
| #2199 | loom Gate-2 delivers the CLI emitter's STAGING layout verbatim: codex/ + gemini/ land at repo root instead of .codex/ + .gemini/ | Queued claim validation; issue is value anchor |
| #2194 | Governance API actor fields are caller-asserted: granted_by / created_by come from the request body, and there is no per-principal identity to derive them from | Queued claim validation; issue is value anchor |
| #2189 | Defect class worth sweeping for: an absence rendered as a success | Queued claim validation; issue is value anchor |
| #2181 | codeql: defer 11474 / 11484 / 11485 — three FALSE POSITIVES from the open-HIGH triage (url_credentials, gateway/security) | Scanner disposition revalidation; no new defer approved |
| #2180 | CI: kailash-kaizen tests/integration/ (131 files) is invoked by no workflow — the #2074 bug class, third instance | Queued claim validation; issue is value anchor |
| #2178 | codeql: defer py/clear-text-logging-sensitive-data — http.py masked-log sites (PR #2176) | Scanner disposition revalidation; no new defer approved |
| #2173 | security.py sanitize_input: does context="python_exec" output reach an HTML sink? (CodeQL 131-134 bad-tag-filter) | Queued claim validation; issue is value anchor |
| #2172 | trust/constraints/commerce.py:150 interpolates a caller-supplied beneficiary id into a log line unsanitized | Queued claim validation; issue is value anchor |
| #2171 | Nexus rate-limit middleware fingerprints a client IP with an unkeyed hash — the privacy it claims does not hold | Queued claim validation; issue is value anchor |
| #2170 | kaizen/llm/url_safety.py documents its URL tag as "non-reversible" when it is not (Rule 3e) | Queued claim validation; issue is value anchor |
| #2168 | Design: check_url performs a live DNS lookup during Endpoint construction | Queued claim validation; issue is value anchor |
| #2166 | MiddlewareAccessControlManager.check_session_access can never succeed — PermissionCheckNode declares none of the kwargs it passes | Queued claim validation; issue is value anchor |
| #2158 | A bare `git stash -u` / `git stash pop` pair can pop ANOTHER session's stash when the tree is clean | Queued claim validation; issue is value anchor |
| #2153 | kaizen SSRF guard permits CGNAT (100.64.0.0/10) while nexus blocks it — decide the posture | Queued claim validation; issue is value anchor |
| #2146 | codeql: defer py/weak-sensitive-data-hashing — SHA-256 over CSPRNG-generated API keys in api_keys.py | Scanner disposition revalidation; no new defer approved |
| #2142 | kailash-kaizen: two un-gated HTTP surfaces (MetricsEndpoint binds 0.0.0.0; monitoring dashboard app + websocket serve anonymously) | Queued claim validation; issue is value anchor |
| #2141 | kailash-ml: dashboard serves an unauthenticated DELETE /api/runs/{run_id}, and --auth unlocks a 0.0.0.0 bind while installing nothing | Queued claim validation; issue is value anchor |
| #2138 | RotatingCredentialNode drives CredentialManagerNode through four operations that do not exist — rotation never fires | Queued claim validation; issue is value anchor |
| #2135 | kailash-align has no GPU-hardware test coverage — test-gpu job removed in #2076 until real tests exist | Queued claim validation; issue is value anchor |
| #2127 | codeql: defer py/clear-text-logging-sensitive-data — mfa_config name heuristic reaches the MFA opt-out WARN through a **kwargs splat | Scanner disposition revalidation; no new defer approved |
| #2117 | CheckpointEncryptor.hash_key_for_verification is an unsalted SHA-256 over a fixed-salt KDF output | Queued claim validation; issue is value anchor |
| #2116 | PR #2098 follow-ups: assertion precision, type-confusion branch, and two silently-ignored inputs | Queued claim validation; issue is value anchor |
| #2110 | MEDIUM: the audit trail is unbounded, unrotated, and lands relative to CWD (from #2084) | Queued claim validation; issue is value anchor |
| #2109 | MEDIUM: the audit trail drops records under load and corrupts under concurrency (durability, from #2084) | Queued claim validation; issue is value anchor |
| #2107 | kailash: ten __del__ finalizers call close() inside try/except Exception: pass (logging-lock deadlock class) | Closure-review: dev landing exists; validate residuals/promotion |
| #2086 | MCPMixin.expose_as_mcp_server cannot register any auto-generated tool when standalone fastmcp is importable | Queued claim validation; issue is value anchor |
| #2075 | DataFlow pool leak on auto_migrate='warn' DDL-failure path: pool_count()=9 exceeds cap of 5 | Closure-review: dev landing exists; validate residuals/promotion |
| #2056 | Nexus MCP resources fail to register when official FastMCP is importable (URI template mismatch) | Queued claim validation; issue is value anchor |
| #2052 | fix(dataflow): schema-introspected column defaults are bound as literal SQL text on CREATE | Queued claim validation; issue is value anchor |
| #2044 | codeql: py/clear-text-logging-sensitive-data persists at 3 redacted sites — the query does not model fingerprint_secret as a sanitizer | Scanner disposition revalidation; no new defer approved |
| #2039 | chore: isort mode disagreement (--files vs --all-files) — cause UNKNOWN, three hypotheses excluded; src_paths half closed by 2cf40a17b | Queued claim validation; issue is value anchor |
| #2010 | kaizen: stale E2E passes description= to BaseAgent.__init__, which does not accept it | Queued claim validation; issue is value anchor |
| #2000 | Core: PythonCodeNode first execution costs ~9-11s — security.py eagerly imports torch/sklearn, failing nexus e2e test_concurrent_requests 3/3 | Queued claim validation; issue is value anchor |

### Evidence files

- `recovery-2026-10-02-sweep-inventory.json`: original snapshots, refs, workspace census, release history.
- `recovery-2026-10-02-sweep-content.json`: 539 dirty-path entries and byte-equality results against dev.
- `recovery-2026-10-02-sweep-github.json`: current-repo issue/PR/deferred-quality outputs and command status.
- `recovery-2026-10-02-sweep-forest.json`: report-only forest/size, ledger aggregation, escalation outputs.
- `recovery-2026-10-02-sweep-controls.json`: known-present/known-absent symbol and ancestry controls.

Ran signal: all ten sweep categories executed or structurally N/A with the reason above. No implementation test or redteam convergence is claimed. The report is intentionally uncommitted pending orchestrator integration; sweep closure requires that eventual commit and a final post-recovery census.
