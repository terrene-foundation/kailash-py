"""
Guide: Creating Custom Agents from BaseAgent

This example shows how to extend BaseAgent to create your own specialized agents.
Learn the fundamental pattern used by all Kaizen agents.

Learning Path:
1. Using specialized agents - USE pre-built agents
2. This example - CREATE custom agents from BaseAgent ← YOU ARE HERE
"""

import os
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Optional

from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature

# ============================================================================
# STEP 1: Define Your Signature (Input/Output Structure)
# ============================================================================
# Signatures define what inputs your agent accepts and what outputs it returns


class TranslationSignature(Signature):
    """Translate text between languages with quality assessment."""

    text: str = InputField(desc="Text to translate")
    source_lang: str = InputField(desc="Source language", default="auto")
    target_lang: str = InputField(desc="Target language")

    translation: str = OutputField(desc="Translated text")
    quality_score: float = OutputField(desc="Translation quality 0.0-1.0")
    notes: str = OutputField(desc="Translation notes or warnings")


# ============================================================================
# STEP 2: Define Your Configuration (Agent Settings)
# ============================================================================
# Configuration defines what settings your agent accepts


@dataclass
class TranslationConfig:
    """Configuration for translation agent with zero-config defaults."""

    # LLM settings (with environment variable support)
    llm_provider: str = field(
        default_factory=lambda: os.getenv("KAIZEN_LLM_PROVIDER", "openai")
    )
    model: str = field(default_factory=lambda: os.getenv("KAIZEN_MODEL", "gpt-4"))
    temperature: float = 0.3  # Lower temp for more accurate translations
    max_tokens: int = 1000

    # Domain-specific settings
    preserve_formatting: bool = True
    formal_tone: bool = False
    min_quality_threshold: float = 0.7

    # Technical settings
    timeout: int = 30
    retry_attempts: int = 3
    provider_config: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# STEP 3: Create Your Agent Class (Extend BaseAgent)
# ============================================================================


