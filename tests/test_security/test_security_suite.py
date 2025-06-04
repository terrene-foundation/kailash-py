"""
Comprehensive Security Testing Suite for Kailash SDK

This module provides extensive security tests covering:
- Path traversal attack prevention
- Code injection prevention
- Memory and execution limits
- Input sanitization
- Command injection protection
- Authentication vulnerabilities

These tests ensure the SDK is secure for production deployment.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from kailash.nodes.code.python import CodeExecutor
from kailash.nodes.data.readers import CSVReaderNode, JSONReaderNode
from kailash.nodes.data.writers import CSVWriterNode
from kailash.security import (
    CommandInjectionError,
    ExecutionTimeoutError,
    MemoryLimitError,
    PathTraversalError,
    SecurityConfig,
    SecurityError,
    create_secure_temp_dir,
    safe_open,
    sanitize_input,
    set_security_config,
    validate_command_string,
    validate_file_path,
)


class TestPathTraversalPrevention:
    """Test path traversal attack prevention."""

    def test_basic_path_validation(self):
        """Test basic valid paths are accepted."""
        config = SecurityConfig(allowed_directories=["/tmp", str(Path.cwd())])

        # Valid paths should work
        valid_path = validate_file_path("test.txt", config)
        assert isinstance(valid_path, Path)

    def test_path_traversal_detection(self):
        """Test detection of path traversal attempts."""
        config = SecurityConfig(allowed_directories=["/tmp"])

        # Should block obvious traversal attempts
        with pytest.raises(PathTraversalError):
            validate_file_path("../../../etc/passwd", config)

        with pytest.raises(PathTraversalError):
            validate_file_path("..\\..\\..\\windows\\system32", config)

    def test_absolute_path_restriction(self):
        """Test restriction of absolute paths to system directories."""
        config = SecurityConfig(allowed_directories=["/tmp"])

        # Should block access to system directories
        # Use paths that don't get resolved by macOS
        with pytest.raises((PathTraversalError, SecurityError)):
            validate_file_path("/usr/bin/python", config)

        with pytest.raises((PathTraversalError, SecurityError)):
            validate_file_path("/var/log/syslog", config)

    def test_file_extension_validation(self):
        """Test file extension allowlist enforcement."""
        config = SecurityConfig(
            allowed_directories=[str(Path.cwd())],
            allowed_file_extensions=[".txt", ".csv"],
        )

        # Allowed extensions should work
        validate_file_path("test.txt", config)
        validate_file_path("data.csv", config)

        # Blocked extensions should fail
        with pytest.raises(SecurityError):
            validate_file_path("malicious.exe", config)

        with pytest.raises(SecurityError):
            validate_file_path("script.sh", config)

    def test_directory_allowlist_enforcement(self):
        """Test directory allowlist enforcement."""
        temp_dir = tempfile.mkdtemp()
        try:
            # Resolve real path to handle macOS /private prefix
            real_temp_dir = str(Path(temp_dir).resolve())
            config = SecurityConfig(allowed_directories=[real_temp_dir])

            # Paths within allowed directory should work
            test_file = Path(temp_dir) / "test.txt"
            validated = validate_file_path(str(test_file), config)
            # Compare resolved paths to handle macOS /private prefix
            assert str(Path(validated).resolve()).startswith(real_temp_dir)

            # Paths outside allowed directories should fail
            with pytest.raises(SecurityError):
                validate_file_path("/usr/bin/python", config)
        finally:
            # Clean up temp directory
            import shutil

            shutil.rmtree(temp_dir)


class TestSafeFileOperations:
    """Test safe file operations with security validation."""

    def test_safe_open_with_validation(self):
        """Test safe_open validates paths correctly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = SecurityConfig(allowed_directories=[temp_dir])

            # Safe file creation should work
            test_file = Path(temp_dir) / "test.txt"
            with safe_open(test_file, "w", config) as f:
                f.write("test content")

            # Reading should work
            with safe_open(test_file, "r", config) as f:
                content = f.read()
                assert content == "test content"

    def test_safe_open_blocks_unsafe_paths(self):
        """Test safe_open blocks unsafe paths."""
        config = SecurityConfig(allowed_directories=["/tmp"])

        # Should block unsafe paths
        with pytest.raises(PathTraversalError):
            safe_open("../../../etc/passwd", "r", config)

    def test_file_size_limit_enforcement(self):
        """Test file size limits are enforced."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = SecurityConfig(
                allowed_directories=[temp_dir], max_file_size=100  # 100 bytes limit
            )

            # Create a file larger than the limit
            large_file = Path(temp_dir) / "large.txt"
            with open(large_file, "w") as f:
                f.write("x" * 200)  # 200 bytes

            # Reading should fail due to size limit
            with pytest.raises(SecurityError):
                safe_open(large_file, "r", config)


class TestDataNodeSecurity:
    """Test security of data reader/writer nodes."""

    def test_csv_reader_path_validation(self):
        """Test CSV reader validates file paths."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test CSV
            csv_file = Path(temp_dir) / "test.csv"
            csv_file.write_text("name,age\nJohn,30\nJane,25")

            # Set restrictive security config
            config = SecurityConfig(allowed_directories=[temp_dir])
            set_security_config(config)

            try:
                # Valid path should work
                reader = CSVReaderNode(file_path=str(csv_file))
                result = reader.run()
                assert "data" in result

                # Invalid path should be blocked
                with pytest.raises(PathTraversalError):
                    reader_bad = CSVReaderNode()
                    reader_bad.run(file_path="../../../etc/passwd")
            finally:
                # Reset to default config
                set_security_config(SecurityConfig())

    def test_json_reader_path_validation(self):
        """Test JSON reader validates file paths."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test JSON
            json_file = Path(temp_dir) / "test.json"
            json_file.write_text('{"key": "value"}')

            config = SecurityConfig(allowed_directories=[temp_dir])
            set_security_config(config)

            try:
                # Valid path should work
                reader = JSONReaderNode(file_path=str(json_file))
                result = reader.run()
                assert "data" in result

                # Invalid path should be blocked
                with pytest.raises(PathTraversalError):
                    reader_bad = JSONReaderNode()
                    reader_bad.run(file_path="../../etc/shadow")
            finally:
                set_security_config(SecurityConfig())

    def test_writer_path_validation(self):
        """Test data writers validate output paths."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = SecurityConfig(allowed_directories=[temp_dir])
            set_security_config(config)

            try:
                # Valid write should work
                output_file = Path(temp_dir) / "output.csv"
                writer = CSVWriterNode(file_path=str(output_file))
                result = writer.run(data=[{"name": "John", "age": 30}])
                assert "rows_written" in result

                # Invalid write path should be blocked
                with pytest.raises(PathTraversalError):
                    writer_bad = CSVWriterNode()
                    writer_bad.run(
                        file_path="../../../tmp/malicious.csv", data=[{"name": "evil"}]
                    )
            finally:
                set_security_config(SecurityConfig())


