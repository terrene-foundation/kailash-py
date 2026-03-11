# Query Parameters

## Overview

Query parameters enable flexible data filtering, pagination, sorting, and search in REST APIs. Nexus custom endpoints provide full FastAPI query parameter support with automatic type validation, default values, and comprehensive error handling.

Query parameters appear in the URL after `?` and are separated by `&`:
```
GET /api/items?limit=20&offset=0&sort=created_at&filter=active
```

**When to use query parameters:**
- Pagination (limit, offset, page)
- Filtering and search (status, category, query)
- Sorting (sort_by, order)
- Optional configuration (include_deleted, expand)
- Multiple value selection (tags, categories)

**Query parameters vs Path parameters:**
- **Query parameters**: Optional, for filtering/configuration (`?limit=20`)
- **Path parameters**: Required, for resource identification (`/users/{user_id}`)

## Quick Start

```python
from nexus import Nexus

app = Nexus(api_port=8000)

@app.endpoint("/api/items", methods=["GET"])
async def list_items(
    limit: int = 20,        # Default value
    offset: int = 0,        # Default value
    filter: str = "all"     # Default value
):
    return {
        "items": list(range(offset, offset + limit)),
        "limit": limit,
        "offset": offset,
        "filter": filter
    }

app.run()
```

**Usage:**
```bash
# Use defaults
curl http://localhost:8000/api/items
# Returns: {"items": [0..19], "limit": 20, "offset": 0, "filter": "all"}

# Override parameters
curl "http://localhost:8000/api/items?limit=5&offset=10&filter=active"
# Returns: {"items": [10..14], "limit": 5, "offset": 10, "filter": "active"}
```

## Basic Examples

### Example 1: Simple Query Parameters

```python
from nexus import Nexus

app = Nexus(api_port=8000)

@app.endpoint("/api/search", methods=["GET"])
async def search(
    q: str,                    # Required (no default)
    limit: int = 10,           # Optional with default
    lang: str = "en"           # Optional with default
):
    """Search endpoint with query parameters.

    Args:
        q: Search query (required)
        limit: Number of results (default: 10)
        lang: Language code (default: "en")
    """
    return {
        "query": q,
        "limit": limit,
        "language": lang,
        "results": []
    }

app.run()
```

**Usage:**
```bash
# Valid - all parameters provided
curl "http://localhost:8000/api/search?q=nexus&limit=5&lang=es"

# Valid - only required parameter
curl "http://localhost:8000/api/search?q=nexus"

# Invalid - missing required parameter 'q' (422 error)
curl "http://localhost:8000/api/search?limit=10"
```

### Example 2: Type Validation

FastAPI automatically validates parameter types:

```python
from nexus import Nexus

app = Nexus(api_port=8000)

@app.endpoint("/api/products", methods=["GET"])
async def list_products(
    page: int = 1,              # Integer
    per_page: int = 20,         # Integer
    in_stock: bool = True,      # Boolean
    min_price: float = 0.0      # Float
):
    """List products with type-validated parameters."""
    return {
        "page": page,
        "per_page": per_page,
        "in_stock": in_stock,
        "min_price": min_price
    }

app.run()
```

**Usage:**
```bash
# Valid - correct types
curl "http://localhost:8000/api/products?page=2&per_page=50&in_stock=false&min_price=9.99"

# Invalid - wrong type for 'page' (422 error)
curl "http://localhost:8000/api/products?page=abc"

# Boolean conversion (FastAPI handles common formats)
curl "http://localhost:8000/api/products?in_stock=true"    # true
curl "http://localhost:8000/api/products?in_stock=1"       # true
curl "http://localhost:8000/api/products?in_stock=false"   # false
curl "http://localhost:8000/api/products?in_stock=0"       # false
```

### Example 3: Optional Parameters

