"""
Unit tests for pagination helper functions.

Tests offset calculation, total pages calculation, and pagination metadata.
"""

from typing import Dict

import pytest


@pytest.mark.unit
class TestPaginationHelpers:
    """Test pagination helper functions."""

    def test_calculate_offset_first_page(self):
        """Test offset calculation for first page."""
        from templates.api_gateway_starter.utils.pagination import calculate_offset

        offset = calculate_offset(page=1, limit=10)

        assert offset == 0

    def test_calculate_offset_second_page(self):
        """Test offset calculation for second page."""
        from templates.api_gateway_starter.utils.pagination import calculate_offset

        offset = calculate_offset(page=2, limit=10)

        assert offset == 10

    def test_calculate_offset_negative_page(self):
        """Test offset calculation with negative page (should raise error)."""
        from templates.api_gateway_starter.utils.pagination import calculate_offset

        with pytest.raises(ValueError) as exc_info:
            calculate_offset(page=0, limit=10)

        assert "page" in str(exc_info.value).lower()

    def test_calculate_total_pages_exact(self):
        """Test total pages calculation with exact division."""
        from templates.api_gateway_starter.utils.pagination import calculate_total_pages

        total_pages = calculate_total_pages(total=100, limit=10)

        assert total_pages == 10

    def test_calculate_total_pages_partial(self):
        """Test total pages calculation with partial last page."""
        from templates.api_gateway_starter.utils.pagination import calculate_total_pages

        total_pages = calculate_total_pages(total=105, limit=10)

        # 105 items / 10 per page = 10 full pages + 1 partial = 11 total
        assert total_pages == 11

    def test_calculate_total_pages_zero_items(self):
        """Test total pages calculation with zero items."""
        from templates.api_gateway_starter.utils.pagination import calculate_total_pages

        total_pages = calculate_total_pages(total=0, limit=10)

        assert total_pages == 0

    def test_get_pagination_metadata_first_page(self):
        """Test pagination metadata for first page."""
        from templates.api_gateway_starter.utils.pagination import (
            get_pagination_metadata,
        )

        metadata = get_pagination_metadata(total=50, page=1, limit=10)

        assert metadata["total"] == 50
        assert metadata["page"] == 1
        assert metadata["limit"] == 10
        assert metadata["total_pages"] == 5
        assert metadata["has_next"] is True
        assert metadata["has_prev"] is False

    def test_get_pagination_metadata_last_page(self):
        """Test pagination metadata for last page."""
        from templates.api_gateway_starter.utils.pagination import (
            get_pagination_metadata,
        )

        metadata = get_pagination_metadata(total=50, page=5, limit=10)

        assert metadata["page"] == 5
        assert metadata["total_pages"] == 5
        assert metadata["has_next"] is False
        assert metadata["has_prev"] is True

    def test_get_pagination_metadata_middle_page(self):
        """Test pagination metadata for middle page."""
        from templates.api_gateway_starter.utils.pagination import (
            get_pagination_metadata,
        )

        metadata = get_pagination_metadata(total=100, page=5, limit=10)

        assert metadata["page"] == 5
        assert metadata["total_pages"] == 10
        assert metadata["has_next"] is True
        assert metadata["has_prev"] is True

    def test_get_pagination_metadata_single_page(self):
        """Test pagination metadata for single page (total < limit)."""
        from templates.api_gateway_starter.utils.pagination import (
            get_pagination_metadata,
        )

        metadata = get_pagination_metadata(total=5, page=1, limit=10)

        assert metadata["total"] == 5
        assert metadata["page"] == 1
        assert metadata["total_pages"] == 1
        assert metadata["has_next"] is False
        assert metadata["has_prev"] is False
