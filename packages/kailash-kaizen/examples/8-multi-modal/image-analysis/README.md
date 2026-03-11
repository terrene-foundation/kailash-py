# Image Analysis Example - Ollama Vision

This example demonstrates vision processing with Kaizen using Ollama's llava model.

## Features

- **Image Description**: Generate detailed descriptions of images
- **Visual Question Answering**: Answer questions about images
- **Text Extraction (OCR)**: Extract text from images
- **Object Detection**: Identify objects in images
- **Batch Analysis**: Process multiple images efficiently

## Requirements

- Ollama installed and running
- llava:13b model downloaded (`ollama pull llava:13b`)
- Kaizen with Ollama support

## Installation

```bash
# Install Ollama (if not already installed)
# Visit: https://ollama.ai/download

# Pull the vision model
ollama pull llava:13b

# Install Kaizen
pip install kailash-kaizen
```

## Usage

```bash
# Run the example
python workflow.py
```

## Example Output

```
=== Kaizen Vision Processing Example ===

1. Image Description
----------------------------------------
Description: A vibrant landscape with rolling hills and a clear blue sky.

2. Visual Question Answering
----------------------------------------
Question: What components are shown in this architecture diagram?
Answer: The diagram shows three main components: API Gateway, Processing Engine, and Database Layer, connected with bidirectional arrows.
Confidence: 0.85

3. Text Extraction (OCR)
----------------------------------------
Extracted text:
INVOICE #12345
Date: 2024-10-05
Total: $1,234.56

4. Batch Image Analysis
----------------------------------------
Image 1: A red sports car parked in front of a modern building.
Image 2: A group of people collaborating in a meeting room.
Image 3: A sunset over the ocean with vibrant orange and pink hues.

=== Vision Processing Complete ===
```

## Supported Image Formats

- JPEG (.jpg, .jpeg)
- PNG (.png)
- WebP (.webp)

## Performance Notes

- First analysis may take longer due to model loading
- Subsequent analyses are faster (model stays in memory)
- Larger images are automatically resized for optimal performance
- Expected processing time: 2-5 seconds per image

## Advanced Usage

See the workflow.py file for examples of:
- Custom detail levels (brief, detailed, auto)
- Batch processing with different questions
- Error handling and recovery
- Memory integration for storing results

## Troubleshooting

**Model not found error:**
```bash
ollama pull llava:13b
```

**Ollama not running:**
```bash
ollama serve
```

**Image format error:**
Ensure images are in supported formats (JPG, PNG, WebP)
