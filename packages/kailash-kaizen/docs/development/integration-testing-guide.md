# Integration Testing Guide

**Purpose**: Ensure real model validation catches integration bugs that mocked tests miss
**Last Updated**: 2025-10-05 (Phase 4 Validation Lessons)

---

## 🎯 Why Integration Testing Matters

### The Phase 4 Lesson

**Situation**: Phase 4 declared "complete" with 94 unit tests passing (100%).

**Problem**: All tests used mocks - NO real model inference validation.

**Result**: When validating with real Ollama inference:
- ❌ 2 critical API integration bugs found
- ❌ Image path handling broken
- ❌ Real model responses never tested

**Lesson**: **Unit tests validate implementation, integration tests validate reality.**

---

## 📋 Integration Testing Requirements

### Definition

**Integration Test**: Tests that use REAL infrastructure:
- Real Ollama models (bakllava, llava:13b)
- Real Whisper transcription
- Real file I/O
- Real model inference
- **NO MOCKING** of core functionality

### When Required

Integration tests are REQUIRED before declaring a phase complete when:
1. ✅ New provider APIs added (Phase 2: OllamaVisionProvider)
2. ✅ Cross-phase integration (Phase 4: MultiModalAdapter → Phase 2 APIs)
3. ✅ External dependencies (Ollama, Whisper, OpenAI)
4. ✅ Multi-modal processing (image, audio, video)
5. ✅ File handling and I/O

---

## 🏗️ Test Structure

### 3-Tier Testing Strategy

```
Tier 1: Unit Tests (Mocked)
├── Fast (milliseconds)
├── Isolated components
├── Mock all external dependencies
└── Coverage target: 95%+

Tier 2: Integration Tests (Real Local Infrastructure)
├── Medium speed (seconds)
├── Real Ollama models
├── Real file processing
├── NO MOCKING of core functionality
└── Coverage target: Critical paths

Tier 3: End-to-End Tests (Real External Services)
├── Slow (may cost money)
├── Real OpenAI API (limited)
├── Real production workflows
└── Coverage target: Happy paths
```

**Rule**: Tiers 2-3 have **NO MOCKING** policy for core functionality.

---

## ✅ Integration Test Template

### Basic Structure

```python
"""
Integration Tests - Real Ollama Infrastructure

CRITICAL: These tests use REAL models (NO MOCKING).
"""

import pytest
from pathlib import Path
import tempfile

# Check infrastructure availability
try:
    from kaizen.providers import OLLAMA_AVAILABLE
    from kaizen.providers.ollama_model_manager import OllamaModelManager
    IMPORTS_AVAILABLE = True
except ImportError as e:
    IMPORTS_AVAILABLE = False
    import_error = str(e)

pytestmark = [
    pytest.mark.skipif(not IMPORTS_AVAILABLE, reason=f"Imports not available: {import_error if not IMPORTS_AVAILABLE else ''}"),
    pytest.mark.skipif(not OLLAMA_AVAILABLE, reason="Ollama not installed or not running"),
    pytest.mark.integration,  # Mark as integration test
]


@pytest.fixture(scope="module")
def ensure_vision_model():
    """Ensure vision model is available (download if needed)."""
    manager = OllamaModelManager()

    if not manager.is_ollama_running():
        pytest.skip("Ollama is not running")

    # Check for vision model
    if not manager.model_exists("bakllava"):
        if not manager.model_exists("llava:13b"):
            pytest.skip(
                "No vision model available. Download with: "
                "ollama pull bakllava (or llava:13b)"
            )
            return "llava:13b"
        return "llava:13b"
    return "bakllava"


@pytest.fixture
def test_image(tmp_path):
    """Create test image with clear text."""
    from PIL import Image, ImageDraw

    img = Image.new('RGB', (800, 600), color='white')
    draw = ImageDraw.Draw(img)

    # Add clear test data
    draw.text((50, 50), "INVOICE #2025-001", fill='black')
    draw.text((50, 100), "Total: $500.00", fill='black')

    image_path = tmp_path / "test_invoice.png"
    img.save(image_path)
    return str(image_path)


class TestRealVisionProcessing:
    """Test real vision processing with Ollama."""

    def test_ollama_vision_provider_real_inference(self, ensure_vision_model, test_image):
        """Test REAL vision inference with sample data."""
        from kaizen.providers.ollama_vision_provider import OllamaVisionProvider, OllamaVisionConfig

        # Create provider with real model
        config = OllamaVisionConfig(model=ensure_vision_model)
        provider = OllamaVisionProvider(config=config)

        # Real inference
        result = provider.analyze_image(
            image=test_image,
            prompt="Extract the invoice number and total amount from this invoice."
        )

        # Validate response structure
        assert 'response' in result, "Response should have 'response' key"
        assert isinstance(result['response'], str), "Response should be string"
        assert len(result['response']) > 0, "Response should not be empty"

        # Validate response content (lenient for bakllava)
        response_text = result['response'].lower()
        has_content = (
            'invoice' in response_text or
            '2025' in response_text or
            '500' in response_text or
            len(response_text) > 10
        )
        assert has_content, f"Response should have relevant content: {result['response']}"

        # Log for manual validation
        print(f"\n{'='*60}")
        print(f"Model: {ensure_vision_model}")
        print(f"Response: {result['response']}")
        print(f"{'='*60}\n")
```

