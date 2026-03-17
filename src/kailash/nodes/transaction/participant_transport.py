"""Participant transport abstraction for Two-Phase Commit protocol.

Defines the transport layer used by the 2PC coordinator to communicate with
participants during prepare, commit, and abort phases. Ships with two
implementations:

- LocalNodeTransport: executes participant nodes in-process via NodeExecutor
- HttpTransport: makes real HTTP calls to participant endpoints via aiohttp

Copyright 2026 Terrene Foundation
SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

import ipaddress
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, Optional, Protocol, runtime_checkable
from urllib.parse import urlparse

import aiohttp

if TYPE_CHECKING:
    from kailash.nodes.transaction.two_phase_commit import TwoPhaseCommitParticipant

logger = logging.getLogger(__name__)

# Private IP ranges and reserved addresses blocked to prevent SSRF
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


def _validate_url(url: str) -> None:
    """Raise ValueError if url targets a private/reserved IP or non-http(s) scheme.

    Resolves hostnames to IPs to prevent DNS rebinding attacks.
    """
    import socket

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"URL scheme '{parsed.scheme}' is not allowed; use http or https"
        )
    host = parsed.hostname
    if host is None:
        raise ValueError(f"URL '{url}' has no host")

    def _check_addr(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
        for network in _BLOCKED_NETWORKS:
            if addr in network:
                raise ValueError(
                    f"URL '{url}' resolves to a private/reserved address and is blocked"
                )

    try:
        # Direct IP literal
        addr = ipaddress.ip_address(host)
        _check_addr(addr)
    except ValueError:
        # Hostname — resolve to IP and check all addresses
        try:
            addrinfos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
            for family, _, _, _, sockaddr in addrinfos:
                resolved_ip = ipaddress.ip_address(sockaddr[0])
                _check_addr(resolved_ip)
        except socket.gaierror:
            # DNS resolution failed — allow (will fail at connection time)
            pass


__all__ = [
    "ParticipantTransport",
    "LocalNodeTransport",
    "HttpTransport",
    "TransportResult",
]


@dataclass(frozen=True)
class TransportResult:
    """Result from a transport operation (prepare/commit/abort).

    Attributes:
        success: Whether the operation succeeded.
        vote: For prepare operations, the participant's vote
              ("prepared" or "abort"). None for commit/abort results.
        error: Human-readable error description when success is False.
        details: Additional response data from the participant.
    """

    success: bool
    vote: Optional[str] = None
    error: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


@runtime_checkable
class ParticipantTransport(Protocol):
    """Protocol for 2PC participant communication.

    Implementations carry prepare, commit, and abort messages between the
    coordinator and remote (or local) participants.  Every method returns a
    ``TransportResult`` so the coordinator can update participant state
    without knowing the underlying transport mechanism.
    """

    async def prepare(
        self,
        participant: TwoPhaseCommitParticipant,
        transaction_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> TransportResult:
        """Ask the participant to prepare for commit.

        Args:
            participant: The target participant.
            transaction_id: Globally unique transaction identifier.
            context: Optional transaction context data forwarded to the
                     participant so it can evaluate its vote.

        Returns:
            TransportResult with ``vote`` set to ``"prepared"`` or
            ``"abort"``.
        """
        ...

    async def commit(
        self,
        participant: TwoPhaseCommitParticipant,
        transaction_id: str,
    ) -> TransportResult:
        """Tell the participant to commit its prepared work.

        Args:
            participant: The target participant.
            transaction_id: Globally unique transaction identifier.

        Returns:
            TransportResult indicating success or failure.
        """
        ...

    async def abort(
        self,
        participant: TwoPhaseCommitParticipant,
        transaction_id: str,
    ) -> TransportResult:
        """Tell the participant to abort (roll back) its prepared work.

        Args:
            participant: The target participant.
            transaction_id: Globally unique transaction identifier.

        Returns:
            TransportResult indicating success or failure.
        """
        ...


class LocalNodeTransport:
    """Executes participant nodes in the same process using ``NodeExecutor``.

    This transport is the default for single-process deployments.  Each
    participant's ``participant_id`` is treated as the ``node_type`` passed to
    the ``NodeExecutor.execute()`` method.  The 2PC phase (prepare / commit /
    abort) is forwarded as the ``operation`` parameter so the participant node
    can branch on it.

    Usage::

        from kailash.nodes.transaction.node_executor import RegistryNodeExecutor
        transport = LocalNodeTransport(RegistryNodeExecutor())

    If no ``NodeExecutor`` is provided the transport falls back to a built-in
    no-op mode that always votes *prepared* and commits successfully.  This
    preserves backward-compatible behaviour with the original simulated
    implementation while allowing callers to inject real executors.
    """

    def __init__(self, executor: Any = None) -> None:
        """Initialise with an optional ``NodeExecutor``.

        Args:
            executor: An object implementing the ``NodeExecutor`` protocol
                      (i.e. an ``async execute(node_type, params, timeout)``
                      method).  When *None*, a default always-succeed mode
                      is used.
        """
        self._executor = executor

    async def prepare(
        self,
        participant: TwoPhaseCommitParticipant,
        transaction_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> TransportResult:
        """Execute the participant's prepare logic locally."""
        pid = participant.participant_id
        logger.info("LocalNodeTransport: PREPARE %s for tx %s", pid, transaction_id)

        if self._executor is None:
            # Default no-op: always vote prepared (backward-compatible)
            return TransportResult(success=True, vote="prepared")

        try:
            result = await self._executor.execute(
                pid,
                {
                    "operation": "prepare",
                    "transaction_id": transaction_id,
                    "context": context or {},
                },
                timeout=float(participant.timeout),
            )
            vote = (
                result.get("vote", "prepared")
                if isinstance(result, dict)
                else "prepared"
            )
            return TransportResult(
                success=True,
                vote=vote,
                details=result if isinstance(result, dict) else None,
            )
        except Exception as exc:
            logger.error(
                "LocalNodeTransport: PREPARE failed for %s: %s",
                pid,
                exc,
            )
            return TransportResult(success=False, vote="abort", error=str(exc))

    async def commit(
        self,
        participant: TwoPhaseCommitParticipant,
        transaction_id: str,
    ) -> TransportResult:
        """Execute the participant's commit logic locally."""
        pid = participant.participant_id
        logger.info("LocalNodeTransport: COMMIT %s for tx %s", pid, transaction_id)

        if self._executor is None:
            return TransportResult(success=True)

        try:
            result = await self._executor.execute(
                pid,
                {
                    "operation": "commit",
                    "transaction_id": transaction_id,
                },
                timeout=float(participant.timeout),
            )
            return TransportResult(
                success=True,
                details=result if isinstance(result, dict) else None,
            )
        except Exception as exc:
            logger.error(
                "LocalNodeTransport: COMMIT failed for %s: %s",
                pid,
                exc,
            )
            return TransportResult(success=False, error=str(exc))

    async def abort(
        self,
        participant: TwoPhaseCommitParticipant,
        transaction_id: str,
    ) -> TransportResult:
        """Execute the participant's abort logic locally."""
        pid = participant.participant_id
        logger.info("LocalNodeTransport: ABORT %s for tx %s", pid, transaction_id)

        if self._executor is None:
            return TransportResult(success=True)

        try:
            result = await self._executor.execute(
                pid,
                {
                    "operation": "abort",
                    "transaction_id": transaction_id,
                },
                timeout=float(participant.timeout),
            )
            return TransportResult(
                success=True,
                details=result if isinstance(result, dict) else None,
            )
        except Exception as exc:
            logger.warning(
                "LocalNodeTransport: ABORT failed for %s: %s",
                pid,
                exc,
            )
            return TransportResult(success=False, error=str(exc))


