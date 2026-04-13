# Kailash Kaizen -- Domain Specification — Signatures & Structured Output

Version: 2.7.3
Package: `kailash-kaizen`

Parent domain: Kailash Kaizen AI agent framework. This file covers the signature system (InputField, OutputField, Signature, SignatureMeta, parser/compiler/validator, templates, enterprise extensions, multi-modal, execution patterns) and structured output (JSON schema generation). See also `kaizen-core.md`, `kaizen-providers.md`, and `kaizen-advanced.md`.

---

## 2. Signature System

The signature system replaces prompt engineering with declarative input/output contracts. Signatures define what an agent does, not how it prompts.

### 2.1 InputField

```python
class InputField:
    def __init__(
        self,
        desc: str = "",
        description: str = None,   # Preferred alias (takes precedence over desc)
        default: Any = None,
        required: bool = True,     # Auto-set to False if default is provided
        **kwargs,                  # Stored in self.metadata
    )
```

**Contracts:**

- If `description` is provided, it takes precedence over `desc` (both stored as `self.desc`).
- If `default` is not None, `required` is forced to False regardless of the passed value.
- Additional kwargs are stored in `self.metadata` for extension points (e.g., validation rules).

### 2.2 OutputField

```python
class OutputField:
    def __init__(
        self,
        desc: str = "",
        description: str = None,   # Preferred alias
        **kwargs,                  # Stored in self.metadata
    )
```

**Contracts:**

- Same `desc`/`description` precedence as InputField.
- OutputFields have no `default` or `required` attributes -- all outputs are always produced.

### 2.3 Signature (metaclass: SignatureMeta)

Two creation patterns:

**Class-based (recommended, DSPy-inspired):**

```python
class QASignature(Signature):
    """You are a helpful assistant."""            # docstring -> instructions

    __intent__ = "Answer user questions"          # WHY (Journey Orchestration)
    __guidelines__ = [                            # HOW (behavioral constraints)
        "Be concise",
        "Cite sources when possible",
    ]

    question: str = InputField(description="User question")
    context: str = InputField(description="Supporting context", default="")
    answer: str = OutputField(description="Clear, accurate answer")
    confidence: float = OutputField(description="Confidence score 0.0-1.0")
```

**Programmatic (backward compatible):**

```python
sig = Signature(
    inputs=["question", "context"],
    outputs=["answer", "confidence"],
    name="QASignature",
    description="Q&A workflow",
)
```

#### SignatureMeta Metaclass

Processes class definitions at creation time:

1. Walks the MRO chain in reverse order (base to derived) to merge fields.
2. Child class fields override parent fields with the same name.
3. Extracts `__intent__` and `__guidelines__` class attributes (inherit from parents if not defined).
4. Stores results in `_signature_inputs`, `_signature_outputs`, `_signature_description`, `_signature_intent`, `_signature_guidelines` class variables.

#### Signature Constructor

```python
def __init__(
    self,
    inputs: Optional[List[str]] = None,
    outputs: Optional[List[Union[str, List[str]]]] = None,
    signature_type: str = "basic",      # basic, multi_io, complex, enterprise, multi_modal
    name: Optional[str] = None,
    description: Optional[str] = None,
    input_types: Optional[Dict[str, Any]] = None,
    output_types: Optional[Dict[str, Any]] = None,
    parameters: Optional[Dict[str, Any]] = None,
    execution_pattern: Optional[str] = None,   # cot, react, etc.
    requires_privacy_check: bool = False,
    requires_audit_trail: bool = False,
    supports_multi_modal: bool = False,
    **kwargs,
)
```

**Contracts:**

- For class-based signatures: `inputs`/`outputs` are auto-populated from field annotations. Passing them explicitly is ignored.
- For programmatic signatures: both `inputs` and `outputs` must be provided or `ValueError` is raised.
- `name` defaults to the class name (class-based) or `signature_{timestamp}` (programmatic).

#### Key Properties

