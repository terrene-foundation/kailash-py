"""Unit tests for secure logging utilities."""

import json
import logging
import re
from unittest.mock import MagicMock, Mock, patch

import pytest
from kailash.utils.secure_logging import (
    SecureLogger,
    SecureLoggingMixin,
    SecureLoggingPatterns,
    apply_secure_logging_to_node,
    secure_log,
)


class TestSecureLoggingPatterns:
    """Test pattern definitions for sensitive data detection."""

    def test_credit_card_pattern(self):
        """Test credit card pattern matching."""
        pattern = SecureLoggingPatterns.CREDIT_CARD

        # Valid credit card formats
        assert pattern.search("4111111111111111")
        assert pattern.search("4111 1111 1111 1111")
        assert pattern.search("4111-1111-1111-1111")

        # Invalid formats
        assert not pattern.search("411111111111111")  # Too short
        assert not pattern.search("41111111111111111")  # Too long
        assert not pattern.search("4111-11-1111-1111")  # Wrong grouping

    def test_ssn_pattern(self):
        """Test SSN pattern matching."""
        pattern = SecureLoggingPatterns.SSN

        # Valid SSN formats
        assert pattern.search("123-45-6789")
        assert pattern.search("123456789")

        # Invalid formats
        assert not pattern.search("12-345-6789")
        assert not pattern.search("1234-5-6789")

    def test_email_pattern(self):
        """Test email pattern matching."""
        pattern = SecureLoggingPatterns.EMAIL

        # Valid emails
        assert pattern.search("user@example.com")
        assert pattern.search("user.name+tag@example.co.uk")
        assert pattern.search("test_email@company-name.org")

        # Invalid emails
        assert not pattern.search("@example.com")
        assert not pattern.search("user@")
        assert not pattern.search("user.example.com")

    def test_phone_pattern(self):
        """Test phone number pattern matching."""
        pattern = SecureLoggingPatterns.PHONE

        # Valid phone formats
        assert pattern.search("(555)123-4567")
        assert pattern.search("555-123-4567")
        assert pattern.search("5551234567")
        assert pattern.search("+1(555)123-4567")
        assert pattern.search("+1-555-123-4567")
        assert pattern.search("1-555-123-4567")
        assert pattern.search("555.123.4567")

        # Test the actual pattern catches phone numbers in context
        assert pattern.search("Call me at 555-123-4567")
        assert pattern.search("Phone: 5551234567")

    def test_api_key_patterns(self):
        """Test API key pattern matching."""
        patterns = SecureLoggingPatterns.API_KEY_PATTERNS

        # OpenAI key
        assert any(
            p.search("sk-abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWX")
            for p in patterns
        )

        # Google key
        assert any(p.search("AIzaSyAbcdefGhijKlmnopQrstuvWxyz123456") for p in patterns)

        # GitHub key
        assert any(
            p.search("ghp_abcdefghijklmnopqrstuvwxyz0123456789") for p in patterns
        )

        # Generic 32-char key
        assert any(p.search("abcdef0123456789abcdef0123456789") for p in patterns)

    def test_password_patterns(self):
        """Test password pattern matching."""
        patterns = SecureLoggingPatterns.PASSWORD_PATTERNS

        test_cases = [
            'password: "secret123"',
            "password = 'mypass'",
            "pwd: mysecret",
            "pass=p@ssw0rd",
            '"password": "value"',
        ]

        for test_str in test_cases:
            assert any(p.search(test_str) for p in patterns)

    def test_token_patterns(self):
        """Test token pattern matching."""
        patterns = SecureLoggingPatterns.TOKEN_PATTERNS

        test_cases = [
            'token: "abc123xyz"',
            "api_key = 'secret-key-123'",
            "secret: mysecretvalue",
            '"token": "bearer-xyz"',
        ]

        for test_str in test_cases:
            assert any(p.search(test_str) for p in patterns)

    def test_pii_field_names(self):
        """Test PII field name set."""
        pii_fields = SecureLoggingPatterns.PII_FIELD_NAMES

        # Check common fields are included
        assert "ssn" in pii_fields
        assert "credit_card" in pii_fields
        assert "password" in pii_fields
        assert "email" in pii_fields
        assert "phone_number" in pii_fields
        assert "date_of_birth" in pii_fields

        # Check case sensitivity (should be lowercase)
        assert "SSN" not in pii_fields
        assert "Password" not in pii_fields


