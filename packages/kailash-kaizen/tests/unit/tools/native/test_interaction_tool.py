"""
Unit Tests for AskUserQuestionTool (Tier 1)

Tests the user interaction tool for autonomous agents.
Part of TODO-207 ClaudeCodeAgent Full Tool Parity.
"""

import asyncio
from typing import List

import pytest

from kaizen.tools.native.interaction_tool import (
    AskUserQuestionTool,
    Question,
    QuestionAnswer,
    QuestionOption,
)
from kaizen.tools.types import DangerLevel, ToolCategory


class TestQuestionOption:
    """Tests for QuestionOption dataclass."""

    def test_create_option(self):
        """Test creating an option."""
        opt = QuestionOption(label="React", description="UI library")
        assert opt.label == "React"
        assert opt.description == "UI library"

    def test_to_dict(self):
        """Test serialization."""
        opt = QuestionOption(label="React", description="UI library")
        data = opt.to_dict()
        assert data["label"] == "React"
        assert data["description"] == "UI library"

    def test_from_dict(self):
        """Test deserialization."""
        data = {"label": "Vue", "description": "Progressive framework"}
        opt = QuestionOption.from_dict(data)
        assert opt.label == "Vue"
        assert opt.description == "Progressive framework"

    def test_from_dict_minimal(self):
        """Test from_dict with minimal data."""
        data = {"label": "Angular"}
        opt = QuestionOption.from_dict(data)
        assert opt.label == "Angular"
        assert opt.description == ""


class TestQuestion:
    """Tests for Question dataclass."""

    def test_create_question(self):
        """Test creating a question."""
        q = Question(
            question="Which framework?",
            header="Framework",
            options=[
                QuestionOption("React", "UI library"),
                QuestionOption("Vue", "Progressive"),
            ],
            multi_select=False,
        )
        assert q.question == "Which framework?"
        assert q.header == "Framework"
        assert len(q.options) == 2
        assert q.multi_select is False

    def test_validate_valid(self):
        """Test validation passes for valid question."""
        q = Question(
            question="Which one?",
            header="Choice",
            options=[
                QuestionOption("A", ""),
                QuestionOption("B", ""),
            ],
        )
        assert q.validate() is None

    def test_validate_empty_question(self):
        """Test validation fails for empty question."""
        q = Question(
            question="",
            header="Choice",
            options=[QuestionOption("A", ""), QuestionOption("B", "")],
        )
        error = q.validate()
        assert error is not None
        assert "Question" in error

    def test_validate_empty_header(self):
        """Test validation fails for empty header."""
        q = Question(
            question="Which one?",
            header="",
            options=[QuestionOption("A", ""), QuestionOption("B", "")],
        )
        error = q.validate()
        assert error is not None
        assert "Header" in error

    def test_validate_header_too_long(self):
        """Test validation fails for header > 12 chars."""
        q = Question(
            question="Which one?",
            header="This is too long",
            options=[QuestionOption("A", ""), QuestionOption("B", "")],
        )
        error = q.validate()
        assert error is not None
        assert "12" in error

    def test_validate_too_few_options(self):
        """Test validation fails for < 2 options."""
        q = Question(
            question="Which one?",
            header="Choice",
            options=[QuestionOption("A", "")],
        )
        error = q.validate()
        assert error is not None
        assert "2 options" in error

    def test_validate_too_many_options(self):
        """Test validation fails for > 4 options."""
        q = Question(
            question="Which one?",
            header="Choice",
            options=[
                QuestionOption("A", ""),
                QuestionOption("B", ""),
                QuestionOption("C", ""),
                QuestionOption("D", ""),
                QuestionOption("E", ""),
            ],
        )
        error = q.validate()
        assert error is not None
        assert "4" in error

    def test_validate_empty_option_label(self):
        """Test validation fails for empty option label."""
        q = Question(
            question="Which one?",
            header="Choice",
            options=[QuestionOption("A", ""), QuestionOption("", "")],
        )
        error = q.validate()
        assert error is not None
        assert "label" in error.lower()

    def test_to_dict(self):
        """Test serialization."""
        q = Question(
            question="Which one?",
            header="Choice",
            options=[QuestionOption("A", "Desc A")],
            multi_select=True,
        )
        # Add another option to pass validation (not testing validation here)
        q.options.append(QuestionOption("B", "Desc B"))
        data = q.to_dict()
        assert data["question"] == "Which one?"
        assert data["header"] == "Choice"
        assert data["multiSelect"] is True
        assert len(data["options"]) == 2

    def test_from_dict(self):
        """Test deserialization."""
        data = {
            "question": "Pick one?",
            "header": "Pick",
            "options": [
                {"label": "X", "description": "Desc X"},
                {"label": "Y", "description": "Desc Y"},
            ],
            "multiSelect": True,
        }
        q = Question.from_dict(data)
        assert q.question == "Pick one?"
        assert q.header == "Pick"
        assert q.multi_select is True
        assert len(q.options) == 2