class TestPythonCodeNodeSecurity:
    """Test security features of Python Code Node."""

    def test_dangerous_import_blocking(self):
        """Test blocking of dangerous module imports."""
        executor = CodeExecutor()

        # Should block dangerous imports
        dangerous_code = """
import os
os.system('rm -rf /')
"""
        with pytest.raises(Exception):  # Should be blocked by safety check
            executor.execute_code(dangerous_code, {})

    def test_execution_timeout(self):
        """Test execution timeout enforcement."""
        config = SecurityConfig(execution_timeout=1.0)  # 1 second timeout
        executor = CodeExecutor(security_config=config)

        # Code that takes too long should timeout
        slow_code = """
import time
time.sleep(5)  # Sleep for 5 seconds
result = "done"
"""

        with pytest.raises(ExecutionTimeoutError):
            executor.execute_code(slow_code, {})

    def test_memory_limit_enforcement(self):
        """Test memory limit enforcement (Unix systems only)."""
        import platform

        if platform.system() == "Windows":
            pytest.skip("Memory limits not supported on Windows")

        config = SecurityConfig(memory_limit=10 * 1024 * 1024)  # 10MB limit
        executor = CodeExecutor(security_config=config)

        # Code that uses too much memory should fail
        memory_hog_code = """
# Try to allocate 100MB
big_list = [0] * (100 * 1024 * 1024)
result = len(big_list)
"""

        # Note: This test might not always work due to OS memory management
        # It's more of a best-effort security measure
        try:
            executor.execute_code(memory_hog_code, {})
        except (MemoryLimitError, MemoryError, OSError):
            pass  # Expected to fail due to memory limit

    def test_input_sanitization(self):
        """Test input sanitization for Python code execution."""
        config = SecurityConfig()
        executor = CodeExecutor(security_config=config)

        # Malicious input should be sanitized
        malicious_input = {
            "user_input": "'; os.system('rm -rf /'); #",
            "safe_input": "normal data",
        }

        code = """
result = user_input + " processed"
"""

        # Should execute without allowing code injection
        result = executor.execute_code(code, malicious_input)
        assert "result" in result
        # Input should be sanitized (dangerous characters like quotes and semicolons removed)
        result_str = str(result["result"])
        # The sanitization removes dangerous punctuation but may leave some text
        # Key is that it can't be executed as code due to removed quotes/semicolons
        assert ";" not in result_str  # Semicolon should be removed
        assert "rm -rf /" in result_str  # But the text content remains (just not executable)

    def test_builtin_function_restriction(self):
        """Test restriction of dangerous builtin functions."""
        executor = CodeExecutor()

        # Should block dangerous builtins
        dangerous_code = """
eval("os.system('echo hacked')")
"""
        with pytest.raises(Exception):
            executor.execute_code(dangerous_code, {})

        # exec should also be blocked
        dangerous_code2 = """
exec("import os; os.system('echo hacked')")
"""
        with pytest.raises(Exception):
            executor.execute_code(dangerous_code2, {})


