# Multi-Modal API Reference

Complete reference for Kaizen's multi-modal processing capabilities (vision and audio).

## 🎯 Overview

Kaizen supports multi-modal processing through specialized agents:
- **VisionAgent**: Image analysis (Ollama + OpenAI GPT-4V)
- **TranscriptionAgent**: Audio transcription (Whisper)

## 🖼️ Vision Processing

### VisionAgent API

```python
from kaizen.agents import VisionAgent, VisionAgentConfig

# Initialize agent
config = VisionAgentConfig(
    llm_provider="ollama",  # or "openai"
    model="bakllava"        # or "llava" for Ollama, "gpt-4o" for OpenAI
)
agent = VisionAgent(config=config)

# Analyze image
result = agent.analyze(
    image="/path/to/image.png",  # File path (NOT base64)
    question="What is in this image?"  # 'question' parameter (NOT 'prompt')
)

# Access result
answer = result['answer']  # 'answer' key (NOT 'response')
```

### Supported Providers

#### Ollama (Free, Local)

**Models**: `llava`, `bakllava`
**Requirements**: Ollama must be installed and running locally

```python
config = VisionAgentConfig(
    llm_provider="ollama",
    model="bakllava"  # Recommended for better quality
)
```

**Installation**:
```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull vision model
ollama pull bakllava
```

#### OpenAI (Paid, Cloud)

**Models**: `gpt-4o`, `gpt-4-turbo`
**Requirements**: OpenAI API key in `.env`

```python
config = VisionAgentConfig(
    llm_provider="openai",
    model="gpt-4o"  # Latest vision model
)
```

### Complete API Signature

```python
def analyze(
    self,
    image: str,           # File path to image
    question: str,        # Question about the image
    session_id: Optional[str] = None  # Optional session for memory
) -> dict:
    """
    Analyze an image and answer questions about it.

    Args:
        image: Path to image file (PNG, JPG, etc.)
        question: What you want to know about the image
        session_id: Optional session ID for memory continuity

    Returns:
        {
            'answer': str,      # Answer to your question
            'confidence': float # Confidence score 0.0-1.0 (if available)
        }
    """
```

### Usage Examples

**Receipt Analysis:**
```python
result = agent.analyze(
    image="/path/to/receipt.jpg",
    question="What is the total amount?"
)
print(result['answer'])  # "$42.99"
```

**Document Understanding:**
```python
result = agent.analyze(
    image="/path/to/invoice.png",
    question="Extract all line items with quantities and prices"
)
print(result['answer'])
```

**Image Description:**
```python
result = agent.analyze(
    image="/path/to/photo.jpg",
    question="Describe what you see in detail"
)
print(result['answer'])
```

## 🎵 Audio Processing

### TranscriptionAgent API

```python
from kaizen.agents import TranscriptionAgent, TranscriptionAgentConfig

# Initialize agent
config = TranscriptionAgentConfig()  # Uses Whisper by default
agent = TranscriptionAgent(config=config)

# Transcribe audio
result = agent.transcribe(
    audio_path="/path/to/audio.mp3"
)

# Access result
transcription = result['transcription']
duration = result['duration']
language = result['language']
```

### Supported Audio Formats

- MP3
- WAV
- M4A
- FLAC
- OGG

### Complete API Signature

```python
def transcribe(
    self,
    audio_path: str  # Path to audio file
) -> dict:
    """
    Transcribe audio file to text.

    Args:
        audio_path: Path to audio file

    Returns:
        {
            'transcription': str,  # Full text transcription
            'duration': float,     # Audio duration in seconds
            'language': str        # Detected language code
        }
    """
```

### Usage Examples

**Meeting Transcription:**
```python
result = agent.transcribe(audio_path="/path/to/meeting.mp3")
print(result['transcription'])
```

**Interview Processing:**
```python
result = agent.transcribe(audio_path="/path/to/interview.wav")
print(f"Duration: {result['duration']} seconds")
print(f"Language: {result['language']}")
print(result['transcription'])
```

## ⚠️ Common Pitfalls

### 1. Wrong Vision API Parameters

**❌ WRONG:**
```python
# Using 'prompt' instead of 'question'
result = agent.analyze(image="/path/to/image.png", prompt="What is this?")

# Using 'response' key instead of 'answer'
answer = result['response']

# Passing base64 string instead of file path
result = agent.analyze(image=base64_encoded_string, question="...")
```

