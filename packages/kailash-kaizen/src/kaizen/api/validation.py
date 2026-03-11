"""
Configuration Validation for Unified Agent API

This module provides validation for agent configurations with helpful error messages.
All errors include remediation suggestions to help users fix configuration issues.
"""

from typing import Any, Dict, List, Optional, Set, Tuple

from kaizen.api.types import AgentCapabilities, ExecutionMode, MemoryDepth, ToolAccess


class ConfigurationError(Exception):
    """
    Exception raised for invalid agent configurations.

    Includes a helpful message with remediation suggestions.

    Attributes:
        message: Error description
        field: Configuration field that caused the error
        value: Invalid value provided
        suggestions: List of remediation suggestions
    """

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        value: Any = None,
        suggestions: Optional[List[str]] = None,
    ):
        self.message = message
        self.field = field
        self.value = value
        self.suggestions = suggestions or []

        # Build full error message
        full_message = message
        if self.suggestions:
            full_message += "\n\nSuggestions:\n" + "\n".join(
                f"  • {s}" for s in self.suggestions
            )

        super().__init__(full_message)

    def to_dict(self) -> dict:
        """Serialize error to dictionary."""
        return {
            "message": self.message,
            "field": self.field,
            "value": self.value,
            "suggestions": self.suggestions,
        }


# === Model-Runtime Compatibility ===

# Models that require specific runtimes
RUNTIME_LOCKED_MODELS: Dict[str, str] = {
    # Claude Code runtime models
    "claude-3-opus": "claude_code",
    "claude-3-sonnet": "claude_code",
    "claude-3.5-sonnet": "claude_code",
    "claude-3-haiku": "claude_code",
    "claude-3.5-haiku": "claude_code",
    # These can also run on "local" runtime
}

# Models that only work with specific runtimes (hard constraints)
RUNTIME_REQUIRED_MODELS: Dict[str, Set[str]] = {
    # Models locked to their native runtimes in external adapters
    # But ALL models work with "local" runtime via LocalKaizenAdapter
}

# Runtimes and their supported model families
RUNTIME_MODEL_FAMILIES: Dict[str, Set[str]] = {
    "local": {
        "gpt-",
        "claude-",
        "gemini-",
        "llama",
        "mistral",
        "codellama",
        "deepseek",
        "qwen",
        "o1",
    },
    "claude_code": {"claude-"},
    "codex": {"gpt-", "o1"},
    "gemini_cli": {"gemini-"},
}


def validate_model_runtime_compatibility(
    model: str,
    runtime: str,
) -> Tuple[bool, Optional[ConfigurationError]]:
    """
    Validate that a model and runtime are compatible.

    Args:
        model: Model name (e.g., "gpt-4", "claude-3-opus")
        runtime: Runtime name (e.g., "local", "claude_code")

    Returns:
        Tuple of (is_valid, error_if_invalid)

    Examples:
        # Valid combinations
        is_valid, error = validate_model_runtime_compatibility("gpt-4", "local")
        assert is_valid and error is None

        # Invalid: Claude model on Codex runtime
        is_valid, error = validate_model_runtime_compatibility("claude-3-opus", "codex")
        assert not is_valid and error is not None
    """
    model_lower = model.lower()
    runtime_lower = runtime.lower().replace("-", "_")

    # Local runtime supports all models
    if runtime_lower in ("local", "kaizen", "native"):
        return True, None

    # Check if runtime supports this model family
    supported_families = RUNTIME_MODEL_FAMILIES.get(runtime_lower, set())
    model_supported = any(
        model_lower.startswith(family) for family in supported_families
    )

    if not model_supported:
        # Generate helpful suggestions
        compatible_runtimes = [
            rt
            for rt, families in RUNTIME_MODEL_FAMILIES.items()
            if any(model_lower.startswith(f) for f in families)
        ]

        suggestions = [
            'Use runtime="local" which supports all models',
        ]
        if compatible_runtimes:
            suggestions.append(
                f"Compatible runtimes for {model}: {', '.join(compatible_runtimes)}"
            )

        return False, ConfigurationError(
            message=f"Model '{model}' is not compatible with runtime '{runtime}'.",
            field="runtime",
            value=runtime,
            suggestions=suggestions,
        )

    return True, None


