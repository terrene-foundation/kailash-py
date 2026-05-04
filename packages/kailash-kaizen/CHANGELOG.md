# Changelog

All notable changes to the Kaizen AI Agent Framework will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **`research` and `web-search` optional-dependency extras (closes #814 Shard 2).** `pyproject.toml` now declares two optional-extras groups so users opt in to the lazy-imported runtime deps in `kaizen.research.parser` (arXiv paper search + PDF parsing) and `kaizen.tools.native.search_tools` (DuckDuckGo + HTML extraction). Install via `pip install 'kailash-kaizen[research]'` or `pip install 'kailash-kaizen[web-search]'` per `rules/dependencies.md` "Declared = Imported". Replaces the pre-existing pattern where `arxiv`, `pypdf`, `duckduckgo-search`, and `beautifulsoup4` were lazy-imported in source but undeclared in the manifest.
- **`kaizen.llm.testing.mock_preset()` test-only deployment factory (closes #788; cross-SDK parity with kailash-rs `LlmDeployment::mock()` at `crates/kailash-kaizen/src/llm/deployment/presets.rs:1183`).** New module `kaizen.llm.testing` exposes `mock_preset(model: str = "mock-model") -> LlmDeployment` for test code that needs a structurally-valid `LlmDeployment` without binding to a real provider. The deployment carries `preset_name="mock"`, `WireProtocol.OpenAiChat`, `StaticNone` auth, and an endpoint at `https://example.com/v1` (RFC-2606 reserved test host that resolves under the SSRF guard). Cross-SDK parity: Rust gates `mock()` behind `#[cfg(any(test, feature = "test-utils"))]` so the symbol does not exist in production builds; Python lacks cargo features, so the structural defense is **physical module separation** — `LlmDeployment.mock` does NOT exist on the production class, `kaizen.llm.presets.mock_preset` does NOT exist, and `"mock"` is NOT a registered preset. Test code MUST `from kaizen.llm.testing import mock_preset` explicitly. The module path is the deliberate red flag — production code that imports from a module named `testing` is structurally identifiable by `grep -rn 'kaizen.llm.testing' src/`. `mock_preset(...).supports()` returns the fail-closed all-False matrix, matching Rust's `CapabilityMatrix::for_preset("mock")` fall-through behavior (no explicit `"mock"` row in either SDK).
- **7 capability matrix rows for Python-only OpenAI-compatible aggregators + local-server presets (closes #790).** `together`, `fireworks`, `openrouter`, `deepseek`, `lm_studio`, `llama_cpp`, `docker_model_runner` previously fell through to `ALL_FALSE_CAPABILITIES` because they had no row in `kaizen.llm.capabilities._PRESET_CAPABILITIES`. Calls to `LlmDeployment.together(...).supports()` reported the deployment as uncapable for tools / vision even though Together AI hosts tool-calling and vision-capable models. New rows assert the deployment-surface capability following the existing convention (vision=True means "can serve vision-capable models, per-model gating is caller's responsibility" — same as `ollama` / `groq` / `mistral`). `deepseek` is the conservative outlier (vision=False) because `api.deepseek.com/v1` exposes only deepseek-chat / deepseek-coder at the deployment surface; the DeepSeek-VL family is distributed as separate weights, not served by this preset's endpoint. Per-preset shape tests added to `tests/unit/llm/test_supports_capability_matrix.py`; the `_NON_EMPTY_PRESETS` parametrized sweep extended to cover all 7. The `<provider>_default` convenience presets (#787) carry the PARENT preset literal so capability lookup routes through the parent row automatically — no separate `_default` rows needed.
- **Cross-SDK reconciliation note (#790).** kailash-rs `CapabilityMatrix::for_preset` at `crates/kailash-kaizen/src/llm/deployment/capabilities.rs:120-250` does NOT yet have rows for these 7 presets; it currently falls through to `Self::all_false()`. Per `rules/upstream-issue-hygiene.md`, no auto-cross-file — the kailash-rs side should land equivalent rows in a coordinated cross-SDK release. Until then, Python `supports()` reports the canonical capability matrix; Rust returns all-False for the same preset name.

### Changed

- **`WebFetchTool._extract_text` raises `ImportError` when beautifulsoup4 is missing instead of silently returning raw HTML (closes #814).** Pre-fix: caller passed `extract_text=True`, beautifulsoup4 was missing, the helper logged a `WARNING` and returned the original HTML — invisible to the LLM caller, who treated raw markup as extracted text. Post-fix: the helper raises `ImportError("extract_text=True requires beautifulsoup4 — install via `pip install 'kailash-kaizen[web-search]'` or pass extract_text=False to receive raw HTML.")` and `WebFetchTool.execute(...)` catches it at the call site, returning `NativeToolResult.from_error(...)` so the LLM sees the failure. Module-scope `_BeautifulSoup` sentinel replaces the inline `try/except ImportError` per `rules/dependencies.md` BLOCKED anti-pattern (silent fallback to None). Behavioral regression at `tests/regression/test_issue_814_bs4_loud_failure.py`.
- **`cohere_preset` default endpoint advanced from `https://api.cohere.com/v1` (legacy Generate API) to `https://api.cohere.ai/v2` (modern Chat API) for cross-SDK parity with kailash-rs (closes #794).** kailash-rs `LlmDeployment::cohere()` at `crates/kailash-kaizen/src/llm/deployment/presets.rs:386-396` constructs `Endpoint::new("https://api.cohere.ai/v2")`; Python `cohere_preset` previously diverged at `api.cohere.com/v1`, breaking byte-equivalent cross-SDK code-portability per `rules/cross-sdk-inspection.md` § 3 (EATP D6). The on-wire request envelope at `/v2` is OpenAI-Chat-compatible — Rust delegates v2 through `OpenAiAdapter` (see `presets.rs:378-380`) and Python preserves the same `WireProtocol.CohereGenerate` tag for adapter routing continuity. The new `LlmDeployment.cohere_from_env()` constructor from #791 inherits the new default automatically. Both Cohere endpoints currently coexist (v1 has no announced sunset date), but Cohere's published API reference now directs new integrations at v2.

#### Migration — `cohere_preset` endpoint (#794)

Callers who explicitly relied on the legacy v1 Generate API request envelope (different shape from the v2 Chat envelope) MUST opt in via explicit overrides:

```python
from kaizen.llm.presets import cohere_preset

# Default behavior in 2.18.0+: v2 Chat API on api.cohere.ai
dep = cohere_preset(api_key="...", model="command-r-plus")
# → endpoint: https://api.cohere.ai/v2

# Pre-2.18.0 legacy v1 Generate API on api.cohere.com (callers who built
# request bodies in v1 Generate format MUST migrate via this opt-in):
dep = cohere_preset(
    api_key="...",
    model="command-r-plus",
    base_url="https://api.cohere.com",
    path_prefix="/v1",
)
```

Callers who did not pass explicit `base_url` / `path_prefix` overrides AND whose request handling treats Cohere as OpenAI-compatible (the canonical kaizen pattern) require no migration — the v2 Chat API is OpenAI-compatible by design.

### Removed

- **Vestigial `kaizen.research` integration subsystem moved out by PR #75 — 5 source files + 4 test files + 1 example dir (closes #814 Shard 2).** PR #75 (`801de2bb`, 2026-03-25, "structural split — move ~44K lines of L2 engine code to kaizen-agents") relocated `advanced_patterns.py`, `experimental.py`, and `intelligent_optimizer.py` to `packages/kaizen-agents/src/kaizen_agents/research_patterns/` but left `kaizen.research.__init__.py` re-exporting 7 names (`AdvancedPatternBuilder`, `CompositionalPattern`, `HierarchicalPattern`, `AdaptivePattern`, `MetaLearningPattern`, `ExperimentalFeature`, `IntelligentOptimizer`, `FeatureManager`, `IntegrationWorkflow`, `DocumentationGenerator`, `CompatibilityChecker`, `FeatureOptimizer`) and 5 source files (`feature_manager.py`, `integration_workflow.py`, `documentation_generator.py`, `compatibility_checker.py`, `feature_optimizer.py`) all carrying unguarded `from kaizen_agents.research_patterns.experimental import ExperimentalFeature` — `kaizen-agents` is NOT in `kailash-kaizen/pyproject.toml::dependencies`, so any clean `pip install kailash-kaizen` raised `ModuleNotFoundError` at first `from kaizen.research import …`. The full vestigial cluster has been deleted: 5 src files, 4 unit tests (`test_advanced_patterns.py`, `test_experimental_feature.py`, `test_intelligent_optimizer.py`, `test_compatibility_checker.py`, `test_feature_manager.py`, `test_integration_workflow.py`, `test_documentation_generator.py`, `test_feature_optimizer.py`), 1 integration test (`test_phase2_integration.py`), 1 example directory (`examples/research-integration/`).

#### Migration

Per `rules/zero-tolerance.md` Rule 6a, public-API removal normally requires a `DeprecationWarning` shim covering one minor cycle. **No shim owed**: from PR #75 forward (2026-03-25, ~6 weeks before this release), `from kaizen.research import AdvancedPatternBuilder` raised `ModuleNotFoundError` on first use because the underlying `advanced_patterns.py` no longer existed in this package. The `__all__` re-export resolved the name, but `import` failed. **No consumer could have ever successfully imported these symbols on main since 2026-03-25** (verified: `git log --oneline --since=2026-03-25 packages/kailash-kaizen/src/kaizen/research/{advanced_patterns,experimental,intelligent_optimizer}.py` returns zero results). There is no working public surface to deprecate.

Callers who imported the moved patterns SHOULD migrate to `kaizen_agents.research_patterns.*`:

```python
# Before (raised ModuleNotFoundError since 2026-03-25)
from kaizen.research import AdvancedPatternBuilder, ExperimentalFeature

# After (kaizen-agents installed)
from kaizen_agents.research_patterns.advanced_patterns import AdvancedPatternBuilder
from kaizen_agents.research_patterns.experimental import ExperimentalFeature
```

The `FeatureManager`, `IntegrationWorkflow`, `DocumentationGenerator`, `CompatibilityChecker`, `FeatureOptimizer` classes have no migration path — they were a Phase-2 experimental-feature subsystem orchestrating the now-relocated patterns; with patterns owned by `kaizen-agents`, the subsystem belongs there. Re-implementation in `kaizen-agents` is a future workstream tracked in a follow-up issue.

The remaining `kaizen.research` public surface (`ResearchAdapter`, `ResearchParser`, `ResearchValidator`, `ResearchRegistry`, `SignatureAdapter`, `ResearchPaper`, `ValidationResult`, `RegistryEntry`) is unchanged.

### Fixed

- **`kaizen.research.adapter.ResearchAdapter.create_signature_adapter` passed `dict` to `Signature(inputs=, outputs=)` which expects `List[str]` (closes #814 Cluster D, shipped in #818).** The adapter was silently corrupting `Signature._inputs_list` since the file was authored — `_inputs_list` was populated with dict iteration order rather than parameter names. Behavioral regression at `tests/regression/test_issue_814_research_adapter_inputs_list.py` exercises both the param-name path and the empty-params fallback.

- **All 22 `BaseTool.execute(...)` overrides across `kaizen.tools.native.*` now widen `**kwargs`per LSP override conformance (closes #814 Cluster A, shipped in #818).** Pre-fix: 17 of 22 override sites declared narrower signatures than the`BaseTool.execute(self, **kwargs)`base, triggering pyright`reportIncompatibleMethodOverride`. Post-fix: every override declares `\*, <named keyword-only params>, **\_kwargs: Any` — keyword-only marker matches the runtime contract (`ToolRegistry`dispatches via`tool.execute_with_timing(\*\*params)`); underscore prefix documents the parameter as a sink. The LLM tool-calling surface is `BaseTool.get_schema()` and is unaffected by the signature widening.

- **6 Optional/None safety issues in `kaizen.tools.native.*` + `kaizen.research.adapter` (closes #814 Cluster B, shipped in #818).** `notebook_tool.py` validator-narrowing across function boundaries; `parser.py` lazy-import sentinel typing; `task_tool.py` typed `None` adapter guard per `rules/zero-tolerance.md` Rule 3a; `interaction_tool.py` `Union[sync, async]` callback narrowing.

## [2.18.1] — 2026-05-03 — issue #781 hygiene release (T2) + #801 test fix

Patch release cutting PyPI for T2 (kaizen TODO-NNN comment-strip) of the issue #781 cleanup workstream, plus the test-only #801 fix already on main.

### Changed (T2 of #781 — comment-only, packages/kailash-kaizen/src/)

- Stripped 80 `TODO-NNN` markers across 31 files in `research/`, `tools/native/`, `core/`, `core/autonomy/`, `mixins/`, `strategies/`, `execution/`, `session/`, `integrations/`, `docs/` per the ratified disposition catalog (19 Class 1a banner / inline-shipped, 54 Class 1b module docstring provenance, 7 Class 3 mid-comment cross-reference). ADR-013 references in `tools/native/skill_tool.py` + `tools/native/task_tool.py` docstrings preserved per the catalog rule (strip TODO-NNN, keep ADR ref).

### Fixed (recap)

- `tests/unit/llm/openai/test_openai_strict_mode.py` — opt explicitly into `response_format` per #801 (already on main).

### Notes

- Comment-only diff for T2 (zero logic changes). The bump cuts PyPI per `build-repo-release-discipline.md` Rule 1.

## [2.17.1] — 2026-05-02 — CodeQL hygiene cleanup (#789 FIX track)

Patch bump. Closes 4 of 13 open CodeQL findings on the kaizen surface
per the #789 Rule 1b deferral track. The remaining 9 findings are tracked
as DEFER with per-finding runtime-safety proofs in #789's triage comment;
all 9 fall into 4 categorical CodeQL false-positive classes (fingerprint
redaction not recognised, runtime-deferred local imports, `Protocol` stub
bodies, `__del__` interpreter-shutdown defense).

### Fixed

- **`packages/kailash-kaizen/src/kaizen/orchestration/runtime.py`** — removed unused `Union` import (closes CodeQL alert #10874, `py/unused-import`).
- **`packages/kailash-kaizen/src/kaizen/signatures/core.py`** — removed unused `TYPE_CHECKING` import; the file's line-41 comment explicitly opts out of TYPE_CHECKING back-edges, so the import was deliberate non-use (closes CodeQL alert #10865, `py/unused-import`).
- **`packages/kailash-kaizen/src/kaizen/strategies/async_single_shot.py`** — refactored two `runtime = AsyncLocalRuntime() / try / finally: runtime.close()` blocks to `async with AsyncLocalRuntime() as runtime:` form (closes CodeQL alerts #10923 + #10924, `py/should-use-with`). `AsyncLocalRuntime` exposes `__aenter__` / `__aexit__` (`src/kailash/runtime/async_local.py:1580,1590`) so the refactor is drop-in. The new form propagates exceptions cleanly through `__aexit__` on every code path including the inner-loop `break` and outer-`except` propagation; the prior form relied on an explicit synchronous `close()` in `finally` that did not await async cleanup.
- **`packages/kailash-kaizen/tests/unit/strategies/test_async_single_shot_tool_calls.py`** — extended 7 `mock_runtime_instance` setups with `__aenter__` / `__aexit__` `AsyncMock` hooks per `orphan-detection.md` Rule 4 (refactor sweeps tests in same commit). 14/14 tool-call tests pass; 456/456 broader strategies + orchestration + signatures sweep clean.

### Known follow-ups (filed separately, not blocking this release)

- **9 remaining CodeQL findings** tracked as DEFER per `zero-tolerance.md` Rule 1b on issue #789 with per-finding runtime-safety proofs. Each finding falls into a categorical CodeQL static-analyzer limitation (not project-specific debt). Rule 1b conditions met: runtime-safety proof ✓, tracking issue (#789) ✓, release-PR link (this CHANGELOG entry) ✓, release-specialist signoff to be confirmed at the release PR review.

## [2.17.0] — 2026-05-02 — `<provider>_from_env` cross-SDK convenience constructors (#791)

Minor bump. Closes the deferred cross-SDK API-shape parity gap surfaced
by the post-2.16.2 audit: kailash-rs exposes 12 zero-arg
`pub fn <provider>() -> Self` classmethods on `LlmDeployment` (constructing
auth-less deployments with the canonical hosted URL; callers chain
`.with_api_key(...)` to populate credentials before use). Python's parent
`<provider>_preset(api_key, model)` factories require both inputs at
construction per `rules/env-models.md`, so a Rust user porting
`LlmDeployment::openai()` directly hit `TypeError`. This release adds an
explicit `_from_env` constructor variant per provider — eager-validates
against the environment, raises typed `MissingCredential` on missing keys
or models, and routes capability lookups through the parent preset row.

### Added

- **12 `<provider>_from_env` convenience constructors on `LlmDeployment` (closes #791; cross-SDK parity with the 12 zero-arg `pub fn <provider>() -> Self` classmethods on kailash-rs `LlmDeployment` at `crates/kailash-kaizen/src/llm/deployment/presets.rs:153,249,346,386,408,430,458,928,964,1000,1036,1072`).** Each `LlmDeployment.<provider>_from_env()` (and module-level `<provider>_from_env_preset()`) reads `<PROVIDER>_API_KEY` plus `<PROVIDER>_PROD_MODEL` (with legacy fallback to `<PROVIDER>_MODEL`) from the environment and delegates to the existing parent factory. Eager-validates per `rules/env-models.md` — missing env vars raise typed `MissingCredential` with the env var name as `source_hint`. Providers covered: `openai`, `anthropic`, `google`, `cohere`, `mistral`, `perplexity`, `huggingface`, `groq`, `together`, `fireworks`, `openrouter`, `deepseek`. Each returned deployment carries the PARENT `preset_name` literal (e.g. `"openai"`, not `"openai_from_env"`) so `LlmDeployment.supports()` and `for_preset(...)` capability lookups route through the parent row automatically — consistent with the `<provider>_default` precedent (#787).
- **Registry round-trip via `get_preset("<provider>_from_env")()`.** Each `<provider>_from_env` name is registered alongside its classmethod attachment so both surfaces produce structurally identical deployments. Cross-SDK parity sweep enumerates all 12 names against a frozen set in `tests/unit/llm/test_from_env_presets.py::test_from_env_preset_names_complete`; adding a new Rust zero-arg classmethod without wiring its Python `_from_env` peer fails the sweep loudly.

### Implementation notes — design rationale (#791)

Three candidate designs were on the issue body; **Option 3 (`_from_env` variant)** was selected because it is the only design that satisfies `rules/env-models.md` ("ALL API keys MUST come from `.env`") while preserving the eager-validation convention every existing `_preset` factory already enforces. Option 1 (auth-less constructor + `.with_api_key(...)` builder) introduces an `LlmDeployment` whose state is structurally unauthenticated until a builder call — a divergent shape from every other Python preset factory. Option 2 (`<provider>(api_key=os.environ.get(...))`) silently couples the default to an env var; the call site cannot tell whether env was consulted, which is the implicit-magic failure pattern the Python idiom rejects. Option 3 is a separate explicit method per provider; the suffix announces env-driven construction at every call site. Per EATP D6 (`rules/cross-sdk-inspection.md` § 3): semantics match Rust (same endpoint, wire protocol, eventual auth strategy); the idiom-difference is the explicit `_from_env` naming + eager validation at construction time.

A user porting Rust `LlmDeployment::openai()` (zero-arg, auth-less, configured later via `.with_api_key(env::var("OPENAI_API_KEY")?)`) transcribes the contract to Python as a single `LlmDeployment.openai_from_env()` call; the resulting deployment is byte-equivalent to the long-form `openai_preset(api_key, model)` shape with credentials sourced from `OPENAI_API_KEY` + `OPENAI_PROD_MODEL`.

### Tested

- `tests/unit/llm/test_from_env_presets.py` — 36 tests covering: cross-SDK registry parity sweep across all 12 names; per-provider deployment shape (wire / auth / preset_name / endpoint URL byte-pinned to the Rust source-of-truth literal); typed `MissingCredential` raise on missing api_key (parametrized × 12) and on missing model (parametrized × 4 representative providers); `<PROVIDER>_PROD_MODEL` precedence over `<PROVIDER>_MODEL`; legacy `<PROVIDER>_MODEL` fallback when PROD is unset; `GEMINI_PROD_MODEL` legacy fallback for `google_from_env`; classmethod ↔ module-function agreement; registry round-trip via `get_preset`; capability-matrix routing through the parent row. All env-mutating tests serialize through a module-scope `threading.Lock` per `rules/testing.md` § "Serialize Env-Var-Mutating Tests Via Module Lock".

### Known follow-ups (filed separately, not blocking this release)

- **Cohere endpoint URL divergence between Python (`api.cohere.com/v1` + `CohereGenerate` wire) and Rust (`api.cohere.ai/v2`).** Surfaced during the #791 cross-SDK source-of-truth audit; pre-dates #791. The `_from_env` wrapper inherits whichever URL the parent `cohere_preset` exposes, so reconciling the parent URL automatically lifts both surfaces. Tracked separately so the URL+wire decision (v1 Generate vs v2 Chat — different on-wire contracts) gets its own design pass.
- **#788 (`LlmDeployment.mock()` test-utils gating), #789 (CodeQL Rule 1b deferral track), #790 (capability rows for 7 Python-only presets).** Sibling cross-SDK parity / hygiene workstreams from the post-2.16.2 audit.

## [2.16.2] — 2026-05-02 — Default-URL convenience presets (cross-SDK parity)

Patch bump. Closes the cross-SDK API-shape parity gap surfaced by the
`/redteam` audit immediately following 2.16.1: kailash-rs exposes four
zero-arg classmethods on `LlmDeployment` for canonical localhost defaults
(`ollama_default()`, `lm_studio_default()`, `llama_cpp_default()`, zero-arg
`docker_model_runner()`); Python required callers to thread the localhost
URL by hand. Same bug class as 2.16.1's preset-alias fix per
`rules/cross-sdk-inspection.md` § 3a — fix-immediately disposition under
`rules/autonomous-execution.md` Rule 4.

### Added

- **`LlmDeployment.ollama_default(model)` + `ollama_default_preset(model)` (cross-SDK parity with kailash-rs `LlmDeployment::ollama_default()` at `crates/kailash-kaizen/src/llm/deployment/presets.rs:509`).** Convenience constructor equivalent to `ollama_preset("http://localhost:11434/v1", model)`. Deployment carries `preset_name="ollama"` (parent literal — mirrors Rust's `Self::ollama(...)` delegation), so capability-matrix lookup routes through the parent row automatically. The `_default` variant is a constructor convenience, not a distinct preset identity.
- **`LlmDeployment.lm_studio_default(model)` + `lm_studio_default_preset(model)` (cross-SDK parity with `LlmDeployment::lm_studio_default()` at `presets.rs:1138`).** Equivalent to `lm_studio_preset("http://localhost:1234", model)`. Deployment carries `preset_name="lm_studio"`.
- **`LlmDeployment.llama_cpp_default(model)` + `llama_cpp_default_preset(model)` (cross-SDK parity with `LlmDeployment::llama_cpp_default()` at `presets.rs:1170`).** Equivalent to `llama_cpp_preset("http://localhost:8080", model)`. Deployment carries `preset_name="llama_cpp"`.
- **`LlmDeployment.docker_model_runner_default(model)` + `docker_model_runner_default_preset(model)` (cross-SDK parity with the zero-arg form of `LlmDeployment::docker_model_runner()` at `presets.rs:527`).** Constructs `http://localhost:12434/engines/llama.cpp/v1` (Rust's engine-specific default). Deployment carries `preset_name="docker_model_runner"`. Note: the convenience variant uses `path_prefix="/engines/llama.cpp/v1"` to match Rust exactly; the long-form `docker_model_runner_preset` retains its existing default `path_prefix="/engines/v1"` (both are valid Docker Model Runner endpoints).

### Implementation notes

- Python idiom-difference vs Rust per EATP D6: `model` is REQUIRED on every Python `_default_preset(model)` factory per `rules/env-models.md` (which mandates explicit model selection at construction time and never silent defaults). Rust accepts truly zero-arg signatures because Rust's preset surface does not carry the same env-driven model-selection convention. Semantics match — both SDKs route requests to a local server with the canonical default URL — only the construction arity differs.
- All four registry names (`ollama_default`, `lm_studio_default`, `llama_cpp_default`, `docker_model_runner_default`) added to `_PRESETS` so `get_preset(name)(model=...)` round-trips identically with the classmethod surface.

### Tested

- `tests/unit/llm/test_default_url_presets.py` — 28 tests covering: cross-SDK parity registry naming, per-preset deployment shape (wire / auth / preset_name / endpoint URL), byte-equivalence with the long-form factory, classmethod ↔ free-function agreement, empty-model rejection (per `rules/env-models.md`), registry round-trip via `get_preset`, and capability-matrix routing through the parent row (`<provider>_default(model).supports() == <provider>_preset(default_url, model).supports()`).

### Known follow-ups (filed separately)

- **`LlmDeployment.mock()` constructor** — kailash-rs gates this behind `cfg(any(test, feature = "test-utils"))` to prevent "mock shipped to prod" at compile time (`presets.rs:1181`). Python parity requires designing an equivalent gate (test-only module, import-side opt-in, or env-var) and cross-SDK alignment per `rules/cross-sdk-inspection.md` § 2; exceeds shard budget.
- **17 open CodeQL findings on the kaizen surface** — including `#10866 py/clear-text-logging-sensitive-data` on `presets.py:101`, which is a verified false positive: `_fingerprint(name)` calls `fingerprint_secret(raw)` (BLAKE2b non-reversible per #617). Tracking via Rule 1b deferral with per-finding runtime-safety proof.
- **Capability matrix rows for 7 Python-only presets** (`together`, `fireworks`, `openrouter`, `deepseek`, `lm_studio`, `llama_cpp`, `docker_model_runner`) — currently fail-closed via the all-False default; provider-specific research + cross-SDK alignment with kailash-rs `CapabilityMatrix::for_preset` required.

## [2.16.1] — 2026-05-02 — `ollama_default` preset alias parity

Patch bump. Closes the deferred cross-SDK parity gap reviewer flagged during
the 2.16.0 pre-release pass: the `"ollama_default"` preset literal kailash-rs
`CapabilityMatrix::for_preset` accepts as an alias for `"ollama"` was missing
from `kaizen.llm.capabilities._PRESET_CAPABILITIES`, so a Python caller
porting the alias from Rust hit the fail-closed all-False default while the
Rust caller saw the wired row.

### Fixed

- **`for_preset("ollama_default")` now returns the canonical Ollama capability row (cross-SDK parity with kailash-rs `CapabilityMatrix::for_preset` line 212 — `str_eq(preset_name, "ollama") || str_eq(preset_name, "ollama_default")`).** Row is byte-identical to `"ollama"` (`tools=True, vision=True, batch=False, caching=False, audio=False`) per `rules/cross-sdk-inspection.md` § 3a. Test surface: `_NON_EMPTY_PRESETS` parametrized sweep in `tests/unit/llm/test_supports_capability_matrix.py` extended to `"ollama_default"` so a future row drift in either SDK fails loudly.

## [2.16.0] — 2026-05-02 — LlmDeployment.supports() + register_bedrock_region

Cross-SDK parity with kailash-rs PR #725 (`CapabilityMatrix::for_preset`)
and PR #726 (`LlmDeployment::register_bedrock_region`). Both build on the
`preset_name` field landed in 2.15.0 (#761/#762).

### Added

- **`LlmDeployment.supports() -> dict[str, bool]` capability negotiation matrix (closes #763; cross-SDK parity with kailash-rs PR #725).** Returns a five-key dict (`tools`, `vision`, `batch`, `caching`, `audio`) describing what the deployment's wire protocol + endpoint surface CAN carry. Per-preset rows are byte-identical to kailash-rs `CapabilityMatrix::for_preset` per `rules/cross-sdk-inspection.md` § 3a so cross-SDK callers see the same capability bits for the same preset name. Fail-closed default (`rules/security.md` § Fail-Closed): unknown / future preset names AND manual constructions whose `preset_name` is `None` return all-False — adding a new preset constructor without wiring its capability row in `kaizen.llm.capabilities._PRESET_CAPABILITIES` leaves the new deployment marked uncapable until the wiring lands. Returned dicts are independent copies; mutating one cannot corrupt the matrix table or another caller's result. Per-model gating (e.g. `gpt-4o` supports vision but `gpt-3.5-turbo` does not) remains the caller's responsibility — the matrix reports the deployment surface, not per-model capability. New module `kaizen.llm.capabilities` (`for_preset`, `ALL_FALSE_CAPABILITIES`, `CAPABILITY_KEYS`).
- **`LlmDeployment.register_bedrock_region(region)` runtime override (closes #764; cross-SDK parity with kailash-rs PR #726).** Hatch-of-last-resort for operators on a newly-published AWS Bedrock region not yet in `BEDROCK_SUPPORTED_REGIONS` (the canonical fix is a kailash-py release that adds the region to the static set; this hatch covers the days/weeks before that release lands). Process-local registry (NOT shared across replicas — operators behind a load balancer MUST register on every replica at boot). Idempotent (repeated registration is a no-op). Format-validated against `^[a-z]{2,3}-[a-z]+-\d+$` (byte-identical regex to kailash-rs); malformed input raises the new typed `kaizen.llm.auth.aws.InvalidRegionFormat`, distinct from `RegionNotAllowed` (well-formed-but-unknown). Static allowlist short-circuits first; runtime registry is consulted only for regions not in `BEDROCK_SUPPORTED_REGIONS`. Thread-safe — copy-on-write `frozenset` swap under `threading.RLock`; readers are lock-free. Kailash-rs gates this behind `cargo feature = "bedrock-region-override"` (default OFF); Python is single-feature-set, so the function exists unconditionally and the call site IS the explicit opt-in.
- **`InvalidRegionFormat` typed error in `kaizen.llm.auth.aws.__all__`.** Distinct from `RegionNotAllowed` so operators can grep "I typo'd" vs "kailash-py hasn't released this region yet" — two-tier signaling per kailash-rs PR #726.

### Tested

- `tests/unit/llm/test_supports_capability_matrix.py` — 13 tests covering shape (five-key dict, all booleans), provider-distinct matrices for openai / anthropic / ollama / perplexity / bedrock_claude (issue AC: ≥3 presets), fail-closed for unknown preset names AND manual `preset_name=None` constructions, returned-dict independence (mutation cannot corrupt the table), compatible-preset inheritance from openai / anthropic rows (#761/#762), and a parametrized cross-SDK row-completeness sweep across 19 documented presets.
- `tests/unit/llm/auth/test_register_bedrock_region.py` — 13 tests covering static-allowlist short-circuit, registered-region validates, registered-region flows through `bedrock_claude(region, auth)` (issue AC), idempotency, malformed-input format rejection (10 parametrized cases mirroring kailash-rs `invalid_format_rejected`), non-string type-confusion rejection, two-tier `InvalidRegionFormat` vs `RegionNotAllowed` signal isolation, classmethod attachment on `LlmDeployment`, and a 16-thread concurrent registration / read soak test for thread-safety.

## [2.15.0] — 2026-05-02 — LlmDeployment escape-hatch presets + `preset_name` retrofit

Minor bump. Two cross-SDK parity issues close together:

- **(Added)** `LlmDeployment.openai_compatible(base_url, api_key)` (#761) and `LlmDeployment.anthropic_compatible(base_url, api_key)` (#762) escape-hatch presets — wrap an arbitrary HTTPS endpoint with the canonical OpenAI Chat / Anthropic Messages wire protocol. Cross-SDK parity with kailash-rs PR #722 / PR #724.
- **(Added)** `LlmDeployment.preset_name: Optional[str]` field, set by every preset factory (24 existing + 2 new) to the canonical literal. Cross-SDK parity with kailash-rs `LlmDeployment::preset_name()`.

### Added

- **`LlmDeployment.openai_compatible(base_url, api_key)` + `LlmDeployment.anthropic_compatible(base_url, api_key)` escape-hatch presets (closes #761, #762; cross-SDK parity with kailash-rs PR #722 / PR #724).** Wraps an arbitrary HTTPS endpoint with the canonical OpenAI Chat / Anthropic Messages wire protocol — useful for vLLM, llama.cpp servers, LM Studio remotes, LiteLLM proxies, OpenRouter Anthropic mode, internal gateways, and third-party OpenAI/Anthropic-compatible providers. SSRF guard runs on `Endpoint.base_url` automatically via the field validator (`deployment.py:129`, `mode="before"`); loopback (literal-IP) / RFC1918 private / link-local / cloud-metadata / non-HTTP(S) URLs raise `InvalidEndpoint` at construction. Anthropic variant defaults `anthropic-version: 2023-06-01` on `Endpoint.required_headers` (overridable). Both factories are reachable via the registry (`get_preset("openai_compatible")`, `get_preset("anthropic_compatible")`) AND the classmethod surface.
- **`LlmDeployment.preset_name: Optional[str]` field — canonical preset literal exposed on every constructed deployment.** Set by every preset factory (all 24 existing presets retrofitted in the same PR per `rules/zero-tolerance.md` Rule 6 Implement Fully) to the literal registered in `_PRESETS`. The literal — NOT the host or any caller-supplied URL fragment — prevents log-aggregator label cardinality blow-up and credential enumeration via observability per `rules/observability.md` § 8 (schema-revealing field names). Manual constructions leave it `None`; that's structural — `preset_name` is a public-API contract for preset-built deployments only. Cross-SDK parity with kailash-rs `LlmDeployment::preset_name()`. Python idiom is field access (`dep.preset_name`) rather than the Rust method-style (`dep.preset_name()`); the field IS the contract surface, and is consumed by the upcoming `supports()` capability matrix (#763) without per-call introspection.
- **`azure_openai_preset` added to `kaizen.llm.presets.__all__`.** Pre-existing orphan-detection §6 violation surfaced by this change (`__all__`-completeness audit) — the preset was eagerly defined and registered at module load, but absent from `__all__`, so `from kaizen.llm.presets import *` silently dropped it from the public re-export. Same-bug-class fix-immediately per `rules/autonomous-execution.md` MUST Rule 4.

### Tested

- `tests/unit/llm/test_preset_name_and_compatible.py` — 22 tests covering both new compatible presets (shape, classmethod parity, empty-arg rejection, parametrized SSRF guard rejection over loopback / private / link-local / cloud-metadata / non-HTTP(S)), every retrofitted preset's `preset_name` literal, registry membership, and a structural `len(list_presets()) == 26` lock so future regressions surface loudly.

## [2.14.0] — 2026-04-30 — Canonical `kaizen.core` re-exports + MLAwareAgent + env-model resolution

Minor bump. Three load-bearing changes land together:

- **(Fixed, HIGH-2)** Restores the canonical Quick Start from `specs/kaizen-core.md` §3 + `rules/patterns.md` § Kaizen — `from kaizen.core import BaseAgent, Signature, InputField, OutputField` now resolves on every fresh install.
- **(Added)** `kaizen.ml.MLAwareAgent` — first production consumer of the §2.4 ML tool-discovery surface, closing F-D-55 (orphan-detection §1).
- **(Changed)** `CoreAgent` + `GovernedSupervisor` no longer hardcode model strings; both resolve from `KAIZEN_DEFAULT_MODEL` per `rules/env-models.md` (closes F-D-02 + F-D-50).

### Fixed

- **`from kaizen.core import BaseAgent, Signature, InputField, OutputField` raised `ImportError` on every fresh install** — the canonical Quick Start documented in `specs/kaizen-core.md` §3 BaseAgent AND the project rule `rules/patterns.md` § Kaizen Quick Start crashed before any agent code ran. `BaseAgent` lives at `kaizen.core.base_agent`; `Signature` / `InputField` / `OutputField` live in `kaizen.signatures`. Neither was re-exported through `kaizen/core/__init__.py`. Surfaced by /sweep Sweep 6 spec-vs-code drift audit (2026-04-30, HIGH-2). Fix: re-export all four symbols from `kaizen.core` and add them to `__all__`. Also adds `StructuredOutput` to `__all__` (pre-existing orphan-detection §6 violation — eagerly imported but absent). Three Tier-1 regression tests in `packages/kailash-kaizen/tests/regression/test_kaizen_core_quickstart_imports.py` pin the contract structurally (import-resolution, `__all__` membership, canonical-module identity).

### Changed

- **Removed hardcoded model strings from `CoreAgent` + `GovernedSupervisor`; both now read from `KAIZEN_DEFAULT_MODEL` env var (closes F-D-02 + F-D-50).** `CoreAgent` (`kaizen.core.agents.Agent`) and `GovernedSupervisor` (`kaizen_agents.supervisor.GovernedSupervisor`) previously defaulted to `"gpt-3.5-turbo"` and `"claude-sonnet-4-6"` respectively when the caller omitted `model=`. This violated `rules/env-models.md` (model identifiers MUST come from `.env`) and locked every default-API deployment to a single provider. Both constructors now resolve the default from `KAIZEN_DEFAULT_MODEL` and raise `kaizen.errors.EnvModelMissing` (new typed error) with an actionable message when the env var is unset. Existing callers passing explicit `model=<literal>` are unaffected. Tier-1 unit tests in `tests/unit/test_kaizen_default_model_env.py` cover env-set, caller-override, env-unset, and empty-string env paths for both constructors.

### Added

- **`kaizen.errors.EnvModelMissing`**: typed `RuntimeError` subclass for "model identifier required but `.env` did not provide it" failures. Carries `env_var` and `component` attributes so multi-call-site triage can disambiguate which entry point raised. Surfaces as a top-level export from `kaizen.errors`.
- **`.env.example` at repo root**: documents `KAIZEN_DEFAULT_MODEL` plus the matching provider API-key entries per `rules/env-models.md` Model-Key Pairings table.
- **W6-012 — `kaizen.ml.MLAwareAgent` wires the §2.4 ML tool-discovery surface to a production call site (closes F-D-55).** Spec `kaizen-ml-integration.md §2.4.6` defined the canonical `BaseAgent` subclass that derives its tool-set from `km.list_engines()` / `km.engine_info()` per the §E11.3 MUST 1 binding clause; the discovery surface (`kaizen.ml.discover_ml_tools`, `kaizen.ml.engine_info`, `kaizen.ml.MLEngineDescriptor`) shipped in 2.12.x but had ZERO production consumer — classic orphan pattern per `rules/orphan-detection.md §1`. `MLAwareAgent` is now that consumer: at construction time it calls `discover_ml_tools(tenant_id=..., clearance_filter=...)`, converts every `MethodSignature` into a `kaizen.tools.types.ToolDefinition` whose `description` field embeds `kailash_ml.__version__` (so the §2.4.4 version-sync invariant is observable on the LLM-visible tool surface), and exposes the result as the immutable `agent.ml_tools` tuple. New file: `packages/kailash-kaizen/src/kaizen/ml/ml_aware_agent.py` (~250 LOC). New Tier-2 wiring test: `packages/kailash-kaizen/tests/integration/ml/test_kaizen_agent_engine_discovery_wiring.py` (4 tests covering tool-count parity, naming convention, immutability, and tenant-id flow per spec §2.4.7). Symbols test updated to enforce the new `MLAwareAgent` export. Per `rules/agent-reasoning.md` Permitted Deterministic Logic clauses 1+5+6: tool-set construction (mapping `MethodSignature → ToolDefinition`) is structural plumbing — the LLM still owns every routing/classification decision.
- **W6-011 — 28 Tier-1 unit tests for `kaizen.judges` (closes F-D-25).** Added `packages/kailash-kaizen/tests/unit/judges/` with 28 tests across construction, signature/protocol conformance, env-sourced model resolution, position-swap bias mitigation, microdollar budget enforcement, error taxonomy, classification-fingerprint redaction, helper-math (`_clamp_unit`, `_resolve_winner`), and wrapper validation (`FaithfulnessJudge`, `SelfConsistencyJudge`, `RefusalCalibrator`, `LLMDiagnostics`). All tests pass <1s per test (full suite 0.16s). Spec `specs/kaizen-judges.md` § 11 mandated 24 Tier-1 tests at `tests/unit/judges/`; the directory did not exist on main. Sibling Tier-2 wiring tests already lived at `packages/kailash-kaizen/tests/integration/judges/test_judges_wiring.py`. Tests use a deterministic `_ScriptedDelegate` (NOT a Mock — a real Python class satisfying the Delegate duck-type with scripted responses) per `rules/testing.md` "Protocol-Satisfying Deterministic Adapters" exception, exercising the same code paths a production Delegate hits.

## [2.13.1] — 2026-04-25 — Fix clean-venv ImportError (post-2.13.0 hotfix)

Patch — guards a pre-existing unconditional `import kaizen_agents.patterns.patterns` in `kaizen/orchestration/__init__.py` behind a `try/except ImportError`. The `kaizen-agents` package is NOT a declared dependency of `kailash-kaizen`; the proxies that consumed it were defensive `mock.patch` aliases for legacy test code. Without the guard, `from kaizen.orchestration import OrchestrationRuntime` (the new #602 surface in 2.13.0) raised `ModuleNotFoundError` for any clean-venv install of `kailash-kaizen` without `kaizen-agents` present. The proxy aliases are now installed only when `kaizen-agents` is co-installed.

### Fixed

- **`kaizen.orchestration` clean-venv import**: `import kaizen_agents.patterns.patterns` (and 3 sibling proxy imports) now wrapped in `try/except ImportError`. Surface unaffected when both packages co-installed; clean-venv `kailash-kaizen` install no longer breaks at module load.

This is the structural defense for `rules/dependencies.md` § "Declared = Imported — No Silent Missing Dependencies" — a verification gap caught by the post-release clean-venv install check (per `rules/build-repo-release-discipline.md` Rule 2).

## [2.13.0] — 2026-04-25 — PlanSuspension parity (#598) + OrchestrationRuntime parity (#602)

Minor bump — two cross-SDK parity surfaces land together: L3 plan suspension (PACT N3) and strategy-driven multi-agent orchestration runtime (kailash-rs ISS-27).

### Added

- **`kaizen.l3.plan.suspension` module** — five-variant `SuspensionReason` tagged union (frozen dataclasses + `Literal` `kind` discriminator) plus `SuspensionRecord` capturing the resume frontier:
  - `HumanApprovalGateReason(held_node, reason)` — node entered Held gradient zone
  - `CircuitBreakerTrippedReason(breaker_id, triggering_node)` — downstream dependency tripped
  - `BudgetExceededReason(dimension, usage_pct, triggering_node)` — envelope dimension hit threshold (default 90%)
  - `EnvelopeViolationReason(dimension, detail, triggering_node)` — envelope check rejected for non-budget reason (clearance, classification, dimension policy). Python-only today; cross-SDK parity for the 5th variant tracked in a sibling kailash-rs issue.
  - `ExplicitCancellationReason(reason, resume_hint)` — caller-initiated cancel
- **`SuspensionRecord.from_plan(reason, plan)`** — partitions plan node states into `running_nodes` / `ready_nodes` / `pending_nodes` (sorted lex for cross-SDK comparison stability), captures `suspended_at` UTC timestamp, and accepts an opaque `resume_context` payload.
- **`Plan.suspension: Optional[SuspensionRecord]`** — present while the plan is in `SUSPENDED` state, cleared on `resume()`. Round-trips through `Plan.to_dict` / `Plan.from_dict`.
- **`PlanExecutor.suspend(plan, reason=...)` / `AsyncPlanExecutor.suspend(plan, reason=...)`** — optional `reason` kwarg attaches the record at suspend time.
- **`PlanExecutor.suspend_for_circuit_breaker(plan, breaker_id, triggering_node)`** + async variant — convenience wrapper for the `CircuitBreakerTripped` variant; required because the breaker-trip signal originates outside the executor's hot loop.
- **`PlanExecutor.cancel(plan, reason="...", resume_hint="...")`** + async variant — always attaches `ExplicitCancellationReason` BEFORE cascading node-skip transitions, so `running_nodes` / `ready_nodes` / `pending_nodes` capture the pre-cancel snapshot.
- **Wire format helpers** — `suspension_reason_to_dict` / `suspension_reason_from_dict` / `suspension_reason_label` matching Rust serde `#[serde(tag = "kind", rename_all = "snake_case")]`. Cross-SDK forensic correlation works without a third-party tagged-union library.

### Changed

- **`PlanExecutor.resume(plan)` / `AsyncPlanExecutor.resume(plan)`** — now clears `plan.suspension` (PACT N3: the suspension record is consumed by resume; downstream callers that need the record for audit MUST capture it before calling `resume()`).
- **`AsyncPlanExecutor._execute_node` BLOCKED-verdict path** — classifies the suspension cause as `BudgetExceededReason` when the verdict reports a numeric overflow (`requested > available` on a known dimension) and `EnvelopeViolationReason` otherwise (structural rejection: clearance, classification, dimension policy).
- **Both executors' `_determine_terminal_state`** — when the loop ends with one or more HELD nodes, attaches `HumanApprovalGateReason` for the lexicographically-first HELD node. Takes precedence over a previously-recorded `EnvelopeViolation` because the actionable resume path is the human-approval gate.

### Cross-SDK Parity

Wire-format `kind` tags (`human_approval_gate`, `circuit_breaker_tripped`, `budget_exceeded`, `envelope_violation`, `explicit_cancellation`) are reserved across SDKs. Field shapes match `kailash-rs/crates/kailash-kaizen/src/l3/core/plan/types.rs:267-396`. The `envelope_violation` variant is the Python SDK's 5th; a follow-up kailash-rs issue tracks adding it for full parity.

### Tests

- 30 Tier 1 unit tests at `tests/unit/l3/plan/test_suspension.py` — variant construction, frozen-dataclass invariant, label stability, wire-format round-trip, parametrized cross-SDK vector table.
- 12 Tier 2 integration tests at `tests/integration/l3/test_suspension_emission.py` — drives each of the 5 trigger conditions end-to-end through `PlanExecutor` / `AsyncPlanExecutor`, asserts `plan.suspension.reason` is the right variant, asserts `Plan.to_dict` / `from_dict` round-trips the suspension field.

### Added (#602 — OrchestrationRuntime parity)

- **`kaizen.orchestration.OrchestrationRuntime`** — strategy-driven multi-agent coordinator mirroring the Rust `kaizen-agents::orchestration::runtime::OrchestrationRuntime` shape. Builder-style `add_agent` / `strategy` / `coordinator` / `config` setters; async `run(input)` returns `OrchestrationResult` with the same five-field shape as the Rust struct (`agent_results`, `final_output`, `total_iterations`, `total_tokens`, `duration_ms`). Sequential / Parallel / Hierarchical / Pipeline strategies dispatch through a single `agent_invoker` seam — Protocol-conforming agents need only implement `name` + `run_async` to participate.
- New surface: `OrchestrationRuntime`, `OrchestrationStrategy` (frozen dataclass + `sequential() / parallel() / hierarchical(name) / pipeline(steps)` factories), `OrchestrationStrategyKind` StrEnum (lowercase values match Rust serde), `OrchestrationConfig`, `OrchestrationResult`, `OrchestrationError`, `Coordinator` Protocol, `AgentLike` Protocol, `SharedMemoryCoordinator` (default in-memory backed by `SharedMemoryPool`), `PipelineStep`, `PipelineInputSource`.
- Coexists with — does NOT replace — `kaizen_agents.patterns.OrchestrationRuntime` (registry/lifecycle runtime for 10-100 agent fleets) and `kaizen.trust.orchestration.TrustAwareOrchestrationRuntime` (trust-policy enforcement).
- Tier 1: 37 unit tests in `tests/unit/orchestration/test_runtime.py`. Tier 2: 9 integration tests in `tests/integration/orchestration/test_runtime_e2e.py` exercising the runtime end-to-end through the real `SharedMemoryPool` coordinator + `TestCrossSdkShapeParity` locking the result-field set against the Rust struct shape.
- Spec: `specs/kaizen-agents-governance.md` § 19.6.

## [2.12.3] — 2026-04-25 — Security sweep (#614 + #617)

Patch bump — defense-in-depth tightening of tenant-id log hygiene and credential-adjacent fingerprinting. No API changes.

### Fixed

- **Raw `tenant_id` leak in `kaizen.judges.llm_diagnostics`** (#614 item 1+2). Five structured log emissions (`kaizen.llm_diagnostics.init` + 4 call-trace lines) shipped `tenant_id` as a plaintext extras key `"llm_diag_tenant_id"`, bleeding tenant identity into log aggregators whose access surface is strictly wider than the production database (per `rules/observability.md` §8 + `rules/tenant-isolation.md` §4). All 5 sites now route through `_hash_tenant_id(tenant_id)` (shared helper in `kaizen.observability.trace_exporter`, SHA-256 `sha256:<8hex>` — cross-SDK contract with `format_record_id_for_event` per `rules/event-payload-classification.md` §2). Regression test: `tests/unit/test_issue_614_tenant_id_no_raw_leak.py` (11 tests, source + behavioral + symlink-rejection).
- **SHA-256 → BLAKE2b sweep across `kaizen.llm.*`** (#617). Five credential-adjacent call sites migrated from `hashlib.sha256` to `kailash.utils.url_credentials.fingerprint_secret` (BLAKE2b) — closes CodeQL `py/weak-sensitive-data-hashing` consistently across the package and eliminates intent-drift between "BLAKE2b here / SHA-256 there". Sites: `kaizen/llm/auth/bearer.py::ApiKey.__init__`, `kaizen/llm/errors.py::_fingerprint`, `kaizen/llm/presets.py::_fingerprint`, `kaizen/llm/from_env.py::_fingerprint_selector`, `kaizen/llm/auth/gcp.py::CachedToken.__post_init__`. Regression test: `tests/unit/test_issue_617_fingerprint_sweep.py` (15 tests, source + direct-call-per-site + docstring-enhancement).

### Changed

- **`fingerprint_secret` docstring** (#617 MEDIUM-2) — added collision-stability + per-tenant-uniqueness + not-a-secret caveats at `src/kailash/utils/url_credentials.py`. Fingerprints ARE collision-stable across installs (intentional — enables cross-node trace correlation) and MUST NOT be treated as per-tenant-unique identifiers or as secrets.

## [2.12.2] — 2026-04-24 — Cyclic-import refactor (issue #612)

### Changed

- **CodeQL `py/unsafe-cyclic-import` hardening** — extracted `kaizen.signatures._types` to break the `signatures/core.py` ↔ `signatures/enterprise.py` static cycle. `SignatureCompositionProtocol` (new) captures the structural shape `core` needs (`.signatures` attribute) without importing `enterprise`; concrete `SignatureComposition` in `enterprise.py` satisfies the Protocol structurally. The protocol is `@runtime_checkable` for static-analyzer compatibility but the canonical runtime check in `core.py` remains `hasattr(sig, "signatures")` — NOT isinstance against the Protocol. Docstring now pins the discouragement against `isinstance(x, SignatureCompositionProtocol)` in security-sensitive paths per sec-review on PR #616.
- **Regression invariant** — new `tests/regression/test_issue_612_protocol_isinstance_invariant.py` greps production trees for `isinstance(..., *Protocol)` and fails loudly; prevents a future session from swapping a concrete admission check (`isinstance(db, DataFlow)`) to a Protocol-based one.

## [2.12.1] — 2026-04-24 — Security patch (issue #613)

### Changed

- **`kaizen.llm.auth.azure` correlation fingerprint** (`py/weak-sensitive-data-hashing`) — migrated `hashlib.sha256(api_key)` to `kailash.utils.url_credentials.fingerprint_secret(api_key)` (BLAKE2b, 8-char) at two sites (`CachedToken.from_raw` line 84, `AzureEntra.__init__` line 181). The value is NOT used for verification — only grep-able correlation in `__repr__` / log lines — so BLAKE2b is architecturally correct AND satisfies the CodeQL scanner. No migration required; neither fingerprint is persisted. Same-class sibling fix in kailash-mcp 0.2.9 per `rules/agents.md` fix-immediately rule.

## [2.12.0] — 2026-04-23 — ML integration (W32.a, kailash-ml wave)

### Why

Kaizen agent runs and kailash-ml training runs currently flow telemetry to
two separate observability surfaces — the Kaizen `TraceExporter` sink and
the kailash-ml `ExperimentTracker`. Researchers running mixed workflows
("train classical RF + use RAG agent for feature engineering + fine-tune
LLM reranker") see two dashboards instead of one. This release unifies
the surfaces: every Kaizen diagnostic adapter auto-emits to the ambient
`km.track()` run when present, a shared `SQLiteSink` writes agent traces
into the same `~/.kailash_ml/ml.db` store `ExperimentTracker` uses, and
the `CostDelta` wire format is migrated to integer microdollars so
Kaizen / PACT / AutoML cost flows share one numeric contract.

Agent tool-set construction gains a discovery-driven entry point
(`kaizen.ml.discover_ml_tools` + `kaizen.ml.engine_info`) so ML-aware
agents pick up new engines at runtime without hardcoded imports —
spec `kaizen-ml-integration.md §2.4.5` blocks the direct-import pattern
as a `rules/specs-authority.md §5b` drift violation.

### Added

- `kaizen.ml` module — public facade for every Kaizen↔kailash-ml
  integration point (spec `kaizen-ml-integration.md §1.1`):
  - `CostDelta` / `CostDeltaError` — cross-SDK microdollar wire format
    with `to_dict` / `from_dict` / `from_usd` helpers. Rejects NaN, Inf,
    and negative USD at the financial-field gate.
  - `SQLiteSink` / `SQLiteSinkError` / `default_ml_db_path` /
    `VALID_AGENT_RUN_STATUSES` — durable `TraceExporter` sink writing
    `_kml_agent_runs` + `_kml_agent_events` to the canonical
    `~/.kailash_ml/ml.db` store. N4 canonical fingerprint parity with
    kailash-rs v3.17.1+.
  - `resolve_active_tracker` / `emit_metric` / `emit_param` /
    `emit_artifact` / `is_emit_rank_0` — tracker-bridge helpers used
    by every diagnostic adapter's auto-emission path. Rank-0-only
    gate for distributed-training parity with `DLDiagnostics`.
  - `discover_ml_tools` / `engine_info` / `MLEngineDescriptor` /
    `MLRegistryUnavailableError` / `MLToolDiscoveryError` —
    discovery-driven agent tool-set construction routed through
    `km.engine_info()` / `km.list_engines()` (spec §2.4).
- `tracker=Optional[ExperimentRun]` kwarg on every Kaizen diagnostic
  adapter:
  - `AgentDiagnostics` (`kaizen.observability.agent_diagnostics`)
  - `LLMDiagnostics` (`kaizen.judges.llm_diagnostics`)
  - `InterpretabilityDiagnostics` (`kaizen.interpretability.core`)
- Auto-emission from every `record_*` / `track_*` event-capture method
  when an ambient tracker is active — NO opt-in flag (spec §1.1 item 2).
  Metric prefixes locked: `agent.*`, `llm.*`, `interp.*` (spec §3.2).

### Changed

- `AgentDiagnostics.record` / `.record_async` now route captured events
  through `_auto_emit` before returning. Behavior when no tracker is
  present is unchanged.
- `LLMDiagnostics.llm_as_judge` / `.faithfulness` / `.self_consistency`
  / `.refusal_calibrator` emit scalar metrics to the ambient tracker
  whenever one resolves at call time.
- `InterpretabilityDiagnostics.attention_heatmap` / `.logit_lens` /
  `.probe` emit scalar metrics to the ambient tracker whenever one
  resolves at call time.

### Related specs

- `specs/kaizen-ml-integration.md` — authoritative spec.
- `specs/kaizen-observability.md` — TraceExporter + AgentDiagnostics
  core (unchanged in shape).

### Related issues

- Implements W32 sub-shard 32a per
  `workspaces/kailash-ml-audit/todos/active/W32-kaizen-align-pact-integrations.md`.

## [2.11.0] — 2026-04-21 — LLM deployment four-axis abstraction (#498)

### Why

Enterprise LLM deployments cannot be expressed by a single provider-name string. Bedrock-Claude is Anthropic's wire protocol with AWS SigV4 auth against a Bedrock endpoint under a Bedrock-specific model grammar; Vertex-Claude is the same wire protocol with GCP OAuth2 auth against a Vertex endpoint under a Vertex-specific model grammar; Azure-OpenAI is OpenAI's wire protocol with Azure Entra auth and pinned api-version. Every new foundation-model host that lands as a per-provider `kaizen.providers.registry.*` class forks the adapter surface further. This release decomposes the LLM call into four orthogonal axes (wire × auth × endpoint × grammar) so each new host becomes a ≤10-LOC preset instead of a full adapter. Cross-SDK parity with kailash-rs#406 is enforced by a shared parity suite (see `packages/kailash-kaizen/tests/cross_sdk_parity/`).

### Added

- `LlmClient.from_deployment(deployment)` + `LlmClient.from_env()` — four-axis LLM deployment abstraction (ADR-0001).
- `LlmDeployment` frozen Pydantic model composing `WireProtocol` + `Endpoint` + `AuthStrategy` + `ModelGrammar` + defaults.
- **24 presets** (cross-SDK parity with kailash-rs): `openai`, `anthropic`, `google`, `cohere`, `mistral`, `perplexity`, `huggingface`, `ollama`, `docker_model_runner`, `groq`, `together`, `fireworks`, `openrouter`, `deepseek`, `lm_studio`, `llama_cpp`, `bedrock_claude`, `bedrock_llama`, `bedrock_titan`, `bedrock_mistral`, `bedrock_cohere`, `vertex_claude`, `vertex_gemini`, `azure_openai`.
- Auth strategies: `ApiKeyBearer`, `StaticNone`, `AwsBearerToken`, `AwsSigV4`, `GcpOauth`, `AzureEntra` (with three mutually-exclusive variants: api-key, workload-identity, managed-identity).
- `LlmClient.from_env()` three-tier precedence: `KAILASH_LLM_DEPLOYMENT` URI > `KAILASH_LLM_PROVIDER` selector > legacy per-provider keys (OpenAI > Azure > Anthropic > Google). Never falls back to mock.
- URI schemes with strict per-scheme regex validation: `bedrock://{region}/{model}`, `vertex://{project}/{region}/{model}`, `azure://{resource}/{deployment}?api-version=…`, `openai-compat://{host}/{model}`.
- Plugin hook `register_preset(name, factory)` with regex-validated name gate (`^[a-z][a-z0-9_]{0,31}$`) for third-party preset extension.
- `LlmHttpClient` — only HTTP client constructor path for LLM calls; grep-auditable. Emits structured log fields `deployment_preset`, `auth_strategy_kind`, `endpoint_host`, `request_id`, `latency_ms`, `method`, `status_code`, `exception_class`.
- `SafeDnsResolver` — post-connect peer-IP revalidation to close the DNS-rebinding window on every LLM HTTP call.
- `check_url(url)` SSRF guard — structural gate at `Endpoint.from_url` rejecting private IPs, loopback, link-local, and non-HTTPS schemes before the endpoint is finalized.
- `BedrockClaudeGrammar`, `BedrockLlamaGrammar`, `BedrockTitanGrammar`, `BedrockMistralGrammar`, `BedrockCohereGrammar`, `VertexClaudeGrammar`, `VertexGeminiGrammar`, `AzureOpenAIGrammar`.
- Cross-SDK parity suite at `packages/kailash-kaizen/tests/cross_sdk_parity/` — 32 tests asserting preset names, from_env precedence, observability field names, and error taxonomy match Rust byte-for-byte.
- Authoritative spec `specs/kaizen-llm-deployments.md` (238 LOC) and migration guide `docs/migration/llm-deployments-v2.md`.
- Optional extras: `kailash-kaizen[bedrock]` (botocore for SigV4), `[vertex]` (google-auth), `[azure]` (azure-identity for workload/managed variants). API-key-only Azure usage does not require `[azure]`.

### Security

- `ApiKey` newtype wraps `SecretStr`. No `__eq__` / `__hash__`; only `ApiKey.constant_time_eq(other)` via `hmac.compare_digest`. Eliminates timing side-channels in credential comparison.
- Every auth class `__repr__` emits `auth_strategy_kind()` + an 8-hex-char SHA-256 fingerprint — the raw credential never reaches a log line, a repr, or a pickled trace event.
- `AwsSigV4.sign_request` routes through `botocore.auth.SigV4Auth`. Inlined `hmac.new` signing is grep-blocked in `packages/kailash-kaizen/src/kaizen/llm/auth/aws.py`.
- `AwsBearerToken` and `AwsSigV4` enforce a region allowlist at construction time (`BEDROCK_SUPPORTED_REGIONS`). No default `AWS_REGION`.
- `ResolvedModel.with_extra_header` deny-lists 7 forbidden header names (`authorization`, `host`, `cookie`, `x-amz-security-token`, `x-api-key`, `x-goog-api-key`, `anthropic-version`) — prevents callers from overriding the deployment's auth or routing layer.
- `ModelGrammar.resolve` validates `caller_model` against `^[a-zA-Z0-9._:/@-]{1,256}$` before any parsing or URL interpolation.
- `LlmDeployment.mock()` is gated behind `KAILASH_TEST_MODE=1` OR the optional `[test-utils]` extra. `LlmClient.from_env()` NEVER returns a mock deployment — empty env raises `NoKeysConfigured`.
- `GcpOauth` and `AzureEntra` token caches use `asyncio.Lock` for single-flight refresh (no thundering herd on expiry).
- `Endpoint` is a frozen Pydantic model with `extra='forbid'`; side-door writes after construction are rejected at type level.

### Changed

- `kaizen.providers.registry.*` and `kaizen.config.providers.*` now route internally through the preset layer. Public API unchanged; no import breakage.

### Deprecated

- `kaizen.providers.registry.get_provider(name)` — preserved through v2.x; v3.0 earliest removal (≥ 18 months coexistence). Prefer `LlmClient.from_deployment(LlmDeployment.<preset>())`. See `docs/migration/llm-deployments-v2.md` for the full symbol-by-symbol mapping. No deprecation warnings in this release; deprecation-window announcement will precede removal.

### Migration Notes

Zero breaking changes. Legacy code paths continue to work unchanged; every `OpenAIProvider`, `AnthropicProvider`, etc. remains importable and functionally identical. When BOTH the new deployment-tier env vars (URI or selector) AND legacy per-provider keys are set, a single `WARNING llm_client.migration.legacy_and_deployment_both_configured` is emitted and the deployment path wins. `tests/regression/test_legacy_key_does_not_leak_into_deployment_path` enforces no credential cross-contamination.

## [2.10.1] — 2026-04-21 — Security patch on kaizen.observability (PR #587 security-reviewer feedback)

### Security

- **C2 (HIGH) — Tier 2 security coverage added.** Three new assertions in the AgentDiagnostics wiring test exercise classified-PK redaction via `payload_hash`, tenant-id scrub on WARN+ log records, and vendor-SDK brand non-leakage in serialized TraceEvent output. Closes `rules/testing.md` audit-mode MUST "Verify security mitigations have tests" for the spec's § Security Threats subsection.
- **H1 (HIGH) — Tenant-id hashed before INFO / WARN emission.** Raw `tenant_id` on WARN+ log lines bled schema-level identifiers into broader-audience log aggregators (Datadog, Splunk, CloudWatch). All five `TraceExporter` log sites plus the two `AgentDiagnostics` log sites now route `tenant_id` through a new `_hash_tenant_id()` helper producing the cross-SDK `sha256:<8-hex>` prefix form (same contract as `payload_hash` per `rules/event-payload-classification.md` §2). Forensic correlation across Python + Rust streams remains stable; log-aggregator enumeration of tenant IDs is no longer possible. Enforces `rules/observability.md` §8 + `rules/tenant-isolation.md` §4.
- **H2 (HIGH) — `JsonlSink` path resolve + `O_NOFOLLOW` symlink refusal.** The original `JsonlSink.__init__` used `Path(path)` verbatim without resolving traversal or applying `O_NOFOLLOW`, so an attacker-planted symlink at the destination silently redirected the trace stream. Fix: `__init__` resolves via `expanduser().resolve(strict=False)` (normalizes `..` segments); `__call__` opens via `os.open(str(path), O_WRONLY|O_CREAT|O_APPEND|O_NOFOLLOW, 0o600)` on POSIX — symlink at destination raises `OSError` instead of being followed. File-mode bits are `0o600` (owner-only). `mode` validation rejects anything but `"a"` or `"w"`. Docstring documents that callers MUST pre-validate tenant-derived paths against an allowlist. Four regression tests at `tests/regression/test_jsonl_sink_path_safety.py`.
- **M1 (MED) — Async sink tasks retained against GC.** `TraceExporter._run_async` used `loop.create_task(awaitable)` without retaining the Task; GC firing mid-coroutine silently cancelled the sink write and lost the trace event. Fix: new `self._pending_tasks: set[asyncio.Task]` on `__init__`; every scheduled task is added + a done-callback discards on completion (bounded retention = "currently in-flight tasks only"). New `async aclose()` awaits outstanding tasks via `asyncio.gather(return_exceptions=True)`; exceptions are WARN-logged not propagated. Three Tier 1 tests cover retention, exception tolerance, and empty-exporter fast path.

No changes to the public API shape beyond the additive `TraceExporter.aclose()` method; the existing `export()` / `export_async()` / sink signatures are unchanged. No breaking changes for consumers.

## [2.10.0] — 2026-04-21 — AgentDiagnostics + TraceExporter → kaizen.observability (#567 PR#6 of 7)

### Added

- **`kaizen.observability.AgentDiagnostics`** — concrete Kaizen-side adapter satisfying the cross-SDK `kailash.diagnostics.protocols.Diagnostic` Protocol. Context-managed agent-run session that captures `TraceEvent` records and produces a `report()` rollup (counts by `event_type`, total cost in integer microdollars, p50/p95 duration, error rate, errored-export count). Signature-free — pure data aggregator; outside `rules/agent-reasoning.md` scope.
- **`kaizen.observability.TraceExporter`** — single-filter-point sink adapter for `TraceEvent` records. Every event stamped with the cross-SDK-locked SHA-256 fingerprint from `kailash.diagnostics.protocols.compute_trace_event_fingerprint` (byte-identical with kailash-rs#468 / v3.17.1+, commit `e29d0bad`). Sinks: `NoOpSink`, `JsonlSink` (append-only JSONL with thread-safe writes), `CallableSink` (sync or async user-supplied callable). No third-party commercial-SDK imports anywhere in the surface per `rules/independence.md`.
- **`BaseAgent.attach_trace_exporter(exporter)` + `BaseAgent.trace_exporter` property** — production hot-path wiring of the exporter. `AgentLoop.run_sync` and `run_async` emit `agent.run.start` and `agent.run.end` TraceEvents through the attached exporter, threading `parent_event_id` from start → end and stamping `duration_ms` + `status`. Fire-and-forget: exporter failures WARN-log and continue so the agent hot path never breaks because a trace sink failed. Closes `rules/orphan-detection.md` §1 for `kaizen.observability`.
- **`kaizen.observability.AgentDiagnosticsReport`** — frozen dataclass shape returned by `AgentDiagnostics.report_dataclass()`; `.to_dict()` matches the `Diagnostic` Protocol's dict-shape contract.
- **`specs/kaizen-observability.md`** — authoritative spec documenting the cross-SDK fingerprint canonicalization contract, BaseAgent wiring surface, tenant-isolation and classification discipline (payload_hash `"sha256:<8-hex>"` per `rules/event-payload-classification.md` §2), security threats subsection, Tier 1 + Tier 2 testing contract, and MLFP attribution history.
- **`specs/diagnostics-catalog.md`** — catalog indexing every `Diagnostic` adapter (`DLDiagnostics`, `RAGDiagnostics`, `AlignmentDiagnostics`, `InterpretabilityDiagnostics`, `LLMJudge` / `LLMDiagnostics`, `AgentDiagnostics`, `GovernanceEngine` extensions) with its Tier 2 wiring-test file name (grep-able per `rules/facade-manager-detection.md` §2), medical-metaphor regression gate, and the additive extension flow for an 8th diagnostic.

### Tests

- **`packages/kailash-kaizen/tests/integration/observability/test_agent_diagnostics_wiring.py`** — 4 Tier 2 tests exercising a real `BaseAgent` + attached `TraceExporter`; asserts start + end events fire via `AgentLoop`, `run_id` stability, `parent_event_id` threading, fingerprint parity with the canonical helper, cost rollup as int microdollars, and short-circuit behaviour when `attach_trace_exporter(None)`.
- **`packages/kailash-kaizen/tests/unit/observability/test_trace_exporter_fingerprint.py`** — 15 Tier 1 tests covering determinism, hex shape, per-field sensitivity of the 6 mandatory fields, canonicalization form (sort-keys, compact separators, `+00:00`, no `Z`), Enum string serialization, `cost_microdollars` MUST-be-int invariant (rejects float, negative, bool), re-export parity, and bounded-counter contract (no unbounded `_events` buffer).

### Cross-SDK Parity

- **kailash-rs#468** (v3.17.1+, commit `e29d0bad`) — the Rust-side `TraceEvent` + `compute_trace_event_fingerprint` pair; 4 round-trip tests green. The Python-side fingerprint contract in this release is byte-identical with the Rust side.
- **kailash-rs#497** — Rust TraceExporter Kaizen-rs wiring tracker; this Python PR integrates against the byte-identical parity locked in kailash-rs#468.

## [2.9.0] — 2026-04-20 — LLMDiagnostics + JudgeCallable → kaizen.judges + kaizen.evaluation split (#567 PR#5 of 7)

### Added

- **`kaizen.judges.LLMJudge`** — concrete Kaizen-side implementation of the cross-SDK `kailash.diagnostics.protocols.JudgeCallable` Protocol (async `__call__(JudgeInput) -> JudgeResult`). Wraps `kaizen_agents.Delegate` so every LLM call routes through the framework's cost tracker + env-sourced model resolution per `rules/framework-first.md` + `rules/env-models.md`. Raw `openai.chat.completions.create` / `litellm.completion` are BLOCKED (`rules/zero-tolerance.md` Rule 4). Structured `Signature(InputField/OutputField)` drives scoring — no regex on LLM output per `rules/agent-reasoning.md` MUST Rule 3.
- **`kaizen.judges.LLMDiagnostics`** — context-managed Diagnostic session satisfying `kailash.diagnostics.protocols.Diagnostic`. Aggregates `llm_as_judge()` / `faithfulness()` / `self_consistency()` / `refusal_calibrator()` into a single `report()` dict with severity banding, polars DataFrame accessors (`judge_df` / `faithfulness_df`), and plotly dashboard (`plot_output_dashboard()`).
- **`kaizen.judges.FaithfulnessJudge`**, **`kaizen.judges.SelfConsistencyJudge`**, **`kaizen.judges.RefusalCalibrator`** — rubric-bound judge wrappers. `SelfConsistencyJudge` shares one `CostTracker` across N independent scorings and surfaces variance statistics (`SelfConsistencyReport`).
- **`kaizen.judges.JudgeBudgetExhaustedError`** — typed error when the judge's integer-microdollar `budget_cap` is hit mid-evaluation. Position-swap bias mitigation plus budget enforcement are routed through a shared `CostTracker` per `rules/tenant-isolation.md` when a `tenant_id` is present.
- **`kaizen.evaluation.ROUGE`**, **`kaizen.evaluation.BLEU`**, **`kaizen.evaluation.BERTScore`** — pure-algorithmic NLP metrics as a **separate namespace** from `kaizen.judges`. Split intentional: judges carry LLM / cost / budget surface; evaluation is lightweight string math. Each metric raises a loud, actionable `ImportError` naming the `[evaluation]` extra if the underlying library is absent per `rules/dependencies.md` "Optional Extras with Loud Failure".
- **New `[judges]` extra**: `bert-score>=0.3.13` + `rouge-score>=0.1.2` + `sacrebleu>=2.4`. Covers the judge runtime's algorithmic fallbacks.
- **New `[evaluation]` extra**: same deps, narrower scope — for users who only want reference-comparison metrics without the judge / cost / budget surface.
- **`specs/kaizen-judges.md`** and **`specs/kaizen-evaluation.md`** — new spec files documenting Protocol conformance contract, public API, cost-budget discipline, position-swap bias mitigation mechanics, security threats, Tier 1 + Tier 2 testing contract, MLFP attribution history. Both referenced from `specs/_index.md`.

### Security

- **No raw openai / litellm imports in `kaizen.judges` / `kaizen.evaluation`** — every LLM call routes through `kaizen_agents.Delegate`.
- **No regex on LLM output for winner selection** — judge verdicts come from structured `OutputField` parsing via Signature. `_parse_score` regex heuristics from the MLFP donor source were replaced with Signature-based extraction.
- **Budget tracking in integer microdollars** — `CostTracker` is the single source of truth; raw USD floats are not accumulated. Cross-SDK parity with `pact.costs.CostTracker`.
- **Typed error on budget exhaustion** — `JudgeBudgetExhaustedError` is raised loud per `rules/zero-tolerance.md` Rule 3 rather than silently returning partial-result dicts that look successful.

### Attribution

- Portions of `LLMJudge` / `LLMDiagnostics` / `FaithfulnessJudge` / `SelfConsistencyJudge` / `RefusalCalibrator` originated in the MLFP diagnostics helpers (`shared/mlfp06/diagnostics/output.py` + `_judges.py`, Apache 2.0) and were re-authored for the Kailash ecosystem with medical-metaphor cleanup, framework-first routing through Delegate, structured Signature scoring, and `run_id` correlation. MLFP donation history recorded in the root `NOTICE` file per Apache-2.0 §4(d) (blocker B4 shipped in #569).

## [2.8.0] — 2026-04-20 — InterpretabilityDiagnostics adapter for open-weight LLM analysis (#567 PR#4 of 7)

### Added

- **`kaizen.interpretability.InterpretabilityDiagnostics` adapter (#567 PR#4 of 7)**: post-hoc interpretability session for local open-weight language models (Llama / Gemma / Phi / Mistral). Satisfies the cross-SDK `kailash.diagnostics.protocols.Diagnostic` Protocol (`run_id` + `__enter__` + `__exit__` + `report()`), so `isinstance(diag, Diagnostic)` holds at runtime for downstream telemetry pipelines. Four analyses expose attention heatmaps (plotly), logit-lens top-`k` predictions per layer (polars DataFrame), scikit-learn linear probes on last-token hidden states, and optional Gemma-Scope SAE feature activations via `sae-lens`. Every per-analysis buffer uses `deque(maxlen=window)` for bounded-memory discipline; `close()` on context exit releases the model and clears CUDA / MPS caches.
- **New `[interpretability]` extra**: `transformers>=4.40,<5.0` + `sae-lens>=3.0`. Plotting methods raise a loud `ImportError` naming the extra if plotly / matplotlib is absent per `rules/dependencies.md` "Optional Extras with Loud Failure". Base-install construction + API-only refusal paths run without the extra installed.
- **`kaizen.interpretability` facade module**: public surface `from kaizen.interpretability import InterpretabilityDiagnostics`. Tier 2 wiring test asserts facade import per `rules/orphan-detection.md` §1.
- **`specs/kaizen-interpretability.md`** — new spec file documenting Protocol conformance contract, public API, VRAM / memory budget guidance, 6 security threats with mitigations, Tier 1 + Tier 2 testing contract, MLFP attribution history. Referenced from `specs/_index.md`.

### Security

- **Local-files-only default** — `from_pretrained(local_files_only=True)` is the default so a diagnostic call NEVER silently downloads multi-GB weights over the network. Operators pass `allow_download=True` explicitly to opt in.
- **No hardcoded HF token** — auth token read from `HF_TOKEN` / `HUGGINGFACE_TOKEN` env vars via `os.environ.get` only.
- **API-only refusal** — `gpt-*` / `o1-*` / `o3-*` / `o4-*` / `claude-*` / `gemini-*` / `deepseek-*` model prefixes are refused with a canonical `{"mode": "not_applicable"}` payload rather than fabricating interpretability readings. Honest failure per `rules/zero-tolerance.md` Rule 2.
- **No raw prompt text in logs** — structured logs carry `interp_run_id` correlation IDs only; `interp_*`-prefixed fields avoid the LogRecord attribute-collision hazard documented in `rules/observability.md` MUST Rule 9.

## [2.7.5] - 2026-04-19 — LlmClient.embed() + trust migration fix + Python 3.14 compatibility (#462 #499 #477)

### Added

- **`LlmClient.embed()` for OpenAI + Ollama (#462, PR #502)**: `LlmClient.embed(texts, *, model)` exposes a first-class embedding API on the existing `LlmClient` surface. Supports OpenAI (`text-embedding-3-small`, `text-embedding-3-large`, `text-embedding-ada-002`) and Ollama (`nomic-embed-text` and any Ollama-hosted embedding model). Returns a `List[List[float]]` consistent with OpenAI's embedding response shape.

### Fixed

- **LLM endpoint trust migration identifier validation (#499, PR #504)**: `kaizen.llm.migration` used f-string interpolation for identifier names in log and error message paths. All identifier-containing paths now route through `_validate_identifier()` before use.
- **Python 3.14 (PEP 649 / PEP 749) silently broke every class-based `Signature`.**

- **Python 3.14 (PEP 649 / PEP 749) silently broke every class-based `Signature`.** `SignatureMeta.__new__` read `namespace.get("__annotations__", {})` to discover `InputField` / `OutputField` declarations. On 3.14 the compiler emits `namespace["__annotate__"]` (a lazy callable) instead of populating `__annotations__` directly, so the metaclass saw `{}`, produced signatures with zero fields, and every dependent `BaseAgent` refused to construct. The fix routes the read through the new shared helper `kailash.utils.annotations.get_namespace_annotations`, which evaluates `__annotate__` (preferring `Format.VALUE`, falling back to `Format.FORWARDREF` on unresolved names) on 3.14 and reads the eager dict on 3.13 and earlier.
- **`kaizen.deploy.introspect.build_card_for`** previously called `getattr(signature_cls, "__annotations__", {})`, which can raise `NameError` instead of returning a default on 3.14 if the signature has any string forward reference. Replaced with `kailash.utils.annotations.get_class_annotations(signature_cls)` so every annotation read in the SDK flows through the one-place handler for 3.13/3.14 differences.
- **`type_introspector`, `core/autonomy/state/types`, `memory/enterprise`, `strategies/single_shot`, `strategies/multi_cycle`** all updated to read class annotations through `kailash.utils.annotations.get_class_annotations`, so PEP 649 forward references are surfaced safely instead of crashing the introspection path.

### Pyright

- `signatures/core.py` cleanup (touched while applying the 3.14 fix): `description: str = None` → `Optional[str] = None`; dropped `ClassVar[…]` on the `_signature_*` attributes that get per-instance overrides; declared `_outputs_list: List[Union[str, List[str]]]` at class scope so the multi-output return type holds; added a `TYPE_CHECKING` import for `SignatureComposition` (defined in `signatures.enterprise`); added narrowing casts at dispatchers where `hasattr` already proves the discriminator.

## [2.7.3] - 2026-04-12 — Post-Convergence Security Hardening

### Security

- **SQL injection fix in `security/audit.py` `query_events()`**: the prior implementation built a raw f-string `WHERE` clause from caller-supplied `event_type` and `agent_id` parameters. These arguments could contain SQL metacharacters, enabling injection via crafted event type strings. Fixed to use parameterized queries; identifier segments validated with `re.match` before interpolation.
- **Audit forwarding with `exc_info=True`**: `logger.error()` calls in `core/autonomy/observability/audit.py` and `security/audit.py` now include `exc_info=True`, ensuring stack traces appear in the log pipeline rather than just the message string. Previously, exceptions were swallowed silently on the audit forwarding path.

### Changed

- **Strategy deprecation warnings**: `async_single_shot.py` and `single_shot.py` now emit `DeprecationWarning` when invoked, directing users to `DelegateEngine` as the canonical async strategy. The single-shot strategies remain functional but are officially deprecated.

## [2.3.0] - 2026-03-25

### Changed

- **Structural split**: Moved ~44K lines of Layer 2 (LLM-dependent) engine code to kaizen-agents package
- Moved modules: agents/, orchestration/ (→patterns/), journey/, api/, workflows/, coordination/, integrations/dataflow/, runtime/adapters/, research patterns
- `from kaizen import Agent` now conditionally resolves to async Agent from kaizen-agents (fallback: CoreAgent)
- kaizen-agents added to root `[kaizen]` optional dependency group

### Deprecated

- `kaizen.agent.Agent` (sync wrapper) — use `kaizen_agents.api.agent.Agent` (async) instead

### Removed

- `kaizen/agents/` — moved to kaizen-agents package
- `kaizen/orchestration/` — moved to kaizen-agents as `patterns/`
- `kaizen/journey/` — moved to kaizen-agents
- `kaizen/api/` — moved to kaizen-agents (canonical async Agent API)
- `kaizen/workflows/` — moved to kaizen-agents
- `kaizen/coordination/` — moved to kaizen-agents
- `kaizen/integrations/dataflow/` — moved to kaizen-agents
- `kaizen/runtime/adapters/` — moved to kaizen-agents as `runtime_adapters/`

## [2.2.0] - 2026-03-24

### LLM-First Autonomous Agents

All autonomous agents now default to MCP tool discovery enabled, and the framework enforces LLM-first reasoning as an absolute directive.

### Changed

- **ReActAgent**: `mcp_discovery_enabled` default changed from `False` to `True`
- **CodeGenerationAgent**: Added `mcp_enabled: bool = True` to config
- **RAGResearchAgent**: Added `mcp_enabled: bool = True` to config
- **SelfReflectionAgent**: Added `mcp_enabled: bool = True` to config (now classified as autonomous)
- Agent Classification updated: 4 autonomous agents (was 3), SelfReflectionAgent promoted

### Removed

- **ReActAgent.\_discover_mcp_tools()**: Removed no-op stub method. MCP discovery flows through `BaseAgent.discover_mcp_tools()` (the real async implementation)

### Fixed

- `test_memory_agent`: Fixed mock provider detection in execution test
- `test_http_transport`: Fixed `base_url` fixture scope conflict with pytest-base-url plugin
- `test_agent_execution_patterns_e2e`: Relaxed content assertions for mock provider compatibility

## [2.1.0] - 2026-03-22

### L3 Autonomy Primitives

Five deterministic SDK primitives enabling agents that spawn child agents, allocate constrained budgets, communicate through typed channels, and execute dynamic task graphs under PACT governance.

### Added

- **`kaizen.l3.envelope`** — EnvelopeTracker, EnvelopeSplitter, EnvelopeEnforcer (continuous budget tracking, ratio-based division, non-bypassable enforcement)
- **`kaizen.l3.context`** — ScopedContext, ScopeProjection, DataClassification (hierarchical context with projection-based access control and 5-level clearance)
- **`kaizen.l3.messaging`** — MessageChannel, MessageRouter, DeadLetterStore, 6 typed payloads (bounded async channels with priority ordering and 8-step routing validation)
- **`kaizen.l3.factory`** — AgentFactory, AgentInstanceRegistry, AgentSpec, AgentInstance (runtime agent spawning with 6-state lifecycle machine and cascade termination)
- **`kaizen.l3.plan`** — Plan DAG, PlanValidator, PlanExecutor, PlanModification (DAG task graphs with gradient-driven scheduling and 7 typed mutations)
- **`kaizen.agent_config`** — Optional `envelope` field for PACT constraint governance
- **`kaizen.composition.graph_utils`** — Generic cycle detection and topological ordering
- 868 new tests (581 unit + 240 security + 47 integration/E2E)

## [1.2.1] - 2026-02-22

### V4 Audit Hardening Patch

Post-release reliability hardening from V4 final audit.

### Fixed

- **FallbackRouter Error Truncation**: `get_error_summary()` now truncates error messages to 200 characters, matching `execute()` behavior
- **Hardcoded Model Removal**: `BaseAgent._execute_signature` model fallback uses `os.environ` only, no hardcoded `"gpt-4o"`
- **Timestamping Silent Swallows**: 3 bare `except: pass` blocks in RFC 3161 fallback chain replaced with `logger.debug()` calls
- **Stale Tests**: Updated timestamping tests that expected `NotImplementedError` from now-implemented RFC 3161 authority

### Test Results

- Kaizen: 128 fallback-related tests passed, 60 timestamping tests passed

## [1.2.0] - 2026-02-21

### Quality Milestone Release - V4 Audit Cleared

This release completes 4 rounds of production quality audits (V1-V4) with all Kaizen-specific gaps remediated.

### Added

- **FallbackRouter Safety**: `on_fallback` callback fires before each fallback (raise `FallbackRejectedError` to block), WARNING-level logging on every fallback, model capability validation
- **MCP Session Methods**: `discover_mcp_resources()`, `read_mcp_resource()`, `discover_mcp_prompts()`, `get_mcp_prompt()` wired and functional
- **RFC 3161 Timestamping**: Ed25519 local timestamp authority with clock drift detection and production warnings
- **AgentTeam Deprecation**: Proper `DeprecationWarning` with migration guidance to `OrchestrationRuntime`

### Changed

- **Model Fallback**: `BaseAgent._execute_signature` now reads model from `os.environ` instead of hardcoded `"gpt-4"` fallback
- **Error Truncation**: FallbackRouter truncates error messages to 200 chars to prevent log flooding

### Security

- No hardcoded model names in runtime code (all from environment variables)
- Cryptographically secure nonce generation via `secrets.token_hex(16)`
- V4 audit: 0 CRITICAL findings

### Test Results

- 385 unit tests passed (+1 pre-existing)

## [1.0.0] - 2026-01-25

### Added

#### Phase 7: Production Deployment & GA Release

**TODO-199: Performance Optimization**

- Performance benchmarks suite with 15 comprehensive tests
- Schema caching: ~4.6μs per operation
- Embedding caching: ~17.9μs per operation
- Parallel tool execution: 4.6x speedup over sequential
- Hook parallelization: 8.4x speedup over sequential

**TODO-200: Production Deployment Guides**

- Complete Docker deployment guide with multi-stage builds
- Kubernetes orchestration with health checks and auto-scaling
- Monitoring setup with Prometheus, Grafana, and Loki
- Security hardening documentation

**TODO-201: v1.0 GA Release Validation**

- Comprehensive test suite: 7,400+ unit tests, 226+ integration tests
- Docker image builds and runs successfully
- Fresh pip install verified (kailash-kaizen-1.0.0 installs cleanly)
- Security scan completed (4 documented unfixable vulnerabilities in dependencies)

### Changed

- Version bumped to 1.0.0 (GA release)
- `setup.py` version synchronized with `pyproject.toml` and `__init__.py`
- Semver validation regex updated to accept PEP 440 pre-release format
- HTTP transport tests updated for local development (`allow_insecure=True`)
- Rate limiter fixture converted to `@pytest_asyncio.fixture`

### Fixed

- **OrchestrationRuntime**: Removed incompatible `execution_timeout` parameter from AsyncLocalRuntime initialization
- **Governance datetime comparison**: Fixed offset-naive/aware datetime comparison in `timeout_pending_approvals()`
- **Planning agent response extraction**: Enhanced nested response parsing for Ollama models
- **Rate limiter async fixture**: Corrected decorator for pytest-asyncio compatibility
- **Missing dependencies**: Added motor (MongoDB async driver) and trio (async library)

### Security

- Security scan performed with pip-audit
- 4 remaining unfixable vulnerabilities documented:
  - ecdsa: No fix available (low severity)
  - mcp: Version pinned by kailash (acceptable risk)
  - protobuf: No fix version available (low severity)
  - py: Legacy package (acceptable risk)

---

## [1.0.0b1] - 2026-01-24

### Added

#### Phase 6: Autonomous Execution Layer (922+ tests)

Complete implementation of autonomous agent capabilities enabling Claude Code-level functionality.

**TODO-190: Native Tool System**

- `BaseTool`: Abstract base for all native tools with schema generation
- `NativeToolResult`: Standardized result format with success/error handling
- `KaizenToolRegistry`: Central registry with category-based registration
- `DangerLevel`: 5-level danger classification (SAFE, LOW, MEDIUM, HIGH, CRITICAL)
- 7 file tools: ReadFileTool, WriteFileTool, EditFileTool, GlobTool, GrepTool, ListDirectoryTool, FileExistsTool
- 2 search tools: WebSearchTool, WebFetchTool
- 1 bash tool: BashTool with sandboxing support

**TODO-191: Runtime Abstraction Layer**

- `RuntimeAdapter`: Abstract base class for runtime adapters
- `LocalKaizenAdapter`: Native Kaizen runtime for autonomous execution
- `RuntimeSelector`: Automatic adapter selection based on context
- Plugin system for custom runtime adapters

**TODO-192: LocalKaizenAdapter - TAOD Loop (371 tests)**

- Think → Act → Observe → Decide autonomous execution loop
- Tool call management with approval workflows
- Cycle detection and prevention
- Error recovery with automatic retry
- Execution metrics and performance tracking

**TODO-193: Memory Provider Interface (112 tests)**

- `MemoryProvider`: Abstract interface for memory backends
- `InMemoryProvider`: Default in-memory storage
- `HierarchicalMemory`: Hot/Warm/Cold tier system
- Memory search and retrieval with relevance scoring
- Configurable retention policies

**TODO-194: Multi-LLM Routing (145 tests)**

- `LLMRouter`: Intelligent routing across LLM providers
- `TaskAnalyzer`: Task complexity analysis for routing decisions
- `FallbackRouter`: Automatic failover on provider errors
- `RoutingRule`: Configurable routing policies
- Provider capability detection and matching

**TODO-195: Unified Agent API (217 tests)**

- `Agent`: Single class supporting all capability combinations
- `ExecutionMode`: SINGLE, MULTI, AUTONOMOUS modes
- `MemoryDepth`: STATELESS, SESSION, PERSISTENT, HIERARCHICAL
- `ToolAccess`: NONE, READ_ONLY, READ_WRITE, FULL
- `AgentResult`: Standardized execution results with tool call records
- `CapabilityPresets`: 9 pre-configured capability sets
- Progressive configuration from 2-line quickstart to expert mode

**TODO-196: External Runtime Adapters**

- Claude SDK adapter for Claude Code integration
- OpenAI adapter for GPT-based agents
- Extensible adapter architecture

#### Phase 6.5: Enterprise-App Enablement (530+ tests)

**TODO-202: Specialist System - ADR-013 (107 tests)**

- `SpecialistDefinition`: Type-safe specialist definitions
- `SkillDefinition`: Skill specifications with triggers
- `SpecialistRegistry`: Central registry with discovery
- Built-in specialists: sdk-navigator, pattern-expert, testing-specialist
- Plugin architecture for custom specialists

**TODO-203: Task/Skill Tools (132 tests)**

- `TaskTool`: Spawn subagent specialists
- `SkillTool`: Invoke reusable skills
- Background execution with TaskOutput retrieval
- Shared state management between tools

**TODO-204: Enterprise-App Streaming (291 tests)**

- 10 streaming event types for real-time progress
- `StreamingExecutor`: Async streaming execution
- Event buffering and batching
- WebSocket and SSE transport support

#### Phase 6.6: Claude Code Tool Parity (214 tests)

**TODO-207: Full Tool Parity with Claude Code**

- `TodoWriteTool`: Structured task list management
- `NotebookEditTool`: Jupyter notebook cell editing
- `AskUserQuestionTool`: Bidirectional user communication
- `EnterPlanModeTool`: Plan mode workflow entry
- `ExitPlanModeTool`: Plan mode with approval workflow
- `KillShellTool`: Background process termination
- `TaskOutputTool`: Background task output retrieval
- **19 total native tools** via KaizenToolRegistry
- `PlanModeManager`: Coordinated planning tool state
- `ProcessManager`: Background task tracking

**Documentation**

- Unified Agent API Guide: `docs/developers/05-unified-agent-api-guide.md`
- Claude Code Parity Tools Guide: `docs/developers/08-claude-code-parity-tools-guide.md`

### Changed

- Default version updated to 1.0.0b1 (beta release)
- `Agent` class now primary entry point (replaces `BaseAgent` for new code)
- Tool registry now supports 7 categories: file, bash, search, agent, interaction, planning, process

### Fixed

- Timeout error message format in AskUserQuestionTool (includes "timeout" keyword)
- Metadata passthrough in AskUserQuestionTool when no callback configured

---

## [0.8.0] - 2025-12-16

### Added

#### Enterprise Agent Trust Protocol (EATP)

Complete implementation of cryptographically verifiable trust chains for AI agents.

**Phase 1: Foundation & Single Agent Trust (Weeks 1-4)**

- `TrustLineageChain`: Complete trust chain data structure
- `GenesisRecord`: Cryptographic proof of agent authorization
- `CapabilityAttestation`: What agents are authorized to do
- `DelegationRecord`: Trust transfer between agents
- `ConstraintEnvelope`: Limits on agent behavior
- `AuditAnchor`: Tamper-proof action records
- `TrustOperations`: ESTABLISH, DELEGATE, VERIFY, AUDIT operations
- `PostgresTrustStore`: Persistent trust chain storage
- `OrganizationalAuthorityRegistry`: Authority lifecycle management
- `TrustKeyManager`: Ed25519 key management
- `TrustedAgent`: BaseAgent with automatic trust verification
- `TrustedSupervisorAgent`: Delegation to worker agents

**Phase 2: Multi-Agent Trust (Weeks 5-8)**

- `AgentRegistry`: Central registry for agent discovery
- `AgentHealthMonitor`: Background health monitoring
- `SecureChannel`: End-to-end encrypted messaging
- `MessageVerifier`: Multi-step message verification
- `InMemoryReplayProtection`: Replay attack prevention
- `TrustExecutionContext`: Trust state propagation
- `TrustPolicyEngine`: Policy-based trust evaluation
- `TrustAwareOrchestrationRuntime`: Trust-aware workflow execution

**Phase 3: Enterprise Features (Weeks 9-12)**

- `A2AService`: FastAPI A2A protocol service
- `AgentCardGenerator`: A2A Agent Card with trust extensions
- `JsonRpcHandler`: JSON-RPC 2.0 handler
- `A2AAuthenticator`: JWT-based authentication
- `EnterpriseSystemAgent` (ESA): Proxy for legacy systems
- `DatabaseESA`: SQL database ESA (PostgreSQL, MySQL, SQLite)
- `APIESA`: REST API ESA with OpenAPI support (see details below)
- `ESARegistry`: ESA discovery and management
- `TrustChainCache`: LRU cache with TTL (100x+ speedup)
- `CredentialRotationManager`: Periodic key rotation
- `TrustSecurityValidator`: Input validation and sanitization
- `SecureKeyStorage`: Encrypted key storage (Fernet)
- `TrustRateLimiter`: Per-authority rate limiting
- `SecurityAuditLogger`: Security event logging

**APIESA - REST API Enterprise System Agent (2025-12-15)**

Production-ready ESA for trust-aware REST API integration:

_Core Features:_

- OpenAPI/Swagger spec parsing with automatic capability generation
- HTTP operations: GET, POST, PUT, DELETE, PATCH with full async support
- Rate limiting: per-second, per-minute, per-hour with sliding window
- Request/response audit logging with circular buffer (last 1000 requests)
- Flexible authentication: Bearer tokens, API keys, custom headers

_Trust Integration:_

- Full `EnterpriseSystemAgent` inheritance
- `discover_capabilities()`, `execute_operation()`, `validate_connection()`
- Trust establishment and capability delegation support

_Error Handling:_

- Timeout, request, and connection error handling
- Missing parameter validation
- Rate limit exceeded errors with detailed context

_Documentation:_

- API Reference: `docs/trust/esa/APIESA.md`
- Quick Reference: `docs/trust/esa/APIESA_QUICK_REFERENCE.md`
- Example: `examples/trust/esa_api_example.py`
- 33 unit tests in `tests/unit/trust/esa/test_apiesa.py`

**Performance Targets Met**

- VERIFY QUICK: <1ms (target <5ms)
- VERIFY STANDARD: <5ms (target <50ms)
- VERIFY FULL: <50ms (target <100ms)
- Cache hit: <0.5ms (100x+ speedup)

**Testing**

- 691 total tests (548 unit + 143 integration)
- NO MOCKING policy for Tier 2-3 tests
- Real PostgreSQL infrastructure testing

**Documentation**

- API Reference: `docs/api/trust.md`
- Migration Guide: `docs/guides/eatp-migration-guide.md`
- Security Best Practices: `docs/guides/eatp-security-best-practices.md`
- 10 usage examples in `examples/trust/`

### Changed

- `BaseAgent` now supports optional trust verification via `TrustedAgent` subclass
- Orchestration runtime can be trust-aware via `TrustAwareOrchestrationRuntime`

### Fixed

- SecurityEventType enum now includes rotation events
- APIESA capability name generation fixed for path parameters
- Integration tests now use real implementations (NO MOCKING)

---

## [0.1.x] - Previous Releases

See individual release notes for earlier versions.

---

## Migration

To upgrade from 0.7.x to 0.8.0, see the [EATP Migration Guide](docs/guides/eatp-migration-guide.md).

Key changes:

- New `kaizen.trust` module with all EATP components
- Optional trust verification for existing agents
- Backward compatible - existing `BaseAgent` code works unchanged

## Links

- [Documentation](https://docs.kailash.dev/kaizen)
- [GitHub](https://github.com/terrene-foundation/kailash-py)
- [Issues](https://github.com/terrene-foundation/kailash-py/issues)
