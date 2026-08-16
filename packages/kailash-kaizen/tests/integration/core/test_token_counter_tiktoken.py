"""Tier-2 tests for TokenCounter against REAL tiktoken encoding data.

Moved out of ``tests/unit/core/test_token_counter.py``. These assert the
content of tiktoken's own BPE tables ("Hello, world!" is exactly 4 tokens in
``cl100k_base``), and tiktoken does not ship those tables in its wheel — it
fetches them from ``openaipublic.blob.core.windows.net`` on first use. A test
that downloads 1.7MB before it can assert is an integration test regardless of
which directory it sits in (``rules/testing.md`` § 3-Tier: Tier-1 MUST NOT
touch the network).

They passed for as long as they did because a developer machine, and any CI
runner with a warm tiktoken cache, already had the file on disk. On a cold
cache with no network ``_get_encoder`` returns None and ``count`` falls back
to the character estimate, so ``count("Hello, world!")`` returns 3 rather
than 4.

The Tier-1 half of this contract — that ``count`` DELEGATES to an encoder when
one exists rather than silently estimating — is covered offline with a stub
encoder in ``tests/unit/core/test_token_counter.py::TestEncoderDelegation``.
What lives here is only the part that genuinely needs the real tables.
"""

import pytest

from kaizen.core.token_counter import TokenCounter

try:
    import tiktoken

    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False


@pytest.mark.integration
@pytest.mark.skipif(
    not TIKTOKEN_AVAILABLE,
    reason="tiktoken not installed - tests require tiktoken",
)
class TestTiktokenSpecific:
    """Tests that specifically require real tiktoken encoding data."""

    def test_tiktoken_exact_count(self):
        """Test exact token count with tiktoken."""
        counter = TokenCounter()
        # "Hello, world!" is exactly 4 tokens in cl100k_base
        tokens = counter.count("Hello, world!", encoding_name="cl100k_base")
        assert tokens == 4

    def test_tiktoken_encoding_for_model(self):
        """Test tiktoken-based encoding selection."""
        import tiktoken

        counter = TokenCounter()
        # Get encoding directly from tiktoken
        expected = tiktoken.encoding_for_model("gpt-4")
        actual = counter._get_encoder("cl100k_base")
        assert actual is not None
        # Verify they produce same result
        text = "Test text"
        assert len(expected.encode(text)) == len(actual.encode(text))