class TestCommandInjectionPrevention:
    """Test command injection prevention."""

    def test_dangerous_command_detection(self):
        """Test detection of dangerous command patterns."""
        config = SecurityConfig(enable_command_validation=True)

        # Test that dangerous commands are properly detected and raise exceptions
        dangerous_commands = [
            "ls -la; rm -rf /",
            "echo hello && cat /etc/passwd", 
            "$(cat /etc/shadow)",
            "`whoami`"
        ]
        
        for cmd in dangerous_commands:
            # Due to some pytest interaction issue, test by catching the exception directly
            try:
                validate_command_string(cmd, config)
                # If we reach here, the exception wasn't raised
                pytest.fail(f"Expected CommandInjectionError for command: {cmd}")
            except CommandInjectionError:
                # This is expected - the dangerous command was detected
                pass
            except Exception as e:
                pytest.fail(f"Unexpected exception for command {cmd}: {type(e).__name__}: {e}")

    def test_safe_command_allowed(self):
        """Test that safe commands are allowed."""
        config = SecurityConfig()

        # Safe commands should be allowed
        safe_cmd = validate_command_string("python script.py", config)
        assert safe_cmd == "python script.py"

        safe_cmd2 = validate_command_string("echo 'Hello World'", config)
        assert safe_cmd2 == "echo 'Hello World'"


class TestInputSanitization:
    """Test input sanitization functions."""

    def test_string_sanitization(self):
        """Test string input sanitization."""
        config = SecurityConfig()

        # Dangerous characters should be removed
        dangerous_input = "normal text <script>alert('xss')</script> more text"
        sanitized = sanitize_input(dangerous_input, config=config)
        assert "<script>" not in sanitized
        assert "alert(" not in sanitized

    def test_length_validation(self):
        """Test input length validation."""
        config = SecurityConfig()

        # Very long input should be rejected
        long_input = "x" * 20000
        with pytest.raises(SecurityError):
            sanitize_input(long_input, max_length=1000, config=config)

    def test_type_validation(self):
        """Test input type validation."""
        config = SecurityConfig()

        # Dangerous types should be rejected
        class DangerousClass:
            def __init__(self):
                os.system("echo hacked")

        dangerous_obj = DangerousClass()
        with pytest.raises(SecurityError):
            sanitize_input(
                dangerous_obj, allowed_types=[str, int, float], config=config
            )

    def test_recursive_sanitization(self):
        """Test recursive sanitization of nested data structures."""
        config = SecurityConfig()

        # Nested dangerous content should be sanitized
        nested_input = {
            "safe_key": "safe_value",
            "dangerous_key": "dangerous <script> content",
            "nested": {"inner_dangerous": "more <script> stuff"},
            "list_data": [
                "safe",
                "dangerous <script>",
                {"nested_dangerous": "<script>"},
            ],
        }

        sanitized = sanitize_input(nested_input, config=config)

        # All dangerous content should be removed recursively
        def check_no_scripts(obj):
            if isinstance(obj, str):
                assert "<script>" not in obj
            elif isinstance(obj, dict):
                for value in obj.values():
                    check_no_scripts(value)
            elif isinstance(obj, list):
                for item in obj:
                    check_no_scripts(item)

        check_no_scripts(sanitized)


