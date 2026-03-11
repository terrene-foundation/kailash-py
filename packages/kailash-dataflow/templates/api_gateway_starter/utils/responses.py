"""
Response formatting functions for API Gateway.

Provides standardized response formats for success, pagination, and resource creation.
"""

from typing import Any, Dict, List, Optional

from templates.api_gateway_starter.utils.pagination import get_pagination_metadata


def success_response(
    data: Any, message: str = "Success", metadata: Optional[Dict] = None
) -> Dict:
    """
    Format standard success response.

    Args:
        data: Response data (can be any type)
        message: Success message (default: "Success")
        metadata: Optional metadata dictionary

    Returns:
        Standardized success response dictionary

    Example:
        >>> success_response({"id": "user_123", "name": "Alice"})
        {
            "status": "success",
            "message": "Success",
            "data": {"id": "user_123", "name": "Alice"}
        }
    """
    response = {"status": "success", "message": message, "data": data}

    if metadata is not None:
        response["metadata"] = metadata

    return response


def paginated_response(
    data: List, total: int, page: int, limit: int, metadata: Optional[Dict] = None
) -> Dict:
    """
    Format paginated response with pagination metadata.

    Args:
        data: List of items for current page
        total: Total number of items across all pages
        page: Current page number (1-indexed)
        limit: Items per page
        metadata: Optional additional metadata

    Returns:
        Paginated response dictionary

    Example:
        >>> paginated_response([{"id": "user_1"}], total=50, page=1, limit=10)
        {
            "status": "success",
            "data": [{"id": "user_1"}],
            "pagination": {
                "total": 50,
                "page": 1,
                "limit": 10,
                "total_pages": 5,
                "has_next": True,
                "has_prev": False
            }
        }
    """
    pagination_metadata = get_pagination_metadata(total, page, limit)

    response = {"status": "success", "data": data, "pagination": pagination_metadata}

    if metadata is not None:
        response["metadata"] = metadata

    return response


def created_response(data: Any, resource_id: str) -> Dict:
    """
    Format 201 Created response.

    Args:
        data: Created resource data
        resource_id: ID of the created resource

    Returns:
        Created response dictionary

    Example:
        >>> created_response({"id": "user_123", "name": "Alice"}, "user_123")
        {
            "status": "success",
            "message": "Resource created successfully",
            "data": {"id": "user_123", "name": "Alice"},
            "resource_id": "user_123"
        }
    """
    return {
        "status": "success",
        "message": "Resource created successfully",
        "data": data,
        "resource_id": resource_id,
    }
