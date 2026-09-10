# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
A2A bearer-token verification regression tests.

Before this shard, `JsonRpcHandler.handle` tested the bearer token for
truthiness and discarded it. `A2AAuthenticator.verify_token` — which checks the
Ed25519 signature, expiry, audience and trust chain — had no call site in the
request path, so ``'AAAA'``, ``' '`` and any other non-empty string
authenticated every protected method, including `trust.delegate` and
`audit.query`.

The load-bearing test here is `test_arbitrary_bearer_string_is_rejected`: it
fails against the pre-shard code and passes after, which is what makes the rest
of this file evidence rather than decoration.

These are Tier 1 — the verifier is exercised through a deterministic adapter
satisfying the `TokenVerifier` Protocol, not a mock of one. Per `testing.md`
§ "Protocol Adapters", a class satisfying a `typing.Protocol` at runtime with
deterministic output is not a mock. The real Ed25519 path is covered by the
kaizen Tier 2 integration suite, which mints genuine tokens.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from kailash.trust.a2a.auth import CallerIdentity
from kailash.trust.a2a.exceptions import (
    AuthenticationError,
    InvalidTokenError,
    TokenExpiredError,
)
from kailash.trust.a2a.jsonrpc import JsonRpcHandler
from kailash.trust.a2a.models import A2AToken

THIS_AGENT = "agent-under-test"
VALID_TOKEN = "valid-signed-token-for-this-agent"
OTHER_AUDIENCE_TOKEN = "valid-signed-token-for-a-different-agent"
EXPIRED_TOKEN = "expired-but-well-formed-token"


def _claims(sub: str, aud: str) -> A2AToken:
    now = datetime.now(timezone.utc)
    return A2AToken(
        sub=sub,
        iss=sub,
        aud=aud,
        exp=now + timedelta(hours=1),
        iat=now,
        jti="jti-1",
        authority_id="org-001",
        trust_chain_hash="chainhash",
        capabilities=["invoke"],
    )


