# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Transport wiring for the universal outbound-effect governance seam (#1517 leg-b).

The domain-neutral interceptor core lives in
:mod:`kailash.trust.pact.outbound`. THIS module is the production wiring that
binds that seam to the three concrete outbound transports an agent uses:

- :class:`GovernedProvider` -- LLM completions (wraps any Kaizen provider so
  every ``chat`` / ``chat_async`` / ``stream_chat`` call is governed).
- :class:`GovernedToolInvoker` -- tool / MCP invocations.
- :class:`GovernedHTTPClient` -- outbound HTTP requests.

Each facade is a THIN, transparent proxy over the interceptor: it builds the
kind-specific :class:`~kailash.trust.pact.outbound.OutboundEffect` from the
transport's own call and routes it through the interceptor. The agent's code is
UNCHANGED -- an agent that calls ``provider.chat(messages)`` calls the governed
provider's ``chat(messages)`` with the identical signature; the envelope is
applied without the agent ever referencing governance.

Layering: the transport-specific normalization (which call arg is the model,
the URL, the tool name) lives HERE, at the framework seam (per
framework-first.md: Kaizen owns the LLM/provider seam). The core stays
transport-agnostic.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

from kailash.trust.pact.outbound import (
    EffectKind,
    OutboundEffect,
    OutboundEffectInterceptor,
    active_interceptor,
    wrap_transport,
    wrap_transport_async,
)

logger = logging.getLogger(__name__)

__all__ = [
    "GovernedProvider",
    "GovernedToolInvoker",
    "GovernedHTTPClient",
    "resolve_interceptor",
    "redact_http_target",
]

# Grep-safe sentinel returned when a request URL cannot be parsed -- distinct
# from any successful redaction so it is never mistaken for a real target and a
# malformed credential-bearing string never reaches the audit record.
_REDACTED_URL_SENTINEL = "<redacted url>"


def redact_http_target(url: str) -> str:
    """Strip credentials from a request URL before it becomes an audit target.

    The raw request URL flows verbatim from :class:`GovernedHTTPClient` into
    :class:`~kailash.trust.pact.outbound.OutboundEffect`'s ``target`` field, and
    from there into the :class:`~kailash.trust.pact.outbound.OutboundVerdict`,
    the bounded audit deque, any ``audit_sink``, and
    :class:`~kailash.trust.pact.outbound.OutboundEffectRefused`'s ``details``.
    A URL carrying userinfo (``https://user:pass@host``) or a secret query
    parameter (``?api_key=...``) would therefore write a credential into the
    audit trail -- the ``rules/security.md`` § "No secrets in logs" failure mode.

    This keeps ONLY ``scheme://host[:port]/path`` -- everything the audit trail
    needs for observability -- and drops BOTH credential vectors: the userinfo
    component AND the entire query string (and fragment). Fail-closed: a value
    that cannot be parsed as a URL is reduced to :data:`_REDACTED_URL_SENTINEL`
    rather than echoed verbatim.
    """
    if not isinstance(url, str) or not url:
        return ""
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
        if ":" in host:  # IPv6 literal -- re-bracket it
            host = f"[{host}]"
        netloc = host
        if parts.port:
            netloc = f"{netloc}:{parts.port}"
        # Drop userinfo, query, and fragment; keep scheme://host[:port]/path.
        return urlunsplit((parts.scheme, netloc, parts.path, "", ""))
    except (ValueError, AttributeError):
        return _REDACTED_URL_SENTINEL


def resolve_interceptor(
    interceptor: OutboundEffectInterceptor | None,
) -> OutboundEffectInterceptor:
    """Return the explicit interceptor, else the process-global one.

    Fail-closed: if neither is available, raise -- an ungoverned transport MUST
    NOT be silently constructed (that would defeat the seam).
    """
    resolved = interceptor if interceptor is not None else active_interceptor()
    if resolved is None:
        raise ValueError(
            "No OutboundEffectInterceptor available: pass one explicitly or "
            "install a process-global one via install_interceptor(). Refusing "
            "to build an ungoverned transport (fail-closed)."
        )
    return resolved


