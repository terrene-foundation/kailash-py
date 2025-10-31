# Kaizen Structured Outputs

**Version**: 0.6.3+
**Feature**: OpenAI Structured Outputs API with 100% schema compliance

---

## Overview

Kaizen provides first-class support for OpenAI's Structured Outputs API, enabling 100% reliable JSON schema compliance with supported models. This guide covers configuration, signature inheritance, and integration patterns.

---

## Quick Start

### Basic Usage with Strict Mode

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField
from kaizen.core.config import BaseAgentConfig
from kaizen.core.structured_output import create_structured_output_config

class ProductAnalysisSignature(Signature):
    """Structured product analysis."""
    product_description: str = InputField(desc="Product description")
    category: str = OutputField(desc="Product category")
    price_range: str = OutputField(desc="Price range estimate")
    confidence: float = OutputField(desc="Confidence score 0-1")

# Create structured output config (strict mode)
config = BaseAgentConfig(
    llm_provider="openai",
    model="gpt-4o-2024-08-06",
    provider_config=create_structured_output_config(
        signature=ProductAnalysisSignature(),
        strict=True,
        name="product_analysis"
    )
)

# Create agent with structured outputs
agent = BaseAgent(config=config, signature=ProductAnalysisSignature())

# Run with guaranteed schema compliance
result = agent.run(product_description="Wireless noise-cancelling headphones with 30-hour battery")
print(result)
# Output: {'category': 'Electronics', 'price_range': '$200-$400', 'confidence': 0.95}
```

---

## Configuration Modes

### Strict Mode (Recommended)

**100% schema compliance** with gpt-4o-2024-08-06+

```python
from kaizen.core.structured_output import create_structured_output_config

# Strict mode configuration
provider_config = create_structured_output_config(
    signature=MySignature(),
    strict=True,  # Enforces schema compliance
    name="my_response"
)

config = BaseAgentConfig(
    llm_provider="openai",
    model="gpt-4o-2024-08-06",
    provider_config=provider_config
)
```

**Generated Format:**
```python
{
    "type": "json_schema",
    "json_schema": {
        "name": "my_response",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {...},
            "required": [...],
            "additionalProperties": False
        }
    }
}
```

### Legacy Mode (Best-Effort)

**70-85% reliability** with older models

```python
# Legacy mode configuration
provider_config = create_structured_output_config(
    signature=MySignature(),
    strict=False,  # Best-effort JSON object mode
    name="my_response"
)

config = BaseAgentConfig(
    llm_provider="openai",
    model="gpt-4",  # Works with older models
    provider_config=provider_config
)
```

**Generated Format:**
```python
{
    "type": "json_object",
    "schema": {
        "type": "object",
        "properties": {...},
        "required": [...]
    }
}
```

---

## Signature Inheritance

**New in v0.6.3**: Child signatures now **MERGE** parent fields instead of replacing them.

### Parent-Child Inheritance

```python
from kaizen.signatures import Signature, InputField, OutputField

class BaseConversationSignature(Signature):
    """Parent signature with 6 output fields."""
    conversation_text: str = InputField(desc="The conversation text")

    # Parent fields (6 fields)
    next_action: str = OutputField(desc="Next action to take")
    extracted_fields: dict = OutputField(desc="Extracted fields")
    conversation_context: str = OutputField(desc="Context of conversation")
    user_intent: str = OutputField(desc="User intent")
    system_response: str = OutputField(desc="System response")
    confidence_level: float = OutputField(desc="Confidence level 0-1")

class ReferralConversationSignature(BaseConversationSignature):
    """Child signature that EXTENDS parent with 4 additional fields."""

    # Child fields (4 new fields)
    confidence_score: float = OutputField(desc="Confidence score for referral")
    user_identity_detected: bool = OutputField(desc="Whether user identity detected")
    referral_needed: bool = OutputField(desc="Whether referral is needed")
    referral_reason: str = OutputField(desc="Reason for referral")