class DeterministicVerifier:
    """Satisfies the `TokenVerifier` Protocol with fixed, deterministic rules.

    Accepts exactly one token for this agent, one minted for a different
    audience, and one expired token; RAISES on everything else — which is the
    contract the Protocol documents and the property under test.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    async def verify_token(
        self,
        token: str,
        expected_audience: str | None = None,
        verify_trust: bool = True,
    ) -> A2AToken:
        self.calls.append((token, expected_audience))

        if token == EXPIRED_TOKEN:
            raise TokenExpiredError()
        if token == OTHER_AUDIENCE_TOKEN:
            claims = _claims("caller-agent", "some-other-agent")
        elif token == VALID_TOKEN:
            claims = _claims("caller-agent", THIS_AGENT)
        else:
            raise InvalidTokenError("Invalid token signature")

        if expected_audience and claims.aud != expected_audience:
            raise InvalidTokenError(
                f"Token audience mismatch: expected {expected_audience}, "
                f"got {claims.aud}"
            )
        return claims


def _handler(**kwargs) -> tuple[JsonRpcHandler, list]:
    """A handler with one public and one protected method registered."""
    seen: list = []

    async def protected(params, caller):
        seen.append(caller)
        return {"ok": True}

    async def public(params, caller):
        seen.append(caller)
        return {"ok": True}

    rpc = JsonRpcHandler(**kwargs)
    rpc.register_method("trust.delegate", protected)
    rpc.register_method("agent.capabilities", public)
    return rpc, seen


def _request(method: str):
    return {"jsonrpc": "2.0", "id": 1, "method": method, "params": {}}


# --------------------------------------------------------------------------
# The regression this shard exists for
# --------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bogus", ["AAAA", " ", "not-a-jwt-at-all", "Bearer", "null", "0"]
)
async def test_arbitrary_bearer_string_is_rejected(bogus):
    """An unsigned string MUST NOT authenticate a protected method.

    Fails against the pre-shard code, where `handle` only checked truthiness.
    """
    rpc, seen = _handler(
        token_verifier=DeterministicVerifier(), expected_audience=THIS_AGENT
    )
    response = await rpc.handle(_request("trust.delegate"), bogus)

    assert response.error is not None, f"{bogus!r} authenticated — auth is bypassed"
    assert response.result is None
    assert seen == [], "handler ran despite an unverifiable token"


@pytest.mark.regression
@pytest.mark.asyncio
async def test_valid_token_still_reaches_the_handler():
    """Negative control for the test above: a good token MUST get through.

    Without this, a handler that rejected everything would pass the bypass test
    and the suite could not tell "secure" from "broken".
    """
    rpc, seen = _handler(
        token_verifier=DeterministicVerifier(), expected_audience=THIS_AGENT
    )
    response = await rpc.handle(_request("trust.delegate"), VALID_TOKEN)

    assert response.error is None, f"valid token rejected: {response.error}"
    assert response.result == {"ok": True}
    assert len(seen) == 1


# --------------------------------------------------------------------------
# Identity propagation
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handler_receives_verified_identity_not_a_raw_token():
    rpc, seen = _handler(
        token_verifier=DeterministicVerifier(), expected_audience=THIS_AGENT
    )
    await rpc.handle(_request("trust.delegate"), VALID_TOKEN)

    caller = seen[0]
    assert isinstance(caller, CallerIdentity)
    assert not isinstance(caller, str), "handler still receives a raw token"
    assert caller.agent_id == "caller-agent"
    assert caller.token == VALID_TOKEN
    assert caller.claims.aud == THIS_AGENT


@pytest.mark.asyncio
async def test_caller_identity_is_immutable():
    """A handler must not be able to edit the identity it was handed."""
    rpc, seen = _handler(
        token_verifier=DeterministicVerifier(), expected_audience=THIS_AGENT
    )
    await rpc.handle(_request("trust.delegate"), VALID_TOKEN)

    with pytest.raises(Exception):
        seen[0].agent_id = "someone-else"


@pytest.mark.asyncio
async def test_public_method_gets_none_and_needs_no_token():
    rpc, seen = _handler(
        token_verifier=DeterministicVerifier(), expected_audience=THIS_AGENT
    )
    response = await rpc.handle(_request("agent.capabilities"), None)

    assert response.error is None
    assert seen == [None], "public method should receive no caller identity"


# --------------------------------------------------------------------------
# Token properties that must be enforced
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_token_minted_for_another_agent_is_rejected():
    """Audience pinning: a token for another agent MUST NOT be replayable here."""
    rpc, seen = _handler(
        token_verifier=DeterministicVerifier(), expected_audience=THIS_AGENT
    )
    response = await rpc.handle(_request("trust.delegate"), OTHER_AUDIENCE_TOKEN)

    assert response.error is not None
    assert seen == []


@pytest.mark.asyncio
async def test_expired_token_is_rejected():
    rpc, seen = _handler(
        token_verifier=DeterministicVerifier(), expected_audience=THIS_AGENT
    )
    response = await rpc.handle(_request("trust.delegate"), EXPIRED_TOKEN)

    assert response.error is not None
    assert seen == []


@pytest.mark.asyncio
async def test_expected_audience_is_actually_passed_to_the_verifier():
    """Guards against wiring the verifier but forgetting the audience pin."""
    verifier = DeterministicVerifier()
    rpc, _ = _handler(token_verifier=verifier, expected_audience=THIS_AGENT)
    await rpc.handle(_request("trust.delegate"), VALID_TOKEN)

    assert verifier.calls == [(VALID_TOKEN, THIS_AGENT)]


@pytest.mark.asyncio
async def test_missing_token_still_rejected():
    rpc, seen = _handler(
        token_verifier=DeterministicVerifier(), expected_audience=THIS_AGENT
    )
    response = await rpc.handle(_request("trust.delegate"), None)

    assert response.error is not None
    assert response.error["code"] == -40002
    assert seen == []


# --------------------------------------------------------------------------
# Audience pin — needs its OWN enforcement surface
# --------------------------------------------------------------------------


class AudienceIgnoringVerifier:
    """A conformant-looking verifier that ignores `expected_audience`.

    Legitimate shape: `TokenVerifier` is a Protocol a deployment may implement
    itself. If the audience pin lives ONLY inside the verifier, such an
    implementation silently disables it with nothing else to catch it.
    """

    async def verify_token(
        self,
        token: str,
        expected_audience: str | None = None,
        verify_trust: bool = True,
    ) -> A2AToken:
        return _claims("caller-agent", "a-completely-different-agent")


@pytest.mark.regression
@pytest.mark.asyncio
async def test_audience_reasserted_even_if_the_verifier_ignores_it():
    """Enforcement-surface parity: the handler re-checks `aud` itself."""
    rpc, seen = _handler(
        token_verifier=AudienceIgnoringVerifier(), expected_audience=THIS_AGENT
    )
    response = await rpc.handle(_request("trust.delegate"), VALID_TOKEN)

    assert response.error is not None, (
        "a token for another audience was accepted because the only audience "
        "check lived inside the verifier"
    )
    assert "audience mismatch" in response.error["message"]
    assert seen == []


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("audience", [None, ""])
async def test_missing_expected_audience_fails_closed(audience):
    """No audience to pin against means the pin cannot fire — so refuse.

    `verify_token` skips the audience check on a falsy `expected_audience`,
    so verifying a signature without one is not authentication for THIS agent.
    """
    rpc, seen = _handler(
        token_verifier=DeterministicVerifier(), expected_audience=audience
    )
    response = await rpc.handle(_request("trust.delegate"), VALID_TOKEN)

    assert response.error is not None
    assert "expected_audience is not configured" in response.error["message"]
    assert seen == []


# --------------------------------------------------------------------------
# Fail-closed default (security.md § Secure-Default)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_verifier_configured_fails_closed():
    """The default with no verifier is REFUSE, not accept-anything."""
    rpc, seen = _handler()
    response = await rpc.handle(_request("trust.delegate"), "any-token")

    assert response.error is not None
    assert "verification is not configured" in response.error["message"]
    assert seen == []


@pytest.mark.asyncio
async def test_no_verifier_still_serves_public_methods():
    """Failing closed must not break unauthenticated public methods."""
    rpc, seen = _handler()
    response = await rpc.handle(_request("agent.capabilities"), None)

    assert response.error is None
    assert seen == [None]


@pytest.mark.asyncio
async def test_unverified_opt_in_is_explicit_and_warns_once(caplog):
    """The escape hatch works, is opt-in, and is loud."""
    rpc, seen = _handler(allow_unverified_tokens=True)

    with caplog.at_level("WARNING"):
        first = await rpc.handle(_request("trust.delegate"), "anything")
        second = await rpc.handle(_request("trust.delegate"), "anything-else")

    assert first.error is None, "explicit opt-in should permit the call"
    assert second.error is None
    assert len(seen) == 2
    assert seen == [None, None], "unverified mode must not fabricate an identity"

    warnings = [
        r for r in caplog.records if r.message == "a2a.auth.unverified_tokens_enabled"
    ]
    assert len(warnings) == 1, f"expected exactly one warning, got {len(warnings)}"


@pytest.mark.asyncio
async def test_unverified_opt_in_still_requires_a_token():
    """The escape hatch relaxes VERIFICATION, never the requirement itself."""
    rpc, seen = _handler(allow_unverified_tokens=True)
    response = await rpc.handle(_request("trust.delegate"), None)

    assert response.error is not None
    assert seen == []


# --------------------------------------------------------------------------
# The verification error must survive the JSON-RPC envelope
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verification_failure_is_an_auth_error_not_a_500():
    """A bad token is the caller's fault; -32603 would blame the server."""
    rpc, _ = _handler(
        token_verifier=DeterministicVerifier(), expected_audience=THIS_AGENT
    )
    response = await rpc.handle(_request("trust.delegate"), "forged")

    assert response.error is not None
    assert response.error["code"] != -32603, "verification failure surfaced as a 500"


@pytest.mark.asyncio
async def test_batch_requests_are_authenticated_per_element():
    """Batch must not be an auth bypass."""
    rpc, seen = _handler(
        token_verifier=DeterministicVerifier(), expected_audience=THIS_AGENT
    )
    responses = await rpc.handle_batch(
        [_request("trust.delegate"), _request("trust.delegate")], "bogus-token"
    )

    assert len(responses) == 2
    assert all(r.error is not None for r in responses)
    assert seen == []


@pytest.mark.asyncio
async def test_direct_authenticate_raises_for_unknown_protected_method():
    """An unregistered method is still protected — auth precedes dispatch."""
    rpc, _ = _handler(
        token_verifier=DeterministicVerifier(), expected_audience=THIS_AGENT
    )
    with pytest.raises(AuthenticationError):
        await rpc._authenticate("some.unregistered.method", None)
