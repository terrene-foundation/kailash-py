# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Integration tests (Tier 2) for ``nexus.typed_service_client``.

Exercises every typed-model verb against a real HTTP server. Demonstrates:

* Happy-path round trip for GET / POST / PUT / DELETE → dataclass instance.
* Deserialize-error surface when the upstream response is missing a field
  or returns a wrong-typed scalar.
* Custom decoder registration (simulating pydantic / msgspec) dispatched
  against a real response.
* HTTP status errors bubble through unchanged — the typed wrapper does
  NOT mask ``ServiceClientHttpStatusError``.

Runs against ``pytest_httpserver`` which gives us a real httpx → HTTP →
werkzeug round trip — no mocks, real network stack.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from nexus.service_client import (
    ServiceClientDeserializeError,
    ServiceClientHttpStatusError,
)
from nexus.typed_service_client import TypedServiceClient


@dataclass(frozen=True)
class User:
    id: int
    name: str
    email: str


@pytest.fixture
def service(httpserver) -> TypedServiceClient:
    """TypedServiceClient pointing at pytest-httpserver.

    Uses ``allow_loopback=True`` because the test server binds 127.0.0.1.
    Production callers never set this flag.
    """
    base = f"http://{httpserver.host}:{httpserver.port}"
    return TypedServiceClient(
        base,
        bearer_token="test-token-xyz",
        allow_loopback=True,
        timeout_secs=5.0,
    )


# ---------------------------------------------------------------------------
# Happy paths — every typed verb round-trips a User through a real server
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestTypedVerbsRoundTrip:
    @pytest.mark.asyncio
    async def test_get_typed_returns_user(
        self, httpserver, service: TypedServiceClient
    ) -> None:
        httpserver.expect_request("/users/42").respond_with_json(
            {"id": 42, "name": "Alice", "email": "alice@example.com"}
        )
        try:
            user = await service.get_typed("/users/42", User)
            assert isinstance(user, User)
            assert user == User(id=42, name="Alice", email="alice@example.com")
        finally:
            await service.aclose()

    @pytest.mark.asyncio
    async def test_post_typed_returns_user(
        self, httpserver, service: TypedServiceClient
    ) -> None:
        httpserver.expect_request("/users", method="POST").respond_with_json(
            {"id": 1, "name": "Alice", "email": "alice@example.com"}
        )
        try:
            user = await service.post_typed(
                "/users",
                {"name": "Alice", "email": "alice@example.com"},
                User,
            )
            assert isinstance(user, User)
            assert user.id == 1
        finally:
            await service.aclose()

    @pytest.mark.asyncio
    async def test_put_typed_returns_user(
        self, httpserver, service: TypedServiceClient
    ) -> None:
        httpserver.expect_request("/users/42", method="PUT").respond_with_json(
            {"id": 42, "name": "Alice Updated", "email": "alice@example.com"}
        )
        try:
            user = await service.put_typed(
                "/users/42",
                {"name": "Alice Updated"},
                User,
            )
            assert user.name == "Alice Updated"
        finally:
            await service.aclose()

    @pytest.mark.asyncio
    async def test_delete_typed_returns_user(
        self, httpserver, service: TypedServiceClient
    ) -> None:
        httpserver.expect_request("/users/42", method="DELETE").respond_with_json(
            {"id": 42, "name": "Alice", "email": "alice@example.com"}
        )
        try:
            user = await service.delete_typed("/users/42", User)
            assert user.id == 42
        finally:
            await service.aclose()


