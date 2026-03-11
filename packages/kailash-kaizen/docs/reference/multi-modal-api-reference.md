# Multi-Modal API Reference

**Status**: Phase 4 Complete
**Last Updated**: 2025-10-05

---

## 📚 Table of Contents

- [Overview](#overview)
- [Provider APIs](#provider-apis)
- [Agent APIs](#agent-apis)
- [Common Pitfalls](#common-pitfalls)
- [Integration Examples](#integration-examples)

---

## Overview

Kaizen's multi-modal system spans Phases 0-4:
- **Phase 0**: Ollama infrastructure
- **Phase 1**: Signature system (ImageField, AudioField)
- **Phase 2**: Vision processing (OllamaVisionProvider, VisionAgent)
- **Phase 3**: Audio processing (WhisperProcessor, TranscriptionAgent)
- **Phase 4**: Unified orchestration (MultiModalAdapter, MultiModalAgent)

---

## Provider APIs

### OllamaVisionProvider

**Location**: `src/kaizen/providers/ollama_vision_provider.py`

#### Initialization

```python
from kaizen.providers.ollama_vision_provider import OllamaVisionProvider, OllamaVisionConfig

# ✅ CORRECT: Use config object
config = OllamaVisionConfig(model="bakllava")  # or "llava:13b"
provider = OllamaVisionProvider(config=config)

# ❌ WRONG: Direct parameters not supported
provider = OllamaVisionProvider(model="bakllava")  # TypeError!
```

**Config Options**:
```python
@dataclass
class OllamaVisionConfig(OllamaConfig):
    model: str = "llava:13b"      # Vision model name
    max_images: int = 10          # Max images per request
    detail: str = "auto"          # Detail level: auto, low, high
    temperature: float = 0.7      # Generation temperature
```

#### Methods

##### `analyze_image(image, prompt, system=None, **kwargs)`
Analyze a single image with a text prompt.

**Parameters**:
- `image`: `Union[ImageField, str, Path]` - Image to analyze
- `prompt`: `str` - Text question about the image
- `system`: `Optional[str]` - System prompt
- `**kwargs`: Additional parameters (temperature, etc.)

**Returns**: `Dict[str, Any]` with `'response'` key

**Example**:
```python
result = provider.analyze_image(
    image="/path/to/invoice.png",
    prompt="What is the invoice number and total amount?"
)
print(result['response'])  # Model's text response
```

**Image Handling**:
```python
# ✅ File paths (string or Path)
result = provider.analyze_image(image="/path/to/image.png", prompt="...")

# ✅ ImageField objects
from kaizen.signatures.multi_modal import ImageField
img = ImageField()
img.load("/path/to/image.png")
result = provider.analyze_image(image=img, prompt="...")

# ⚠️ NOTE: Ollama expects FILE PATHS, not base64 data URLs
# The provider handles this automatically
```

##### `describe_image(image, detail="auto", **kwargs)`
Generate description of an image.

**Returns**: `str` - Description text

##### `extract_text(image, **kwargs)`
Extract text from image (OCR).

**Returns**: `str` - Extracted text

---

### OllamaMultiModalAdapter

**Location**: `src/kaizen/providers/multi_modal_adapter.py`

#### Initialization

```python
from kaizen.providers.multi_modal_adapter import OllamaMultiModalAdapter

# Initialize with model selection
adapter = OllamaMultiModalAdapter(
    model="bakllava",           # Vision model
    whisper_model="base",       # Audio model size
    auto_download=True          # Auto-download models if missing
)
```

#### Methods

##### `process_multi_modal(image=None, audio=None, text=None, prompt=None, **kwargs)`
Process multi-modal inputs (vision + audio + text).

**Parameters**:
- `image`: `Optional[Union[str, Path, ImageField]]` - Image input
- `audio`: `Optional[Union[str, Path, AudioField]]` - Audio input
- `text`: `Optional[str]` - Text input
- `prompt`: `Optional[str]` - Processing prompt/question
- `**kwargs`: Provider-specific parameters

**Returns**: `Dict[str, Any]` - Combined processing results

**Example**:
```python
# Vision only
result = adapter.process_multi_modal(
    image="/path/to/document.png",
    prompt="Extract the invoice number"
)

# Audio only
result = adapter.process_multi_modal(
    audio="/path/to/recording.wav",
    prompt="Transcribe this audio"
)

# Combined
result = adapter.process_multi_modal(
    image="/path/to/frame.png",
    audio="/path/to/audio.wav",
    prompt="What's happening in this video?"
)
```

##### `estimate_cost(modality, input_size=None, duration=None, **kwargs)`
Estimate processing cost.

**Returns**: `float` - Cost in USD (always $0.00 for Ollama)

---

## Agent APIs

### VisionAgent

**Location**: `src/kaizen/agents/vision_agent.py`

#### Initialization

```python
from kaizen.agents.vision_agent import VisionAgent, VisionAgentConfig

config = VisionAgentConfig(
    llm_provider="ollama",
    model="bakllava",          # or "llava:13b"
    temperature=0.7,
    max_images=5
)

agent = VisionAgent(config=config)
```

#### Methods

##### `analyze(image, question, store_in_memory=True)`
Analyze image and answer question.

**⚠️ CRITICAL**: Parameter is `question`, NOT `prompt`!

**Parameters**:
- `image`: `Union[ImageField, str, Path]` - Image to analyze
- `question`: `str` - Question about the image (NOT "prompt"!)
- `store_in_memory`: `bool` - Store result in agent memory

**Returns**: `Dict[str, Any]` with keys:
- `'answer'`: Model's answer (NOT "response"!)
- `'confidence'`: Confidence score
- `'model'`: Model name
- `'question'`: Original question

**Example**:
```python
# ✅ CORRECT: Use 'question' parameter
result = agent.analyze(
    image="/path/to/invoice.png",
    question="What is the total amount?"  # NOT prompt=...
)
print(result['answer'])  # NOT result['response']

# ❌ WRONG: 'prompt' parameter doesn't exist
result = agent.analyze(image="...", prompt="...")  # TypeError!
```

##### `describe(image, detail="auto")`
Generate description of image.

**Returns**: `str` - Description text

##### `extract_text(image)`
Extract text from image (OCR).

**Returns**: `str` - Extracted text

---

### MultiModalAgent

**Location**: `src/kaizen/agents/multi_modal_agent.py`

#### Initialization

```python
from kaizen.agents.multi_modal_agent import MultiModalAgent, MultiModalConfig
from kaizen.signatures.multi_modal import MultiModalSignature, ImageField
from kaizen.signatures import InputField, OutputField

# Define signature
class InvoiceSignature(MultiModalSignature):
    image: ImageField = InputField(description="Invoice image")
    invoice_number: str = OutputField(description="Invoice number")
    total_amount: str = OutputField(description="Total amount")

# Create config
config = MultiModalConfig(
    llm_provider="ollama",
    model="bakllava",
    prefer_local=True,            # Prefer Ollama over OpenAI
    enable_cost_tracking=True
)

# Create agent
agent = MultiModalAgent(
    config=config,
    signature=InvoiceSignature()
)
```

#### Methods

##### `analyze(image=None, audio=None, text=None, **kwargs)`
Process multi-modal inputs using signature.

**Parameters**:
- `image`: `Optional[Union[str, Path, ImageField]]` - Image input
- `audio`: `Optional[Union[str, Path, AudioField]]` - Audio input
- `text`: `Optional[str]` - Text input
- `**kwargs`: Additional signature fields
- `store_in_memory`: `bool` - Store in SharedMemoryPool

**Returns**: `Dict[str, Any]` - Signature output fields

**Example**:
```python
result = agent.analyze(image="/path/to/invoice.png")
print(result)  # {'invoice_number': '...', 'total_amount': '...'}
```

---

## Common Pitfalls

### 1. OllamaVisionProvider Initialization

**Problem**: Passing parameters directly instead of config object.

```python
# ❌ WRONG - TypeError: unexpected keyword argument 'model'
provider = OllamaVisionProvider(model="bakllava", auto_download=True)

# ✅ CORRECT - Use config object
config = OllamaVisionConfig(model="bakllava")
provider = OllamaVisionProvider(config=config)
```

**Fix Location**: `src/kaizen/providers/multi_modal_adapter.py:142-150`

---

### 2. VisionAgent Parameter Names

**Problem**: Using `prompt` instead of `question`, expecting `response` instead of `answer`.

```python
# ❌ WRONG - TypeError: unexpected keyword argument 'prompt'
result = agent.analyze(image="...", prompt="What do you see?")
print(result['response'])

# ✅ CORRECT - Use 'question' and 'answer'
result = agent.analyze(image="...", question="What do you see?")
print(result['answer'])
```

**API Design**: VisionAgent is designed for Q&A, not generic prompting.

---

### 3. Image Path Handling with Ollama

**Problem**: Converting images to base64 data URLs, but Ollama expects file paths.

```python
# ❌ WRONG - Ollama doesn't accept data URLs
image_field = ImageField()
image_field.load("/path/to/image.png")
provider.analyze_image(image=image_field.to_base64(), prompt="...")
# Error: Invalid image data, expected base64 string or path to image file

# ✅ CORRECT - Pass file path directly
provider.analyze_image(image="/path/to/image.png", prompt="...")

# ✅ ALSO CORRECT - Pass ImageField directly (provider handles it)
image_field = ImageField()
image_field.load("/path/to/image.png")
provider.analyze_image(image=image_field, prompt="...")
```

**Fix Location**: `src/kaizen/providers/ollama_vision_provider.py:79-92`

**Technical Detail**: `ImageField.to_base64()` returns `"data:image/jpeg;base64,..."` format, but Ollama's vision API expects either:
- Plain file path: `/path/to/image.png`
- Plain base64 string: `iVBORw0KGgoAAAANS...` (no prefix)

The provider now extracts file paths directly from ImageField objects.

---

### 4. Response Format Differences

**Problem**: Different APIs return results with different keys.

```python
# OllamaVisionProvider returns 'response'
result = provider.analyze_image(image="...", prompt="...")
text = result['response']  # ✅

# VisionAgent returns 'answer'
result = agent.analyze(image="...", question="...")
text = result['answer']  # ✅

# MultiModalAgent returns signature fields
result = agent.analyze(image="...")
invoice_num = result['invoice_number']  # ✅ (depends on signature)
```

**Recommendation**: Always check the API documentation for the specific component you're using.

---

### 5. Integration Testing Requirements

**Problem**: Unit tests with mocks passing, but real inference failing.

**Example**: Phase 4 had 94 unit tests passing, but 2 critical integration bugs were only found when testing with real Ollama inference.

**Solution**: Always validate with real models before declaring a phase complete.

```python
# ❌ INSUFFICIENT - Mocked tests only
@pytest.mark.unit
def test_vision_processing_mocked():
    provider = MockVisionProvider()
    result = provider.analyze_image(...)
    assert result  # Passes, but doesn't test real API

# ✅ REQUIRED - Real model validation
@pytest.mark.integration
def test_vision_processing_real():
    config = OllamaVisionConfig(model="bakllava")
    provider = OllamaVisionProvider(config=config)

    # Real inference with sample data
    result = provider.analyze_image(
        image="/path/to/test/invoice.png",
        prompt="Extract invoice number and amount"
    )

    # Validate actual model response
    assert 'response' in result
    assert len(result['response']) > 0
    print(f"Model response: {result['response']}")
```

**Best Practice**: Create integration tests with real sample data (invoices, documents, etc.) to validate end-to-end functionality.

---

## Integration Examples

### Example 1: Phase 2 + Phase 4 Integration

Correct way to use OllamaVisionProvider from MultiModalAdapter:

```python
from kaizen.providers.multi_modal_adapter import OllamaMultiModalAdapter
from kaizen.providers.ollama_vision_provider import OllamaVisionConfig

# Phase 4 adapter
adapter = OllamaMultiModalAdapter(model="bakllava")

# Internally creates Phase 2 provider correctly:
# config = OllamaVisionConfig(model=self.model)
# provider = OllamaVisionProvider(config=config)  ✅

# Use adapter
result = adapter.process_multi_modal(
    image="/path/to/image.png",
    prompt="Analyze this image"
)
```

### Example 2: Complete Multi-Modal Pipeline

```python
from kaizen.agents.multi_modal_agent import MultiModalAgent, MultiModalConfig
from kaizen.signatures.multi_modal import MultiModalSignature, ImageField
from kaizen.signatures import InputField, OutputField
from kaizen.memory.shared_memory import SharedMemoryPool
from kaizen.cost.tracker import CostTracker

# Step 1: Define signature
class DocumentOCRSignature(MultiModalSignature):
    image: ImageField = InputField(description="Document to OCR")
    extracted_text: str = OutputField(description="Extracted text")

# Step 2: Setup infrastructure
memory_pool = SharedMemoryPool()
cost_tracker = CostTracker(budget_limit=5.0)

# Step 3: Create agent
config = MultiModalConfig(
    llm_provider="ollama",
    model="bakllava",
    prefer_local=True,
    enable_cost_tracking=True
)

agent = MultiModalAgent(
    config=config,
    signature=DocumentOCRSignature(),
    memory_pool=memory_pool,
    cost_tracker=cost_tracker,
    agent_id="ocr_agent"
)

# Step 4: Process document
result = agent.analyze(
    image="/path/to/invoice.png",
    store_in_memory=True
)

# Step 5: Verify results
print(f"Extracted text: {result['extracted_text']}")
print(f"Cost: ${cost_tracker.get_total_cost():.3f}")  # $0.00 for Ollama
print(f"Memories: {len(memory_pool.retrieve(agent_id='ocr_agent'))}")
```

### Example 3: Real Validation Test

```python
#!/usr/bin/env python3
"""Real Ollama validation with sample data."""

from kaizen.providers.ollama_vision_provider import OllamaVisionProvider, OllamaVisionConfig
from PIL import Image, ImageDraw
import tempfile

# Create test invoice image
img = Image.new('RGB', (800, 600), color='white')
draw = ImageDraw.Draw(img)
draw.text((50, 50), "INVOICE #2025-001", fill='black')
draw.text((50, 100), "Total: $500.00", fill='black')

# Save test image
with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
    img.save(tmp.name)
    test_image = tmp.name

# Test real inference
config = OllamaVisionConfig(model="bakllava")
provider = OllamaVisionProvider(config=config)

result = provider.analyze_image(
    image=test_image,
    prompt="Extract the invoice number and total amount."
)

print(f"Model response: {result['response']}")

# Validate response quality
response_text = result['response'].lower()
has_invoice = 'invoice' in response_text or '2025' in response_text
has_amount = '500' in response_text or '$' in response_text

print(f"Invoice detected: {has_invoice}")
print(f"Amount detected: {has_amount}")
```

---

## Model Accuracy Baselines

Based on real validation with sample invoice data:

| Model | Size | Speed | Accuracy | Use Case |
|-------|------|-------|----------|----------|
| **bakllava** | 4.7GB | Fast (2-4s) | 40-60% | Development, quick testing |
| **llava:13b** | 7GB | Medium (4-8s) | 80-90% | Production, high quality |

**Recommendation**:
- Development/Testing: bakllava (faster, good enough for API validation)
- Production: llava:13b (better accuracy, worth the download)

---

## Troubleshooting

### Error: `TypeError: OllamaVisionProvider.__init__() got an unexpected keyword argument 'model'`

**Cause**: Trying to pass parameters directly instead of config object.

**Fix**:
```python
# Change from:
provider = OllamaVisionProvider(model="bakllava")

# To:
config = OllamaVisionConfig(model="bakllava")
provider = OllamaVisionProvider(config=config)
```

### Error: `TypeError: VisionAgent.analyze() got an unexpected keyword argument 'prompt'`

**Cause**: Using wrong parameter name.

**Fix**:
```python
# Change from:
result = agent.analyze(image="...", prompt="What do you see?")

# To:
result = agent.analyze(image="...", question="What do you see?")
```

### Error: `ValueError: Invalid image data, expected base64 string or path to image file`

**Cause**: Passing base64 data URL to Ollama, which expects file paths.

**Fix**: Ensure OllamaVisionProvider is updated to handle ImageField correctly (fixed in Phase 4 validation).

### Low Model Accuracy

**Symptoms**: Model returns incorrect or random responses.

**Possible Causes**:
1. Using bakllava (smaller model) - **Solution**: Upgrade to llava:13b
2. Poor image quality - **Solution**: Use clearer images with larger text
3. Unclear prompts - **Solution**: Be more explicit in questions

**Example**:
```python
# ❌ Vague prompt
prompt = "What do you see?"

# ✅ Explicit prompt
prompt = "Extract: 1) Invoice number, 2) Total amount. Be specific."
```

---

## API Version History

### Phase 0 (Ollama Setup)
- OllamaProvider base class
- OllamaModelManager

### Phase 1 (Signatures)
- MultiModalSignature
- ImageField
- AudioField

### Phase 2 (Vision)
- OllamaVisionProvider
- OllamaVisionConfig
- VisionAgent
- VisionAgentConfig

### Phase 3 (Audio)
- WhisperProcessor
- TranscriptionAgent
- TranscriptionAgentConfig

### Phase 4 (Orchestration)
- MultiModalAdapter (abstract)
- OllamaMultiModalAdapter
- OpenAIMultiModalAdapter (validation)
- MultiModalAgent
- MultiModalConfig
- CostTracker

### Phase 4 Validation (Bug Fixes)
- Fixed: OllamaVisionProvider initialization in adapter
- Fixed: Image path handling for Ollama
- Added: Real inference validation tests

---

## Best Practices

### 1. Always Use Config Objects
```python
# ✅ Good
config = OllamaVisionConfig(model="bakllava")
provider = OllamaVisionProvider(config=config)

# ❌ Bad
provider = OllamaVisionProvider(model="bakllava")
```

### 2. Check Response Keys
Different APIs return different keys - always check documentation.

### 3. Validate with Real Models
Don't rely solely on mocked tests - always validate with real inference.

### 4. Use Explicit Prompts
Clear, specific prompts improve accuracy significantly.

### 5. Track Costs
Even with free Ollama, use CostTracker to understand usage patterns.

---

**Document Version**: 1.0
**Last Validated**: 2025-10-05 (Phase 4 Real Inference Validation)
**Maintainer**: Kaizen AI Team
