"""
HTTP/API Security Validation for Kaizen Built-in Tools

Provides security validation functions for HTTP-related operations:
- URL validation with scheme enforcement (http/https only)
- SSRF protection (blocks localhost, private IPs, link-local addresses)
- Timeout validation (1-300 seconds range)

Usage:
    >>> from kaizen.tools.builtin.api import validate_url, validate_timeout

    # URL validation
    >>> is_valid, error = validate_url("https://example.com")
    >>> assert is_valid is True

    >>> is_valid, error = validate_url("http://127.0.0.1")
    >>> assert is_valid is False  # SSRF protection

    # Timeout validation
    >>> is_valid, error = validate_timeout(30)
    >>> assert is_valid is True

    >>> is_valid, error = validate_timeout(500)
    >>> assert is_valid is False  # Exceeds 300 seconds
"""

import ipaddress
from typing import Optional, Tuple
from urllib.parse import urlparse


def validate_url(url: str) -> Tuple[bool, Optional[str]]:
    """
    Validate URL for scheme and SSRF protection.

    Validates that:
    1. URL is not empty
    2. URL scheme is http or https only
    3. URL does not target localhost or private IP addresses (SSRF protection)

    Args:
        url: The URL string to validate

    Returns:
        Tuple of (is_valid, error_message):
        - (True, None) if valid
        - (False, error_message) if invalid

    Examples:
        >>> validate_url("https://example.com")
        (True, None)

        >>> validate_url("ftp://example.com")
        (False, 'Invalid URL scheme: ftp. Scheme must be http or https')

        >>> validate_url("http://127.0.0.1")
        (False, 'Localhost URLs are not allowed (SSRF protection)')

        >>> validate_url("http://192.168.1.1")
        (False, 'Private/internal IP addresses are not allowed (SSRF protection)')
    """
    # Check for empty URL
    if not url:
        return False, "URL cannot be empty"

    # Parse the URL
    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"Invalid URL format: {e}"

    # Validate scheme (http/https only)
    if parsed.scheme not in ("http", "https"):
        if not parsed.scheme:
            return False, "URL must have a scheme. Scheme must be http or https"
        return (
            False,
            f"Invalid URL scheme: {parsed.scheme}. Scheme must be http or https",
        )

    # Get hostname for SSRF protection
    hostname = parsed.hostname
    if not hostname:
        return False, "URL must have a hostname"

    # Block localhost by name
    hostname_lower = hostname.lower()
    if hostname_lower in ("localhost", "127.0.0.1", "::1"):
        return False, "Localhost URLs are not allowed (SSRF protection)"

    # Handle bracketed IPv6 (e.g., [::1])
    clean_hostname = hostname.strip("[]")

    # Check for IP addresses
    try:
        ip = ipaddress.ip_address(clean_hostname)

        # Block loopback addresses
        if ip.is_loopback:
            return False, "Localhost URLs are not allowed (SSRF protection)"

        # Block private addresses (10.x.x.x, 192.168.x.x, 172.16-31.x.x)
        if ip.is_private:
            return (
                False,
                "Private/internal IP addresses are not allowed (SSRF protection)",
            )

        # Block link-local addresses (169.254.x.x, fe80::/10)
        if ip.is_link_local:
            return (
                False,
                "Private/internal IP addresses are not allowed (SSRF protection)",
            )

        # Block multicast and reserved addresses
        if ip.is_multicast or ip.is_reserved:
            return (
                False,
                "Private/internal IP addresses are not allowed (SSRF protection)",
            )

    except ValueError:
        # Not an IP address, hostname is fine
        pass

    return True, None


def validate_timeout(timeout: int) -> Tuple[bool, Optional[str]]:
    """
    Validate timeout value is within acceptable range.

    Validates that timeout is between 1 and 300 seconds (inclusive).
    This prevents:
    - Zero or negative timeouts (invalid)
    - Excessively long timeouts (resource exhaustion)

    Args:
        timeout: The timeout value in seconds

    Returns:
        Tuple of (is_valid, error_message):
        - (True, None) if valid
        - (False, error_message) if invalid

    Examples:
        >>> validate_timeout(30)
        (True, None)

        >>> validate_timeout(0)
        (False, 'Timeout must be at least 1 second')

        >>> validate_timeout(301)
        (False, 'Timeout must not exceed 300 seconds')
    """
    if timeout < 1:
        return False, "Timeout must be at least 1 second"

    if timeout > 300:
        return False, "Timeout must not exceed 300 seconds"

    return True, None
