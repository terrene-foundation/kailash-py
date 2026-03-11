"""
Native Search Tools

Provides web search and URL fetching capabilities for autonomous agents.

Tools:
- WebSearchTool: Search the web using DuckDuckGo
- WebFetchTool: Fetch and extract content from URLs
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from kaizen.tools.native.base import BaseTool, NativeToolResult
from kaizen.tools.types import DangerLevel, ToolCategory

logger = logging.getLogger(__name__)


class WebSearchTool(BaseTool):
    """
    Search the web using DuckDuckGo.

    Returns search results with titles, URLs, and snippets.
    Uses duckduckgo-search library if available, otherwise returns an error.

    Parameters:
        query: Search query
        num_results: Number of results to return (default: 5, max: 10)
    """

    name = "web_search"
    description = "Search the web for information using DuckDuckGo"
    danger_level = DangerLevel.SAFE
    category = ToolCategory.NETWORK

    def __init__(self, search_provider: str = "duckduckgo"):
        """
        Initialize WebSearchTool.

        Args:
            search_provider: Search provider to use (currently only "duckduckgo")
        """
        super().__init__()
        self.search_provider = search_provider
        self._ddg_available = None

    def _check_ddg_available(self) -> bool:
        """Check if duckduckgo-search is available."""
        if self._ddg_available is None:
            try:
                from duckduckgo_search import DDGS

                self._ddg_available = True
            except ImportError:
                self._ddg_available = False
                logger.warning(
                    "duckduckgo-search not installed. Install with: pip install duckduckgo-search"
                )
        return self._ddg_available

    async def execute(
        self,
        query: str,
        num_results: int = 5,
    ) -> NativeToolResult:
        """
        Search the web.

        Args:
            query: Search query
            num_results: Number of results (max: 10)

        Returns:
            List of search results with title, url, snippet
        """
        if not query or not query.strip():
            return NativeToolResult.from_error("Search query cannot be empty")

        num_results = min(max(1, num_results), 10)

        if self.search_provider == "duckduckgo":
            return await self._search_duckduckgo(query, num_results)
        else:
            return NativeToolResult.from_error(
                f"Unknown search provider: {self.search_provider}"
            )

    async def _search_duckduckgo(
        self, query: str, num_results: int
    ) -> NativeToolResult:
        """Search using DuckDuckGo."""
        if not self._check_ddg_available():
            return NativeToolResult.from_error(
                "DuckDuckGo search not available. Install duckduckgo-search: pip install duckduckgo-search"
            )

        try:
            from duckduckgo_search import DDGS

            # Run in thread pool since DDGS is synchronous
            def do_search():
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=num_results))
                return results

            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(None, do_search)

            # Format results
            formatted = []
            for r in results:
                formatted.append(
                    {
                        "title": r.get("title", ""),
                        "url": r.get("href", r.get("link", "")),
                        "snippet": r.get("body", r.get("snippet", "")),
                    }
                )

            return NativeToolResult.from_success(
                formatted,
                query=query,
                num_results=len(formatted),
                provider="duckduckgo",
            )
        except Exception as e:
            logger.error(f"DuckDuckGo search failed: {e}")
            return NativeToolResult.from_error(f"Search failed: {str(e)}")

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query",
                },
                "num_results": {
                    "type": "integer",
                    "description": "Number of results to return (max: 10)",
                    "default": 5,
                },
            },
            "required": ["query"],
        }


class WebFetchTool(BaseTool):
    """
    Fetch content from a URL.

    Retrieves web page content and optionally extracts text from HTML.
    Uses aiohttp for async HTTP requests.

    Parameters:
        url: URL to fetch
        extract_text: If True, extract text from HTML (default: True)
    """

    name = "web_fetch"
    description = "Fetch and extract content from a URL"
    danger_level = DangerLevel.SAFE
    category = ToolCategory.NETWORK

    # URLs that should be blocked for security
    BLOCKED_URL_PATTERNS = [
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "169.254.",  # Link-local
        "10.",  # Private Class A
        "192.168.",  # Private Class C
        "172.16.",  # Private Class B start
        "172.17.",
        "172.18.",
        "172.19.",
        "172.20.",
        "172.21.",
        "172.22.",
        "172.23.",
        "172.24.",
        "172.25.",
        "172.26.",
        "172.27.",
        "172.28.",
        "172.29.",
        "172.30.",
        "172.31.",
        "file://",
    ]

    def __init__(self, timeout: int = 30, max_content_length: int = 100000):
        """
        Initialize WebFetchTool.

        Args:
            timeout: Request timeout in seconds
            max_content_length: Maximum content length to fetch
        """
        super().__init__()
        self.timeout = timeout
        self.max_content_length = max_content_length

    def _validate_url(self, url: str) -> Optional[str]:
        """
        Validate URL for safety.

        Returns:
            Error message if URL is invalid/unsafe, None if valid
        """
        # Check scheme
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return f"Invalid URL scheme: {parsed.scheme}. Only http/https allowed."

        # Check for blocked patterns
        url_lower = url.lower()
        for pattern in self.BLOCKED_URL_PATTERNS:
            if pattern in url_lower:
                return f"URL contains blocked pattern: {pattern}"

        return None

    async def execute(
        self,
        url: str,
        extract_text: bool = True,
    ) -> NativeToolResult:
        """
        Fetch content from URL.

        Args:
            url: URL to fetch
            extract_text: Extract text from HTML (default: True)

        Returns:
            Page content (text or HTML)
        """
        # Validate URL
        error = self._validate_url(url)
        if error:
            return NativeToolResult.from_error(error)

        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                    allow_redirects=True,
                    max_redirects=5,
                ) as response:
                    # Check content length
                    content_length = response.headers.get("Content-Length")
                    if content_length and int(content_length) > self.max_content_length:
                        return NativeToolResult.from_error(
                            f"Content too large: {content_length} bytes (max: {self.max_content_length})"
                        )

                    # Read content
                    content = await response.text()

                    # Truncate if needed
                    truncated = len(content) > self.max_content_length
                    if truncated:
                        content = content[: self.max_content_length]

                    # Extract text if requested
                    if extract_text:
                        content = self._extract_text(content)

                    return NativeToolResult.from_success(
                        content,
                        url=str(response.url),
                        status_code=response.status,
                        content_type=response.headers.get("Content-Type", ""),
                        truncated=truncated,
                    )

        except ImportError:
            return NativeToolResult.from_error(
                "aiohttp not installed. Install with: pip install aiohttp"
            )
        except asyncio.TimeoutError:
            return NativeToolResult.from_error(
                f"Request timed out after {self.timeout} seconds"
            )
        except Exception as e:
            return NativeToolResult.from_error(f"Fetch failed: {str(e)}")

    def _extract_text(self, html: str) -> str:
        """Extract text content from HTML."""
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")

            # Remove script and style elements
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()

            # Get text
            text = soup.get_text(separator="\n", strip=True)

            # Clean up whitespace
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            return "\n".join(lines)

        except ImportError:
            logger.warning(
                "beautifulsoup4 not installed, returning raw HTML. "
                "Install with: pip install beautifulsoup4"
            )
            return html
        except Exception as e:
            logger.warning(f"Text extraction failed: {e}, returning raw content")
            return html

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to fetch (http/https only)",
                },
                "extract_text": {
                    "type": "boolean",
                    "description": "Extract text from HTML, removing scripts and styles",
                    "default": True,
                },
            },
            "required": ["url"],
        }
