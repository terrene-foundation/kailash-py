"""
CodeGenerationAgent - Production-Ready Code Generation Agent

Zero-config usage:
    from kaizen.agents import CodeGenerationAgent

    agent = CodeGenerationAgent()
    result = agent.run(task_description="Create a function to calculate fibonacci numbers", language="python")
    print(result["code"])
    print(result["test_cases"])
    print(f"Confidence: {result['confidence']}")

Progressive configuration:
    agent = CodeGenerationAgent(
        llm_provider="openai",
        model="gpt-4",
        temperature=0.1,
        programming_language="typescript",
        include_tests=True,
        include_documentation=True
    )

Environment variable support:
    KAIZEN_LLM_PROVIDER=openai
    KAIZEN_MODEL=gpt-4o-mini
    KAIZEN_TEMPERATURE=0.2
    KAIZEN_MAX_TOKENS=2000
    KAIZEN_PROGRAMMING_LANGUAGE=python
    KAIZEN_INCLUDE_TESTS=true
    KAIZEN_INCLUDE_DOCUMENTATION=true
"""

import os
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional

from kailash.nodes.base import NodeMetadata

from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature
from kaizen.strategies.multi_cycle import MultiCycleStrategy


@dataclass
class CodeGenConfig:
    """
    Configuration for Code Generation Agent.

    All parameters have sensible defaults and can be overridden via:
    1. Constructor arguments (highest priority)
    2. Environment variables (KAIZEN_*)
    3. Default values (lowest priority)
    """

    # LLM configuration
    llm_provider: str = field(
        default_factory=lambda: os.getenv("KAIZEN_LLM_PROVIDER", "openai")
    )
    model: str = field(
        default_factory=lambda: os.getenv("KAIZEN_MODEL", "gpt-4o-mini")
    )  # Better for code
    temperature: float = field(
        default_factory=lambda: float(os.getenv("KAIZEN_TEMPERATURE", "0.2"))
    )  # Lower for deterministic code
    max_tokens: int = field(
        default_factory=lambda: int(os.getenv("KAIZEN_MAX_TOKENS", "8000"))
    )

    # Code-specific configuration
    programming_language: str = field(
        default_factory=lambda: os.getenv("KAIZEN_PROGRAMMING_LANGUAGE", "python")
    )
    include_tests: bool = field(
        default_factory=lambda: os.getenv("KAIZEN_INCLUDE_TESTS", "true").lower()
        in ("true", "1", "yes")
    )
    include_documentation: bool = field(
        default_factory=lambda: os.getenv(
            "KAIZEN_INCLUDE_DOCUMENTATION", "true"
        ).lower()
        in ("true", "1", "yes")
    )

    # Autonomous execution configuration
    max_cycles: int = field(
        default_factory=lambda: int(os.getenv("KAIZEN_MAX_CYCLES", "10"))
    )  # Code generation may need iteration (generate → test → fix)

    # Technical configuration
    timeout: int = 30
    retry_attempts: int = 3
    provider_config: Dict[str, Any] = field(default_factory=dict)


class CodeGenSignature(Signature):
    """
    Signature for code generation pattern.

    Takes a natural language description and generates code with tests and docs.
    """

    # Input fields
    task_description: str = InputField(
        desc="Natural language description of what the code should do"
    )
    language: str = InputField(
        desc="Target programming language (e.g., python, javascript, typescript)"
    )

    # Output fields
    code: str = OutputField(desc="Generated code implementation")
    explanation: str = OutputField(desc="Explanation of how the code works")
    test_cases: list = OutputField(desc="List of test cases for the generated code")
    documentation: str = OutputField(desc="Documentation string for the code")
    confidence: float = OutputField(desc="Confidence in code correctness (0.0-1.0)")
    tool_calls: list = OutputField(
        desc="Tools to call for code generation/testing (empty = converged)"
    )


