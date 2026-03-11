"""
Unit Tests for NotebookEditTool (Tier 1)

Tests the Jupyter notebook editing tool for autonomous agents.
Part of TODO-207 ClaudeCodeAgent Full Tool Parity.
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from kaizen.tools.native.notebook_tool import CellType, EditMode, NotebookEditTool
from kaizen.tools.types import DangerLevel, ToolCategory


class TestCellType:
    """Tests for CellType enum."""

    def test_cell_type_values(self):
        """Test all cell type values exist."""
        assert CellType.CODE.value == "code"
        assert CellType.MARKDOWN.value == "markdown"

    def test_cell_type_from_string(self):
        """Test creating cell type from string."""
        assert CellType("code") == CellType.CODE
        assert CellType("markdown") == CellType.MARKDOWN

    def test_invalid_cell_type_raises(self):
        """Test invalid cell type raises ValueError."""
        with pytest.raises(ValueError):
            CellType("invalid")


class TestEditMode:
    """Tests for EditMode enum."""

    def test_edit_mode_values(self):
        """Test all edit mode values exist."""
        assert EditMode.REPLACE.value == "replace"
        assert EditMode.INSERT.value == "insert"
        assert EditMode.DELETE.value == "delete"

    def test_edit_mode_from_string(self):
        """Test creating edit mode from string."""
        assert EditMode("replace") == EditMode.REPLACE
        assert EditMode("insert") == EditMode.INSERT
        assert EditMode("delete") == EditMode.DELETE


class TestNotebookEditTool:
    """Tests for NotebookEditTool class."""

    def test_tool_attributes(self):
        """Test tool has required attributes."""
        tool = NotebookEditTool()
        assert tool.name == "notebook_edit"
        assert tool.description != ""
        assert tool.danger_level == DangerLevel.MEDIUM
        assert tool.category == ToolCategory.SYSTEM

    def test_get_schema(self):
        """Test schema generation."""
        tool = NotebookEditTool()
        schema = tool.get_schema()
        assert schema["type"] == "object"
        assert "notebook_path" in schema["properties"]
        assert "new_source" in schema["properties"]
        assert "cell_id" in schema["properties"]
        assert "cell_type" in schema["properties"]
        assert "edit_mode" in schema["properties"]

    def test_get_full_schema(self):
        """Test full schema for LLM."""
        tool = NotebookEditTool()
        schema = tool.get_full_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "notebook_edit"

    @pytest.fixture
    def sample_notebook(self, tmp_path):
        """Create a sample notebook file."""
        notebook = {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {"kernelspec": {"name": "python3"}},
            "cells": [
                {
                    "id": "cell-001",
                    "cell_type": "code",
                    "source": "print('Hello')",
                    "metadata": {},
                    "outputs": [],
                    "execution_count": None,
                },
                {
                    "id": "cell-002",
                    "cell_type": "markdown",
                    "source": "# Heading",
                    "metadata": {},
                },
            ],
        }
        path = tmp_path / "test.ipynb"
        with open(path, "w") as f:
            json.dump(notebook, f)
        return str(path)

    @pytest.mark.asyncio
    async def test_replace_cell(self, sample_notebook):
        """Test replacing cell content."""
        tool = NotebookEditTool()
        result = await tool.execute(
            notebook_path=sample_notebook,
            new_source="print('Updated!')",
            cell_id="cell-001",
            cell_type="code",
            edit_mode="replace",
        )
        assert result.success is True
        assert "Replaced" in result.output

        # Verify file was updated
        with open(sample_notebook) as f:
            nb = json.load(f)
        assert nb["cells"][0]["source"] == "print('Updated!')"

    @pytest.mark.asyncio
    async def test_replace_cell_type(self, sample_notebook):
        """Test replacing cell and changing type."""
        tool = NotebookEditTool()
        result = await tool.execute(
            notebook_path=sample_notebook,
            new_source="# Code Comment",
            cell_id="cell-001",
            cell_type="markdown",
            edit_mode="replace",
        )
        assert result.success is True

        with open(sample_notebook) as f:
            nb = json.load(f)
        assert nb["cells"][0]["cell_type"] == "markdown"

    @pytest.mark.asyncio
    async def test_insert_cell_after(self, sample_notebook):
        """Test inserting cell after specified cell."""
        tool = NotebookEditTool()
        result = await tool.execute(
            notebook_path=sample_notebook,
            new_source="# New cell",
            cell_id="cell-001",
            cell_type="markdown",
            edit_mode="insert",
        )
        assert result.success is True
        assert "Inserted" in result.output

        with open(sample_notebook) as f:
            nb = json.load(f)
        assert len(nb["cells"]) == 3
        assert nb["cells"][1]["source"] == "# New cell"
        assert nb["cells"][1]["cell_type"] == "markdown"

    @pytest.mark.asyncio
    async def test_insert_cell_at_beginning(self, sample_notebook):
        """Test inserting cell at beginning."""
        tool = NotebookEditTool()
        result = await tool.execute(
            notebook_path=sample_notebook,
            new_source="# First cell",
            cell_id=None,  # Insert at beginning
            cell_type="markdown",
            edit_mode="insert",
        )
        assert result.success is True
        assert "beginning" in result.output

        with open(sample_notebook) as f:
            nb = json.load(f)
        assert len(nb["cells"]) == 3
        assert nb["cells"][0]["source"] == "# First cell"

    @pytest.mark.asyncio
    async def test_delete_cell(self, sample_notebook):
        """Test deleting cell."""
        tool = NotebookEditTool()
        result = await tool.execute(
            notebook_path=sample_notebook,
            new_source="",  # Ignored for delete
            cell_id="cell-001",
            edit_mode="delete",
        )
        assert result.success is True
        assert "Deleted" in result.output

        with open(sample_notebook) as f:
            nb = json.load(f)
        assert len(nb["cells"]) == 1
        assert nb["cells"][0]["id"] == "cell-002"

    @pytest.mark.asyncio
    async def test_cell_not_found(self, sample_notebook):
        """Test error when cell not found."""
        tool = NotebookEditTool()
        result = await tool.execute(
            notebook_path=sample_notebook,
            new_source="test",
            cell_id="nonexistent",
            edit_mode="replace",
        )
        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_notebook_not_found(self, tmp_path):
        """Test error when notebook not found."""
        tool = NotebookEditTool()
        result = await tool.execute(
            notebook_path=str(tmp_path / "nonexistent.ipynb"),
            new_source="test",
            cell_id="cell-001",
            edit_mode="replace",
        )
        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_invalid_json(self, tmp_path):
        """Test error on invalid JSON."""
        path = tmp_path / "invalid.ipynb"
        with open(path, "w") as f:
            f.write("not json")

        tool = NotebookEditTool()
        result = await tool.execute(
            notebook_path=str(path),
            new_source="test",
            cell_id="cell-001",
            edit_mode="replace",
        )
        assert result.success is False
        assert "Invalid" in result.error

    @pytest.mark.asyncio
    async def test_invalid_edit_mode(self, sample_notebook):
        """Test error on invalid edit mode."""
        tool = NotebookEditTool()
        result = await tool.execute(
            notebook_path=sample_notebook,
            new_source="test",
            cell_id="cell-001",
            edit_mode="invalid",
        )
        assert result.success is False
        assert "edit_mode" in result.error.lower()

    @pytest.mark.asyncio
    async def test_invalid_cell_type(self, sample_notebook):
        """Test error on invalid cell type."""
        tool = NotebookEditTool()
        result = await tool.execute(
            notebook_path=sample_notebook,
            new_source="test",
            cell_id="cell-001",
            cell_type="invalid",
            edit_mode="replace",
        )
        assert result.success is False
        assert "cell_type" in result.error.lower()

    @pytest.mark.asyncio
    async def test_empty_notebook_path(self):
        """Test error on empty notebook path."""
        tool = NotebookEditTool()
        result = await tool.execute(
            notebook_path="",
            new_source="test",
            edit_mode="insert",
        )
        assert result.success is False
        assert "required" in result.error.lower()

    @pytest.mark.asyncio
    async def test_relative_path_rejected(self, tmp_path):
        """Test relative path is rejected."""
        tool = NotebookEditTool()
        result = await tool.execute(
            notebook_path="relative/path.ipynb",
            new_source="test",
            edit_mode="insert",
        )
        assert result.success is False
        assert "absolute" in result.error.lower()

    @pytest.mark.asyncio
    async def test_non_ipynb_rejected(self, tmp_path):
        """Test non-.ipynb file is rejected."""
        path = tmp_path / "test.txt"
        path.write_text("text")

        tool = NotebookEditTool()
        result = await tool.execute(
            notebook_path=str(path),
            new_source="test",
            edit_mode="insert",
        )
        assert result.success is False
        assert ".ipynb" in result.error

    @pytest.mark.asyncio
    async def test_replace_requires_cell_id(self, sample_notebook):
        """Test replace mode requires cell_id."""
        tool = NotebookEditTool()
        result = await tool.execute(
            notebook_path=sample_notebook,
            new_source="test",
            cell_id=None,  # Missing
            edit_mode="replace",
        )
        assert result.success is False
        assert "cell_id" in result.error.lower()

    @pytest.mark.asyncio
    async def test_delete_requires_cell_id(self, sample_notebook):
        """Test delete mode requires cell_id."""
        tool = NotebookEditTool()
        result = await tool.execute(
            notebook_path=sample_notebook,
            new_source="",
            cell_id=None,  # Missing
            edit_mode="delete",
        )
        assert result.success is False
        assert "cell_id" in result.error.lower()

    @pytest.mark.asyncio
    async def test_insert_requires_source(self, sample_notebook):
        """Test insert mode requires source."""
        tool = NotebookEditTool()
        result = await tool.execute(
            notebook_path=sample_notebook,
            new_source="",  # Empty
            cell_type="code",
            edit_mode="insert",
        )
        assert result.success is False
        assert "new_source" in result.error.lower()

    @pytest.mark.asyncio
    async def test_insert_creates_new_notebook(self, tmp_path):
        """Test insert creates new notebook if doesn't exist."""
        path = tmp_path / "new.ipynb"

        tool = NotebookEditTool()
        result = await tool.execute(
            notebook_path=str(path),
            new_source="# First cell",
            cell_type="markdown",
            edit_mode="insert",
        )
        assert result.success is True

        with open(path) as f:
            nb = json.load(f)
        assert len(nb["cells"]) == 1
        assert nb["cells"][0]["source"] == "# First cell"

    @pytest.mark.asyncio
    async def test_code_cell_has_outputs(self, sample_notebook):
        """Test code cells have outputs array."""
        tool = NotebookEditTool()
        result = await tool.execute(
            notebook_path=sample_notebook,
            new_source="x = 1",
            cell_id="cell-001",
            cell_type="code",
            edit_mode="insert",
        )
        assert result.success is True

        with open(sample_notebook) as f:
            nb = json.load(f)
        # Find the inserted cell
        new_cell = nb["cells"][1]
        assert "outputs" in new_cell
        assert new_cell["outputs"] == []
        assert "execution_count" in new_cell

    @pytest.mark.asyncio
    async def test_result_metadata(self, sample_notebook):
        """Test result contains metadata."""
        tool = NotebookEditTool()
        result = await tool.execute(
            notebook_path=sample_notebook,
            new_source="test",
            cell_id="cell-001",
            edit_mode="replace",
        )
        assert "notebook_path" in result.metadata
        assert "edit_mode" in result.metadata
        assert "cell_count" in result.metadata

    @pytest.mark.asyncio
    async def test_missing_cells_key(self, tmp_path):
        """Test error when cells key is missing."""
        path = tmp_path / "bad.ipynb"
        with open(path, "w") as f:
            json.dump({"nbformat": 4}, f)

        tool = NotebookEditTool()
        result = await tool.execute(
            notebook_path=str(path),
            new_source="test",
            cell_id="cell-001",
            edit_mode="replace",
        )
        assert result.success is False
        assert "cells" in result.error.lower()

    @pytest.mark.asyncio
    async def test_home_directory_expansion(self, tmp_path, monkeypatch):
        """Test ~ is expanded to home directory."""
        # Create notebook in temp dir and monkeypatch expanduser
        nb_path = tmp_path / "test.ipynb"
        notebook = {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {},
            "cells": [
                {"id": "cell-001", "cell_type": "code", "source": "", "metadata": {}},
            ],
        }
        with open(nb_path, "w") as f:
            json.dump(notebook, f)

        # Monkeypatch expanduser to return our temp path
        def mock_expanduser(path):
            if path.startswith("~"):
                return str(tmp_path / path[2:])  # Replace ~ with tmp_path
            return path

        monkeypatch.setattr(os.path, "expanduser", mock_expanduser)

        tool = NotebookEditTool()
        result = await tool.execute(
            notebook_path="~/test.ipynb",
            new_source="updated",
            cell_id="cell-001",
            edit_mode="replace",
        )
        assert result.success is True