# === Capability Consistency Validation ===


def validate_capability_consistency(
    capabilities: AgentCapabilities,
) -> Tuple[bool, List[ConfigurationError]]:
    """
    Validate that capability settings are internally consistent.

    Args:
        capabilities: AgentCapabilities to validate

    Returns:
        Tuple of (is_valid, list_of_errors)

    Examples:
        # Valid capabilities
        caps = AgentCapabilities(
            execution_modes=[ExecutionMode.AUTONOMOUS],
            max_memory_depth=MemoryDepth.SESSION,
            tool_access=ToolAccess.CONSTRAINED,
        )
        is_valid, errors = validate_capability_consistency(caps)
        assert is_valid

        # Invalid: AUTONOMOUS mode with no tools
        caps = AgentCapabilities(
            execution_modes=[ExecutionMode.AUTONOMOUS],
            tool_access=ToolAccess.NONE,
        )
        is_valid, errors = validate_capability_consistency(caps)
        # Warning but not error - autonomous can work without tools
    """
    errors = []
    warnings = []

    # Check: AUTONOMOUS mode typically needs tools
    if ExecutionMode.AUTONOMOUS in capabilities.execution_modes:
        if capabilities.tool_access == ToolAccess.NONE:
            # This is a warning, not an error - autonomous can work without tools
            # but it's unusual and likely a mistake
            pass  # Could add to warnings list if we want to track them

    # Check: LEARNING memory requires storage path
    if capabilities.max_memory_depth == MemoryDepth.LEARNING:
        # This will be validated elsewhere when creating the memory provider
        pass

    # Check: Execution limits are reasonable
    if capabilities.max_cycles < 1:
        errors.append(
            ConfigurationError(
                message="max_cycles must be at least 1.",
                field="max_cycles",
                value=capabilities.max_cycles,
                suggestions=["Set max_cycles to a positive integer (default: 100)"],
            )
        )

    if capabilities.max_turns < 1:
        errors.append(
            ConfigurationError(
                message="max_turns must be at least 1.",
                field="max_turns",
                value=capabilities.max_turns,
                suggestions=["Set max_turns to a positive integer (default: 50)"],
            )
        )

    if capabilities.max_tool_calls < 0:
        errors.append(
            ConfigurationError(
                message="max_tool_calls cannot be negative.",
                field="max_tool_calls",
                value=capabilities.max_tool_calls,
                suggestions=[
                    "Set max_tool_calls to 0 (unlimited) or a positive integer"
                ],
            )
        )

    if capabilities.timeout_seconds <= 0:
        errors.append(
            ConfigurationError(
                message="timeout_seconds must be positive.",
                field="timeout_seconds",
                value=capabilities.timeout_seconds,
                suggestions=[
                    "Set timeout_seconds to a positive value (default: 300.0)"
                ],
            )
        )

    # Check: Tool whitelist and blacklist conflict
    if capabilities.allowed_tools and capabilities.denied_tools:
        overlap = set(t.lower() for t in capabilities.allowed_tools) & set(
            t.lower() for t in capabilities.denied_tools
        )
        if overlap:
            errors.append(
                ConfigurationError(
                    message=f"Tools appear in both allowed_tools and denied_tools: {overlap}",
                    field="allowed_tools/denied_tools",
                    value={
                        "allowed": capabilities.allowed_tools,
                        "denied": capabilities.denied_tools,
                    },
                    suggestions=[
                        "Remove conflicting tools from one of the lists",
                        "Use only allowed_tools (whitelist) OR denied_tools (blacklist), not both",
                    ],
                )
            )

    return len(errors) == 0, errors


# === Full Configuration Validation ===


