"""
Image Analysis Example - Ollama Vision

Demonstrates vision processing with Kaizen using Ollama llava model.

Features:
- Image description generation
- Visual question answering
- Text extraction (OCR)
- Object detection

Requirements:
- Ollama installed with llava:13b model
"""

import sys
from pathlib import Path

from kaizen.agents.multi_modal.vision_agent import VisionAgent, VisionAgentConfig
from PIL import Image


def create_sample_images():
    """Create sample images for demonstration."""
    images_dir = Path(__file__).parent / "test_images"
    images_dir.mkdir(exist_ok=True)

    # Create sample colored images
    colors = [("red", (255, 0, 0)), ("blue", (0, 0, 255)), ("green", (0, 255, 0))]

    for color_name, color_rgb in colors:
        img = Image.new("RGB", (200, 200), color=color_rgb)
        img_path = images_dir / f"{color_name}_square.jpg"
        img.save(img_path, format="JPEG")

    # Create a landscape image
    landscape = Image.new("RGB", (400, 300), color=(135, 206, 235))  # Sky blue
    landscape_path = images_dir / "landscape.jpg"
    landscape.save(landscape_path, format="JPEG")

    # Create a document-like image
    document = Image.new("RGB", (600, 400), color=(255, 255, 255))  # White
    document_path = images_dir / "document.jpg"
    document.save(document_path, format="JPEG")

    return images_dir


def main():
    """Run vision processing examples."""
    print("=== Kaizen Vision Processing Example ===\n")

    # Check if Ollama is available
    try:
        import ollama

        # Test connection
        ollama.list()
    except Exception as e:
        print(f"❌ Ollama is not available: {e}")
        print("\nPlease install Ollama and run:")
        print("  ollama pull llama3.1:8b-instruct-q8_0-vision")
        sys.exit(1)

    # Create sample images
    print("Creating sample images...")
    images_dir = create_sample_images()
    print(f"✅ Sample images created in: {images_dir}\n")

    # Create vision agent
    config = VisionAgentConfig(
        model="llama3.2-vision", temperature=0.7  # Using llama3.2-vision model
    )

    try:
        agent = VisionAgent(config)
        print(f"✅ Vision agent created with model: {config.model}\n")
    except RuntimeError as e:
        if "Failed to download" in str(e):
            print(f"❌ Model not available: {e}")
            print("\nPlease run:")
            print("  ollama pull llama3.1:8b-instruct-q8_0-vision")
            sys.exit(1)
        raise

    # Example 1: Image Description
    print("1. Image Description")
    print("-" * 40)

    landscape_path = images_dir / "landscape.jpg"
    description = agent.describe(image=str(landscape_path), detail="detailed")
    print(f"Description: {description}\n")

    # Example 2: Visual Question Answering
    print("2. Visual Question Answering")
    print("-" * 40)

    red_square_path = images_dir / "red_square.jpg"
    result = agent.analyze(
        image=str(red_square_path), question="What is the dominant color in this image?"
    )
    print(f"Question: {result['question']}")
    print(f"Answer: {result['answer']}")
    print(f"Confidence: {result['confidence']}\n")

    # Example 3: Text Extraction (OCR)
    print("3. Text Extraction (OCR)")
    print("-" * 40)

    document_path = images_dir / "document.jpg"
    text = agent.extract_text(image=str(document_path))
    print(f"Extracted text:\n{text}\n")

    # Example 4: Batch Analysis
    print("4. Batch Image Analysis")
    print("-" * 40)

    images = [
        str(images_dir / "red_square.jpg"),
        str(images_dir / "blue_square.jpg"),
        str(images_dir / "green_square.jpg"),
    ]

    results = agent.batch_analyze(
        images=images, question="What is the main color of this image?"
    )

    for i, result in enumerate(results, 1):
        print(f"Image {i}: {result['answer']}")

    print("\n=== Vision Processing Complete ===")
    print(f"\nSample images saved in: {images_dir}")
    print("You can replace these with your own images for testing.")


if __name__ == "__main__":
    main()