# Verify field merging
sig = ReferralConversationSignature()
print(f"Total output fields: {len(sig.output_fields)}")  # 10 (6 from parent + 4 from child)
print(f"Parent fields preserved: {all(f in sig.output_fields for f in ['next_action', 'extracted_fields', 'conversation_context', 'user_intent', 'system_response', 'confidence_level'])}")  # True
print(f"Child fields added: {all(f in sig.output_fields for f in ['confidence_score', 'user_identity_detected', 'referral_needed', 'referral_reason'])}")  # True
```

### Multi-Level Inheritance

```python
class Level1Signature(Signature):
    """Level 1: Base signature."""
    input1: str = InputField(desc="Level 1 input")
    output1: str = OutputField(desc="Level 1 output")

class Level2Signature(Level1Signature):
    """Level 2: Extends Level 1."""
    output2: str = OutputField(desc="Level 2 output")

class Level3Signature(Level2Signature):
    """Level 3: Extends Level 2."""
    output3: str = OutputField(desc="Level 3 output")

# Verify multi-level merging
sig = Level3Signature()
print(f"Total output fields: {len(sig.output_fields)}")  # 3 (1 from each level)
assert "output1" in sig.output_fields  # From Level1
assert "output2" in sig.output_fields  # From Level2
assert "output3" in sig.output_fields  # From Level3
```

### Field Overriding

```python
class ParentSignature(Signature):
    """Parent with default field."""
    input_text: str = InputField(desc="Input text")
    result: str = OutputField(desc="Parent result")

class ChildSignature(ParentSignature):
    """Child overrides parent field."""
    result: str = OutputField(desc="Child result (overridden)")
    extra: str = OutputField(desc="Extra field")

# Verify override behavior
sig = ChildSignature()
print(sig.output_fields["result"]["desc"])  # "Child result (overridden)"
print(len(sig.output_fields))  # 2 (parent field overridden + child extra)
```

---

## Integration with BaseAgent

### Manual Provider Config

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.core.config import BaseAgentConfig

# Option 1: Pass provider_config directly to BaseAgentConfig
config = BaseAgentConfig(
    llm_provider="openai",
    model="gpt-4o-2024-08-06",
    provider_config={
        "type": "json_schema",
        "json_schema": {
            "name": "response",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "answer": {"type": "string", "description": "Answer to question"}
                },
                "required": ["answer"],
                "additionalProperties": False
            }
        }
    }
)

agent = BaseAgent(config=config, signature=MySignature())
```

### Using Helper Function

```python
from kaizen.core.structured_output import create_structured_output_config

# Option 2: Use helper function (recommended)
provider_config = create_structured_output_config(
    signature=MySignature(),
    strict=True,
    name="my_response"
)

config = BaseAgentConfig(
    llm_provider="openai",
    model="gpt-4o-2024-08-06",
    provider_config=provider_config
)

agent = BaseAgent(config=config, signature=MySignature())
```

---

## Supported Models

### OpenAI Structured Outputs (Strict Mode)

**Supported Models** (strict=True):
- `gpt-4o-2024-08-06` (recommended)
- `gpt-4o-mini-2024-07-18`
- Newer models released after August 2024

**Features**:
- 100% schema compliance guaranteed
- Automatic validation and error handling
- Supports complex nested objects, arrays, enums
- `additionalProperties: false` enforced by default

### Legacy JSON Object Mode

**Supported Models** (strict=False):
- `gpt-4` / `gpt-4-turbo`
- `gpt-3.5-turbo`
- Any model with JSON mode support

**Features**:
- Best-effort schema compliance (70-85%)
- May produce extra fields or incorrect types
- Requires additional validation in application code

---

## Type Mapping

Kaizen automatically converts Python types to JSON schema types:

| Python Type | JSON Schema Type | Notes |
|-------------|------------------|-------|
| `str` | `"string"` | Basic string type |
| `int` | `"integer"` | Whole numbers |
| `float` | `"number"` | Decimal numbers |
| `bool` | `"boolean"` | True/False |
| `dict` | `"object"` | Nested objects |
| `list` | `"array"` | Arrays of items |
| `List[str]` | `{"type": "array", "items": {"type": "string"}}` | Typed arrays |
| `Optional[str]` | Not in `required` | Optional fields |

### Complex Type Example