```python
from nexus import Nexus
from typing import Optional

app = Nexus(api_port=8000)

@app.endpoint("/api/users", methods=["GET"])
async def list_users(
    name: Optional[str] = None,         # Optional, defaults to None
    email: Optional[str] = None,        # Optional, defaults to None
    role: Optional[str] = None,         # Optional, defaults to None
    limit: int = 50                      # Optional with numeric default
):
    """List users with optional filters."""
    filters = {}
    if name:
        filters["name"] = name
    if email:
        filters["email"] = email
    if role:
        filters["role"] = role

    return {
        "filters": filters,
        "limit": limit,
        "users": []
    }

app.run()
```

**Usage:**
```bash
# No filters
curl "http://localhost:8000/api/users"
# Returns: {"filters": {}, "limit": 50, "users": []}

# With some filters
curl "http://localhost:8000/api/users?name=John&role=admin"
# Returns: {"filters": {"name": "John", "role": "admin"}, "limit": 50, "users": []}

# All filters
curl "http://localhost:8000/api/users?name=John&email=john@example.com&role=admin&limit=10"
```

## Advanced Query Parameter Features

### Example 1: Using FastAPI Query for Validation

```python
from nexus import Nexus
from fastapi import Query

app = Nexus(api_port=8000)

@app.endpoint("/api/items", methods=["GET"])
async def list_items(
    limit: int = Query(20, gt=0, le=100, description="Number of results (1-100)"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    sort_by: str = Query("created_at", pattern="^(created_at|updated_at|name)$"),
    search: str = Query("", min_length=0, max_length=100)
):
    """List items with advanced query parameter validation.

    Args:
        limit: Number of items (1-100)
        offset: Pagination offset (>= 0)
        sort_by: Sort field (created_at, updated_at, or name)
        search: Search query (max 100 chars)
    """
    return {
        "items": [],
        "limit": limit,
        "offset": offset,
        "sort_by": sort_by,
        "search": search
    }

app.run()
```

**Query Validation Parameters:**
- `gt`: Greater than
- `ge`: Greater than or equal
- `lt`: Less than
- `le`: Less than or equal
- `min_length`: Minimum string length
- `max_length`: Maximum string length
- `regex`: Regular expression pattern
- `description`: Parameter description (OpenAPI docs)

**Usage:**
```bash
# Valid
curl "http://localhost:8000/api/items?limit=50&sort_by=name"

# Invalid - limit exceeds max (422 error)
curl "http://localhost:8000/api/items?limit=150"

# Invalid - sort_by doesn't match regex (422 error)
curl "http://localhost:8000/api/items?sort_by=price"
```

### Example 2: Multiple Values (List Parameters)

```python
from nexus import Nexus
from fastapi import Query
from typing import List

app = Nexus(api_port=8000)

@app.endpoint("/api/articles", methods=["GET"])
async def list_articles(
    tags: List[str] = Query([]),                    # Empty list default
    categories: List[str] = Query([]),              # Empty list default
    authors: List[int] = Query([])                  # Integer list
):
    """Filter articles by multiple tags, categories, and authors.

    Usage:
        /api/articles?tags=python&tags=api&categories=tech&authors=1&authors=2
    """
    return {
        "tags": tags,
        "categories": categories,
        "authors": authors,
        "articles": []
    }

app.run()
```

**Usage:**
```bash
# Multiple tags
curl "http://localhost:8000/api/articles?tags=python&tags=api&tags=nexus"
# Returns: {"tags": ["python", "api", "nexus"], ...}

# Multiple categories and authors
curl "http://localhost:8000/api/articles?categories=tech&categories=ai&authors=1&authors=2"

# No values (empty lists)
curl "http://localhost:8000/api/articles"
# Returns: {"tags": [], "categories": [], "authors": [], ...}
```

### Example 3: Enum Validation

```python
from nexus import Nexus
from enum import Enum

app = Nexus(api_port=8000)

class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"

class Status(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"

@app.endpoint("/api/posts", methods=["GET"])
async def list_posts(
    status: Status = Status.ACTIVE,         # Enum with default
    order: SortOrder = SortOrder.DESC       # Enum with default
):
    """List posts with enum-validated parameters."""
    return {
        "status": status,
        "order": order,
        "posts": []
    }

app.run()
```