---

## 🔍 Sample Data Creation

### Good Test Images

```python
from PIL import Image, ImageDraw, ImageFont

def create_invoice_image(output_path: str):
    """Create high-quality test invoice image."""
    img = Image.new('RGB', (800, 600), color='white')
    draw = ImageDraw.Draw(img)

    # Try to use larger font
    try:
        font_large = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 32)
        font_medium = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 24)
    except:
        font_large = ImageFont.load_default()
        font_medium = ImageFont.load_default()

    # Draw structured content
    y = 50
    draw.text((50, y), "INVOICE #2025-001", fill='black', font=font_large)
    y += 80

    invoice_lines = [
        "Date: January 15, 2025",
        "Due: February 15, 2025",
        "",
        "Bill To: Acme Corp",
        "123 Business Street",
        "",
        "Item: Software License",
        "Amount: $500.00",
        "",
        "TOTAL: $500.00"
    ]

    for line in invoice_lines:
        draw.text((50, y), line, fill='black', font=font_medium)
        y += 40

    # Add border
    draw.rectangle([30, 30, 770, 570], outline='black', width=3)

    img.save(output_path)
    return output_path
```

**Best Practices**:
- ✅ Large, clear text (32pt+ for headings)
- ✅ Structured layout (headers, sections)
- ✅ High contrast (black on white)
- ✅ Realistic content (invoice numbers, amounts, dates)
- ❌ Avoid small fonts (<16pt)
- ❌ Avoid complex backgrounds
- ❌ Avoid random/meaningless text

---

## 📊 Validation Strategies

### 1. Lenient Content Validation

For smaller models (bakllava), use lenient validation:

```python
# ❌ Too strict for smaller models
assert result['response'] == "Invoice #2025-001, Total: $500.00"

# ✅ Lenient validation for bakllava
response = result['response'].lower()
has_invoice_ref = 'invoice' in response or '2025' in response
has_amount_ref = '500' in response or '$' in response

assert has_invoice_ref or has_amount_ref, \
    f"Response should mention invoice or amount: {result['response']}"
```

### 2. API Structure Validation

Always validate response structure:

```python
def test_response_structure(self, provider, test_image):
    """Validate response has correct structure."""
    result = provider.analyze_image(image=test_image, prompt="Describe this.")

    # Structure validation (always required)
    assert isinstance(result, dict), "Response should be dict"
    assert 'response' in result, "Should have 'response' key"
    assert isinstance(result['response'], str), "Response should be string"

    # Content validation (may vary by model)
    assert len(result['response']) > 0, "Response should not be empty"
```

