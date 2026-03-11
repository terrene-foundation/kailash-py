"""
Pagination helper functions for API Gateway.

Calculates offsets, total pages, and pagination metadata.
"""

import math
from typing import Dict


def calculate_offset(page: int, limit: int) -> int:
    """
    Convert page number to offset.

    Args:
        page: Page number (1-indexed)
        limit: Items per page

    Returns:
        Offset value

    Raises:
        ValueError: If page is less than 1

    Example:
        >>> calculate_offset(page=1, limit=10)
        0
        >>> calculate_offset(page=3, limit=10)
        20
    """
    if page < 1:
        raise ValueError("Parameter 'page' must be greater than or equal to 1")

    return (page - 1) * limit


def calculate_total_pages(total: int, limit: int) -> int:
    """
    Calculate total number of pages from total count.

    Args:
        total: Total number of items
        limit: Items per page

    Returns:
        Total number of pages

    Example:
        >>> calculate_total_pages(total=100, limit=10)
        10
        >>> calculate_total_pages(total=105, limit=10)
        11
        >>> calculate_total_pages(total=0, limit=10)
        0
    """
    if total == 0 or limit == 0:
        return 0

    return math.ceil(total / limit)


def get_pagination_metadata(total: int, page: int, limit: int) -> Dict:
    """
    Get pagination metadata including has_next and has_prev flags.

    Args:
        total: Total number of items
        page: Current page number (1-indexed)
        limit: Items per page

    Returns:
        Dictionary containing pagination metadata

    Example:
        >>> get_pagination_metadata(total=50, page=1, limit=10)
        {
            "total": 50,
            "page": 1,
            "limit": 10,
            "total_pages": 5,
            "has_next": True,
            "has_prev": False
        }
    """
    total_pages = calculate_total_pages(total, limit)

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }
