# Implicit Coupling Analysis: Kaizen Provider Configuration

## 1. Executive Summary

Kaizen-py's provider configuration layer contains six interconnected implicit behaviors that silently transform, generate, or patch configuration as it flows from `BaseAgentConfig` to the LLM provider backends. These behaviors were designed as convenience features but have created a tightly coupled system where a change to any single implicit behavior cascades across 4-5 modules, producing bugs that are invisible until runtime API calls fail. Issues #254, #255, #256, and #257 are all symptoms of the same architectural root cause: the configuration pipeline performs undocumented transformations at multiple points, and no single module has full visibility into what the final configuration will be.

The kailash-rs SDK avoids all four bugs by design. It uses explicit configuration: users provide `base_url` and `api_version` as separate typed fields, structured output config is a dedicated type (not a dual-purpose dict), and there is no env-var guessing or URL-pattern regex detection. The Rust approach trades 2-3 lines of user-written config for complete predictability.

The refactor path is clear but non-trivial. Six implicit behaviors touch 14+ source files and have 40+ tests that depend on current auto-generation semantics. A phased approach -- starting with the highest-risk dual-purpose `provider_config` field and ending with the lowest-risk system prompt unification -- minimizes breakage while delivering incremental value at each step.

---

## 2. Implicit Behavior Catalog

### 2.1 Auto-Generation of `provider_config` (Structured Output)

**What it does automatically:**
When `provider_config` is `None` (the default) and the effective provider is in `["openai", "google", "gemini", "azure"]` and a signature is present, `WorkflowGenerator.generate_signature_workflow()` (lines 190-208) calls `create_structured_output_config()` to auto-generate a structured output configuration. For OpenAI without a custom prompt_generator, it generates `{"type": "json_schema", "json_schema": {..., "strict": True}}`. For Azure and other providers, or when a prompt_generator is present, it generates `{"type": "json_object"}` (strict=False).

**What coupling it creates:**

- `WorkflowGenerator` depends on `create_structured_output_config` (from `structured_output.py`)
- `WorkflowGenerator` must know which providers support structured output (hardcoded list at line 187)
- `WorkflowGenerator` must infer strict mode eligibility from `prompt_generator is None` (line 200-201)
- `LLMAgentNode` receives generated config without knowing it was auto-generated vs user-provided
- `SingleShotStrategy` and `AsyncSingleShotStrategy` must independently check for `json_object` type to append JSON instructions to user messages (lines 394-401 and 226-231 respectively)
- `SchemaFactory` reads `provider_config` to detect OpenAI strict mode, creating a third consumer of the same field

**How it fails:**

- **Issue #254:** Auto-generated `json_object` for Azure triggers Azure's requirement that "json" appear in messages, but the auto-generated system prompt does not contain "json" -- resulting in an API error.
- **Silent override:** If a user sets `provider_config` to `None` intending "no structured output", the auto-generation fills it in anyway, changing LLM behavior without the user's knowledge.
- **Strict mode misfire:** The heuristic `prompt_generator is None` as a proxy for "no tool calling" is fragile. A user who provides a plain prompt_generator (no tools) still gets `strict=False`.

**Explicit alternative (kailash-rs model):**
User provides structured output config explicitly as a separate `StructuredOutputConfig` type. If no config is provided, no structured output is used. The SDK does not guess.

```python
# Explicit model
config = BaseAgentConfig(
    structured_output=StructuredOutputConfig.json_schema(
        schema=QASignature.to_json_schema(),
        strict=True,
    ),
)
```

**Blast radius of changing it:**

- `WorkflowGenerator.generate_signature_workflow()` -- remove auto-generation block (lines 190-208)
- `test_workflow_generator_provider_config.py::test_empty_provider_config_gets_auto_generated_json_schema` -- test asserts auto-generation happens; must be rewritten
- All e2e tests that rely on implicit structured output (any test creating a BaseAgent with a signature and no explicit provider_config that expects JSON output) -- approximately 8-12 test files
- `SingleShotStrategy` and `AsyncSingleShotStrategy` JSON instruction injection may become unnecessary
- Documentation in `.claude/skills/04-kaizen/kaizen-structured-outputs.md` references auto-configuration

---

### 2.2 Dual-Purpose `provider_config` Field