**Usage:**
```bash
# Valid enum values
curl "http://localhost:8000/api/posts?status=active&order=asc"
curl "http://localhost:8000/api/posts?status=archived&order=desc"

# Invalid enum value (422 error)
curl "http://localhost:8000/api/posts?status=invalid"
```

### Example 4: Combining Path and Query Parameters

```python
from nexus import Nexus
from fastapi import Query, Path
from typing import Optional

app = Nexus(api_port=8000)

@app.endpoint("/api/users/{user_id}/posts", methods=["GET"])
async def get_user_posts(
    user_id: str = Path(..., min_length=3, max_length=50),    # Path parameter
    limit: int = Query(10, gt=0, le=100),                      # Query parameter
    offset: int = Query(0, ge=0),                              # Query parameter
    published: Optional[bool] = Query(None)                    # Query parameter
):
    """Get posts for a specific user with pagination and filtering.

    Path parameter:
        user_id: User identifier (3-50 chars)

    Query parameters:
        limit: Number of posts (1-100)
        offset: Pagination offset
        published: Filter by publication status (optional)
    """
    filters = {"user_id": user_id}
    if published is not None:
        filters["published"] = published

    return {
        "filters": filters,
        "limit": limit,
        "offset": offset,
        "posts": []
    }

app.run()
```

**Usage:**
```bash
# Path param + query params
curl "http://localhost:8000/api/users/u123/posts?limit=20&offset=0"

# Path param + all query params
curl "http://localhost:8000/api/users/u123/posts?limit=5&offset=10&published=true"

# Only path param (query params use defaults)
curl "http://localhost:8000/api/users/u123/posts"
```

## Complete Working Example: Pagination & Search API

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
from fastapi import Query, HTTPException
from typing import Optional, List
from enum import Enum
from datetime import datetime

app = Nexus(
    api_port=8000,
    enable_auth=False,
    enable_monitoring=False
)

# Enum for sort fields
class SortField(str, Enum):
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    TITLE = "title"
    POPULARITY = "popularity"

class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"

class Status(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"

# Mock database (use real database in production)
mock_articles = [
    {
        "id": i,
        "title": f"Article {i}",
        "content": f"Content for article {i}",
        "author": f"author{i % 5}",
        "status": ["draft", "published", "archived"][i % 3],
        "tags": ["python", "api", "nexus"][:i % 3 + 1],
        "category": ["tech", "ai", "tutorial"][i % 3],
        "created_at": datetime.utcnow().isoformat(),
        "popularity": i * 10
    }
    for i in range(1, 101)
]

# === ARTICLE LISTING WITH ADVANCED FILTERING ===

@app.endpoint("/api/articles", methods=["GET"], rate_limit=100)
async def list_articles(
    # Pagination
    page: int = Query(1, ge=1, le=1000, description="Page number"),
    per_page: int = Query(20, gt=0, le=100, description="Items per page"),

    # Search
    search: Optional[str] = Query(None, min_length=1, max_length=200, description="Search query"),

    # Filtering
    status: Optional[Status] = Query(None, description="Filter by status"),
    author: Optional[str] = Query(None, min_length=3, max_length=50, description="Filter by author"),
    category: Optional[str] = Query(None, description="Filter by category"),
    tags: List[str] = Query([], description="Filter by tags (multiple allowed)"),

    # Sorting
    sort_by: SortField = Query(SortField.CREATED_AT, description="Sort field"),
    order: SortOrder = Query(SortOrder.DESC, description="Sort order"),

    # Options
    include_content: bool = Query(False, description="Include full content")
):
    """List articles with comprehensive filtering, pagination, and search.

    Query Parameters:
        - page: Page number (1-1000)
        - per_page: Items per page (1-100)
        - search: Search in title and content
        - status: Filter by status (draft, published, archived)
        - author: Filter by author username
        - category: Filter by category
        - tags: Filter by tags (can specify multiple)
        - sort_by: Sort field (created_at, updated_at, title, popularity)
        - order: Sort order (asc, desc)
        - include_content: Include full article content

    Returns:
        Paginated list of articles with metadata
    """
    # Filter articles
    filtered = mock_articles.copy()

    # Apply filters
    if search:
        search_lower = search.lower()
        filtered = [
            a for a in filtered
            if search_lower in a["title"].lower() or search_lower in a["content"].lower()
        ]

    if status:
        filtered = [a for a in filtered if a["status"] == status]

    if author:
        filtered = [a for a in filtered if a["author"] == author]

    if category:
        filtered = [a for a in filtered if a["category"] == category]

    if tags:
        filtered = [
            a for a in filtered
            if all(tag in a["tags"] for tag in tags)
        ]

    # Sort
    reverse = (order == SortOrder.DESC)
    if sort_by == SortField.CREATED_AT:
        filtered.sort(key=lambda x: x["created_at"], reverse=reverse)
    elif sort_by == SortField.TITLE:
        filtered.sort(key=lambda x: x["title"], reverse=reverse)
    elif sort_by == SortField.POPULARITY:
        filtered.sort(key=lambda x: x["popularity"], reverse=reverse)

    # Pagination
    total = len(filtered)
    offset = (page - 1) * per_page
    paginated = filtered[offset:offset + per_page]

    # Remove content if not requested
    if not include_content:
        for article in paginated:
            article.pop("content", None)

    # Calculate pagination metadata
    total_pages = (total + per_page - 1) // per_page
    has_next = page < total_pages
    has_prev = page > 1

    return {
        "articles": paginated,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "has_next": has_next,
            "has_prev": has_prev
        },
        "filters": {
            "search": search,
            "status": status,
            "author": author,
            "category": category,
            "tags": tags,
            "sort_by": sort_by,
            "order": order
        }
    }

