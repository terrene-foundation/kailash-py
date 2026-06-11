# FU5 + FU4 + zero-tolerance closures — /redteam CONVERGED 2026-06-11

Posture L5_DELEGATED. Scope: the full held-uncommitted tree vs HEAD `a3de6cbee` — the already-
converged F31-FU2 + Wave-3 portions (receipts 16-19) PLUS this session's FU5/FU4/zero-tolerance
closures (receipt 20 + its R1/R2 correction sections). BUILD repo — commit stays with the user.

## Round history (durable receipts — verify-resource-existence MUST-4)

| Round | Agents (task IDs) | Verdicts | Outcome |
| ----- | ----------------- | -------- | ------- |
| FU4 audit | workflow `wf_35c79bbd-b30` (14 agents) | 55 doubles audited, 3 confirmed FALSE_GREEN | 2 production defects + 1 test-only fixed (receipt 20) |
| R1 | reviewer `a9dc866b983d07efc` / security `a28dc0b3bbc39dd6d` / closure-parity `ac35cecc28c641852` | APPROVE / CHANGES-REQUESTED (1 HIGH) / ALL-VERIFIED (3 LOW precision) | HIGH = directory_integration.py flat-shape ×4 → FIXED same-session |
| R2 | reviewer `a9874fec67c137b94` / security `a1d55cb61628f8024` | APPROVE / CHANGES-REQUESTED (3 same-class HIGH via wider sweep) | ai_threat_detection + ai_behavior_analysis + gdpr → FIXED same-session; LOW (prompt-capture doubles) also fixed |
| R3 | kaizen-specialist `a1c2d25d298658200` (Bash+Read) | **CONVERGED-CLEAN** — zero findings; independent fresh sweep; receipts verified claim-by-claim | Convergence confirmed |

Convergence per workspace convention (receipts 16/17/18: fix-round → clean-round = converged):
R2-reviewer clean + R3 all-clean; every security finding fixed and adversarially re-verified
in the SAME session (autonomous-execution Rule 4 — zero follow-up issues filed for in-budget gaps).

## The wrong-shape-adapter class — final tally (sessions 1+2)

Production LLMAgentNode envelope: `{"success", "response": {"content", "role"}, ...}`
(llm_agent.py:993-1012). Sites where production code read the FLAT shape and silently lost the
AI path, all FIXED with nested parse + raise-on-missing → documented fail-closed fallback:

1. `core/agents.py` communicate_with — dict-repr pollution of agent messages/history.
2. `nodes/auth/enterprise_auth_provider.py` — AI fraud detection fail-open (0.0/"allow").
3. `nodes/auth/directory_integration.py` ×4 — incl. AI-driven MFA tightening dead (R1).
4. `nodes/security/ai_threat_detection.py` — AI threat intelligence dead (R2).
5. `nodes/security/ai_behavior_analysis.py` — AI behavior analysis dead (R2).
6. `nodes/compliance/gdpr.py` — AI compliance analysis dead (R2).

R3's independent repo-wide sweep adjudicated every remaining `.get("content")`/`.get("response")`
hit as nested-correct or different-dict-shape — class CLOSED across kailash-kaizen src.

Test-side: 25+ doubles corrected to the production envelope across 4 unit files;
`tests/regression/test_issue_f31_fu4_wrong_shape_adapters.py` = 11 behavioral tests
(parse-production-envelope + fail-closed per site; equality-not-substring; legacy flat-string
path pinned where production retains it).

## Final gates (all verified by command at write time)

| Gate | Result |
| ---- | ------ |
| Canonical workstream gate (`tests/unit/rag tests/integration/rag tests/regression`, env -u KAIZEN_DEFAULT_MODEL) | **1644 passed, 0 failed, 1 warning** (the dispositioned by-design v3.0 deprecation banner) |
| kaizen-agents `tests/unit tests/regression` (full) | **3171 passed, 0 failed, 61 skipped** |
| FU4-affected suites (regression + auth + nodes) | 66/66 |
| FU5 regression (subprocess import-blocker) | 10/10 — `import kaizen` / `kaizen.nodes` / `kaizen.nodes.ai` / `kaizen_agents.patterns.runtime` all green WITHOUT numpy |
| `grep -c '"code":'` across 9 real-content RAG files | 0 ×9 (Wave-4 files untouched, retain theirs BY DESIGN) |
| `pytest --collect-only` both packages | exit 0 (13.8k + 3.4k collected) |
| ruff | clean: kaizen src+tests; kaizen-agents src + every test file this session touched |
| `uv pip check` | 252 packages compatible |
| Inline-DDL sweep (schema-migration 1a) | clean |
| Operator-path sweep (`/Users/esperie` in src) | clean (suspension.py docstring scrubbed) |

## Combined-invocation isolation finding (forest item, NOT a held-work defect)

The FIRST-EVER single-process run of the FULL `tests/unit` tree + `tests/integration/rag`
(11,394 passed / 51 failed) exhibits cross-suite global-state pollution: 32 rag integration
tests fail ONLY in that combination (`KeyError: 'model'` inside workflow-launched LLM stages;
mock-confidence drift 0.8 vs 0.85 — registry/provider global-state class, cf. the v2.23.0
node-registry-collisions release). Proven NOT the held work: (a) every suite green per-suite;
(b) env-var A/B negative; (c) all session-enabled files (examples / protocol / providers-document)
coexist green with the rag tests (209/209 probe). The polluter is long-standing unit-tree code;
bisecting 11k tests is its own shard. Repro: combined invocation above. Canonical gates for this
repo are per-suite (matching CI tier separation).

## Remaining 19 pre-existing per-suite failures (documented, out of shard)

In never-previously-gated dirs, all failing identically at HEAD-content: 7×
test_intelligent_agent_responses (mock-quality assertions), 5× llm/huggingface preset endpoint
resolution (network-dependent), 2× issue-12 SSRF env-dependent, 1× document_understanding adapter
kwarg drift, 1× nexus temperature, 1× bs4-not-installed assert (bs4 installed), 1× boto3 sibling,
1× timestamping multi-fallback. (The 20th — platform-compat hardcoded path — was FIXED this
session via suspension.py.) Forest item with this list as the acceptance inventory.
