"""Regression: #353 — PostgreSQLAdapter.get_connection_parameters ignores sslmode.

Prior to 2.0, `sslmode=disable` in the URL had no effect because
get_connection_parameters() did not include the ssl parameter.
"""

import pytest


@pytest.mark.regression
class TestPostgreSQLSSLMode:
    """Verify sslmode from URL reaches asyncpg connection parameters."""

    def _make_adapter(self, url: str):
        from dataflow.adapters.postgresql import PostgreSQLAdapter

        return PostgreSQLAdapter(url)

    def test_sslmode_disable_sets_ssl_false(self):
        """sslmode=disable must set ssl=False in connection params."""
        adapter = self._make_adapter(
            "postgresql://user:pass@localhost:5432/db?sslmode=disable"
        )
        params = adapter.get_connection_parameters()
        assert params["ssl"] is False

    def test_sslmode_require_sets_ssl_true(self):
        """sslmode=require must set ssl=True in connection params."""
        adapter = self._make_adapter(
            "postgresql://user:pass@localhost:5432/db?sslmode=require"
        )
        params = adapter.get_connection_parameters()
        assert params["ssl"] is True

    def test_sslmode_prefer_omits_ssl(self):
        """sslmode=prefer (default) must NOT set ssl key — let asyncpg negotiate."""
        adapter = self._make_adapter(
            "postgresql://user:pass@localhost:5432/db?sslmode=prefer"
        )
        params = adapter.get_connection_parameters()
        assert "ssl" not in params

    def test_sslmode_default_omits_ssl(self):
        """No sslmode in URL defaults to prefer — ssl key absent."""
        adapter = self._make_adapter("postgresql://user:pass@localhost:5432/db")
        params = adapter.get_connection_parameters()
        assert "ssl" not in params

    def test_sslmode_verify_ca_sets_ssl_context(self):
        """sslmode=verify-ca must set ssl to an SSLContext."""
        import ssl

        adapter = self._make_adapter(
            "postgresql://user:pass@localhost:5432/db?sslmode=verify-ca"
        )
        params = adapter.get_connection_parameters()
        assert isinstance(params["ssl"], ssl.SSLContext)
        assert params["ssl"].check_hostname is False

    def test_sslmode_verify_full_sets_ssl_context_with_hostname_check(self):
        """sslmode=verify-full must set ssl to an SSLContext with check_hostname."""
        import ssl

        adapter = self._make_adapter(
            "postgresql://user:pass@localhost:5432/db?sslmode=verify-full"
        )
        params = adapter.get_connection_parameters()
        assert isinstance(params["ssl"], ssl.SSLContext)
        assert params["ssl"].check_hostname is True

    def test_application_name_forwarded(self):
        """application_name must be forwarded as server_settings."""
        adapter = self._make_adapter("postgresql://user:pass@localhost:5432/db")
        params = adapter.get_connection_parameters()
        assert params["server_settings"]["application_name"] == "dataflow"

    def test_custom_application_name(self):
        """Custom application_name via kwargs must override default."""
        from dataflow.adapters.postgresql import PostgreSQLAdapter

        adapter = PostgreSQLAdapter(
            "postgresql://user:pass@localhost:5432/db",
            application_name="my-app",
        )
        params = adapter.get_connection_parameters()
        assert params["server_settings"]["application_name"] == "my-app"
