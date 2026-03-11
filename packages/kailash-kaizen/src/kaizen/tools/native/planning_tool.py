"""Planning Tools - Plan mode management for autonomous agents.

Implements EnterPlanMode and ExitPlanMode tools that allow agents to
manage planning workflows, matching Claude Code's planning functionality.

See: TODO-207 ClaudeCodeAgent Full Tool Parity

Example:
    >>> from kaizen.tools.native import EnterPlanModeTool, ExitPlanModeTool
    >>> from kaizen.tools.native import KaizenToolRegistry
    >>>
    >>> registry = KaizenToolRegistry()
    >>> registry.register(EnterPlanModeTool(on_enter=my_enter_callback))
    >>> registry.register(ExitPlanModeTool(on_exit=my_exit_callback))
    >>>
    >>> # Agent enters plan mode
    >>> result = await registry.execute("enter_plan_mode", {})
    >>>
    >>> # Agent exits plan mode with plan
    >>> result = await registry.execute("exit_plan_mode", {
    ...     "allowedPrompts": [
    ...         {"tool": "Bash", "prompt": "run tests"}
    ...     ]
    ... })
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union

from kaizen.tools.native.base import BaseTool, NativeToolResult
from kaizen.tools.types import DangerLevel, ToolCategory

logger = logging.getLogger(__name__)


class PlanMode(str, Enum):
    """Plan mode states."""

    INACTIVE = "inactive"
    ACTIVE = "active"
    READY_FOR_APPROVAL = "ready_for_approval"
    APPROVED = "approved"


@dataclass
class AllowedPrompt:
    """Permission prompt for plan execution.

    Attributes:
        tool: The tool this prompt applies to (e.g., "Bash")
        prompt: Semantic description of the action (e.g., "run tests")
    """

    tool: str
    prompt: str

    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary."""
        return {
            "tool": self.tool,
            "prompt": self.prompt,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AllowedPrompt":
        """Create from dictionary."""
        return cls(
            tool=data["tool"],
            prompt=data["prompt"],
        )


@dataclass
class PlanState:
    """Current plan mode state.

    Attributes:
        mode: Current plan mode
        entered_at: When plan mode was entered
        plan_file: Optional path to plan file
        allowed_prompts: Permissions needed for plan execution
    """

    mode: PlanMode = PlanMode.INACTIVE
    entered_at: Optional[str] = None
    plan_file: Optional[str] = None
    allowed_prompts: List[AllowedPrompt] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "mode": self.mode.value,
            "entered_at": self.entered_at,
            "plan_file": self.plan_file,
            "allowed_prompts": [p.to_dict() for p in self.allowed_prompts],
        }


# Type alias for callbacks
PlanModeCallback = Union[
    Callable[[PlanState], None],
    Callable[[PlanState], Awaitable[None]],
]


class EnterPlanModeTool(BaseTool):
    """Enter plan mode for implementation planning.

    The EnterPlanMode tool transitions the agent into plan mode where it can:
    - Explore the codebase using Glob, Grep, and Read tools
    - Understand existing patterns and architecture
    - Design an implementation approach
    - Present the plan to the user for approval

    Use this tool proactively when:
    - Starting a non-trivial implementation task
    - Multiple valid approaches exist
    - Code modifications affect existing behavior
    - Multi-file changes are likely
    - Requirements need clarification

    Do NOT use for:
    - Simple, single-line fixes
    - Tasks with very specific instructions already given
    - Pure research/exploration tasks

    Example:
        >>> tool = EnterPlanModeTool(on_enter=my_callback)
        >>> result = await tool.execute()
        >>> # Agent is now in plan mode
    """

    name = "enter_plan_mode"
    description = (
        "Enter plan mode to design an implementation approach before writing code. "
        "Use this when starting non-trivial tasks that require planning. "
        "In plan mode, explore the codebase and design your approach, then use "
        "ExitPlanMode when ready for user approval."
    )
    danger_level = DangerLevel.SAFE
    category = ToolCategory.CUSTOM

    def __init__(
        self,
        on_enter: Optional[PlanModeCallback] = None,
        state: Optional[PlanState] = None,
    ):
        """Initialize EnterPlanModeTool.

        Args:
            on_enter: Callback when plan mode is entered
            state: Shared plan state (for coordination with ExitPlanModeTool)
        """
        super().__init__()
        self._on_enter = on_enter
        self._state = state or PlanState()

    @property
    def state(self) -> PlanState:
        """Get current plan state."""
        return self._state

    def set_state(self, state: PlanState) -> None:
        """Set shared plan state."""
        self._state = state

    async def execute(self, **kwargs) -> NativeToolResult:
        """Enter plan mode.

        Returns:
            NativeToolResult indicating plan mode entry

        Example:
            >>> result = await tool.execute()
            >>> print(result.output)  # "Entered plan mode"
        """
        try:
            # Check if already in plan mode
            if self._state.mode == PlanMode.ACTIVE:
                return NativeToolResult.from_success(
                    output="Already in plan mode",
                    mode=self._state.mode.value,
                    entered_at=self._state.entered_at,
                )

            # Enter plan mode
            self._state.mode = PlanMode.ACTIVE
            self._state.entered_at = datetime.now(timezone.utc).isoformat()
            self._state.allowed_prompts = []

            logger.info("Entered plan mode")

            # Call callback if provided
            if self._on_enter is not None:
                import asyncio

                if asyncio.iscoroutinefunction(self._on_enter):
                    await self._on_enter(self._state)
                else:
                    self._on_enter(self._state)

            return NativeToolResult.from_success(
                output="Entered plan mode. Explore the codebase and design your implementation approach.",
                mode=self._state.mode.value,
                entered_at=self._state.entered_at,
            )

        except Exception as e:
            logger.error(f"EnterPlanMode failed: {e}")
            return NativeToolResult.from_exception(e)

    def get_schema(self) -> Dict[str, Any]:
        """Get JSON Schema for tool parameters."""
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }


class ExitPlanModeTool(BaseTool):
    """Exit plan mode with completed plan for approval.

    The ExitPlanMode tool signals that the plan is complete and ready for
    user approval. Use this when:
    - Your plan is complete and unambiguous
    - All questions about requirements are resolved
    - You're ready to implement

    Do NOT use for:
    - Research tasks (no code implementation planned)
    - Asking "Is my plan okay?" (this tool IS the approval request)

    The plan should already be written to the plan file before calling this tool.

    Example:
        >>> tool = ExitPlanModeTool(on_exit=my_callback)
        >>> result = await tool.execute(
        ...     allowedPrompts=[
        ...         {"tool": "Bash", "prompt": "run tests"},
        ...         {"tool": "Bash", "prompt": "install dependencies"},
        ...     ]
        ... )
    """

    name = "exit_plan_mode"
    description = (
        "Exit plan mode and request user approval of your plan. "
        "The plan should already be written to the plan file. "
        "Include any permissions needed to implement the plan."
    )
    danger_level = DangerLevel.SAFE
    category = ToolCategory.CUSTOM

    def __init__(
        self,
        on_exit: Optional[PlanModeCallback] = None,
        state: Optional[PlanState] = None,
    ):
        """Initialize ExitPlanModeTool.

        Args:
            on_exit: Callback when plan mode is exited
            state: Shared plan state (for coordination with EnterPlanModeTool)
        """
        super().__init__()
        self._on_exit = on_exit
        self._state = state or PlanState()

    @property
    def state(self) -> PlanState:
        """Get current plan state."""
        return self._state

    def set_state(self, state: PlanState) -> None:
        """Set shared plan state."""
        self._state = state

    async def execute(
        self,
        allowedPrompts: Optional[List[Dict[str, str]]] = None,
        pushToRemote: bool = False,
        remoteSessionId: Optional[str] = None,
        remoteSessionTitle: Optional[str] = None,
        remoteSessionUrl: Optional[str] = None,
        **kwargs,
    ) -> NativeToolResult:
        """Exit plan mode and request approval.

        Args:
            allowedPrompts: List of permission prompts for plan execution.
                Each item should have 'tool' and 'prompt' keys.
            pushToRemote: Whether to push to remote session
            remoteSessionId: Remote session ID if pushing
            remoteSessionTitle: Remote session title if pushing
            remoteSessionUrl: Remote session URL if pushing

        Returns:
            NativeToolResult indicating plan mode exit

        Example:
            >>> result = await tool.execute(
            ...     allowedPrompts=[
            ...         {"tool": "Bash", "prompt": "run tests"},
            ...     ]
            ... )
        """
        try:
            # Check if in plan mode
            if self._state.mode != PlanMode.ACTIVE:
                return NativeToolResult.from_error(
                    f"Not in plan mode. Current mode: {self._state.mode.value}"
                )

            # Parse allowed prompts
            parsed_prompts: List[AllowedPrompt] = []
            if allowedPrompts:
                for i, prompt_data in enumerate(allowedPrompts):
                    if "tool" not in prompt_data:
                        return NativeToolResult.from_error(
                            f"allowedPrompts[{i}] missing 'tool' field"
                        )
                    if "prompt" not in prompt_data:
                        return NativeToolResult.from_error(
                            f"allowedPrompts[{i}] missing 'prompt' field"
                        )
                    parsed_prompts.append(AllowedPrompt.from_dict(prompt_data))

            # Update state
            self._state.mode = PlanMode.READY_FOR_APPROVAL
            self._state.allowed_prompts = parsed_prompts

            logger.info(f"Exited plan mode with {len(parsed_prompts)} permissions")

            # Call callback if provided
            if self._on_exit is not None:
                import asyncio

                if asyncio.iscoroutinefunction(self._on_exit):
                    await self._on_exit(self._state)
                else:
                    self._on_exit(self._state)

            return NativeToolResult.from_success(
                output="Plan ready for approval",
                mode=self._state.mode.value,
                allowed_prompts=[p.to_dict() for p in parsed_prompts],
                push_to_remote=pushToRemote,
                remote_session_id=remoteSessionId,
                remote_session_title=remoteSessionTitle,
                remote_session_url=remoteSessionUrl,
            )

        except Exception as e:
            logger.error(f"ExitPlanMode failed: {e}")
            return NativeToolResult.from_exception(e)

    def get_schema(self) -> Dict[str, Any]:
        """Get JSON Schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "allowedPrompts": {
                    "type": "array",
                    "description": (
                        "Prompt-based permissions needed to implement the plan. "
                        "Each describes a category of actions rather than specific commands."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "tool": {
                                "type": "string",
                                "enum": ["Bash"],
                                "description": "The tool this prompt applies to",
                            },
                            "prompt": {
                                "type": "string",
                                "description": (
                                    "Semantic description of the action, "
                                    "e.g., 'run tests', 'install dependencies'"
                                ),
                            },
                        },
                        "required": ["tool", "prompt"],
                    },
                },
                "pushToRemote": {
                    "type": "boolean",
                    "description": "Whether to push the plan to a remote session",
                },
                "remoteSessionId": {
                    "type": "string",
                    "description": "Remote session ID if pushing",
                },
                "remoteSessionTitle": {
                    "type": "string",
                    "description": "Remote session title if pushing",
                },
                "remoteSessionUrl": {
                    "type": "string",
                    "description": "Remote session URL if pushing",
                },
            },
            "additionalProperties": True,
        }


class PlanModeManager:
    """Manages plan mode state across tools.

    This class provides a coordinated way to manage plan mode state
    across EnterPlanModeTool and ExitPlanModeTool instances.

    Example:
        >>> manager = PlanModeManager()
        >>> enter_tool = manager.create_enter_tool()
        >>> exit_tool = manager.create_exit_tool()
        >>>
        >>> # Both tools share the same state
        >>> await enter_tool.execute()
        >>> print(manager.state.mode)  # "active"
        >>> await exit_tool.execute()
        >>> print(manager.state.mode)  # "ready_for_approval"
    """

    def __init__(
        self,
        on_enter: Optional[PlanModeCallback] = None,
        on_exit: Optional[PlanModeCallback] = None,
    ):
        """Initialize PlanModeManager.

        Args:
            on_enter: Callback when entering plan mode
            on_exit: Callback when exiting plan mode
        """
        self._state = PlanState()
        self._on_enter = on_enter
        self._on_exit = on_exit

    @property
    def state(self) -> PlanState:
        """Get current plan state."""
        return self._state

    @property
    def is_active(self) -> bool:
        """Check if plan mode is active."""
        return self._state.mode == PlanMode.ACTIVE

    @property
    def is_ready_for_approval(self) -> bool:
        """Check if plan is ready for approval."""
        return self._state.mode == PlanMode.READY_FOR_APPROVAL

    def create_enter_tool(self) -> EnterPlanModeTool:
        """Create EnterPlanModeTool with shared state."""
        return EnterPlanModeTool(
            on_enter=self._on_enter,
            state=self._state,
        )

    def create_exit_tool(self) -> ExitPlanModeTool:
        """Create ExitPlanModeTool with shared state."""
        return ExitPlanModeTool(
            on_exit=self._on_exit,
            state=self._state,
        )

    def approve(self) -> None:
        """Approve the current plan."""
        if self._state.mode == PlanMode.READY_FOR_APPROVAL:
            self._state.mode = PlanMode.APPROVED
            logger.info("Plan approved")

    def reset(self) -> None:
        """Reset plan mode state."""
        self._state = PlanState()
        logger.info("Plan mode reset")