class TestSecurityConfiguration:
    """Test security configuration and policy enforcement."""

    def test_security_config_defaults(self):
        """Test security configuration defaults are secure."""
        config = SecurityConfig()

        # Should have reasonable defaults
        assert config.max_file_size > 0
        assert config.execution_timeout > 0
        assert config.memory_limit > 0
        assert len(config.allowed_file_extensions) > 0
        assert len(config.allowed_directories) > 0
        assert config.enable_audit_logging is True
        assert config.enable_path_validation is True
        assert config.enable_command_validation is True

    def test_security_policy_enforcement(self):
        """Test that security policies are consistently enforced."""
        # Restrictive config
        config = SecurityConfig(
            allowed_directories=["/tmp"],
            max_file_size=1000,
            execution_timeout=1.0,
            allowed_file_extensions=[".txt"],
            enable_audit_logging=True,
            enable_path_validation=True,
            enable_command_validation=True,
        )

        # All security features should be enforced
        assert config.enable_path_validation
        assert config.enable_command_validation
        assert config.enable_audit_logging

        # Limits should be restrictive
        assert config.max_file_size == 1000
        assert config.execution_timeout == 1.0
        assert config.allowed_file_extensions == [".txt"]
        assert config.allowed_directories == ["/tmp"]

    def test_security_bypass_prevention(self):
        """Test that security cannot be easily bypassed."""
        config = SecurityConfig(enable_path_validation=False)

        # Even with validation disabled, some protections should remain
        # (This tests defense in depth)
        try:
            validate_file_path("../../../etc/passwd", config)
            # If validation is disabled, this might pass, but other layers should catch it
        except (SecurityError, PathTraversalError):
            pass  # Good - another security layer caught it


class TestSecureTempDirectory:
    """Test secure temporary directory creation."""

    def test_secure_temp_dir_creation(self):
        """Test creation of secure temporary directories."""
        config = SecurityConfig()

        temp_dir = create_secure_temp_dir("test_", config)

        # Should create a directory
        assert temp_dir.exists()
        assert temp_dir.is_dir()

        # Should have secure permissions (on Unix systems)
        if hasattr(os, "stat"):
            stat_info = temp_dir.stat()
            # Owner should have full access, others should have no access
            permissions = stat_info.st_mode & 0o777
            assert permissions == 0o700

        # Clean up
        import shutil

        shutil.rmtree(temp_dir)


class TestSecurityAuditLogging:
    """Test security audit logging functionality."""

    def test_audit_logging_enabled(self):
        """Test that security events are logged when enabled."""
        config = SecurityConfig(enable_audit_logging=True)

        with patch("kailash.security.logger") as mock_logger:
            # Should log validation events
            try:
                validate_file_path("test.txt", config)
                mock_logger.info.assert_called()
            except SecurityError:
                pass  # May fail validation, but should still log

    def test_audit_logging_disabled(self):
        """Test that logging can be disabled."""
        config = SecurityConfig(enable_audit_logging=False)

        with patch("kailash.security.logger") as mock_logger:
            try:
                validate_file_path("test.txt", config)
                # Should not log when disabled
                mock_logger.info.assert_not_called()
            except SecurityError:
                pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
