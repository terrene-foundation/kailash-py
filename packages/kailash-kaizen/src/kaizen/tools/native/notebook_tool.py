"""NotebookEditTool - Jupyter notebook cell editing for autonomous agents.

Implements the NotebookEdit tool that allows editing Jupyter notebook cells,
matching Claude Code's NotebookEdit functionality. Supports replace, insert,
and delete operations on notebook cells.

See: TODO-207 ClaudeCodeAgent Full Tool Parity

Example:
    >>> from kaizen.tools.native import NotebookEditTool, KaizenToolRegistry
    >>>
    >>> notebook_tool = NotebookEditTool()
    >>> registry = KaizenToolRegistry()
    >>> registry.register(notebook_tool)
    >>>
    >>> result = await registry.execute("notebook_edit", {
    ...     "notebook_path": "/path/to/notebook.ipynb",
    ...     "new_source": "print('Hello, world!')",
    ...     "cell_id": "cell-001",
    ...     "cell_type": "code",
    ...     "edit_mode": "replace",
    ... })
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from kaizen.tools.native.base import BaseTool, NativeToolResult
from kaizen.tools.types import DangerLevel, ToolCategory

logger = logging.getLogger(__name__)


class CellType(str, Enum):
    """Valid Jupyter notebook cell types."""

    CODE = "code"
    MARKDOWN = "markdown"


class EditMode(str, Enum):
    """Notebook cell edit modes."""

    REPLACE = "replace"  # Replace existing cell content
    INSERT = "insert"  # Insert new cell after specified cell
    DELETE = "delete"  # Delete specified cell


class NotebookEditTool(BaseTool):
    """Edit Jupyter notebook cells.

    The NotebookEdit tool enables agents to modify Jupyter notebooks by:
    - Replacing cell content
    - Inserting new cells
    - Deleting existing cells

    Jupyter notebooks (.ipynb) are JSON files with a specific structure:
    - nbformat: Notebook format version
    - cells: List of cell objects
    - metadata: Notebook metadata

    Each cell has:
    - cell_type: "code" or "markdown"
    - source: Cell content (string or list of strings)
    - id: Optional cell identifier
    - metadata: Cell metadata
    - outputs: For code cells, execution outputs
    - execution_count: For code cells, execution count

    Parameters:
        notebook_path: Absolute path to the .ipynb file
        new_source: New content for the cell
        cell_id: ID of cell to edit (for replace/delete)
        cell_type: "code" or "markdown" (for insert)
        edit_mode: "replace", "insert", or "delete"

    Example:
        >>> result = await tool.execute(
        ...     notebook_path="/path/to/notebook.ipynb",
        ...     new_source="import pandas as pd\\ndf = pd.read_csv('data.csv')",
        ...     cell_id="cell-001",
        ...     cell_type="code",
        ...     edit_mode="replace",
        ... )
    """

    name = "notebook_edit"
    description = (
        "Edit Jupyter notebook (.ipynb) cells. Supports replacing cell content, "
        "inserting new cells, and deleting cells. Use edit_mode='replace' to "
        "modify existing cells, 'insert' to add new cells, and 'delete' to remove cells."
    )
    danger_level = DangerLevel.MEDIUM  # Modifies files
    category = ToolCategory.SYSTEM

    def __init__(self):
        """Initialize NotebookEditTool."""
        super().__init__()

    async def execute(
        self,
        notebook_path: str,
        new_source: str,
        cell_id: Optional[str] = None,
        cell_type: str = "code",
        edit_mode: str = "replace",
        **kwargs,
    ) -> NativeToolResult:
        """Edit a Jupyter notebook cell.

        Args:
            notebook_path: Absolute path to the .ipynb file
            new_source: New content for the cell (for replace/insert)
            cell_id: ID of cell to edit/delete, or after which to insert
            cell_type: "code" or "markdown" (required for insert)
            edit_mode: "replace", "insert", or "delete"

        Returns:
            NativeToolResult with success status and details

        Example:
            >>> # Replace cell content
            >>> result = await tool.execute(
            ...     notebook_path="/path/to/nb.ipynb",
            ...     new_source="print('Updated!')",
            ...     cell_id="cell-001",
            ...     edit_mode="replace",
            ... )
            >>>
            >>> # Insert new cell
            >>> result = await tool.execute(
            ...     notebook_path="/path/to/nb.ipynb",
            ...     new_source="# New section",
            ...     cell_id="cell-001",  # Insert after this cell
            ...     cell_type="markdown",
            ...     edit_mode="insert",
            ... )
            >>>
            >>> # Delete cell
            >>> result = await tool.execute(
            ...     notebook_path="/path/to/nb.ipynb",
            ...     new_source="",  # Ignored for delete
            ...     cell_id="cell-001",
            ...     edit_mode="delete",
            ... )
        """
        try:
            # Validate notebook path
            if not notebook_path:
                return NativeToolResult.from_error("notebook_path is required")

            notebook_path = os.path.expanduser(notebook_path)
            path = Path(notebook_path)

            if not path.is_absolute():
                return NativeToolResult.from_error(
                    f"notebook_path must be absolute, got: {notebook_path}"
                )

            if not path.suffix == ".ipynb":
                return NativeToolResult.from_error(
                    f"File must be a Jupyter notebook (.ipynb), got: {path.suffix}"
                )

            # Validate edit mode
            try:
                mode = EditMode(edit_mode)
            except ValueError:
                return NativeToolResult.from_error(
                    f"Invalid edit_mode '{edit_mode}'. "
                    f"Must be one of: replace, insert, delete"
                )

            # Validate cell type
            try:
                ctype = CellType(cell_type)
            except ValueError:
                return NativeToolResult.from_error(
                    f"Invalid cell_type '{cell_type}'. "
                    f"Must be one of: code, markdown"
                )

            # For replace and delete, cell_id is required
            if mode in (EditMode.REPLACE, EditMode.DELETE) and not cell_id:
                return NativeToolResult.from_error(
                    f"cell_id is required for edit_mode='{mode.value}'"
                )

            # For insert, new_source is required
            if mode == EditMode.INSERT and not new_source:
                return NativeToolResult.from_error(
                    "new_source is required for edit_mode='insert'"
                )

            # Read notebook
            if not path.exists():
                # For insert mode, create new notebook if doesn't exist
                if mode == EditMode.INSERT:
                    notebook = self._create_empty_notebook()
                else:
                    return NativeToolResult.from_error(
                        f"Notebook not found: {notebook_path}"
                    )
            else:
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        notebook = json.load(f)
                except json.JSONDecodeError as e:
                    return NativeToolResult.from_error(f"Invalid notebook JSON: {e}")

            # Validate notebook structure
            if "cells" not in notebook:
                return NativeToolResult.from_error(
                    "Invalid notebook format: missing 'cells' key"
                )

            # Perform edit
            if mode == EditMode.REPLACE:
                result = self._replace_cell(notebook, cell_id, new_source, ctype)
            elif mode == EditMode.INSERT:
                result = self._insert_cell(notebook, cell_id, new_source, ctype)
            elif mode == EditMode.DELETE:
                result = self._delete_cell(notebook, cell_id)

            if not result["success"]:
                return NativeToolResult.from_error(result["error"])

            # Write notebook back
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(notebook, f, indent=1, ensure_ascii=False)
            except Exception as e:
                return NativeToolResult.from_error(f"Failed to write notebook: {e}")

            logger.info(f"Notebook {mode.value}: {notebook_path}")

            return NativeToolResult.from_success(
                output=result["message"],
                notebook_path=str(path),
                edit_mode=mode.value,
                cell_id=result.get("cell_id", cell_id),
                cell_count=len(notebook["cells"]),
            )

        except Exception as e:
            logger.error(f"NotebookEdit failed: {e}")
            return NativeToolResult.from_exception(e)

    def _create_empty_notebook(self) -> Dict[str, Any]:
        """Create an empty Jupyter notebook structure."""
        return {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {
                "kernelspec": {
                    "display_name": "Python 3",
                    "language": "python",
                    "name": "python3",
                },
            },
            "cells": [],
        }

    def _find_cell_index(
        self,
        cells: List[Dict[str, Any]],
        cell_id: str,
    ) -> Optional[int]:
        """Find cell index by ID.

        Args:
            cells: List of notebook cells
            cell_id: Cell ID to find

        Returns:
            Index of cell if found, None otherwise
        """
        for i, cell in enumerate(cells):
            if cell.get("id") == cell_id:
                return i
        return None

    def _create_cell(
        self,
        source: str,
        cell_type: CellType,
    ) -> Dict[str, Any]:
        """Create a new notebook cell.

        Args:
            source: Cell content
            cell_type: "code" or "markdown"

        Returns:
            Cell dictionary
        """
        cell = {
            "id": str(uuid.uuid4())[:8],
            "cell_type": cell_type.value,
            "source": source,
            "metadata": {},
        }

        if cell_type == CellType.CODE:
            cell["outputs"] = []
            cell["execution_count"] = None

        return cell

    def _replace_cell(
        self,
        notebook: Dict[str, Any],
        cell_id: str,
        new_source: str,
        cell_type: CellType,
    ) -> Dict[str, Any]:
        """Replace content of existing cell.

        Args:
            notebook: Notebook dictionary
            cell_id: ID of cell to replace
            new_source: New cell content
            cell_type: New cell type

        Returns:
            Result dictionary with success/error
        """
        cells = notebook["cells"]
        index = self._find_cell_index(cells, cell_id)

        if index is None:
            return {
                "success": False,
                "error": f"Cell not found: {cell_id}",
            }

        # Update cell
        cells[index]["source"] = new_source
        cells[index]["cell_type"] = cell_type.value

        # Reset outputs if code cell
        if cell_type == CellType.CODE:
            cells[index]["outputs"] = []
            cells[index]["execution_count"] = None

        return {
            "success": True,
            "message": f"Replaced cell {cell_id}",
            "cell_id": cell_id,
        }

    def _insert_cell(
        self,
        notebook: Dict[str, Any],
        after_cell_id: Optional[str],
        new_source: str,
        cell_type: CellType,
    ) -> Dict[str, Any]:
        """Insert new cell after specified cell.

        Args:
            notebook: Notebook dictionary
            after_cell_id: ID of cell to insert after (None for beginning)
            new_source: Cell content
            cell_type: Cell type

        Returns:
            Result dictionary with success/error
        """
        cells = notebook["cells"]
        new_cell = self._create_cell(new_source, cell_type)

        if after_cell_id is None or len(cells) == 0:
            # Insert at beginning
            cells.insert(0, new_cell)
            position = "at beginning"
        else:
            index = self._find_cell_index(cells, after_cell_id)
            if index is None:
                return {
                    "success": False,
                    "error": f"Cell not found: {after_cell_id}",
                }
            # Insert after the found cell
            cells.insert(index + 1, new_cell)
            position = f"after {after_cell_id}"

        return {
            "success": True,
            "message": f"Inserted new {cell_type.value} cell {position}",
            "cell_id": new_cell["id"],
        }

    def _delete_cell(
        self,
        notebook: Dict[str, Any],
        cell_id: str,
    ) -> Dict[str, Any]:
        """Delete cell by ID.

        Args:
            notebook: Notebook dictionary
            cell_id: ID of cell to delete

        Returns:
            Result dictionary with success/error
        """
        cells = notebook["cells"]
        index = self._find_cell_index(cells, cell_id)

        if index is None:
            return {
                "success": False,
                "error": f"Cell not found: {cell_id}",
            }

        deleted_cell = cells.pop(index)

        return {
            "success": True,
            "message": f"Deleted {deleted_cell['cell_type']} cell {cell_id}",
            "cell_id": cell_id,
        }

    def get_schema(self) -> Dict[str, Any]:
        """Get JSON Schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "notebook_path": {
                    "type": "string",
                    "description": "Absolute path to the Jupyter notebook file",
                },
                "new_source": {
                    "type": "string",
                    "description": "New source content for the cell",
                },
                "cell_id": {
                    "type": "string",
                    "description": (
                        "ID of cell to edit. For insert mode, new cell is inserted "
                        "after this cell. Omit to insert at beginning."
                    ),
                },
                "cell_type": {
                    "type": "string",
                    "enum": ["code", "markdown"],
                    "description": "Type of cell (code or markdown). Default: code",
                },
                "edit_mode": {
                    "type": "string",
                    "enum": ["replace", "insert", "delete"],
                    "description": "Edit mode: replace, insert, or delete. Default: replace",
                },
            },
            "required": ["notebook_path", "new_source"],
            "additionalProperties": False,
        }