**What it does automatically:**
`provider_config` in `BaseAgentConfig` (line 50 of config.py) is a single `Optional[Dict[str, Any]]` that serves two conflicting purposes:

1. **Structured output config:** `{"type": "json_schema", "json_schema": {...}}` or `{"type": "json_object"}`
2. **Provider-specific settings:** `{"api_version": "2025-04-01-preview"}` for Azure

`LLMAgentNode.execute()` (lines 756-766) attempts to disambiguate by checking for a `"type"` key: if present, treats as response_format; if absent, ignores it. This was the fix for issue #255.

**What coupling it creates:**

- `LLMAgentNode` must understand the semantics of `provider_config` to route it correctly
- `WorkflowGenerator` reads `provider_config` at two separate points (line 165 and line 483) for different purposes
- `SingleShotStrategy` and `AsyncSingleShotStrategy` also read `provider_config` to decide whether to inject JSON instructions
- `SchemaFactory._is_openai_strict_mode()` reads `provider_config` assuming it might contain a nested `response_format` key (line 114-115), which is a THIRD interpretation of the same field
- Azure-specific settings (api_version, deployment) have no canonical place to live

**How it fails:**

- **Issue #255:** User sets `provider_config={"api_version": "2025-04-01-preview"}` for Azure. LLMAgentNode (before the fix) blindly assigned this as `response_format`, causing `'Missing required parameter: response_format.type'`.
- **Semantic ambiguity:** A dict like `{"type": "json_schema", "api_version": "2025-04-01-preview"}` is valid structured output config but also contains Azure-specific keys. The current code treats the entire dict as response_format, discarding api_version.
- **SchemaFactory divergence:** `SchemaFactory` looks for `provider_config.response_format.type`, while `WorkflowGenerator` looks for `provider_config.type` directly -- two different shapes for the same concept.

**Explicit alternative (kailash-rs model):**
Separate fields:

- `structured_output: Optional[StructuredOutputConfig]` -- for response format
- `provider_options: Optional[Dict[str, Any]]` -- for provider-specific settings (api_version, deployment, etc.)

These never overlap, and each consumer knows exactly which field to read.

**Blast radius of changing it:**

- `BaseAgentConfig` -- add new fields, deprecate `provider_config`
- `WorkflowGenerator` -- update all 3 read sites (lines 165, 372, 483)
- `LLMAgentNode` -- remove disambiguation logic (lines 756-766)
- `SingleShotStrategy` / `AsyncSingleShotStrategy` -- update provider_config reads
- `SchemaFactory` -- update to read new field
- `base_agent.py` -- update line 1472
- `schema_factory.py` -- update line 114
- All test files referencing `provider_config` (12+ files found via grep)
- All user-facing documentation and examples

---

### 2.3 Azure Backend Auto-Detection (URL Pattern Matching)

**What it does automatically:**
`AzureBackendDetector.detect()` reads up to 6 environment variables (`AZURE_ENDPOINT`, `AZURE_OPENAI_ENDPOINT`, `AZURE_AI_INFERENCE_ENDPOINT`, `AZURE_API_KEY`, `AZURE_OPENAI_API_KEY`, `AZURE_AI_INFERENCE_API_KEY`) and applies regex pattern matching against 7 URL patterns to determine whether to use Azure OpenAI or Azure AI Foundry backend. If no pattern matches, it defaults to Azure OpenAI with a warning. If the API call fails with specific error signatures, it switches backends automatically.

**What coupling it creates:**

- `AzureBackendDetector` -- regex patterns must track Azure's evolving URL schemes
- `UnifiedAzureProvider` -- delegates entirely to detector for backend selection
- `AzureOpenAIBackend.__init__()` -- independently reads the SAME env vars (lines 126-133) with DIFFERENT priority ordering than the detector
- `AzureAIFoundryBackend.__init__()` -- reads env vars with yet ANOTHER priority ordering (lines 394-396)
- Three separate modules read `AZURE_OPENAI_API_VERSION` / `AZURE_API_VERSION` independently

**How it fails:**

