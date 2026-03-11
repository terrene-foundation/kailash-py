"""
Web Tools for MCP - Content Fetching and Parsing

Provides 2 MCP tools for web scraping:
- fetch_url: Fetch content from a URL
- extract_links: Extract links from HTML content

Security Features:
- User agent customization
- Timeout protection (default 30s)
- HTMLParser for robust link extraction (not regex)

All tools use @tool decorator for MCP compliance.
"""

from html.parser import HTMLParser
from typing import List, Optional
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin

from kaizen.mcp.builtin_server.decorators import mcp_tool


class LinkExtractor(HTMLParser):
    """
    HTML parser for extracting links from <a> tags.

    More robust than regex-based extraction:
    - Only extracts from actual <a href="..."> tags
    - Handles malformed HTML gracefully
    - Prevents extraction from scripts, comments, or attributes
    - Properly handles nested tags and edge cases
    """

    def __init__(self):
        super().__init__()
        self.links: List[str] = []
        self._in_script = False
        self._in_style = False

    def handle_starttag(self, tag: str, attrs: List[tuple]) -> None:
        """Handle start tags, extracting href from <a> tags."""
        # Track if we're inside script or style tags (don't extract from these)
        if tag == "script":
            self._in_script = True
        elif tag == "style":
            self._in_style = True

        # Only extract from <a> tags, not script/style
        if tag == "a" and not self._in_script and not self._in_style:
            for attr_name, attr_value in attrs:
                if attr_name.lower() == "href" and attr_value:
                    self.links.append(attr_value)

    def handle_endtag(self, tag: str) -> None:
        """Handle end tags to track context."""
        if tag == "script":
            self._in_script = False
        elif tag == "style":
            self._in_style = False


# =============================================================================
# MCP Tools (2 total)
# =============================================================================


@mcp_tool(
    name="fetch_url",
    description="Fetch content from a URL",
    parameters={
        "url": {"type": "string", "description": "URL to fetch"},
        "timeout": {
            "type": "integer",
            "description": "Request timeout in seconds (default 30)",
        },
        "user_agent": {"type": "string", "description": "User agent string"},
    },
)
async def fetch_url(
    url: str, timeout: int = 30, user_agent: Optional[str] = None
) -> dict:
    """
    Fetch content from a URL (MCP tool implementation).

    Args:
        url: URL to fetch
        timeout: Request timeout in seconds (default 30)
        user_agent: User agent string (optional)

    Returns:
        Dictionary with:
            - content (str): Page content
            - status_code (int): HTTP status code
            - content_type (str): Content type
            - size (int): Content size in bytes
            - success (bool): True if fetch succeeded
            - error (str, optional): Error message if failed
    """
    if user_agent is None:
        user_agent = "Kaizen-MCP/1.0 (compatible; bot)"

    try:
        headers = {"User-Agent": user_agent}
        req = urllib_request.Request(url, headers=headers)

        with urllib_request.urlopen(req, timeout=timeout) as response:
            content = response.read().decode("utf-8")
            status_code = response.status
            content_type = response.headers.get("Content-Type", "")
            size = len(content.encode("utf-8"))

            return {
                "content": content,
                "status_code": status_code,
                "content_type": content_type,
                "size": size,
                "success": True,
            }

    except HTTPError as e:
        return {
            "content": "",
            "status_code": e.code,
            "content_type": "",
            "size": 0,
            "success": False,
            "error": f"HTTP Error {e.code}: {e.reason}",
        }

    except URLError as e:
        return {
            "content": "",
            "status_code": 0,
            "content_type": "",
            "size": 0,
            "success": False,
            "error": str(e.reason),
        }

    except Exception as e:
        return {
            "content": "",
            "status_code": 0,
            "content_type": "",
            "size": 0,
            "success": False,
            "error": str(e),
        }


@mcp_tool(
    name="extract_links",
    description="Extract links from HTML content",
    parameters={
        "html": {"type": "string", "description": "HTML content to parse"},
        "base_url": {
            "type": "string",
            "description": "Base URL for resolving relative links",
        },
    },
)
async def extract_links(html: str, base_url: str = "") -> dict:
    """
    Extract links from HTML content using HTMLParser (MCP tool implementation).

    Uses html.parser.HTMLParser for robust link extraction:
    - Only extracts from actual <a href="..."> tags
    - Handles malformed HTML gracefully
    - Prevents extraction from scripts, comments, attributes
    - More reliable than regex-based parsing

    Args:
        html: HTML content to parse
        base_url: Base URL for resolving relative links (optional)

    Returns:
        Dictionary with:
            - links (list[str]): List of extracted links (in order found)
            - count (int): Number of links found
            - unique_count (int): Number of unique links
            - unique_links (list[str]): Sorted list of unique links
            - error (str, optional): Error message if parsing failed
    """
    try:
        # Use HTMLParser for robust link extraction
        parser = LinkExtractor()
        parser.feed(html)

        links = []
        for link in parser.links:
            # Skip empty links, anchors, and javascript
            if not link or link.startswith("#") or link.startswith("javascript:"):
                continue

            # Skip data URIs and mailto links
            if link.startswith(("data:", "mailto:")):
                continue

            # Convert relative to absolute if base_url provided
            if base_url:
                # urljoin handles all cases: absolute paths, relative paths, already absolute URLs
                link = urljoin(base_url, link)

            links.append(link)

        unique_links = list(set(links))

        return {
            "links": links,
            "count": len(links),
            "unique_count": len(unique_links),
            "unique_links": sorted(unique_links),
        }

    except Exception as e:
        return {
            "links": [],
            "count": 0,
            "unique_count": 0,
            "unique_links": [],
            "error": str(e),
        }
