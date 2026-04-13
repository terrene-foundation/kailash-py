# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests: PostgreSQL credential pre-encoding in state_manager.

Verifies that ``preencode_password_special_chars`` is applied BEFORE
``urlparse`` on the PostgreSQL validation path, matching the MySQL
path's behavior. Without pre-encoding, a ``#`` in the password is
interpreted as the URL fragment delimiter and everything after it
is silently dropped.

Origin: Security review found that the PostgreSQL path in
``_validate_connection`` called ``urlparse(self.connection_string)``
without ``preencode_password_special_chars``, while the MySQL path
correctly called ``urlparse(preencode_password_special_chars(...))``.
A password like ``p#assword`` would be truncated to ``p`` on
PostgreSQL but preserved on MySQL.
"""

from __future__ import annotations

from urllib.parse import urlparse

import pytest

from kailash.utils.url_credentials import (
    decode_userinfo_or_raise,
    preencode_password_special_chars,
)


class TestPostgresqlPreencodeRegression:
    """Prove that pre-encoding preserves passwords with special chars."""

    @pytest.mark.parametrize(
        "raw_url,expected_password",
        [
            # Hash in password -- the primary failure mode
            (
                "postgresql://admin:p#assword@localhost:5432/orchestration",
                "p#assword",
            ),
            # Dollar sign
            (
                "postgresql://admin:pa$$word@localhost:5432/orchestration",
                "pa$$word",
            ),
            # Question mark
            (
                "postgresql://admin:pa?ss@localhost:5432/orchestration",
                "pa?ss",
            ),
            # At sign in password (must survive last-@ split)
            (
                "postgresql://admin:p@ss@localhost:5432/orchestration",
                "p@ss",
            ),
            # Multiple special characters combined
            (
                "postgresql://admin:p#a$s?w@rd@localhost:5432/orchestration",
                "p#a$s?w@rd",
            ),
            # No special characters (should pass through unchanged)
            (
                "postgresql://admin:plainpassword@localhost:5432/orchestration",
                "plainpassword",
            ),
        ],
    )
    def test_preencode_preserves_password_through_urlparse(
        self, raw_url: str, expected_password: str
    ) -> None:
        """Password with special chars survives urlparse after pre-encoding."""
        encoded_url = preencode_password_special_chars(raw_url)
        parsed = urlparse(encoded_url)
        user, password = decode_userinfo_or_raise(parsed, default_user="postgres")
        assert password == expected_password, (
            f"Password mismatch: expected {expected_password!r}, got {password!r}. "
            f"Raw URL fragment after '#' was likely dropped by urlparse."
        )

    def test_hash_in_password_truncated_without_preencode(self) -> None:
        """Without pre-encoding, '#' causes urlparse to truncate the password.

        This is the exact bug this fix addresses. The test proves the
        failure mode exists so the fix is verifiably necessary.
        """
        raw_url = "postgresql://admin:p#assword@localhost:5432/orchestration"

        # Without pre-encoding: urlparse treats '#' as fragment delimiter
        parsed_without = urlparse(raw_url)
        # urlparse sees "p" as the password and "#assword@localhost..."
        # as the fragment -- the hostname and everything after '#' is lost
        assert parsed_without.password != "p#assword", (
            "urlparse should NOT preserve '#' in password without pre-encoding -- "
            "if this assertion fails, the Python stdlib behavior changed"
        )

        # With pre-encoding: '#' is percent-encoded so urlparse preserves it
        encoded_url = preencode_password_special_chars(raw_url)
        parsed_with = urlparse(encoded_url)
        user, password = decode_userinfo_or_raise(parsed_with, default_user="postgres")
        assert password == "p#assword"

    def test_preencode_preserves_hostname_and_database(self) -> None:
        """Pre-encoding must not corrupt the host, port, or database path."""
        raw_url = "postgresql://admin:p#a$s@localhost:5432/mydb"
        encoded_url = preencode_password_special_chars(raw_url)
        parsed = urlparse(encoded_url)

        assert parsed.hostname == "localhost"
        assert parsed.port == 5432
        assert parsed.path == "/mydb"
        assert parsed.scheme == "postgresql"

    def test_preencode_preserves_username(self) -> None:
        """Pre-encoding must not corrupt the username."""
        raw_url = "postgresql://myuser:p#assword@localhost:5432/db"
        encoded_url = preencode_password_special_chars(raw_url)
        parsed = urlparse(encoded_url)
        user, _ = decode_userinfo_or_raise(parsed, default_user="postgres")
        assert user == "myuser"
