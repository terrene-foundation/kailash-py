"""
Unit Tests for Native Bash Tool (Tier 1)

Tests the BashTool for sandboxed command execution.

Coverage:
- Basic command execution
- Security pattern blocking
- Timeout handling
- Output handling and truncation
- Working directory support
- Error handling
"""

import os
import shutil
import tempfile

import pytest

from kaizen.tools.native.bash_tools import BashTool
from kaizen.tools.types import DangerLevel, ToolCategory


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    dirpath = tempfile.mkdtemp()
    yield dirpath
    shutil.rmtree(dirpath, ignore_errors=True)


class TestBashToolAttributes:
    """Test BashTool attributes and configuration."""

    def test_tool_attributes(self):
        """Test tool has correct attributes."""
        tool = BashTool()

        assert tool.name == "bash_command"
        assert (
            "bash" in tool.description.lower() or "command" in tool.description.lower()
        )
        assert tool.danger_level == DangerLevel.HIGH
        assert tool.category == ToolCategory.SYSTEM

    def test_get_schema(self):
        """Test schema is correct."""
        tool = BashTool()
        schema = tool.get_schema()

        assert schema["type"] == "object"
        assert "command" in schema["properties"]
        assert "timeout" in schema["properties"]
        assert "cwd" in schema["properties"]
        assert "command" in schema["required"]

    def test_default_sandbox_mode(self):
        """Test sandbox mode is enabled by default."""
        tool = BashTool()
        assert tool.sandbox_mode is True

    def test_can_disable_sandbox(self):
        """Test sandbox mode can be disabled."""
        tool = BashTool(sandbox_mode=False)
        assert tool.sandbox_mode is False


class TestBashToolExecution:
    """Test basic command execution."""

    @pytest.mark.asyncio
    async def test_simple_command(self):
        """Test executing a simple command."""
        tool = BashTool()

        result = await tool.execute(command="echo 'hello world'")

        assert result.success is True
        assert "hello world" in result.output

    @pytest.mark.asyncio
    async def test_command_with_exit_code(self):
        """Test command exit code is captured."""
        tool = BashTool()

        # Successful command
        result1 = await tool.execute(command="true")
        assert result1.success is True
        assert result1.metadata["exit_code"] == 0

        # Failing command
        result2 = await tool.execute(command="false")
        assert result2.success is False
        assert result2.metadata["exit_code"] != 0

    @pytest.mark.asyncio
    async def test_command_with_working_directory(self, temp_dir):
        """Test command execution in specific directory."""
        tool = BashTool()

        result = await tool.execute(command="pwd", cwd=temp_dir)

        assert result.success is True
        assert temp_dir in result.output

    @pytest.mark.asyncio
    async def test_command_with_stderr(self):
        """Test stderr is captured."""
        tool = BashTool()

        result = await tool.execute(command="echo 'error' >&2")

        # Stderr should be captured
        assert "error" in result.output or result.metadata.get("stderr_length", 0) > 0

    @pytest.mark.asyncio
    async def test_piped_command(self):
        """Test piped commands work."""
        tool = BashTool()

        result = await tool.execute(command="echo 'hello world' | wc -w")

        assert result.success is True
        assert "2" in result.output  # 2 words


class TestBashToolTimeout:
    """Test timeout handling."""

    @pytest.mark.asyncio
    async def test_command_with_timeout(self):
        """Test command completes within timeout."""
        tool = BashTool()

        result = await tool.execute(command="sleep 0.1", timeout=10)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_command_timeout_exceeded(self):
        """Test command that exceeds timeout."""
        tool = BashTool()

        result = await tool.execute(command="sleep 10", timeout=1)

        assert result.success is False
        assert "timed out" in result.error.lower() or "timeout" in result.error.lower()
        assert result.metadata.get("timeout") is True

    @pytest.mark.asyncio
    async def test_timeout_capped_at_maximum(self):
        """Test timeout is capped at 600 seconds."""
        tool = BashTool()

        # Even with huge timeout, should be capped
        result = await tool.execute(command="echo 'test'", timeout=99999)

        assert result.success is True
        # Command should still execute

    @pytest.mark.asyncio
    async def test_invalid_timeout(self):
        """Test invalid timeout values."""
        tool = BashTool()

        result = await tool.execute(command="echo 'test'", timeout=-1)

        assert result.success is False
        assert "timeout" in result.error.lower()


