"""
Unit tests for PostgreSQLAdapter's credential_provider wiring (issue #1737).

Tests the pure connect-wrapper logic (validation, fail-closed error shape,
no-secret-in-exception-message) WITHOUT a live database connection. Uses a
deterministic Protocol-satisfying fake for ``asyncpg`` — never a MagicMock —
per rules/testing.md's "Protocol-Satisfying Deterministic Adapters" carve-out.

Tier-2 end-to-end coverage (real Postgres: per-physical-connection invocation
count, fail-closed on a real pool, token-rotation-establishes-new-connection,
token never logged) lives in
tests/integration/database/test_credential_provider.py.
"""

from __future__ import annotations

from typing import Callable, List, Optional

import pytest
from dataflow.adapters.postgresql import PostgreSQLAdapter
from dataflow.exceptions import DataFlowConnectionError


class _FakeAsyncpgConnection:
    """Minimal stand-in for an asyncpg.Connection — records the password it
    was constructed with so tests can assert on it without a real socket."""

    def __init__(self, password: Optional[str]):
        self.password = password


class _FakeAsyncpgModule:
    """Protocol-satisfying fake for the ``asyncpg`` module surface the
    connect-wrapper touches (``asyncpg.connect``). Deterministic, records
    every call's kwargs for inspection. NOT a MagicMock — a plain object
    with a real (if trivial) async implementation.
    """

    def __init__(self):
        self.connect_calls: List[dict] = []

    async def connect(self, *args, **kwargs):
        self.connect_calls.append(dict(kwargs))
        return _FakeAsyncpgConnection(kwargs.get("password"))


class RotatingTokenProvider:
    """Deterministic, Protocol-satisfying credential provider.

    Returns tokens from a fixed sequence, advancing one step per call and
    holding on the final value once the sequence is exhausted. Tracks
    ``call_count`` for invocation-count assertions. Satisfies
    ``Callable[[], str]`` structurally — NOT a MagicMock.
    """

    def __init__(self, tokens: List[str]):
        self._tokens = list(tokens)
        self.call_count = 0

    def __call__(self) -> str:
        self.call_count += 1
        idx = min(self.call_count - 1, len(self._tokens) - 1)
        return self._tokens[idx]


class RaisingProvider:
    """Deterministic provider that always raises, carrying a marker string
    in its exception message so tests can assert the marker is NEVER
    propagated verbatim into the raised DataFlowConnectionError."""

    def __init__(self, secret_marker: str):
        self._secret_marker = secret_marker
        self.call_count = 0

    def __call__(self) -> str:
        self.call_count += 1
        raise RuntimeError(f"token endpoint failed for secret={self._secret_marker}")


class NonStrProvider:
    """Deterministic provider returning a non-str / empty value."""

    def __init__(self, value):
        self._value = value
        self.call_count = 0

    def __call__(self):
        self.call_count += 1
        return self._value


def _adapter(
    credential_provider: Optional[Callable[[], str]] = None,
) -> PostgreSQLAdapter:
    return PostgreSQLAdapter(
        "postgresql://static_user:static_pw@localhost:5432/testdb",
        credential_provider=credential_provider,
    )


class TestCredentialProviderFieldWiring:
    """AC: connection config accepts the optional per-connection callback."""

    def test_credential_provider_defaults_to_none(self):
        adapter = _adapter()
        assert adapter.credential_provider is None

    def test_credential_provider_stored_when_provided(self):
        provider = RotatingTokenProvider(["token-v1"])
        adapter = _adapter(credential_provider=provider)
        assert adapter.credential_provider is provider


class TestConnectWrapperMintsFreshCredentialPerCall:
    """AC: the wrapper re-mints on every invocation (the per-physical-
    connection hook asyncpg.Pool calls for initial/recycled/overflow/
    reconnect connections — see postgresql.py docstring)."""

    @pytest.mark.asyncio
    async def test_wrapper_calls_provider_and_overrides_static_password(self):
        provider = RotatingTokenProvider(["token-v1", "token-v2", "token-v3"])
        adapter = _adapter(credential_provider=provider)
        fake_asyncpg = _FakeAsyncpgModule()
        connect = adapter._make_credential_provider_connect(fake_asyncpg)

        con1 = await connect(password="STALE-STATIC-PASSWORD")
        con2 = await connect(password="STALE-STATIC-PASSWORD")
        con3 = await connect(password="STALE-STATIC-PASSWORD")

        # Every physical connection got a FRESH, distinct credential — never
        # the stale static password captured at pool-construction time.
        assert con1.password == "token-v1"
        assert con2.password == "token-v2"
        assert con3.password == "token-v3"
        assert provider.call_count == 3
        assert len(fake_asyncpg.connect_calls) == 3

    @pytest.mark.asyncio
    async def test_wrapper_forwards_non_password_kwargs_unchanged(self):
        provider = RotatingTokenProvider(["token-v1"])
        adapter = _adapter(credential_provider=provider)
        fake_asyncpg = _FakeAsyncpgModule()
        connect = adapter._make_credential_provider_connect(fake_asyncpg)

        await connect(
            host="db.example.com", port=5432, password="ignored", database="app"
        )

        call = fake_asyncpg.connect_calls[0]
        assert call["host"] == "db.example.com"
        assert call["port"] == 5432
        assert call["database"] == "app"
        assert call["password"] == "token-v1"


class TestConnectWrapperFailsClosed:
    """AC: callback error fails closed (raises typed error, no stale-token
    reuse)."""

    @pytest.mark.asyncio
    async def test_raising_provider_raises_typed_dataflow_error(self):
        provider = RaisingProvider(secret_marker="TOKEN-SHOULD-NOT-LEAK-8f3a")
        adapter = _adapter(credential_provider=provider)
        fake_asyncpg = _FakeAsyncpgModule()
        connect = adapter._make_credential_provider_connect(fake_asyncpg)

        with pytest.raises(DataFlowConnectionError):
            await connect(password="STALE-STATIC-PASSWORD")

        # Fail-closed: asyncpg.connect was NEVER reached — no stale-token
        # fallback connection was attempted.
        assert len(fake_asyncpg.connect_calls) == 0

    @pytest.mark.asyncio
    async def test_raising_provider_exception_message_excludes_secret_marker(self):
        secret = "TOKEN-SHOULD-NOT-LEAK-8f3a"
        provider = RaisingProvider(secret_marker=secret)
        adapter = _adapter(credential_provider=provider)
        fake_asyncpg = _FakeAsyncpgModule()
        connect = adapter._make_credential_provider_connect(fake_asyncpg)

        with pytest.raises(DataFlowConnectionError) as exc_info:
            await connect(password="STALE-STATIC-PASSWORD")

        # The original provider exception's str() (which embeds the secret
        # marker) MUST NOT appear in the raised DataFlow error's message —
        # only the exception TYPE name is safe to surface.
        message = str(exc_info.value)
        assert secret not in message
        assert "RuntimeError" in message

    @pytest.mark.asyncio
    async def test_non_str_return_raises_typed_dataflow_error(self):
        provider = NonStrProvider(value=None)
        adapter = _adapter(credential_provider=provider)
        fake_asyncpg = _FakeAsyncpgModule()
        connect = adapter._make_credential_provider_connect(fake_asyncpg)

        with pytest.raises(DataFlowConnectionError, match="non-empty str"):
            await connect(password="STALE-STATIC-PASSWORD")
        assert len(fake_asyncpg.connect_calls) == 0

    @pytest.mark.asyncio
    async def test_empty_str_return_raises_typed_dataflow_error(self):
        provider = NonStrProvider(value="")
        adapter = _adapter(credential_provider=provider)
        fake_asyncpg = _FakeAsyncpgModule()
        connect = adapter._make_credential_provider_connect(fake_asyncpg)

        with pytest.raises(DataFlowConnectionError, match="non-empty str"):
            await connect(password="STALE-STATIC-PASSWORD")
        assert len(fake_asyncpg.connect_calls) == 0

    @pytest.mark.asyncio
    async def test_non_str_type_int_raises_typed_dataflow_error(self):
        provider = NonStrProvider(value=12345)
        adapter = _adapter(credential_provider=provider)
        fake_asyncpg = _FakeAsyncpgModule()
        connect = adapter._make_credential_provider_connect(fake_asyncpg)

        with pytest.raises(DataFlowConnectionError, match="non-empty str"):
            await connect(password="STALE-STATIC-PASSWORD")
        assert len(fake_asyncpg.connect_calls) == 0


class TestAbsentCredentialProviderUnchanged:
    """AC: absent the callback, behavior is unchanged (static-string path)."""

    def test_create_connection_pool_params_omit_connect_key_when_absent(self):
        """When credential_provider is None, get_connection_parameters()'s
        static ``password`` field is used untouched — create_connection_pool
        never injects a ``connect`` override into asyncpg's create_pool
        kwargs. This is asserted structurally (no live connection needed):
        the adapter's credential_provider attribute gates the override in
        create_connection_pool(), verified directly here.
        """
        adapter = _adapter(credential_provider=None)
        assert adapter.credential_provider is None
        params = adapter.get_connection_parameters()
        assert "connect" not in params
        assert params["password"] == "static_pw"
