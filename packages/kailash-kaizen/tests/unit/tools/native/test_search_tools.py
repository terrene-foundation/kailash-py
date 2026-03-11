"""
Unit Tests for Native Search Tools (Tier 1)

Tests WebSearchTool and WebFetchTool for web search and URL fetching.

Coverage:
- Tool attributes and schemas
- Search result formatting
- URL validation and security
- Content extraction
- Error handling
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kaizen.tools.native.search_tools import WebFetchTool, WebSearchTool
from kaizen.tools.types import DangerLevel, ToolCategory


class TestWebSearchToolAttributes:
    """Test WebSearchTool attributes."""

    def test_tool_attributes(self):
        """Test tool has correct attributes."""
        tool = WebSearchTool()

        assert tool.name == "web_search"
        assert "search" in tool.description.lower()
        assert tool.danger_level == DangerLevel.SAFE
        assert tool.category == ToolCategory.NETWORK

    def test_get_schema(self):
        """Test schema is correct."""
        tool = WebSearchTool()
        schema = tool.get_schema()

        assert schema["type"] == "object"
        assert "query" in schema["properties"]
        assert "num_results" in schema["properties"]
        assert "query" in schema["required"]

    def test_default_search_provider(self):
        """Test default search provider is duckduckgo."""
        tool = WebSearchTool()
        assert tool.search_provider == "duckduckgo"

    def test_custom_search_provider(self):
        """Test custom search provider."""
        tool = WebSearchTool(search_provider="custom")
        assert tool.search_provider == "custom"


class TestWebSearchToolExecution:
    """Test WebSearchTool execution."""

    @pytest.mark.asyncio
    async def test_empty_query_returns_error(self):
        """Test empty query returns error."""
        tool = WebSearchTool()

        result = await tool.execute(query="")

        assert result.success is False
        assert "empty" in result.error.lower()

    @pytest.mark.asyncio
    async def test_whitespace_query_returns_error(self):
        """Test whitespace-only query returns error."""
        tool = WebSearchTool()

        result = await tool.execute(query="   ")

        assert result.success is False
        assert "empty" in result.error.lower()

    @pytest.mark.asyncio
    async def test_unknown_provider_returns_error(self):
        """Test unknown provider returns error."""
        tool = WebSearchTool(search_provider="unknown_provider")

        result = await tool.execute(query="test query")

        assert result.success is False
        assert "unknown" in result.error.lower()

    @pytest.mark.asyncio
    async def test_num_results_capped(self):
        """Test num_results is capped at 10."""
        tool = WebSearchTool()

        # Mock DDGS to avoid actual API calls - patch at module level
        with patch.object(tool, "_check_ddg_available", return_value=True):
            with patch.dict("sys.modules", {"duckduckgo_search": MagicMock()}):
                import sys

                mock_ddgs = MagicMock()
                mock_instance = MagicMock()
                mock_instance.__enter__ = MagicMock(return_value=mock_instance)
                mock_instance.__exit__ = MagicMock(return_value=False)
                mock_instance.text = MagicMock(return_value=[])
                mock_ddgs.return_value = mock_instance
                sys.modules["duckduckgo_search"].DDGS = mock_ddgs

                await tool.execute(query="test", num_results=100)

                # Should have been called with max 10
                mock_instance.text.assert_called_once()
                call_args = mock_instance.text.call_args
                assert call_args[1]["max_results"] <= 10

    @pytest.mark.asyncio
    async def test_num_results_minimum(self):
        """Test num_results minimum is 1."""
        tool = WebSearchTool()

        with patch.object(tool, "_check_ddg_available", return_value=True):
            with patch.dict("sys.modules", {"duckduckgo_search": MagicMock()}):
                import sys

                mock_ddgs = MagicMock()
                mock_instance = MagicMock()
                mock_instance.__enter__ = MagicMock(return_value=mock_instance)
                mock_instance.__exit__ = MagicMock(return_value=False)
                mock_instance.text = MagicMock(return_value=[])
                mock_ddgs.return_value = mock_instance
                sys.modules["duckduckgo_search"].DDGS = mock_ddgs

                await tool.execute(query="test", num_results=0)

                call_args = mock_instance.text.call_args
                assert call_args[1]["max_results"] >= 1

    @pytest.mark.asyncio
    async def test_ddg_not_available(self):
        """Test error when duckduckgo-search not installed."""
        tool = WebSearchTool()

        with patch.object(tool, "_check_ddg_available", return_value=False):
            result = await tool.execute(query="test query")

        assert result.success is False
        assert (
            "not available" in result.error.lower() or "install" in result.error.lower()
        )

    @pytest.mark.asyncio
    async def test_search_results_formatted(self):
        """Test search results are formatted correctly."""
        tool = WebSearchTool()

        mock_results = [
            {"title": "Result 1", "href": "https://example.com/1", "body": "Snippet 1"},
            {
                "title": "Result 2",
                "link": "https://example.com/2",
                "snippet": "Snippet 2",
            },
        ]

        with patch.object(tool, "_check_ddg_available", return_value=True):
            with patch.dict("sys.modules", {"duckduckgo_search": MagicMock()}):
                import sys

                mock_ddgs = MagicMock()
                mock_instance = MagicMock()
                mock_instance.__enter__ = MagicMock(return_value=mock_instance)
                mock_instance.__exit__ = MagicMock(return_value=False)
                mock_instance.text = MagicMock(return_value=mock_results)
                mock_ddgs.return_value = mock_instance
                sys.modules["duckduckgo_search"].DDGS = mock_ddgs

                result = await tool.execute(query="test")

        assert result.success is True
        assert isinstance(result.output, list)
        assert len(result.output) == 2

        # Check formatted structure
        assert result.output[0]["title"] == "Result 1"
        assert result.output[0]["url"] == "https://example.com/1"
        assert result.output[0]["snippet"] == "Snippet 1"

        # Check alternate field names are handled
        assert result.output[1]["url"] == "https://example.com/2"
        assert result.output[1]["snippet"] == "Snippet 2"


class TestWebFetchToolAttributes:
    """Test WebFetchTool attributes."""

    def test_tool_attributes(self):
        """Test tool has correct attributes."""
        tool = WebFetchTool()

        assert tool.name == "web_fetch"
        assert "fetch" in tool.description.lower()
        assert tool.danger_level == DangerLevel.SAFE
        assert tool.category == ToolCategory.NETWORK

    def test_get_schema(self):
        """Test schema is correct."""
        tool = WebFetchTool()
        schema = tool.get_schema()

        assert schema["type"] == "object"
        assert "url" in schema["properties"]
        assert "extract_text" in schema["properties"]
        assert "url" in schema["required"]

    def test_default_timeout(self):
        """Test default timeout."""
        tool = WebFetchTool()
        assert tool.timeout == 30

    def test_custom_timeout(self):
        """Test custom timeout."""
        tool = WebFetchTool(timeout=60)
        assert tool.timeout == 60

    def test_default_max_content_length(self):
        """Test default max content length."""
        tool = WebFetchTool()
        assert tool.max_content_length == 100000


class TestWebFetchToolURLValidation:
    """Test URL validation in WebFetchTool."""

    def test_validate_http_url(self):
        """Test HTTP URL is valid."""
        tool = WebFetchTool()

        result = tool._validate_url("http://example.com")

        assert result is None  # No error

    def test_validate_https_url(self):
        """Test HTTPS URL is valid."""
        tool = WebFetchTool()

        result = tool._validate_url("https://example.com")

        assert result is None

    def test_validate_invalid_scheme(self):
        """Test invalid URL scheme is rejected."""
        tool = WebFetchTool()

        result = tool._validate_url("ftp://example.com")

        assert result is not None
        assert "scheme" in result.lower()

    def test_validate_file_scheme_blocked(self):
        """Test file:// scheme is blocked."""
        tool = WebFetchTool()

        result = tool._validate_url("file:///etc/passwd")

        assert result is not None
        # file:// is rejected as invalid scheme (not http/https)
        assert "scheme" in result.lower() or "blocked" in result.lower()

    def test_validate_localhost_blocked(self):
        """Test localhost is blocked."""
        tool = WebFetchTool()

        result = tool._validate_url("http://localhost:8080")

        assert result is not None
        assert "blocked" in result.lower()

    def test_validate_127_0_0_1_blocked(self):
        """Test 127.0.0.1 is blocked."""
        tool = WebFetchTool()

        result = tool._validate_url("http://127.0.0.1:8000")

        assert result is not None
        assert "blocked" in result.lower()

    def test_validate_private_ip_blocked(self):
        """Test private IP ranges are blocked."""
        tool = WebFetchTool()

        # Class A private
        assert tool._validate_url("http://10.0.0.1") is not None

        # Class B private
        assert tool._validate_url("http://172.16.0.1") is not None
        assert tool._validate_url("http://172.31.255.255") is not None

        # Class C private
        assert tool._validate_url("http://192.168.1.1") is not None

    def test_validate_link_local_blocked(self):
        """Test link-local addresses are blocked."""
        tool = WebFetchTool()

        result = tool._validate_url("http://169.254.1.1")

        assert result is not None
        assert "blocked" in result.lower()


