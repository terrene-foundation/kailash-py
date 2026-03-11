"""
DataFlow Enhanced Exception System

Provides rich, actionable error messages with context, causes, and solutions.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from dataflow.decorators import ValidationError as DecoratorValidationError


@dataclass
class ErrorSolution:
    """A suggested solution to fix an error."""

    priority: int
    description: str
    code_template: str
    auto_fixable: bool = False
    variables: Dict[str, str] = field(default_factory=dict)

    def format(self, **kwargs) -> str:
        """Format code template with provided variables."""
        template = self.code_template
        for key, value in {**self.variables, **kwargs}.items():
            template = template.replace(f"{{{{{key}}}}}", str(value))
        return template


@dataclass
class EnhancedDataFlowError(Exception):
    """Enhanced error with context and solutions."""

    error_code: str
    message: str
    context: Dict[str, Any] = field(default_factory=dict)
    causes: List[str] = field(default_factory=list)
    solutions: List[ErrorSolution] = field(default_factory=list)
    docs_url: str = ""
    original_error: Optional[Exception] = None

    def __str__(self) -> str:
        """Return formatted error message."""
        return self.format_enhanced(color=False)

    def format_enhanced(self, color: bool = True) -> str:
        """
        Format error with colors and structure.

        Args:
            color: Whether to include ANSI color codes

        Returns:
            Formatted error message string
        """
        # ANSI color codes
        if color:
            RED = "\033[91m"
            YELLOW = "\033[93m"
            BLUE = "\033[94m"
            GREEN = "\033[92m"
            BOLD = "\033[1m"
            RESET = "\033[0m"
        else:
            RED = YELLOW = BLUE = GREEN = BOLD = RESET = ""

        lines = []

        # Header
        lines.append(f"{RED}{BOLD}❌ DataFlow Error [{self.error_code}]{RESET}")
        lines.append(f"{BOLD}{self.message}{RESET}")
        lines.append("")

        # Context
        if self.context:
            lines.append(f"{BLUE}📍 Context:{RESET}")
            for key, value in self.context.items():
                lines.append(f"  {key}: {value}")
            lines.append("")

        # Possible Causes
        if self.causes:
            lines.append(f"{YELLOW}🔍 Possible Causes:{RESET}")
            for i, cause in enumerate(self.causes[:5], 1):  # Limit to 5
                lines.append(f"  {i}. {cause}")
            lines.append("")

        # Solutions
        if self.solutions:
            lines.append(f"{GREEN}💡 Solutions:{RESET}")
            for i, solution in enumerate(self.solutions[:3], 1):  # Limit to 3
                lines.append(f"  {i}. {solution.description}")
                if solution.code_template:
                    # Show first 3 lines of code template
                    code_lines = solution.code_template.strip().split("\n")[:3]
                    for line in code_lines:
                        lines.append(f"     {line}")
                    if len(solution.code_template.strip().split("\n")) > 3:
                        lines.append("     ...")
                lines.append("")

        # Documentation URL
        if self.docs_url:
            lines.append(f"{BLUE}📚 Documentation:{RESET}")
            lines.append(f"  {self.docs_url}")
            lines.append("")

        # Original error
        if self.original_error:
            lines.append(f"{YELLOW}🔗 Original Error:{RESET}")
            lines.append(
                f"  {type(self.original_error).__name__}: {self.original_error}"
            )

        return "\n".join(lines)


# Legacy exception classes for backward compatibility
class DataFlowError(Exception):
    """Base exception for DataFlow errors."""

    pass


class DataFlowConfigurationError(DataFlowError):
    """Configuration error."""

    pass


class DataFlowModelError(DataFlowError):
    """Model definition error."""

    pass


class DataFlowNodeError(DataFlowError):
    """Node operation error."""

    pass


class DataFlowRuntimeError(DataFlowError):
    """Runtime execution error."""

    pass


class DataFlowMigrationError(DataFlowError):
    """Migration error."""

    pass


class DataFlowConnectionError(DataFlowError):
    """Connection error."""

    pass


class ModelValidationError(DataFlowError):
    """Raised when model validation fails in strict mode."""

    def __init__(self, errors: List["ValidationError"]):
        """
        Initialize model validation error.

        Args:
            errors: List of ValidationError objects
        """
        self.errors = errors
        messages = [f"[{e.code}] {e.message}" for e in errors]
        super().__init__("Model validation failed:\n" + "\n".join(messages))


class DataFlowValidationWarning(UserWarning):
    """Warning category for DataFlow validation issues."""

    pass
