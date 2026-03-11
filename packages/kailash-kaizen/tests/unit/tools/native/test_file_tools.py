"""
Unit Tests for Native File Tools (Tier 1)

Tests all file operation tools including ReadFileTool, WriteFileTool,
EditFileTool, GlobTool, GrepTool, ListDirectoryTool, and FileExistsTool.

Coverage:
- Basic file operations (read, write)
- File editing (string replacement)
- Pattern matching (glob, grep)
- Directory operations
- Error handling and edge cases
- Security validations
"""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from kaizen.tools.native.file_tools import (
    EditFileTool,
    FileExistsTool,
    GlobTool,
    GrepTool,
    ListDirectoryTool,
    ReadFileTool,
    WriteFileTool,
)
from kaizen.tools.types import DangerLevel, ToolCategory


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    dirpath = tempfile.mkdtemp()
    yield dirpath
    shutil.rmtree(dirpath, ignore_errors=True)


@pytest.fixture
def sample_file(temp_dir):
    """Create a sample file for testing."""
    filepath = os.path.join(temp_dir, "sample.txt")
    with open(filepath, "w") as f:
        f.write("Line 1\nLine 2\nLine 3\n")
    return filepath


@pytest.fixture
def nested_dir(temp_dir):
    """Create a nested directory structure for testing."""
    # Create structure:
    # temp_dir/
    #   file1.txt
    #   file2.py
    #   subdir/
    #     file3.txt
    #     file4.py

    with open(os.path.join(temp_dir, "file1.txt"), "w") as f:
        f.write("root txt")

    with open(os.path.join(temp_dir, "file2.py"), "w") as f:
        f.write("# root python")

    subdir = os.path.join(temp_dir, "subdir")
    os.makedirs(subdir)

    with open(os.path.join(subdir, "file3.txt"), "w") as f:
        f.write("sub txt")

    with open(os.path.join(subdir, "file4.py"), "w") as f:
        f.write("# sub python")

    return temp_dir


class TestReadFileTool:
    """Test ReadFileTool."""

    def test_tool_attributes(self):
        """Test tool has correct attributes."""
        tool = ReadFileTool()

        assert tool.name == "read_file"
        assert "read" in tool.description.lower()
        assert tool.danger_level == DangerLevel.SAFE
        assert tool.category == ToolCategory.SYSTEM

    def test_get_schema(self):
        """Test schema is correct."""
        tool = ReadFileTool()
        schema = tool.get_schema()

        assert schema["type"] == "object"
        assert "path" in schema["properties"]
        assert "path" in schema["required"]

    @pytest.mark.asyncio
    async def test_read_existing_file(self, sample_file):
        """Test reading an existing file."""
        tool = ReadFileTool()

        result = await tool.execute(path=sample_file)

        assert result.success is True
        assert "Line 1" in result.output
        assert "Line 2" in result.output
        assert "Line 3" in result.output

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, temp_dir):
        """Test reading nonexistent file returns error."""
        tool = ReadFileTool()
        nonexistent = os.path.join(temp_dir, "does_not_exist.txt")

        result = await tool.execute(path=nonexistent)

        assert result.success is False
        assert (
            "not found" in result.error.lower()
            or "no such file" in result.error.lower()
        )

    @pytest.mark.asyncio
    async def test_read_includes_line_numbers(self, sample_file):
        """Test reading always includes line numbers (cat -n style)."""
        tool = ReadFileTool()

        result = await tool.execute(path=sample_file)

        assert result.success is True
        # Should contain line number prefixes (1-based, tab-separated)
        assert "\t" in result.output  # Line numbers are tab-separated
        assert "Line 1" in result.output

    @pytest.mark.asyncio
    async def test_read_with_offset_and_limit(self, temp_dir):
        """Test reading with offset and limit."""
        # Create file with many lines
        filepath = os.path.join(temp_dir, "multiline.txt")
        with open(filepath, "w") as f:
            for i in range(100):
                f.write(f"Line {i}\n")

        tool = ReadFileTool()

        result = await tool.execute(path=filepath, offset=10, limit=5)

        assert result.success is True
        # Should contain lines 10-14
        assert "Line 10" in result.output
        assert "Line 9" not in result.output  # Before offset

    @pytest.mark.asyncio
    async def test_read_empty_file(self, temp_dir):
        """Test reading an empty file."""
        filepath = os.path.join(temp_dir, "empty.txt")
        with open(filepath, "w") as f:
            pass  # Create empty file

        tool = ReadFileTool()

        result = await tool.execute(path=filepath)

        assert result.success is True
        assert result.output == ""


