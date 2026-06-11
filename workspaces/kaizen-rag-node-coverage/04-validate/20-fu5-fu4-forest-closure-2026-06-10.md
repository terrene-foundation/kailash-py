# F31-FU5 + F31-FU4 forest closure — 2026-06-10 (session 2)

Value-anchor: brief _"provably correct, not merely importable"_ — FU5 is literally an importability
defect on the base surface; FU4 is the brief's "false-green hides real defects" clause, generalized
from the Wave-2 RAG discovery (`04-validate/15` § Wave-level learning) to the non-RAG kaizen surface.
BUILD repo — ALL work held UNCOMMITTED alongside F31-FU2 + Wave 3; commit stays with the user.

## F31-FU5 — numpy eager-import broke base `import kaizen` (CLOSED)

**Root cause (worse than the ledger claimed):** not just `kaizen.nodes.*` — bare `import kaizen`
hard-crashed without the `[rag]` extra. Chain: `kaizen/__init__.py:18` → `kaizen_agents` →
`patterns/runtime.py` → `from kaizen.nodes.ai.a2a import A2AAgentCard` → `nodes/ai/__init__.py`
eagerly imports `hybrid_search`/`semantic_memory` (module-scope numpy) → ImportError → fallback
`A2AAgentCard = None` → eager PEP-604 `A2AAgentCard | None` annotation (runtime.py:214) →
`TypeError: unsupported operand type(s) for |: 'NoneType' and 'NoneType'` at class creation.
The try/except ImportError in `kaizen/__init__.py` could not catch the TypeError.

**Fixes (root-cause, both layers):**

1. `kaizen/nodes/_optional.py` (NEW) — `require_numpy(feature)` helper: typed ImportError with
   `pip install kailash-kaizen[rag]` guidance (matches the `llm/auth/*` extras idiom).
2. `nodes/ai/hybrid_search.py` + `nodes/ai/semantic_memory.py` — `from __future__ import annotations`,
   numpy under TYPE_CHECKING, function-local `np = require_numpy(...)` at the 7 use sites.
3. `kaizen-agents/patterns/runtime.py` — `from __future__ import annotations` (annotations lazy;
   the `A2AAgentCard = None` fallback now degrades gracefully; runtime usage is getattr-based).
4. Same-class sweep (autonomous-execution Rule 4): PEP-604/isinstance scan over every
   `except ImportError: X = None` fallback in kaizen + kaizen-agents → runtime.py:214 was the only
   unguarded crash site (3 isinstance sites are `DATAFLOW_AVAILABLE`/`is None`-guarded upstream).
5. `tests/utils/docker_config.py` — module-scope `import pymongo` (same FU5 class in test infra:
   poisoned collection for every test importing `tests.utils`) made lazy in `_check_mongodb`;
   `pymongo` declared in kaizen `[dev]` (Declared=Imported).

