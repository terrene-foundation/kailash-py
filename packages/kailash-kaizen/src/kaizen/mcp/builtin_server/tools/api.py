"""
API Tools for MCP - HTTP Request Operations

Provides 4 MCP tools for HTTP operations:
- http_get: Make HTTP GET request
- http_post: Make HTTP POST request
- http_put: Make HTTP PUT request
- http_delete: Make HTTP DELETE request

Security Features:
- URL validation (SSRF protection - blocks localhost, private IPs)
- Timeout validation (1-300 seconds)
- Response size limiting (10MB max, prevents DoS)
- Allowed schemes only (http, https)

All tools preserve security validations from original implementations.
All tools use @tool decorator for MCP compliance.
"""

import ipaddress
import json
from typing import Any, Dict, Optional, Tuple
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse

from kaizen.mcp.builtin_server.decorators import mcp_tool

# Security constants (from original implementation)
MAX_RESPONSE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_TIMEOUT = 300  # 5 minutes
MIN_TIMEOUT = 1  # 1 second
ALLOWED_SCHEMES = {"http", "https"}


def validate_url(url: str) -> Tuple[bool, Optional[str]]:
    """
    Validate URL for security (SSRF protection).

    Validates that:
    1. URL uses http or https scheme only
    2. URL does not target localhost or private IP addresses

    Args:
        url: URL to validate

    Returns:
        Tuple of (is_valid, error_message)

    Note: This function is copied from kaizen/tools/builtin/api.py
    """
    if not url:
        return False, "URL cannot be empty"

    try:
        parsed = urlparse(url)

        # Check scheme
        if parsed.scheme not in ALLOWED_SCHEMES:
            return False, f"URL scheme must be http or https, got: {parsed.scheme}"

        # Check hostname exists
        if not parsed.hostname:
            return False, "URL must have a valid hostname"

        hostname = parsed.hostname.lower()

        # Check for localhost
        if hostname in ("localhost", "127.0.0.1", "::1"):
            return False, "Access to localhost is not allowed (SSRF protection)"

        # Check for private IP addresses
        try:
            ip = ipaddress.ip_address(hostname)

            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
                return (
                    False,
                    f"Access to private/internal IP addresses is not allowed (SSRF protection): {hostname}",
                )

        except ValueError:
            # Not an IP address, it's a domain name - that's fine
            pass

        return True, None

    except Exception as e:
        return False, f"Invalid URL: {str(e)}"


def validate_timeout(timeout: int) -> Tuple[bool, Optional[str]]:
    """
    Validate timeout is within safe range.

    Args:
        timeout: Timeout value in seconds

    Returns:
        Tuple of (is_valid, error_message)
    """
    if timeout < MIN_TIMEOUT:
        return False, f"Timeout must be at least {MIN_TIMEOUT} second(s)"

    if timeout > MAX_TIMEOUT:
        return False, f"Timeout must not exceed {MAX_TIMEOUT} seconds"

    return True, None


def read_response_with_limit(
    response, max_size: int = MAX_RESPONSE_SIZE
) -> Tuple[str, bool]:
    """
    Read HTTP response with size limit to prevent DoS.

    Args:
        response: HTTP response object from urllib
        max_size: Maximum bytes to read (default 10MB)

    Returns:
        Tuple of (body, was_truncated)
    """
    chunks = []
    total_size = 0
    was_truncated = False

    # Read in 8KB chunks
    chunk_size = 8192

    while True:
        chunk = response.read(chunk_size)
        if not chunk:
            break

        total_size += len(chunk)

        if total_size > max_size:
            # Truncate to max_size
            excess = total_size - max_size
            chunk = chunk[:-excess]
            chunks.append(chunk)
            was_truncated = True
            break

        chunks.append(chunk)

    body = b"".join(chunks).decode("utf-8", errors="replace")
    return body, was_truncated


def _make_http_request(
    method: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 30,
    data: Optional[Any] = None,
) -> dict:
    """
    Internal helper for making HTTP requests with shared validation and error handling.

    Args:
        method: HTTP method (GET, POST, PUT, DELETE)
        url: URL to request
        headers: HTTP headers (optional)
        timeout: Request timeout in seconds (default 30)
        data: Request body data for POST/PUT (optional)

    Returns:
        Dictionary with:
            - status_code (int): HTTP status code
            - body (str): Response body
            - headers (dict): Response headers
            - success (bool): True if status code is 2xx
            - error (str, optional): Error message if request failed
            - warning (str, optional): Warning if response was truncated
    """
    headers = headers or {}

    # Security validation: URL
    is_valid, error = validate_url(url)
    if not is_valid:
        return {
            "status_code": 0,
            "body": "",
            "headers": {},
            "success": False,
            "error": f"URL validation failed: {error}",
        }

    # Security validation: timeout
    is_valid, error = validate_timeout(timeout)
    if not is_valid:
        return {
            "status_code": 0,
            "body": "",
            "headers": {},
            "success": False,
            "error": f"Timeout validation failed: {error}",
        }

    try:
        # Prepare request data (for POST/PUT)
        data_bytes = None
        if data is not None:
            if isinstance(data, dict):
                # Default to JSON if dict
                if "Content-Type" not in headers:
                    headers["Content-Type"] = "application/json"
                data_bytes = json.dumps(data).encode("utf-8")
            else:
                data_bytes = data.encode("utf-8") if isinstance(data, str) else data

        # Create and execute request
        req = urllib_request.Request(
            url, data=data_bytes, headers=headers, method=method
        )
        with urllib_request.urlopen(req, timeout=timeout) as response:
            # Security: Read response with size limit
            body, was_truncated = read_response_with_limit(response)
            status_code = response.status
            response_headers = dict(response.headers)

            result = {
                "status_code": status_code,
                "body": body,
                "headers": response_headers,
                "success": 200 <= status_code < 300,
            }

            # Warn if response was truncated
            if was_truncated:
                result["warning"] = (
                    f"Response exceeded {MAX_RESPONSE_SIZE} bytes and was truncated"
                )

            return result

    except HTTPError as e:
        return {
            "status_code": e.code,
            "body": e.read().decode("utf-8") if e.fp else "",
            "headers": dict(e.headers) if e.headers else {},
            "success": False,
            "error": str(e),
        }

    except URLError as e:
        return {
            "status_code": 0,
            "body": "",
            "headers": {},
            "success": False,
            "error": str(e.reason),
        }

    except Exception as e:
        return {
            "status_code": 0,
            "body": "",
            "headers": {},
            "success": False,
            "error": str(e),
        }


