"""
Quick start guide for using vision with LLMs in Kailash SDK.

Prerequisites:
- Set OPENAI_API_KEY or ANTHROPIC_API_KEY environment variable
- Have an image file ready (or use the sample created here)
"""

import os
import sys

# Add src to path
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
)

from kailash.nodes.ai import LLMAgentNode


# Create a simple test image (optional - you can use your own)
def create_test_image():
    try:
        from PIL import Image, ImageDraw

        img = Image.new("RGB", (100, 100), "red")
        draw = ImageDraw.Draw(img)
        draw.rectangle([25, 25, 75, 75], fill="blue")
        img.save("test_image.png")
        return "test_image.png"
    except ImportError:
        return "your_image.png"  # Use your own image


# Quick example 1: Analyze an image
def analyze_image_simple():
    print("🖼️ Simple Image Analysis")

    agent = LLMAgentNode()
    image_path = create_test_image()

    # The key change: content is now a list with text and image items
    result = agent.run(
        provider="openai",  # or "anthropic" or "ollama"
        model="gpt-4o-mini",  # or "claude-3-haiku-20240307" or "llama3.2-vision"
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What do you see in this image?"},
                    {"type": "image", "path": image_path},
                ],
            }
        ],
    )

    if result["success"]:
        print(f"AI Response: {result['response']['content']}")
    else:
        print(f"Error: {result['error']}")


# Quick example 2: Compare two images
def compare_images_simple():
    print("\n📊 Comparing Two Images")

    agent = LLMAgentNode()

    # Create two simple images
    try:
        from PIL import Image

        # Image 1: Red background
        img1 = Image.new("RGB", (50, 50), "red")
        img1.save("img1.png")

        # Image 2: Blue background
        img2 = Image.new("RGB", (50, 50), "blue")
        img2.save("img2.png")

        result = agent.run(
            provider="anthropic",
            model="claude-3-haiku-20240307",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "What's the difference between these images?",
                        },
                        {"type": "image", "path": "img1.png"},
                        {"type": "image", "path": "img2.png"},
                    ],
                }
            ],
        )

        if result["success"]:
            print(f"AI Response: {result['response']['content']}")

    except ImportError:
        print("PIL not available for creating test images")


# Quick example 3: Using base64 images
def use_base64_image():
    print("\n🔤 Using Base64 Encoded Image")

    import base64

    agent = LLMAgentNode()

    # Read an image and convert to base64
    with open(create_test_image(), "rb") as f:
        image_base64 = base64.b64encode(f.read()).decode("utf-8")

    result = agent.run(
        provider="openai",
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image"},
                    {
                        "type": "image",
                        "base64": image_base64,
                        "media_type": "image/png",
                    },
                ],
            }
        ],
    )

    if result["success"]:
        print(f"AI Response: {result['response']['content']}")


if __name__ == "__main__":
    print("🚀 Kailash Vision Quick Start")
    print("=" * 40)

    # Check for API keys
    if not (os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")):
        print("⚠️  Please set OPENAI_API_KEY or ANTHROPIC_API_KEY environment variable")
        print("   export OPENAI_API_KEY='your-key-here'")
        print("   export ANTHROPIC_API_KEY='your-key-here'")
    else:
        analyze_image_simple()
        compare_images_simple()
        use_base64_image()

        # Cleanup
        import os

        for f in ["test_image.png", "img1.png", "img2.png"]:
            if os.path.exists(f):
                os.remove(f)

        print("\n✅ Done! Now try with your own images!")
        print("\n💡 Tips:")
        print("- OpenAI: Use o4-mini or gpt-4-vision-preview")
        print("- Anthropic: All Claude 3 models support vision")
        print("- Ollama: Use llama3.2-vision, bakllava, or llava")
        print("- Keep images under 20MB for best results")