- **Issue #256:** Endpoints using `*.cognitiveservices.azure.com` (India South region) were not in the regex patterns, causing a warning on every LLM call even though the default fallback was correct.
- **Pattern lag:** Every new Azure region or URL scheme requires a code change to the regex list. Users discover the bug only at runtime.
- **Error-based fallback:** The `handle_error()` method parses error message strings to detect wrong backend selection. Error message formats are not a stable API and change without notice.
- **Env var chaos:** Three modules read the same env vars with different priority orderings:
  - Detector: `AZURE_ENDPOINT` > `AZURE_OPENAI_ENDPOINT` > `AZURE_AI_INFERENCE_ENDPOINT`
  - AzureOpenAIBackend: `AZURE_OPENAI_ENDPOINT` > `AZURE_ENDPOINT`
  - AzureAIFoundryBackend: `AZURE_AI_INFERENCE_ENDPOINT` > `AZURE_ENDPOINT`

**Explicit alternative (kailash-rs model):**
User provides `base_url` and `backend: "azure_openai" | "azure_ai_foundry"` explicitly. No URL pattern matching, no env var guessing. The SDK validates the URL is reachable but does not infer backend type from it.

```python
config = BaseAgentConfig(
    llm_provider="azure",
    base_url="https://myresource.openai.azure.com",
    azure_backend="openai",  # Explicit
    azure_api_version="2024-10-21",  # Explicit
)
```

**Blast radius of changing it:**

- `azure_detection.py` -- simplify or deprecate `AzureBackendDetector`
- `unified_azure_provider.py` -- accept explicit backend parameter
- `azure_backends.py` -- remove env var reading from `__init__`, accept params
- All tests in `tests/unit/nodes/ai/test_azure_detection.py`
- All tests in `tests/regression/test_issue_256_*.py` and `test_issue_257_*.py`
- User code that relies on auto-detection (backward compatibility layer needed)

---

### 2.4 System Prompt Auto-Patching for Azure JSON Requirements

**What it does automatically:**
`WorkflowGenerator.generate_signature_workflow()` (lines 241-253) checks if `provider_config` has `type` in `("json_object", "json_schema")` and if the system prompt does not contain "json" (case-insensitive). If so, it appends `"\n\nRespond with a JSON object containing the output fields."` to the system prompt.

Additionally, `SingleShotStrategy._build_messages()` (lines 394-401) and `AsyncSingleShotStrategy._build_messages()` (lines 226-231) independently append `"\n\nPlease respond in JSON format."` to the USER message (not system prompt) when `provider_config.type == "json_object"`.

**What coupling it creates:**

- `WorkflowGenerator` must understand Azure's API requirements (leaked provider concern)
- `SingleShotStrategy` / `AsyncSingleShotStrategy` must ALSO understand the same requirement and independently implement a fix
- The system prompt is modified AFTER `_get_system_prompt()` returns it, meaning the prompt_generator callback's output is silently altered
- Detection is based on string matching (`"json" not in system_prompt.lower()`), which is fragile -- a prompt mentioning "JSON" in a different context prevents the patch

**How it fails:**

- **Issue #254:** Before the fix, no auto-patching existed. Azure calls with `json_object` format failed because "json" was not in any message.
- **Double patching:** Both WorkflowGenerator (system prompt) and SingleShotStrategy (user message) may patch simultaneously, creating redundant instructions.
- **False negative:** A prompt containing "json" in an unrelated context (e.g., "parse the JSON config file") prevents the auto-patch even when the JSON response instruction is still needed.
- **Invisible mutation:** `_generate_system_prompt()` returns one thing; the LLM receives something different. Debugging prompt issues becomes difficult because the actual sent prompt is not what the user expects.

**Explicit alternative (kailash-rs model):**
No auto-patching. If the user wants JSON output, they explicitly configure structured output, and the SDK adds the necessary format instructions as a documented part of the structured output config, not as a silent post-hoc patch.

**Blast radius of changing it:**

- `WorkflowGenerator` -- remove post-hoc system prompt patching (lines 241-253)
- `SingleShotStrategy` / `AsyncSingleShotStrategy` -- remove JSON injection in messages
- `test_issue_254_azure_json_prompt.py` -- regression tests assert auto-patching; must be rewritten
- Any e2e test that relies on Azure JSON output working without explicit prompt instructions

---

### 2.5 Environment Variable Guessing (Multiple Names for Same Setting)

**What it does automatically:**
Azure configuration reads from multiple env var names with different priority orderings across different modules:

| Setting          | Env Vars Read (in priority order)                                        | Modules Reading                                                       |
| ---------------- | ------------------------------------------------------------------------ | --------------------------------------------------------------------- |
| Endpoint         | `AZURE_ENDPOINT`, `AZURE_OPENAI_ENDPOINT`, `AZURE_AI_INFERENCE_ENDPOINT` | `azure_detection.py`, `azure_backends.py` (x2), `config/providers.py` |
| API Key          | `AZURE_API_KEY`, `AZURE_OPENAI_API_KEY`, `AZURE_AI_INFERENCE_API_KEY`    | `azure_detection.py`, `azure_backends.py` (x2), `config/providers.py` |
| API Version      | `AZURE_OPENAI_API_VERSION`, `AZURE_API_VERSION` (default: `2024-10-21`)  | `azure_detection.py`, `azure_backends.py`                             |
| Deployment       | `AZURE_DEPLOYMENT`                                                       | `azure_detection.py`, `azure_backends.py`                             |
| Backend Override | `AZURE_BACKEND`                                                          | `azure_detection.py` only                                             |

**What coupling it creates:**

- Each module independently reads and resolves env vars, creating N parallel sources of truth
- Priority ordering differs between modules (see 2.3 above)
- Default values are hardcoded in multiple places (`"2024-10-21"` appears in both `azure_detection.py` line 228 and `azure_backends.py` line 20)
- `config/providers.py::check_azure_available()` only checks `AZURE_AI_INFERENCE_ENDPOINT` / `AZURE_AI_INFERENCE_API_KEY`, missing unified `AZURE_ENDPOINT` / `AZURE_API_KEY`

**How it fails:**

- **Issue #257:** `azure_backends.py` only read `AZURE_API_VERSION` but Azure's standard tooling and documentation uses `AZURE_OPENAI_API_VERSION`. Users had to set both to satisfy Kaizen and other Azure tools.
- **Priority divergence:** User sets `AZURE_ENDPOINT` (unified) but also has legacy `AZURE_OPENAI_ENDPOINT` set. Different modules may resolve to different endpoints.
- **Incomplete availability check:** `config/providers.py::check_azure_available()` returns `False` for users who only set `AZURE_ENDPOINT` and `AZURE_API_KEY` (the recommended unified vars).

**Explicit alternative (kailash-rs model):**
Single source: user provides `base_url` and `api_key` in config. Env var reading happens once at a single entry point, not scattered across modules.

**Blast radius of changing it:**

- Create a single `AzureConfig` resolution module that all Azure code imports from
- `azure_detection.py` -- delegate to shared resolver
- `azure_backends.py` -- delegate to shared resolver
- `config/providers.py` -- update `check_azure_available()` and `get_azure_config()`
- `test_issue_257_*.py` -- regression tests assert specific env var priority; may need updating
- User documentation listing env vars

---

### 2.6 Dual System Prompt Generation

**What it does automatically:**
Two parallel `_generate_system_prompt()` implementations exist:

1. **`BaseAgent._generate_system_prompt()`** (lines 1580-1704 of `base_agent.py`): Generates prompt from signature fields AND includes MCP tool documentation with ReAct pattern instructions. Used when BaseAgent passes `self._generate_system_prompt` as `prompt_generator` callback to WorkflowGenerator (line 350).

2. **`WorkflowGenerator._generate_system_prompt()`** (lines 411-529 of `workflow_generator.py`): Generates prompt from signature fields only. Includes JSON formatting instructions when NOT using OpenAI structured outputs. Used as fallback when no `prompt_generator` callback is provided.

**Routing logic in WorkflowGenerator.\_get_system_prompt():**

- If `self.prompt_generator is not None` (always true when created by BaseAgent): uses callback (BaseAgent version)
- Else (WorkflowGenerator used standalone): uses its own implementation

**What coupling it creates:**

- Two implementations must stay synchronized for field formatting (input/output field descriptions)
- BaseAgent version handles MCP tools; WorkflowGenerator version handles JSON formatting instructions
- Neither version handles BOTH concerns
- WorkflowGenerator's JSON formatting logic (lines 476-529) runs only in the fallback path, meaning BaseAgent-created agents NEVER get JSON formatting instructions from this code path
- The JSON formatting responsibility is then split: WorkflowGenerator adds it to system prompt in the fallback path, but the auto-patching (behavior 2.4) handles it in the BaseAgent path