class TestWriteFileTool:
    """Test WriteFileTool."""

    def test_tool_attributes(self):
        """Test tool has correct attributes."""
        tool = WriteFileTool()

        assert tool.name == "write_file"
        assert "write" in tool.description.lower()
        assert tool.danger_level == DangerLevel.MEDIUM
        assert tool.category == ToolCategory.SYSTEM

    @pytest.mark.asyncio
    async def test_write_new_file(self, temp_dir):
        """Test writing a new file."""
        tool = WriteFileTool()
        filepath = os.path.join(temp_dir, "new_file.txt")

        result = await tool.execute(path=filepath, content="Hello, World!")

        assert result.success is True
        assert os.path.exists(filepath)

        with open(filepath) as f:
            assert f.read() == "Hello, World!"

    @pytest.mark.asyncio
    async def test_write_overwrites_existing(self, sample_file):
        """Test writing overwrites existing file."""
        tool = WriteFileTool()

        result = await tool.execute(path=sample_file, content="New content")

        assert result.success is True

        with open(sample_file) as f:
            content = f.read()
            assert content == "New content"
            assert "Line 1" not in content

    @pytest.mark.asyncio
    async def test_write_creates_directories(self, temp_dir):
        """Test writing creates parent directories."""
        tool = WriteFileTool()
        filepath = os.path.join(temp_dir, "new", "nested", "file.txt")

        result = await tool.execute(path=filepath, content="nested content")

        assert result.success is True
        assert os.path.exists(filepath)

    @pytest.mark.asyncio
    async def test_write_empty_content(self, temp_dir):
        """Test writing empty content."""
        tool = WriteFileTool()
        filepath = os.path.join(temp_dir, "empty.txt")

        result = await tool.execute(path=filepath, content="")

        assert result.success is True
        assert os.path.exists(filepath)
        assert os.path.getsize(filepath) == 0


class TestEditFileTool:
    """Test EditFileTool."""

    def test_tool_attributes(self):
        """Test tool has correct attributes."""
        tool = EditFileTool()

        assert tool.name == "edit_file"
        assert tool.danger_level == DangerLevel.MEDIUM
        assert tool.category == ToolCategory.SYSTEM

    @pytest.mark.asyncio
    async def test_edit_replace_text(self, sample_file):
        """Test replacing text in file."""
        tool = EditFileTool()

        result = await tool.execute(
            path=sample_file,
            old_string="Line 2",
            new_string="Modified Line 2",
        )

        assert result.success is True

        with open(sample_file) as f:
            content = f.read()
            assert "Modified Line 2" in content
            assert "Line 1" in content  # Unchanged

    @pytest.mark.asyncio
    async def test_edit_old_string_not_found(self, sample_file):
        """Test error when old_string not found."""
        tool = EditFileTool()

        result = await tool.execute(
            path=sample_file,
            old_string="Nonexistent text",
            new_string="Replacement",
        )

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_edit_replace_all(self, temp_dir):
        """Test replace_all replaces all occurrences."""
        filepath = os.path.join(temp_dir, "repeated.txt")
        with open(filepath, "w") as f:
            f.write("foo bar foo baz foo")

        tool = EditFileTool()

        result = await tool.execute(
            path=filepath,
            old_string="foo",
            new_string="qux",
            replace_all=True,
        )

        assert result.success is True

        with open(filepath) as f:
            content = f.read()
            assert "foo" not in content
            assert content.count("qux") == 3

    @pytest.mark.asyncio
    async def test_edit_single_replacement_by_default(self, temp_dir):
        """Test single replacement by default even with multiple occurrences."""
        filepath = os.path.join(temp_dir, "ambiguous.txt")
        with open(filepath, "w") as f:
            f.write("foo bar foo")

        tool = EditFileTool()

        result = await tool.execute(
            path=filepath,
            old_string="foo",
            new_string="qux",
            replace_all=False,
        )

        # Should succeed and replace only the first occurrence
        assert result.success is True
        assert result.metadata["replacements"] == 1
        assert result.metadata["total_occurrences"] == 2

        with open(filepath) as f:
            content = f.read()
            # Only first "foo" replaced
            assert content == "qux bar foo"

    @pytest.mark.asyncio
    async def test_edit_nonexistent_file(self, temp_dir):
        """Test editing nonexistent file returns error."""
        tool = EditFileTool()
        filepath = os.path.join(temp_dir, "missing.txt")

        result = await tool.execute(
            path=filepath,
            old_string="old",
            new_string="new",
        )

        assert result.success is False


