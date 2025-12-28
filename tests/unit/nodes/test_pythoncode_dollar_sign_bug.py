"""
Test for $ character corruption bug in PythonCodeNode.

This test reproduces the critical bug where $ characters are stripped from
string data when passed through PythonCodeNode connections, breaking bcrypt
password hashes and other data containing $ characters.

Bug Report: SDK Bug Report: $ Character Corruption in PythonCodeNode Parameter Passing
Severity: Critical
Root Cause: security.py:755 - sanitize_input() strips $ characters
"""

import pytest
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestPythonCodeDollarSignBug:
    """Test suite for $ character preservation in PythonCodeNode."""

    def test_bcrypt_hash_preservation(self):
        """
        Test that bcrypt password hashes are preserved through PythonCodeNode.

        Bcrypt hashes start with $2b$ or $2a$ - these $ characters must not be stripped.
        """
        # Bcrypt hash example (actual hash format)
        bcrypt_hash = "$2b$12$BC9rNwMq3rpIFNmOjdd4hOUGqT2L40FZo/f1vuN2wKaRMqKc/DPAG"

        workflow = WorkflowBuilder()

        # Create a simple source node that outputs the hash
        workflow.add_node(
            "PythonCodeNode",
            "source",
            {"code": f'result = {{"password_hash": "{bcrypt_hash}"}}'},
        )

        # Pass through another PythonCodeNode via connection
        workflow.add_node(
            "PythonCodeNode",
            "validator",
            {
                "code": """
# Receive password_hash from connection
result = {
    'hash_value': password_hash,
    'length_value': len(password_hash),
    'starts_with_dollar_2b': password_hash.startswith('$2b$'),
    'first_10': password_hash[:10]
}
"""
            },
        )

        workflow.add_connection(
            "source", "result.password_hash", "validator", "password_hash"
        )

        with LocalRuntime() as runtime:
            results, _ = runtime.execute(workflow.build())

        # Verify the hash was preserved
        output_hash = results["validator"]["result"]["hash_value"]

        assert output_hash == bcrypt_hash, (
            f"Bcrypt hash corrupted!\n"
            f"Expected: {bcrypt_hash}\n"
            f"Got:      {output_hash}\n"
            f"Expected length: {len(bcrypt_hash)}\n"
            f"Got length:      {len(output_hash)}\n"
        )

        assert (
            results["validator"]["result"]["length_value"] == 60
        ), f"Hash length incorrect: expected 60, got {results['validator']['result']['length_value']}"
        assert (
            results["validator"]["result"]["starts_with_dollar_2b"] is True
        ), "Hash doesn't start with $2b$"
        assert results["validator"]["result"]["first_10"] == "$2b$12$BC9", (
            f"First 10 characters corrupted: "
            f"expected '$2b$12$BC9', got '{results['validator']['result']['first_10']}'"
        )

    def test_multiple_dollar_signs_preservation(self):
        """Test that multiple $ characters are all preserved."""
        test_string = "$VAR1$VAR2$VAR3$"

        workflow = WorkflowBuilder()

        workflow.add_node(
            "PythonCodeNode",
            "source",
            {"code": f'result = {{"data": "{test_string}"}}'},
        )

        workflow.add_node(
            "PythonCodeNode",
            "processor",
            {"code": "result = {'output': data, 'count': data.count('$')}"},
        )

        workflow.add_connection("source", "result.data", "processor", "data")

        with LocalRuntime() as runtime:
            results, _ = runtime.execute(workflow.build())

        assert (
            results["processor"]["result"]["output"] == test_string
        ), f"String corrupted: expected {test_string}, got {results['processor']['result']['output']}"
        assert (
            results["processor"]["result"]["count"] == 4
        ), f"Dollar signs missing: expected 4, got {results['processor']['result']['count']}"

    def test_currency_values_preservation(self):
        """Test that currency values with $ are preserved."""
        price = "$199.99"

        workflow = WorkflowBuilder()

        workflow.add_node(
            "PythonCodeNode", "source", {"code": f'result = {{"price": "{price}"}}'}
        )

        workflow.add_node(
            "PythonCodeNode",
            "parser",
            {
                "code": """
result = {
    'original': price,
    'starts_with_dollar': price.startswith('$'),
    'numeric_part': price[1:] if price.startswith('$') else price
}
"""
            },
        )

        workflow.add_connection("source", "result.price", "parser", "price")

        with LocalRuntime() as runtime:
            results, _ = runtime.execute(workflow.build())

        assert (
            results["parser"]["result"]["original"] == price
        ), f"Price corrupted: expected {price}, got {results['parser']['result']['original']}"
        assert (
            results["parser"]["result"]["starts_with_dollar"] is True
        ), "Price doesn't start with $"
        assert (
            results["parser"]["result"]["numeric_part"] == "199.99"
        ), "Failed to parse numeric part"

    def test_regex_anchor_preservation(self):
        """Test that regex patterns with $ (end-of-line anchor) are preserved."""
        regex_pattern = "^test$"

        workflow = WorkflowBuilder()

        workflow.add_node(
            "PythonCodeNode",
            "source",
            {"code": f'result = {{"pattern": "{regex_pattern}"}}'},
        )

        workflow.add_node(
            "PythonCodeNode",
            "validator",
            {
                "code": """
import re
result = {
    'pattern': pattern,
    'has_start_anchor': pattern.startswith('^'),
    'has_end_anchor': pattern.endswith('$'),
    'matches_test': bool(re.match(pattern, 'test'))
}
"""
            },
        )

        workflow.add_connection("source", "result.pattern", "validator", "pattern")

        with LocalRuntime() as runtime:
            results, _ = runtime.execute(workflow.build())

        assert (
            results["validator"]["result"]["pattern"] == regex_pattern
        ), f"Regex pattern corrupted: expected {regex_pattern}, got {results['validator']['result']['pattern']}"
        assert (
            results["validator"]["result"]["has_start_anchor"] is True
        ), "Missing ^ anchor"
        assert (
            results["validator"]["result"]["has_end_anchor"] is True
        ), "Missing $ anchor"
        assert (
            results["validator"]["result"]["matches_test"] is True
        ), "Regex doesn't match"

    def test_argon2_hash_preservation(self):
        """Test that Argon2 password hashes are preserved."""
        argon2_hash = "$argon2id$v=19$m=65536,t=2,p=1$somesalthere$hashvaluehere"

        workflow = WorkflowBuilder()

        workflow.add_node(
            "PythonCodeNode",
            "source",
            {"code": f'result = {{"hash": "{argon2_hash}"}}'},
        )

        workflow.add_node(
            "PythonCodeNode",
            "validator",
            {
                "code": """
result = {
    'hash': hash_value,
    'starts_with_argon2': hash_value.startswith('$argon2'),
    'dollar_count': hash_value.count('$')
}
""",
                "inputs": {"hash_value": "hash"},
            },
        )

        workflow.add_connection("source", "result.hash", "validator", "hash_value")

        with LocalRuntime() as runtime:
            results, _ = runtime.execute(workflow.build())

        assert (
            results["validator"]["result"]["hash"] == argon2_hash
        ), f"Argon2 hash corrupted: expected {argon2_hash}, got {results['validator']['result']['hash']}"
        assert (
            results["validator"]["result"]["starts_with_argon2"] is True
        ), "Hash doesn't start with $argon2"
        assert (
            results["validator"]["result"]["dollar_count"] == 5
        ), f"Dollar signs missing: expected 5, got {results['validator']['result']['dollar_count']}"

    def test_all_shell_metacharacters_preservation(self):
        """
        Test that all shell metacharacters are preserved in Python context.

        PythonCodeNode executes Python code via exec(), not shell commands.
        Therefore, shell metacharacters like $, ;, &, |, `, (, ) should be
        preserved as they are just regular characters in Python strings.
        """
        test_strings = {
            "dollar": "$HOME",
            "semicolon": "cmd1; cmd2",
            "ampersand": "a && b",
            "pipe": "a | b",
            "backtick": "result=`command`",
            "parens": "$(command)",
            "angles": "<tag>",
            "combined": "$VAR; echo $(test) | grep `pattern`",
        }

        for name, test_str in test_strings.items():
            workflow = WorkflowBuilder()

            workflow.add_node(
                "PythonCodeNode",
                "source",
                {"code": f'result = {{"data": """{test_str}"""}}'},
            )

            workflow.add_node(
                "PythonCodeNode",
                "validator",
                {"code": "result = {'output': data, 'length': len(data)}"},
            )

            workflow.add_connection("source", "result.data", "validator", "data")

            with LocalRuntime() as runtime:
                results, _ = runtime.execute(workflow.build())

                assert results["validator"]["result"]["output"] == test_str, (
                    f"String '{name}' corrupted!\n"
                    f"Expected: {test_str}\n"
                    f"Got:      {results['validator']['result']['output']}\n"
                )

                assert results["validator"]["result"]["length"] == len(test_str), (
                    f"String '{name}' length mismatch!\n"
                    f"Expected: {len(test_str)}\n"
                    f"Got:      {results['validator']['result']['length']}\n"
                )
