"""
Tool Calling Type System

Defines the core types and schemas for tool calling capabilities in Kaizen.
Enables agents to execute bash commands, file operations, API calls, and custom tools
with automatic approval workflows based on danger levels.

Architecture:
    ToolDefinition → describes a tool's interface and behavior
    ToolParameter → defines tool input parameters with validation
    ToolCategory → organizes tools by domain (system, network, AI, etc.)
    DangerLevel → determines approval requirements (safe → critical)
    ToolResult → standardized output from tool execution

Example:
    >>> from kaizen.tools.types import ToolDefinition, ToolParameter, ToolCategory, DangerLevel
    >>>
    >>> def bash_executor(command: str) -> dict:
    ...     import subprocess
    ...     result = subprocess.run(command, shell=True, capture_output=True, text=True)
    ...     return {"stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode}
    >>>
    >>> bash_tool = ToolDefinition(
    ...     name="bash_command",
    ...     description="Execute bash commands",
    ...     category=ToolCategory.SYSTEM,
    ...     danger_level=DangerLevel.HIGH,
    ...     parameters=[
    ...         ToolParameter("command", str, "Bash command to execute", required=True)
    ...     ],
    ...     returns={"stdout": "str", "stderr": "str", "returncode": "int"},
    ...     executor=bash_executor
    ... )
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class ToolCategory(Enum):
    """
    Tool categories for organization and discovery.

    Categories help agents understand what domain a tool operates in
    and enable category-based filtering and recommendation.

    Values:
        SYSTEM: System operations (bash, file I/O, process management)
        NETWORK: Network operations (API calls, web scraping, HTTP requests)
        DATA: Data operations (database queries, CSV/JSON parsing, transforms)
        AI: AI operations (LLM calls, embeddings, vision, audio processing)
        MCP: Model Context Protocol tools (discovered from MCP servers)
        CUSTOM: User-defined custom tools
    """

    SYSTEM = "system"
    NETWORK = "network"
    DATA = "data"
    AI = "ai"
    MCP = "mcp"
    CUSTOM = "custom"


class DangerLevel(Enum):
    """
    Danger level classification for approval workflow.

    Determines whether user approval is required before tool execution.
    Higher danger levels trigger more explicit approval workflows.

    Values:
        SAFE: No approval needed (read-only, non-destructive operations)
        LOW: Approval for batch operations (many API calls, large reads)
        MEDIUM: Approval for writes (file creation, API mutations)
        HIGH: Approval every time (file deletion, bash commands)
        CRITICAL: Always explicit approval (destructive ops like `rm -rf`, database drops)

    Example:
        >>> # SAFE: Read file
        >>> tool = ToolDefinition(..., danger_level=DangerLevel.SAFE)  # No approval
        >>>
        >>> # HIGH: Bash command
        >>> tool = ToolDefinition(..., danger_level=DangerLevel.HIGH)  # Always approve
        >>>
        >>> # CRITICAL: Delete all files
        >>> tool = ToolDefinition(..., danger_level=DangerLevel.CRITICAL)  # Explicit confirm
    """

    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ToolParameter:
    """
    Tool parameter definition with validation.

    Defines a single parameter accepted by a tool, including its type,
    description, default value, and optional validation function.

    Attributes:
        name: Parameter name (must be unique within tool)
        type: Expected Python type (str, int, bool, dict, list, etc.)
        description: Human-readable description for agents and users
        required: Whether parameter must be provided (default: True)
        default: Default value if not provided (only valid if required=False)
        validation: Optional validation function (param → bool)

    Example:
        >>> from kaizen.tools.types import ToolParameter
        >>>
        >>> # Required string parameter
        >>> file_path = ToolParameter(
        ...     name="path",
        ...     type=str,
        ...     description="File path to read",
        ...     required=True
        ... )
        >>>
        >>> # Optional parameter with default
        >>> encoding = ToolParameter(
        ...     name="encoding",
        ...     type=str,
        ...     description="File encoding",
        ...     required=False,
        ...     default="utf-8"
        ... )
        >>>
        >>> # Parameter with validation
        >>> def validate_positive(value):
        ...     return value > 0
        >>>
        >>> count = ToolParameter(
        ...     name="count",
        ...     type=int,
        ...     description="Number of items",
        ...     required=True,
        ...     validation=validate_positive
        ... )
    """

    name: str
    type: type
    description: str
    required: bool = True
    default: Any = None
    validation: Optional[Callable[[Any], bool]] = None

    def validate(self, value: Any) -> bool:
        """
        Validate parameter value.

        Args:
            value: Value to validate

        Returns:
            True if valid, False otherwise

        Raises:
            TypeError: If value is not the expected type
            ValueError: If validation function returns False
        """
        # Type check
        if not isinstance(value, self.type):
            raise TypeError(
                f"Parameter '{self.name}' expects {self.type.__name__}, "
                f"got {type(value).__name__}"
            )

        # Custom validation
        if self.validation is not None:
            if not self.validation(value):
                raise ValueError(
                    f"Parameter '{self.name}' failed validation: {self.description}"
                )

        return True


@dataclass
class ToolDefinition:
    """
    Complete tool definition with metadata and executor.

    Defines a tool's interface, behavior, danger level, and execution logic.
    Tools are exposed via MCP (Model Context Protocol) servers.

    Attributes:
        name: Unique tool identifier (e.g., "bash_command", "read_file")
        description: Human-readable description for agents and users
        category: Tool category (system, network, data, AI, MCP, custom)
        danger_level: Danger level for approval workflow (safe → critical)
        parameters: List of ToolParameter definitions
        returns: Return value schema as dict (e.g., {"result": "str"})
        executor: Callable that implements tool logic
        examples: Optional list of example calls
        approval_message_template: Custom approval message (uses default if None)
        approval_details_extractor: Function to extract approval details from params

    Example:
        >>> from kaizen.tools.types import ToolDefinition, ToolParameter, ToolCategory, DangerLevel
        >>>
        >>> def read_file_impl(path: str, encoding: str = "utf-8") -> dict:
        ...     with open(path, "r", encoding=encoding) as f:
        ...         return {"content": f.read(), "size": len(f.read())}
        >>>
        >>> read_file_tool = ToolDefinition(
        ...     name="read_file",
        ...     description="Read file contents",
        ...     category=ToolCategory.SYSTEM,
        ...     danger_level=DangerLevel.SAFE,
        ...     parameters=[
        ...         ToolParameter("path", str, "File path", required=True),
        ...         ToolParameter("encoding", str, "Encoding", required=False, default="utf-8")
        ...     ],
        ...     returns={"content": "str", "size": "int"},
        ...     executor=read_file_impl,
        ...     examples=[
        ...         {"path": "data.txt", "expected": {"content": "...", "size": 100}}
        ...     ]
        ... )
    """

    name: str
    description: str
    category: ToolCategory
    danger_level: DangerLevel
    parameters: List[ToolParameter]
    returns: Dict[str, Any]
    executor: Callable
    examples: Optional[List[Dict[str, Any]]] = None
    approval_message_template: Optional[str] = None
    approval_details_extractor: Optional[Callable] = None

    def validate_parameters(self, params: Dict[str, Any]) -> bool:
        """
        Validate all parameters against their definitions.

        Args:
            params: Parameter dictionary to validate

        Returns:
            True if all parameters valid

        Raises:
            ValueError: If required parameter missing or validation fails
            TypeError: If parameter has wrong type
        """
        # Check required parameters
        for param_def in self.parameters:
            if param_def.required and param_def.name not in params:
                raise ValueError(
                    f"Required parameter '{param_def.name}' missing for tool '{self.name}'"
                )

        # Validate provided parameters
        for name, value in params.items():
            # Find parameter definition
            param_def = next((p for p in self.parameters if p.name == name), None)
            if param_def is None:
                raise ValueError(f"Unknown parameter '{name}' for tool '{self.name}'")

            # Validate parameter value
            param_def.validate(value)

        return True

    def get_approval_message(self, params: Dict[str, Any]) -> str:
        """
        Generate approval message for this tool execution.

        Args:
            params: Parameters being passed to tool

        Returns:
            Approval message string

        Example:
            >>> tool.get_approval_message({"command": "ls -la"})
            "Execute bash command: 'ls -la'"
        """
        if self.approval_message_template:
            return self.approval_message_template.format(**params)

        # Default message
        return f"Execute tool '{self.name}' with parameters: {params}"

    def get_approval_details(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract approval details for this tool execution.

        Args:
            params: Parameters being passed to tool

        Returns:
            Dict of approval details for user display

        Example:
            >>> tool.get_approval_details({"path": "/etc/passwd"})
            {"file": "/etc/passwd", "danger": "HIGH", "action": "read"}
        """
        if self.approval_details_extractor:
            return self.approval_details_extractor(params)

        # Default details
        return {
            "tool": self.name,
            "category": self.category.value,
            "danger_level": self.danger_level.value,
            "parameters": params,
        }


