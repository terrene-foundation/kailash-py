# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests (Tier 1) for ``nexus.typed_service_client.TypedServiceClient``.

Coverage:

* The default dataclass decoder produces instances for well-formed JSON.
* Missing required fields, wrong scalar types, and non-object top-level
  payloads collapse into ``ServiceClientDeserializeError``.
* Custom decoder registration dispatches per-model and is instance-scoped.
* ``register_decoder`` returns ``self`` for chained registration.
* Custom decoder exceptions are wrapped in ``ServiceClientDeserializeError``.
* Type-annotation edge cases — ``Optional[X]`` accepts ``None``, plain
  ``X`` rejects ``None``, ``bool`` is NOT accepted where ``int`` declared.

These tests exercise the decoder surface in isolation. End-to-end round
trips against a real HTTP server live in the Tier 2 wiring suite at
``tests/integration/test_typed_service_client_wiring.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pytest

from nexus.service_client import ServiceClientDeserializeError
from nexus.typed_service_client import (
    Decoder,
    TypedServiceClient,
    _default_decode,
)


# ---------------------------------------------------------------------------
# Test dataclasses — plain, frozen, with defaults, with optional fields
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class User:
    id: int
    name: str
    email: str


@dataclass
class UserWithDefault:
    id: int
    name: str
    active: bool = True


@dataclass
class UserWithOptional:
    id: int
    name: str
    email: Optional[str] = None


@dataclass
class UserWithPostInit:
    id: int
    name: str

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("name must not be empty")


@dataclass
class UserWithListField:
    id: int
    name: str
    # Generic containers fall through the default type-check; they are
    # accepted as-is and the caller registers a decoder if they want
    # deep validation.
    tags: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Default decoder — happy paths
# ---------------------------------------------------------------------------


class TestDefaultDecoderHappyPath:
    def test_simple_dataclass_round_trip(self) -> None:
        user = _default_decode(
            {"id": 42, "name": "Alice", "email": "a@example.com"}, User
        )
        assert user == User(id=42, name="Alice", email="a@example.com")

    def test_dataclass_with_default_uses_default_when_absent(self) -> None:
        user = _default_decode({"id": 1, "name": "Alice"}, UserWithDefault)
        assert user.active is True

    def test_dataclass_with_default_accepts_override(self) -> None:
        user = _default_decode(
            {"id": 1, "name": "Alice", "active": False}, UserWithDefault
        )
        assert user.active is False

    def test_optional_field_accepts_none(self) -> None:
        user = _default_decode(
            {"id": 1, "name": "Alice", "email": None}, UserWithOptional
        )
        assert user.email is None

    def test_optional_field_accepts_value(self) -> None:
        user = _default_decode(
            {"id": 1, "name": "Alice", "email": "a@x.com"}, UserWithOptional
        )
        assert user.email == "a@x.com"

    def test_optional_field_absent_uses_default(self) -> None:
        user = _default_decode({"id": 1, "name": "Alice"}, UserWithOptional)
        assert user.email is None

    def test_list_field_accepted_as_is(self) -> None:
        """Generic ``list`` annotation falls through the scalar type-check.

        Callers who want deep validation register a decoder.
        """
        user = _default_decode(
            {"id": 1, "name": "Alice", "tags": ["admin", "vip"]},
            UserWithListField,
        )
        assert user.tags == ["admin", "vip"]


# ---------------------------------------------------------------------------
# Default decoder — failure modes
# ---------------------------------------------------------------------------