**✅ CORRECT:**
```python
# Use 'question' parameter
result = agent.analyze(image="/path/to/image.png", question="What is this?")

# Use 'answer' key
answer = result['answer']

# Use file path (NOT base64)
result = agent.analyze(image="/path/to/image.png", question="...")
```

### 2. Missing Ollama Installation

**Error:**
```
ConnectionError: Could not connect to Ollama
```

**Solution:**
```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama service
ollama serve

# Pull vision model
ollama pull bakllava
```

### 3. Missing OpenAI API Key

**Error:**
```
AuthenticationError: No API key provided
```

**Solution:**
```python
# Create .env file with API key
# OPENAI_API_KEY=sk-...

from dotenv import load_dotenv
load_dotenv()  # Load before creating agent

config = VisionAgentConfig(llm_provider="openai", model="gpt-4o")
agent = VisionAgent(config=config)
```

### 4. Image File Not Found

**Error:**
```
FileNotFoundError: Image file not found
```

**Solution:**
```python
import os

# Verify file exists
image_path = "/path/to/image.png"
if not os.path.exists(image_path):
    print(f"File not found: {image_path}")

# Use absolute paths
image_path = os.path.abspath("images/photo.jpg")
result = agent.analyze(image=image_path, question="...")
```

### 5. Audio File Format Not Supported

**Error:**
```
ValueError: Unsupported audio format
```

**Solution:**
```python
# Convert to supported format (MP3, WAV, M4A, FLAC, OGG)
# Using ffmpeg:
# ffmpeg -i input.avi -acodec mp3 output.mp3

result = agent.transcribe(audio_path="/path/to/audio.mp3")
```

## 🔧 Configuration Reference

### VisionAgentConfig

```python
@dataclass
class VisionAgentConfig:
    llm_provider: str = "ollama"  # "ollama" or "openai"
    model: str = "bakllava"       # Model name
    temperature: float = 0.7      # Creativity (0.0-1.0)
    max_tokens: int = 500         # Maximum response length
    timeout: int = 30             # Request timeout (seconds)
```

### TranscriptionAgentConfig

```python
@dataclass
class TranscriptionAgentConfig:
    model: str = "whisper"        # Transcription model
    language: Optional[str] = None  # Force specific language (auto-detect if None)
```

## 📊 Performance Characteristics

### Vision Processing

**Ollama (Local):**
- Speed: ~2-5 seconds per image
- Cost: Free
- Quality: Good for most use cases
- Requires: Local installation, ~4GB RAM

**OpenAI (Cloud):**
- Speed: ~1-2 seconds per image
- Cost: ~$0.01-0.02 per image
- Quality: Excellent
- Requires: API key, internet connection

### Audio Transcription

**Whisper:**
- Speed: ~0.5x real-time (1 min audio → ~30 sec processing)
- Cost: Free (local processing)
- Quality: Excellent
- Supports: 90+ languages

## 🧪 Testing Multi-Modal Agents

```python
import pytest
from kaizen.agents import VisionAgent, VisionAgentConfig

def test_vision_agent():
    """Test vision agent with sample image."""
    config = VisionAgentConfig(llm_provider="ollama", model="bakllava")
    agent = VisionAgent(config=config)

    result = agent.analyze(
        image="test_images/sample.png",
        question="What color is dominant in this image?"
    )

    assert 'answer' in result
    assert isinstance(result['answer'], str)
    assert len(result['answer']) > 0

def test_transcription_agent():
    """Test transcription agent with sample audio."""
    config = TranscriptionAgentConfig()
    agent = TranscriptionAgent(config=config)

    result = agent.transcribe(audio_path="test_audio/sample.mp3")

    assert 'transcription' in result
    assert 'duration' in result
    assert 'language' in result
```

## 🔗 Related Documentation

- **[README.md](../../README.md)** - Complete Kaizen guide
- **[Quickstart](../getting-started/quickstart.md)** - Getting started tutorial
- **[Troubleshooting](troubleshooting.md)** - Common issues and solutions
- **[Examples](../../../../apps/kailash-kaizen/examples/8-multi-modal/)** - Working multi-modal examples

---

**Need help?** Check [Troubleshooting](troubleshooting.md) or review [Working Examples](../../../../apps/kailash-kaizen/examples/8-multi-modal/).