### 3. Model Quality Baselines

Document expected accuracy for each model:

```python
def test_extraction_accuracy_baseline(self, provider, test_image):
    """Document extraction accuracy baseline."""
    result = provider.analyze_image(
        image=test_image,
        prompt="Extract: 1) Invoice number, 2) Total amount"
    )

    response = result['response'].lower()

    # Check detection (lenient)
    invoice_detected = '2025' in response or 'invoice' in response
    amount_detected = '500' in response or '$' in response

    # Document baseline (don't fail test)
    accuracy = sum([invoice_detected, amount_detected]) / 2 * 100
    print(f"\nModel: {provider.vision_config.model}")
    print(f"Accuracy baseline: {accuracy:.0f}%")
    print(f"Invoice detected: {invoice_detected}")
    print(f"Amount detected: {amount_detected}")

    # Baseline expectations
    if provider.vision_config.model == "bakllava":
        # bakllava baseline: 40-60%
        assert accuracy >= 40, "bakllava should achieve at least 40% detection"
    elif provider.vision_config.model == "llava:13b":
        # llava:13b baseline: 80-90%
        assert accuracy >= 80, "llava:13b should achieve at least 80% accuracy"
```

---

## 🐛 Bug Detection Patterns

### Pattern 1: API Signature Mismatches

**What to Test**:
```python
def test_api_signature_compatibility(self):
    """Test that APIs are called with correct parameters."""
    from kaizen.providers.ollama_vision_provider import OllamaVisionProvider, OllamaVisionConfig

    # This should NOT raise TypeError
    config = OllamaVisionConfig(model="bakllava")
    provider = OllamaVisionProvider(config=config)

    # Verify provider initialized correctly
    assert provider.vision_config.model == "bakllava"
```

**What This Catches**: Parameter naming issues, missing config objects.

### Pattern 2: Data Format Mismatches

**What to Test**:
```python
def test_image_path_handling(self, provider, test_image):
    """Test that image paths are handled correctly."""
    # Test with file path string
    result1 = provider.analyze_image(image=test_image, prompt="Describe")
    assert 'response' in result1

    # Test with Path object
    from pathlib import Path
    result2 = provider.analyze_image(image=Path(test_image), prompt="Describe")
    assert 'response' in result2

    # Test with ImageField
    from kaizen.signatures.multi_modal import ImageField
    img = ImageField()
    img.load(test_image)
    result3 = provider.analyze_image(image=img, prompt="Describe")
    assert 'response' in result3
```

**What This Catches**: Base64 encoding issues, file path problems.

### Pattern 3: Cross-Component Integration

**What to Test**:
```python
def test_phase2_phase4_integration(self, test_image):
    """Test that Phase 4 adapter correctly uses Phase 2 provider."""
    from kaizen.providers.multi_modal_adapter import OllamaMultiModalAdapter

    # Create Phase 4 adapter
    adapter = OllamaMultiModalAdapter(model="bakllava")

    # Should internally create Phase 2 provider correctly
    result = adapter.process_multi_modal(
        image=test_image,
        prompt="Analyze this image"
    )

    # Verify it worked
    assert result is not None
    assert isinstance(result, dict)
```

**What This Catches**: Integration bugs between phases, incorrect API usage.

---

## ⚡ Performance Baselines

### Expected Response Times

```python
import time

def test_performance_baseline(self, provider, test_image):
    """Document performance baseline for model."""
    start = time.time()

    result = provider.analyze_image(image=test_image, prompt="Describe this.")

    elapsed = time.time() - start

    print(f"\nModel: {provider.vision_config.model}")
    print(f"Response time: {elapsed:.2f}s")

    # Baseline expectations
    if provider.vision_config.model == "bakllava":
        assert elapsed < 30, "bakllava should respond within 30s"
    elif provider.vision_config.model == "llava:13b":
        assert elapsed < 60, "llava:13b should respond within 60s"
```

