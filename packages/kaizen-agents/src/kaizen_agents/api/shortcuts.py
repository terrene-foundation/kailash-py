"""
String Shortcuts for Unified Agent API

This module provides string-to-implementation mappings for progressive configuration.
Users can use simple strings like "session" instead of SessionMemory() instances.

Shortcut Categories:
- Memory shortcuts: "stateless", "session", "persistent", "learning"
- Runtime shortcuts: "local", "claude_code", "codex", "gemini_cli"
- Tool access shortcuts: "none", "read_only", "constrained", "full"
"""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Union

from kaizen_agents.api.types import MemoryDepth, ToolAccess

if TYPE_CHECKING:
    from kaizen_agents.api.types import ExecutionMode

logger = logging.getLogger(__name__)

# Type aliases for lazy loading
MemoryProviderType = Any  # Will be MemoryProvider when imported
RuntimeAdapterType = Any  # Will be RuntimeAdapter when imported


# === Memory Shortcuts ===


def _create_stateless_memory(**kwargs) -> "MemoryProviderType":
    """Create a stateless (no-op) memory provider."""
    from kaizen.memory.providers.buffer_adapter import BufferMemoryAdapter

    return BufferMemoryAdapter(max_turns=0)


def _create_session_memory(**kwargs) -> "MemoryProviderType":
    """Create a session-scoped memory provider."""
    from kaizen.memory.providers.buffer_adapter import BufferMemoryAdapter

    max_turns = kwargs.get("max_turns", 50)
    return BufferMemoryAdapter(max_turns=max_turns)


def _safe_sqlite_dsn(memory_path: str) -> str:
    """Build a DataFlow-safe 4-slash absolute SQLite DSN from a filesystem path.

    DataFlow requires the 4-slash absolute form (``sqlite:////abs/path``); the
    3-slash form (``sqlite:///rel/path``) is parsed as a *relative* path and
    fails with ``DDLFailedError: unable to open database file`` (issue #855).

    ``memory_path`` is treated as a directory (a ``memory.db`` file is created
    inside it) unless it already ends in ``.db``, in which case it is the file.

    Raises:
        ValueError: if the path contains ``?``, ``#``, or a null byte, which
            would corrupt the SQLite connection URI.
    """
    from pathlib import Path

    if any(c in memory_path for c in ("?", "#", "\x00")):
        raise ValueError(
            f"Invalid memory_path {memory_path!r}: must not contain '?', '#', "
            "or null bytes (these corrupt the SQLite connection URI)."
        )

    p = Path(memory_path).expanduser()
    if p.suffix == ".db":
        db_file = p.resolve()
        db_file.parent.mkdir(parents=True, exist_ok=True)
    else:
        p.mkdir(parents=True, exist_ok=True)
        db_file = (p / "memory.db").resolve()

    # 4-slash absolute form: "sqlite:////" + absolute-path-without-leading-slash.
    return "sqlite:////" + str(db_file).lstrip("/")


def _build_dataflow_warm_backend(memory_path: str) -> "MemoryProviderType":
    """Build a DataFlow-backed warm-tier memory backend for the given path.

    Registers ``MemoryEntryModel`` with a ``tag_list`` column — NOT ``tags``,
    which collides with the core SDK's reserved ``NodeMetadata.tags`` (``set[str]``)
    and fails CreateNode validation (issue #855) — then returns a
    ``DataFlowMemoryBackend``.

    Returns ``None`` (the caller falls back to a hot-tier-only provider) when
    DataFlow is not installed, so ``store()`` never silently drops writes nor
    raises on a missing optional dependency.
    """
    try:
        from dataflow import DataFlow

        from kaizen.memory.providers.dataflow_backend import DataFlowMemoryBackend
    except ImportError:
        logger.warning(
            "kaizen_agents.memory: DataFlow is not installed; persistent/learning "
            "memory degrades to hot-tier-only (no cross-session persistence). "
            "Install with: pip install kailash-dataflow kailash"
        )
        return None

    db = DataFlow(database_url=_safe_sqlite_dsn(memory_path))

    @db.model
    class MemoryEntryModel:
        id: str
        session_id: str
        content: str
        role: str
        timestamp: str
        source: str
        importance: float
        # Column is "tag_list" not "tags" — see issue #855 (reserved-name collision).
        tag_list: str
        metadata: str
        embedding: str = ""

    return DataFlowMemoryBackend(db, model_name="MemoryEntryModel")