def validate_configuration(
    model: str,
    runtime: str = "local",
    execution_mode: str = "single",
    memory: str = "stateless",
    tool_access: str = "none",
    capabilities: Optional[AgentCapabilities] = None,
    **kwargs,
) -> Tuple[bool, List[ConfigurationError]]:
    """
    Validate a complete agent configuration.

    Args:
        model: Model name
        runtime: Runtime name or shortcut
        execution_mode: Execution mode string
        memory: Memory shortcut
        tool_access: Tool access level
        capabilities: Optional explicit capabilities
        **kwargs: Additional configuration parameters

    Returns:
        Tuple of (is_valid, list_of_errors)

    Examples:
        # Validate a configuration
        is_valid, errors = validate_configuration(
            model="gpt-4",
            runtime="local",
            execution_mode="autonomous",
            memory="session",
            tool_access="constrained",
        )

        if not is_valid:
            for error in errors:
                print(f"Error: {error.message}")
                for suggestion in error.suggestions:
                    print(f"  Suggestion: {suggestion}")
    """
    errors = []

    # 1. Validate model is provided
    if not model:
        errors.append(
            ConfigurationError(
                message="Model is required.",
                field="model",
                value=model,
                suggestions=[
                    'Specify a model: Agent(model="gpt-4")',
                    'Common models: "gpt-4", "gpt-4o", "claude-3-sonnet", "gemini-1.5-pro"',
                ],
            )
        )

    # 2. Validate model-runtime compatibility
    if model:
        is_valid, error = validate_model_runtime_compatibility(model, runtime)
        if not is_valid and error:
            errors.append(error)

    # 3. Validate execution mode
    valid_modes = {em.value for em in ExecutionMode}
    if execution_mode.lower() not in valid_modes:
        errors.append(
            ConfigurationError(
                message=f"Invalid execution_mode: '{execution_mode}'.",
                field="execution_mode",
                value=execution_mode,
                suggestions=[f'Valid modes: {", ".join(valid_modes)}'],
            )
        )

    # 4. Validate memory shortcut
    valid_memory = {"stateless", "session", "persistent", "learning"}
    if isinstance(memory, str) and memory.lower() not in valid_memory:
        errors.append(
            ConfigurationError(
                message=f"Invalid memory shortcut: '{memory}'.",
                field="memory",
                value=memory,
                suggestions=[
                    f'Valid shortcuts: {", ".join(valid_memory)}',
                    "Or pass a MemoryProvider instance directly",
                ],
            )
        )

    # 5. Validate tool access
    valid_access = {ta.value for ta in ToolAccess}
    if isinstance(tool_access, str) and tool_access.lower() not in valid_access:
        errors.append(
            ConfigurationError(
                message=f"Invalid tool_access: '{tool_access}'.",
                field="tool_access",
                value=tool_access,
                suggestions=[f'Valid levels: {", ".join(valid_access)}'],
            )
        )

    # 6. Validate explicit capabilities if provided
    if capabilities:
        caps_valid, caps_errors = validate_capability_consistency(capabilities)
        errors.extend(caps_errors)

    # 7. Validate additional parameters
    if "max_cycles" in kwargs:
        max_cycles = kwargs["max_cycles"]
        if not isinstance(max_cycles, int) or max_cycles < 1:
            errors.append(
                ConfigurationError(
                    message="max_cycles must be a positive integer.",
                    field="max_cycles",
                    value=max_cycles,
                    suggestions=[
                        "Set max_cycles to a positive integer (e.g., 50, 100)"
                    ],
                )
            )

    if "timeout_seconds" in kwargs:
        timeout = kwargs["timeout_seconds"]
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            errors.append(
                ConfigurationError(
                    message="timeout_seconds must be a positive number.",
                    field="timeout_seconds",
                    value=timeout,
                    suggestions=[
                        "Set timeout_seconds to a positive number (e.g., 300.0)"
                    ],
                )
            )

    return len(errors) == 0, errors


# === Validation Helpers ===


