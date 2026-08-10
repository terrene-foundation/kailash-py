# Launch Ledger — session M (2026-08-10)

Durable orchestration record per `rules/orchestration-launch-ledger.md` MUST-1.
Consult BEFORE every spawn (MUST-2); match every completion against it (MUST-3).

Branch: `fix/issue-1720-forest-drain` · PR **#2016 OPEN** · base `main`.

## Wave 1 — CI red-to-green (3 independent shards, disjoint file scopes)

Entry state: CI **33 pass / 3 fail** on head `fix/issue-1720-forest-drain`.
All three agents run in the MAIN checkout (NOT worktrees) — deliberate, see § Isolation note.

| track       | agent | scope (disjoint)                                | branch                      | status    |
| ----------- | ----- | ----------------------------------------------- | --------------------------- | --------- |
| W1-dataflow | W1-df | `packages/kailash-dataflow/**` (adapters+tests) | fix/issue-1720-forest-drain | in-flight |
| W1-ml       | W1-ml | `packages/kailash-ml/**`                        | fix/issue-1720-forest-drain | in-flight |
| W1-codeql   | W1-cq | read-only diagnosis, `.github/workflows/**`     | fix/issue-1720-forest-drain | in-flight |

### Failure inventory (measured, not inferred)

**A — `Test DataFlow Unit Suite (Tier 1)`** run 31323588202, step "DataFlow infra-free regression
gates": `4 failed, 678 passed, 6 skipped, 176 deselected in 47.42s`. All four in
`tests/regression/test_issue_1502_sqlite_memory_shared_cache.py`:

- `test_memory_shared_cache_ddl_and_crud_reach_same_db` — `AdapterError: Unsupported database
scheme: file. Supported schemes: mariadb, mongodb, mysql, pgsql, postgres, postgresql, sqlite`
- `test_two_memory_instances_are_isolated` — same
- `test_model_registry_sync_path_reaches_shared_memory_db` — `assert False is True`
- `test_close_disposes_registry_pool_no_id_reuse_aliasing` — `registry StaticPool should exist for
this instance's URI before close()`

Suspect commit `d8b29d038` (per-dialect identifier budgets, fail-closed) — it is one of only two
commits touching `packages/kailash-dataflow/src/dataflow/adapters/` on this branch, and `git log -S
"Unsupported database scheme"` names it. **Hypothesis, not established** — the agent proves it.

**B — `Base (Python 3.12)` / Coverage** run 31323588102: `18 failed, 2437 passed, 36 skipped in
507.10s`. Coverage gate itself PASSED (75.88% ≥ 60%) — the job fails on test failures, NOT coverage.
All 18 in `packages/kailash-ml/tests/integration/`:
`test_feature_materialiser_wiring.py` (9), `test_feature_store_erase_tenant_wiring.py` (7),
`test_online_store_and_reopen_wiring.py` (2). Every one:
`FeatureStoreError(reason='materialize failed: TypeError', tenant_fingerprint='sha256:...')`.
The real `TypeError` is swallowed into `reason=` — the agent must recover the underlying traceback.

**C — `CodeQL`** check-run 93271127308, `fail` in **11s**, while the actual analysis job
"Analyze Python" (run 31323588135) **passed in 7m46s**. `gh run view --log-failed` on that run
returns EMPTY ⇒ the red is NOT an Actions job failure. Session-L notes claim the open alerts are
pre-existing quality findings (`py/unused-import`, `py/cyclic-import`, `py/repeated-import`,
`py/catch-base-exception`) with no security severity — **that claim is UNVERIFIED and is exactly
what shard C establishes or refutes.**

### Isolation note (deliberate deviation from worktree default)

`worktree-isolation.md` Rule 1 prefers sibling worktrees for parallel agents. NOT used here, for two
recorded reasons: (1) session-L trap — the venv's editable installs resolve `kailash*` to the MAIN
repo, so a worktree agent's probe silently measures unmutated main code; (2) the three scopes are
genuinely disjoint packages, and agents are instructed NOT to `git commit` (orchestrator commits
centrally), which removes the index race that motivates isolation for same-tree parallel work.