**`kaizen.nodes.rag` requiring `[rag]` is BY DESIGN** (pyproject documents the extra as "the complete
`import kaizen.nodes.rag` dependency set"); the regression pins that its failure stays a clean
ModuleNotFoundError, never the TypeError class.

**Regression tests:** `tests/regression/test_issue_f31_fu5_numpy_lazy_import.py` — 10 tests:
subprocess meta-path blocker proves `kaizen` / `kaizen.nodes` / `kaizen.nodes.ai` /
`kaizen_agents.patterns.runtime` import WITHOUT numpy; runtime graceful-degrade with a2a blocked
(A2A_AVAILABLE False, AgentMetadata constructible); rag clean-MNFE; require_numpy guidance both ways;
behavioral numeric parity with numpy present (hash-embedding round-trip, TF-IDF cosine).

## F31-FU4 — wrong-shape-adapter false-green audit (CLOSED)

**Method:** mechanical prefilter (552 non-RAG kaizen test files → 26 candidates via adapter-class /
patch / fake-response-shape greps) → 4-cluster parallel audit workflow → adversarial verification of
every FALSE_GREEN candidate. Durable receipt: workflow run `wf_35c79bbd-b30` (14 agents,
55 doubles audited, 10 candidates, 3 confirmed). Ground truth: production LLMAgentNode publishes
`{"success": ..., "response": {"content": ..., "role": ...}}` (llm_agent.py:995, :586, :1020-1024).

**Confirmed #1 (HIGH, production defect FIXED):** `Agent.communicate_with`
(`src/kaizen/core/agents.py:2517-2520`) `str()`'d the response with no dict-content extraction —
production agent-to-agent messages + conversation history carried the dict REPR of the nested
response, not the text. Test double (flat string) masked it. Fix mirrors the existing dual-shape
handler (agents.py:926-933); adapter corrected to production envelope; assertion tightened
substring → equality (the dict repr CONTAINS the text — substring would still false-green).

**Confirmed #2 (HIGH, security-critical production defect FIXED):**
`EnterpriseAuthProviderNode._ai_risk_assessment` (`src/kaizen/nodes/auth/enterprise_auth_provider.py:218`)
read `result.get("content", "{}")` — the key-miss on every production envelope yielded `"{}"` →
score 0.0 / "allow": **AI fraud detection silently disabled in production (fail-open)**. The 6 test
doubles were reverse-engineered from the buggy parse (test comments admitted it). Fix: nested parse
matching the sibling sso.py:226-228 + RAISE on missing content so the except branch engages the
rule-based fallback (fail-closed to rule-based, never silent 0.0/allow). All 8 doubles in the file
corrected to the production envelope (incl. invalid-JSON test now genuinely exercising
json.JSONDecodeError, and 2 prompt-capture closures).

**Confirmed #3 (MEDIUM, test-only FIXED):** `test_sso_unit.py` "AI methods with various providers"
exercised ZERO AI-path code — the flat-string double routed through the rule-based fallback via
AttributeError; the weak email-only assertion greened on fallback output. Production sso.py parse was
CORRECT. Fix: production envelope + first_name/last_name assertions that only the AI path satisfies;
same-shape sweep over the 2 prompt-capture doubles in the file.

**Not-confirmed candidates (verified, refuted):** the flat-string doubles in
`test_kaizen_core_feature_completion.py` / `test_async_execution.py` exercise REAL legacy str-branches
production parsers retain (parser.py:1016-1017) — wrong-contract fixtures but no masked defect;
noted as hardening candidates, not defects.

**Regression tests:** `tests/regression/test_issue_f31_fu4_wrong_shape_adapters.py` — 5 behavioral
tests feeding the docs-exact production envelope: communicate_with equality + history, legacy
flat-string compatibility, enterprise-auth score/action parse (0.95/block), malformed-envelope
fail-closed-to-rule-based (sentinel-patched parent), sso AI-path field surfacing.

## Same-session zero-tolerance closures (found-it-own-it)

- `pytest.ini` vestigial `env_files = .env` key removed (pytest-env never installed; .env loads via
  `tests/conftest.py:18-20`) — kills the PytestConfigWarning.
- Pre-existing `EnvModelMissing` failure class: 9 tests in `test_kaizen_multi_agent_coordination.py`
  (byte-identical to HEAD a3de6cbee — proven pre-existing) + 36 in kaizen-agents
  (supervisor/governance) — no CI lane or .env supplies `KAIZEN_DEFAULT_MODEL`. Fixed via the
  issue-822 pattern: autouse fixture (kaizen file) + conftest `setdefault` (kaizen-agents; no test
  asserts the missing-var path).
- kaizen-agents adapter tests: `anthropic`/`google-generativeai` exercised by unit tests but
  undeclared — declared in kaizen-agents `[dev]` (Declared=Imported) + installed.
- `test_envelope_allocator_sdk.py` stale GradientZone contract (module legitimately dropped the
  symbol in PactEngine v0.4.0 type alignment) — rewritten to assert the original no-duplicate intent
  durably; + pre-existing lint debt in the file (F401/F841/B007/I001) cleared.
- 2 pre-existing UP037 quoted annotations (kaizen-agents runtime.py:748, state_manager.py:238) fixed.

## Warning dispositions (observability Rule 5)

- `FutureWarning structured_output_mode='auto' deprecated` (async_single_shot.py:344, fired by the
  822 regression test): **by-design** — kaizen's own v3.0 deprecation banner on the user-default path
  the test intentionally exercises; the shim must live through its cycle (zero-tolerance 6a);
  suppressing in tests would mask the banner. Removal scheduled v3.0.
- `env_files` PytestConfigWarning: **Fixed** (this session, see above).

## Gates at time of writing

ruff clean across kaizen src+tests AND kaizen-agents src + the test files this session touched
(kaizen-agents tests/unit carries ~369 PRE-EXISTING lint findings in files untouched by any session
gate — declared forest item, see 21-* receipt); kaizen RAG+regression suites 1633 passed / 1 warning
(dispositioned above); FU4-affected files 55/55; kaizen-agents last-failed re-run 40/40 green; full
kaizen unit + kaizen-agents unit/regression re-runs in flight at writing — final counts in the
convergence receipt (21-*).

## R1 redteam corrections (2026-06-11)

**R1 security-reviewer HIGH — CLOSED same-session (autonomous-execution Rule 4):**
`src/kaizen/nodes/auth/directory_integration.py` carried the IDENTICAL flat-shape parse at 4 sites
the FU4 sweep missed (`_ai_search_analysis` :267, `_ai_role_assignment` :444,
`_ai_permission_mapping` :511, `_ai_security_settings` :575 pre-fix). Security blast radius:
`_ai_security_settings` returned `{}` on every production envelope — AI-driven MFA tightening
silently dead; role/permission sites were fail-safe (least-privilege defaults). Fix: nested parse +
raise-on-missing at all 4 sites (the enterprise_auth shape, so the documented except-fallbacks
engage); 10 test doubles in test_directory_integration_unit.py corrected to the production
envelope; 3 regression tests added to test_issue_f31_fu4_wrong_shape_adapters.py (settings parse,
settings fail-closed-to-safe-defaults, roles parse + least-privilege fail-closed — the flat shape
must never grant "admin"). 63/63 across regression + auth suites post-fix.

**R1 verifier LOW precision corrections to this receipt:** (1) the communicate_with extraction
lives at agents.py:2519-2525 (not :2517-2520); (2) test_enterprise_auth_provider_unit.py has 9
nested-envelope doubles (not 8); (3) test_sso_unit.py "3 corrected" = the AI-path doubles
specifically; the file carries 6 nested-envelope literals total (3 were already correct).

**R1 security LOW (advisory, pre-existing, NOT fixed this session):**
enterprise_auth_provider.py:59 constructor default `ai_model: str = "gpt-4o-mini"` is a hardcoded
model string (env-models.md) — predates this diff; same class exists across the auth node family;
forest item.

## R2 redteam corrections (2026-06-11)

R2 reviewer: **APPROVE** (all 5 delta items verified, 63/63, receipt claims confirmed against the
live tree). R2 security: **CHANGES-REQUESTED** — its mandated WIDER repo sweep (adjudicating ~130
`.get("content")` hits) surfaced a residual cluster of the SAME bug class at 3 security/compliance
sites outside the auth family, all CLOSED same-session (Rule 4):

1. `src/kaizen/nodes/security/ai_threat_detection.py:263` (pre-fix) — flat read → dict →
   `.split()` AttributeError swallowed by the except: **AI threat intelligence dead** on every
   production envelope. Fixed: dict-guarded content extraction + raise-on-missing → documented
   `ai_available: False` degrade.
2. `src/kaizen/nodes/security/ai_behavior_analysis.py:254` (pre-fix) — identical; **AI behavior
   analysis dead**. Same fix.
3. `src/kaizen/nodes/compliance/gdpr.py:1549` (pre-fix) — flat read → `json.loads(dict)` TypeError
   → None: **AI compliance analysis dead**. Same fix (raise → documented None degrade).

None of the three had ANY test coverage of the LLM parse path (why the class survived). 3
behavioral regression tests added to test_issue_f31_fu4_wrong_shape_adapters.py (now 11 tests):
production-envelope parses (narrative/intelligence extraction, recommendations extraction,
risk_level parse) + malformed-envelope fail-closed per site. Module-level `LLMAgentNode` stub via
monkeypatch for the two security nodes (they instantiate the node inside the method).

R2 security's adjudicated-correct sweep also confirmed: a2a.py (5 sites), multimodal.py, sso.py,
strategies/agent_loop/providers/wire_protocols/memory `.get("content"/"response")` hits are either
nested-correct or genuinely different dict shapes — NOT the bug class.

R2 LOW closed: the 4 prompt-capture doubles in test_directory_integration_unit.py
(TestDirectoryIntegrationPromptEngineering) aligned to the nested production envelope so the
parse path their names imply is actually exercised. 66/66 across auth + nodes + regression
post-fix; ruff clean.