class CodeGenerationAgent(BaseAgent):
    """
    Production-ready Code Generation Agent using BaseAgent architecture.

    Features:
    - Zero-config with sensible defaults
    - Progressive configuration (override as needed)
    - Environment variable support
    - Multi-language support (Python, JavaScript, TypeScript, etc.)
    - Automatic test case generation
    - Code documentation generation
    - Quality metrics (lines of code, has tests, has documentation)
    - Built-in error handling and logging
    - Lower temperature (0.2) for deterministic code
    - **Autonomous execution**: Multi-cycle generate → test → fix loops

    Inherits from BaseAgent:
    - Signature-based code generation pattern
    - **Autonomous execution via MultiCycleStrategy** (generate → test → fix cycles)
    - **Objective convergence detection** (tool_calls field, ADR-013)
    - Error handling (ErrorHandlingMixin)
    - Performance tracking (PerformanceMixin)
    - Structured logging (LoggingMixin)
    - Workflow generation for Core SDK integration

    Usage:
        # Zero-config (easiest)
        agent = CodeGenerationAgent()
        result = agent.run(task_description="Create a function to calculate fibonacci numbers", language="python")

        # With configuration
        agent = CodeGenerationAgent(
            llm_provider="openai",
            model="gpt-4",
            temperature=0.1,
            programming_language="typescript",
            include_tests=True,
            include_documentation=True
        )

        # View results
        result = agent.run(task_description="Create a binary search function", language="typescript")
        print(result["code"])
        print(f"Lines of code: {result['lines_of_code']}")
        print(f"Has tests: {result['has_tests']}")
        print(f"Confidence: {result['confidence']}")
    """

    # Node metadata for Studio discovery
    metadata = NodeMetadata(
        name="CodeGenerationAgent",
        description="Multi-language code generation with automatic tests and documentation",
        version="1.0.0",
        tags={
            "ai",
            "kaizen",
            "code-generation",
            "programming",
            "testing",
            "documentation",
        },
    )

    def __init__(
        self,
        llm_provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        programming_language: Optional[str] = None,
        include_tests: Optional[bool] = None,
        include_documentation: Optional[bool] = None,
        timeout: Optional[int] = None,
        retry_attempts: Optional[int] = None,
        provider_config: Optional[Dict[str, Any]] = None,
        config: Optional[CodeGenConfig] = None,
        mcp_servers: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ):
        """
        Initialize Code Generation Agent with zero-config defaults.

        Args:
            llm_provider: Override default LLM provider
            model: Override default model
            temperature: Override default temperature
            max_tokens: Override default max tokens
            programming_language: Override default programming language
            include_tests: Override default test generation
            include_documentation: Override default documentation generation
            timeout: Override default timeout
            retry_attempts: Override default retry attempts
            provider_config: Additional provider-specific configuration
            config: Full config object (overrides individual params)            mcp_servers: Optional MCP server configurations for tool discovery
        """
        # If config object provided, use it; otherwise build from parameters
        if config is None:
            config = CodeGenConfig()

            # Override defaults with provided parameters
            if llm_provider is not None:
                config = replace(config, llm_provider=llm_provider)
            if model is not None:
                config = replace(config, model=model)
            if temperature is not None:
                config = replace(config, temperature=temperature)
            if max_tokens is not None:
                config = replace(config, max_tokens=max_tokens)
            if programming_language is not None:
                config = replace(config, programming_language=programming_language)
            if include_tests is not None:
                config = replace(config, include_tests=include_tests)
            if include_documentation is not None:
                config = replace(config, include_documentation=include_documentation)
            if timeout is not None:
                config = replace(config, timeout=timeout)
            if retry_attempts is not None:
                config = replace(config, retry_attempts=retry_attempts)
            if provider_config is not None:
                config = replace(config, provider_config=provider_config)

        # Merge timeout into provider_config
        if config.timeout and (
            not config.provider_config or "timeout" not in config.provider_config
        ):
            provider_cfg = (
                config.provider_config.copy() if config.provider_config else {}
            )
            provider_cfg["timeout"] = config.timeout
            config = replace(config, provider_config=provider_cfg)

        # CRITICAL: Initialize MultiCycleStrategy for autonomous execution
        # Code generation is iterative: generate → test → fix → repeat
        multi_cycle_strategy = MultiCycleStrategy(
            max_cycles=config.max_cycles, convergence_check=self._check_convergence
        )

        # Initialize BaseAgent with auto-config extraction
        super().__init__(
            config=config,  # Auto-extracted to BaseAgentConfig
            signature=CodeGenSignature(),
            strategy=multi_cycle_strategy,  # CRITICAL: Autonomous execution
            mcp_servers=mcp_servers,
            **kwargs,
        )

        self.codegen_config = config

    def _check_convergence(self, result: Dict[str, Any]) -> bool:
        """
        Check if code generation cycle should stop (convergence detection).

        Implements ADR-013: Objective convergence detection via tool_calls field.

        Convergence logic (priority order):
        1. OBJECTIVE (preferred): Check tool_calls field
           - tool_calls present and non-empty → NOT converged (continue)
           - tool_calls present but empty → CONVERGED (stop)
        2. SUBJECTIVE (fallback): Check confidence
           - confidence >= 0.90 → CONVERGED (code looks good)
        3. DEFAULT: CONVERGED (safe fallback)

        Args:
            result: Cycle result from LLM

        Returns:
            True if converged (stop), False if continue

        Examples:
            >>> # Cycle 1: Generate code, needs testing
            >>> result = {"tool_calls": [{"name": "bash_command", "params": {...}}]}
            >>> agent._check_convergence(result)
            False  # Has tool calls → continue

            >>> # Cycle 2: Code tested, all good
            >>> result = {"tool_calls": [], "confidence": 0.95}
            >>> agent._check_convergence(result)
            True  # Empty tool calls → converged
        """
        # OBJECTIVE CONVERGENCE (PREFERRED)
        if "tool_calls" in result:
            tool_calls = result.get("tool_calls", [])

            # Validate format
            if not isinstance(tool_calls, list):
                # Malformed tool_calls → stop for safety
                return True

            if tool_calls:
                # Has tool calls → continue generating/testing
                return False

            # Empty tool calls → converged
            return True

        # SUBJECTIVE FALLBACK (backward compatibility)
        # Higher threshold for code (0.90 vs 0.85) - code needs to be correct
        confidence = result.get("confidence", 0)
        if confidence >= 0.90:
            return True  # High confidence → converged

        # DEFAULT: Converged (safe fallback)
        return True

    def run(
        self, task_description: str, language: Optional[str] = None, **kwargs
    ) -> Dict[str, Any]:
        """
        Generate code from natural language description.

        Overrides BaseAgent.run() to add input validation and post-processing.

        Args:
            task_description: What the code should do
            language: Target programming language (overrides config if provided)
            **kwargs: Additional keyword arguments for BaseAgent.run()

        Returns:
            Dict containing code, explanation, test_cases, documentation, confidence,
            and quality metrics (lines_of_code, has_tests, has_documentation, language)

        Example:
            >>> agent = CodeGenerationAgent()
            >>> result = agent.run(task_description="Create a function to calculate fibonacci numbers", language="python")
            >>> print(result['code'])
            >>> print(result['test_cases'])
            >>> print(f"Lines: {result['lines_of_code']}, Has tests: {result['has_tests']}")
        """
        # Input validation
        if not task_description or not task_description.strip():
            return {
                "code": "",
                "explanation": "Please provide a valid task description.",
                "test_cases": [],
                "documentation": "",
                "confidence": 0.0,
                "error": "INVALID_INPUT",
            }

        # Use provided language or default from config
        target_language = language or self.codegen_config.programming_language

        # Build enhanced prompt with code generation requirements
        enhanced_prompt = self._build_code_gen_prompt(
            task_description.strip(), target_language
        )

        # Execute via BaseAgent
        result = super().run(
            task_description=enhanced_prompt, language=target_language, **kwargs
        )

        # Validate and enhance result
        if "code" in result and result["code"]:
            # Add language metadata
            result["language"] = target_language

            # Ensure test_cases is a list
            if not isinstance(result.get("test_cases"), list):
                result["test_cases"] = []

            # Add quality metrics
            result["lines_of_code"] = len(result["code"].split("\n"))
            result["has_tests"] = len(result.get("test_cases", [])) > 0
            result["has_documentation"] = bool(result.get("documentation", ""))

        return result

    def generate_code(
        self, task_description: str, language: Optional[str] = None, **kwargs
    ) -> Dict[str, Any]:
        """
        Convenience method for code generation.

        Alias for run() - provided for API clarity.

        Args:
            task_description: What the code should do
            language: Target programming language (overrides config if provided)
            **kwargs: Additional keyword arguments

        Returns:
            Dict containing code, explanation, test_cases, documentation, and confidence

        Example:
            >>> agent = CodeGenerationAgent()
            >>> result = agent.generate_code("Create a function to add two numbers")
            >>> print(result['code'])
        """
        return self.run(task_description=task_description, language=language, **kwargs)

    def generate_tests(
        self, code: str, language: str = "python"
    ) -> List[Dict[str, Any]]:
        """
        Generate test cases for existing code.

        Args:
            code: The code to generate tests for
            language: Programming language of the code

        Returns:
            List of test cases

        Example:
            >>> agent = CodeGenerationAgent()
            >>> tests = agent.generate_tests("def add(a, b): return a + b")
            >>> print(tests)
        """
        test_prompt = f"""Generate comprehensive test cases for the following {language} code:

```{language}
{code}
```

Generate at least 3 test cases covering:
1. Normal/happy path cases
2. Edge cases (empty inputs, zero, negative numbers, etc.)
3. Error cases (invalid inputs, exceptions, etc.)

For each test case, provide:
- Input values
- Expected output
- Description of what is being tested
"""

        result = super().run(task_description=test_prompt, language=language)

        return result.get("test_cases", [])

    def explain_code(self, code: str, language: str = "python") -> str:
        """
        Generate explanation for existing code.

        Args:
            code: The code to explain
            language: Programming language of the code

        Returns:
            Explanation string

        Example:
            >>> agent = CodeGenerationAgent()
            >>> explanation = agent.explain_code("def factorial(n): return 1 if n <= 1 else n * factorial(n-1)")
            >>> print(explanation)
        """
        explain_prompt = f"""Explain how the following {language} code works:

```{language}
{code}
```

Provide:
1. High-level description of what it does
2. Step-by-step explanation of the logic
3. Time and space complexity analysis
4. Potential improvements or issues
"""

        result = super().run(task_description=explain_prompt, language=language)

        return result.get("explanation", "")

    def refactor_code(
        self, code: str, refactoring_goal: str, language: str = "python"
    ) -> Dict[str, Any]:
        """
        Refactor existing code to improve quality.

        Args:
            code: The code to refactor
            refactoring_goal: What to improve (e.g., "improve performance", "make more readable")
            language: Programming language

        Returns:
            Dict with refactored code, explanation, and improvements

        Example:
            >>> agent = CodeGenerationAgent()
            >>> result = agent.refactor_code(code, "improve readability and add type hints")
            >>> print(result['code'])
        """
        refactor_prompt = f"""Refactor the following {language} code to: {refactoring_goal}

Original code:
```{language}
{code}
```

Provide:
1. Refactored code
2. Explanation of changes made
3. Benefits of the refactoring
"""

        result = super().run(task_description=refactor_prompt, language=language)

        result["original_code"] = code
        result["refactoring_goal"] = refactoring_goal

        return result

    def _build_code_gen_prompt(self, task_description: str, language: str) -> str:
        """
        Build enhanced prompt with code generation requirements.

        Args:
            task_description: What the code should do
            language: Target programming language

        Returns:
            Enhanced prompt string with requirements
        """
        prompt_parts = [
            f"Generate {language} code for the following task:",
            f"\nTask: {task_description}",
            "\nRequirements:",
            "1. Write clean, readable, well-structured code",
            f"2. Follow {language} best practices and conventions",
            "3. Include appropriate error handling",
            "4. Add comments for complex logic",
        ]

        if self.codegen_config.include_tests:
            prompt_parts.append(
                "5. Provide test cases covering normal, edge, and error scenarios"
            )

        if self.codegen_config.include_documentation:
            prompt_parts.append(
                "6. Include documentation (docstrings for Python, JSDoc for JavaScript, etc.)"
            )

        prompt_parts.extend(
            [
                "\nProvide:",
                "- Complete, runnable code",
                "- Clear explanation of the implementation",
                "- Test cases (input → expected output)",
                "- Documentation/comments",
                "- Confidence score (0.0-1.0) in correctness",
            ]
        )

        return "\n".join(prompt_parts)


# Convenience function for quick code generation
def generate_code_quick(task: str, language: str = "python") -> Dict[str, Any]:
    """
    Quick code generation with default configuration.

    Args:
        task: What the code should do
        language: Target programming language

    Returns:
        Dict with generated code and metadata

    Example:
        >>> from kaizen.agents.specialized.code_generation import generate_code_quick
        >>> result = generate_code_quick("binary search function")
        >>> print(result['code'])
    """
    agent = CodeGenerationAgent(programming_language=language)
    return agent.run(task_description=task, language=language)
