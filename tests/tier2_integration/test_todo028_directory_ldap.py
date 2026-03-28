"""Unit tests for TODO-028: Directory Integration real LDAP implementation."""

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kailash.nodes.auth.directory_integration import DirectoryIntegrationNode


# Create a fake ldap3 module so that patch("ldap3.X") works even when
# the real ldap3 package is not installed.
_mock_ldap3 = MagicMock()
_mock_ldap3.ALL_ATTRIBUTES = "*"


@pytest.fixture(autouse=True)
def _inject_ldap3_module():
    """Ensure ldap3 is patchable in sys.modules for every test."""
    prev = sys.modules.get("ldap3")
    sys.modules["ldap3"] = _mock_ldap3
    yield
    if prev is None:
        sys.modules.pop("ldap3", None)
    else:
        sys.modules["ldap3"] = prev


@pytest.fixture
def ldap_node():
    """Create a DirectoryIntegrationNode with LDAP configuration."""
    return DirectoryIntegrationNode(
        name="test_ldap",
        directory_type="ldap",
        connection_config={
            "server": "ldap://ldap.test.com:389",
            "bind_dn": "cn=admin,dc=test,dc=com",
            "bind_password": "admin_pass",
            "base_dn": "dc=test,dc=com",
            "user_base_dn": "ou=users,dc=test,dc=com",
            "group_base_dn": "ou=groups,dc=test,dc=com",
        },
    )


class TestLDAPFilterBuilding:
    def test_simple_filter(self, ldap_node):
        result = ldap_node._build_ldap_filter_string("person", {"uid": "jdoe"})
        assert "(objectClass=person)" in result
        assert "(uid=jdoe)" in result
        assert result.startswith("(&")

    def test_search_term_filter(self, ldap_node):
        result = ldap_node._build_ldap_filter_string("person", {"search_term": "john"})
        assert "(objectClass=person)" in result
        assert "(|(cn=*john*)(uid=*john*)(mail=*john*))" in result

    def test_escapes_special_chars(self, ldap_node):
        result = ldap_node._build_ldap_filter_string("person", {"uid": "test(user)"})
        assert "\\28" in result  # escaped (
        assert "\\29" in result  # escaped )

    def test_empty_filters(self, ldap_node):
        result = ldap_node._build_ldap_filter_string("group", {})
        assert result == "(objectClass=group)"

    def test_skips_internal_keys(self, ldap_node):
        result = ldap_node._build_ldap_filter_string(
            "person",
            {
                "objectClass": "person",
                "base_dn": "dc=test",
                "modified_since": "2024-01-01",
                "uid": "jdoe",
            },
        )
        assert "(uid=jdoe)" in result
        assert "modified_since" not in result
        assert "base_dn=" not in result


class TestFallbackDirectorySearch:
    def test_users_all(self, ldap_node):
        results = ldap_node._fallback_directory_search("users", {})
        assert len(results) == 4  # All built-in users

    def test_users_by_uid(self, ldap_node):
        results = ldap_node._fallback_directory_search("users", {"uid": "jdoe"})
        assert len(results) == 1
        assert results[0]["uid"] == "jdoe"

    def test_users_by_mail(self, ldap_node):
        results = ldap_node._fallback_directory_search(
            "users", {"mail": "john.doe@test.com"}
        )
        assert len(results) == 1

    def test_users_search_term(self, ldap_node):
        results = ldap_node._fallback_directory_search("users", {"search_term": "Jane"})
        assert len(results) == 2  # jsmith and jane.smith

    def test_groups(self, ldap_node):
        results = ldap_node._fallback_directory_search("groups", {})
        assert len(results) == 2
        assert results[0]["cn"] == "Engineers"


class TestFallbackDirectoryAuth:
    def test_valid_known_user(self, ldap_node):
        result = ldap_node._fallback_directory_auth("jdoe", "user_password")
        assert result["authenticated"] is True

    def test_invalid_password(self, ldap_node):
        result = ldap_node._fallback_directory_auth("jdoe", "wrong")
        assert result["authenticated"] is False
        assert result["reason"] == "invalid_credentials"

    def test_default_password(self, ldap_node):
        result = ldap_node._fallback_directory_auth("unknown_user", "password123")
        assert result["authenticated"] is True