def validate_model_name(model: str) -> Tuple[bool, Optional[str]]:
    """
    Check if a model name is valid/recognized.

    Args:
        model: Model name to validate

    Returns:
        Tuple of (is_valid, suggestion_if_invalid)
    """
    known_prefixes = {
        "gpt-",
        "claude-",
        "gemini-",
        "llama",
        "mistral",
        "codellama",
        "deepseek",
        "qwen",
        "o1",
        "o1-",
        "mixtral",
        "phi-",
        "yi-",
    }

    model_lower = model.lower()

    # Check known prefixes
    for prefix in known_prefixes:
        if model_lower.startswith(prefix):
            return True, None

    # Not recognized - might still be valid (custom model)
    suggestion = (
        f"Model '{model}' is not a recognized model. "
        f"Known model families: {', '.join(sorted(known_prefixes))}. "
        f"If this is a custom model, make sure it's registered in your provider."
    )
    return True, suggestion  # Return True but with a suggestion


def validate_execution_mode_for_task(
    task: str,
    mode: ExecutionMode,
) -> Tuple[bool, Optional[str]]:
    """
    Suggest optimal execution mode based on task characteristics.

    Args:
        task: Task description
        mode: Current execution mode

    Returns:
        Tuple of (is_appropriate, suggestion_if_not)
    """
    task_lower = task.lower()

    # Indicators of complex tasks
    complex_indicators = {
        "implement",
        "create",
        "build",
        "develop",
        "design",
        "analyze",
        "research",
        "investigate",
        "debug",
        "fix",
        "multi-step",
        "multiple",
        "several",
        "comprehensive",
    }

    # Indicators of simple tasks
    simple_indicators = {
        "what is",
        "define",
        "explain",
        "describe",
        "list",
        "tell me",
        "how do",
        "why does",
        "when did",
    }

    has_complex = any(ind in task_lower for ind in complex_indicators)
    has_simple = any(ind in task_lower for ind in simple_indicators)

    if has_complex and mode == ExecutionMode.SINGLE:
        return True, (
            "Task appears complex. Consider execution_mode='autonomous' "
            "for multi-step tasks."
        )

    if has_simple and mode == ExecutionMode.AUTONOMOUS:
        return True, (
            "Task appears simple. Consider execution_mode='single' "
            "to reduce overhead."
        )

    return True, None


def get_recommended_configuration(
    task: str,
    model: str = "gpt-4",
) -> Dict[str, Any]:
    """
    Get recommended configuration based on task description.

    Args:
        task: Task description
        model: Preferred model

    Returns:
        Recommended configuration dictionary

    Example:
        config = get_recommended_configuration(
            "Implement a REST API with authentication"
        )
        # Returns: {"execution_mode": "autonomous", "tool_access": "constrained", ...}
    """
    task_lower = task.lower()

    # Default recommendation
    config = {
        "model": model,
        "execution_mode": "single",
        "memory": "session",
        "tool_access": "none",
    }

    # Detect code-related tasks
    code_indicators = {
        "implement",
        "code",
        "function",
        "class",
        "debug",
        "fix",
        "refactor",
        "api",
        "endpoint",
        "database",
        "script",
        "program",
    }
    if any(ind in task_lower for ind in code_indicators):
        config["execution_mode"] = "autonomous"
        config["tool_access"] = "constrained"
        config["memory"] = "session"

    # Detect research tasks
    research_indicators = {
        "research",
        "investigate",
        "analyze",
        "study",
        "compare",
        "evaluate",
        "review",
        "find",
        "search",
    }
    if any(ind in task_lower for ind in research_indicators):
        config["execution_mode"] = "autonomous"
        config["tool_access"] = "read_only"
        config["memory"] = "session"

    # Detect simple Q&A
    qa_indicators = {
        "what is",
        "define",
        "explain",
        "tell me about",
        "how do",
    }
    if any(ind in task_lower for ind in qa_indicators):
        config["execution_mode"] = "single"
        config["tool_access"] = "none"
        config["memory"] = "stateless"

    # Detect multi-turn tasks
    conversation_indicators = {
        "help me",
        "let's",
        "together",
        "step by step",
        "guide me",
    }
    if any(ind in task_lower for ind in conversation_indicators):
        config["execution_mode"] = "multi"
        config["memory"] = "session"

    return config
