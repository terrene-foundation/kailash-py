"""
Comprehensive example of using vision capabilities with LLM providers in Kailash SDK.

This example demonstrates:
1. Basic image analysis with file paths
2. Using base64 encoded images
3. Multiple image analysis
4. Comparing different providers
5. Error handling and best practices
"""

import base64
import os
import sys
from pathlib import Path

# Add the src directory to Python path for imports
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
)

from kailash.nodes.ai import LLMAgentNode


def create_sample_image():
    """Create a sample image for testing (requires PIL)."""
    try:
        from PIL import Image, ImageDraw, ImageFont

        # Create a simple image with shapes and text
        img = Image.new("RGB", (200, 200), color="white")
        draw = ImageDraw.Draw(img)

        # Draw a red circle
        draw.ellipse([50, 50, 100, 100], fill="red", outline="black")

        # Draw a blue square
        draw.rectangle([120, 50, 170, 100], fill="blue", outline="black")

        # Draw a green triangle
        draw.polygon([(85, 120), (60, 170), (110, 170)], fill="green", outline="black")

        # Add text
        draw.text((70, 10), "Shapes Test", fill="black")

        # Save the image
        img_path = Path("sample_shapes.png")
        img.save(img_path)
        return str(img_path)
    except ImportError:
        print("PIL not available. Using a placeholder image path.")
        return "sample_image.png"


def example_1_basic_image_analysis():
    """Example 1: Basic image analysis with file path."""
    print("\n=== Example 1: Basic Image Analysis ===")

    # Create or use an existing image
    image_path = create_sample_image()

    # Create the LLM agent
    agent = LLMAgentNode()

    # Analyze image with OpenAI
    if os.getenv("OPENAI_API_KEY"):
        print("\nUsing OpenAI (o4-mini):")
        result = agent.run(
            provider="openai",
            model="o4-mini",  # Vision-capable model
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "What shapes and colors do you see in this image? Please list them. Be concise.",
                        },
                        {"type": "image", "path": image_path},
                    ],
                }
            ],
            generation_config={
                "max_completion_tokens": 200,
            },
        )

        if result["success"]:
            print(f"Response: {result['response']['content']}")
            print(f"Tokens used: {result['usage']['total_tokens']}")
        else:
            print(f"Error: {result['error']}")

    # Analyze image with Anthropic
    if os.getenv("ANTHROPIC_API_KEY"):
        print("\nUsing Anthropic (Claude 4):")
        result = agent.run(
            provider="anthropic",
            model="claude-sonnet-4-20250514",  # Fast, vision-capable model
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Describe the geometric shapes in this image. Be concise.",
                        },
                        {"type": "image", "path": image_path},
                    ],
                }
            ],
            generation_config={"max_tokens": 200, "temperature": 0.5},
        )

        if result["success"]:
            print(f"Response: {result['response']['content']}")
        else:
            print(f"Error: {result['error']}")


def example_2_base64_image():
    """Example 2: Using base64 encoded images."""
    print("\n=== Example 2: Base64 Encoded Images ===")

    # Create a small test image
    image_path = create_sample_image()

    # Read and encode the image
    with open(image_path, "rb") as img_file:
        image_data = img_file.read()
        base64_image = base64.b64encode(image_data).decode("utf-8")

    agent = LLMAgentNode()

    # Use base64 image instead of file path
    if os.getenv("OPENAI_API_KEY"):
        result = agent.run(
            provider="openai",
            model="o4-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What's in this image? Be concise."},
                        {
                            "type": "image",
                            "base64": base64_image,
                            "media_type": "image/png",  # Specify the media type
                        },
                    ],
                }
            ],
            generation_config={"max_completion_tokens": 300},
        )

        if result["success"]:
            print(f"Response: {result['response']['content']}")
        else:
            print(f"Error: {result['error']}")
    else:
        print("OpenAI API key not set, skipping base64 example")


def example_3_multiple_images():
    """Example 3: Analyzing multiple images."""
    print("\n=== Example 3: Multiple Images Analysis ===")

    # Create two different images
    try:
        from PIL import Image, ImageDraw

        # Image 1: Circles
        img1 = Image.new("RGB", (100, 100), "white")
        draw1 = ImageDraw.Draw(img1)
        draw1.ellipse([20, 20, 80, 80], fill="red")
        img1_path = "circles.png"
        img1.save(img1_path)

        # Image 2: Squares
        img2 = Image.new("RGB", (100, 100), "white")
        draw2 = ImageDraw.Draw(img2)
        draw2.rectangle([20, 20, 80, 80], fill="blue")
        img2_path = "squares.png"
        img2.save(img2_path)

        agent = LLMAgentNode()

        # Compare multiple images
        if os.getenv("OPENAI_API_KEY"):
            result = agent.run(
                provider="openai",
                model="o4-mini",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Compare these two images. What are the differences? Be concise.",
                            },
                            {"type": "image", "path": img1_path},
                            {"type": "image", "path": img2_path},
                        ],
                    }
                ],
                generation_config={"max_completion_tokens": 500},
            )

            if result["success"]:
                print(f"Response: {result['response']['content']}")
            else:
                print(f"Error: {result['error']}")
        else:
            print("OpenAI API key not set, skipping multiple images example")

        # Clean up
        Path(img1_path).unlink(missing_ok=True)
        Path(img2_path).unlink(missing_ok=True)

    except ImportError:
        print("PIL not available for creating multiple images.")


