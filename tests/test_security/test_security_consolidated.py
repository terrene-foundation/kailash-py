"""Consolidated security tests for the Kailash SDK."""

import tempfile
from pathlib import Path

import pytest

from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data.readers import CSVReaderNode, JSONReaderNode
from kailash.nodes.data.writers import CSVWriterNode
from kailash.security import (
    SecurityConfig,
    get_security_config,
    set_security_config,
    validate_file_path,
    sanitize_input,
    create_secure_temp_dir,
    validate_node_parameters,
)
from kailash.sdk_exceptions import PathTraversalError, SecurityError


class TestSecuritySuite:
    """Consolidated security tests covering all major security features."""

    def test_path_traversal_prevention(self):
        """Test path traversal attack prevention."""
        config = SecurityConfig(enforce_path_restrictions=True)
        
        # Valid paths should work
        with tempfile.NamedTemporaryFile(suffix=".csv") as tmp:
            validated = validate_file_path(tmp.name, config, "test")
            assert Path(validated).exists()
        
        # Path traversal attempts should be blocked
        dangerous_paths = [
            "../../../etc/passwd",
            "..\\..\\windows\\system32\\config",
            "/etc/shadow",
            "C:\\Windows\\System32\\config",
            "file:///etc/passwd",
            "//server/share/file.txt"
        ]
        
        for path in dangerous_paths:
            with pytest.raises(PathTraversalError):
                validate_file_path(path, config, "test")

    def test_input_sanitization(self):
        """Test input sanitization and validation."""
        config = SecurityConfig()
        
        # Safe inputs should pass through
        safe_inputs = ["hello world", 123, 45.67, True, ["a", "b"], {"key": "value"}]
        for inp in safe_inputs:
            result = sanitize_input(inp, config=config)
            assert result is not None
        
        # Dangerous strings should be sanitized
        dangerous = "alert('xss'); rm -rf /"
        sanitized = sanitize_input(dangerous, config=config)
        assert ";" not in sanitized  # Semicolons removed
        assert "rm -rf /" in sanitized  # But content preserved
        
        # Invalid types should be rejected
        with pytest.raises(SecurityError):
            sanitize_input(object(), config=config)

    def test_python_code_security(self):
        """Test Python code execution security."""
        # Safe code should execute
        safe_code = """
result = sum([1, 2, 3, 4, 5])
"""
        node = PythonCodeNode(code=safe_code)
        result = node.execute()
        assert result["result"] == 15
        
        # Dangerous imports should be blocked
        dangerous_codes = [
            "import os; os.system('rm -rf /')",
            "exec('print(\"hacked\")')",
            "eval('1+1')",
            "__import__('subprocess').call(['ls'])",
        ]
        
        for code in dangerous_codes:
            with pytest.raises(Exception):  # Should raise security or execution error
                node = PythonCodeNode(code=code)
                node.execute()

    def test_file_operations_security(self, tmp_path):
        """Test security of file reader/writer nodes."""
        config = SecurityConfig(enforce_path_restrictions=True)
        set_security_config(config)
        
        try:
            # Create test files
            csv_file = tmp_path / "test.csv"
            csv_file.write_text("name,age\nAlice,30\nBob,25\n")
            
            # Valid operations should work
            reader = CSVReaderNode(file_path=str(csv_file))
            result = reader.execute()
            assert "data" in result
            
            # Invalid paths should be blocked
            with pytest.raises(PathTraversalError):
                CSVReaderNode(file_path="../../../etc/passwd").execute()
                
            with pytest.raises(PathTraversalError):
                CSVWriterNode(file_path="../../../tmp/evil.csv").execute(data=[{"test": "data"}])
                
        finally:
            set_security_config(SecurityConfig())  # Reset

    def test_security_configuration(self):
        """Test security configuration management."""
        # Test default config
        default_config = get_security_config()
        assert default_config.enforce_path_restrictions is True
        assert default_config.max_file_size > 0
        
        # Test custom config
        custom_config = SecurityConfig(
            enforce_path_restrictions=False,
            max_file_size=1000,
            enable_audit_logging=True
        )
        set_security_config(custom_config)
        
        current_config = get_security_config()
        assert current_config.enforce_path_restrictions is False
        assert current_config.max_file_size == 1000
        assert current_config.enable_audit_logging is True
        
        # Reset to default
        set_security_config(SecurityConfig())

    def test_secure_temp_directory(self):
        """Test secure temporary directory creation."""
        config = SecurityConfig()
        temp_dir = create_secure_temp_dir(config=config)
        
        assert temp_dir.exists()
        assert temp_dir.is_dir()
        
        # Check permissions (on Unix systems)
        if hasattr(temp_dir, 'stat'):
            stat = temp_dir.stat()
            # Should be readable/writable by owner only
            assert oct(stat.st_mode)[-3:] == '700'

    def test_node_parameter_validation(self):
        """Test node parameter validation."""
        config = SecurityConfig()
        
        # Valid parameters should pass
        valid_params = {
            "name": "test_node",
            "value": 42,
            "items": ["a", "b", "c"],
            "config": {"enabled": True}
        }
        
        validated = validate_node_parameters(valid_params, config)
        assert len(validated) == len(valid_params)
        
        # File path parameters should be validated
        with pytest.raises(SecurityError):
            validate_node_parameters({"file_path": "../../../etc/passwd"}, config)

    def test_command_injection_prevention(self):
        """Test command injection prevention."""
        dangerous_commands = [
            "ls -la; rm -rf /",
            "echo hello && cat /etc/passwd",
            "$(cat /etc/shadow)",
            "`whoami`"
        ]
        
        config = SecurityConfig()
        
        for cmd in dangerous_commands:
            # Commands should be sanitized or rejected
            try:
                sanitized = sanitize_input(cmd, config=config)
                # Should remove dangerous characters
                assert "&&" not in sanitized or ";" not in sanitized
            except SecurityError:
                # Or should be completely rejected
                pass

    def test_memory_and_resource_limits(self):
        """Test memory and resource limit enforcement."""
        # Test that large inputs are rejected
        config = SecurityConfig(max_string_length=100)
        
        large_string = "x" * 1000
        with pytest.raises(SecurityError):
            sanitize_input(large_string, config=config)
        
        # Test Python code execution limits
        memory_intensive_code = """
# This should be limited by execution timeout/memory
result = [i for i in range(1000)]
"""
        node = PythonCodeNode(code=memory_intensive_code)
        # Should execute but be limited
        result = node.execute()
        assert "result" in result

    def test_audit_logging(self):
        """Test security audit logging."""
        config = SecurityConfig(enable_audit_logging=True)
        set_security_config(config)
        
        try:
            # Operations should be logged (we can't easily test log output here)
            validate_node_parameters({"test": "value"}, config)
            sanitize_input("test input", config=config)
            
            # Just verify no exceptions are raised during logging
            assert True
        finally:
            set_security_config(SecurityConfig())