def _governed(
    interceptor: OutboundEffectInterceptor,
    effect_builder: Callable[[tuple[Any, ...], dict[str, Any]], OutboundEffect],
    fn: Callable[..., Any],
) -> Callable[..., Any]:
    """Wrap ``fn`` (sync OR async) in the governance seam, auto-detecting shape."""
    if inspect.iscoroutinefunction(fn):
        return wrap_transport_async(interceptor, effect_builder, fn)
    return wrap_transport(interceptor, effect_builder, fn)


class GovernedProvider:
    """Transparent governance proxy around any Kaizen LLM provider.

    Wrap a provider ONCE at construction/bootstrap; hand the wrapped provider to
    an agent exactly as you would the raw one. Every outbound completion method
    (``chat`` / ``chat_async`` / ``stream_chat`` / ``complete`` / ``generate``)
    is routed through the interceptor before the real provider is called. Every
    OTHER attribute (``name``, ``capabilities``, ``model``, ...) is forwarded
    unchanged, so the proxy is a drop-in replacement -- the "no agent code
    change" property.

    Args:
        provider: The underlying provider (any object exposing the completion
            methods below). Not modified.
        interceptor: The governance interceptor. If None, the process-global
            interceptor is used; if neither exists, construction fails closed.
        caller: The D/T/R role address (or resolved identity) of the agent
            producing the effects. Passed to governance as ``role_address``.
        cost_estimator: Optional callable ``(method, args, kwargs) -> float``
            producing a per-call cost estimate for the financial envelope
            dimension. Defaults to a zero-cost estimate.
    """

    _OUTBOUND_METHODS = frozenset(
        {"chat", "chat_async", "stream_chat", "complete", "generate"}
    )

    def __init__(
        self,
        provider: Any,
        interceptor: OutboundEffectInterceptor | None = None,
        *,
        caller: str,
        cost_estimator: (
            Callable[[str, tuple[Any, ...], dict[str, Any]], float] | None
        ) = None,
    ) -> None:
        # object.__setattr__ so these land before __getattr__/__setattr__ wiring.
        object.__setattr__(self, "_provider", provider)
        object.__setattr__(self, "_interceptor", resolve_interceptor(interceptor))
        object.__setattr__(self, "_caller", str(caller))
        object.__setattr__(self, "_cost_estimator", cost_estimator)

    def _target(self) -> str:
        """Best-effort model/target label for audit (never a governance bypass)."""
        for attr in ("model", "model_name", "name"):
            value = getattr(self._provider, attr, None)
            if isinstance(value, str) and value:
                return value
        return type(self._provider).__name__

    def _effect_builder(
        self, method: str
    ) -> Callable[[tuple[Any, ...], dict[str, Any]], OutboundEffect]:
        def build(args: tuple[Any, ...], kwargs: dict[str, Any]) -> OutboundEffect:
            cost = 0.0
            if self._cost_estimator is not None:
                cost = float(self._cost_estimator(method, args, kwargs))
            return OutboundEffect(
                kind=EffectKind.LLM,
                operation=f"llm.{method}",
                target=self._target(),
                cost_estimate=cost,
                caller=self._caller,
            )

        return build

    def __getattr__(self, name: str) -> Any:
        # __getattr__ only fires for attrs not found normally, i.e. everything
        # that belongs to the wrapped provider.
        attr = getattr(self._provider, name)
        if name in self._OUTBOUND_METHODS and callable(attr):
            return _governed(self._interceptor, self._effect_builder(name), attr)
        return attr


