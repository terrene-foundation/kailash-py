# Kaizen Common Issues & Fixes

Quick troubleshooting guide for common Kaizen errors and solutions.

## Config Not Auto-Converting

```python
# WRONG
agent = MyAgent(config=BaseAgentConfig(...))

# RIGHT - Use domain config, auto-converts
agent = MyAgent(config=MyDomainConfig(...))
```

## Shared Memory Not Working

```python
# Missing shared_memory parameter
shared_pool = SharedMemoryPool()
agent = MyAgent(config, shared_pool, agent_id="my_agent")
```

## Extract Methods Failing

```python
# Debug first
print(result.keys())
data = self.extract_list(result, "actual_key_name", default=[])
```

## Multi-Modal API Errors

**See**: `sdk-users/apps/kaizen/docs/reference/multi-modal-api-reference.md` - Common Pitfalls section

## Provider Compatibility for Structured Outputs (v0.8.2)

**Multi-Provider Support**: OpenAI, Google/Gemini, and Azure AI Foundry all support structured outputs with automatic format translation. Ollama/Anthropic do NOT support structured outputs API.

**Provider Support Matrix**:
- OpenAI: Full support for `json_schema` (strict mode) and `json_object` (legacy)
- Google/Gemini: Full support - auto-translates to `response_mime_type` + `response_schema`
- Azure AI Foundry: Full support - auto-translates to `JsonSchemaFormat`
- Ollama: NO support for structured outputs API
- Anthropic: NO support for structured outputs API

**Affected Agents** (require structured output provider):
- `PlanningAgent` - Uses `List[PlanStep]` schema
- `PEVAgent` - Uses `List[Refinement]` schema
- `ToTAgent` - Uses `List[ToTNode]` schema
- `MetaController` - Uses complex routing schemas

**Symptoms with Unsupported Providers**:
```python
# Test times out after 60-120s
# JSON_PARSE_FAILED errors
# Provider tries to generate matching JSON but can't comply with strict schema
```

**Solution** (choose any supported provider):
```python
# WRONG (will timeout with complex schemas)
agent = PlanningAgent(
    llm_provider="ollama",
    model="llama3.1:8b-instruct-q8_0"
)

# RIGHT - OpenAI (100% schema compliance)
agent = PlanningAgent(
    llm_provider="openai",
    model="gpt-4o-mini"
)

# RIGHT - Google Gemini (100% schema compliance, v0.8.2)
agent = PlanningAgent(
    llm_provider="google",
    model="gemini-2.0-flash"
)

# RIGHT - Azure AI Foundry (100% schema compliance, v0.8.2)
agent = PlanningAgent(
    llm_provider="azure",
    model="gpt-4o"
)
```

**When to Use Each Provider**:
- **OpenAI** (RECOMMENDED): Widest model selection, proven reliability
- **Google/Gemini** (GOOD): Free tier available, multimodal support
- **Azure** (ENTERPRISE): Azure ecosystem integration, compliance
- **Ollama** (SIMPLE ONLY): Free local inference, string/dict outputs only

## pytest-asyncio Version Compatibility

**CRITICAL**: pytest-asyncio version affects async test execution. Use 0.21.1 for E2E tests.

**Issue**: pytest-asyncio 1.x forces `Mode.STRICT` even with `asyncio_mode = auto` in pytest.ini
- Version 1.2.0+: Ignores `asyncio_mode = auto`, enforces STRICT mode
- Version 0.23.0: `AttributeError: 'Package' object has no attribute 'obj'`
- Version 0.21.1: Works correctly with E2E tests

**Solution**:
```bash
pip install pytest-asyncio==0.21.1
```

**pytest.ini Configuration**:
```ini
[pytest]
asyncio_mode = auto
asyncio_default_fixture_loop_scope = function
asyncio_default_test_loop_scope = function
```

## Multi-Modal Pitfalls

### Pitfall 1: OllamaVisionProvider Initialization
```python
# WRONG - TypeError
provider = OllamaVisionProvider(model="bakllava")

# CORRECT
config = OllamaVisionConfig(model="bakllava")
provider = OllamaVisionProvider(config=config)
```

### Pitfall 2: VisionAgent Parameter Names
```python
# WRONG - TypeError
result = agent.run(image="...", prompt="What do you see?")

# CORRECT
result = agent.run(image="...", question="What do you see?")
```

### Pitfall 3: Image Path Handling
```python
# WRONG - Ollama doesn't accept data URLs
img = ImageField()
img.load("/path/to/image.png")
provider.analyze_image(image=img.to_base64(), ...)

# CORRECT - Pass file path or ImageField
provider.analyze_image(image="/path/to/image.png", ...)
```

### Pitfall 4: Response Format Differences
```python
# OllamaVisionProvider -> 'response' key
result = provider.analyze_image(...)
text = result['response']

# VisionAgent -> 'answer' key
result = agent.run(...)
text = result['answer']

# MultiModalAgent -> signature fields
result = agent.run(...)
invoice = result['invoice_number']  # Depends on signature
```

### Pitfall 5: Integration Testing
**CRITICAL**: Always validate with real models, not just mocks.

```python
# INSUFFICIENT
def test_vision_mocked():
    provider = MockVisionProvider()
    result = provider.analyze_image(...)
    assert result  # Passes but doesn't test real API

# REQUIRED
@pytest.mark.integration
def test_vision_real():
    config = OllamaVisionConfig(model="bakllava")
    provider = OllamaVisionProvider(config=config)
    result = provider.analyze_image(
        image="/path/to/test/invoice.png",
        prompt="Extract invoice number"
    )
    assert 'response' in result
    assert len(result['response']) > 0
```

## UX Improvements

### Config Auto-Extraction
```python
# OLD - DON'T DO THIS
agent_config = BaseAgentConfig(
    llm_provider=config.llm_provider,
    model=config.model,
    temperature=config.temperature,
    max_tokens=config.max_tokens
)
super().__init__(config=agent_config, ...)

# NEW - ALWAYS DO THIS
super().__init__(config=config, ...)  # Auto-converted
```

### Shared Memory Convenience
```python
# OLD - DON'T DO THIS
if self.shared_memory:
    self.shared_memory.write_insight({
        "agent_id": self.agent_id,
        "content": json.dumps(result),
        "tags": ["processing"],
        "importance": 0.9
    })

# NEW - ALWAYS DO THIS
self.write_to_memory(
    content=result,  # Auto-serialized
    tags=["processing"],
    importance=0.9
)
```

### Result Parsing Helpers
```python
# OLD - DON'T DO THIS
field_raw = result.get("field", "[]")
try:
    field = json.loads(field_raw) if isinstance(field_raw, str) else field_raw
except:
    field = []

# NEW - ALWAYS DO THIS
field = self.extract_list(result, "field", default=[])
```

**Available Methods**: `extract_list()`, `extract_dict()`, `extract_float()`, `extract_str()`

## Reference

- Multi-modal API: `sdk-users/apps/kaizen/docs/reference/multi-modal-api-reference.md`
- Structured outputs: `kaizen-structured-outputs.md` skill
- Testing patterns: `kaizen-testing-patterns.md` skill
- UX helpers: `kaizen-ux-helpers.md` skill