| Property           | Type                          | Description                                      |
| ------------------ | ----------------------------- | ------------------------------------------------ |
| `inputs`           | `List[str]`                   | Input field names                                |
| `outputs`          | `List[Union[str, List[str]]]` | Output field names                               |
| `input_fields`     | `Dict[str, Any]`              | Input field definitions with metadata            |
| `output_fields`    | `Dict[str, Any]`              | Output field definitions with metadata           |
| `has_list_outputs` | `bool`                        | True if any output is a list                     |
| `intent`           | `str`                         | Purpose of the agent (from `__intent__`)         |
| `guidelines`       | `List[str]`                   | Behavioral constraints (copy, prevents mutation) |
| `instructions`     | `str`                         | Docstring-based instructions                     |

#### Signature Inheritance

Signatures support Python class inheritance with proper field merging:

```python
class BaseQA(Signature):
    question: str = InputField(description="Question")
    answer: str = OutputField(description="Answer")

class DetailedQA(BaseQA):
    context: str = InputField(description="Additional context")
    confidence: float = OutputField(description="Confidence")
    # Inherits question and answer from BaseQA
```

### 2.4 SignatureParser

Parses string-based signature notation:

```python
parser = SignatureParser()
result: ParseResult = parser.parse("question, context -> answer, confidence")
```

`ParseResult` fields: `inputs`, `outputs`, `is_valid`, `signature_type`, `error_message`, `has_list_outputs`, `requires_privacy_check`, `requires_audit_trail`, `input_types`, `supports_multi_modal`.

### 2.5 SignatureCompiler

Compiles signatures to Core SDK workflow parameters:

```python
compiler = SignatureCompiler()
params = compiler.compile(signature)
# Returns dict suitable for WorkflowBuilder.add_node("LLMAgentNode", ...)
```

Performance target: <50ms for complex signatures.

### 2.6 SignatureValidator

```python
validator = SignatureValidator()
result: ValidationResult = validator.validate(signature)
```

`ValidationResult` fields: `is_valid`, `errors`, `warnings`, `has_type_checking`, `security_validated`, `privacy_compliance`, `audit_ready`, `multi_modal_supported`, `supported_modalities`, `composition_valid`, `data_flow_valid`.

### 2.7 SignatureTemplate

Reusable signature patterns for common use cases.

### 2.8 Enterprise Extensions

- `EnterpriseSignatureValidator`: Security validation, privacy compliance, audit readiness.
- `MultiModalSignature`: Support for image + audio + text inputs.
- `SignatureComposition`: Combine multiple signatures into pipelines.
- `SignatureRegistry`: Central registry for named signatures.

### 2.9 Multi-Modal Fields

```python
from kaizen.signatures import ImageField, AudioField

class VisionSignature(Signature):
    image: str = ImageField(description="Image to analyze")
    question: str = InputField(description="Question about the image")
    analysis: str = OutputField(description="Image analysis")
```

### 2.10 Execution Patterns

Pre-built patterns that compose signatures with execution strategies:

| Pattern               | Class                         | Description                   |
| --------------------- | ----------------------------- | ----------------------------- |
| Chain of Thought      | `ChainOfThoughtPattern`       | Step-by-step reasoning        |
| ReAct                 | `ReActPattern`                | Reason + Act + Observe cycles |
| RAG Pipeline          | `RAGPipelinePattern`          | Retrieve + Generate           |
| Multi-Agent           | `MultiAgentPattern`           | Coordinate multiple agents    |
| Enterprise Validation | `EnterpriseValidationPattern` | Security + audit              |

Patterns are registered in `PatternRegistry` and accessible via `pattern_registry` singleton.

---

## 18. Structured Output

### 18.1 JSON Schema Generation

```python
from kaizen.core.structured_output import create_structured_output_config

config = create_structured_output_config(
    signature=my_signature,
    strict=True,  # Requires gpt-4o-2024-08-06+
)
# Returns dict suitable for response_format in BaseAgentConfig
```

### 18.2 StructuredOutputGenerator

```python
schema = StructuredOutputGenerator.signature_to_json_schema(signature)
```

Generates OpenAI-compatible JSON schemas from Kaizen signatures. Properties are derived from output fields. All output fields are required. `additionalProperties` is False.

**Contracts:**

- `strict=True` mode provides 100% format compliance but requires specific OpenAI model versions.
- `strict=False` (legacy json_object) provides ~70-85% compliance across all OpenAI models.
- When structured output is enabled, MCP auto-discovery is suppressed (see `kaizen-providers.md` section 10.5).