# =============================================================================
# MCP Tools (4 total)
# =============================================================================


@mcp_tool(
    name="http_get",
    description="Make an HTTP GET request",
    parameters={
        "url": {"type": "string", "description": "URL to request"},
        "headers": {"type": "object", "description": "HTTP headers"},
        "timeout": {
            "type": "integer",
            "description": "Request timeout in seconds (default 30)",
        },
    },
)
async def http_get(
    url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 30
) -> dict:
    """
    Make an HTTP GET request (MCP tool implementation).

    Args:
        url: URL to request
        headers: HTTP headers (optional)
        timeout: Request timeout in seconds (default 30)

    Returns:
        Dictionary with:
            - status_code (int): HTTP status code
            - body (str): Response body
            - headers (dict): Response headers
            - success (bool): True if status code is 2xx
            - error (str, optional): Error message if failed
            - warning (str, optional): Warning if response was truncated

    Security:
        - URL validation (SSRF protection)
        - Timeout validation (1-300 seconds)
        - Response size limiting (10MB max)
    """
    return _make_http_request(method="GET", url=url, headers=headers, timeout=timeout)


@mcp_tool(
    name="http_post",
    description="Make an HTTP POST request",
    parameters={
        "url": {"type": "string", "description": "URL to request"},
        "data": {
            "type": ["object", "string"],
            "description": "POST data (dict or string)",
        },
        "headers": {"type": "object", "description": "HTTP headers"},
        "timeout": {
            "type": "integer",
            "description": "Request timeout in seconds (default 30)",
        },
    },
)
async def http_post(
    url: str,
    data: Optional[Any] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 30,
) -> dict:
    """
    Make an HTTP POST request (MCP tool implementation).

    Args:
        url: URL to request
        data: POST data (dict or string)
        headers: HTTP headers (optional)
        timeout: Request timeout in seconds (default 30)

    Returns:
        Dictionary with:
            - status_code (int): HTTP status code
            - body (str): Response body
            - headers (dict): Response headers
            - success (bool): True if status code is 2xx
            - error (str, optional): Error message if failed
            - warning (str, optional): Warning if response was truncated

    Security:
        - URL validation (SSRF protection)
        - Timeout validation (1-300 seconds)
        - Response size limiting (10MB max)
    """
    return _make_http_request(
        method="POST", url=url, headers=headers, timeout=timeout, data=data
    )


@mcp_tool(
    name="http_put",
    description="Make an HTTP PUT request",
    parameters={
        "url": {"type": "string", "description": "URL to request"},
        "data": {
            "type": ["object", "string"],
            "description": "PUT data (dict or string)",
        },
        "headers": {"type": "object", "description": "HTTP headers"},
        "timeout": {
            "type": "integer",
            "description": "Request timeout in seconds (default 30)",
        },
    },
)
async def http_put(
    url: str,
    data: Optional[Any] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 30,
) -> dict:
    """
    Make an HTTP PUT request (MCP tool implementation).

    Args:
        url: URL to request
        data: PUT data (dict or string)
        headers: HTTP headers (optional)
        timeout: Request timeout in seconds (default 30)

    Returns:
        Dictionary with:
            - status_code (int): HTTP status code
            - body (str): Response body
            - headers (dict): Response headers
            - success (bool): True if status code is 2xx
            - error (str, optional): Error message if failed
            - warning (str, optional): Warning if response was truncated

    Security:
        - URL validation (SSRF protection)
        - Timeout validation (1-300 seconds)
        - Response size limiting (10MB max)
    """
    return _make_http_request(
        method="PUT", url=url, headers=headers, timeout=timeout, data=data
    )


@mcp_tool(
    name="http_delete",
    description="Make an HTTP DELETE request",
    parameters={
        "url": {"type": "string", "description": "URL to request"},
        "headers": {"type": "object", "description": "HTTP headers"},
        "timeout": {
            "type": "integer",
            "description": "Request timeout in seconds (default 30)",
        },
    },
)
async def http_delete(
    url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 30
) -> dict:
    """
    Make an HTTP DELETE request (MCP tool implementation).

    Args:
        url: URL to request
        headers: HTTP headers (optional)
        timeout: Request timeout in seconds (default 30)

    Returns:
        Dictionary with:
            - status_code (int): HTTP status code
            - body (str): Response body
            - headers (dict): Response headers
            - success (bool): True if status code is 2xx
            - error (str, optional): Error message if failed
            - warning (str, optional): Warning if response was truncated

    Security:
        - URL validation (SSRF protection)
        - Timeout validation (1-300 seconds)
        - Response size limiting (10MB max)
    """
    return _make_http_request(
        method="DELETE", url=url, headers=headers, timeout=timeout
    )