class TestRealLDAPSearch:
    @pytest.mark.asyncio
    async def test_ldap_search_with_mock(self, ldap_node):
        """Test real LDAP search path with mocked ldap3."""
        mock_entry = MagicMock()
        mock_entry.entry_attributes = ["uid", "cn", "mail"]
        mock_entry.__getitem__ = lambda self, key: MagicMock(
            value={"uid": "testuser", "cn": "Test User", "mail": "test@test.com"}[key]
        )

        mock_conn = MagicMock()
        mock_conn.bind.return_value = True
        mock_conn.search.return_value = True
        mock_conn.entries = [mock_entry]
        mock_conn.unbind.return_value = None

        with (
            patch("ldap3.Server") as mock_server,
            patch("ldap3.Connection", return_value=mock_conn),
        ):
            results = await ldap_node._ldap_directory_search(
                "users", {"uid": "testuser"}
            )

        assert len(results) == 1
        assert results[0]["uid"] == "testuser"

    @pytest.mark.asyncio
    async def test_ldap_search_falls_back_on_import_error(self, ldap_node):
        """Falls back to built-in data when ldap3 is not installed."""
        with patch.object(
            ldap_node,
            "_ldap_directory_search",
            side_effect=ImportError("No ldap3"),
        ):
            results = await ldap_node._simulate_directory_search(
                "users", {"uid": "jdoe"}
            )

        assert len(results) == 1
        assert results[0]["uid"] == "jdoe"


class TestRealLDAPAuth:
    @pytest.mark.asyncio
    async def test_ldap_auth_success(self, ldap_node):
        """Test real LDAP bind authentication with mock."""
        mock_conn = MagicMock()
        mock_conn.bind.return_value = True
        mock_conn.unbind.return_value = None

        with patch("ldap3.Server"), patch("ldap3.Connection", return_value=mock_conn):
            result = await ldap_node._ldap_directory_auth("admin", "correct_pass")

        assert result["authenticated"] is True

    @pytest.mark.asyncio
    async def test_ldap_auth_failure(self, ldap_node):
        mock_conn = MagicMock()
        mock_conn.bind.return_value = False
        mock_conn.unbind.return_value = None

        with patch("ldap3.Server"), patch("ldap3.Connection", return_value=mock_conn):
            result = await ldap_node._ldap_directory_auth("admin", "wrong_pass")

        assert result["authenticated"] is False

    @pytest.mark.asyncio
    async def test_ldap_auth_falls_back(self, ldap_node):
        """Falls back to built-in auth when ldap3 is unavailable."""
        with patch.object(
            ldap_node,
            "_ldap_directory_auth",
            side_effect=ImportError("No ldap3"),
        ):
            result = await ldap_node._simulate_directory_auth("jdoe", "user_password")

        assert result["authenticated"] is True


class TestLDAPConnectionPool:
    @pytest.mark.asyncio
    async def test_multiple_servers_pool(self, ldap_node):
        """When multiple servers are configured, uses ServerPool."""
        ldap_node.connection_config["servers"] = [
            "ldap://server1:389",
            "ldap://server2:389",
        ]

        mock_conn = MagicMock()
        mock_conn.entries = []
        mock_conn.unbind.return_value = None

        with (
            patch("ldap3.Server") as mock_server_cls,
            patch("ldap3.ServerPool") as mock_pool_cls,
            patch("ldap3.Connection", return_value=mock_conn),
        ):
            await ldap_node._ldap_directory_search("users", {})
            mock_pool_cls.assert_called_once()


class TestTLSSupport:
    @pytest.mark.asyncio
    async def test_ldaps_enables_tls(self, ldap_node):
        """LDAPS URL should create a TLS configuration."""
        ldap_node.connection_config["server"] = "ldaps://secure.ldap.test:636"

        mock_conn = MagicMock()
        mock_conn.entries = []
        mock_conn.unbind.return_value = None

        with (
            patch("ldap3.Server") as mock_server_cls,
            patch("ldap3.Tls") as mock_tls_cls,
            patch("ldap3.Connection", return_value=mock_conn),
        ):
            await ldap_node._ldap_directory_search("users", {})
            mock_tls_cls.assert_called_once()
