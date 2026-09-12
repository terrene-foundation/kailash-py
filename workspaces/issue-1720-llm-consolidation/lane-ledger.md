# Lane Ledger — cont-33

Lane-keyed per `orchestration-launch-ledger.md` MUST-1. The row unit is the LANE
(the ceiling-bound worktree+branch), NOT the agent and NOT the task. Ceilings bind
lanes; agents are unbounded (MUST-6).

| lane | branch | tasks (issues) | agents (status) | lane status |
| --- | --- | --- | --- | --- |
| L1-rest | fix/rest-pagination | #2230, #2231 | (mini-orchestrator: fans out internally) | in-flight |
| L2-df | fix/dataflow-warns | #1971, emit-forensics | (mini-orchestrator: fans out internally) | in-flight |

## Packing rationale (MUST-6)

4 dispatchable tasks → 2 ceiling slots, NOT 4. Two lanes, each a mini-orchestrator.

- **#2230 + #2231 are CO-LOCATED, not merely packed.** Both touch
  `src/kailash/nodes/api/rest.py`. Splitting them across lanes would guarantee a
  merge conflict on the same file — so bound (c) (joint revert-safety on one
  branch) forces them together rather than merely permitting it.
- **#1971 + emit-forensics are packed by disjointness.** `packages/kailash-dataflow/**`
  and `.claude/bin/**` share no file with each other or with L1, so one ceiling
  slot carries both safely.

## Ordering constraint carried into L1 (do NOT reorder)

#2230's shape fix ARMS a latent credential-exfiltration path: `_handle_async_pagination`
follows a response-body-supplied link with the caller's headers and no origin
validation, unreachable today only because the shape bug keeps the link out of
metadata. The guard lands BEFORE or WITH the shape fix, never after.

## cont-33 wave 2 — forced march

| lane | branch | tasks (issues) | ceiling slot | status |
| --- | --- | --- | --- | --- |
| L3-guard | fix/rest-guard-parity | 12 review findings | yes | in-flight |
| A1-A4 archive adjudication | — | 51 archive refs + 5 stashes | **NO — read-only** | in-flight |
| B1-dataflow | fix/dataflow-cluster | #2210, #2206, #2075, #2052 | yes | in-flight |
| B2-audit | fix/audit-cluster | #2110, #2109, #2107 | yes | in-flight |
| B3-kaizen | fix/kaizen-cluster | #2212, #2010, #2086 | yes | in-flight |

Packing note: A1–A4 are READ-ONLY adjudication and consume ZERO ceiling slots —
the ceiling binds worktrees/branches, not agents, so analysis lanes are free.
B1–B3 are packed by subsystem so each lane's tasks are co-landable on one branch.

## Quota-pause recovery — 2026-09-12, and the two brief gaps it exposed

An account session-limit paused every lane at once. Nothing was corrupted and
nothing was killed — but the survey found **49 uncommitted files across 4
worktrees and ZERO commits on any lane branch**, so the entire fleet's output
existed only as working-tree state. Preservation, not relaunch, was the first
move: each resume brief now leads with "commit what you already have on the
branch before starting anything new".

Liveness was established by a **process check with a fired control** (`lsof -t
+D <worktree>` returning 0 open fds on all five, control = this shell's own
pid), never by a stale last-commit or a clean `git status` — both of those are
equally consistent with "gone" and "mid-run".

### Gap 1 — STEP-0 asserts worktree IDENTITY, not OCCUPANCY

I dispatched a second lane into the audit worktree while another lane held 21
uncommitted files there. The STEP-0 assertion **passed**, correctly: it compares
`--show-toplevel` to `pwd -P` and to the main checkout, which answers "am I in
the right tree", not "is anyone already working here". Two writers on one
worktree under one git identity is the collision `--author` cannot untangle.

**Fix for every future dispatch brief:** add a `git status --porcelain`
emptiness check at spawn time. Empty = free tree; non-empty = occupied, refuse
and report. The lane that caught this made the point itself before standing
down.

### Gap 2 — lane briefs did not require a tool-inventory check before fan-out

The crypto lane fanned #2172 out to an agent with Read/Grep/Glob only. It
refused correctly per `agents.md` § "Verify Specialist Tool Inventory Before
Implementation Delegation" rather than faking a receipt it could not produce —
but a full agent turn was spent to learn that. A mini-orchestrator brief MUST
carry the same tool-inventory obligation the top-level orchestrator carries:
implementation work goes only to a specialist declaring BOTH `Edit` AND `Bash`.

That refusal was still net-positive: its read-only derivation corrected the
issue from **1 site to 13 across 5 files** (its own first grep missed the very
file the issue names; a multiline re-fire caught it), and corrected two
attributions — `sanitizers.model.yml` does NOT model the function (it says so
in-file, a model row was tried and measured ineffective), and lazy `%s` is not
a barrier because the record still formats at emit.