# === ARTICLE SEARCH WITH AUTOCOMPLETE ===

@app.endpoint("/api/articles/search/autocomplete", methods=["GET"], rate_limit=50)
async def autocomplete(
    q: str = Query(..., min_length=1, max_length=100, description="Search query"),
    limit: int = Query(10, gt=0, le=50, description="Max suggestions")
):
    """Autocomplete endpoint for article search."""
    q_lower = q.lower()

    suggestions = [
        a["title"] for a in mock_articles
        if q_lower in a["title"].lower()
    ][:limit]

    return {
        "query": q,
        "suggestions": suggestions,
        "count": len(suggestions)
    }

# === FILTER OPTIONS ENDPOINT ===

@app.endpoint("/api/articles/filters", methods=["GET"], rate_limit=100)
async def get_filter_options():
    """Get available filter options for articles."""
    authors = list(set(a["author"] for a in mock_articles))
    categories = list(set(a["category"] for a in mock_articles))
    all_tags = set()
    for article in mock_articles:
        all_tags.update(article["tags"])

    return {
        "status": [s.value for s in Status],
        "authors": sorted(authors),
        "categories": sorted(categories),
        "tags": sorted(list(all_tags)),
        "sort_fields": [f.value for f in SortField],
        "sort_orders": [o.value for o in SortOrder]
    }

# === ARTICLE STATISTICS ===

@app.endpoint("/api/articles/stats", methods=["GET"], rate_limit=50)
async def get_statistics(
    status: Optional[Status] = Query(None),
    author: Optional[str] = Query(None),
    category: Optional[str] = Query(None)
):
    """Get article statistics with optional filtering."""
    filtered = mock_articles.copy()

    if status:
        filtered = [a for a in filtered if a["status"] == status]
    if author:
        filtered = [a for a in filtered if a["author"] == author]
    if category:
        filtered = [a for a in filtered if a["category"] == category]

    total = len(filtered)
    by_status = {}
    for s in Status:
        by_status[s.value] = len([a for a in filtered if a["status"] == s.value])

    return {
        "total": total,
        "by_status": by_status,
        "filters": {
            "status": status,
            "author": author,
            "category": category
        }
    }