class TestDefaultDecoderFailures:
    def test_missing_required_field_raises(self) -> None:
        with pytest.raises(ServiceClientDeserializeError) as exc_info:
            _default_decode({"id": 42, "name": "Alice"}, User)  # no email
        assert "email" in str(exc_info.value)
        assert "missing required field" in str(exc_info.value)

    def test_wrong_scalar_type_raises(self) -> None:
        with pytest.raises(ServiceClientDeserializeError) as exc_info:
            _default_decode(
                {"id": "not-an-int", "name": "Alice", "email": "a@x.com"}, User
            )
        assert "id" in str(exc_info.value)
        assert "expected int" in str(exc_info.value)

    def test_bool_rejected_for_int_field(self) -> None:
        """bool is a subclass of int; rejected explicitly to catch drift."""
        with pytest.raises(ServiceClientDeserializeError) as exc_info:
            _default_decode(
                {"id": True, "name": "Alice", "email": "a@x.com"}, User
            )
        assert "bool" in str(exc_info.value)

    def test_null_rejected_for_non_optional_field(self) -> None:
        with pytest.raises(ServiceClientDeserializeError) as exc_info:
            _default_decode(
                {"id": 42, "name": None, "email": "a@x.com"}, User
            )
        assert "null" in str(exc_info.value) or "None" in str(exc_info.value)

    def test_non_mapping_payload_raises(self) -> None:
        with pytest.raises(ServiceClientDeserializeError) as exc_info:
            _default_decode([{"id": 1, "name": "A", "email": "a@x"}], User)
        assert "expected a JSON object" in str(exc_info.value)

    def test_scalar_payload_raises(self) -> None:
        with pytest.raises(ServiceClientDeserializeError):
            _default_decode("just a string", User)

    def test_post_init_failure_wrapped(self) -> None:
        with pytest.raises(ServiceClientDeserializeError) as exc_info:
            _default_decode({"id": 1, "name": ""}, UserWithPostInit)
        # Original ValueError is chained.
        assert exc_info.value.__cause__ is not None
        assert "name must not be empty" in str(exc_info.value)

    def test_extra_unknown_field_raises(self) -> None:
        """``cls(**payload)`` with an unknown key raises ``TypeError``.

        The default decoder translates it into
        ``ServiceClientDeserializeError`` rather than letting ``TypeError``
        leak into the caller's error-handling plane.
        """
        with pytest.raises(ServiceClientDeserializeError):
            _default_decode(
                {"id": 1, "name": "A", "email": "a@x", "unknown": "x"}, User
            )


# ---------------------------------------------------------------------------
# Non-dataclass target — extra fields reach cls(**payload) → typed error
# ---------------------------------------------------------------------------


class PlainKwargsClass:
    """Not a dataclass; takes **kwargs to prove the fallback path."""

    def __init__(self, **kwargs: object) -> None:
        self.fields = kwargs


class StrictKwargsClass:
    """Not a dataclass; rejects unknown kwargs."""

    def __init__(self, id: int, name: str) -> None:
        self.id = id
        self.name = name


class TestNonDataclassTargets:
    def test_plain_kwargs_class_accepts_any_payload(self) -> None:
        obj = _default_decode({"a": 1, "b": 2}, PlainKwargsClass)
        assert isinstance(obj, PlainKwargsClass)
        assert obj.fields == {"a": 1, "b": 2}

    def test_strict_kwargs_class_rejects_unknown_field(self) -> None:
        with pytest.raises(ServiceClientDeserializeError):
            _default_decode(
                {"id": 1, "name": "A", "extra": True}, StrictKwargsClass
            )

    def test_strict_kwargs_class_rejects_missing_required(self) -> None:
        with pytest.raises(ServiceClientDeserializeError):
            _default_decode({"name": "A"}, StrictKwargsClass)


# ---------------------------------------------------------------------------
# TypedServiceClient — register_decoder, dispatch, chaining
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> TypedServiceClient:
    """A minimal TypedServiceClient — no network calls in these tests."""
    return TypedServiceClient("https://api.example.com")