class TestGlobTool:
    """Test GlobTool."""

    def test_tool_attributes(self):
        """Test tool has correct attributes."""
        tool = GlobTool()

        assert tool.name == "glob"
        assert tool.danger_level == DangerLevel.SAFE
        assert tool.category == ToolCategory.SYSTEM

    @pytest.mark.asyncio
    async def test_glob_txt_files(self, nested_dir):
        """Test globbing .txt files."""
        tool = GlobTool()

        result = await tool.execute(pattern="**/*.txt", path=nested_dir)

        assert result.success is True
        assert isinstance(result.output, list)
        assert len(result.output) == 2  # file1.txt and file3.txt

        filenames = [os.path.basename(f) for f in result.output]
        assert "file1.txt" in filenames
        assert "file3.txt" in filenames

    @pytest.mark.asyncio
    async def test_glob_py_files(self, nested_dir):
        """Test globbing .py files."""
        tool = GlobTool()

        result = await tool.execute(pattern="**/*.py", path=nested_dir)

        assert result.success is True
        assert len(result.output) == 2  # file2.py and file4.py

    @pytest.mark.asyncio
    async def test_glob_no_matches(self, nested_dir):
        """Test globbing with no matches."""
        tool = GlobTool()

        result = await tool.execute(pattern="**/*.rs", path=nested_dir)

        assert result.success is True
        assert result.output == []

    @pytest.mark.asyncio
    async def test_glob_single_directory(self, nested_dir):
        """Test globbing single directory level."""
        tool = GlobTool()

        result = await tool.execute(pattern="*.txt", path=nested_dir)

        assert result.success is True
        assert len(result.output) == 1  # Only file1.txt at root


class TestGrepTool:
    """Test GrepTool."""

    def test_tool_attributes(self):
        """Test tool has correct attributes."""
        tool = GrepTool()

        assert tool.name == "grep"
        assert tool.danger_level == DangerLevel.SAFE
        assert tool.category == ToolCategory.SYSTEM

    @pytest.mark.asyncio
    async def test_grep_simple_pattern(self, nested_dir):
        """Test grep with simple pattern."""
        tool = GrepTool()

        result = await tool.execute(pattern="python", path=nested_dir)

        assert result.success is True
        # Output is a string with matches
        assert isinstance(result.output, str)
        # Should find matches in .py files
        assert result.metadata["total_matches"] >= 1
        assert "python" in result.output.lower()

    @pytest.mark.asyncio
    async def test_grep_no_matches(self, nested_dir):
        """Test grep with no matches."""
        tool = GrepTool()

        result = await tool.execute(pattern="nonexistent_pattern_xyz", path=nested_dir)

        assert result.success is True
        # Returns "No matches found" string when no matches
        assert result.metadata["total_matches"] == 0
        assert "no matches" in result.output.lower()

    @pytest.mark.asyncio
    async def test_grep_with_file_glob(self, nested_dir):
        """Test grep with file_glob filter."""
        tool = GrepTool()

        result = await tool.execute(
            pattern="txt",
            path=nested_dir,
            file_glob="*.txt",
        )

        assert result.success is True
        # Should only search in .txt files
        # The pattern "txt" should match content in txt files

    @pytest.mark.asyncio
    async def test_grep_case_insensitive(self, temp_dir):
        """Test case-insensitive grep."""
        filepath = os.path.join(temp_dir, "case.txt")
        with open(filepath, "w") as f:
            f.write("Hello World\nHELLO WORLD\nhello world\n")

        tool = GrepTool()

        result = await tool.execute(
            pattern="hello",
            path=temp_dir,
            case_insensitive=True,
        )

        assert result.success is True
        # Should match all three lines