if __name__ == "__main__":
    print("Starting Articles API with advanced query parameters...")
    print("API Documentation: http://localhost:8000/docs")
    print()
    print("Example queries:")
    print("  - List all: http://localhost:8000/api/articles")
    print("  - Search: http://localhost:8000/api/articles?search=Article&page=1&per_page=10")
    print("  - Filter: http://localhost:8000/api/articles?status=published&category=tech")
    print("  - Sort: http://localhost:8000/api/articles?sort_by=popularity&order=desc")
    print("  - Tags: http://localhost:8000/api/articles?tags=python&tags=api")
    print("  - Autocomplete: http://localhost:8000/api/articles/search/autocomplete?q=Art")
    print()
    app.run()
```

**API Usage Examples:**

```bash
# 1. Basic pagination
curl "http://localhost:8000/api/articles?page=1&per_page=10"

# 2. Search articles
curl "http://localhost:8000/api/articles?search=python&page=1"

# 3. Filter by status
curl "http://localhost:8000/api/articles?status=published"

# 4. Filter by multiple tags
curl "http://localhost:8000/api/articles?tags=python&tags=api"

# 5. Sort by popularity
curl "http://localhost:8000/api/articles?sort_by=popularity&order=desc"

# 6. Complex query (search + filter + sort + paginate)
curl "http://localhost:8000/api/articles?search=tutorial&status=published&category=tech&tags=python&sort_by=created_at&order=desc&page=1&per_page=20&include_content=true"

# 7. Autocomplete suggestions
curl "http://localhost:8000/api/articles/search/autocomplete?q=Art&limit=5"

# 8. Get filter options
curl "http://localhost:8000/api/articles/filters"

# 9. Get statistics
curl "http://localhost:8000/api/articles/stats?status=published"
```

## API Design Best Practices

### 1. Use Consistent Naming

```python
# Good - consistent snake_case
@app.endpoint("/api/items", methods=["GET"])
async def list_items(
    per_page: int = 20,
    sort_by: str = "created_at"
):
    pass

# Avoid - mixed naming conventions
@app.endpoint("/api/items", methods=["GET"])
async def list_items(
    perPage: int = 20,      # camelCase
    sort_by: str = "created_at"  # snake_case
):
    pass
```

### 2. Provide Sensible Defaults

```python
# Good - reasonable defaults
@app.endpoint("/api/items", methods=["GET"])
async def list_items(
    page: int = 1,          # Start at page 1
    per_page: int = 20,     # Reasonable page size
    sort_by: str = "created_at",  # Default sort
    order: str = "desc"     # Recent first
):
    pass
```

### 3. Validate Ranges

```python
from fastapi import Query

@app.endpoint("/api/items", methods=["GET"])
async def list_items(
    page: int = Query(1, ge=1, le=10000),          # Prevent excessive pages
    per_page: int = Query(20, gt=0, le=100),       # Limit page size
    search: str = Query("", max_length=200)         # Prevent long queries
):
    pass
```

### 4. Document Parameters

```python
from fastapi import Query

@app.endpoint("/api/items", methods=["GET"])
async def list_items(
    limit: int = Query(
        20,
        gt=0,
        le=100,
        description="Number of items to return (1-100)"
    ),
    offset: int = Query(
        0,
        ge=0,
        description="Number of items to skip for pagination"
    )
):
    """List items with pagination.

    Query Parameters:
        limit: Maximum number of items to return
        offset: Number of items to skip (for pagination)

    Returns:
        Paginated list of items
    """
    pass
```

### 5. Return Pagination Metadata

```python
@app.endpoint("/api/items", methods=["GET"])
async def list_items(page: int = 1, per_page: int = 20):
    total = 100  # Total items
    total_pages = (total + per_page - 1) // per_page

    return {
        "items": [...],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1
        }
    }
```

### 6. Use Enums for Fixed Values

```python
from enum import Enum

class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"

@app.endpoint("/api/items", methods=["GET"])
async def list_items(order: SortOrder = SortOrder.ASC):
    # FastAPI validates that 'order' is either "asc" or "desc"
    pass
```

### 7. Handle Optional Filters Gracefully

```python
from typing import Optional