def _create_persistent_memory(**kwargs) -> "MemoryProviderType":
    """Create a persistent memory provider with a DataFlow warm-tier backend.

    The warm tier persists entries across sessions; when DataFlow is unavailable
    the provider degrades to hot-tier-only (a logged warning, not a silent drop).
    """
    from kaizen.memory.providers.hierarchical import HierarchicalMemory

    memory_path = kwargs.get("memory_path", "./data/memory")
    return HierarchicalMemory(warm_backend=_build_dataflow_warm_backend(memory_path))


def _create_learning_memory(**kwargs) -> "MemoryProviderType":
    """Create a learning memory provider with a DataFlow warm-tier backend.

    Wired identically to ``persistent`` today: ``HierarchicalMemory`` does not
    yet implement a cold/summarization tier, so learning shares the warm-backed
    configuration rather than advertising a cold tier that would silently drop
    writes (issue #855). Cold-tier learning is tracked as follow-up work.
    """
    from kaizen.memory.providers.hierarchical import HierarchicalMemory

    memory_path = kwargs.get("memory_path", "./data/memory")
    return HierarchicalMemory(warm_backend=_build_dataflow_warm_backend(memory_path))


# Memory shortcut registry
MEMORY_SHORTCUTS: dict[str, Callable[..., "MemoryProviderType"]] = {
    "stateless": _create_stateless_memory,
    "session": _create_session_memory,
    "persistent": _create_persistent_memory,
    "learning": _create_learning_memory,
}

# Map MemoryDepth enum to shortcuts
MEMORY_DEPTH_TO_SHORTCUT: dict[MemoryDepth, str] = {
    MemoryDepth.STATELESS: "stateless",
    MemoryDepth.SESSION: "session",
    MemoryDepth.PERSISTENT: "persistent",
    MemoryDepth.LEARNING: "learning",
}


def resolve_memory_shortcut(
    memory: Union[str, "MemoryProviderType", MemoryDepth, None],
    **kwargs,
) -> "MemoryProviderType":
    """
    Resolve a memory shortcut to an actual MemoryProvider instance.

    Args:
        memory: Memory specification - string shortcut, MemoryDepth enum,
                or existing MemoryProvider instance
        **kwargs: Additional arguments passed to memory factory

    Returns:
        MemoryProvider instance

    Raises:
        ValueError: If the shortcut is not recognized

    Examples:
        # String shortcut
        memory = resolve_memory_shortcut("session")

        # MemoryDepth enum
        memory = resolve_memory_shortcut(MemoryDepth.PERSISTENT, memory_path="./data")

        # Pass-through existing instance
        memory = resolve_memory_shortcut(my_custom_memory)
    """
    # Handle None -> default to stateless
    if memory is None:
        return _create_stateless_memory(**kwargs)

    # Handle MemoryDepth enum
    if isinstance(memory, MemoryDepth):
        shortcut = MEMORY_DEPTH_TO_SHORTCUT.get(memory, "stateless")
        return MEMORY_SHORTCUTS[shortcut](**kwargs)

    # Handle string shortcut
    if isinstance(memory, str):
        shortcut = memory.lower().strip()
        if shortcut not in MEMORY_SHORTCUTS:
            valid = ", ".join(f'"{k}"' for k in MEMORY_SHORTCUTS)
            raise ValueError(
                f"Unknown memory shortcut: '{memory}'. "
                f"Valid shortcuts are: {valid}. "
                f"Or pass a MemoryProvider instance directly."
            )
        return MEMORY_SHORTCUTS[shortcut](**kwargs)

    # Assume it's already a MemoryProvider instance
    return memory


# === Runtime Shortcuts ===


def _create_local_runtime(**kwargs) -> "RuntimeAdapterType":
    """Create a LocalKaizenAdapter for native Kaizen execution."""
    from kaizen_agents.runtime_adapters.kaizen_local import LocalKaizenAdapter

    return LocalKaizenAdapter(**kwargs)


def _create_claude_code_runtime(**kwargs) -> "RuntimeAdapterType":
    """Create a ClaudeCodeAdapter for Claude Code execution."""
    # ClaudeCodeAdapter is an optional adapter; import lazily and surface a typed error if missing
    try:
        from kaizen_agents.runtime_adapters.claude_code import ClaudeCodeAdapter

        return ClaudeCodeAdapter(**kwargs)
    except ImportError:
        raise ValueError(
            "ClaudeCodeAdapter is not yet available. "
            "Use runtime='local' with model='claude-*' for now."
        ) from None


def _create_codex_runtime(**kwargs) -> "RuntimeAdapterType":
    """Create an OpenAI Codex adapter for Codex execution."""
    # OpenAICodexAdapter is an optional adapter; import lazily and surface a typed error if missing
    try:
        from kaizen_agents.runtime_adapters.openai_codex import OpenAICodexAdapter

        return OpenAICodexAdapter(**kwargs)
    except ImportError:
        raise ValueError(
            "OpenAICodexAdapter is not yet available. "
            "Use runtime='local' with model='gpt-*' for now."
        ) from None