## Wave 1b — `#2005` re-triage + fix (launched alongside Wave 1)

| track     | agent     | scope                                                             | status    |
| --------- | --------- | ----------------------------------------------------------------- | --------- |
| W1-tenant | W1-tenant | `packages/kailash-kaizen/src/kaizen/memory/enterprise.py` + tests | in-flight |

`#2005` re-triaged INCREMENTAL → BUG (`deferred-quality` removed, `bug`+`security` added;
rationale posted as issue comment). Grounds: (1) the issue's OWN text calls it "the same
structural shape as a defect fixed on `fix/issue-1720-forest-drain` — a falsy identity widening
scope through a truthiness `or`-chain", which fires `autonomous-execution.md` MUST-4's
fix-while-warm mandate and BLOCKS a sixth defer; (2) `product-completion-first.md` MUST-1 is
fail-closed and a tenant-isolation shape resolves ON-LIST. **Scope verified disjoint** —
`memory/enterprise.py` is NOT in this branch's diff (`git diff --name-only origin/main..HEAD`).

## Wave 2 — after CI green (planned, not launched)

1. Merge #2016 — pinned-head READ, then MERGE as a **separate command** per `git.md`
   § "CI-check and merge are SEPARATE steps".
2. `/release` in dependency order. **Deltas measured against pypi.org, not assumed:**

   | package          | local  | PyPI   | release owed           |
   | ---------------- | ------ | ------ | ---------------------- |
   | kailash          | 2.63.0 | 2.62.0 | **YES — FIRST (root)** |
   | kailash-kaizen   | 2.46.0 | 2.45.0 | YES                    |
   | kailash-nexus    | 2.16.0 | 2.15.0 | YES                    |
   | kailash-dataflow | 2.20.0 | 2.19.1 | YES                    |
   | kailash-ml       | 2.2.3  | 2.2.2  | YES                    |
   | kailash-mcp      | 0.5.1  | 0.5.1  | already published      |
   | kailash-align    | 0.7.4  | 0.7.4  | no                     |
   | kailash-pact     | 0.18.0 | 0.18.0 | no                     |

   **Corrects a stale session-L/earlier claim that "no kailash-ml release is owed"** — there IS a
   2.2.2→2.2.3 delta, and W1-ml is changing ml source this session, so re-verify at release time.
   kaizen 2.46.0 carries a `### Changed (BREAKING)` entry (`matches_requirement` async→sync).

3. Decision B: kailash-mcp 0.5.0/0.5.1 were published from an UNMERGED branch. After merge, cut
   `mcp-v0.5.1` from main so the tag matches the published artifact.
4. Decision C: residuals P2/P3 could not be filed — no substantive content survives. Filing would
   mean inventing findings. Accept the loss; do NOT fabricate.

---

## Wave 1 — CLOSED. All four agents reported; findings reconciled.

| track     | verdict | note |
| --------- | ------- | ---- |
| W1-df     | done    | `file:` allowlist entry + engine parity branch; verified by orchestrator under CI's exact invocation |
| W1-ml     | done    | Root cause found, **outside its own scope** — correctly routed instead of forcing an in-scope fix |
| W1-cq     | done    | CodeQL fully characterised; session-L claim REFUTED with evidence |
| W1-tenant | done    | #2005 fixed; 22 tests with an honest red/green classification |

### Corrections agents made to MY briefs (recorded — I was wrong)