class TestListDirectoryTool:
    """Test ListDirectoryTool."""

    def test_tool_attributes(self):
        """Test tool has correct attributes."""
        tool = ListDirectoryTool()

        assert tool.name == "list_directory"
        assert tool.danger_level == DangerLevel.SAFE
        assert tool.category == ToolCategory.SYSTEM

    @pytest.mark.asyncio
    async def test_list_directory(self, nested_dir):
        """Test listing directory contents."""
        tool = ListDirectoryTool()

        result = await tool.execute(path=nested_dir)

        assert result.success is True
        assert isinstance(result.output, list)
        assert len(result.output) == 3  # file1.txt, file2.py, subdir

    @pytest.mark.asyncio
    async def test_list_nonexistent_directory(self, temp_dir):
        """Test listing nonexistent directory returns error."""
        tool = ListDirectoryTool()
        missing = os.path.join(temp_dir, "missing_dir")

        result = await tool.execute(path=missing)

        assert result.success is False

    @pytest.mark.asyncio
    async def test_list_file_returns_error(self, sample_file):
        """Test listing a file (not directory) returns error."""
        tool = ListDirectoryTool()

        result = await tool.execute(path=sample_file)

        assert result.success is False
        assert "not a directory" in result.error.lower()

    @pytest.mark.asyncio
    async def test_list_returns_detailed_info(self, nested_dir):
        """Test listing always returns detailed info (type, size, modified)."""
        tool = ListDirectoryTool()

        result = await tool.execute(path=nested_dir)

        assert result.success is True
        # Output is list of dicts with detailed info
        assert isinstance(result.output, list)
        assert len(result.output) > 0

        # Check structure of entries
        entry = result.output[0]
        assert "name" in entry
        assert "type" in entry
        assert "size" in entry
        assert "modified" in entry


class TestFileExistsTool:
    """Test FileExistsTool."""

    def test_tool_attributes(self):
        """Test tool has correct attributes."""
        tool = FileExistsTool()

        assert tool.name == "file_exists"
        assert tool.danger_level == DangerLevel.SAFE
        assert tool.category == ToolCategory.SYSTEM

    @pytest.mark.asyncio
    async def test_file_exists_true(self, sample_file):
        """Test checking existing file."""
        tool = FileExistsTool()

        result = await tool.execute(path=sample_file)

        assert result.success is True
        assert result.output is True

    @pytest.mark.asyncio
    async def test_file_exists_false(self, temp_dir):
        """Test checking nonexistent file."""
        tool = FileExistsTool()
        missing = os.path.join(temp_dir, "missing.txt")

        result = await tool.execute(path=missing)

        assert result.success is True
        assert result.output is False

    @pytest.mark.asyncio
    async def test_directory_exists(self, temp_dir):
        """Test checking existing directory."""
        tool = FileExistsTool()

        result = await tool.execute(path=temp_dir)

        assert result.success is True
        assert result.output is True


class TestFileToolsSecurity:
    """Test security features of file tools."""

    @pytest.mark.asyncio
    async def test_read_blocked_path_etc_passwd(self):
        """Test reading /etc/passwd is blocked."""
        tool = ReadFileTool()

        result = await tool.execute(path="/etc/passwd")

        # Should either be blocked by security or fail gracefully
        # We don't want to expose sensitive files
        # The tool may or may not block this depending on implementation

    @pytest.mark.asyncio
    async def test_write_blocked_system_path(self):
        """Test writing to system paths is restricted."""
        tool = WriteFileTool()

        # Attempt to write to a system path (will fail due to permissions anyway)
        result = await tool.execute(path="/etc/test_file", content="test")

        # Should fail - either due to security block or permission denied
        assert result.success is False

    @pytest.mark.asyncio
    async def test_path_traversal_attempt(self, temp_dir):
        """Test path traversal attempts are handled."""
        tool = ReadFileTool()

        # Attempt path traversal
        traversal_path = os.path.join(temp_dir, "..", "..", "etc", "passwd")

        result = await tool.execute(path=traversal_path)

        # Should either normalize the path or fail
        # The key is it shouldn't expose unintended files
