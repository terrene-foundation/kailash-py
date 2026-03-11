"""SkillTool - Skill invocation for autonomous execution.

Implements the Skill tool that invokes registered skills dynamically,
loading skill content on demand (progressive disclosure) and injecting
it into the execution context.

See: TODO-203 Task/Skill Tools, ADR-013 Specialist System

Example:
    >>> from kaizen.tools.native import SkillTool, KaizenToolRegistry
    >>> from kaizen.runtime.adapters import LocalKaizenAdapter
    >>>
    >>> adapter = LocalKaizenAdapter(kaizen_options=options)
    >>> skill_tool = SkillTool(adapter=adapter)
    >>> registry = KaizenToolRegistry()
    >>> registry.register(skill_tool)
    >>>
    >>> result = await registry.execute("skill", {
    ...     "skill_name": "python-patterns",
    ... })
    >>> print(result.output.content)
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from kaizen.execution.events import SkillCompleteEvent, SkillInvokeEvent
from kaizen.execution.subagent_result import SkillResult
from kaizen.tools.native.base import BaseTool, NativeToolResult
from kaizen.tools.types import DangerLevel, ToolCategory

if TYPE_CHECKING:
    from kaizen.runtime.adapters.kaizen_local import LocalKaizenAdapter

logger = logging.getLogger(__name__)

# Type alias for event callback
EventCallback = Callable[[Any], None]


class SkillTool(BaseTool):
    """Invoke registered skills to augment agent capabilities.

    The Skill tool enables knowledge injection by loading skill content
    dynamically. Skills provide domain-specific knowledge that agents
    can use to improve their responses.

    Features:
    - Query skills from registry
    - Progressive disclosure (metadata first, content on demand)
    - Load additional files from skill directory
    - Emit events for tracking

    Parameters:
        skill_name: Name of skill to invoke (from registry)
        load_additional_files: Whether to load additional .md files

    Example:
        >>> result = await skill_tool.execute(skill_name="python-patterns")
        >>> print(result.output.content)
        >>> print(result.output.additional_files)  # {"examples.md": "..."}
    """

    name = "skill"
    description = (
        "Invoke a registered skill to get domain-specific knowledge. "
        "Use this when you need expert knowledge on a specific topic."
    )
    danger_level = DangerLevel.SAFE  # Read-only operation
    category = ToolCategory.DATA

    def __init__(
        self,
        adapter: Optional["LocalKaizenAdapter"] = None,
        agent_id: Optional[str] = None,
        on_event: Optional[EventCallback] = None,
        session_id: Optional[str] = None,
    ):
        """Initialize SkillTool.

        Args:
            adapter: LocalKaizenAdapter with skill registry
            agent_id: ID of the agent invoking skills
            on_event: Callback for emitting execution events
            session_id: Session ID for event correlation
        """
        super().__init__()
        self._adapter = adapter
        self._agent_id = agent_id or f"agent_{uuid.uuid4().hex[:8]}"
        self._on_event = on_event
        self._session_id = session_id or f"session_{uuid.uuid4().hex[:8]}"

    async def execute(
        self,
        skill_name: str,
        load_additional_files: bool = True,
    ) -> NativeToolResult:
        """Invoke a registered skill.

        Args:
            skill_name: Name of skill to invoke (from registry)
            load_additional_files: Whether to load additional .md files

        Returns:
            NativeToolResult with SkillResult in output
        """
        # Validate adapter
        if self._adapter is None:
            return NativeToolResult.from_error(
                "SkillTool requires an adapter with skill registry"
            )

        # Emit skill_invoke event
        invoke_event = SkillInvokeEvent(
            session_id=self._session_id,
            skill_name=skill_name,
            agent_id=self._agent_id,
            args={"load_additional_files": load_additional_files},
        )
        await self._emit_event(invoke_event)

        # Get skill from registry
        skill = self._adapter.get_skill(skill_name)
        if skill is None:
            available = self._adapter.list_skills()
            error_msg = (
                f"Skill '{skill_name}' not found. "
                f"Available skills: {', '.join(available) if available else 'none'}"
            )

            # Emit error completion event
            complete_event = SkillCompleteEvent(
                session_id=self._session_id,
                skill_name=skill_name,
                agent_id=self._agent_id,
                success=False,
                error_message=error_msg,
            )
            await self._emit_event(complete_event)

            return NativeToolResult.from_error(error_msg)

        try:
            # Load skill content (progressive disclosure)
            loaded_skill = self._adapter.load_skill_content(skill)

            # Build result
            content = loaded_skill.skill_content or ""
            additional_files = {}

            if load_additional_files and loaded_skill.additional_files:
                additional_files = loaded_skill.additional_files

            result = SkillResult.from_success(
                skill_name=skill_name,
                content=content,
                description=loaded_skill.description,
                location=loaded_skill.location,
                source=loaded_skill.source,
                additional_files=additional_files,
            )

            # Emit completion event
            complete_event = SkillCompleteEvent(
                session_id=self._session_id,
                skill_name=skill_name,
                agent_id=self._agent_id,
                success=True,
                content_loaded=True,
                content_size=len(content),
                additional_files_count=len(additional_files),
            )
            await self._emit_event(complete_event)

            return NativeToolResult.from_success(
                result,
                skill_name=skill_name,
                content_size=len(content),
                additional_files=list(additional_files.keys()),
            )

        except Exception as e:
            logger.exception(f"Failed to load skill: {e}")

            # Emit error completion event
            complete_event = SkillCompleteEvent(
                session_id=self._session_id,
                skill_name=skill_name,
                agent_id=self._agent_id,
                success=False,
                error_message=str(e),
            )
            await self._emit_event(complete_event)

            result = SkillResult.from_error(
                skill_name=skill_name,
                error_message=str(e),
            )

            return NativeToolResult.from_error(
                f"Failed to load skill '{skill_name}': {e}",
                skill_result=result.to_dict(),
            )

    def list_skills(self) -> List[str]:
        """List all available skills.

        Returns:
            List of skill names
        """
        if self._adapter is None:
            return []
        return self._adapter.list_skills()

    def get_skill_info(self, skill_name: str) -> Optional[Dict[str, Any]]:
        """Get metadata about a skill without loading content.

        Args:
            skill_name: Name of skill

        Returns:
            Skill metadata dict or None if not found
        """
        if self._adapter is None:
            return None

        skill = self._adapter.get_skill(skill_name)
        if skill is None:
            return None

        return {
            "name": skill.name,
            "description": skill.description,
            "location": skill.location,
            "source": skill.source,
            "is_loaded": skill.is_loaded,
        }

    async def _emit_event(self, event: Any) -> None:
        """Emit an execution event.

        Args:
            event: Event to emit
        """
        if self._on_event:
            try:
                import asyncio

                if asyncio.iscoroutinefunction(self._on_event):
                    await self._on_event(event)
                else:
                    self._on_event(event)
            except Exception as e:
                logger.warning(f"Failed to emit event: {e}")

    def get_schema(self) -> Dict[str, Any]:
        """Return JSON Schema for LLM function calling."""
        return {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": (
                        "The name of the skill to invoke from the registry. "
                        "Use list_skills() to see available skills."
                    ),
                },
                "load_additional_files": {
                    "type": "boolean",
                    "description": (
                        "Whether to load additional .md files from the skill directory. "
                        "Set to false for faster loading if you only need the main content."
                    ),
                    "default": True,
                },
            },
            "required": ["skill_name"],
        }


__all__ = ["SkillTool"]
