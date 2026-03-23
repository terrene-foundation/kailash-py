"""Tests for kz.tools — file tools, search, and shell execution.

All file-based tests use pytest's ``tmp_path`` fixture for real filesystem operations.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from kaizen_agents.delegate.tools.base import Tool, ToolRegistry, ToolResult
from kaizen_agents.delegate.tools.bash_tool import BashTool
from kaizen_agents.delegate.tools.file_edit import FileEditTool
from kaizen_agents.delegate.tools.file_read import FileReadTool
from kaizen_agents.delegate.tools.file_write import FileWriteTool
from kaizen_agents.delegate.tools.glob_tool import GlobTool
from kaizen_agents.delegate.tools.grep_tool import GrepTool
from kaizen_agents.delegate.tools import create_default_tools


# =====================================================================
# ToolResult
# =====================================================================


class TestToolResult:
    def test_success(self) -> None:
        r = ToolResult.success("hello")
        assert r.output == "hello"
        assert r.error == ""
        assert r.is_error is False

    def test_failure(self) -> None:
        r = ToolResult.failure("bad")
        assert r.output == ""
        assert r.error == "bad"
        assert r.is_error is True


# =====================================================================
# ToolRegistry
# =====================================================================


class _DummyTool(Tool):
    def __init__(self, tool_name: str) -> None:
        self._name = tool_name

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "dummy"

    @property
    def parameters_schema(self) -> dict:
        return {}

    def execute(self, **kwargs) -> ToolResult:
        return ToolResult.success("ok")


class TestToolRegistry:
    def test_register_and_get(self) -> None:
        reg = ToolRegistry()
        tool = _DummyTool("alpha")
        reg.register(tool)
        assert reg.get("alpha") is tool

    def test_get_returns_none_for_unknown(self) -> None:
        reg = ToolRegistry()
        assert reg.get("nope") is None

    def test_get_or_raise(self) -> None:
        reg = ToolRegistry()
        reg.register(_DummyTool("x"))
        assert reg.get_or_raise("x").name == "x"
        with pytest.raises(KeyError, match="unknown"):
            reg.get_or_raise("unknown")

    def test_duplicate_registration_raises(self) -> None:
        reg = ToolRegistry()
        reg.register(_DummyTool("dup"))
        with pytest.raises(ValueError, match="dup"):
            reg.register(_DummyTool("dup"))

    def test_list_tools(self) -> None:
        reg = ToolRegistry()
        reg.register(_DummyTool("a"))
        reg.register(_DummyTool("b"))
        assert [t.name for t in reg.list_tools()] == ["a", "b"]

    def test_names(self) -> None:
        reg = ToolRegistry()
        reg.register(_DummyTool("x"))
        reg.register(_DummyTool("y"))
        assert reg.names == ["x", "y"]


# =====================================================================
# create_default_tools
# =====================================================================


class TestCreateDefaultTools:
    def test_returns_registry_without_bash_when_no_gate(self) -> None:
        reg = create_default_tools()
        expected = {"file_read", "file_write", "file_edit", "glob", "grep"}
        assert set(reg.names) == expected

    def test_returns_registry_with_bash_when_gate_provided(self) -> None:
        reg = create_default_tools(permission_gate=lambda cmd: True)
        expected = {"file_read", "file_write", "file_edit", "glob", "grep", "bash"}
        assert set(reg.names) == expected


# =====================================================================
# FileReadTool
# =====================================================================


class TestFileReadTool:
    def setup_method(self) -> None:
        self.tool = FileReadTool()

    def test_read_simple_file(self, tmp_path: Path) -> None:
        f = tmp_path / "hello.txt"
        f.write_text("line one\nline two\nline three\n", encoding="utf-8")

        result = self.tool.execute(file_path=str(f))
        assert not result.is_error
        assert "1\tline one" in result.output
        assert "2\tline two" in result.output
        assert "3\tline three" in result.output

    def test_read_with_offset(self, tmp_path: Path) -> None:
        f = tmp_path / "data.txt"
        f.write_text("a\nb\nc\nd\ne\n", encoding="utf-8")

        result = self.tool.execute(file_path=str(f), offset=3)
        assert not result.is_error
        assert "1\t" not in result.output
        assert "3\tc" in result.output
        assert "5\te" in result.output

    def test_read_with_limit(self, tmp_path: Path) -> None:
        f = tmp_path / "data.txt"
        f.write_text("a\nb\nc\nd\ne\n", encoding="utf-8")

        result = self.tool.execute(file_path=str(f), limit=2)
        assert not result.is_error
        assert "1\ta" in result.output
        assert "2\tb" in result.output
        assert "3\t" not in result.output

    def test_read_with_offset_and_limit(self, tmp_path: Path) -> None:
        f = tmp_path / "data.txt"
        f.write_text("a\nb\nc\nd\ne\n", encoding="utf-8")

        result = self.tool.execute(file_path=str(f), offset=2, limit=2)
        assert not result.is_error
        assert "2\tb" in result.output
        assert "3\tc" in result.output
        assert "4\t" not in result.output

    def test_read_missing_file(self) -> None:
        result = self.tool.execute(file_path="/nonexistent/file.txt")
        assert result.is_error
        assert "not found" in result.error.lower()

    def test_read_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.txt"
        f.write_text("", encoding="utf-8")
        result = self.tool.execute(file_path=str(f))
        assert not result.is_error
        assert "empty" in result.output.lower()


# =====================================================================
# FileWriteTool
# =====================================================================


class TestFileWriteTool:
    def setup_method(self) -> None:
        self.tool = FileWriteTool()

    def test_write_new_file(self, tmp_path: Path) -> None:
        target = tmp_path / "output.txt"
        result = self.tool.execute(file_path=str(target), content="hello world")
        assert not result.is_error
        assert target.read_text(encoding="utf-8") == "hello world"

    def test_write_creates_parent_dirs(self, tmp_path: Path) -> None:
        target = tmp_path / "a" / "b" / "c" / "deep.txt"
        result = self.tool.execute(file_path=str(target), content="deep content")
        assert not result.is_error
        assert target.read_text(encoding="utf-8") == "deep content"

    def test_write_overwrites_existing(self, tmp_path: Path) -> None:
        target = tmp_path / "exists.txt"
        target.write_text("old", encoding="utf-8")
        result = self.tool.execute(file_path=str(target), content="new")
        assert not result.is_error
        assert target.read_text(encoding="utf-8") == "new"

    def test_write_reports_byte_count(self, tmp_path: Path) -> None:
        target = tmp_path / "count.txt"
        content = "abcde"
        result = self.tool.execute(file_path=str(target), content=content)
        assert "5 bytes" in result.output


# =====================================================================
# FileEditTool
# =====================================================================


class TestFileEditTool:
    def setup_method(self) -> None:
        self.tool = FileEditTool()

    def test_simple_replacement(self, tmp_path: Path) -> None:
        f = tmp_path / "code.py"
        f.write_text('name = "old"\nprint(name)\n', encoding="utf-8")

        result = self.tool.execute(
            file_path=str(f),
            old_string='name = "old"',
            new_string='name = "new"',
        )
        assert not result.is_error
        assert f.read_text(encoding="utf-8") == 'name = "new"\nprint(name)\n'

    def test_uniqueness_check_fails_on_duplicate(self, tmp_path: Path) -> None:
        f = tmp_path / "dup.txt"
        f.write_text("foo bar\nfoo baz\n", encoding="utf-8")

        result = self.tool.execute(
            file_path=str(f),
            old_string="foo",
            new_string="qux",
        )
        assert result.is_error
        assert "2 times" in result.error

    def test_replace_all(self, tmp_path: Path) -> None:
        f = tmp_path / "multi.txt"
        f.write_text("aaa bbb aaa ccc aaa\n", encoding="utf-8")

        result = self.tool.execute(
            file_path=str(f),
            old_string="aaa",
            new_string="xxx",
            replace_all=True,
        )
        assert not result.is_error
        assert "3 occurrence" in result.output
        assert f.read_text(encoding="utf-8") == "xxx bbb xxx ccc xxx\n"

    def test_old_string_not_found(self, tmp_path: Path) -> None:
        f = tmp_path / "miss.txt"
        f.write_text("hello world\n", encoding="utf-8")

        result = self.tool.execute(
            file_path=str(f),
            old_string="goodbye",
            new_string="farewell",
        )
        assert result.is_error
        assert "not found" in result.error.lower()

    def test_same_old_and_new_rejected(self, tmp_path: Path) -> None:
        f = tmp_path / "same.txt"
        f.write_text("content\n", encoding="utf-8")

        result = self.tool.execute(
            file_path=str(f),
            old_string="content",
            new_string="content",
        )
        assert result.is_error
        assert "identical" in result.error.lower()

    def test_edit_missing_file(self) -> None:
        result = self.tool.execute(
            file_path="/nonexistent/file.txt",
            old_string="a",
            new_string="b",
        )
        assert result.is_error

    def test_edit_preserves_rest_of_file(self, tmp_path: Path) -> None:
        f = tmp_path / "preserve.txt"
        original = "line1\nTARGET_LINE\nline3\nline4\n"
        f.write_text(original, encoding="utf-8")

        self.tool.execute(
            file_path=str(f),
            old_string="TARGET_LINE",
            new_string="REPLACED_LINE",
        )
        expected = "line1\nREPLACED_LINE\nline3\nline4\n"
        assert f.read_text(encoding="utf-8") == expected


# =====================================================================
# GlobTool
# =====================================================================


class TestGlobTool:
    def setup_method(self) -> None:
        self.tool = GlobTool()

    def test_find_python_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("# a", encoding="utf-8")
        (tmp_path / "b.py").write_text("# b", encoding="utf-8")
        (tmp_path / "c.txt").write_text("c", encoding="utf-8")

        result = self.tool.execute(pattern="*.py", path=str(tmp_path))
        assert not result.is_error
        assert "a.py" in result.output
        assert "b.py" in result.output
        assert "c.txt" not in result.output

    def test_recursive_glob(self, tmp_path: Path) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "deep.py").write_text("# deep", encoding="utf-8")
        (tmp_path / "top.py").write_text("# top", encoding="utf-8")

        result = self.tool.execute(pattern="**/*.py", path=str(tmp_path))
        assert not result.is_error
        assert "deep.py" in result.output
        assert "top.py" in result.output

    def test_sorted_by_mtime(self, tmp_path: Path) -> None:
        f1 = tmp_path / "old.txt"
        f1.write_text("old", encoding="utf-8")
        # Ensure measurable time difference
        time.sleep(0.05)
        f2 = tmp_path / "new.txt"
        f2.write_text("new", encoding="utf-8")

        result = self.tool.execute(pattern="*.txt", path=str(tmp_path))
        lines = result.output.strip().split("\n")
        # Newest first
        assert "new.txt" in lines[0]
        assert "old.txt" in lines[1]

    def test_no_matches(self, tmp_path: Path) -> None:
        result = self.tool.execute(pattern="*.xyz", path=str(tmp_path))
        assert "no matches" in result.output.lower()

    def test_invalid_directory(self) -> None:
        result = self.tool.execute(pattern="*", path="/nonexistent/dir")
        assert result.is_error

    def test_excludes_directories(self, tmp_path: Path) -> None:
        (tmp_path / "dir_match").mkdir()
        (tmp_path / "file_match.txt").write_text("f", encoding="utf-8")

        result = self.tool.execute(pattern="*", path=str(tmp_path))
        assert "file_match.txt" in result.output
        # The directory itself should not appear as a match
        lines = result.output.strip().split("\n")
        for line in lines:
            assert not line.endswith("dir_match")


# =====================================================================
# GrepTool
# =====================================================================


class TestGrepTool:
    def setup_method(self) -> None:
        self.tool = GrepTool()

    def _create_fixtures(self, tmp_path: Path) -> tuple[Path, Path, Path]:
        """Create test files and return their paths."""
        f1 = tmp_path / "alpha.py"
        f1.write_text("import os\nimport sys\nprint('hello')\n", encoding="utf-8")

        f2 = tmp_path / "beta.py"
        f2.write_text("import os\ndef main():\n    pass\n", encoding="utf-8")

        f3 = tmp_path / "gamma.txt"
        f3.write_text("no imports here\njust text\n", encoding="utf-8")

        return f1, f2, f3

    def test_files_with_matches(self, tmp_path: Path) -> None:
        f1, f2, f3 = self._create_fixtures(tmp_path)
        result = self.tool.execute(pattern="import os", path=str(tmp_path))
        assert not result.is_error
        assert "alpha.py" in result.output
        assert "beta.py" in result.output
        assert "gamma.txt" not in result.output

    def test_content_mode(self, tmp_path: Path) -> None:
        f1, _, _ = self._create_fixtures(tmp_path)
        result = self.tool.execute(
            pattern="import",
            path=str(f1),
            output_mode="content",
        )
        assert not result.is_error
        assert "import os" in result.output
        assert "import sys" in result.output

    def test_count_mode(self, tmp_path: Path) -> None:
        f1, _, _ = self._create_fixtures(tmp_path)
        result = self.tool.execute(
            pattern="import",
            path=str(f1),
            output_mode="count",
        )
        assert not result.is_error
        assert ":2" in result.output

    def test_case_insensitive(self, tmp_path: Path) -> None:
        f = tmp_path / "case.txt"
        f.write_text("Hello World\nhello world\nHELLO WORLD\n", encoding="utf-8")

        result = self.tool.execute(
            pattern="hello",
            path=str(f),
            output_mode="count",
            case_insensitive=True,
        )
        assert ":3" in result.output

    def test_context_lines(self, tmp_path: Path) -> None:
        f = tmp_path / "ctx.txt"
        f.write_text("line1\nline2\nTARGET\nline4\nline5\n", encoding="utf-8")

        result = self.tool.execute(
            pattern="TARGET",
            path=str(f),
            output_mode="content",
            context=1,
        )
        assert "line2" in result.output
        assert "TARGET" in result.output
        assert "line4" in result.output

    def test_head_limit(self, tmp_path: Path) -> None:
        for i in range(10):
            (tmp_path / f"file{i}.py").write_text(f"match_{i}\n", encoding="utf-8")

        result = self.tool.execute(
            pattern="match_",
            path=str(tmp_path),
            output_mode="files_with_matches",
            head_limit=3,
        )
        lines = [l for l in result.output.strip().split("\n") if l]
        assert len(lines) == 3

    def test_glob_filter(self, tmp_path: Path) -> None:
        (tmp_path / "include.py").write_text("target\n", encoding="utf-8")
        (tmp_path / "exclude.txt").write_text("target\n", encoding="utf-8")

        result = self.tool.execute(
            pattern="target",
            path=str(tmp_path),
            glob="*.py",
        )
        assert "include.py" in result.output
        assert "exclude.txt" not in result.output

    def test_regex_pattern(self, tmp_path: Path) -> None:
        f = tmp_path / "regex.txt"
        f.write_text("foo123bar\nfoo456bar\nhello\n", encoding="utf-8")

        result = self.tool.execute(
            pattern=r"foo\d+bar",
            path=str(f),
            output_mode="count",
        )
        assert ":2" in result.output

    def test_invalid_regex(self, tmp_path: Path) -> None:
        result = self.tool.execute(pattern="[invalid", path=str(tmp_path))
        assert result.is_error
        assert "regex" in result.error.lower()

    def test_no_matches(self, tmp_path: Path) -> None:
        (tmp_path / "empty_search.txt").write_text("nothing here\n", encoding="utf-8")
        result = self.tool.execute(pattern="zzzzz", path=str(tmp_path))
        assert "no matches" in result.output.lower()

    def test_search_single_file(self, tmp_path: Path) -> None:
        f = tmp_path / "single.txt"
        f.write_text("needle in haystack\n", encoding="utf-8")
        result = self.tool.execute(pattern="needle", path=str(f))
        assert "single.txt" in result.output


# =====================================================================
# BashTool
# =====================================================================


class TestBashTool:
    def setup_method(self) -> None:
        self.tool = BashTool(permission_gate=lambda cmd: True)

    def test_requires_permission_gate(self) -> None:
        with pytest.raises(ValueError, match="requires a permission_gate"):
            BashTool(permission_gate=None)

    def test_simple_command(self) -> None:
        result = self.tool.execute(command="echo hello")
        assert not result.is_error
        assert "hello" in result.output

    def test_command_with_exit_code(self) -> None:
        result = self.tool.execute(command="exit 1")
        assert result.is_error
        assert "code 1" in result.error

    def test_captures_stderr(self) -> None:
        result = self.tool.execute(command="echo err >&2")
        assert "err" in result.output

    def test_timeout(self) -> None:
        result = self.tool.execute(command="sleep 10", timeout=1)
        assert result.is_error
        assert "timed out" in result.error.lower()

    def test_working_directory_is_cwd(self) -> None:
        result = self.tool.execute(command="pwd")
        assert not result.is_error
        assert len(result.output.strip()) > 0

    def test_permission_gate_blocks(self) -> None:
        tool = BashTool(permission_gate=lambda cmd: False)
        result = tool.execute(command="echo blocked")
        assert result.is_error
        assert "permission denied" in result.error.lower()

    def test_permission_gate_allows(self) -> None:
        tool = BashTool(permission_gate=lambda cmd: True)
        result = tool.execute(command="echo allowed")
        assert not result.is_error
        assert "allowed" in result.output

    def test_pipe_commands(self) -> None:
        result = self.tool.execute(command="echo 'a b c' | tr ' ' '\\n' | wc -l")
        assert not result.is_error
        assert "3" in result.output.strip()

    def test_no_output_command(self) -> None:
        result = self.tool.execute(command="true")
        assert not result.is_error
        assert result.output == "(no output)"