@dataclass
class ToolResult:
    """
    Standardized tool execution result.

    Wraps tool output with metadata about execution status, errors, and timing.
    Used by ToolExecutor to return consistent results regardless of tool type.

    Attributes:
        tool_name: Name of tool that was executed
        success: Whether execution succeeded
        result: Tool output (if success=True)
        error: Error message (if success=False)
        error_type: Exception class name (if success=False)
        execution_time_ms: Execution duration in milliseconds
        approved: Whether user approved execution (None if no approval needed)
        cached: Whether result was from cache

    Example:
        >>> from kaizen.tools.types import ToolResult
        >>>
        >>> # Successful execution
        >>> result = ToolResult(
        ...     tool_name="read_file",
        ...     success=True,
        ...     result={"content": "Hello world", "size": 11},
        ...     execution_time_ms=5.2,
        ...     approved=None  # SAFE tool, no approval needed
        ... )
        >>>
        >>> # Failed execution
        >>> result = ToolResult(
        ...     tool_name="bash_command",
        ...     success=False,
        ...     error="Command failed with exit code 127",
        ...     error_type="CalledProcessError",
        ...     execution_time_ms=120.5,
        ...     approved=True  # User approved but execution failed
        ... )
    """

    tool_name: str
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    execution_time_ms: Optional[float] = None
    approved: Optional[bool] = None
    cached: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for serialization.

        Returns:
            Dict representation of result
        """
        return {
            "tool_name": self.tool_name,
            "success": self.success,
            "result": self.result,
            "error": self.error,
            "error_type": self.error_type,
            "execution_time_ms": self.execution_time_ms,
            "approved": self.approved,
            "cached": self.cached,
        }

    @classmethod
    def from_exception(
        cls,
        tool_name: str,
        exception: Exception,
        execution_time_ms: float,
        approved: Optional[bool] = None,
    ) -> "ToolResult":
        """
        Create ToolResult from exception.

        Args:
            tool_name: Name of tool that raised exception
            exception: Exception that was raised
            execution_time_ms: Execution duration
            approved: Whether execution was approved

        Returns:
            ToolResult with error information
        """
        return cls(
            tool_name=tool_name,
            success=False,
            error=str(exception),
            error_type=type(exception).__name__,
            execution_time_ms=execution_time_ms,
            approved=approved,
        )


# Type aliases for convenience
ToolExecutorFunc = Callable[[Dict[str, Any]], Dict[str, Any]]
ToolValidationFunc = Callable[[Any], bool]
ApprovalExtractorFunc = Callable[[Dict[str, Any]], Dict[str, Any]]