def example_4_ollama_vision():
    """Example 4: Using Ollama for local vision models."""
    print("\n=== Example 4: Ollama Vision (Local Models) ===")

    agent = LLMAgentNode()
    image_path = create_sample_image()

    # Check if Ollama is available
    from kailash.nodes.ai.ai_providers import get_provider

    ollama_provider = get_provider("ollama")

    if ollama_provider.is_available():
        # Try different vision models
        vision_models = ["llama3.2-vision"]

        for model in vision_models:
            print(f"\nTrying {model}:")
            try:
                result = agent.run(
                    provider="ollama",
                    model=model,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Describe this image briefly. Be concise.",
                                },
                                {"type": "image", "path": image_path},
                            ],
                        }
                    ],
                    generation_config={"max_tokens": 100},
                )

                if result["success"]:
                    print(f"Response: {result['response']['content']}")
                    break  # Stop after first successful model
                else:
                    print(
                        f"Model {model} not available or error: {result.get('error', 'Unknown error')}"
                    )

            except Exception as e:
                print(f"Error with {model}: {e}")
    else:
        print(
            "Ollama is not available. Please install and start Ollama to use local vision models."
        )


def example_5_best_practices():
    """Example 5: Best practices and error handling."""
    print("\n=== Example 5: Best Practices ===")

    agent = LLMAgentNode()

    # 1. Check image size before sending
    from kailash.nodes.ai.vision_utils import validate_image_size

    image_path = create_sample_image()
    is_valid, error_msg = validate_image_size(image_path, max_size_mb=20.0)

    if not is_valid:
        print(f"Image validation failed: {error_msg}")
        return

    # 2. Use appropriate models for vision
    vision_models = {
        "openai": ["o4-mini"],
        "anthropic": [
            "claude-sonnet-4-20250514",
        ],
        "ollama": ["llama3.2-vision"],
    }

    # 3. Handle provider-specific requirements d
    result = agent.run(
        provider="openai",
        model="o4-mini",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What objects are in this image?"},
                    {"type": "image", "path": image_path},
                ],
            }
        ],
        generation_config={
            "max_completion_tokens": 300,  # Use new parameter for modern models
        },
    )

    # 4. Always check for success
    if result["success"]:
        print(f"Analysis: {result['response']['content']}")
        print("\nMetadata:")
        print(f"- Model: {result['metadata']['model']}")
        print(f"- Provider: {result['metadata']['provider']}")
        print(f"- Tokens: {result['usage']['total_tokens']}")
        if "estimated_cost_usd" in result["usage"]:
            print(f"- Estimated cost: ${result['usage']['estimated_cost_usd']:.6f}")
    else:
        print(f"Error: {result['error']}")
        print(f"Error type: {result.get('error_type', 'Unknown')}")
        if "recovery_suggestions" in result:
            print("Suggestions:")
            for suggestion in result["recovery_suggestions"]:
                print(f"- {suggestion}")


def example_6_workflow_integration():
    """Example 6: Integrating vision in a workflow."""
    print("\n=== Example 6: Workflow Integration ===")

    print("Vision nodes can be integrated into workflows for:")
    print("- Document processing: Extract text and analyze layouts")
    print("- Quality control: Detect defects in manufacturing")
    print("- Data extraction: Process charts, graphs, and infographics")
    print("- Receipt processing: Extract data from invoices and receipts")
    print("- Medical imaging: Analyze X-rays or scans (with appropriate models)")
    print("\nExample workflow structure:")
    print(
        """
    workflow = Workflow(name="doc_processor", workflow_id="doc_001")

    # Add vision analysis node
    workflow.add_node(
        LLMAgentNode(name="analyze_document"),
        inputs={
            "provider": "openai",
            "model": "o4-mini",
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": "Extract all text and data from this document"},
                    {"type": "image", "path": "{{ document_path }}"}
                ]
            }]
        }
    )
    """
    )


def main():
    """Run all examples."""
    print("🖼️ Kailash SDK Vision Capabilities Examples")
    print("=" * 50)

    # Run examples
    example_1_basic_image_analysis()
    example_2_base64_image()
    example_3_multiple_images()
    example_4_ollama_vision()
    example_5_best_practices()
    example_6_workflow_integration()

    # Clean up
    for file in ["sample_shapes.png", "circles.png", "squares.png"]:
        Path(file).unlink(missing_ok=True)

    print("\n✅ Vision examples completed!")
    print("\nKey takeaways:")
    print("1. Vision support is seamless - just add image items to content")
    print("2. All major providers (OpenAI, Anthropic, Ollama) are supported")
    print("3. Use file paths or base64 encoded images")
    print("4. Multiple images can be analyzed together")
    print("5. Always validate image size and use appropriate models")


if __name__ == "__main__":
    main()
