# Audio Transcription Example

This example demonstrates speech-to-text transcription using Kaizen with local Whisper models.

## Features

- **Speech-to-Text**: Convert audio to text using Whisper
- **Multi-Language Support**: Supports 99+ languages
- **Word-Level Timestamps**: Get precise timing for each word
- **Language Detection**: Automatically detect audio language
- **Batch Processing**: Transcribe multiple files efficiently

## Requirements

Install faster-whisper for local transcription:

```bash
pip install faster-whisper
```

For GPU acceleration (optional):

```bash
# CUDA support
pip install faster-whisper[cuda]
```

## Usage

Run the example:

```bash
python workflow.py
```

The example will:
1. Create sample audio files for testing
2. Transcribe basic speech-to-text
3. Show word-level timestamps
4. Detect language
5. Process multiple files in batch

## Whisper Model Sizes

Choose the model size based on your needs:

| Model  | Parameters | Speed    | Accuracy | Memory  |
|--------|-----------|----------|----------|---------|
| tiny   | 39M       | ~32x     | Low      | ~1 GB   |
| base   | 74M       | ~16x     | Good     | ~1 GB   |
| small  | 244M      | ~6x      | Better   | ~2 GB   |
| medium | 769M      | ~2x      | Great    | ~5 GB   |
| large  | 1550M     | ~1x      | Best     | ~10 GB  |

Speed is relative to real-time on CPU.

## Example Output

```
=== Kaizen Audio Transcription Example ===

1. Basic Speech-to-Text
----------------------------------------
Text: Hello, this is a test of the audio transcription system.
Language: en (95.00%)
Duration: 5.2s
Confidence: 0.85

2. Transcription with Word Timestamps
----------------------------------------

Segment 1 [0.0s - 2.5s]:
  Text: Hello, this is a test
  Words:
    Hello [0.00s]
    this [0.50s]
    is [0.80s]
    a [1.00s]
    test [1.50s]

3. Language Detection
----------------------------------------
Detected: en (98.00%)

4. Batch Transcription
----------------------------------------

File 1: The quick brown fox jumps over the lazy dog...
  Language: en, Duration: 3.2s

File 2: Bonjour, comment allez-vous aujourd'hui...
  Language: fr, Duration: 2.8s

=== Audio Transcription Complete ===
```

## Integration with Kaizen

The `TranscriptionAgent` integrates seamlessly with Kaizen:

```python
from kaizen.agents.transcription_agent import (
    TranscriptionAgent,
    TranscriptionAgentConfig
)

# Create agent
config = TranscriptionAgentConfig(
    model_size="base",
    device="cpu",
    word_timestamps=True
)
agent = TranscriptionAgent(config)

# Transcribe
result = agent.transcribe("audio.mp3")
print(result["text"])

# Batch process
results = agent.transcribe_batch(["audio1.mp3", "audio2.mp3"])
```

## Performance Tips

1. **Model Selection**: Start with `tiny` or `base` for testing
2. **GPU Acceleration**: Use CUDA if available for faster processing
3. **Batch Processing**: Process multiple files to amortize model loading
4. **Audio Quality**: Higher quality audio = better transcription

## Multi-Modal Integration

Combine with other Kaizen capabilities:

```python
# Transcribe + Vision Analysis
transcription_agent = TranscriptionAgent(config)
vision_agent = VisionAgent(vision_config)

# Process audio
audio_result = transcription_agent.transcribe("meeting.mp3")

# Analyze related images
image_result = vision_agent.analyze("presentation.png")

# Combine insights
combined = {
    "transcript": audio_result["text"],
    "visual_notes": image_result["description"]
}
```

## Troubleshooting

**Issue**: Model download fails
- **Solution**: Check internet connection, models are downloaded on first use

**Issue**: Slow transcription
- **Solution**: Use smaller model or enable GPU acceleration

**Issue**: Poor accuracy
- **Solution**: Use larger model (small/medium) or improve audio quality

**Issue**: Language detection wrong
- **Solution**: Provide explicit language hint: `agent.transcribe(audio, language="en")`

## Next Steps

- Explore **multi-language** transcription
- Try **translation** to English (task="translate")
- Integrate with **RAG** for audio-based Q&A
- Build **meeting summarization** workflows