1. **W1-ml refuted my brief's premise.** I asserted the underlying `TypeError` was "DESTROYED … you cannot diagnose from CI output alone" and told it to add temporary instrumentation. FALSE: `materialiser.py:317` already did `raise ... from exc` and `logger.exception` at :303 logged the full traceback. One grep on the CI log recovered it. No instrumentation was ever needed. The wrapper discarded the message from the *summary line*, not from the log.
2. **W1-ml found the real root cause is cross-package**, not in kailash-ml at all: CI installs `kailash==2.63.0` from branch source but `kailash-dataflow==2.19.1` from PyPI (log lines 293/428). All four ml `_validate_identifier` call sites already pass `max_length` — ml was clean, and no ml-side fix existed.
3. **W1-tenant found a FIFTH tenant-sensitive path #2005 never enumerated** — `clear()` at HEAD `:342` bypasses `_build_tenant_key` entirely and had its own `if tenant_id:`. `clear(tenant_id="")` wiped ALL tiers for ALL tenants. Destructive instance of the same class.
4. **My `test_ml_from_brief` attribution was wrong.** I told the user it was the documented invalid `OPENAI_API_KEY`. The observed evidence (an all-empty LLM result) does not discriminate between a bad credential and an unresolved provider — I asserted one cause without an instrument that could tell them apart. W1-ml identified a real structural defect behind it: `from_brief.py:736` builds `BaseAgentConfig` with no `llm_provider`. **Filed as #2022.**

### Orchestrator-run security probes (because neither security agent returned a verdict)

Both dispatched adversarial security reviewers (`M-sec`, `M-sec2`) went idle WITHOUT reporting. Per `agents.md` § Redteam Reviewer Dispatch an errored/empty return is ZERO evidence and MUST NOT count as a clean round — so **no clean adversarial security round is claimed for this change.** What IS claimed is the narrower set of targeted probes below, run directly:

**Sentinel (`_GlobalScopeSentinel(str)`) — the round-11 CRITICAL vector, re-probed:**

| probe | result |
| ----- | ------ |
| tenant literally named `__global__` | `tenant:__global__:k` — NOT collapsed (`isinstance`, not `==`) |
| hostile `str` subclass (`__eq__`→True, `__hash__`, `__str__`) | namespaced, does NOT escape to global |
| subclass of the sentinel | collapses to global |
| `__class__` reassignment on a `str` | blocked by CPython (`TypeError`) |
| deepcopy / pickle round-trip | preserves sentinel — intended |

The two collapse cases both require the caller to construct an arbitrary Python object as `tenant_id` — a capability that already subsumes passing `GLOBAL_SCOPE` or the target tenant string directly. **No privilege escalation.** The load-bearing property (a tenant NAMED `__global__` is not confused for the sentinel) holds.

**`file:` scheme — no new capability:**
`sqlite:////etc/passwd`, `sqlite:///../../../etc/passwd` and `sqlite:///tmp/x.db?mode=rwc` were ALL already accepted before this change, so pointing SQLite at an arbitrary path is inherent to the pre-existing `sqlite:` scheme, not introduced by `file:`. `gopher://` still raises — fail-closed posture intact. Scheme matching is case-insensitive (`FILE:`/`File:` classify identically), consistent with the other schemes.

### CodeQL — characterised, unchanged across both pushes

Advisory, NOT merge-required (`required_status_checks.contexts` is `[]`). The PR's actual blocker is `REVIEW_REQUIRED` (1 approving review) + `required_conversation_resolution`; `enforce_admins: false`.

Delta vs main by rule+path: exactly **ONE** branch-introduced security alert — `py/weak-sensitive-data-hashing` HIGH at `dataflow/adapters/dialect.py:193`. W1-cq pulled the SARIF flow (`security_definer.py:572 → dialect.py:209 → 183 → 193`): the tainted value is `_password_column`, set by `.password_column("password_hash")` — a **column NAME**, not a credential. `_identifier_fingerprint` is private, 18 call sites, every one an identifier-validator argument inside an error/log message. **Verified false positive.** Rewriting it to placate the heuristic would reintroduce a real defect: its docstring records why SHA-256 over `hash()` (PYTHONHASHSEED randomisation breaks cross-process log correlation).

### Final CI — head `dc2f246d2`: 38 pass / 1 fail (advisory CodeQL) / 12 skipped.

---

## Security round — COMPLETED BY THE ORCHESTRATOR, not by a review agent

