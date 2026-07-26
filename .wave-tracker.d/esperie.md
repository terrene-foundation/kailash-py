# Wave tracker — esperie

## Status: WAVE 7 IN FLIGHT (2026-07-26, session C)

Branch `fix/issue-1720-forest-drain`. Forest work SECURED at commit `0066e4fcb`
(73 files, all five issues) — the prior session's uncommitted-tree risk is CLOSED.
`black --check` clean on all 77 changed .py files; pre-commit passed on the commit.

## Launch ledger — Wave 7 (orchestration-launch-ledger.md MUST-1)

Check this table BEFORE spawning anything. Match every completion notification
against it BEFORE reacting (MUST-2 / MUST-3).

| track            | scope (files owned EXCLUSIVELY)                                      | specialist        | status                    |
| ---------------- | -------------------------------------------------------------------- | ----------------- | ------------------------- |
| w7-1981-contract | kaizen a2a.py error-contract, runtime.py:992, #1981 consumers        | kaizen-spec       | in-flight                 |
| w7-cred-audit    | S4 `__cause__` sites, fallback.py:91, sweep autouse-skip (READ-ONLY) | security-reviewer | **DONE** — report applied |
| w7-nexus         | packages/kailash-nexus/** — S8 atomicity, `_tools`, MINOR bump       | nexus-spec        | **DONE** — `84f08d203`    |
| w7-core-dialect  | src/kailash/db/dialect.py, connection_parser.py, staging_utilities   | infra-spec        | in-flight                 |
| w7-2nd-scrubber  | kaizen/llm/errors.py (S1)                                            | kaizen-spec       | in-flight                 |
| w7-nexus-del     | `Nexus.__del__` -> close() deadlock (patterns.md); nexus tests       | nexus-spec        | in-flight                 |

### Landed this wave

- `0066e4fcb` — the five-issue forest, secured from its uncommitted state (73 files)
- `cd6b82950` — S2 (`FallbackResult.to_dict` raw leak) + S6 (sweep autouse-skipped in CI)
- `84f08d203` — S8 nexus register() all-or-nothing + `_tools` removal + 2.16.0 MINOR

### Verified, do NOT re-derive

- **S4 is 23 sites, not the ledger's 8.** 9 explicit `raise … from e` + 14 BARE raises inside
  `except` where Python sets `__context__` implicitly. The 14 are invisible to a `from e` grep —
  that is why the original sweep missed them. `packages/kaizen-agents/` has ZERO sites.
- **Nexus registration touches SEVEN stores**, not four (2 registry + 1 gateway + 4 MCP). The
  ledger's "four" was the MCP subset.
- **`_register_handler_workflow` never existed** anywhere in kailash-nexus — it was a phantom
  method name in the CHANGELOG and a code comment. Real surface is `Nexus.register_handler`.
- **`_tools` writes register nothing reachable**: it exists only on the FastMCP fallback shim,
  which `MCPServer` assigns to `self._mcp`, never to itself; the JSON-RPC handler iterates
  `_tool_registry`.

### AF-3 RESOLVED by orchestrator probe — do NOT re-open

The credential audit flagged `kaizen/llm/client.py:863,1402,1603` (`raise Timeout() from exc`)
as _possibly_ S4 sites and correctly refused to assert either way, since it needed httpx
behavior not readable from this repo. Probed directly:

| exception                                             | `str()` renders the URL?                          |
| ----------------------------------------------------- | ------------------------------------------------- |
| `TimeoutException` / `ConnectTimeout` / `ReadTimeout` | **NO** — `'timed out'` only                       |
| `ConnectError`                                        | **NO**                                            |
| `HTTPStatusError` **from `raise_for_status()`**       | **YES** — full URL incl. userinfo AND query token |

So the three `raise Timeout() from exc` sites are **NOT** message/traceback leaks and need no
`from None` treatment. `e.request.url` still holds the credential as an ATTRIBUTE, but nothing
in kaizen/kaizen-agents reads it (`http_client.py:235` takes `.host` only).

**This makes S4 concrete rather than theoretical.** All four `raise_for_status()` call sites
(`multi_modal.py:169,412`; `landing_ai_provider.py:240`; `ollama_vision_provider.py:216`) are
ALREADY in the S4 list (A6, A7, B11-B14, B9/B10) — so the enumeration is complete for this
class, and the `__cause__` those sites carry is a real credentialed URL, not a hypothetical one.

### Open concern to challenge at report time

`DIALECT_UNKNOWN_MAX_IDENTIFIER_LENGTH = SQLITE_MAX_IDENTIFIER_LENGTH` (128, the LOOSEST budget)
in `src/kailash/db/dialect.py`. Documented as a deliberate greppable marker rather than a silent
fail-open, which is defensible — but it does NOT close NEW-1 for PostgreSQL deployments, where a
100-char identifier still passes validation and is then truncated server-side at 63, aliasing two
models onto one table. DataFlow's engine DOES know its dialect (`_fit_identifier_to_dialect`), so
those call sites can pass the real budget. Do not accept "documented + greppable" as closure.

Exclusive-ownership split is deliberate: no two tracks may edit the same file.
`a2a.py` error-CONTRACT belongs to w7-1981-contract; `a2a.py` credential-sanitize
belongs to NO track this wave (w7-cred-audit is read-only and reports only).
Version anchors + CHANGELOGs belong to w7-nexus (nexus only) and the orchestrator.

## Findings queue — session B redteam round 2, the "recorded, NOT fixed" table

| id    | sev      | assigned to                                                                                                                 |
| ----- | -------- | --------------------------------------------------------------------------------------------------------------------------- |
| NEW-1 | CRITICAL | w7-core-dialect                                                                                                             |
| NEW-2 | HIGH     | w7-core-dialect                                                                                                             |
| S1    | HIGH     | w7-2nd-scrubber                                                                                                             |
| S3    | HIGH     | w7-1981-contract                                                                                                            |
| S4    | MED-HIGH | w7-cred-audit                                                                                                               |
| S2    | MED      | w7-cred-audit                                                                                                               |
| S6    | MED      | w7-cred-audit                                                                                                               |
| S7    | MED      | w7-1981-contract                                                                                                            |
| S8    | MED      | w7-nexus                                                                                                                    |
| W9    | —        | UNASSIGNED — sweep-completeness CI ratchet (enumerator already exists at `04-validate/find-unsanitized-provider-errors.py`) |

## Standing operational note (carried from session B — still live)

Agents go idle WITHOUT delivering a final report — **6 occurrences in session B**. The
working remedy is to RESUME via message rather than re-dispatch: it recovered 3 of 4,
including the round-1 security report that found both HIGH credential leaks, and a
round-1 lens that surfaced ~6 hours late carrying the session's only commit-blocker.
Re-dispatch only after a resume ALSO returns empty. Never score a silent-idle as a clean
round — that manufactures a convergence that never happened.

## Concurrency

Cold-start ~3 concurrent (`rules/worktree-isolation.md` Rule 4); Wave 7 opened at 3 and
stepped to 5 with NO throttle signal observed. Back off only on the falsifiable signal
(≥2 agents dying in a ~30–48s window carrying `not your usage limit`). Session B lost all
6 shards of Wave 5 to a usage limit — work survived ONLY because shards edited the SHARED
tree rather than `isolation: "worktree"`, which would have left 6 orphan checkouts to
recover. Keep using the shared tree with exclusive file ownership.

Run heavy test suites SERIALLY: concurrent suite runs alongside live agents produced
`sqlite3 disk I/O error` and perf-threshold failures that were self-inflicted, not real.