**Baselines** (local GPU):
- bakllava: 2-4s typical, 30s max
- llava:13b: 4-8s typical, 60s max

---

## 🎯 Checklist for Phase Completion

Before declaring a phase complete:

### Unit Testing (Tier 1)
- [ ] 95%+ code coverage
- [ ] All edge cases tested
- [ ] Mock external dependencies
- [ ] Fast execution (<1s total)

### Integration Testing (Tier 2)
- [ ] Real model inference tested
- [ ] Sample data validated
- [ ] API integrations verified
- [ ] Cross-phase compatibility tested
- [ ] Performance baselines documented

### Validation
- [ ] Manual testing with real data
- [ ] Response quality assessed
- [ ] Common use cases verified
- [ ] Documentation updated

### Phase 4 Example

**Before Validation**:
- ✅ 94 unit tests passing
- ❌ No real model validation
- ❌ Integration bugs undiscovered

**After Validation**:
- ✅ 94 unit tests passing
- ✅ Real model inference validated
- ✅ 2 integration bugs found and fixed
- ✅ Response quality documented

**Time Investment**: 2h validation found bugs that would have cost days in production.

---

## 📝 Test Organization

### Directory Structure

```
tests/
├── unit/                       # Tier 1: Mocked tests
│   ├── providers/
│   │   ├── test_ollama_vision_provider.py  # Mocked
│   │   └── test_multi_modal_adapter.py     # Mocked
│   └── agents/
│       └── test_vision_agent.py            # Mocked
│
├── integration/                # Tier 2: Real local infrastructure
│   ├── test_ollama_validation.py           # Real Ollama
│   ├── test_vision_real.py                 # Real vision models
│   └── test_multi_modal_real.py            # Real multi-modal
│
└── e2e/                        # Tier 3: Real external services
    └── test_openai_validation.py           # Real OpenAI (limited)
```

### Markers

```python
# Tier 1: Unit tests (default)
def test_something():
    pass

# Tier 2: Integration tests
@pytest.mark.integration
def test_real_infrastructure():
    pass

# Tier 3: E2E tests (may cost money)
@pytest.mark.e2e
@pytest.mark.expensive  # Requires budget approval
def test_openai_integration():
    pass
```

### Running Tests

```bash
# Run only unit tests (fast)
pytest tests/unit/ -v

# Run integration tests (requires Ollama)
pytest tests/integration/ -v -m integration

# Run all tests except expensive
pytest -v -m "not expensive"

# Run specific integration test
pytest tests/integration/test_ollama_validation.py::TestOllamaValidationSummary -v
```

---

## 🏆 Success Criteria

### Integration Test Quality

**Good Integration Test**:
- ✅ Uses real models (Ollama, Whisper)
- ✅ Tests with sample data
- ✅ Validates response structure
- ✅ Documents quality baselines
- ✅ Catches API mismatches
- ✅ Runs in <60s

**Bad Integration Test**:
- ❌ Mocks core functionality
- ❌ No sample data
- ❌ Only checks "not None"
- ❌ No quality assessment
- ❌ Doesn't test integration points

### Coverage Targets

| Test Tier | Coverage Target | Purpose |
|-----------|----------------|---------|
| **Unit (Tier 1)** | 95%+ code | Validate implementation |
| **Integration (Tier 2)** | Critical paths | Validate reality |
| **E2E (Tier 3)** | Happy paths | Validate production |

---

## 📚 Additional Resources

- [Multi-Modal API Reference](./multi-modal-api-reference.md) - API signatures and common pitfalls
- [Troubleshooting Guide](../reference/troubleshooting.md) - Common errors and fixes
- [Testing Strategy (ADR-005)](../architecture/adr/ADR-005-testing-strategy-alignment.md) - 3-tier approach

---

**Document Version**: 1.0
**Created**: 2025-10-05 (Phase 4 Validation Lessons)
**Maintainer**: Kaizen AI Team
