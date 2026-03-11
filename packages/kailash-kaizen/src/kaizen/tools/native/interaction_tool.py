"""AskUserQuestionTool - Bidirectional user communication for autonomous agents.

Implements the AskUserQuestion tool that allows agents to ask users questions
during execution, matching Claude Code's AskUserQuestion functionality.
Supports multiple choice, multi-select, and free-form questions.

See: TODO-207 ClaudeCodeAgent Full Tool Parity

Example:
    >>> from kaizen.tools.native import AskUserQuestionTool, KaizenToolRegistry
    >>>
    >>> ask_tool = AskUserQuestionTool(user_callback=my_callback)
    >>> registry = KaizenToolRegistry()
    >>> registry.register(ask_tool)
    >>>
    >>> result = await registry.execute("ask_user_question", {
    ...     "questions": [
    ...         {
    ...             "question": "Which framework should we use?",
    ...             "header": "Framework",
    ...             "options": [
    ...                 {"label": "React", "description": "Popular UI library"},
    ...                 {"label": "Vue", "description": "Progressive framework"},
    ...             ],
    ...             "multiSelect": False,
    ...         }
    ...     ]
    ... })
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union

from kaizen.tools.native.base import BaseTool, NativeToolResult
from kaizen.tools.types import DangerLevel, ToolCategory

logger = logging.getLogger(__name__)


@dataclass
class QuestionOption:
    """A single option for a question.

    Attributes:
        label: Display text for the option (1-5 words)
        description: Explanation of what this option means
    """

    label: str
    description: str = ""

    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary."""
        return {
            "label": self.label,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QuestionOption":
        """Create from dictionary."""
        return cls(
            label=data["label"],
            description=data.get("description", ""),
        )


@dataclass
class Question:
    """A question to ask the user.

    Attributes:
        question: The complete question text
        header: Short label for display (max 12 chars)
        options: List of available options (2-4 options)
        multi_select: Whether multiple options can be selected
    """

    question: str
    header: str
    options: List[QuestionOption]
    multi_select: bool = False

    def validate(self) -> Optional[str]:
        """Validate question structure.

        Returns:
            Error message if invalid, None if valid
        """
        if not self.question.strip():
            return "Question text is required"
        if not self.header.strip():
            return "Header is required"
        if len(self.header) > 12:
            return f"Header must be max 12 characters, got {len(self.header)}"
        if len(self.options) < 2:
            return "At least 2 options are required"
        if len(self.options) > 4:
            return "Maximum 4 options allowed"
        for i, opt in enumerate(self.options):
            if not opt.label.strip():
                return f"Option {i} label is required"
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "question": self.question,
            "header": self.header,
            "options": [opt.to_dict() for opt in self.options],
            "multiSelect": self.multi_select,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Question":
        """Create from dictionary."""
        options = [
            QuestionOption.from_dict(opt) if isinstance(opt, dict) else opt
            for opt in data.get("options", [])
        ]
        return cls(
            question=data["question"],
            header=data["header"],
            options=options,
            multi_select=data.get("multiSelect", False),
        )


@dataclass
class QuestionAnswer:
    """Answer to a question.

    Attributes:
        question_index: Index of the question answered
        selected_labels: Labels of selected options
        custom_text: Custom text if "Other" was selected
        answered_at: Timestamp of answer
    """

    question_index: int
    selected_labels: List[str]
    custom_text: Optional[str] = None
    answered_at: str = ""

    def __post_init__(self):
        if not self.answered_at:
            self.answered_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "question_index": self.question_index,
            "selected_labels": self.selected_labels,
            "custom_text": self.custom_text,
            "answered_at": self.answered_at,
        }


# Type alias for user callback
# Can be sync or async function
UserCallback = Union[
    Callable[[List[Question]], List[QuestionAnswer]],
    Callable[[List[Question]], Awaitable[List[QuestionAnswer]]],
]