@app.endpoint("/api/items", methods=["GET"])
async def list_items(
    category: Optional[str] = None,
    status: Optional[str] = None
):
    filters = {}

    if category:
        filters["category"] = category
    if status:
        filters["status"] = status

    # Only filter if parameters provided
    return {"filters": filters, "items": []}
```

## Production Considerations

### 1. Performance Optimization

```python
# Use database query optimization
@app.endpoint("/api/items", methods=["GET"])
async def list_items(
    limit: int = Query(20, le=100),
    offset: int = Query(0)
):
    # Good - database handles pagination
    # items = db.query(Item).limit(limit).offset(offset).all()

    # Bad - loading all items then slicing
    # all_items = db.query(Item).all()
    # items = all_items[offset:offset + limit]

    pass
```

### 2. Rate Limiting by Complexity

```python
# Lower limits for expensive operations
@app.endpoint("/api/search", methods=["GET"], rate_limit=10)
async def search(q: str, limit: int = 10):
    # Complex search operation
    pass

# Higher limits for simple operations
@app.endpoint("/api/items", methods=["GET"], rate_limit=100)
async def list_items(limit: int = 20):
    # Simple pagination
    pass
```

### 3. Input Sanitization

```python
@app.endpoint("/api/search", methods=["GET"])
async def search(
    q: str = Query(..., max_length=200, pattern="^[a-zA-Z0-9 ]+$")
):
    # Only allow alphanumeric and spaces
    # Prevents injection attacks
    pass
```

### 4. Response Caching

```python
from fastapi import Header
from typing import Optional

@app.endpoint("/api/items", methods=["GET"])
async def list_items(
    page: int = 1,
    per_page: int = 20,
    if_none_match: Optional[str] = Header(None)
):
    # Generate ETag for response
    etag = f'"{page}-{per_page}-{get_last_modified()}"'

    # Check if cached
    if if_none_match == etag:
        from fastapi import Response
        return Response(status_code=304)  # Not Modified

    items = get_items(page, per_page)

    return Response(
        content=json.dumps({"items": items}),
        headers={"ETag": etag, "Cache-Control": "max-age=60"}
    )
```

## Troubleshooting

### Error: Validation error (422) for query parameter

**Problem:** Query parameter type doesn't match expected type.

**Solution:**
```python
# Ensure correct type in URL
# Good: ?page=1
# Bad: ?page=abc

# Or make parameter optional
page: Optional[int] = None
```

### Error: Missing required query parameter

**Problem:** Required parameter not provided.

**Solution:**
```python
# Add default value to make optional
limit: int = 20  # Now optional

# Or make explicit that it's required
limit: int = Query(...)  # Required, no default
```

### Error: Query parameter exceeds maximum length

**Problem:** String parameter too long.

**Solution:**
```python
# Set appropriate max_length
search: str = Query(..., max_length=200)

# Client should truncate or show error
if len(query) > 200:
    query = query[:200]
```

### Issue: Boolean parameter not working as expected

**Problem:** Boolean conversion confusion.

**Solution:**
```python
# FastAPI boolean conversion:
# - "true", "True", "1", "on", "yes" → True
# - "false", "False", "0", "off", "no" → False

# Use consistent format in clients
curl "http://localhost:8000/api/items?active=true"
```

### Issue: List parameter only returns last value

**Problem:** Not using proper list type hint.

**Solution:**
```python
from typing import List
from fastapi import Query

# Good - returns list
tags: List[str] = Query([])

# Bad - returns only last value
tags: str = None
```

## Next Steps

- **Custom Endpoints Guide**: Create endpoints with path parameters and workflow integration
- **SSE Streaming Guide**: Add real-time streaming to query-based endpoints
- **Authentication Guide**: Secure query-based APIs with authentication
- **Performance Guide**: Optimize query-heavy endpoints for production

## Related Documentation

- [Custom Endpoints Guide](./custom_endpoints.md)
- [SSE Streaming Guide](./sse_streaming.md)
- [Security Guide](./security-guide.md)
- [FastAPI Query Parameters](https://fastapi.tiangolo.com/tutorial/query-params/)