class TestSecureLogger:
    """Test SecureLogger functionality."""

    @pytest.fixture
    def logger(self):
        """Create a SecureLogger instance."""
        return SecureLogger("test_logger")

    def test_initialization(self):
        """Test SecureLogger initialization."""
        logger = SecureLogger(
            "test",
            mask_char="#",
            mask_length=10,
            custom_patterns=[re.compile(r"custom\d+")],
            custom_fields={"custom_field"},
        )

        assert logger.mask_char == "#"
        assert logger.mask_length == 10
        assert len(logger.custom_patterns) == 1
        assert "custom_field" in logger.custom_fields

    def test_mask_value_fixed_length(self):
        """Test masking with fixed length."""
        logger = SecureLogger("test", mask_length=8)

        assert logger._mask_value("short") == "********"
        assert logger._mask_value("verylongvalue") == "********"
        assert logger._mask_value("") == ""

    def test_mask_value_preserve_partial(self):
        """Test masking with partial preservation."""
        logger = SecureLogger("test", mask_length=0)

        # Long values preserve first 2 and last 2
        assert (
            logger._mask_value("1234567890123456", preserve_partial=True)
            == "12************56"
        )

        # Short values are fully masked
        assert logger._mask_value("12345678", preserve_partial=True) == "********"

        # No preservation
        assert logger._mask_value("1234567890", preserve_partial=False) == "**********"

    def test_mask_dict(self, logger):
        """Test masking dictionary values."""
        data = {
            "username": "john_doe",
            "password": "secret123",
            "email": "john@example.com",
            "age": 30,
            "nested": {"ssn": "123-45-6789", "public_info": "visible"},
        }

        masked = logger._mask_dict(data)

        assert masked["username"] == "john_doe"  # Not in PII fields
        assert masked["password"] != "secret123"  # Masked
        assert masked["email"] != "john@example.com"  # Masked
        assert masked["age"] == 30  # Not sensitive
        assert masked["nested"]["ssn"] != "123-45-6789"  # Masked
        assert masked["nested"]["public_info"] == "visible"  # Not sensitive

    def test_mask_dict_with_lists(self, logger):
        """Test masking dictionaries containing lists."""
        data = {
            "users": [
                {"name": "Alice", "email": "alice@example.com"},
                {"name": "Bob", "email": "bob@example.com"},
            ],
            "credit_card": "4111111111111111",
        }

        masked = logger._mask_dict(data)

        assert masked["users"][0]["name"] == "Alice"
        assert masked["users"][0]["email"] != "alice@example.com"
        assert masked["users"][1]["email"] != "bob@example.com"
        assert masked["credit_card"] != "4111111111111111"

    def test_mask_string(self, logger):
        """Test masking patterns in strings."""
        text = """
        User email: john@example.com
        Credit card: 4111-1111-1111-1111
        SSN: 123-45-6789
        Phone: 555-123-4567
        API Key: sk-abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWX
        Password: secret123
        """

        masked = logger._mask_string(text)

        assert "john@example.com" not in masked
        assert "4111-1111-1111-1111" not in masked
        assert "123-45-6789" not in masked
        assert "555-123-4567" not in masked
        assert "sk-abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWX" not in masked
        assert "secret123" not in masked

    def test_mask_email(self, logger):
        """Test email masking preserves domain."""
        # Default logger has mask_length=8 (fixed length)
        assert logger._mask_email("user@example.com") == "********@example.com"
        assert logger._mask_email("longusername@domain.org") == "********@domain.org"
        assert logger._mask_email("notanemail") == "********"

    def test_mask_data_various_types(self, logger):
        """Test masking various data types."""
        # String
        assert "secret" not in logger._mask_data("password: secret")

        # Dictionary
        masked_dict = logger._mask_data({"password": "secret"})
        assert masked_dict["password"] != "secret"

        # List
        masked_list = logger._mask_data(["public", "password: secret"])
        assert masked_list[0] == "public"
        assert "secret" not in masked_list[1]

        # Other types
        assert logger._mask_data(42) == 42
        assert logger._mask_data(None) is None

    def test_custom_patterns(self):
        """Test custom pattern masking."""
        custom_pattern = re.compile(r"CUSTOM-\d{4}")
        logger = SecureLogger("test", custom_patterns=[custom_pattern])

        text = "Custom ID: CUSTOM-1234"
        masked = logger._mask_string(text)

        assert "CUSTOM-1234" not in masked
        assert "Custom ID:" in masked  # Text before match is preserved

    def test_custom_fields(self):
        """Test custom field masking."""
        logger = SecureLogger("test", custom_fields={"api_token", "secret_key"})

        data = {
            "api_token": "my-secret-token",
            "secret_key": "private-key-123",
            "public_data": "visible",
        }

        masked = logger._mask_dict(data)

        assert masked["api_token"] != "my-secret-token"
        assert masked["secret_key"] != "private-key-123"
        assert masked["public_data"] == "visible"

    @patch("logging.getLogger")
    def test_logging_methods(self, mock_get_logger):
        """Test logging methods mask data correctly."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        logger = SecureLogger("test")

        # Test debug
        logger.debug("Password: %s", "secret123")
        mock_logger.debug.assert_called()
        args = mock_logger.debug.call_args[0]
        # The string is formatted first, then masked based on patterns
        # "Password: secret123" matches password pattern, so the value is masked
        assert "secret123" not in args[0]
        assert "Password:" in args[0]

        # Test info with kwargs
        logger.info("User login", user="john", password="secret")
        mock_logger.info.assert_called()
        kwargs = mock_logger.info.call_args[1]
        assert kwargs.get("password") != "secret"

        # Test warning
        logger.warning("Credit card: 4111111111111111")
        mock_logger.warning.assert_called()
        args = mock_logger.warning.call_args[0]
        assert "4111111111111111" not in args[0]

        # Test error
        logger.error("SSN exposed: 123-45-6789")
        mock_logger.error.assert_called()
        args = mock_logger.error.call_args[0]
        assert "123-45-6789" not in args[0]


class TestSecureLoggingMixin:
    """Test SecureLoggingMixin functionality."""

    def test_mixin_initialization(self):
        """Test mixin adds secure logger to class."""

        class TestClass(SecureLoggingMixin):
            def __init__(self):
                super().__init__()

        obj = TestClass()
        assert hasattr(obj, "_secure_logger")
        assert isinstance(obj._secure_logger, SecureLogger)

    def test_mixin_with_sensitive_fields(self):
        """Test mixin with custom sensitive fields."""

        class TestClass(SecureLoggingMixin):
            _sensitive_fields = {"custom_secret"}

            def __init__(self):
                super().__init__()

        obj = TestClass()
        assert "custom_secret" in obj._secure_logger.custom_fields

    def test_log_methods(self):
        """Test mixin logging methods."""

        class TestClass(SecureLoggingMixin):
            def __init__(self):
                super().__init__()

        obj = TestClass()

        with patch.object(obj._secure_logger, "debug") as mock_debug:
            obj.log_debug("Test message", {"password": "secret"})
            mock_debug.assert_called_once()
            call_args = mock_debug.call_args[0][0]
            assert "secret" not in call_args

        with patch.object(obj._secure_logger, "info") as mock_info:
            obj.log_info("Info message")
            mock_info.assert_called_once_with("Info message")

        with patch.object(obj._secure_logger, "error") as mock_error:
            ex = Exception("Test error")
            obj.log_error("Error occurred", ex, {"ssn": "123-45-6789"})
            mock_error.assert_called_once()
            call_args = mock_error.call_args[0][0]
            assert "Test error" in call_args
            assert "123-45-6789" not in call_args


class TestSecureLogDecorator:
    """Test secure_log decorator."""

    def test_secure_log_basic(self):
        """Test basic secure logging decorator."""
        with patch("kailash.utils.secure_logging.SecureLogger") as MockLogger:
            mock_logger = MagicMock()
            MockLogger.return_value = mock_logger

            @secure_log()
            def test_func(public_arg, secret_arg="password"):
                return "result"

            result = test_func("public", secret_arg="my-password")

            assert result == "result"
            assert mock_logger.debug.call_count == 2  # Start and end

            # Check logging calls
            start_call = mock_logger.debug.call_args_list[0][0][0]
            assert "test_func" in start_call
            assert "completed successfully" in mock_logger.debug.call_args_list[1][0][0]

    def test_secure_log_with_mask_params(self):
        """Test secure log with specific masked parameters."""
        with patch("kailash.utils.secure_logging.SecureLogger") as MockLogger:
            mock_logger = MagicMock()
            mock_logger._mask_value = lambda x: "****"
            mock_logger._mask_data = lambda x: x if not isinstance(x, str) else "masked"
            MockLogger.return_value = mock_logger

            @secure_log(mask_params=["password", "token"])
            def test_func(username, password, token, data):
                return "result"

            test_func(
                username="john",
                password="secret123",
                token="abc-xyz",
                data={"key": "value"},
            )

            # Verify masked parameters were handled specially
            debug_call = mock_logger.debug.call_args_list[0][0][0]
            assert "test_func" in debug_call

    def test_secure_log_exception_handling(self):
        """Test secure log handles exceptions."""
        with patch("kailash.utils.secure_logging.SecureLogger") as MockLogger:
            mock_logger = MagicMock()
            MockLogger.return_value = mock_logger

            @secure_log()
            def failing_func():
                raise ValueError("Test error")

            with pytest.raises(ValueError, match="Test error"):
                failing_func()

            # Verify error was logged
            mock_logger.error.assert_called_once()
            error_msg = mock_logger.error.call_args[0][0]
            assert "failing_func failed" in error_msg
            assert "Test error" in error_msg


class TestApplySecureLoggingToNode:
    """Test apply_secure_logging_to_node decorator."""

    def test_apply_to_node_class(self):
        """Test applying secure logging to a node class."""

        class TestNode:
            def run(self, **inputs):
                return {"result": "success"}

        SecureNode = apply_secure_logging_to_node(TestNode)

        # Check class properties preserved
        assert SecureNode.__name__ == "TestNode"
        assert issubclass(SecureNode, SecureLoggingMixin)
        assert issubclass(SecureNode, TestNode)

    def test_secure_node_execution(self):
        """Test secure node logs execution."""

        class TestNode:
            def run(self, **inputs):
                if inputs.get("fail"):
                    raise ValueError("Node failed")
                return {"result": inputs.get("value", "default")}

        SecureNode = apply_secure_logging_to_node(TestNode)
        node = SecureNode()

        # Mock the logger
        with patch.object(node, "log_debug") as mock_debug:
            with patch.object(node, "log_error") as mock_error:
                # Successful execution
                result = node.run(value="test", password="secret")
                assert result["result"] == "test"

                assert mock_debug.call_count == 2
                mock_debug.assert_any_call(
                    "Node execution started", {"value": "test", "password": "secret"}
                )
                mock_debug.assert_any_call("Node execution completed")

                # Failed execution
                with pytest.raises(ValueError):
                    node.run(fail=True, ssn="123-45-6789")

                mock_error.assert_called_once()
                error_call_args = mock_error.call_args[0]
                assert error_call_args[0] == "Node execution failed"
                assert isinstance(error_call_args[1], ValueError)
                assert error_call_args[2] == {"fail": True, "ssn": "123-45-6789"}

    def test_secure_node_preserves_functionality(self):
        """Test secure node preserves original functionality."""

        class TestNode:
            def __init__(self, name="test"):
                self.name = name

            def run(self, **inputs):
                return {"name": self.name, "inputs": inputs}

            def custom_method(self):
                return "custom"

        SecureNode = apply_secure_logging_to_node(TestNode)
        node = SecureNode(name="secure-test")

        # Test initialization
        assert node.name == "secure-test"

        # Test run method
        result = node.run(data="value")
        assert result["name"] == "secure-test"
        assert result["inputs"]["data"] == "value"

        # Test custom method
        assert node.custom_method() == "custom"