class TestQuestionAnswer:
    """Tests for QuestionAnswer dataclass."""

    def test_create_answer(self):
        """Test creating an answer."""
        ans = QuestionAnswer(
            question_index=0,
            selected_labels=["React"],
        )
        assert ans.question_index == 0
        assert ans.selected_labels == ["React"]
        assert ans.answered_at != ""

    def test_create_with_custom_text(self):
        """Test answer with custom text."""
        ans = QuestionAnswer(
            question_index=1,
            selected_labels=["Other"],
            custom_text="Custom framework",
        )
        assert ans.custom_text == "Custom framework"

    def test_to_dict(self):
        """Test serialization."""
        ans = QuestionAnswer(
            question_index=0,
            selected_labels=["A", "B"],
            custom_text=None,
        )
        data = ans.to_dict()
        assert data["question_index"] == 0
        assert data["selected_labels"] == ["A", "B"]
        assert "answered_at" in data


class TestAskUserQuestionTool:
    """Tests for AskUserQuestionTool class."""

    def test_tool_attributes(self):
        """Test tool has required attributes."""
        tool = AskUserQuestionTool()
        assert tool.name == "ask_user_question"
        assert tool.description != ""
        assert tool.danger_level == DangerLevel.SAFE
        assert tool.category == ToolCategory.CUSTOM

    def test_get_schema(self):
        """Test schema generation."""
        tool = AskUserQuestionTool()
        schema = tool.get_schema()
        assert schema["type"] == "object"
        assert "questions" in schema["properties"]
        assert schema["properties"]["questions"]["type"] == "array"

    def test_get_full_schema(self):
        """Test full schema for LLM."""
        tool = AskUserQuestionTool()
        schema = tool.get_full_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "ask_user_question"

    @pytest.mark.asyncio
    async def test_execute_no_callback(self):
        """Test execute without callback returns placeholder."""
        tool = AskUserQuestionTool(user_callback=None)
        result = await tool.execute(
            questions=[
                {
                    "question": "Which one?",
                    "header": "Choice",
                    "options": [
                        {"label": "A", "description": ""},
                        {"label": "B", "description": ""},
                    ],
                }
            ]
        )
        assert result.success is True
        assert "no callback" in result.metadata.get(
            "status", ""
        ).lower() or "no_callback" in result.metadata.get("status", "")

    @pytest.mark.asyncio
    async def test_execute_empty_questions(self):
        """Test execute with empty questions fails."""
        tool = AskUserQuestionTool()
        result = await tool.execute(questions=[])
        assert result.success is False
        assert "empty" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_too_many_questions(self):
        """Test execute with > 4 questions fails."""
        tool = AskUserQuestionTool()
        questions = [
            {
                "question": f"Q{i}?",
                "header": f"Q{i}",
                "options": [{"label": "A"}, {"label": "B"}],
            }
            for i in range(5)
        ]
        result = await tool.execute(questions=questions)
        assert result.success is False
        assert "4" in result.error

    @pytest.mark.asyncio
    async def test_execute_missing_question_field(self):
        """Test execute with missing question field fails."""
        tool = AskUserQuestionTool()
        result = await tool.execute(
            questions=[
                {
                    "header": "Choice",
                    "options": [{"label": "A"}, {"label": "B"}],
                }
            ]
        )
        assert result.success is False
        assert "question" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_missing_header_field(self):
        """Test execute with missing header field fails."""
        tool = AskUserQuestionTool()
        result = await tool.execute(
            questions=[
                {
                    "question": "Which?",
                    "options": [{"label": "A"}, {"label": "B"}],
                }
            ]
        )
        assert result.success is False
        assert "header" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_missing_options_field(self):
        """Test execute with missing options field fails."""
        tool = AskUserQuestionTool()
        result = await tool.execute(
            questions=[
                {
                    "question": "Which?",
                    "header": "Choice",
                }
            ]
        )
        assert result.success is False
        assert "options" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_missing_option_label(self):
        """Test execute with missing option label fails."""
        tool = AskUserQuestionTool()
        result = await tool.execute(
            questions=[
                {
                    "question": "Which?",
                    "header": "Choice",
                    "options": [{"description": "no label"}, {"label": "B"}],
                }
            ]
        )
        assert result.success is False
        assert "label" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_header_too_long(self):
        """Test execute with header > 12 chars fails."""
        tool = AskUserQuestionTool()
        result = await tool.execute(
            questions=[
                {
                    "question": "Which?",
                    "header": "This header is too long",
                    "options": [{"label": "A"}, {"label": "B"}],
                }
            ]
        )
        assert result.success is False
        assert "12" in result.error

    @pytest.mark.asyncio
    async def test_execute_with_sync_callback(self):
        """Test execute with synchronous callback."""

        def sync_callback(questions: List[Question]) -> List[QuestionAnswer]:
            return [
                QuestionAnswer(
                    question_index=0,
                    selected_labels=["React"],
                )
            ]

        tool = AskUserQuestionTool(user_callback=sync_callback)
        result = await tool.execute(
            questions=[
                {
                    "question": "Framework?",
                    "header": "Framework",
                    "options": [
                        {"label": "React", "description": ""},
                        {"label": "Vue", "description": ""},
                    ],
                }
            ]
        )
        assert result.success is True
        assert "React" in result.output
        assert result.metadata["status"] == "answered"

    @pytest.mark.asyncio
    async def test_execute_with_async_callback(self):
        """Test execute with async callback."""

        async def async_callback(questions: List[Question]) -> List[QuestionAnswer]:
            await asyncio.sleep(0.01)  # Simulate async work
            return [
                QuestionAnswer(
                    question_index=0,
                    selected_labels=["Vue"],
                )
            ]

        tool = AskUserQuestionTool(user_callback=async_callback)
        result = await tool.execute(
            questions=[
                {
                    "question": "Framework?",
                    "header": "Framework",
                    "options": [
                        {"label": "React", "description": ""},
                        {"label": "Vue", "description": ""},
                    ],
                }
            ]
        )
        assert result.success is True
        assert "Vue" in result.output

    @pytest.mark.asyncio
    async def test_execute_with_custom_text(self):
        """Test execute with custom text answer."""

        def callback(questions: List[Question]) -> List[QuestionAnswer]:
            return [
                QuestionAnswer(
                    question_index=0,
                    selected_labels=["Other"],
                    custom_text="Custom framework",
                )
            ]

        tool = AskUserQuestionTool(user_callback=callback)
        result = await tool.execute(
            questions=[
                {
                    "question": "Framework?",
                    "header": "Framework",
                    "options": [
                        {"label": "React", "description": ""},
                        {"label": "Vue", "description": ""},
                    ],
                }
            ]
        )
        assert result.success is True
        assert "Custom framework" in result.output

    @pytest.mark.asyncio
    async def test_execute_with_multi_select(self):
        """Test execute with multi-select question."""

        def callback(questions: List[Question]) -> List[QuestionAnswer]:
            return [
                QuestionAnswer(
                    question_index=0,
                    selected_labels=["React", "Vue"],
                )
            ]

        tool = AskUserQuestionTool(user_callback=callback)
        result = await tool.execute(
            questions=[
                {
                    "question": "Frameworks?",
                    "header": "Frameworks",
                    "options": [
                        {"label": "React"},
                        {"label": "Vue"},
                        {"label": "Angular"},
                    ],
                    "multiSelect": True,
                }
            ]
        )
        assert result.success is True
        assert "React" in result.output
        assert "Vue" in result.output

    @pytest.mark.asyncio
    async def test_execute_timeout(self):
        """Test execute times out."""

        async def slow_callback(questions: List[Question]) -> List[QuestionAnswer]:
            await asyncio.sleep(10)  # Longer than timeout
            return []

        tool = AskUserQuestionTool(
            user_callback=slow_callback,
            timeout_seconds=0.1,  # Very short timeout
        )
        result = await tool.execute(
            questions=[
                {
                    "question": "Quick?",
                    "header": "Quick",
                    "options": [{"label": "A"}, {"label": "B"}],
                }
            ]
        )
        assert result.success is False
        assert "timeout" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_callback_error(self):
        """Test execute handles callback errors."""

        def bad_callback(questions: List[Question]) -> List[QuestionAnswer]:
            raise ValueError("Callback error")

        tool = AskUserQuestionTool(user_callback=bad_callback)
        result = await tool.execute(
            questions=[
                {
                    "question": "Test?",
                    "header": "Test",
                    "options": [{"label": "A"}, {"label": "B"}],
                }
            ]
        )
        assert result.success is False
        assert "callback" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_returns_metadata(self):
        """Test execute returns proper metadata."""
        tool = AskUserQuestionTool()
        result = await tool.execute(
            questions=[
                {
                    "question": "Test?",
                    "header": "Test",
                    "options": [{"label": "A"}, {"label": "B"}],
                }
            ]
        )
        assert "questions" in result.metadata
        assert "answers" in result.metadata

    def test_set_callback(self):
        """Test setting callback after init."""
        tool = AskUserQuestionTool()
        assert tool._user_callback is None

        def callback(q):
            return []

        tool.set_callback(callback)
        assert tool._user_callback is callback

    def test_pending_questions_property(self):
        """Test pending_questions property."""
        tool = AskUserQuestionTool()
        assert tool.pending_questions == []

    def test_answers_property(self):
        """Test answers property."""
        tool = AskUserQuestionTool()
        assert tool.answers == []

    def test_clear_answers(self):
        """Test clearing answers."""
        tool = AskUserQuestionTool()
        tool._answers = [QuestionAnswer(0, ["A"])]
        tool.clear_answers()
        assert tool.answers == []
        assert tool.pending_questions == []

    def test_is_safe(self):
        """Test tool is marked as safe."""
        tool = AskUserQuestionTool()
        assert tool.is_safe() is True

    @pytest.mark.asyncio
    async def test_execute_with_metadata(self):
        """Test execute with metadata parameter."""
        tool = AskUserQuestionTool()
        result = await tool.execute(
            questions=[
                {
                    "question": "Test?",
                    "header": "Test",
                    "options": [{"label": "A"}, {"label": "B"}],
                }
            ],
            metadata={"source": "test"},
        )
        assert result.success is True
        assert result.metadata.get("metadata", {}).get("source") == "test"

    @pytest.mark.asyncio
    async def test_execute_multiple_questions(self):
        """Test execute with multiple questions."""

        def callback(questions: List[Question]) -> List[QuestionAnswer]:
            return [
                QuestionAnswer(0, ["A"]),
                QuestionAnswer(1, ["X"]),
            ]

        tool = AskUserQuestionTool(user_callback=callback)
        result = await tool.execute(
            questions=[
                {
                    "question": "First?",
                    "header": "First",
                    "options": [{"label": "A"}, {"label": "B"}],
                },
                {
                    "question": "Second?",
                    "header": "Second",
                    "options": [{"label": "X"}, {"label": "Y"}],
                },
            ]
        )
        assert result.success is True
        assert len(result.metadata["answers"]) == 2