class TranslationAgent(BaseAgent):
    """
    Custom translation agent demonstrating BaseAgent extension pattern.

    This agent shows the fundamental pattern for creating custom agents:
    1. Define signature (inputs/outputs)
    2. Define configuration (settings)
    3. Extend BaseAgent
    4. Add domain-specific methods

    Features inherited from BaseAgent:
    - Async execution (AsyncSingleShotStrategy by default)
    - Error handling
    - Performance tracking
    - Structured logging
    - Optional memory
    - Core SDK workflow generation

    Usage:
        # Zero-config
        agent = TranslationAgent()
        result = agent.translate("Hello", target_lang="Spanish")

        # With configuration
        agent = TranslationAgent(
            model="gpt-3.5-turbo",
            formal_tone=True
        )
    """

    def __init__(
        self,
        llm_provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        preserve_formatting: Optional[bool] = None,
        formal_tone: Optional[bool] = None,
        min_quality_threshold: Optional[float] = None,
        config: Optional[TranslationConfig] = None,
    ):
        """
        Initialize translation agent with zero-config defaults.

        Args:
            llm_provider: Override default LLM provider
            model: Override default model
            temperature: Override default temperature
            preserve_formatting: Whether to preserve text formatting
            formal_tone: Whether to use formal tone
            min_quality_threshold: Minimum acceptable quality score
            config: Full config object (overrides individual params)
        """
        # Build configuration from parameters or use provided config
        if config is None:
            config = TranslationConfig()

            # Override defaults with provided parameters
            if llm_provider is not None:
                config = replace(config, llm_provider=llm_provider)
            if model is not None:
                config = replace(config, model=model)
            if temperature is not None:
                config = replace(config, temperature=temperature)
            if preserve_formatting is not None:
                config = replace(config, preserve_formatting=preserve_formatting)
            if formal_tone is not None:
                config = replace(config, formal_tone=formal_tone)
            if min_quality_threshold is not None:
                config = replace(config, min_quality_threshold=min_quality_threshold)

        # Merge timeout into provider_config
        if config.timeout:
            provider_cfg = (
                config.provider_config.copy() if config.provider_config else {}
            )
            provider_cfg["timeout"] = config.timeout
            config = replace(config, provider_config=provider_cfg)

        # Initialize BaseAgent
        # BaseAgent auto-extracts: llm_provider, model, temperature, max_tokens, provider_config
        super().__init__(
            config=config,
            signature=TranslationSignature(),
            # memory can be added here if needed
            # strategy omitted - uses AsyncSingleShotStrategy by default
        )

        self.translation_config = config

    def translate(
        self,
        text: str,
        target_lang: str,
        source_lang: str = "auto",
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Translate text to target language.

        Args:
            text: Text to translate
            target_lang: Target language (e.g., "Spanish", "French", "Japanese")
            source_lang: Source language or "auto" for auto-detection
            session_id: Optional session ID for memory continuity

        Returns:
            Dictionary containing:
            - translation: Translated text
            - quality_score: Quality assessment (0.0-1.0)
            - notes: Translation notes or warnings
            - warning: Optional warning if quality is low

        Example:
            >>> agent = TranslationAgent()
            >>> result = agent.translate("Hello, world!", target_lang="Spanish")
            >>> print(result["translation"])
            ¡Hola, mundo!
        """
        # Input validation
        if not text or not text.strip():
            return {
                "translation": "",
                "quality_score": 0.0,
                "notes": "Empty input provided",
                "error": "INVALID_INPUT",
            }

        if not target_lang:
            return {
                "translation": text,
                "quality_score": 0.0,
                "notes": "No target language specified",
                "error": "MISSING_TARGET_LANG",
            }

        # Execute via BaseAgent (handles logging, performance, error handling)
        result = self.run(
            text=text.strip(),
            source_lang=source_lang,
            target_lang=target_lang,
            session_id=session_id,
        )

        # Validate quality threshold
        quality = result.get("quality_score", 0)
        if quality < self.translation_config.min_quality_threshold:
            result["warning"] = (
                f"Low quality translation "
                f"({quality:.2f} < {self.translation_config.min_quality_threshold}). "
                f"Consider reviewing output."
            )

        return result


# ============================================================================
# DEMONSTRATION: Using Your Custom Agent
# ============================================================================


def main():
    print("=== Creating Custom Agents from BaseAgent ===\n")

    # Example 1: Zero-config usage
    print("Example 1: Zero-config custom agent")
    print("-" * 50)

    agent = TranslationAgent()
    result = agent.translate("Hello, how are you?", target_lang="Spanish")

    print("Original: Hello, how are you?")
    print(f"Translation: {result['translation']}")
    print(f"Quality: {result['quality_score']:.2f}")
    print(f"Notes: {result['notes']}\n")

    # Example 2: With configuration
    print("\nExample 2: With custom configuration")
    print("-" * 50)

    agent = TranslationAgent(
        model="gpt-3.5-turbo", formal_tone=True, min_quality_threshold=0.8
    )

    result = agent.translate("Hey, what's up?", target_lang="French")
    print(f"Translation: {result['translation']}")
    print(f"Quality: {result['quality_score']:.2f}\n")

    # Example 3: Full configuration
    print("\nExample 3: Full custom configuration")
    print("-" * 50)

    config = TranslationConfig(
        llm_provider="openai",
        model="gpt-4",
        temperature=0.2,
        preserve_formatting=True,
        formal_tone=True,
        min_quality_threshold=0.9,
    )

    agent = TranslationAgent(config=config)
    result = agent.translate("Welcome to AI!", target_lang="Japanese")
    print(f"Translation: {result['translation']}\n")

    print("\n✅ Custom Agent Pattern Complete!")
    print("\nKey Takeaways:")
    print("1. Define Signature (inputs/outputs)")
    print("2. Define Config (settings with defaults)")
    print("3. Extend BaseAgent")
    print("4. Add domain-specific methods")
    print("5. Inherit all BaseAgent features (async, logging, error handling)")
    print("\nYou can now create ANY specialized agent following this pattern!")


if __name__ == "__main__":
    main()
