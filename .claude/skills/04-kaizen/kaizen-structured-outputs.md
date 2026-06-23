# Kaizen Structured Outputs

**Requires**: Kaizen 0.8.2+ | Multi-provider (OpenAI, Google/Gemini, Azure AI Foundry)

## Auto-Configuration (Default)

When `BaseAgent` has a signature and no `provider_config`, structured outputs auto-configure:

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField
from kaizen.core.config import BaseAgentConfig

class QASignature(Signature):
    question: str = InputField(desc="User question")
    answer: str = OutputField(desc="Answer")
    confidence: float = OutputField(desc="Confidence 0-1")

config = BaseAgentConfig(llm_provider="openai", model="gpt-4o-2024-08-06")
agent = BaseAgent(config=config, signature=QASignature())
result = agent.run(question="What is AI?")
# result['answer'] and result['confidence'] guaranteed present with correct types
```

Use manual config only to force legacy mode, override schema, or disable structured outputs.

## Manual Configuration

```python
from kaizen.core.structured_output import create_structured_output_config

provider_config = create_structured_output_config(
    signature=MySignature(),  # Signature instance
    strict=True,              # 100% compliance (strict) vs 70-85% (legacy)
    name="my_response",       # Schema name
    auto_fallback=True        # Fall back to legacy if types incompatible (default)
)

config = BaseAgentConfig(
    llm_provider="openai",  # or "google", "azure"
    model="gpt-4o-2024-08-06",
    provider_config=provider_config
)
```

## Strict vs Legacy Mode

| Feature          | Strict (`True`)                                                 | Legacy (`False`)                          |
| ---------------- | --------------------------------------------------------------- | ----------------------------------------- |
| Reliability      | 100% schema compliance                                          | 70-85% best-effort                        |
| Models           | gpt-4o-2024-08-06+                                              | All OpenAI models                         |
| Format           | `json_schema` with constrained sampling                         | `json_object` + system prompt             |
| Compatible types | str, int, float, bool, List[T], Optional[T], Literal, TypedDict | All types including Dict[str, Any], Union |

## Provider Support (v0.8.2)

| Provider         | Strict | Legacy | Translation                              |
| ---------------- | ------ | ------ | ---------------------------------------- |
| OpenAI           | Yes    | Yes    | Native                                   |
| Google/Gemini    | Yes    | Yes    | `response_mime_type` + `response_schema` |
| Azure AI Foundry | Yes    | Yes    | `JsonSchemaFormat`                       |
| Ollama/Anthropic | No     | No     | Prompt-based fallback                    |

## Response Handling

Dict responses from providers are auto-detected -- no JSON parsing needed:

```python
result = agent.run(product_description="Wireless headphones")
print(result['category'])  # Direct dict access, pre-parsed
```

## Supported Types (10 Patterns)

| Python Type                   | JSON Schema                             | Strict Compatible   |
| ----------------------------- | --------------------------------------- | ------------------- |
| `str`, `int`, `float`, `bool` | Basic types                             | Yes                 |
| `Literal["A", "B"]`           | `{"enum": ["A", "B"]}`                  | Yes                 |
| `Optional[str]`               | Not in `required`                       | Yes                 |
| `List[str]`                   | `{"type": "array", "items": ...}`       | Yes                 |
| `TypedDict`                   | `{"type": "object", "properties": ...}` | Yes                 |
| `Union[str, int]`             | `{"oneOf": [...]}`                      | No -- auto-fallback |
| `Dict[str, Any]`              | `{"additionalProperties": ...}`         | No -- auto-fallback |

### Type Validation

```python
from kaizen.core.type_introspector import TypeIntrospector

compatible, reason = TypeIntrospector.is_strict_mode_compatible(field_type)
is_valid, error = TypeIntrospector.validate_value_against_type(value, type_annotation)
schema = TypeIntrospector.type_to_json_schema(type_annotation, "description")
```

## Signature Inheritance (v0.6.3+)

Child signatures MERGE parent fields (not replace):

```python
class BaseConversation(Signature):
    text: str = InputField(desc="Input")
    intent: str = OutputField(desc="Intent")
    confidence: float = OutputField(desc="Confidence")

class ReferralConversation(BaseConversation):
    referral_needed: bool = OutputField(desc="Referral needed")
    # Total: 3 output fields (2 parent + 1 child)
```

Child can override parent fields. Multi-level inheritance works (Level1 -> Level2 -> Level3).

## Custom System Prompts

```python
class CustomAgent(BaseAgent):
    def _generate_system_prompt(self) -> str:
        return "Your custom prompt here"
# Callback pattern: WorkflowGenerator calls this automatically
```

## API Reference

```python
def create_structured_output_config(
    signature: Any,          # Signature instance
    strict: bool = True,     # Strict vs legacy mode
    name: str = "response",  # Schema name
    auto_fallback: bool = True  # Fallback to legacy if incompatible
) -> Dict[str, Any]
# Raises ValueError if strict=True, types incompatible, auto_fallback=False

StructuredOutputGenerator.signature_to_json_schema(signature) -> Dict[str, Any]
```

## Troubleshooting

| Error                                | Cause                         | Fix                                              |
| ------------------------------------ | ----------------------------- | ------------------------------------------------ |
| `TypeError: Subscripted generics`    | Kaizen < 0.6.5                | Upgrade kailash-kaizen                           |
| `Workflow parameters not declared`   | Kaizen < 0.6.3                | Upgrade kailash-kaizen                           |
| `additionalProperties must be false` | Dict[str, Any] in strict mode | Use auto_fallback=True or replace with TypedDict |
| Child missing parent fields          | Kaizen < 0.6.3                | Upgrade kailash-kaizen                           |
| Extra fields in response             | Legacy mode (strict=False)    | Switch to strict mode with gpt-4o-2024-08-06+    |
