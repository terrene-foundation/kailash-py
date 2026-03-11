"""
Content Generation Agent - Enterprise content creation with BaseAgent

Demonstrates content generation for enterprise use cases:
- Blog posts and articles
- Marketing copy and product descriptions
- Technical documentation
- Social media content
- Email campaigns
- Built-in logging, performance tracking, error handling via mixins
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature
from kaizen.strategies.single_shot import SingleShotStrategy


@dataclass
class ContentGenConfig:
    """Configuration for content generation agent behavior."""

    llm_provider: str = "openai"
    model: str = "gpt-4o-mini"
    temperature: float = 0.7  # Higher for more creative content
    max_tokens: int = 2000
    content_type: str = (
        "blog_post"  # blog_post, article, marketing, documentation, social_media, email
    )
    tone: str = (
        "professional"  # professional, casual, technical, conversational, formal
    )
    target_audience: str = "general"  # general, technical, executive, consumer
    provider_config: Dict[str, Any] = field(default_factory=dict)


class ContentGenSignature(Signature):
    """
    Signature for content generation pattern.

    Takes content requirements and generates professional content.
    """

    # Input fields
    topic: str = InputField(desc="Main topic or subject of the content")
    requirements: str = InputField(
        desc="Specific requirements, keywords, or guidelines"
    )

    # Output fields
    content: str = OutputField(desc="Generated content")
    title: str = OutputField(desc="Suggested title/headline")
    summary: str = OutputField(desc="Brief summary of the content")
    keywords: list = OutputField(desc="SEO keywords and key phrases")
    call_to_action: str = OutputField(desc="Suggested call-to-action")
    word_count: int = OutputField(desc="Approximate word count")


class ContentGenerationAgent(BaseAgent):
    """
    Content Generation Agent for enterprise content creation.

    Inherits from BaseAgent:
    - Signature-based content generation
    - Single-shot execution via SingleShotStrategy
    - Error handling (ErrorHandlingMixin)
    - Performance tracking (PerformanceMixin)
    - Structured logging (LoggingMixin)

    Features:
    - Multi-format content generation
    - Tone and audience customization
    - SEO optimization
    - Brand voice consistency
    """

    def __init__(self, config: ContentGenConfig):
        """Initialize content generation agent."""
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=ContentGenSignature(),
            strategy=SingleShotStrategy(),
        )

        self.content_config = config

    def generate_content(
        self,
        topic: str,
        requirements: Optional[str] = None,
        content_type: Optional[str] = None,
        tone: Optional[str] = None,
        target_audience: Optional[str] = None,
        word_count_target: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Generate content based on topic and requirements.

        Args:
            topic: Main content topic
            requirements: Specific requirements or guidelines
            content_type: Override config content type
            tone: Override config tone
            target_audience: Override config audience
            word_count_target: Target word count

        Returns:
            Dict with content, title, summary, keywords, CTA, and word count

        Example:
            >>> agent = ContentGenerationAgent(ContentGenConfig())
            >>> result = agent.generate_content(
            ...     topic="AI in Healthcare",
            ...     requirements="Focus on diagnostics, include case studies",
            ...     word_count_target=1000
            ... )
        """
        if not topic or not topic.strip():
            return {
                "content": "",
                "title": "",
                "summary": "Please provide a valid topic.",
                "keywords": [],
                "call_to_action": "",
                "word_count": 0,
                "error": "INVALID_INPUT",
            }

        # Use overrides or defaults
        content_type = content_type or self.content_config.content_type
        tone = tone or self.content_config.tone
        audience = target_audience or self.content_config.target_audience

        # Build enhanced prompt
        enhanced_requirements = self._build_content_requirements(
            topic.strip(),
            requirements or "",
            content_type,
            tone,
            audience,
            word_count_target,
        )

        # Generate content
        result = self.run(topic=topic.strip(), requirements=enhanced_requirements)

        # Enhance result with metadata
        if "content" in result and result["content"]:
            result["content_type"] = content_type
            result["tone"] = tone
            result["target_audience"] = audience

            # Calculate actual word count if not provided
            if "word_count" not in result or result["word_count"] == 0:
                result["word_count"] = len(result["content"].split())

            # Ensure keywords is a list
            if not isinstance(result.get("keywords"), list):
                result["keywords"] = []

        return result

    def generate_blog_post(
        self, topic: str, keywords: List[str], word_count: int = 1000
    ) -> Dict[str, Any]:
        """
        Generate SEO-optimized blog post.

        Args:
            topic: Blog post topic
            keywords: Target SEO keywords
            word_count: Target word count

        Returns:
            Blog post with SEO optimization
        """
        requirements = f"""
SEO Keywords: {', '.join(keywords)}
Target word count: {word_count} words
Include:
- Engaging introduction
- 3-5 main sections with subheadings
- Practical examples or case studies
- Conclusion with key takeaways
- Meta description (155 characters)
"""

        return self.generate_content(
            topic=topic,
            requirements=requirements,
            content_type="blog_post",
            word_count_target=word_count,
        )

    def generate_marketing_copy(
        self,
        product_name: str,
        key_benefits: List[str],
        target_audience: str = "consumers",
    ) -> Dict[str, Any]:
        """
        Generate marketing copy for product/service.

        Args:
            product_name: Product or service name
            key_benefits: List of key benefits
            target_audience: Target customer segment

        Returns:
            Marketing copy with headlines and CTAs
        """
        requirements = f"""
Product: {product_name}
Key Benefits: {', '.join(key_benefits)}
Target Audience: {target_audience}

Include:
- Attention-grabbing headline
- Compelling product description
- Benefit-focused bullet points
- Emotional appeal
- Strong call-to-action
- Social proof mention
"""

        return self.generate_content(
            topic=f"Marketing copy for {product_name}",
            requirements=requirements,
            content_type="marketing",
            tone="conversational",
            target_audience=target_audience,
        )

    def generate_documentation(
        self,
        feature_name: str,
        technical_details: str,
        audience_level: str = "intermediate",
    ) -> Dict[str, Any]:
        """
        Generate technical documentation.

        Args:
            feature_name: Feature or API name
            technical_details: Technical specifications
            audience_level: beginner, intermediate, advanced

        Returns:
            Technical documentation
        """
        requirements = f"""
Feature: {feature_name}
Technical Details: {technical_details}
Audience Level: {audience_level}

Include:
- Overview and purpose
- Prerequisites
- Step-by-step instructions
- Code examples (if applicable)
- Common issues and troubleshooting
- Best practices
- Related resources
"""

        return self.generate_content(
            topic=f"Documentation for {feature_name}",
            requirements=requirements,
            content_type="documentation",
            tone="technical",
            target_audience="technical",
        )

    def generate_social_media(
        self, topic: str, platform: str = "linkedin", include_hashtags: bool = True
    ) -> Dict[str, Any]:
        """
        Generate social media content.

        Args:
            topic: Post topic
            platform: Social platform (linkedin, twitter, facebook, instagram)
            include_hashtags: Whether to include hashtags

        Returns:
            Platform-optimized social content
        """
        platform_specs = {
            "linkedin": "Professional tone, 1300 characters max, industry insights",
            "twitter": "Concise, 280 characters max, engaging hook",
            "facebook": "Conversational, storytelling, encourage engagement",
            "instagram": "Visual-focused, emoji-friendly, lifestyle appeal",
        }

        spec = platform_specs.get(platform, "Professional and engaging")

        requirements = f"""
Platform: {platform}
Platform Guidelines: {spec}
{'Include relevant hashtags' if include_hashtags else 'No hashtags'}

Make it:
- Attention-grabbing
- Shareable
- On-brand
- Encourage engagement (likes, comments, shares)
"""

        return self.generate_content(
            topic=topic,
            requirements=requirements,
            content_type="social_media",
            tone="conversational",
        )

    def generate_email_campaign(
        self, campaign_goal: str, target_segment: str, key_message: str
    ) -> Dict[str, Any]:
        """
        Generate email campaign content.

        Args:
            campaign_goal: Campaign objective (e.g., "product launch", "re-engagement")
            target_segment: Target customer segment
            key_message: Main message to convey

        Returns:
            Email content with subject line
        """
        requirements = f"""
Campaign Goal: {campaign_goal}
Target Segment: {target_segment}
Key Message: {key_message}

Include:
- Compelling subject line (< 50 characters)
- Personalized greeting
- Clear value proposition
- Scannable content (short paragraphs, bullet points)
- Strong call-to-action button text
- P.S. line for urgency/scarcity
"""

        return self.generate_content(
            topic=f"Email campaign: {campaign_goal}",
            requirements=requirements,
            content_type="email",
            tone="conversational",
        )

    def _build_content_requirements(
        self,
        topic: str,
        requirements: str,
        content_type: str,
        tone: str,
        audience: str,
        word_count: Optional[int],
    ) -> str:
        """Build enhanced requirements with content generation guidelines."""
        parts = [
            f"Content Type: {content_type}",
            f"Tone: {tone}",
            f"Target Audience: {audience}",
        ]

        if word_count:
            parts.append(f"Target Word Count: {word_count} words")

        if requirements:
            parts.append(f"\nSpecific Requirements:\n{requirements}")

        parts.extend(
            [
                "\nGeneral Guidelines:",
                "- Use clear, engaging language",
                "- Include relevant examples or data",
                "- Structure content with headers/sections",
                "- End with a strong conclusion or CTA",
                "- Optimize for readability (short paragraphs, transitions)",
            ]
        )

        return "\n".join(parts)


# Convenience function for quick content generation
def generate_content_quick(
    topic: str, content_type: str = "blog_post"
) -> Dict[str, Any]:
    """
    Quick content generation with default configuration.

    Args:
        topic: Content topic
        content_type: Type of content to generate

    Returns:
        Dict with generated content

    Example:
        >>> result = generate_content_quick("Future of AI", "article")
        >>> print(result['content'])
    """
    config = ContentGenConfig(content_type=content_type)
    agent = ContentGenerationAgent(config)
    return agent.generate_content(topic)