**How they diverge:**

| Concern                  | BaseAgent version                        | WorkflowGenerator version                        |
| ------------------------ | ---------------------------------------- | ------------------------------------------------ |
| Field descriptions       | Uses `field_def.get("desc")`             | Uses `field_def['desc']` (KeyError risk)         |
| MCP tool documentation   | Included                                 | Not included                                     |
| JSON format instructions | NOT included                             | Included (when not using structured outputs)     |
| Output field types       | Uses `field_type.__name__` with fallback | Uses `field_type.__name__` (AttributeError risk) |
| No-signature fallback    | "You are a helpful AI assistant."        | "You are a helpful AI assistant."                |

**How it fails:**

- **Missing JSON instructions:** When BaseAgent.\_generate_system_prompt() is used (the common case), JSON formatting instructions are NOT included. The auto-patching in behavior 2.4 partially compensates, but only for `json_object`/`json_schema` types, not for general non-OpenAI providers that need prompt-based JSON guidance.
- **Divergence over time:** As features are added to one implementation, the other falls behind. MCP tool documentation exists only in BaseAgent's version. JSON format instructions exist only in WorkflowGenerator's version.
- **Testing gap:** Tests for system prompt generation test each implementation independently, so divergence is never caught by the test suite.

**Explicit alternative (kailash-rs model):**
Single prompt generation function that takes a configuration struct describing all concerns (signature fields, tool documentation, JSON format requirements). Composed from pure functions rather than method overrides.

**Blast radius of changing it:**

- `base_agent.py` lines 1580-1704 -- extract to shared module
- `workflow_generator.py` lines 411-529 -- replace with shared module
- All tests that assert on system prompt content from either path
- BaseAgent subclasses that override `_generate_system_prompt()` -- must migrate to new extension point

---

## 3. Coupling Map

```
User Code
    |
    v
BaseAgentConfig (config.py)
    |-- provider_config: Dict  -----> [Dual-purpose: structured output OR provider settings]
    |-- llm_provider: str
    |-- model: str
    |-- api_key, base_url: str
    |
    v
BaseAgent.__init__ (base_agent.py:347)
    |-- Creates WorkflowGenerator with prompt_generator=self._generate_system_prompt
    |
    v
WorkflowGenerator.generate_signature_workflow() (workflow_generator.py:102)
    |
    |-- [Implicit 2.1] Auto-generates provider_config if None
    |       |-- Reads: config.provider_config, config.llm_provider, self.signature
    |       |-- Calls: create_structured_output_config()
    |       |-- Decides strict mode from: prompt_generator is None AND provider == "openai"
    |
    |-- [Implicit 2.6] Gets system prompt via _get_system_prompt()
    |       |-- If prompt_generator: calls BaseAgent._generate_system_prompt()
    |       |-- Else: calls WorkflowGenerator._generate_system_prompt()
    |       |       |-- [Implicit 2.6 divergence] Includes JSON instructions if not structured output
    |
    |-- [Implicit 2.4] Patches system prompt for Azure JSON requirement
    |       |-- Reads: provider_config.type
    |       |-- Mutates: node_config["system_prompt"]
    |
    |-- Outputs: node_config dict with provider_config nested inside
    |
    v
LLMAgentNode.execute() (llm_agent.py:756)
    |
    |-- [Implicit 2.2] Disambiguates provider_config
    |       |-- If "type" in provider_config: treats as response_format
    |       |-- Else: ignores (Azure api_version case)
    |
    |-- Passes generation_config to provider
    |
    v
Provider Selection
    |
    |-- If "azure": UnifiedAzureProvider
    |       |-- [Implicit 2.3] AzureBackendDetector.detect()
    |       |       |-- [Implicit 2.5] Reads 6+ env vars
    |       |       |-- Regex URL pattern matching (7 patterns)
    |       |       |-- Default fallback to azure_openai
    |       |
    |       |-- AzureOpenAIBackend / AzureAIFoundryBackend
    |               |-- [Implicit 2.5] Reads env vars AGAIN independently
    |               |-- Creates SDK client with resolved config
    |
    |-- If "openai": OpenAIProvider
    |       |-- Passes response_format directly (no translation needed)
    |
    |-- If "google"/"gemini": GoogleProvider
            |-- Translates response_format to response_mime_type + response_json_schema

Strategies (parallel path):
    |
    SingleShotStrategy / AsyncSingleShotStrategy
        |-- [Implicit 2.4 duplicate] Reads agent.config.provider_config
        |-- If type == "json_object": appends JSON instruction to USER message
```

