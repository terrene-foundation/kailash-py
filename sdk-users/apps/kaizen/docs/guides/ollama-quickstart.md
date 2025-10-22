# Kaizen Ollama Integration - Quick Start Guide

## Overview

Kaizen now has first-class Ollama support for local LLM processing! This guide shows you how to use Ollama models with Kaizen.

## Installation

### 1. Install Ollama
```bash
# macOS/Linux
curl -fsSL https://ollama.ai/install.sh | sh

# Or download from: https://ollama.ai/download
```

### 2. Start Ollama Service
```bash
ollama serve
```

### 3. Install Kaizen with Ollama Support
```bash
# The ollama package is optional - Kaizen works without it
pip install ollama
```

## Quick Examples

### Example 1: Check if Ollama is Available
```python
from kaizen.providers import OLLAMA_AVAILABLE

if OLLAMA_AVAILABLE:
    print("✅ Ollama is available!")
    from kaizen.providers import OllamaProvider
else:
    print("❌ Install Ollama: https://ollama.ai/download")
```

### Example 2: List Your Models
```python
from kaizen.providers import OllamaModelManager

manager = OllamaModelManager()
models = manager.list_models()

print(f"You have {len(models)} models:")
for model in models:
    size_gb = model.size / (1024 ** 3)
    print(f"  - {model.name} ({size_gb:.2f} GB)")
```

### Example 3: Simple Text Generation
```python
from kaizen.providers import OllamaProvider, OllamaConfig

# Use any model you have installed
config = OllamaConfig(model="llama3.2")
provider = OllamaProvider(config=config)

result = provider.generate("What is artificial intelligence?")
print(result['response'])
```

### Example 4: Streaming Generation
```python
from kaizen.providers import OllamaProvider, OllamaConfig

config = OllamaConfig(model="llama3.2")
provider = OllamaProvider(config=config)

print("AI: ", end='', flush=True)
for chunk in provider.generate_stream("Tell me a short story about robots"):
    print(chunk, end='', flush=True)
print()
```

### Example 5: Download Vision Models
```python
from kaizen.providers import OllamaModelManager

manager = OllamaModelManager()

# Download llava (best quality, ~7.4GB)
print("Downloading llava:13b...")
manager.download_model('llava:13b')

# Or download bakllava (faster, ~4.7GB)
print("Downloading bakllava...")
manager.download_model('bakllava')

# Or setup both at once
results = manager.setup_vision_models(auto_download=True)
print(f"Vision models ready: {results}")
```

### Example 6: Vision Analysis (Coming in Phase 1)
```python
from kaizen.providers import OllamaProvider, OllamaConfig
from kaizen.providers import OllamaModelManager

# Ensure vision model is available
manager = OllamaModelManager()
manager.ensure_model_available('llava:13b')

# Use vision model
config = OllamaConfig(model="llava:13b")
provider = OllamaProvider(config=config)

result = provider.generate_vision(
    prompt="What do you see in this image? Describe in detail.",
    image_path="photo.jpg"
)

print(result['response'])
```

## Configuration Options

```python
from kaizen.providers import OllamaConfig

config = OllamaConfig(
    model="llama3.2",           # Model name
    base_url="http://localhost:11434",  # Ollama server URL
    timeout=120,                # Request timeout (seconds)
    temperature=0.7,            # Sampling temperature (0.0-1.0)
    top_p=0.9                   # Nucleus sampling parameter
)
```

## Common Models

### Text Models
- **llama3.2** - Latest Llama model (2GB)
- **mistral** - Fast and capable (4GB)
- **qwen2.5** - Excellent for code (5GB)
- **phi3** - Small but powerful (2GB)

### Vision Models (Phase 1)
- **llava:13b** - Best quality vision model (7.4GB)
- **bakllava** - Faster vision model (4.7GB)

### Embedding Models
- **nomic-embed-text** - Text embeddings (274MB)
- **snowflake-arctic-embed2** - Advanced embeddings (1.2GB)

## Pull a Model

```bash
# From command line
ollama pull llama3.2
ollama pull llava:13b

# Or from Python
from kaizen.providers import OllamaModelManager
manager = OllamaModelManager()
manager.download_model('llama3.2')
```

## Integration Test

Run the integration test to verify your setup:

```bash
cd apps/kailash-kaizen
python test_ollama_integration.py
```

**Expected Output**:
```
======================================================================
🚀 KAIZEN OLLAMA INTEGRATION TEST SUITE (Phase 0)
======================================================================
✅ OLLAMA_AVAILABLE = True
✅ Ollama CLI is installed
✅ Ollama service is running
✅ Found X models
✅ Text generation working
✅ ALL TESTS PASSED!
```

## Troubleshooting

### "Ollama not available"
```bash
# 1. Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# 2. Start the service
ollama serve

# 3. Verify it's running
ollama list
```

### "No models available"
```bash
# Pull a model
ollama pull llama3.2

# Or use Python
from kaizen.providers import OllamaModelManager
manager = OllamaModelManager()
manager.download_model('llama3.2')
```

### "Connection refused"
```bash
# Make sure Ollama service is running
ollama serve

# Or check if it's already running
ps aux | grep ollama
```

### "Model not found"
```bash
# List available models
ollama list

# Search for models
# Visit: https://ollama.ai/library
```

## Advanced Usage

### Custom Progress Tracking
```python
from kaizen.providers import OllamaModelManager

def my_progress(status: str, percent: float):
    if percent > 0:
        print(f"[{percent:5.1f}%] {status}")
    else:
        print(f"[     ] {status}")

manager = OllamaModelManager()
manager.download_model('llava:13b', progress_callback=my_progress)
```

### Check Model Without Downloading
```python
from kaizen.providers import OllamaModelManager

manager = OllamaModelManager()

# Just check, don't download
if manager.model_exists('llava:13b'):
    print("✅ llava:13b is ready")
else:
    print("❌ llava:13b not installed")
    print("Run: ollama pull llava:13b")
```

### Get Model Information
```python
from kaizen.providers import OllamaModelManager

manager = OllamaModelManager()
info = manager.get_model_info('llama3.2')

if info:
    print(f"Name: {info.name}")
    print(f"Size: {info.size / (1024**3):.2f} GB")
    print(f"Modified: {info.modified}")
    print(f"Digest: {info.digest}")
```

## Next Steps

- **Phase 1**: OllamaBaseAgent integration with BaseAgent
- **Phase 2**: Vision processing workflows
- **Phase 3**: Multi-modal signatures
- **Phase 4**: Advanced vision examples

## Resources

- **Ollama Website**: https://ollama.ai
- **Model Library**: https://ollama.ai/library
- **Kaizen Docs**: `apps/kailash-kaizen/docs/`
- **Phase 0 Report**: `PHASE_0_OLLAMA_COMPLETION_REPORT.md`

## Support

For issues or questions:
1. Check `test_ollama_integration.py` for working examples
2. Review `PHASE_0_OLLAMA_COMPLETION_REPORT.md` for details
3. Run unit tests: `pytest tests/unit/providers/ -v`

---

**Happy Local LLM Processing with Kaizen + Ollama! 🚀**
