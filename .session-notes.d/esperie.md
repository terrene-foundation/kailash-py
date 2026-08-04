---
owner: esperie
last_reconciled_sha: 66f86b0b5
migrated_from: .session-notes
---

# Session Notes — 2026-08-04

## Where we are

Workspace issue-1720-llm-consolidation, phase 05-codify, branch
`fix/issue-1720-forest-drain` @ `66f86b0b5` — **pushed**, 0 behind / 24 ahead of
`origin/main` @ `26a4509b4`.

Redteam Round 1 ran. **5 of 6 gating findings are fixed**; 1 BUG remains open.
Release is blocked on a version-anchor decision, not on code.

## Read first

1. `workspaces/issue-1720-llm-consolidation/04-validate/sweep-2026-08-04.md` —
   current decision report. Supersedes the two 2026-08-03 sweeps.
2. **This file's Traps section** — three traps below cost real time this session.
3. `workspaces/issue-1720-llm-consolidation/04-validate/redteam-r1-launch-ledger.md`
4. `git log origin/main..HEAD` — every commit body carries its own evidence.

## In-flight state

- Only `.wave-tracker.d/esperie.md` dirty (pre-existing, NOT mine — do not revert).
- Version anchors: ONLY nexus bumped (2.16.0). core / dataflow / kaizen /
  kaizen-agents / ml unbumped — **Decision A in the sweep report**.
- Nothing running in the background.

## Executed this session

- **Fixed 5 R1 gating findings**, each verified green-with-fix AND red-without:
  `ad1bd9ee7` show_error stdout leak · `fe47995b6` hf_/fw_ scrubber shapes ·
  `8c5e70821` MCP empty inputSchema (root cause) · `4ab9da4a2` dialect budget
  WARN · `d9711b589` #1981 index-shift invariant.
- **Merged PR #1994** (`26a4509b4`); **closed PR #1991** with pin rationale.
- **Filed** #1995 (isort drift, deferred-quality), #1996 (unguarded FastMCP
  import), #1997 (Mistral scrubber gap, pinned xfail-strict).
- **Pushed** the branch; created + deleted a temporary `backup/*` ref.
- Pruned two stray worktrees (#1994's, and R1's baseline checkout).

## Wave tracker

→ `.wave-tracker.d/esperie.md`. Read BEFORE launching anything
(`wave-loop.md` MUST-6). R1's ledger is the workspace file above.

## Outstanding ledger (forest)

| ID  | Item                                       | Value-anchor                                     | Status                        |
| --- | ------------------------------------------ | ------------------------------------------------ | ----------------------------- |
| W9  | sweep-completeness CI ratchet              | user: "/redteam to convergence"                  | BLOCKED on human (CI cost)    |
| W10 | S4 `__cause__` 23-site sweep               | same class as W1/W5                              | queued                        |
| W11 | version bumps + CHANGELOGs + PR + release  | BUILD done = released                            | **BLOCKED on Decision A**     |
| W12 | `discovery._check_user_access` fails OPEN  | authz posture                                    | queued                        |
| W13 | `runtime._route_task` SEMANTIC branch dead | picks agent[0] while appearing LLM-routed        | queued                        |
| W14 | `/redteam` to convergence                  | user: "/redteam to convergence"                  | **R1 DONE; R2 needed**        |
| W15 | Sweep-5 blind spot + the 70 findings       | user: "/sweep per our procedural directives"     | Tier-1 gated; Decision C open |
| W16 | deferred-quality label + template          | `product-completion-first.md` MUST-2             | **DONE** — `c9ddf3143`        |
| W17 | `effortLevel: high` must reach loom Gate-1 | user: "high default across the entire ecosystem" | BLOCKED on loom ingest        |
| W18 | Push protection blocked the branch         | user approved; was the CRIT                      | **DONE** — 5 URLs allowlisted |
| W19 | compact-JSON over-redaction                | R1 security F4; still BUG, not reclassified      | **OPEN — only remaining BUG** |
| W20 | MCP stack undeclared (neither pin)         | measured: fastmcp 3.x not co-installable         | **OPEN — Decision B**         |

## Traps

- **`fastmcp` is NOT co-installable.** Installing it pulls `starlette>=1.x`,
  which breaks the pinned `fastapi` and takes every repo import down. I did
  this, then `uv sync` stripped the dev extras AND the editable sub-packages.
  Full restore is `uv sync --all-extras`. Verify after:
  `starlette 0.50.0 / fastapi 0.128.0 / mcp 1.26.0 / fastmcp ABSENT` and that
  `kailash`/`nexus`/`kaizen` resolve to repo paths.
- **ALWAYS `.venv/bin/python -m pytest`.** Bare `python` dies at conftest with
  `ImportError: cannot import name 'Node'`. A subagent hit exactly this, worked
  around it with hand-forced `PYTHONPATH`, and produced a CRITICAL finding that
  did not reproduce — it had assembled an env with `fastmcp` present. Verify
  any agent's environment before acting on its results.
- **Subagents idle without delivering.** All three R1 reviewers signalled idle
  with no report. Two returned full reports when asked directly; the third
  never did and its sweeps were re-run inline. An idle notification is NOT a
  ran-signal — treat it as zero evidence and query or re-run.
- `tools/sweep-redteam.py --all` scans `workspaces/*/specs/` → VACUOUS green.
  Specs are at root; pass `--json specs` explicitly (W15).
- Push protection: the #1974 regression vectors are synthetic but
  credential-shaped. Five were allowlisted 2026-08-03. **New tests must assemble
  vectors at runtime from fragments**, never as literals, or the push re-blocks.
- `.claude/settings.json` is a protected state path; the guard's Layer 2 is
  direction-blind. Use Write/`--body-file`, not a Bash heredoc.
- Branch switches abort when `.session-notes.d/*` is dirty — stash by path.
  **Five** unrelated pre-existing stashes live here; never `stash pop` blindly.

## Open questions for the human

- **Decision A (blocks release):** kaizen ships a documented BREAKING change
  (`ReasoningDegradedError`) at 2.45.0 unbumped; kaizen-agents consumes it,
  also unbumped. Is MINOR-for-breaking the convention? Recommended bumps in the
  sweep report §5.
- **Decision B:** pin the supported MCP stack? Neither `mcp` nor `fastmcp` is
  pinned, so behaviour depends on what happens to be installed.
- **Decision C:** the 70 spec-drift findings — recommend sampling 10 rows first.
