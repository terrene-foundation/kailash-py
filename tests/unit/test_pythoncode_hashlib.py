"""Test hashlib import in PythonCodeNode for TODO-116."""

import pytest
from kailash.nodes.code.python import PythonCodeNode


class TestPythonCodeHashlib:
    """Test hashlib is allowed in PythonCodeNode string execution."""

    def test_hashlib_import_allowed(self):
        """Test that hashlib can be imported in string code."""
        node = PythonCodeNode(
            name="test_hashlib",
            code="""
import hashlib
result = hashlib.md5(b"test").hexdigest()
""",
        )

        result = node.execute()
        assert result["result"] == "098f6bcd4621d373cade4e832627b4f6"

    def test_hashlib_sha256(self):
        """Test SHA256 hashing works correctly."""
        node = PythonCodeNode(
            name="test_sha256",
            code="""
import hashlib
text = "Hello, World!"
result = hashlib.sha256(text.encode()).hexdigest()
""",
        )

        result = node.execute()
        expected = "dffd6021bb2bd5b0af676290809ec3a53191dd81c7f70a4b28688a362182986f"
        assert result["result"] == expected

    def test_hashlib_with_parameters(self):
        """Test hashlib with input parameters."""
        node = PythonCodeNode(
            name="test_hashlib_params",
            code="""
import hashlib
result = hashlib.sha1(text.encode()).hexdigest()
""",
        )

        result = node.execute(text="test message")
        assert result["result"] == "35ee8386410d41d14b3f779fc95f4695f4851682"

    def test_hashlib_multiple_algorithms(self):
        """Test multiple hash algorithms work."""
        node = PythonCodeNode(
            name="test_multiple_hashes",
            code="""
import hashlib

data = b"test data"
result = {
    "md5": hashlib.md5(data).hexdigest(),
    "sha1": hashlib.sha1(data).hexdigest(),
    "sha256": hashlib.sha256(data).hexdigest()
}
""",
        )

        result = node.execute()
        assert result["result"]["md5"] == "eb733a00c0c9d336e65691a37ab54293"
        assert result["result"]["sha1"] == "f48dd853820860816c75d54d0f584dc863327a7c"
        assert (
            result["result"]["sha256"]
            == "916f0027a575074ce72a331777c3478d6513f786a591bd892da1a577bf2335f9"
        )

    def test_hashlib_with_uuid_example(self):
        """Test the example from the critique - using uuid instead of hashlib."""
        node = PythonCodeNode(
            name="test_uuid_replacement",
            code="""
import uuid
import hashlib

# Original workaround with uuid
email = "user@example.com"
attendee_id_uuid = f"CONF2024-{str(uuid.uuid5(uuid.NAMESPACE_DNS, email))[:8].upper()}"

# Now we can use hashlib as originally intended
attendee_id_hash = f"CONF2024-{hashlib.md5(email.encode()).hexdigest()[:8].upper()}"

result = {
    "uuid_method": attendee_id_uuid,
    "hashlib_method": attendee_id_hash
}
""",
        )

        result = node.execute()
        assert "uuid_method" in result["result"]
        assert "hashlib_method" in result["result"]
        assert result["result"]["uuid_method"].startswith("CONF2024-")
        assert result["result"]["hashlib_method"].startswith("CONF2024-")