# ---------------------------------------------------------------------------
# Deserialize errors — upstream payload does not match the model
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestTypedDeserializeErrors:
    @pytest.mark.asyncio
    async def test_missing_field_raises_deserialize_error(
        self, httpserver, service: TypedServiceClient
    ) -> None:
        httpserver.expect_request("/users/42").respond_with_json(
            {"id": 42, "name": "Alice"}  # no email
        )
        try:
            with pytest.raises(ServiceClientDeserializeError) as exc_info:
                await service.get_typed("/users/42", User)
            assert "email" in str(exc_info.value)
        finally:
            await service.aclose()

    @pytest.mark.asyncio
    async def test_wrong_scalar_type_raises_deserialize_error(
        self, httpserver, service: TypedServiceClient
    ) -> None:
        httpserver.expect_request("/users/42").respond_with_json(
            {"id": "not-an-int", "name": "Alice", "email": "a@x.com"}
        )
        try:
            with pytest.raises(ServiceClientDeserializeError) as exc_info:
                await service.get_typed("/users/42", User)
            assert "id" in str(exc_info.value)
        finally:
            await service.aclose()

    @pytest.mark.asyncio
    async def test_top_level_list_raises_deserialize_error(
        self, httpserver, service: TypedServiceClient
    ) -> None:
        httpserver.expect_request("/users/42").respond_with_json(
            [{"id": 42, "name": "Alice", "email": "a@x.com"}]
        )
        try:
            with pytest.raises(ServiceClientDeserializeError):
                await service.get_typed("/users/42", User)
        finally:
            await service.aclose()


# ---------------------------------------------------------------------------
# HTTP status errors bubble through the typed wrapper unchanged
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestTypedStatusErrors:
    @pytest.mark.asyncio
    async def test_404_surfaces_http_status_error(
        self, httpserver, service: TypedServiceClient
    ) -> None:
        httpserver.expect_request("/users/404").respond_with_data(
            "not found", status=404
        )
        try:
            with pytest.raises(ServiceClientHttpStatusError) as exc_info:
                await service.get_typed("/users/404", User)
            assert exc_info.value.status_code == 404
        finally:
            await service.aclose()


# ---------------------------------------------------------------------------
# Custom decoder — simulates pydantic / msgspec integration
# ---------------------------------------------------------------------------


class PydanticLikeUser:
    """Stand-in for a pydantic BaseModel — strict custom __init__."""

    def __init__(self, *, id: int, name: str, email: str) -> None:
        # Mimic pydantic v2 strict coercion (string "42" → int 42).
        self.id = int(id)
        self.name = name
        self.email = email

    @classmethod
    def validate(cls, payload: dict) -> "PydanticLikeUser":
        return cls(**payload)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PydanticLikeUser):
            return NotImplemented
        return (
            self.id == other.id
            and self.name == other.name
            and self.email == other.email
        )


@pytest.mark.integration
class TestCustomDecoderRoundTrip:
    @pytest.mark.asyncio
    async def test_custom_decoder_dispatches_on_typed_get(
        self, httpserver, service: TypedServiceClient
    ) -> None:
        """Register a pydantic-style decoder and verify it runs end-to-end.

        This proves the decoder plug-in path is live against a real
        server, not just a unit-level contract.
        """
        httpserver.expect_request("/users/42").respond_with_json(
            # `id` as string — pydantic-like decoder coerces, default
            # decoder would reject with ``expected int``. This is the
            # exact reason the custom-decoder path exists.
            {"id": "42", "name": "Alice", "email": "alice@example.com"}
        )

        service.register_decoder(
            PydanticLikeUser, lambda payload, cls: cls.validate(payload)
        )
        try:
            user = await service.get_typed("/users/42", PydanticLikeUser)
            assert isinstance(user, PydanticLikeUser)
            assert user == PydanticLikeUser(
                id=42, name="Alice", email="alice@example.com"
            )
        finally:
            await service.aclose()


# ---------------------------------------------------------------------------
# Bearer-token propagation via typed verbs
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestTypedVerbsAuth:
    @pytest.mark.asyncio
    async def test_bearer_token_sent_on_typed_get(
        self, httpserver, service: TypedServiceClient
    ) -> None:
        from werkzeug.wrappers import Response

        received_headers: dict[str, str] = {}

        def handler(request) -> Response:
            received_headers.update(request.headers)
            return Response(
                '{"id": 1, "name": "A", "email": "a@x.com"}',
                status=200,
                content_type="application/json",
            )

        httpserver.expect_request("/users/1").respond_with_handler(handler)
        try:
            await service.get_typed("/users/1", User)
            assert (
                received_headers.get("Authorization") == "Bearer test-token-xyz"
            )
        finally:
            await service.aclose()