class TestBashToolSecurity:
    """Test security features and blocked patterns."""

    @pytest.mark.asyncio
    async def test_block_rm_rf_root(self):
        """Test rm -rf / is blocked."""
        tool = BashTool()

        result = await tool.execute(command="rm -rf /")

        assert result.success is False
        assert "blocked" in result.error.lower() or "security" in result.error.lower()

    @pytest.mark.asyncio
    async def test_block_rm_rf_home(self):
        """Test rm -rf ~ is blocked."""
        tool = BashTool()

        result = await tool.execute(command="rm -rf ~")

        assert result.success is False

    @pytest.mark.asyncio
    async def test_block_fork_bomb(self):
        """Test fork bomb pattern is blocked."""
        tool = BashTool()

        result = await tool.execute(command=":(){ :|:& };:")

        assert result.success is False

    @pytest.mark.asyncio
    async def test_block_shutdown(self):
        """Test shutdown command is blocked."""
        tool = BashTool()

        result = await tool.execute(command="shutdown -h now")

        assert result.success is False

    @pytest.mark.asyncio
    async def test_block_reboot(self):
        """Test reboot command is blocked."""
        tool = BashTool()

        result = await tool.execute(command="reboot")

        assert result.success is False

    @pytest.mark.asyncio
    async def test_block_mkfs(self):
        """Test mkfs command is blocked."""
        tool = BashTool()

        result = await tool.execute(command="mkfs.ext4 /dev/sda1")

        assert result.success is False

    @pytest.mark.asyncio
    async def test_block_dd_to_device(self):
        """Test dd to device is blocked."""
        tool = BashTool()

        result = await tool.execute(command="dd if=/dev/zero of=/dev/sda")

        assert result.success is False

    @pytest.mark.asyncio
    async def test_block_etc_passwd_overwrite(self):
        """Test overwriting /etc/passwd is blocked."""
        tool = BashTool()

        result = await tool.execute(
            command="echo 'hacker:x:0:0::/root:/bin/bash' > /etc/passwd"
        )

        assert result.success is False

    @pytest.mark.asyncio
    async def test_sandbox_disabled_allows_patterns(self):
        """Test sandbox disabled allows normally-blocked patterns."""
        tool = BashTool(sandbox_mode=False)

        # This won't actually run dangerous commands,
        # but should pass the security check
        result = tool._check_command_safety("shutdown -h now")

        assert result is None  # No error when sandbox disabled

    @pytest.mark.asyncio
    async def test_allowed_commands_whitelist(self):
        """Test allowed commands whitelist."""
        tool = BashTool(allowed_commands=["echo", "ls"])

        # Allowed command
        result1 = await tool.execute(command="echo 'test'")
        assert result1.success is True

        # Disallowed command
        result2 = await tool.execute(command="cat /etc/hosts")
        assert result2.success is False
        assert "not in allowed" in result2.error.lower()

    @pytest.mark.asyncio
    async def test_blocked_commands_blacklist(self):
        """Test additional blocked commands."""
        tool = BashTool(blocked_commands=["curl", "wget"])

        result = await tool.execute(command="curl https://example.com")

        assert result.success is False
        assert "blocked" in result.error.lower()


class TestBashToolOutput:
    """Test output handling."""

    @pytest.mark.asyncio
    async def test_output_truncation(self):
        """Test output is truncated when too long."""
        tool = BashTool()

        # Generate long output
        result = await tool.execute(command="seq 1 100000")

        # Output should be truncated
        if len(result.output) >= 30000:
            assert "[truncated]" in result.output or result.metadata.get("truncated")

    @pytest.mark.asyncio
    async def test_output_contains_stdout_length(self):
        """Test metadata contains stdout length."""
        tool = BashTool()

        result = await tool.execute(command="echo 'hello'")

        assert "stdout_length" in result.metadata
        assert result.metadata["stdout_length"] > 0

    @pytest.mark.asyncio
    async def test_output_contains_stderr_length(self):
        """Test metadata contains stderr length."""
        tool = BashTool()

        result = await tool.execute(command="echo 'error' >&2")

        assert "stderr_length" in result.metadata


class TestBashToolErrorHandling:
    """Test error handling."""

    @pytest.mark.asyncio
    async def test_invalid_command(self):
        """Test handling of invalid command."""
        tool = BashTool()

        result = await tool.execute(command="this_command_does_not_exist_xyz")

        assert result.success is False
        assert result.metadata["exit_code"] != 0

    @pytest.mark.asyncio
    async def test_command_with_syntax_error(self):
        """Test handling of command with syntax error."""
        tool = BashTool()

        result = await tool.execute(command="if then else fi")

        assert result.success is False

    @pytest.mark.asyncio
    async def test_nonexistent_working_directory(self, temp_dir):
        """Test error for nonexistent working directory."""
        tool = BashTool()
        nonexistent = os.path.join(temp_dir, "missing_dir")

        result = await tool.execute(command="pwd", cwd=nonexistent)

        assert result.success is False


class TestBashToolIntegration:
    """Integration tests with real filesystem."""

    @pytest.mark.asyncio
    async def test_create_and_read_file(self, temp_dir):
        """Test creating and reading a file."""
        tool = BashTool()

        # Create file
        filepath = os.path.join(temp_dir, "test.txt")
        result1 = await tool.execute(command=f"echo 'Hello from bash' > {filepath}")
        assert result1.success is True

        # Read file
        result2 = await tool.execute(command=f"cat {filepath}")
        assert result2.success is True
        assert "Hello from bash" in result2.output

    @pytest.mark.asyncio
    async def test_list_directory(self, temp_dir):
        """Test listing directory contents."""
        tool = BashTool()

        # Create some files
        for i in range(3):
            filepath = os.path.join(temp_dir, f"file{i}.txt")
            with open(filepath, "w") as f:
                f.write(f"content {i}")

        result = await tool.execute(command=f"ls {temp_dir}")

        assert result.success is True
        assert "file0.txt" in result.output
        assert "file1.txt" in result.output
        assert "file2.txt" in result.output

    @pytest.mark.asyncio
    async def test_grep_in_files(self, temp_dir):
        """Test grep command in files."""
        tool = BashTool()

        # Create files with content
        filepath = os.path.join(temp_dir, "searchable.txt")
        with open(filepath, "w") as f:
            f.write("line 1 hello\nline 2 world\nline 3 hello world\n")

        result = await tool.execute(command=f"grep 'hello' {filepath}")

        assert result.success is True
        assert "line 1 hello" in result.output
        assert "line 3 hello world" in result.output
        assert "line 2 world" not in result.output