def _create_gemini_cli_runtime(**kwargs) -> "RuntimeAdapterType":
    """Create a Gemini CLI adapter for Gemini execution."""
    # GeminiCLIAdapter is an optional adapter; import lazily and surface a typed error if missing
    try:
        from kaizen_agents.runtime_adapters.gemini_cli import GeminiCLIAdapter

        return GeminiCLIAdapter(**kwargs)
    except ImportError:
        raise ValueError(
            "GeminiCLIAdapter is not yet available. "
            "Use runtime='local' with model='gemini-*' for now."
        ) from None


# Runtime shortcut registry
RUNTIME_SHORTCUTS: dict[str, Callable[..., "RuntimeAdapterType"]] = {
    "local": _create_local_runtime,
    "kaizen": _create_local_runtime,  # Alias
    "native": _create_local_runtime,  # Alias
    "claude_code": _create_claude_code_runtime,
    "claude-code": _create_claude_code_runtime,  # Alias
    "codex": _create_codex_runtime,
    "openai_codex": _create_codex_runtime,  # Alias
    "gemini_cli": _create_gemini_cli_runtime,
    "gemini-cli": _create_gemini_cli_runtime,  # Alias
}


def resolve_runtime_shortcut(
    runtime: Union[str, "RuntimeAdapterType", None],
    **kwargs,
) -> "RuntimeAdapterType":
    """
    Resolve a runtime shortcut to an actual RuntimeAdapter instance.

    Args:
        runtime: Runtime specification - string shortcut or existing RuntimeAdapter instance
        **kwargs: Additional arguments passed to runtime factory

    Returns:
        RuntimeAdapter instance

    Raises:
        ValueError: If the shortcut is not recognized

    Examples:
        # String shortcut
        runtime = resolve_runtime_shortcut("local")

        # Pass-through existing instance
        runtime = resolve_runtime_shortcut(my_custom_runtime)
    """
    # Handle None -> default to local
    if runtime is None:
        return _create_local_runtime(**kwargs)

    # Handle string shortcut
    if isinstance(runtime, str):
        shortcut = runtime.lower().strip().replace("-", "_")
        # Also try with dashes
        if shortcut not in RUNTIME_SHORTCUTS:
            shortcut = runtime.lower().strip()
        if shortcut not in RUNTIME_SHORTCUTS:
            valid = ", ".join(f'"{k}"' for k in RUNTIME_SHORTCUTS if "_" not in k)
            raise ValueError(
                f"Unknown runtime shortcut: '{runtime}'. "
                f"Valid shortcuts are: {valid}. "
                f"Or pass a RuntimeAdapter instance directly."
            )
        return RUNTIME_SHORTCUTS[shortcut](**kwargs)

    # Assume it's already a RuntimeAdapter instance
    return runtime


# === Tool Access Shortcuts ===

# Tool access to tool policy mapping
TOOL_ACCESS_POLICIES: dict[ToolAccess, dict[str, Any]] = {
    ToolAccess.NONE: {
        "enabled": False,
        "allowed_tools": [],
        "require_confirmation": False,
    },
    ToolAccess.READ_ONLY: {
        "enabled": True,
        "allowed_tools": [
            "read",
            "glob",
            "grep",
            "list",
            "ls",
            "find",
            "search",
            "get",
            "fetch",
            "view",
            "show",
            "describe",
            "analyze",
        ],
        "require_confirmation": False,
    },
    ToolAccess.CONSTRAINED: {
        "enabled": True,
        "allowed_tools": [
            # Read tools
            "read",
            "glob",
            "grep",
            "list",
            "ls",
            "find",
            "search",
            "get",
            "fetch",
            "view",
            "show",
            "describe",
            "analyze",
            # Safe write tools
            "write",
            "edit",
            "create",
            "mkdir",
            "copy",
            "move",
            # Safe network tools
            "http_get",
            "http_post",
            "api_call",
            # Safe execution
            "python",
            "node",
        ],
        "require_confirmation": True,  # For dangerous operations
        "dangerous_tools": ["bash", "shell", "exec", "rm", "delete"],
    },
    ToolAccess.FULL: {
        "enabled": True,
        "allowed_tools": None,  # All tools allowed
        "require_confirmation": False,
    },
}