```python
from typing import List, Optional

class ComplexSignature(Signature):
    """Signature with complex types."""
    user_id: str = InputField(desc="User ID")

    # Complex output types
    tags: List[str] = OutputField(desc="List of tags")
    metadata: dict = OutputField(desc="Nested metadata object")
    score: float = OutputField(desc="Numeric score")
    is_valid: bool = OutputField(desc="Validation flag")
    notes: Optional[str] = OutputField(desc="Optional notes")

# Generated JSON schema will be:
{
    "type": "object",
    "properties": {
        "tags": {"type": "array", "items": {"type": "string"}},
        "metadata": {"type": "object"},
        "score": {"type": "number"},
        "is_valid": {"type": "boolean"},
        "notes": {"type": "string"}
    },
    "required": ["tags", "metadata", "score", "is_valid"],  # notes is optional
    "additionalProperties": False
}
```

---

## Troubleshooting

### Issue: "Workflow parameters ['provider_config'] not declared"

**Cause**: Using older version of Kaizen (< 0.6.3)

**Solution**: Upgrade to Kaizen 0.6.3+

```bash
pip install --upgrade kailash-kaizen
```

### Issue: "Invalid schema: additionalProperties must be false"

**Cause**: OpenAI Structured Outputs requires `additionalProperties: false`

**Solution**: Use `strict=True` mode (automatically sets this)

```python
config = create_structured_output_config(signature, strict=True)
```

### Issue: Child signature missing parent fields

**Cause**: Using older version of Kaizen (< 0.6.3)

**Solution**: Upgrade to Kaizen 0.6.3+ (fixed in signature inheritance)

```bash
pip install --upgrade kailash-kaizen
```

### Issue: Model returns extra fields not in schema

**Cause**: Using legacy mode (strict=False) with best-effort compliance

**Solution**: Switch to strict mode with supported model

```python
config = BaseAgentConfig(
    llm_provider="openai",
    model="gpt-4o-2024-08-06",  # Use supported model
    provider_config=create_structured_output_config(signature, strict=True)
)
```

### Issue: "Provider config flattened instead of nested"

**Cause**: Using older version of Kaizen (< 0.6.3) with workflow_generator bug

**Solution**: Upgrade to Kaizen 0.6.3+ (fixed in workflow generator)

---

## API Reference

### `create_structured_output_config()`

Create OpenAI-compatible structured output configuration.

**Signature:**
```python
def create_structured_output_config(
    signature: Any,
    strict: bool = True,
    name: str = "response"
) -> Dict[str, Any]
```

**Parameters:**
- `signature` (Signature): Kaizen signature instance to convert to JSON schema
- `strict` (bool): Use strict mode (100% compliance) vs legacy mode (best-effort). Default: `True`
- `name` (str): Schema name for OpenAI API. Default: `"response"`

**Returns:**
- `Dict[str, Any]`: Provider config dict for BaseAgentConfig

**Example:**
```python
from kaizen.core.structured_output import create_structured_output_config

provider_config = create_structured_output_config(
    signature=MySignature(),
    strict=True,
    name="my_analysis"
)
```

### `StructuredOutputGenerator.signature_to_json_schema()`

Convert signature to JSON schema dict.

**Signature:**
```python
@staticmethod
def signature_to_json_schema(signature: Any) -> Dict[str, Any]
```

**Parameters:**
- `signature` (Signature): Kaizen signature instance

**Returns:**
- `Dict[str, Any]`: JSON schema dict with properties, required fields, and type mappings

**Example:**
```python
from kaizen.core.structured_output import StructuredOutputGenerator

schema = StructuredOutputGenerator.signature_to_json_schema(MySignature())
print(schema)
# {'type': 'object', 'properties': {...}, 'required': [...]}
```

---

## Best Practices

1. **Use Strict Mode for Production**
   - Guarantees 100% schema compliance
   - Eliminates need for manual validation
   - Supported by latest OpenAI models

2. **Design Signatures First**
   - Define clear, typed signatures before implementation
   - Use inheritance to share common fields across agents
   - Leverage Python type hints for automatic schema generation

3. **Test Inheritance Chains**
   - Verify child signatures merge all parent fields
   - Check field overriding behavior matches expectations
   - Use multi-level inheritance for complex domain models

