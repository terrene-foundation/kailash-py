# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for pool startup validation (PY-4)."""

from __future__ import annotations

from unittest.mock import patch

import pytest


class TestValidatePoolConfig:
    """Test startup pool configuration validation."""

    def test_skips_for_sqlite(self):
        from dataflow.core.pool_validator import validate_pool_config

        result = validate_pool_config(
            "sqlite:///test.db", pool_size=50, max_overflow=10
        )
        assert result["status"] == "skipped"

    def test_skips_for_none_url(self):
        from dataflow.core.pool_validator import validate_pool_config

        result = validate_pool_config(None, pool_size=50, max_overflow=10)
        assert result["status"] == "skipped"

    @patch("dataflow.core.pool_validator.probe_max_connections", return_value=100)
    @patch("dataflow.core.pool_validator.detect_worker_count", return_value=4)
    def test_error_when_pool_exceeds_max(self, mock_workers, mock_probe):
        from dataflow.core.pool_validator import validate_pool_config

        result = validate_pool_config(
            "postgresql://localhost/db", pool_size=50, max_overflow=10
        )
        assert result["status"] == "error"
        assert result["total_possible"] == 240  # (50+10)*4
        assert result["db_max"] == 100
        assert "WILL EXHAUST" in result["message"]
        assert "Remediation" in result["message"]

    @patch("dataflow.core.pool_validator.probe_max_connections", return_value=100)
    @patch("dataflow.core.pool_validator.detect_worker_count", return_value=1)
    def test_warning_when_near_limit(self, mock_workers, mock_probe):
        from dataflow.core.pool_validator import validate_pool_config

        # 75 out of 100 = 75%, above the 70% safe threshold
        result = validate_pool_config(
            "postgresql://localhost/db", pool_size=60, max_overflow=15
        )
        assert result["status"] == "warning"
        assert result["total_possible"] == 75
        assert "NEAR LIMIT" in result["message"]

    @patch("dataflow.core.pool_validator.probe_max_connections", return_value=200)
    @patch("dataflow.core.pool_validator.detect_worker_count", return_value=2)
    def test_safe_when_within_limit(self, mock_workers, mock_probe):
        from dataflow.core.pool_validator import validate_pool_config

        result = validate_pool_config(
            "postgresql://localhost/db", pool_size=10, max_overflow=5
        )
        assert result["status"] == "safe"
        assert result["total_possible"] == 30  # (10+5)*2
        assert result["db_max"] == 200
        assert "validated" in result["message"]

    @patch("dataflow.core.pool_validator.probe_max_connections", return_value=None)
    @patch("dataflow.core.pool_validator.detect_worker_count", return_value=1)
    def test_warning_when_probe_fails(self, mock_workers, mock_probe):
        from dataflow.core.pool_validator import validate_pool_config

        result = validate_pool_config(
            "postgresql://localhost/db", pool_size=10, max_overflow=5
        )
        assert result["status"] == "warning"
        assert result["db_max"] is None
        assert "probe failed" in result["message"]

    @patch("dataflow.core.pool_validator.probe_max_connections", return_value=100)
    @patch("dataflow.core.pool_validator.detect_worker_count", return_value=4)
    def test_remediation_suggests_correct_pool_size(self, mock_workers, mock_probe):
        from dataflow.core.pool_validator import validate_pool_config

        result = validate_pool_config(
            "postgresql://localhost/db", pool_size=50, max_overflow=10
        )
        # Suggested: max(2, int(100 * 0.7) // (4 * 3 // 2)) = max(2, 70 // 6) = 11
        assert "DATAFLOW_POOL_SIZE=11" in result["message"]