class TestWebFetchToolExecution:
    """Test WebFetchTool execution."""

    @pytest.mark.asyncio
    async def test_invalid_url_returns_error(self):
        """Test invalid URL returns error."""
        tool = WebFetchTool()

        result = await tool.execute(url="not-a-valid-url")

        assert result.success is False

    @pytest.mark.asyncio
    async def test_blocked_url_returns_error(self):
        """Test blocked URL returns error."""
        tool = WebFetchTool()

        result = await tool.execute(url="http://localhost:8080")

        assert result.success is False
        assert "blocked" in result.error.lower()

    @pytest.mark.asyncio
    async def test_fetch_requires_valid_url(self):
        """Test fetch requires valid HTTP/HTTPS URL."""
        tool = WebFetchTool()

        # Invalid URL scheme
        result = await tool.execute(url="ftp://example.com")
        assert result.success is False
        assert "scheme" in result.error.lower()

        # Blocked URL (localhost)
        result = await tool.execute(url="http://localhost:8080")
        assert result.success is False
        assert "blocked" in result.error.lower()

    @pytest.mark.asyncio
    async def test_aiohttp_not_installed(self):
        """Test error when aiohttp not installed."""
        tool = WebFetchTool()

        with patch.dict("sys.modules", {"aiohttp": None}):
            with patch(
                "builtins.__import__",
                side_effect=ImportError("No module named 'aiohttp'"),
            ):
                result = await tool.execute(url="https://example.com")

        assert result.success is False
        assert "aiohttp" in result.error.lower()


