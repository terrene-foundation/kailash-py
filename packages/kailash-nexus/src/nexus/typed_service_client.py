# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Typed-model service-to-service HTTP client — ``TypedServiceClient``.

A thin wrapper around :class:`nexus.service_client.ServiceClient` that adds
model-typed request/response variants. The base class already guarantees:

* SSRF-on-by-default (private-IP / metadata-endpoint rejection before
  allowlist, per issue #473 non-negotiable 1).
* Eager CRLF / control-byte rejection on every header and the bearer token.
* Typed exception hierarchy rooted at ``ServiceClientError``.
* Bounded response-body truncation on non-2xx to prevent token echo into
  exception strings.

This module adds — and nothing else:

* ``get_typed`` / ``post_typed`` / ``put_typed`` / ``delete_typed`` — each
  parameterised by a response model class. The JSON body returned from the
  base client's typed verb is fed through a decoder to produce a concrete
  model instance.
* A default decoder that assumes the target class is a plain ``@dataclass``
  (or any class whose ``__init__`` takes the JSON field names as keyword
  arguments) and invokes ``cls(**payload)``. Missing-field and wrong-type
  failures are translated into
  :class:`~nexus.service_client.ServiceClientDeserializeError`.
* :meth:`TypedServiceClient.register_decoder` — a per-instance override that
  lets downstream users plug in pydantic, msgspec, attrs, or any other
  deserialiser without Nexus taking a hard dependency. Registration is
  instance-scoped (not a process global), so two clients in the same
  process can disagree about the decoder for the same class.

# Out of scope

OpenAPI → Python code generation is *explicitly* deferred until a concrete
consumer arrives (matches the kailash-rs BP-044 decision journal on the
Rust side). The current scope is: give downstream generators and
hand-written dataclass owners a uniform typed surface to call.

# Cross-SDK parity

Semantic match with kailash-rs #400. The four typed verb names
(``get_typed`` / ``post_typed`` / ``put_typed`` / ``delete_typed``) and
the ``ServiceClientDeserializeError`` trigger condition mirror the
Rust surface exactly so callers porting between SDKs hit the same
``isinstance`` checks.
"""

from __future__ import annotations

import dataclasses
import logging
import typing
from typing import Any, Callable, Mapping, Optional, Type, TypeVar

from .service_client import (
    ServiceClient,
    ServiceClientDeserializeError,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Decoder protocol
# ---------------------------------------------------------------------------

# A decoder converts a decoded JSON value (dict / list / str / int / …) into
# an instance of the target model class. The signature is intentionally
# minimal so pydantic / msgspec / attrs / hand-rolled dataclasses can all
# plug in without adapter shims.
Decoder = Callable[[Any, Type[Any]], Any]

# Type variable that lets static type checkers narrow the return type of
# ``get_typed(... , User)`` to ``User``. At runtime the hints are
# advisory — deserialisation errors surface as ``ServiceClientDeserializeError``.
M = TypeVar("M")


def _default_decode(payload: Any, model_cls: Type[M]) -> M:
    """Default decoder — assumes a dataclass-like ``__init__(**fields)``.

    The fallback path works for any class whose constructor accepts the
    JSON object's keys as keyword arguments. This covers:

    * ``@dataclass(frozen=True)`` classes (the OpenAPI-generator target).
    * Plain classes with an explicit ``__init__`` accepting keyword args.
    * ``typing.NamedTuple`` — ``NT(**payload)`` works natively.

    Anything else (pydantic ``BaseModel``, msgspec ``Struct``, attrs class
    with custom ``__init__``) MUST register its own decoder via
    :meth:`TypedServiceClient.register_decoder` to avoid ``TypeError``
    bubbling up from an unsupported constructor signature.

    Failure modes collapsed into ``ServiceClientDeserializeError``:

    * JSON object missing a required field → ``TypeError`` caught → raise.
    * Wrong scalar type for a declared dataclass field (we check this
      explicitly for ``@dataclass`` targets because ``cls(**payload)``
      does NOT validate types by itself, and silently wrong-typed fields
      are the #1 drift source in cross-SDK JSON contracts).
    * Target class constructor raises (e.g. ``__post_init__`` validator) →
      error chained from the original exception so the caller can see
      both the wrapper and the root cause.
    """
    # Only the JSON-object case makes sense for "call cls(**payload)". A
    # top-level JSON array or scalar is a contract mismatch with any
    # @dataclass model and should surface as a deserialize error with a
    # clear message rather than a cryptic ``TypeError`` from cls(**payload)
    # invoked on a non-mapping.
    if not isinstance(payload, Mapping):
        raise ServiceClientDeserializeError(
            f"cannot decode {type(payload).__name__} into "
            f"{getattr(model_cls, '__name__', str(model_cls))}: "
            f"expected a JSON object"
        )

    # Structural dataclass validation — catch wrong-type fields before they
    # land in the instance. ``cls(**payload)`` for a dataclass does NOT
    # type-check; an ``email: str`` field receiving an integer constructs
    # fine and surfaces as a string-formatting bug far from the API
    # boundary. We check dataclass fields against resolved annotations so
    # drift is caught at the deserialisation step.
    if dataclasses.is_dataclass(model_cls):
        try:
            hints = typing.get_type_hints(model_cls)
        except Exception:
            # If PEP 563 / forward-ref resolution fails, fall through and
            # let cls(**payload) do its best. We do NOT silently swallow
            # the eventual TypeError — it becomes a DeserializeError below.
            hints = {}
        fields = dataclasses.fields(model_cls)
        required_names = {
            f.name
            for f in fields
            if f.default is dataclasses.MISSING
            and f.default_factory is dataclasses.MISSING  # type: ignore[misc]
        }
        known_names = {f.name for f in fields}

        missing = required_names - set(payload.keys())
        if missing:
            raise ServiceClientDeserializeError(
                f"cannot decode into {model_cls.__name__}: missing "
                f"required field(s) {sorted(missing)!r}"
            )

        # Type-narrowing — only checks simple, non-generic types. We do NOT
        # attempt to validate List[int] / Dict[str, X] / Union[...]; that
        # is a pydantic / msgspec-scale feature and callers who need it
        # MUST register a decoder. Scalar-type mismatches cover >90% of
        # contract drift in practice and are the bug class that surfaces
        # weeks later as an ``AttributeError``.
        for fname, declared in hints.items():
            if fname not in payload:
                continue
            if fname not in known_names:
                # Type hint for a field the dataclass doesn't expose (e.g.
                # ClassVar, inherited from a non-dataclass base). Skip.
                continue
            value = payload[fname]
            expected = _unwrap_optional(declared)
            if expected is None or not isinstance(expected, type):
                # Generic, Union, ForwardRef, etc. — out of scope for the
                # default decoder. A caller who needs validation for these
                # registers a decoder.
                continue
            if value is None:
                # ``None`` is only acceptable if the declared type itself
                # was ``Optional[X]`` (already unwrapped above, so we only
                # reach here when the annotation permits None).
                if _is_optional(declared):
                    continue
                raise ServiceClientDeserializeError(
                    f"cannot decode into {model_cls.__name__}: field "
                    f"{fname!r} is null but declared as "
                    f"{getattr(expected, '__name__', str(expected))}"
                )
            # bool is a subclass of int; reject `True` arriving for an
            # `int` field because it's almost always a JSON-contract bug.
            if expected is int and isinstance(value, bool):
                raise ServiceClientDeserializeError(
                    f"cannot decode into {model_cls.__name__}: field "
                    f"{fname!r} expected int but received bool"
                )
            if not isinstance(value, expected):
                raise ServiceClientDeserializeError(
                    f"cannot decode into {model_cls.__name__}: field "
                    f"{fname!r} expected "
                    f"{getattr(expected, '__name__', str(expected))} "
                    f"but received {type(value).__name__}"
                )

    try:
        return model_cls(**payload)
    except TypeError as exc:
        # Unexpected keyword (extra field in server response) or missing
        # required keyword that the dataclass-pre-check missed (e.g. the
        # target class is not a dataclass). Translate to DeserializeError
        # so the caller gets a uniform surface.
        raise ServiceClientDeserializeError(
            f"cannot decode into "
            f"{getattr(model_cls, '__name__', str(model_cls))}: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    except ServiceClientDeserializeError:
        raise
    except Exception as exc:
        # Target class constructor or __post_init__ raised. Surface the
        # original error via chained exception but keep the typed surface.
        raise ServiceClientDeserializeError(
            f"cannot decode into "
            f"{getattr(model_cls, '__name__', str(model_cls))}: "
            f"{type(exc).__name__}: {exc}"
        ) from exc


def _is_optional(annotation: Any) -> bool:
    """Return True if the annotation is ``Optional[X]`` / ``X | None``."""
    origin = typing.get_origin(annotation)
    if origin is typing.Union or origin is getattr(__import__("types"), "UnionType", None):
        args = typing.get_args(annotation)
        return type(None) in args
    return False


def _unwrap_optional(annotation: Any) -> Any:
    """Return ``X`` for ``Optional[X]`` / ``X | None``, else the annotation."""
    if _is_optional(annotation):
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return args[0]
        # ``Union[A, B, None]`` — not a scalar; caller falls through to no-check.
        return None
    return annotation


# ---------------------------------------------------------------------------
# TypedServiceClient
# ---------------------------------------------------------------------------


class TypedServiceClient(ServiceClient):
    """Service-to-service client with model-typed request/response verbs.

    Inherits every guarantee of :class:`ServiceClient`:

    * SSRF-on-by-default, layer order per issue #473 NN1.
    * Eager CRLF / control-byte rejection of headers and the bearer token.
    * Typed exception hierarchy (``ServiceClientError`` + variants).

    Adds four model-typed variants that run the base client's JSON verb
    and feed the decoded payload through a decoder keyed by the target
    model class:

    .. code-block:: python

        from dataclasses import dataclass
        from nexus import TypedServiceClient

        @dataclass(frozen=True)
        class User:
            id: int
            name: str
            email: str

        async with TypedServiceClient(
            "https://api.internal",
            bearer_token="...",
            allowed_hosts=["api.internal"],
        ) as client:
            user = await client.get_typed("/users/42", User)
            # user: User
            created = await client.post_typed(
                "/users",
                {"name": "Alice", "email": "alice@example.com"},
                User,
            )

    Downstream users with a pydantic / msgspec / attrs model can plug in
    their own decoder without Nexus taking a hard dependency:

    .. code-block:: python

        import pydantic

        class User(pydantic.BaseModel):
            id: int
            name: str
            email: str

        client = TypedServiceClient("https://api.internal")
        client.register_decoder(User, lambda payload, cls: cls.model_validate(payload))
        user = await client.get_typed("/users/42", User)

    Decoder registration is **instance-scoped** — two clients in the
    same process can disagree about how to decode the same class.
    """

    # Instance-scoped decoder map — NOT a class-level dict. A class-level
    # dict would leak state between clients and make the "per-client
    # decoder" guarantee false. __slots__ extends the base class's
    # __slots__.
    __slots__ = ("_decoders",)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Map from model class -> decoder callable. Class objects are
        # hashable by identity, which is exactly the semantics we want
        # (two dataclasses with the same name in different modules are
        # distinct keys).
        self._decoders: dict[Type[Any], Decoder] = {}

    # ---- Decoder registration --------------------------------------------

    def register_decoder(
        self, model_cls: Type[M], decoder: Decoder
    ) -> "TypedServiceClient":
        """Plug in a custom decoder for ``model_cls``.

        The registered decoder receives ``(json_payload, model_cls)`` and
        MUST return an instance of ``model_cls``. Any exception raised by
        the decoder is wrapped in ``ServiceClientDeserializeError`` when
        surfaced to the caller (so the typed exception hierarchy stays
        uniform regardless of the underlying deserialisation library).

        Returns ``self`` so registrations can chain::

            client = (
                TypedServiceClient("https://api.internal")
                .register_decoder(User, pydantic_decoder)
                .register_decoder(Order, msgspec_decoder)
            )
        """
        if not isinstance(model_cls, type):
            raise TypeError(
                f"model_cls must be a class (got {type(model_cls).__name__})"
            )
        if not callable(decoder):
            raise TypeError(
                f"decoder must be callable (got {type(decoder).__name__})"
            )
        self._decoders[model_cls] = decoder
        logger.debug(
            "nexus.typed_service_client.register_decoder",
            extra={"model_cls": getattr(model_cls, "__name__", str(model_cls))},
        )
        return self

    def _decode(self, payload: Any, model_cls: Type[M]) -> M:
        """Dispatch to the registered decoder for ``model_cls``, or default."""
        decoder = self._decoders.get(model_cls, _default_decode)
        try:
            return decoder(payload, model_cls)
        except ServiceClientDeserializeError:
            raise
        except Exception as exc:
            # Custom decoders do not know about ServiceClientDeserializeError.
            # Convert their exceptions into the typed surface so callers
            # can ``except ServiceClientDeserializeError`` uniformly.
            raise ServiceClientDeserializeError(
                f"decoder for "
                f"{getattr(model_cls, '__name__', str(model_cls))} raised "
                f"{type(exc).__name__}: {exc}"
            ) from exc

    # ---- Typed verbs — status-checked, JSON in, model out -----------------

    async def get_typed(
        self,
        path: str,
        model_cls: Type[M],
        *,
        headers: Optional[Mapping[str, str]] = None,
    ) -> M:
        """GET ``path`` and decode the JSON body into ``model_cls``."""
        payload = await self.get(path, headers=headers)
        return self._decode(payload, model_cls)

    async def post_typed(
        self,
        path: str,
        body: Any,
        model_cls: Type[M],
        *,
        headers: Optional[Mapping[str, str]] = None,
    ) -> M:
        """POST ``body`` as JSON; decode the 2xx JSON body into ``model_cls``.

        ``body`` is forwarded verbatim to :meth:`ServiceClient.post`, which
        serialises it with ``json.dumps``. Callers whose ``body`` is a
        dataclass / pydantic model MUST convert to a dict first
        (``asdict`` / ``model_dump``) or register a request encoder at a
        layer above this client. Handling arbitrary request-model types
        is out of scope until a concrete consumer arrives.
        """
        payload = await self.post(path, body, headers=headers)
        return self._decode(payload, model_cls)

    async def put_typed(
        self,
        path: str,
        body: Any,
        model_cls: Type[M],
        *,
        headers: Optional[Mapping[str, str]] = None,
    ) -> M:
        """PUT ``body`` as JSON; decode the 2xx JSON body into ``model_cls``."""
        payload = await self.put(path, body, headers=headers)
        return self._decode(payload, model_cls)

    async def delete_typed(
        self,
        path: str,
        model_cls: Type[M],
        *,
        headers: Optional[Mapping[str, str]] = None,
    ) -> M:
        """DELETE ``path`` and decode the JSON body into ``model_cls``.

        Note — a 204 No Content response from the base client returns
        ``None``. Feeding ``None`` into a dataclass decoder yields a
        ``ServiceClientDeserializeError`` ("expected a JSON object");
        that is the intended behaviour. Callers who want "delete returns
        the deleted resource on 200, nothing on 204" semantics MUST
        use :meth:`ServiceClient.delete` directly.
        """
        payload = await self.delete(path, headers=headers)
        return self._decode(payload, model_cls)


__all__ = [
    "TypedServiceClient",
    "Decoder",
]