def resolve_tool_access_shortcut(
    tool_access: str | ToolAccess | None,
) -> dict[str, Any]:
    """
    Resolve a tool access shortcut to a tool policy configuration.

    Args:
        tool_access: Tool access specification - string shortcut or ToolAccess enum

    Returns:
        Tool policy configuration dictionary

    Raises:
        ValueError: If the shortcut is not recognized

    Examples:
        # String shortcut
        policy = resolve_tool_access_shortcut("read_only")

        # ToolAccess enum
        policy = resolve_tool_access_shortcut(ToolAccess.CONSTRAINED)
    """
    # Handle None -> default to none
    if tool_access is None:
        return TOOL_ACCESS_POLICIES[ToolAccess.NONE].copy()

    # Handle ToolAccess enum
    if isinstance(tool_access, ToolAccess):
        return TOOL_ACCESS_POLICIES[tool_access].copy()

    # Handle string shortcut
    shortcut = tool_access.lower().strip().replace("-", "_")
    try:
        access_level = ToolAccess(shortcut)
        return TOOL_ACCESS_POLICIES[access_level].copy()
    except ValueError:
        valid = ", ".join(f'"{ta.value}"' for ta in ToolAccess)
        raise ValueError(
            f"Unknown tool access level: '{tool_access}'. Valid levels are: {valid}."
        ) from None


# === Execution Mode Shortcuts ===


def resolve_execution_mode(
    mode: Union[str, "ExecutionMode", None],
) -> "ExecutionMode":
    """
    Resolve an execution mode shortcut to ExecutionMode enum.

    Args:
        mode: Execution mode specification - string or ExecutionMode enum

    Returns:
        ExecutionMode enum value

    Raises:
        ValueError: If the shortcut is not recognized

    Examples:
        # String shortcut
        mode = resolve_execution_mode("autonomous")

        # ExecutionMode enum (pass-through)
        mode = resolve_execution_mode(ExecutionMode.MULTI)
    """
    from kaizen_agents.api.types import ExecutionMode

    # Handle None -> default to single
    if mode is None:
        return ExecutionMode.SINGLE

    # Handle ExecutionMode enum
    if isinstance(mode, ExecutionMode):
        return mode

    # Handle string shortcut
    shortcut = mode.lower().strip().replace("-", "_")
    try:
        return ExecutionMode(shortcut)
    except ValueError:
        valid = ", ".join(f'"{em.value}"' for em in ExecutionMode)
        raise ValueError(
            f"Unknown execution mode: '{mode}'. Valid modes are: {valid}."
        ) from None


# === Model Shortcuts ===

# Common model aliases
MODEL_ALIASES: dict[str, str] = {
    # GPT aliases
    "gpt4": "gpt-4",
    "gpt-4o": "gpt-4o",
    "gpt4o": "gpt-4o",
    "gpt-4-turbo": "gpt-4-turbo",
    "gpt4-turbo": "gpt-4-turbo",
    "gpt-3.5": "gpt-3.5-turbo",
    "gpt35": "gpt-3.5-turbo",
    # Claude aliases
    "claude": "claude-3-sonnet",
    "claude-sonnet": "claude-3-sonnet",
    "claude-opus": "claude-3-opus",
    "claude-haiku": "claude-3-haiku",
    "sonnet": "claude-3-sonnet",
    "opus": "claude-3-opus",
    "haiku": "claude-3-haiku",
    # Gemini aliases
    "gemini": "gemini-1.5-pro",
    "gemini-pro": "gemini-1.5-pro",
    "gemini-flash": "gemini-1.5-flash",
    # Local aliases
    "llama": "llama3.2",
    "llama3": "llama3.2",
    "codellama": "codellama",
    "mistral": "mistral",
}


def resolve_model_shortcut(model: str) -> str:
    """
    Resolve a model shortcut to the canonical model name.

    Args:
        model: Model name or alias

    Returns:
        Canonical model name

    Examples:
        resolve_model_shortcut("gpt4")  # Returns "gpt-4"
        resolve_model_shortcut("claude")  # Returns "claude-3-sonnet"
        resolve_model_shortcut("gpt-4")  # Returns "gpt-4" (pass-through)
    """
    return MODEL_ALIASES.get(model.lower().strip(), model)


# === All Shortcuts Summary ===


def get_available_shortcuts() -> dict[str, list]:
    """
    Get all available shortcuts grouped by category.

    Returns:
        Dictionary with shortcut categories and their valid values

    Example:
        shortcuts = get_available_shortcuts()
        print(shortcuts["memory"])  # ["stateless", "session", ...]
    """
    from kaizen_agents.api.types import ExecutionMode

    return {
        "memory": list(MEMORY_SHORTCUTS.keys()),
        "runtime": [k for k in RUNTIME_SHORTCUTS if "_" not in k],
        "tool_access": [ta.value for ta in ToolAccess],
        "execution_mode": [em.value for em in ExecutionMode],
        "model_aliases": list(MODEL_ALIASES.keys()),
    }
