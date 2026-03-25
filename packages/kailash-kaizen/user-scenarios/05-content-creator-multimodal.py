"""
Scenario 5: Content Creator - Multi-Modal Content Analysis
===========================================================

User Profile:
- Content creator working with images and videos
- Needs AI to analyze visual content
- Wants to generate descriptions and metadata
- Requires multi-modal processing (vision + text)

Use Case:
- Analyze product images for e-commerce
- Generate SEO-friendly descriptions
- Extract key visual elements
- Create social media captions

Developer Experience Goals:
- Simple image analysis API
- Clear, structured output
- Multiple analysis tasks
- Production-ready quality
"""

from dotenv import load_dotenv
from kaizen_agents.agents import SimpleQAAgent, VisionAgent, VisionAgentConfig
from kaizen_agents.agents.specialized.simple_qa import SimpleQAConfig

# Load environment variables
load_dotenv()

# Sample images (these would be actual image paths in production)
SAMPLE_IMAGES = [
    {
        "path": "product_laptop.jpg",
        "category": "Electronics",
        "title": "Professional Laptop",
        # Note: In actual usage, this would be a real file path
        # For this demo, we'll create placeholder descriptions
    },
    {
        "path": "product_sneakers.jpg",
        "category": "Fashion",
        "title": "Athletic Sneakers",
    },
    {
        "path": "product_coffee.jpg",
        "category": "Food & Beverage",
        "title": "Artisan Coffee Blend",
    },
]


def main():
    """Content creator workflow - multi-modal content analysis."""

    print("=" * 70)
    print("Content Creator - Multi-Modal Content Analysis")
    print("=" * 70 + "\n")

    # Step 1: Create vision agent for image analysis
    print("👁️  Creating Vision Analysis Agent...")
    vision_config = VisionAgentConfig(
        llm_provider="ollama",
        model="bakllava",  # Multi-modal model for vision
        temperature=0.4,  # Slightly lower for consistent descriptions
    )
    vision_agent = VisionAgent(config=vision_config)
    print("✅ Vision agent ready\n")

    # Step 2: Create text agent for refinement
    print("📝 Creating Content Refinement Agent...")
    text_config = SimpleQAConfig(
        llm_provider="ollama",
        model="llama2",
        temperature=0.7,  # Higher for creative content
    )
    text_agent = SimpleQAAgent(config=text_config)
    print("✅ Text agent ready\n")

    # Step 3: Process each image
    print("🎨 Processing Product Images...")
    print("=" * 70 + "\n")

    results = []

    for idx, image_info in enumerate(SAMPLE_IMAGES, 1):
        image_path = image_info["path"]
        category = image_info["category"]
        title = image_info["title"]

        print(f"📸 Image {idx}/{len(SAMPLE_IMAGES)}: {title}")
        print(f"   Category: {category}")
        print(f"   File: {image_path}")
        print("-" * 70)

        # ========================================
        # NOTE: Vision analysis requires actual image files
        # ========================================
        # In production, you would do:
        #
        # result = vision_agent.analyze(
        #     image=f"/path/to/{image_path}",
        #     question="Describe this product in detail. Include colors, materials, features, and key selling points."
        # )
        # visual_description = result['answer']
        #
        # For this demo, we'll simulate with text-based analysis

        print("   ⚠️  Note: Vision analysis requires actual image file")
        print("   📝 Using text-based simulation for demo...\n")

        # Simulated visual analysis (in production, this comes from vision agent)
        visual_description = (
            f"A high-quality {title.lower()} from the {category} category"
        )

        # Step 4: Generate multiple content variations using text agent

        # 4a. Product description
        desc_prompt = f"""
        Based on this product:
        - Title: {title}
        - Category: {category}
        - Visual: {visual_description}

        Write a compelling 2-3 sentence product description for an e-commerce site.
        Focus on benefits and features.
        """

        try:
            desc_result = text_agent.ask(desc_prompt)
            product_desc = desc_result["answer"]
            print("   📄 Product Description:")
            print(f"      {product_desc[:200]}...")  # Truncate for display
            print()

        except Exception as e:
            print(f"   ❌ Error generating description: {e}\n")
            product_desc = "Description unavailable"

        # 4b. SEO keywords
        seo_prompt = f"""
        For this product:
        - Title: {title}
        - Category: {category}
        - Description: {visual_description}

        Generate 5-7 SEO keywords/phrases.
        List them comma-separated.
        """

        try:
            seo_result = text_agent.ask(seo_prompt)
            seo_keywords = seo_result["answer"]
            print("   🔍 SEO Keywords:")
            print(f"      {seo_keywords}")
            print()

        except Exception as e:
            print(f"   ❌ Error generating SEO keywords: {e}\n")
            seo_keywords = "Keywords unavailable"

        # 4c. Social media caption
        social_prompt = f"""
        Create an engaging Instagram caption for:
        - Product: {title}
        - Description: {visual_description}

        Make it catchy, include emojis, keep it under 150 characters.
        """

        try:
            social_result = text_agent.ask(social_prompt)
            social_caption = social_result["answer"]
            print("   📱 Social Media Caption:")
            print(f"      {social_caption}")
            print()

        except Exception as e:
            print(f"   ❌ Error generating caption: {e}\n")
            social_caption = "Caption unavailable"

        # Store results
        results.append(
            {
                "image": image_path,
                "title": title,
                "category": category,
                "description": product_desc,
                "seo_keywords": seo_keywords,
                "social_caption": social_caption,
            }
        )

        print()

    # Step 5: Generate content strategy summary
    print("=" * 70)
    print("📊 CONTENT STRATEGY SUMMARY")
    print("=" * 70 + "\n")

    strategy_prompt = f"""
    Based on these {len(SAMPLE_IMAGES)} products analyzed:
    - Categories: {", ".join(set(img["category"] for img in SAMPLE_IMAGES))}
    - Products: {", ".join(img["title"] for img in SAMPLE_IMAGES)}

    Suggest:
    1. Overall content strategy for these products
    2. Best channels for promotion (social media, blog, email)
    3. Key messaging themes
    """

    try:
        strategy_result = text_agent.ask(strategy_prompt)
        print("🎯 Content Strategy:")
        print("-" * 70)
        print(strategy_result["answer"])
        print()

    except Exception as e:
        print(f"❌ Error generating strategy: {e}\n")

    # Step 6: Display statistics
    print("=" * 70)
    print("📈 ANALYSIS STATISTICS")
    print("=" * 70)
    print(f"\n✅ Images Processed: {len(SAMPLE_IMAGES)}")
    print(
        f"✅ Descriptions Generated: {len([r for r in results if r['description'] != 'Description unavailable'])}"
    )
    print(
        f"✅ SEO Keywords Generated: {len([r for r in results if r['seo_keywords'] != 'Keywords unavailable'])}"
    )
    print(
        f"✅ Social Captions Generated: {len([r for r in results if r['social_caption'] != 'Caption unavailable'])}"
    )

    print("\n🎨 Multi-Modal Capabilities:")
    print("   • Vision Agent: Image analysis (bakllava model)")
    print("   • Text Agent: Content generation (llama2 model)")
    print("   • Combined workflow for complete content creation")

    print("\n💡 Production Usage:")
    print("   1. Replace simulated images with real file paths")
    print("   2. Vision agent will analyze actual images")
    print("   3. API: vision_agent.analyze(image='/path/to/image.jpg', question='...')")
    print("   4. Extract visual features, colors, objects automatically")

    print("\n" + "=" * 70)
    print("✅ Multi-Modal Content Analysis Complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()
