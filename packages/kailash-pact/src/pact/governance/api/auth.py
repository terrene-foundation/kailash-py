# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Authentication and authorization for governance API endpoints.

Provides scope-based access control for governance operations:
- governance:read  -- query org structure, check access, verify actions
- governance:write -- grant clearance, create bridges, create KSPs
- governance:admin -- all operations including configuration changes

Token verification uses constant-time comparison via hmac.compare_digest()
to prevent timing side-channel attacks (per trust-plane-security.md rule).

Dev mode: When no API token is configured, authentication is disabled
for local development. This matches the existing server.py behavior.

IDENTITY IS NOT A PRINCIPAL (issue #2194)
-----------------------------------------
Authentication here is a single SHARED bearer token, so :meth:`GovernanceAuth.
verify_token` returns one of two CONSTANTS -- ``"authenticated"`` or
``"anonymous"``. Neither names a principal, and neither is a D/T/R role
address. Every caller holding the token is indistinguishable from every
other.

Consequences, which callers of this module MUST respect:

* An actor / approver / grantor role address CANNOT be server-derived
  (``security.md`` § Identity-derivation parity). Endpoints that need one
  take it from the request body, where it is an UNVERIFIED CLAIM.
* Such a claim MUST be recorded in a grammar that marks it unverified --
  see :data:`UNVERIFIED_CLAIM_PREFIX` and :func:`unverified_actor_claim` --
  so no durable record or audit event presents a caller assertion in the
  same grammar as a server-derived fact.
* Comparing a body-supplied role address against ``identity`` would compare
  it against a constant. That is not an authorization check and MUST NOT be
  written. The authorization model is a structural decision open in #2194.

The scopes below are DECLARATIVE, not enforced: ``_verify_from_request``
logs the requested scope but verifies the same single token for all three,
so ``require_admin`` currently grants no more protection than
``require_read``. Fixing that is part of the same #2194 decision.
"""

from __future__ import annotations

import hmac
import logging
import os

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

__all__ = [
    "GovernanceAuth",
    "UNVERIFIED_CLAIM_PREFIX",
    "identity_names_a_principal",
    "unverified_actor_claim",
]


_UNSET = object()
"""Sentinel to distinguish 'not passed' from 'explicitly None'."""


UNVERIFIED_CLAIM_PREFIX = "unverified-claim:"
"""Marks a role address the server did NOT verify the caller holds (#2194).

An actor address supplied in a request body is an assertion, not a fact. It
is recorded prefixed with this marker so that a durable record -- a stored
``RoleClearance``, a ``KnowledgeSharePolicy``, a backup export, the sqlite
``granted_by`` / ``created_by`` column -- cannot be read as an authenticated
grant. The claimed address is preserved verbatim after the prefix; nothing
is discarded.

This follows the existing in-repo convention for a provenance value that is
not a role: ``kailash.trust.pact.yaml_resolvers._YAML_ORG_AUTHORITY``
("yaml-org-definition") occupies the same field for clearances and KSPs
materialised from a YAML org definition.

When per-principal identity lands (#2194 option 1) the prefix disappears
because the address becomes server-derived. Stored records written before
that point stay correctly marked.
"""

_NON_PRINCIPAL_IDENTITIES = frozenset({"authenticated", "anonymous"})
"""Every value :meth:`GovernanceAuth.verify_token` can currently return."""


def identity_names_a_principal(identity: str) -> bool:
    """Return True iff ``identity`` identifies one specific caller.

    Under the shared-token scheme this is always False: ``verify_token``
    returns ``"authenticated"`` or ``"anonymous"``, both of which every
    caller shares. It exists so that the premise of #2194 is asserted in one
    place rather than assumed at each call site -- when token issuance grows
    per-principal identities this starts returning True, and the endpoints
    that depend on the premise fail loudly instead of silently continuing to
    record caller assertions.

    Args:
        identity: The value returned by :meth:`GovernanceAuth.verify_token`.

    Returns:
        True if the identity names a specific principal, False if it is one
        of the shared constants.
    """
    return bool(identity) and identity not in _NON_PRINCIPAL_IDENTITIES


def unverified_actor_claim(
    claimed_role_address: str,
    identity: str,
    *,
    field: str,
) -> tuple[str, dict[str, object]]:
    """Render a body-supplied actor address as an explicitly unverified claim.

    This is an HONESTY transformation, not an authorization check. It does
    not decide whether the caller may claim the address -- nothing in the
    current auth scheme can decide that (#2194). It only ensures the claim
    and the one server-derived fact about the caller are recorded in
    DIFFERENT grammars.

    Args:
        claimed_role_address: The D/T/R address asserted in the request body.
            Already validated for shape by the request schema.
        identity: The server-derived identity from the auth dependency.
        field: Base name of the actor field, e.g. ``"granted_by"``. Used to
            key the claim in the audit payload.

    Returns:
        A ``(recorded_value, audit_fields)`` pair.

        ``recorded_value`` is what to write into the durable audit-trail
        field: the claimed address prefixed with
        :data:`UNVERIFIED_CLAIM_PREFIX` while no principal identity exists,
        and the bare address once one does.

        ``audit_fields`` are keys to merge into a governance event payload:
        ``<field>_claimed`` (the assertion, verbatim), ``actor_verified``
        (False while the actor cannot be derived) and
        ``authenticated_identity`` (what the server actually established).

    Raises:
        ValueError: If ``field`` is empty.
    """
    if not field:
        raise ValueError("field must be a non-empty actor field name")

    verified = identity_names_a_principal(identity)
    recorded = (
        claimed_role_address
        if verified
        else f"{UNVERIFIED_CLAIM_PREFIX}{claimed_role_address}"
    )
    audit_fields: dict[str, object] = {
        f"{field}_claimed": claimed_role_address,
        "actor_verified": verified,
        "authenticated_identity": identity,
    }
    return recorded, audit_fields


class GovernanceAuth:
    """Authorization for governance endpoints.

    Declares three scopes:
    - governance:read  -- GET endpoints and POST check/verify
    - governance:write -- POST endpoints that mutate state
    - governance:admin -- all operations

    The scopes are NOT separately enforced. ``_verify_from_request`` logs the
    requested scope and then verifies the same single shared token for all
    three, so any caller holding that token satisfies ``require_admin`` as
    readily as ``require_read``. Scope separation needs per-principal token
    issuance, which is the open #2194 decision.

    Token resolution order (when api_token is not passed):
    1. PACT_GOVERNANCE_API_TOKEN environment variable
    2. PACT_API_TOKEN environment variable (fallback)
    3. None -- dev mode, auth disabled

    When api_token is explicitly provided (including None), env vars
    are NOT consulted. This allows tests to force dev mode by passing
    api_token=None.
    """

    SCOPES = frozenset({"governance:read", "governance:write", "governance:admin"})

    def __init__(self, api_token: str | None = _UNSET) -> None:  # type: ignore[assignment]
        if api_token is not _UNSET:
            # Explicit value provided (could be a string or None)
            self._api_token: str | None = api_token
        else:
            # Not provided -- resolve from environment
            self._api_token = (
                os.environ.get("PACT_GOVERNANCE_API_TOKEN")
                or os.environ.get("PACT_API_TOKEN")
                or None
            )

        if self._api_token:
            logger.info("GovernanceAuth initialized with API token authentication")
        else:
            logger.warning(
                "GovernanceAuth initialized without API token -- "
                "auth is disabled (dev mode). Set PACT_GOVERNANCE_API_TOKEN "
                "or PACT_API_TOKEN to enable."
            )

    def verify_token(self, token: str | None) -> str:
        """Verify a bearer token and return the identity string.

        The returned value is a CONSTANT, not a principal: one shared token
        authenticates every caller, so the result carries no information
        about WHICH caller presented it. Do not compare it to a role address
        and do not treat it as an actor -- see the module docstring and
        :func:`identity_names_a_principal` (#2194).

        Args:
            token: The bearer token from the Authorization header,
                or None if no token was provided.

        Returns:
            Identity string: "authenticated" for valid tokens,
            "anonymous" for dev mode. Never a D/T/R role address.

        Raises:
            HTTPException: 401 if token is invalid or missing when required.
        """
        # Dev mode: no API token configured
        if not self._api_token:
            return "anonymous"

        # Token required but not provided
        if not token:
            raise HTTPException(
                status_code=401,
                detail="Authentication required: provide Bearer token in Authorization header",
            )

        # Constant-time comparison to prevent timing attacks
        if hmac.compare_digest(token, self._api_token):
            return "authenticated"

        raise HTTPException(
            status_code=401,
            detail="Invalid API token",
        )

    async def require_read(self, request: Request) -> str:
        """Declare governance:read scope. Used as FastAPI dependency.

        Verifies the shared bearer token and records the requested scope.
        The scope is NOT separately enforced -- see the class docstring.

        Args:
            request: The incoming HTTP request.

        Returns:
            Identity string for the authenticated caller.

        Raises:
            HTTPException: 401 if authentication fails.
        """
        return self._verify_from_request(request, "governance:read")

    async def require_write(self, request: Request) -> str:
        """Declare governance:write scope. Used as FastAPI dependency.

        Verifies the shared bearer token and records the requested scope.
        The scope is NOT separately enforced -- see the class docstring.

        Args:
            request: The incoming HTTP request.

        Returns:
            Identity string for the authenticated caller.

        Raises:
            HTTPException: 401 if authentication fails.
        """
        return self._verify_from_request(request, "governance:write")

    async def require_admin(self, request: Request) -> str:
        """Declare governance:admin scope. Used as FastAPI dependency.

        Verifies the shared bearer token and records the requested scope.
        The scope is NOT separately enforced -- see the class docstring.

        Args:
            request: The incoming HTTP request.

        Returns:
            Identity string for the authenticated caller.

        Raises:
            HTTPException: 401 if authentication fails.
        """
        return self._verify_from_request(request, "governance:admin")

    def _verify_from_request(self, request: Request, scope: str) -> str:
        """Extract bearer token from request and verify.

        Args:
            request: The incoming HTTP request.
            scope: The requested scope. Logged for audit only; the same
                single shared token is verified regardless of its value.

        Returns:
            Identity string for the authenticated caller.

        Raises:
            HTTPException: 401 if authentication fails.
        """
        auth_header = request.headers.get("authorization", "")
        token: str | None = None
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:]  # Strip "Bearer " prefix

        identity = self.verify_token(token)

        logger.debug(
            "Governance auth: identity=%s scope=%s path=%s",
            identity,
            scope,
            request.url.path,
        )
        return identity