class AskUserQuestionTool(BaseTool):
    """Ask user questions during autonomous execution.

    The AskUserQuestion tool enables bidirectional communication between
    agents and users. Use this tool when you need to:
    - Gather user preferences or requirements
    - Clarify ambiguous instructions
    - Get decisions on implementation choices
    - Offer choices about what direction to take

    Question Structure:
    - question: Complete question text ending with ?
    - header: Short label (max 12 chars) like "Framework"
    - options: 2-4 choices, each with label and description
    - multiSelect: Whether multiple answers allowed

    Users can always select "Other" to provide custom text input.

    Example:
        >>> tool = AskUserQuestionTool(user_callback=my_callback)
        >>> result = await tool.execute(questions=[
        ...     {
        ...         "question": "Which database should we use?",
        ...         "header": "Database",
        ...         "options": [
        ...             {"label": "PostgreSQL", "description": "Robust relational DB"},
        ...             {"label": "MongoDB", "description": "Flexible document store"},
        ...         ],
        ...         "multiSelect": False,
        ...     }
        ... ])
        >>> print(result.output)  # User's selection
    """

    name = "ask_user_question"
    description = (
        "Ask the user questions during execution. Use this to gather preferences, "
        "clarify instructions, or get decisions. Each question has a header (max 12 chars), "
        "question text, and 2-4 options. Users can always select 'Other' for custom input."
    )
    danger_level = DangerLevel.SAFE
    category = ToolCategory.CUSTOM

    def __init__(
        self,
        user_callback: Optional[UserCallback] = None,
        timeout_seconds: float = 300.0,
    ):
        """Initialize AskUserQuestionTool.

        Args:
            user_callback: Function to call with questions and receive answers.
                          If None, tool will return without answers (for testing).
            timeout_seconds: Maximum time to wait for user response.
        """
        super().__init__()
        self._user_callback = user_callback
        self._timeout_seconds = timeout_seconds
        self._pending_questions: List[Question] = []
        self._answers: List[QuestionAnswer] = []

    def set_callback(self, callback: UserCallback) -> None:
        """Set or update the user callback."""
        self._user_callback = callback

    @property
    def pending_questions(self) -> List[Question]:
        """Get pending questions."""
        return self._pending_questions

    @property
    def answers(self) -> List[QuestionAnswer]:
        """Get collected answers."""
        return self._answers

    async def execute(
        self,
        questions: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> NativeToolResult:
        """Ask user questions and collect answers.

        Args:
            questions: List of question dictionaries, each with:
                - question (str): Complete question text
                - header (str): Short label (max 12 chars)
                - options (list): 2-4 options with label and description
                - multiSelect (bool): Whether multiple answers allowed
            metadata: Optional metadata for tracking (e.g., source)

        Returns:
            NativeToolResult with answers or timeout status

        Example:
            >>> result = await tool.execute(questions=[
            ...     {
            ...         "question": "Which auth method?",
            ...         "header": "Auth",
            ...         "options": [
            ...             {"label": "OAuth", "description": "Third-party auth"},
            ...             {"label": "JWT", "description": "Token-based auth"},
            ...         ],
            ...         "multiSelect": False,
            ...     }
            ... ])
        """
        try:
            # Validate questions
            if not questions:
                return NativeToolResult.from_error("questions list cannot be empty")

            if len(questions) > 4:
                return NativeToolResult.from_error(
                    f"Maximum 4 questions allowed, got {len(questions)}"
                )

            # Parse and validate each question
            parsed_questions: List[Question] = []
            for i, q_data in enumerate(questions):
                # Check required fields
                if "question" not in q_data:
                    return NativeToolResult.from_error(
                        f"Question {i} missing 'question' field"
                    )
                if "header" not in q_data:
                    return NativeToolResult.from_error(
                        f"Question {i} missing 'header' field"
                    )
                if "options" not in q_data:
                    return NativeToolResult.from_error(
                        f"Question {i} missing 'options' field"
                    )

                # Parse options
                options = []
                for j, opt in enumerate(q_data["options"]):
                    if isinstance(opt, dict):
                        if "label" not in opt:
                            return NativeToolResult.from_error(
                                f"Question {i} option {j} missing 'label'"
                            )
                        options.append(QuestionOption.from_dict(opt))
                    else:
                        return NativeToolResult.from_error(
                            f"Question {i} option {j} must be a dictionary"
                        )

                question = Question(
                    question=q_data["question"],
                    header=q_data["header"],
                    options=options,
                    multi_select=q_data.get("multiSelect", False),
                )

                # Validate question
                error = question.validate()
                if error:
                    return NativeToolResult.from_error(f"Question {i}: {error}")

                parsed_questions.append(question)

            self._pending_questions = parsed_questions

            # If no callback, return placeholder (for testing)
            if self._user_callback is None:
                logger.warning("No user callback configured, returning without answers")
                return NativeToolResult.from_success(
                    output="Questions presented (no callback configured)",
                    questions=[q.to_dict() for q in parsed_questions],
                    answers=[],
                    status="no_callback",
                    metadata=metadata or {},
                )

            # Call user callback
            try:
                # Handle both sync and async callbacks
                if asyncio.iscoroutinefunction(self._user_callback):
                    answers = await asyncio.wait_for(
                        self._user_callback(parsed_questions),
                        timeout=self._timeout_seconds,
                    )
                else:
                    answers = await asyncio.wait_for(
                        asyncio.to_thread(self._user_callback, parsed_questions),
                        timeout=self._timeout_seconds,
                    )
            except asyncio.TimeoutError:
                logger.warning(f"User response timeout after {self._timeout_seconds}s")
                return NativeToolResult.from_error(
                    f"Timeout: User response not received after {self._timeout_seconds} seconds"
                )
            except Exception as e:
                logger.error(f"User callback failed: {e}")
                return NativeToolResult.from_error(f"User callback failed: {e}")

            # Store answers
            self._answers = answers if answers else []
            self._pending_questions = []  # Clear pending

            # Format answers for output
            answer_text = []
            for ans in self._answers:
                if ans.custom_text:
                    answer_text.append(f"Q{ans.question_index}: {ans.custom_text}")
                else:
                    answer_text.append(
                        f"Q{ans.question_index}: {', '.join(ans.selected_labels)}"
                    )

            logger.info(f"Received {len(self._answers)} answers from user")

            return NativeToolResult.from_success(
                output="\n".join(answer_text) if answer_text else "No answers provided",
                questions=[q.to_dict() for q in parsed_questions],
                answers=[a.to_dict() for a in self._answers],
                status="answered",
                metadata=metadata or {},
            )

        except Exception as e:
            logger.error(f"AskUserQuestion failed: {e}")
            return NativeToolResult.from_exception(e)

    def get_schema(self) -> Dict[str, Any]:
        """Get JSON Schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "description": "Questions to ask the user (1-4 questions)",
                    "minItems": 1,
                    "maxItems": 4,
                    "items": {
                        "type": "object",
                        "properties": {
                            "question": {
                                "type": "string",
                                "description": "Complete question to ask the user",
                            },
                            "header": {
                                "type": "string",
                                "maxLength": 12,
                                "description": "Short label (max 12 chars)",
                            },
                            "options": {
                                "type": "array",
                                "minItems": 2,
                                "maxItems": 4,
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "label": {
                                            "type": "string",
                                            "description": "Option display text",
                                        },
                                        "description": {
                                            "type": "string",
                                            "description": "Option explanation",
                                        },
                                    },
                                    "required": ["label"],
                                },
                            },
                            "multiSelect": {
                                "type": "boolean",
                                "default": False,
                                "description": "Allow multiple selections",
                            },
                        },
                        "required": ["question", "header", "options"],
                    },
                },
                "metadata": {
                    "type": "object",
                    "description": "Optional metadata for tracking",
                    "additionalProperties": True,
                },
            },
            "required": ["questions"],
        }

    def clear_answers(self) -> None:
        """Clear stored answers."""
        self._answers = []
        self._pending_questions = []