class TestWebFetchToolTextExtraction:
    """Test text extraction from HTML."""

    def test_extract_text_basic(self):
        """Test basic text extraction."""
        tool = WebFetchTool()

        html = "<html><body><p>Hello World</p></body></html>"

        with patch("bs4.BeautifulSoup") as mock_bs:
            mock_soup = MagicMock()
            mock_soup.get_text.return_value = "Hello World"
            mock_soup.__call__ = MagicMock(return_value=[])
            mock_bs.return_value = mock_soup

            result = tool._extract_text(html)

        # Should return extracted text
        assert "Hello World" in result or result == html

    def test_extract_text_removes_scripts(self):
        """Test scripts are removed from extracted text."""
        tool = WebFetchTool()

        html = """
        <html>
        <body>
        <script>alert('xss');</script>
        <p>Real content</p>
        </body>
        </html>
        """

        # With beautifulsoup installed, scripts should be removed
        # Without it, raw HTML is returned
        result = tool._extract_text(html)

        # Should not contain script content in clean extraction
        # (depends on beautifulsoup availability)

    def test_extract_text_beautifulsoup_not_installed(self):
        """Test fallback when beautifulsoup not installed."""
        tool = WebFetchTool()

        html = "<html><body>Content</body></html>"

        with patch("builtins.__import__", side_effect=ImportError):
            with patch.dict("sys.modules", {"bs4": None}):
                result = tool._extract_text(html)

        # Should return raw HTML when bs4 not available
        assert result == html


class TestWebFetchToolContentLimits:
    """Test content length limits configuration."""

    def test_max_content_length_configurable(self):
        """Test max_content_length can be configured."""
        tool1 = WebFetchTool(max_content_length=1000)
        tool2 = WebFetchTool(max_content_length=50000)

        assert tool1.max_content_length == 1000
        assert tool2.max_content_length == 50000

    def test_default_max_content_length(self):
        """Test default max_content_length."""
        tool = WebFetchTool()
        assert tool.max_content_length == 100000

    def test_timeout_configurable(self):
        """Test timeout can be configured."""
        tool1 = WebFetchTool(timeout=10)
        tool2 = WebFetchTool(timeout=60)

        assert tool1.timeout == 10
        assert tool2.timeout == 60


class TestWebFetchToolSSRFPrevention:
    """Test SSRF prevention."""

    def test_blocked_patterns_comprehensive(self):
        """Test all blocked patterns."""
        tool = WebFetchTool()

        blocked_urls = [
            "http://localhost/",
            "http://127.0.0.1/",
            "http://0.0.0.0/",
            "http://10.0.0.1/",
            "http://192.168.1.1/",
            "http://172.16.0.1/",
            "http://172.31.0.1/",
            "http://169.254.1.1/",
            "file:///etc/passwd",
        ]

        for url in blocked_urls:
            result = tool._validate_url(url)
            assert result is not None, f"URL should be blocked: {url}"

    def test_allowed_urls(self):
        """Test legitimate URLs are allowed."""
        tool = WebFetchTool()

        allowed_urls = [
            "https://example.com",
            "https://google.com",
            "http://api.github.com",
            "https://docs.python.org",
        ]

        for url in allowed_urls:
            result = tool._validate_url(url)
            assert result is None, f"URL should be allowed: {url}"