class GovernedToolInvoker:
    """Governs tool / MCP invocations through the universal seam.

    Use :meth:`wrap` to turn a bare tool callable into a governed one, or
    :meth:`invoke` to govern a one-off call. The tool author writes an ordinary
    callable; governance is applied at the invoker, not inside the tool.

    Args:
        interceptor: The governance interceptor. Falls back to the process-global
            one; fails closed if neither exists.
        caller: The D/T/R role address of the agent invoking tools.
    """

    def __init__(
        self,
        interceptor: OutboundEffectInterceptor | None = None,
        *,
        caller: str,
    ) -> None:
        self._interceptor = resolve_interceptor(interceptor)
        self._caller = str(caller)

    def _effect_builder(
        self, tool_name: str, cost: float
    ) -> Callable[[tuple[Any, ...], dict[str, Any]], OutboundEffect]:
        def build(args: tuple[Any, ...], kwargs: dict[str, Any]) -> OutboundEffect:
            return OutboundEffect(
                kind=EffectKind.TOOL,
                operation=f"tool.{tool_name}",
                target=tool_name,
                cost_estimate=cost,
                caller=self._caller,
            )

        return build

    def wrap(
        self, tool_name: str, fn: Callable[..., Any], *, cost: float = 0.0
    ) -> Callable[..., Any]:
        """Return a governed version of tool callable ``fn`` (sync or async)."""
        if not isinstance(tool_name, str) or not tool_name.strip():
            raise ValueError("tool_name must be a non-empty string")
        return _governed(self._interceptor, self._effect_builder(tool_name, cost), fn)

    def invoke(
        self, tool_name: str, fn: Callable[[], Any], *, cost: float = 0.0
    ) -> Any:
        """Govern a single zero-arg tool call ``fn`` and return its result."""
        effect = OutboundEffect(
            kind=EffectKind.TOOL,
            operation=f"tool.{tool_name}",
            target=tool_name,
            cost_estimate=cost,
            caller=self._caller,
        )
        return self._interceptor.intercept(effect, fn)


class GovernedHTTPClient:
    """Governs outbound HTTP requests through the universal seam.

    Wraps a transport-level request callable (e.g. ``httpx.Client.request`` or a
    Nexus outbound-request dispatch) so every request is governed. The caller
    invokes :meth:`request` with the same ``(method, url, **kwargs)`` shape as
    the underlying transport -- no per-request governance call.

    Args:
        request_fn: The underlying request dispatch, ``request(method, url,
            **kwargs) -> response`` (sync or async).
        interceptor: The governance interceptor. Falls back to the process-global
            one; fails closed if neither exists.
        caller: The D/T/R role address of the agent issuing requests.
        cost_estimator: Optional ``(method, url, kwargs) -> float`` cost estimate.
    """

    def __init__(
        self,
        request_fn: Callable[..., Any],
        interceptor: OutboundEffectInterceptor | None = None,
        *,
        caller: str,
        cost_estimator: Callable[[str, str, dict[str, Any]], float] | None = None,
    ) -> None:
        self._interceptor = resolve_interceptor(interceptor)
        self._caller = str(caller)
        self._cost_estimator = cost_estimator
        self._request = _governed(self._interceptor, self._effect_builder, request_fn)

    def _effect_builder(
        self, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> OutboundEffect:
        # request(method, url, ...) -- method/url may be positional or keyword.
        method = kwargs.get("method", args[0] if len(args) >= 1 else "")
        url = kwargs.get("url", args[1] if len(args) >= 2 else "")
        cost = 0.0
        if self._cost_estimator is not None:
            cost = float(self._cost_estimator(str(method), str(url), kwargs))
        return OutboundEffect(
            kind=EffectKind.HTTP,
            operation=f"http.{str(method).upper()}",
            # Redact credentials (userinfo + query) before the URL becomes the
            # audit target -- it flows verbatim into the audit trail otherwise.
            target=redact_http_target(str(url)),
            cost_estimate=cost,
            caller=self._caller,
        )

    def request(self, method: str, url: str, **kwargs: Any) -> Any:
        """Issue a governed HTTP request. Same shape as the wrapped transport."""
        return self._request(method, url, **kwargs)