**Three review dispatches returned NO verdict** (`M-sec`, `M-sec2` = `security-reviewer`; `M-rev` = `reviewer`) — all went idle without reporting. Every `general-purpose`/specialist agent dispatched this session (`W1-df`, `W1-ml`, `W1-cq`, `W1-tenant` = 4/4) reported in full. The discriminating difference is tool inventory: the silent three are the READ-ONLY types (no `Bash`) that were handed a 1358-line scratchpad to read; this is the `agents.md` § "Verify Specialist Tool Inventory Before Delegation" failure shape, one layer over — a read-only reviewer given a task whose evidence needs execution.

Per `agents.md` § Redteam Reviewer Dispatch, an empty return is ZERO evidence and MUST be re-run rather than counted clean. Re-run directly, with executable probes rather than a fourth dispatch.

### Results

| area | verdict | evidence |
| ---- | ------- | -------- |
| `_GlobalScopeSentinel(str)` — the round-11 CRITICAL vector | **CLEAN** | tenant named `__global__` stays namespaced; hostile `str` subclass (`__eq__`/`__hash__`/`__str__` overridden) does NOT escape to global; `__class__` reassignment blocked by CPython; deepcopy/pickle preserve the sentinel. The 2 paths that DO reach global require constructing an arbitrary object as `tenant_id` — a capability already subsuming `GLOBAL_SCOPE`. **No escalation.** |
| `file:` scheme — new capability? | **NONE** | `sqlite:////etc/passwd`, `sqlite:///../../../etc/passwd`, `?mode=rwc` were ALL accepted BEFORE this change. `gopher://` still raises — fail-closed intact. |
| `file:` scheme — **case-sensitivity parity** | **DEFECT FOUND + FIXED** | engine used case-SENSITIVE `startswith("file:")` while its scheme table and the parser are case-INSENSITIVE: `SQLITE:` validated but `FILE:` did not, diverging from the parser that had just classified it SQLite — the exact divergence the branch's own parity comment claims to prevent. Fixed in `1c849f953`. Failed CLOSED, so no security consequence. |
| `clear()` wipe-all reachability | **FIX HOLDS** | `""`/`"   "`/`"\t"` → ValueError; `0`/`False` → TypeError. Only `None`/no-arg/`GLOBAL_SCOPE` reach wipe-all. |
| one-time WARN scoping | **CLEAN** | per-PROCESS dedup (module flag), but the per-INSTANCE acknowledgement is correctly isolated — instance C's `clear_tenant_context()` does NOT silence instance D's accidental omission (D still warns). |
| `describe_exception_origin` message-leak | **CLEAN** | proven with a hostile exception whose `args` property AND `__str__` both raise `AssertionError` — NEITHER fired, so the helper genuinely never reads them. Credentials in the underlying error do not transit. |
| tenant-API callers that now raise | **NONE** | 0 external callers, 0 cross-imports; instrument shown to discriminate (same grep = 11 hits INSIDE `enterprise.py`). DataFlow's identically-named `_validate_tenant_id`/`set_tenant_context` are an independent class. |

### Residuals — recorded, NOT fixed, NOT security-blocking

1. **`clear(GLOBAL_SCOPE)` wipes ALL tiers for ALL tenants.** Consistent with `clear(None)` and an explicit opt-in, but a caller could reasonably read it as "clear only the global namespace". Worth a docstring line.
2. **`clear("real-tenant")` returns `False` and clears NOTHING** ("tenant-specific clear not fully implemented"). A caller who does not check the return believes erasure happened — a right-to-erasure / data-retention concern. **PRE-EXISTING**, not introduced here.
3. **`describe_exception_origin` echoes a module's `__name__` verbatim.** A dynamically-generated module whose name embedded a secret would surface it. Module names are author-chosen, not user input — theoretical, but "leaks nothing" needs that caveat.
4. **One-time WARN is per-process**, so in a many-instance process only the FIRST accidental omission warns. Diagnostic-value reduction, not a bypass.

**Scope of this claim, stated precisely:** these are the results of targeted probes against the areas I enumerated. They are NOT equivalent to an independent adversarial review, and none of the three dispatched reviewers contributed a verdict. A genuinely independent security lens on this diff remains OUTSTANDING.

