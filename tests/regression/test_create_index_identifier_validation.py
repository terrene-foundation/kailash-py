# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests: create_index() rejects SQL-injection payloads.

SEC-01: identifier validation added to ConnectionManager.create_index()
so that injection payloads like 'users"; DROP TABLE x; --' are rejected
before the SQL string is formed.
"""

import pytest

from kailash.db.dialect import _validate_identifier


@pytest.mark.regression
def test_validate_identifier_rejects_injection_payload():
    with pytest.raises(ValueError):
        _validate_identifier('users"; DROP TABLE x; --')


@pytest.mark.regression
def test_validate_identifier_rejects_name_with_data():
    with pytest.raises(ValueError):
        _validate_identifier("name WITH DATA")


@pytest.mark.regression
def test_validate_identifier_rejects_digit_start():
    with pytest.raises(ValueError):
        _validate_identifier("123_starts_with_digit")


@pytest.mark.regression
def test_validate_identifier_rejects_space():
    with pytest.raises(ValueError):
        _validate_identifier("invalid name")


@pytest.mark.regression
def test_validate_identifier_rejects_semicolon():
    with pytest.raises(ValueError):
        _validate_identifier("idx; DROP TABLE users; --")


@pytest.mark.regression
def test_validate_identifier_accepts_valid_index_name():
    # Should not raise
    _validate_identifier("idx_users_active")


@pytest.mark.regression
def test_validate_identifier_accepts_simple_table_name():
    # Should not raise
    _validate_identifier("users")


@pytest.mark.regression
def test_validate_identifier_accepts_column_name():
    # Should not raise
    _validate_identifier("created_at")


@pytest.mark.regression
def test_validate_identifier_accepts_underscore_prefix():
    # Should not raise
    _validate_identifier("_internal")