**Key observation:** The `provider_config` dict is read and interpreted at 7 distinct points in the pipeline, each with slightly different semantics.

---

## 4. Risk Assessment

### Risk Register

| ID  | Risk                                                             | Likelihood                                                          | Impact                                                         | Current Mitigation                    | Recommended Mitigation                                    |
| --- | ---------------------------------------------------------------- | ------------------------------------------------------------------- | -------------------------------------------------------------- | ------------------------------------- | --------------------------------------------------------- |
| R1  | New Azure URL pattern unrecognized                               | **High** (Azure adds regions regularly)                             | **Major** (warning on every call, falls back to default)       | Regex pattern list updated reactively | Eliminate pattern matching; explicit backend config       |
| R2  | provider_config ambiguity causes wrong response_format           | **Medium** (affects Azure users with custom api_version)            | **Critical** (API call fails)                                  | "type" key check in LLMAgentNode      | Separate fields for structured output vs provider options |
| R3  | System prompt divergence between BaseAgent and WorkflowGenerator | **High** (any prompt-related feature touches one but not the other) | **Significant** (missing JSON instructions, missing tool docs) | Manual synchronization                | Single prompt generation pipeline                         |
| R4  | Auto-generated provider_config overrides user intent             | **Low** (requires user to explicitly set None)                      | **Significant** (unexpected LLM behavior)                      | None                                  | Opt-in structured output, never auto-generate             |
| R5  | Env var priority divergence across modules                       | **Medium** (affects users with multiple Azure env vars set)         | **Major** (different modules connect to different endpoints)   | Per-issue fixes (e.g., #257)          | Single env resolution module                              |
| R6  | Error-based backend fallback uses unstable error message parsing | **Medium** (Azure changes error messages)                           | **Major** (fallback stops working silently)                    | String matching on error messages     | Explicit backend selection                                |
| R7  | Double JSON instruction injection (system prompt + user message) | **High** (happens for all Azure json_object usage)                  | **Minor** (redundant but not harmful)                          | None                                  | Single injection point                                    |

### Cascading Effects Matrix

A change to any implicit behavior has these cascading effects:

| Changed Behavior       | WorkflowGenerator | LLMAgentNode | Strategies | Azure Backends | Tests Affected |
| ---------------------- | ----------------- | ------------ | ---------- | -------------- | -------------- |
| 2.1 Auto-generation    | Direct            | Indirect     | Indirect   | None           | ~15            |
| 2.2 Dual-purpose field | Direct            | Direct       | Direct     | None           | ~12            |
| 2.3 URL detection      | None              | None         | None       | Direct         | ~8             |
| 2.4 Prompt patching    | Direct            | None         | Direct     | None           | ~6             |
| 2.5 Env var guessing   | None              | None         | None       | Direct         | ~10            |
| 2.6 Dual prompts       | Direct            | None         | None       | None           | ~8             |

---

## 5. Recommended Refactor Strategy

### Design Principle: Explicit is Better Than Implicit

Align with kailash-rs: the user declares what they want, the SDK does exactly that. No inference, no guessing, no patching. Convenience helpers (like `StructuredOutputConfig.from_signature()`) are available but never invoked automatically.

### Phase 1: Separate `provider_config` into Two Fields (Highest Risk, Highest Value)

**New fields on BaseAgentConfig:**

```python
@dataclass
class BaseAgentConfig:
    # ... existing fields ...

    # Replace provider_config with two explicit fields:
    structured_output: Optional[StructuredOutputConfig] = None  # response_format only
    provider_options: Optional[Dict[str, Any]] = None  # api_version, deployment, etc.

    # Backward compat (deprecated):
    provider_config: Optional[Dict[str, Any]] = None  # Emits deprecation warning
```

**StructuredOutputConfig type:**

```python
@dataclass
class StructuredOutputConfig:
    type: Literal["json_schema", "json_object"]
    json_schema: Optional[Dict] = None  # Only for type="json_schema"
    strict: bool = True
    name: str = "response"

    @classmethod
    def from_signature(cls, signature, strict=True) -> "StructuredOutputConfig":
        """Explicit helper -- user calls this, not the SDK."""
        schema = StructuredOutputGenerator.signature_to_json_schema(signature)
        return cls(type="json_schema", json_schema={"name": name, "schema": schema, "strict": strict})

    def to_response_format(self) -> Dict:
        """Convert to OpenAI-compatible response_format dict."""
        ...
```

**Effort:** 1 session (moderate complexity, many touch points but mechanical changes)

**Success criteria:**

- `provider_config` emits deprecation warning when set
- `structured_output` and `provider_options` are never confused
- Issue #255 class of bugs becomes impossible by construction
- All existing tests pass with backward-compat shim

### Phase 2: Centralize Azure Configuration Resolution (Medium Risk)

**Create `AzureConfigResolver`:**

```python
@dataclass
class AzureResolvedConfig:
    endpoint: str
    api_key: str
    api_version: str
    deployment: Optional[str]
    backend: Literal["azure_openai", "azure_ai_foundry"]

class AzureConfigResolver:
    @staticmethod
    def resolve(
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        api_version: Optional[str] = None,
        backend: Optional[str] = None,
    ) -> AzureResolvedConfig:
        """Single entry point for all Azure config resolution.

        Explicit params take precedence. Falls back to env vars
        with a single, documented priority order.
        """
```

**Effort:** 1 session

**Success criteria:**

- All Azure modules import from `AzureConfigResolver` -- zero direct `os.getenv()` for Azure settings
- Single documented env var priority order
- Issues #256 and #257 class of bugs become impossible
- `AzureBackendDetector` retained but only as a convenience that calls `AzureConfigResolver` internally

### Phase 3: Make Structured Output Opt-In (Medium Risk)

**Remove auto-generation from WorkflowGenerator:**

- Delete lines 190-208 in `workflow_generator.py`
- Provide `StructuredOutputConfig.from_signature()` as a convenience the user calls explicitly
- Update examples and documentation

**Effort:** 1 session

**Success criteria:**

- No structured output config generated unless user explicitly provides one
- Issue #254 class of bugs becomes impossible (no auto-generated json_object)
- JSON instruction patching (behavior 2.4) can be removed since structured output is always intentional

### Phase 4: Unify System Prompt Generation (Lower Risk)

**Create `PromptBuilder`:**

```python
class PromptBuilder:
    @staticmethod
    def build(
        signature: Optional[Signature],
        tools: Optional[List[Dict]],
        structured_output: Optional[StructuredOutputConfig],
        custom_prefix: Optional[str] = None,
    ) -> str:
        """Single prompt generation function handling ALL concerns."""
```

**Effort:** 1 session

**Success criteria:**

- Single code path for all system prompt generation
- MCP tool documentation and JSON instructions always included when applicable
- BaseAgent.\_generate_system_prompt() delegates to PromptBuilder
- WorkflowGenerator.\_generate_system_prompt() delegates to PromptBuilder

### Phase 5: Backward Compatibility Deprecation Period

- Phase 1-4 changes ship with backward-compat shims
- `provider_config` continues working with deprecation warning for 2 minor versions
- Auto-detection continues working but logs recommendation to use explicit config
- Remove shims in next major version

**Effort:** Integrated into each phase

---

### Dependency Order

```
Phase 1 (provider_config split)
    |
    v
Phase 2 (Azure config resolver) -- can run in parallel with Phase 1
    |
    v
Phase 3 (opt-in structured output) -- depends on Phase 1
    |
    v
Phase 4 (prompt unification) -- depends on Phase 3
```

Phases 1 and 2 are independent and can be parallelized. Phase 3 depends on Phase 1 (needs the new `StructuredOutputConfig` type). Phase 4 depends on Phase 3 (prompt builder needs to know whether structured output is present to decide on JSON instructions).

### Total Effort

4 autonomous execution sessions (2 parallel + 2 sequential). With parallel execution of Phases 1 and 2, the critical path is 3 sessions.

### Cross-SDK Alignment

Each phase should produce a cross-SDK inspection against kailash-rs to verify semantic alignment per EATP D6. The Rust SDK already has the explicit model; the Python refactor brings parity.
