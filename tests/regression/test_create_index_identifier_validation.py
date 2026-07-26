# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests: create_index() rejects SQL-injection payloads.

SEC-01: identifier validation added to ConnectionManager.create_index()
so that injection payloads like 'users"; DROP TABLE x; --' are rejected
before the SQL string is formed.
"""

import pytest

from kailash.db.dialect import (
    DIALECT_UNKNOWN_MAX_IDENTIFIER_LENGTH,
    _validate_identifier,
)


@pytest.mark.regression
def test_validate_identifier_rejects_injection_payload():
    with pytest.raises(ValueError):
        _validate_identifier(
            'users"; DROP TABLE x; --', max_length=DIALECT_UNKNOWN_MAX_IDENTIFIER_LENGTH
        )


@pytest.mark.regression
def test_validate_identifier_rejects_name_with_data():
    with pytest.raises(ValueError):
        _validate_identifier(
            "name WITH DATA", max_length=DIALECT_UNKNOWN_MAX_IDENTIFIER_LENGTH
        )


@pytest.mark.regression
def test_validate_identifier_rejects_digit_start():
    with pytest.raises(ValueError):
        _validate_identifier(
            "123_starts_with_digit", max_length=DIALECT_UNKNOWN_MAX_IDENTIFIER_LENGTH
        )


@pytest.mark.regression
def test_validate_identifier_rejects_space():
    with pytest.raises(ValueError):
        _validate_identifier(
            "invalid name", max_length=DIALECT_UNKNOWN_MAX_IDENTIFIER_LENGTH
        )


@pytest.mark.regression
def test_validate_identifier_rejects_semicolon():
    with pytest.raises(ValueError):
        _validate_identifier(
            "idx; DROP TABLE users; --",
            max_length=DIALECT_UNKNOWN_MAX_IDENTIFIER_LENGTH,
        )


@pytest.mark.regression
def test_validate_identifier_accepts_valid_index_name():
    # Should not raise
    _validate_identifier(
        "idx_users_active", max_length=DIALECT_UNKNOWN_MAX_IDENTIFIER_LENGTH
    )


@pytest.mark.regression
def test_validate_identifier_accepts_simple_table_name():
    # Should not raise
    _validate_identifier("users", max_length=DIALECT_UNKNOWN_MAX_IDENTIFIER_LENGTH)


@pytest.mark.regression
def test_validate_identifier_accepts_column_name():
    # Should not raise
    _validate_identifier("created_at", max_length=DIALECT_UNKNOWN_MAX_IDENTIFIER_LENGTH)


@pytest.mark.regression
def test_validate_identifier_accepts_underscore_prefix():
    # Should not raise
    _validate_identifier("_internal", max_length=DIALECT_UNKNOWN_MAX_IDENTIFIER_LENGTH)
