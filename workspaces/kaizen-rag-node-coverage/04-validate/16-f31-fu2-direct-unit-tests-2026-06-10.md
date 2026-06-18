# F31-FU2 — composer/parser DIRECT unit tests (hardening) — CONVERGED 2026-06-10

Value-anchor (re-validated at re-pickup per value-prioritization MUST-3): brief *"provably
correct, not merely importable"* + `testing.md` § "One Direct Test Per Variant" + the prior
session's G4 re-value-rank durable receipt (`04-validate/15-wave-output-side-2026-06-09.md:254`,
F31-FU2 ranked #1). The 18 output-side parsers + 22 input-side composers were proven only via
integration capture / standalone probes; a refactor of any parser's error-mapping shipped a
**silent** regression. This shard adds a direct per-function unit test so such a refactor ships a
**loud** failure.

State at start: F31 input (L3) + output (Wave 2.5) committed + RELEASED as kaizen **2.24.6** on
`main @ a3de6cbee`. This shard is TEST-ONLY, additive, on top of released code. BUILD repo —
held UNCOMMITTED in the working tree; commit stays with the user.

## Delivered

205 new direct-call Tier-1 unit tests across all 6 RAG node files (additive: **1762 insertions,
0 deletions**, `src/` untouched):

| File | new tests | surface |
| ---- | --------- | ------- |
| test_query_processing_nodes.py | 71 | 6 parsers + 6 composers + `_loads_response_object`/`_unwrap` |
| test_agentic_nodes.py + test_conversational_nodes.py | 54 | 5 agentic parsers + 6 agentic composers + 3 conversational composers |
| test_evaluation_nodes.py + test_workflows_nodes.py + test_graph_nodes.py | 80 | 6 parsers + 7 composers + `_parse_score_array` |

Serial execution in the main checkout (worktree isolation infeasible — root `.venv` editable
`kaizen` resolves to the MAIN checkout). Each shard: kaizen-specialist read each source parser
and asserted **its own** documented honest default (zero-tolerance Rule 2) — the parsers diverge
sharply (query_processing top-level `parse_error:"empty-response"`; eval `{"scores":[]}` with NO
sentinel; agentic plan/verification `{}` with nested reasons; agentic decomposition/reasoning_chain
FORWARD values with no sentinel; graph entity-extraction ONE-ELEMENT-LIST wrap; graph global_summary
PROSE with only `empty-response`/`non-string-content`). Red-pre proven per shard.

## Mechanical convergence evidence

- Coverage parity (re-derived independently by R1 + R2): **40/40** module-level parsers+composers
  have ≥1 direct-call test site; **zero gaps**.
- Additive-only: `git diff … | grep -c '^-[^-]'` = **0**.
- Suite green: `pytest packages/kailash-kaizen/tests/unit/rag/ -q` → **805 passed**, exit 0.
- No SUT mocking; no `LocalRuntime` in the unit tier; ruff clean on all 6 files.

## Redteam convergence receipts (durable — verify-resource-existence MUST-4)

Posture: **L5_DELEGATED** (Round 1 OPTIONAL at L5; ran to 2-consecutive-clean per user directive).

- **R1 security-reviewer** — task `a867a5af2a93bff89` — **APPROVE**, 0 CRIT/HIGH/MED/LOW (no secrets;
  fully offline pure-fn tests; the two `exec()` sites are test-controlled execution of SDK-generated
  `PythonCodeNode` codegen with literal namespaces, not attacker input; malformed payloads terminate
  at typed-sentinel assertions with no code/SQL/shell sink; no JWT/HMAC surface).
- **R1 reviewer** — task `a7df75dc50d499267` — **APPROVE**, 0 CRIT/HIGH/MED/LOW (coverage 40/40,
  additive-only, 805 passed, no SUT mock, no LocalRuntime, ruff clean; per-file honest-sentinel
  spot-checks PASS with borrowed-sibling guard confirmed). [First R1 reviewer attempt task
  `a121d9aa9c4e971e8` died on a transient server rate-limit `(not your usage limit)` at ~95s —
  single-agent throttle, NOT the synchronized ≥2-in-30-48s signal; re-launched.]
- **R2 reviewer (exhaustive)** — task `afb9f2e2b0f5b5ca3` — **APPROVE**, **18/18** parsers PASS
  (each asserts the real source sentinel at correct nesting; no false-green; no fabricated value),
  zero variant-completeness gaps, re-confirms held.

**Convergence:** R1 (security APPROVE + reviewer APPROVE, 0 findings) → R2 (exhaustive reviewer
APPROVE, 0 findings) = **2 consecutive clean rounds**. Criteria 1–3 (0 CRIT / 0 HIGH / 2 clean) +
4 (coverage 40/40 AST/grep-verified) + 5 (every parser/composer has a direct test) all met; 6 (frontend
mock) N/A.

## Notes / forest (unchanged disposition)

- 2 pre-existing pyright unused-variable diagnostics (`lambda _q,_c`, `**kwargs` on pre-existing
  helper signatures) git-proven pre-existing; pyright non-gating here (gates = ruff + pytest). Not churned.
- Reviewer-surfaced test-infra nuance: `uv run python -m pytest tests/unit/rag/` resolves the package
  venv deterministically where `.venv/bin/python <abspath>` intermittently collected 0 items (the
  `tests/conftest.py → tests/utils/docker_config.py → import pymongo` sub-venv chain). Env-resolution
  artifact, not a test defect — both forms agree on 805 passed when the env resolves.
- Pre-existing `env_files` pytest-config warning: vestigial `pytest-env` key, test-infra, orthogonal (held).

## Remaining F31 queue (value-ranked, unchanged)

1. Wave 3 — `from_function` migration (large; supersedes held in-place #1117 nested-port patches) → needs its own /todos sharding plan.
2. Wave 4 — simulated-node strip/flag/build → **PRODUCT CALL (user)**.
3. Forest: F31-FU4 (audit non-RAG kaizen tests for the wrong-shape-adapter false-green class — unbounded);
   F31-FU5 (`hybrid_search.py` module-scope `import numpy` makes base `import kaizen.nodes.*` raise without `[rag]`).
