"""
Request validation functions for API Gateway.

Validates CREATE, UPDATE, LIST requests and pagination parameters.
"""

from typing import Dict, Tuple


def validate_create_request(model_name: str, data: Dict) -> Dict:
    """
    Validate CREATE request for DataFlow model.

    Args:
        model_name: Name of the DataFlow model
        data: Request data containing fields to create

    Returns:
        Validated data dictionary

    Raises:
        ValueError: If validation fails

    Example:
        >>> validate_create_request("User", {"id": "user_123", "name": "Alice"})
        {"id": "user_123", "name": "Alice"}
    """
    if not data:
        raise ValueError("Request data cannot be empty")

    if "id" not in data:
        raise ValueError("Field 'id' is required for CREATE operations")

    return data


def validate_update_request(model_name: str, data: Dict) -> Dict:
    """
    Validate UPDATE request for DataFlow model.

    Args:
        model_name: Name of the DataFlow model
        data: Request data containing filter and fields to update

    Returns:
        Validated data dictionary

    Raises:
        ValueError: If validation fails

    Example:
        >>> validate_update_request("User", {
        ...     "filter": {"id": "user_123"},
        ...     "fields": {"name": "Alice Updated"}
        ... })
        {"filter": {"id": "user_123"}, "fields": {"name": "Alice Updated"}}
    """
    if not data:
        raise ValueError("Request data cannot be empty")

    if "filter" not in data:
        raise ValueError("Field 'filter' is required for UPDATE operations")

    if "fields" not in data:
        raise ValueError("Field 'fields' is required for UPDATE operations")

    return data


def validate_list_request(params: Dict) -> Dict:
    """
    Validate LIST request parameters.

    Args:
        params: Request parameters (filters, limit, offset)

    Returns:
        Validated parameters dictionary

    Raises:
        ValueError: If validation fails

    Example:
        >>> validate_list_request({"limit": 10, "offset": 0})
        {"limit": 10, "offset": 0}
    """
    if params.get("limit") is not None:
        if params["limit"] < 0:
            raise ValueError("Parameter 'limit' must be a positive integer or zero")

    if params.get("offset") is not None:
        if params["offset"] < 0:
            raise ValueError("Parameter 'offset' must be a positive integer or zero")

    return params


def validate_pagination_params(
    page: int, limit: int, max_limit: int = 100
) -> Tuple[int, int]:
    """
    Validate and convert page/limit to offset/limit.

    Args:
        page: Page number (1-indexed)
        limit: Items per page
        max_limit: Maximum allowed limit (default: 100)

    Returns:
        Tuple of (offset, limit)

    Raises:
        ValueError: If validation fails

    Example:
        >>> validate_pagination_params(page=1, limit=20)
        (0, 20)
        >>> validate_pagination_params(page=2, limit=20)
        (20, 20)
    """
    if page < 1:
        raise ValueError("Parameter 'page' must be greater than or equal to 1")

    if limit < 0:
        raise ValueError("Parameter 'limit' must be a positive integer or zero")

    # Cap limit at max_limit
    if limit > max_limit:
        limit = max_limit

    # Convert page to offset
    offset = (page - 1) * limit

    return offset, limit