class TestRegisterDecoder:
    def test_register_returns_self_for_chaining(
        self, client: TypedServiceClient
    ) -> None:
        def _fake_decoder(payload, cls):
            return cls()

        class X:
            pass

        class Y:
            pass

        result = client.register_decoder(X, _fake_decoder).register_decoder(
            Y, _fake_decoder
        )
        assert result is client

    def test_register_rejects_non_class(
        self, client: TypedServiceClient
    ) -> None:
        with pytest.raises(TypeError):
            client.register_decoder("not a class", lambda p, c: None)  # type: ignore[arg-type]

    def test_register_rejects_non_callable_decoder(
        self, client: TypedServiceClient
    ) -> None:
        with pytest.raises(TypeError):
            client.register_decoder(User, "not-a-callable")  # type: ignore[arg-type]

    def test_custom_decoder_dispatched(
        self, client: TypedServiceClient
    ) -> None:
        sentinel = object()

        def custom(payload, cls):
            assert payload == {"id": 99}
            assert cls is User
            return sentinel

        client.register_decoder(User, custom)
        assert client._decode({"id": 99}, User) is sentinel

    def test_custom_decoder_exception_wrapped_in_deserialize_error(
        self, client: TypedServiceClient
    ) -> None:
        def bad_decoder(payload, cls):
            raise RuntimeError("decoder blew up")

        client.register_decoder(User, bad_decoder)
        with pytest.raises(ServiceClientDeserializeError) as exc_info:
            client._decode({"id": 1, "name": "A", "email": "a@x"}, User)
        assert "decoder blew up" in str(exc_info.value)
        assert isinstance(exc_info.value.__cause__, RuntimeError)

    def test_deserialize_error_from_decoder_not_double_wrapped(
        self, client: TypedServiceClient
    ) -> None:
        """If the decoder itself raises ``ServiceClientDeserializeError``,
        the wrapper must re-raise it unchanged, NOT wrap it again."""

        original = ServiceClientDeserializeError("decoder-raised")

        def raising(payload, cls):
            raise original

        client.register_decoder(User, raising)
        with pytest.raises(ServiceClientDeserializeError) as exc_info:
            client._decode({"id": 1}, User)
        assert exc_info.value is original

    def test_decoder_scope_is_per_instance(self) -> None:
        """Two clients in the same process MUST have independent decoder maps."""
        c1 = TypedServiceClient("https://api1.example.com")
        c2 = TypedServiceClient("https://api2.example.com")

        sentinel = object()

        def decoder_for_c1(payload, cls):
            return sentinel

        c1.register_decoder(User, decoder_for_c1)
        # c1 dispatches to the custom decoder.
        assert (
            c1._decode({"id": 1, "name": "A", "email": "a@x"}, User) is sentinel
        )
        # c2 falls back to the default decoder and produces a real User.
        assert c2._decode(
            {"id": 1, "name": "A", "email": "a@x"}, User
        ) == User(id=1, name="A", email="a@x")

    def test_unknown_class_uses_default_decoder(
        self, client: TypedServiceClient
    ) -> None:
        """Registering a decoder for class A MUST NOT affect decoding of class B."""

        @dataclass
        class OtherModel:
            id: int
            value: str

        def bad_decoder(payload, cls):
            raise AssertionError("must not be called for OtherModel")

        client.register_decoder(User, bad_decoder)
        other = client._decode({"id": 7, "value": "x"}, OtherModel)
        assert other == OtherModel(id=7, value="x")


# ---------------------------------------------------------------------------
# Construction — TypedServiceClient inherits ServiceClient's validation
# ---------------------------------------------------------------------------


class TestConstructionInheritance:
    def test_empty_base_url_rejected(self) -> None:
        from nexus.service_client import ServiceClientInvalidPathError

        with pytest.raises(ServiceClientInvalidPathError):
            TypedServiceClient("")

    def test_crlf_in_header_rejected(self) -> None:
        from nexus.service_client import ServiceClientInvalidHeaderError

        with pytest.raises(ServiceClientInvalidHeaderError):
            TypedServiceClient(
                "https://api.example.com",
                headers={"X-Bad": "v\r\nX-Injected: 1"},
            )

    def test_decoders_initially_empty(self) -> None:
        client = TypedServiceClient("https://api.example.com")
        assert client._decoders == {}

    def test_is_subclass_of_service_client(self) -> None:
        from nexus.service_client import ServiceClient

        assert issubclass(TypedServiceClient, ServiceClient)

    def test_decoder_type_alias_callable(self) -> None:
        """``Decoder`` is a ``Callable[[Any, Type[Any]], Any]`` alias.

        Covered here so the symbol has a test-site reference and the
        default-collection test suite exercises it.
        """
        assert Decoder is not None