### Final CI — head `1c849f953`: 32 pass / 1 fail (advisory CodeQL) / 8 skipped.

---

## Correctness review (M-rev) — landed late, found a HIGH I missed

`M-rev` reported after I had already closed out. It was worth the wait: it found a
**live, user-facing defect** my own security round did not, and refuted a claim I had
shipped into a **public CHANGELOG**.

### The HIGH — a THIRD independent scheme classifier

`AdapterFactory.detect_database_type` (`adapters/factory.py`) is an independent scheme
ladder — it borrows `parse_connection_string` to split the URL, then dispatches on the
scheme itself. It never inherited the `file:` fix. Verified end-to-end before acting:

```
ConnectionParser.detect_database_type('file:userdb1?mode=memory&cache=shared') -> 'sqlite'
AdapterFactory.detect_database_type('file:userdb1?mode=memory&cache=shared')   -> RAISES
```

and the two disagree INSIDE ONE FUNCTION, two lines apart (`utils/connection.py:116`
classifies, `:125` calls `create_adapter` → re-classifies → raises). Fixed in `8874fa575`
with a regression test that ENUMERATES the classifiers, so a fourth ladder reds the suite.

**Why my own parity probes missed it:** I probed the two surfaces I had CHANGED against
each other and found them consistent. I never enumerated the surfaces that *exist*. A
consistency check across a set I chose cannot discover a member I failed to include —
the instrument could not have found this, which is exactly `instrument-discipline.md`
MUST-1 turned on my own verification.

### Claims of mine it REFUTED

1. **"Restores enforcement-surface parity — only the central detector had never learned
   it."** FALSE twice over: the detector is not a single source of truth, and the six
   surfaces I named are CONSUMERS, not classifiers. Corrected in the public CHANGELOG,
   the in-code comment, and the follow-up commit body.
2. **`617d43212` cited "717 passed, 176 deselected" as its verification.** The run it
   came from was `2 failed, 717 passed, 1 skipped, 176 deselected`. I omitted the two
   pyright-version-skew failures because I had already attributed them — but a commit
   body is a durable artifact, and dropping the failures makes a red run read green
   (`instrument-discipline.md` MUST-2). The attribution was right; presenting the run as
   clean was not. Corrected here, on the record, per `git.md` (follow-up, never amend).

### Also folded in

- **ml call-site wiring was unproven** — the only call-site assertion was a prefix that
  passed with or without the helper. Now shape-pinned and discriminating (`815eabed7`).
- **`GLOBAL_SCOPE` has two meanings, one destructive** — documented; `clear(GLOBAL_SCOPE)`
  wipes all tenants, which my own `clear()` probe had observed but I had filed as a
  residual rather than fixing the docs.

### Confirmed by M-rev, independently

Pyright skew attribution (mechanism, not assertion: no `.venv/bin/pyright` → PATH 1.1.411
vs `pyproject.toml:175` pin 1.1.371; the 5 warnings sit at lines BEFORE the insertion
point, so not session-caused) · the `max_length` skew on both sides, `:3620` byte-exact ·
the ml commit being diagnosability-only · the 8/8 PyPI delta table · dataflow
`tests/unit/` **3670 passed** and kaizen regression+unit **12540 passed**, neither of
which I had run.

### Still open, from M-rev — NOT actioned

- **The editable-vs-PyPI pattern survives in five other CI steps** (`test-kailash-ml.yml`
  :211/:247/:317/:392, `gpu-smoke.yml:117`, `test-kailash-align.yml`:109/:163/:198). None
  currently exercises the dataflow path, so none is failing — but the CLASS is open. I
  closed the instance, not the class.
- **UNVERIFIED:** the combined ml `unit/ + integration/` run (CI's Coverage step) hangs
  locally past 45 min holding SQLite files open, though each directory passes alone in
  ~43s and CI does it in 507s. Local-harness issue, not a merge gate.
- **UNVERIFIED:** 12 of the 22 kaizen tenant tests, past M-rev's maxfail cap.

**M-rev verdict: MERGE-WITH-FIXES.** Both of its blocking items are now fixed.