4. **Handle Optional Fields**
   - Use `Optional[Type]` for optional fields
   - Optional fields won't be in `required` list
   - Model may return None or omit optional fields

5. **Validate Complex Types**
   - Test nested objects and arrays with real data
   - Verify typed lists (List[str]) generate correct schemas
   - Use unit tests to catch schema generation issues

---

## Examples

### Example 1: Customer Support Agent

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField
from kaizen.core.config import BaseAgentConfig
from kaizen.core.structured_output import create_structured_output_config
from typing import List

class SupportTicketSignature(Signature):
    """Structured support ticket analysis."""
    ticket_text: str = InputField(desc="Customer support ticket text")

    category: str = OutputField(desc="Ticket category (technical, billing, feature_request)")
    priority: str = OutputField(desc="Priority level (low, medium, high, urgent)")
    sentiment: str = OutputField(desc="Customer sentiment (positive, neutral, negative)")
    action_items: List[str] = OutputField(desc="List of action items for support team")
    estimated_resolution_hours: int = OutputField(desc="Estimated hours to resolve")

# Create agent with structured outputs
config = BaseAgentConfig(
    llm_provider="openai",
    model="gpt-4o-2024-08-06",
    provider_config=create_structured_output_config(
        signature=SupportTicketSignature(),
        strict=True,
        name="support_analysis"
    )
)

agent = BaseAgent(config=config, signature=SupportTicketSignature())

# Process ticket with guaranteed schema compliance
result = agent.run(
    ticket_text="My payment failed but I was still charged! This is the third time this month. Please fix ASAP!"
)

print(result)
# {
#     'category': 'billing',
#     'priority': 'urgent',
#     'sentiment': 'negative',
#     'action_items': ['Verify payment status', 'Process refund if duplicate charge', 'Investigate recurring payment issue'],
#     'estimated_resolution_hours': 2
# }
```

### Example 2: Multi-Level Inheritance

```python
class BaseAnalysisSignature(Signature):
    """Base analysis for all document types."""
    document_text: str = InputField(desc="Document text to analyze")

    summary: str = OutputField(desc="Document summary")
    key_points: List[str] = OutputField(desc="Key points extracted")

class FinancialAnalysisSignature(BaseAnalysisSignature):
    """Financial document analysis extends base."""
    revenue: float = OutputField(desc="Revenue amount")
    expenses: float = OutputField(desc="Expenses amount")
    profit_margin: float = OutputField(desc="Profit margin percentage")

class QuarterlyReportSignature(FinancialAnalysisSignature):
    """Quarterly report extends financial analysis."""
    quarter: str = OutputField(desc="Fiscal quarter (Q1, Q2, Q3, Q4)")
    year: int = OutputField(desc="Fiscal year")
    growth_rate: float = OutputField(desc="YoY growth rate percentage")

# Create agent with multi-level signature
sig = QuarterlyReportSignature()
print(f"Total fields: {len(sig.output_fields)}")  # 8 fields (2 base + 3 financial + 3 quarterly)

config = BaseAgentConfig(
    llm_provider="openai",
    model="gpt-4o-2024-08-06",
    provider_config=create_structured_output_config(sig, strict=True)
)

agent = BaseAgent(config=config, signature=sig)
```

---

## Version History

### v0.6.3 (Current)
- ✅ OpenAI Structured Outputs API support (strict mode)
- ✅ Signature inheritance field merging (MERGE not REPLACE)
- ✅ provider_config nested dict preservation
- ✅ LLMAgentNode provider_config parameter support
- ✅ Comprehensive test coverage (29 new tests)

### v0.6.2 (Legacy)
- ❌ No OpenAI Structured Outputs support
- ❌ Signature inheritance replaced parent fields
- ❌ provider_config blocked by workflow validation

---

## Further Reading

- [Kaizen BaseAgent Architecture](../../apps/kailash-kaizen/docs/guides/baseagent-architecture.md)
- [Signature Programming Guide](../../apps/kailash-kaizen/docs/guides/signature-programming.md)
- [OpenAI Structured Outputs Documentation](https://platform.openai.com/docs/guides/structured-outputs)
- [Kaizen Configuration Guide](../../apps/kailash-kaizen/docs/reference/configuration.md)