"""
Code Generation Agent - AI-powered code generation with BaseAgent

Demonstrates code generation pattern using BaseAgent + async strategy:
- Natural language to code translation
- Multiple language support (Python, JavaScript, TypeScript, etc.)
- Test case generation
- Code explanation and documentation
- Built-in logging, performance tracking, error handling via mixins
- Uses async strategy by default for better concurrency
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature


@dataclass
class CodeGenConfig:
    """Configuration for code generation agent behavior."""

    llm_provider: str = "openai"
    model: str = "gpt-4o-mini"  # GPT-4 recommended for better code quality
    temperature: float = 0.2  # Lower temperature for more deterministic code
    max_tokens: int = 2000
    programming_language: str = "python"
    include_tests: bool = True
    include_documentation: bool = True
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


class CodeGenerationAgent(BaseAgent):
    """
    Code Generation Agent using BaseAgent architecture.

    Inherits from BaseAgent:
    - Signature-based code generation pattern
    - Single-shot execution via SingleShotStrategy
    - Error handling (ErrorHandlingMixin)
    - Performance tracking (PerformanceMixin)
    - Structured logging (LoggingMixin)
    - Workflow generation for Core SDK integration

    Features:
    - Natural language to code translation
    - Multi-language support
    - Test case generation
    - Documentation generation
    - Code explanation
    """

    def __init__(self, config: CodeGenConfig):
        """Initialize code generation agent with BaseAgent infrastructure."""
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        # Initialize BaseAgent with default async strategy (Task 0A.8)
        super().__init__(config=config, signature=CodeGenSignature())

        self.codegen_config = config

    def generate_code(
        self, task_description: str, language: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate code from natural language description.

        Args:
            task_description: What the code should do
            language: Target programming language (overrides config if provided)

        Returns:
            Dict containing code, explanation, test_cases, documentation, and confidence

        Example:
            >>> agent = CodeGenerationAgent(CodeGenConfig())
            >>> result = agent.generate_code("Create a function to calculate fibonacci numbers")
            >>> print(result['code'])
            >>> print(result['test_cases'])
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
        result = self.run(task_description=enhanced_prompt, language=target_language)

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
            >>> tests = agent.generate_tests("def add(a, b): return a + b")
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

        result = self.run(task_description=test_prompt, language=language)

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
            >>> explanation = agent.explain_code("def factorial(n): return 1 if n <= 1 else n * factorial(n-1)")
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

        result = self.run(task_description=explain_prompt, language=language)

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
            >>> result = agent.refactor_code(code, "improve readability and add type hints")
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

        result = self.run(task_description=refactor_prompt, language=language)

        result["original_code"] = code
        result["refactoring_goal"] = refactoring_goal

        return result

    def _build_code_gen_prompt(self, task_description: str, language: str) -> str:
        """Build enhanced prompt with code generation requirements."""
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
        >>> result = generate_code_quick("binary search function")
        >>> print(result['code'])
    """
    config = CodeGenConfig(programming_language=language)
    agent = CodeGenerationAgent(config)
    return agent.generate_code(task, language=language)