### Self-inflicted, recorded rather than buried

My own `fix(edge)` commit reported **exit code 0 with every gate green and HEAD
unmoved** — the pre-commit formatter rewrote the staged files after staging,
which aborts the commit. Only the explicit before/after `rev-parse` comparison
caught it; the push would then have read "Everything up-to-date" over a stale
HEAD. Landed on the retry as `34d55f5f6`, push confirmed by fetching and
comparing `local == origin/dev`, not by reading the push output.

## Corpus-wide instrument defect: single-line grep is blind to 30.6% of log call sites

Surfaced by a read-only sub-agent on #2172 and MEASURED here on the main
checkout before being acted on. Its first sibling-sweep grep returned zero hits
for `commerce.py` — **the very file the issue names**, so the file HAD to
appear. That known-answer control is what exposed the instrument rather than
the tree.

Cause: Black wraps any `logger.x(f"...")` call whose line exceeds the column
limit, putting the call on one line and the f-string on the next. A single-line
pattern (`logger\.(info|warning|error|debug)\(.*f"`) cannot see that form.

**Measured, both forms, on `src` + `packages` excluding tests:**

| form | sites | files |
| --- | --- | --- |
| same-line `logger.x(f"...` | 3761 | — |
| **strictly wrapped** (f-string on a LATER line) | **1655** | **370** |

**30.6% of all f-string logger call sites are invisible to a single-line grep.**
Control fires decisively: `commerce.py` returns 0 hits single-line, 1 multiline.

Correction to my own intermediate reading, recorded rather than overwritten: my
first comparison (3248 vs 3761) conflated two DIFFERENT patterns and was not a
wrapped-site count — the `\n?` in that probe made it match same-line calls too.
The sound figure is the strict one above, from the second measurement.

**Consequence:** any prior log-injection / secret-in-log / PII-in-log sweep of
this repo that used the single-line form under-reported by roughly a third, and
its empty-or-small result was read as coverage. Sweeps of this class MUST be
re-run with a multiline pattern, and MUST fire at a known-answer case first
(`instrument-discipline.md` MUST-3(a)).

## Wrapped-log-site triage — 1581 sites, 14 genuinely unsanitized, 0 credential leaks

Read-only lane, zero ceiling slots. Control fired first: `commerce.py` returns
**1** multiline hit and **0** single-line, so the instrument discriminates.

**Two instruments RECONCILED rather than one overriding the other.** The lane
measured 1581 where I measured 1655. The 74-site gap is fully explained, not
noise: I excluded only `tests`, it additionally excluded `examples/` (72),
`scripts/` (1), `benchmarks/` (1). 1581 + 74 = 1655 exactly. Agreement once the
denominators are aligned is stronger evidence than either figure alone.

| class | count | disposition |
| --- | --- | --- |
| (a) credential / secret | **0 genuine** (12 candidates) | nothing to fix |
| (b) PII / party identifier | 94 | provenance not traced per-site |
| (c) unsanitized caller-controlled | **14** | routed to owning lanes |
| (d) benign | ~1475 | RESIDUAL by subtraction, not read through |

**Class (a) is clean and was verified, not assumed.** All 12 credential-shaped
sites route through a masking helper, and the lane READ both helpers rather
than trusting their names: `_mask_connection_password` (`sql.py:722-727`) and
`mask_url` (`utils/url_credentials.py:300`, which masks userinfo AND
`password=`/`sslkey=` query params).

**Worst site in the corpus — `security.py:288` and `:297`:**
`f"Path traversal attempt detected: {file_path} -> {path}"` at WARN, where
`file_path` IS the rejected hostile input. A `\n`-bearing path forges log
records in the exact sink an auditor reads after an attack. The control logs
the attack verbatim into the record of the attack.

Routing (each to the lane already holding that package's worktree, so no new
ceiling slot and no two-writer collision):
- `security.py:288/297` → crypto lane (already editing `security.py`)
- `bulk.py:551/827/1293`, `core/nodes.py:3123` → dataflow lane
- `sso.py:318`, `directory_integration.py:278`, `kaizen/nodes/base.py:182`,
  3 document providers → kaizen lane
- `nexus/transports/webhook.py:706`, `nexus/plugins.py:331/337` → no lane owns
  nexus; taken on `dev` directly

**Honesty bounds the lane stated itself, carried forward:** class (d) is a
residual by subtraction — a class (a)/(c) site whose variable name matched no
token list sits in it undetected. Undecided and named rather than guessed:
`client_id` provenance at `kailash_mcp/server.py:4943/5044/5052` (client-supplied
would make them class (c)), and `calling_agent`/`target_agent` at
`nexus/trust/mcp_handler.py:301`.