class HttpTransport:
    """Makes real HTTP calls to participant endpoints via ``aiohttp``.

    Each participant's ``endpoint`` field is treated as a base URL.  The
    transport appends ``/prepare``, ``/commit``, or ``/abort`` to form the
    request URL.

    The expected participant HTTP API contract:

    **POST <endpoint>/prepare**
        Request body: ``{"transaction_id": "...", "context": {...}}``
        Response 200: ``{"vote": "prepared"}``
        Response 4xx/5xx or ``{"vote": "abort"}``: participant votes abort.

    **POST <endpoint>/commit**
        Request body: ``{"transaction_id": "..."}``
        Response 200: ``{"status": "committed"}``

    **POST <endpoint>/abort**
        Request body: ``{"transaction_id": "..."}``
        Response 200: ``{"status": "aborted"}``

    The transport respects each participant's ``timeout`` attribute and
    ``retry_count`` for transient failures.
    """

    def __init__(
        self,
        session: Optional[aiohttp.ClientSession] = None,
        default_timeout: float = 30.0,
        allow_private_urls: bool = False,
    ) -> None:
        """Initialise with an optional pre-existing ``aiohttp.ClientSession``.

        Args:
            session: An existing session to reuse.  When *None* a new
                     session is created per call (less efficient but safe
                     for short-lived coordinators).
            default_timeout: Fallback timeout in seconds if the participant
                             does not specify one.
        """
        self._session = session
        self._owns_session = session is None
        self._default_timeout = default_timeout
        self._allow_private_urls = allow_private_urls

    async def _get_session(self) -> aiohttp.ClientSession:
        """Return the shared session, creating one if necessary."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._owns_session = True
        return self._session

    async def close(self) -> None:
        """Close the owned session if one was created internally."""
        if (
            self._owns_session
            and self._session is not None
            and not self._session.closed
        ):
            await self._session.close()
            self._session = None

    async def __aenter__(self) -> "HttpTransport":
        """Enter async context manager."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context manager and close the session."""
        await self.close()

    async def prepare(
        self,
        participant: TwoPhaseCommitParticipant,
        transaction_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> TransportResult:
        """Send an HTTP POST to ``<endpoint>/prepare``."""
        url = f"{participant.endpoint.rstrip('/')}/prepare"
        if not self._allow_private_urls:
            _validate_url(url)
        payload = {"transaction_id": transaction_id, "context": context or {}}
        timeout = aiohttp.ClientTimeout(
            total=participant.timeout or self._default_timeout
        )

        session = await self._get_session()
        last_error: Optional[str] = None

        for attempt in range(max(1, participant.retry_count)):
            try:
                logger.info(
                    "HttpTransport: PREPARE %s (attempt %d/%d)",
                    participant.participant_id,
                    attempt + 1,
                    participant.retry_count,
                )
                async with session.post(url, json=payload, timeout=timeout) as resp:
                    body = await resp.json()

                    if resp.status >= 400:
                        vote = (
                            body.get("vote", "abort")
                            if isinstance(body, dict)
                            else "abort"
                        )
                        return TransportResult(
                            success=False,
                            vote=vote,
                            error=f"HTTP {resp.status}: {body}",
                            details=body if isinstance(body, dict) else None,
                        )

                    vote = (
                        body.get("vote", "prepared")
                        if isinstance(body, dict)
                        else "prepared"
                    )
                    return TransportResult(
                        success=True,
                        vote=vote,
                        details=body if isinstance(body, dict) else None,
                    )

            except (aiohttp.ClientError, TimeoutError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "HttpTransport: PREPARE %s attempt %d failed: %s",
                    participant.participant_id,
                    attempt + 1,
                    last_error,
                )

        # All retries exhausted
        return TransportResult(success=False, vote="abort", error=last_error)

    async def commit(
        self,
        participant: TwoPhaseCommitParticipant,
        transaction_id: str,
    ) -> TransportResult:
        """Send an HTTP POST to ``<endpoint>/commit``."""
        url = f"{participant.endpoint.rstrip('/')}/commit"
        if not self._allow_private_urls:
            _validate_url(url)
        payload = {"transaction_id": transaction_id}
        timeout = aiohttp.ClientTimeout(
            total=participant.timeout or self._default_timeout
        )

        session = await self._get_session()
        last_error: Optional[str] = None

        for attempt in range(max(1, participant.retry_count)):
            try:
                logger.info(
                    "HttpTransport: COMMIT %s (attempt %d/%d)",
                    participant.participant_id,
                    attempt + 1,
                    participant.retry_count,
                )
                async with session.post(url, json=payload, timeout=timeout) as resp:
                    body = await resp.json()

                    if resp.status >= 400:
                        error_msg = f"HTTP {resp.status}: {body}"
                        # Commit failures on last retry are final
                        if attempt == participant.retry_count - 1:
                            return TransportResult(
                                success=False,
                                error=error_msg,
                                details=body if isinstance(body, dict) else None,
                            )
                        last_error = error_msg
                        continue

                    return TransportResult(
                        success=True,
                        details=body if isinstance(body, dict) else None,
                    )

            except (aiohttp.ClientError, TimeoutError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "HttpTransport: COMMIT %s attempt %d failed: %s",
                    participant.participant_id,
                    attempt + 1,
                    last_error,
                )

        return TransportResult(success=False, error=last_error)

    async def abort(
        self,
        participant: TwoPhaseCommitParticipant,
        transaction_id: str,
    ) -> TransportResult:
        """Send an HTTP POST to ``<endpoint>/abort``."""
        url = f"{participant.endpoint.rstrip('/')}/abort"
        if not self._allow_private_urls:
            _validate_url(url)
        payload = {"transaction_id": transaction_id}
        timeout = aiohttp.ClientTimeout(
            total=participant.timeout or self._default_timeout
        )

        session = await self._get_session()
        last_error: Optional[str] = None

        for attempt in range(max(1, participant.retry_count)):
            try:
                logger.info(
                    "HttpTransport: ABORT %s (attempt %d/%d)",
                    participant.participant_id,
                    attempt + 1,
                    participant.retry_count,
                )
                async with session.post(url, json=payload, timeout=timeout) as resp:
                    body = await resp.json()

                    if resp.status >= 400:
                        error_msg = f"HTTP {resp.status}: {body}"
                        if attempt == participant.retry_count - 1:
                            return TransportResult(
                                success=False,
                                error=error_msg,
                                details=body if isinstance(body, dict) else None,
                            )
                        last_error = error_msg
                        continue

                    return TransportResult(
                        success=True,
                        details=body if isinstance(body, dict) else None,
                    )

            except (aiohttp.ClientError, TimeoutError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "HttpTransport: ABORT %s attempt %d failed: %s",
                    participant.participant_id,
                    attempt + 1,
                    last_error,
                )

        return TransportResult(success=False, error=last_error)
