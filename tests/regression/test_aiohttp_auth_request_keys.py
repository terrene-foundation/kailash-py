# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Typed request identity and legacy aliases on every authentication path.

Positive pole: verified JWT/API-key identities reach a real HTTP handler with
both key APIs referencing the same values. Negative pole: rejected credentials
never reach that handler. Warning controls reject any expanded filter scope.
"""

import warnings

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer, make_mocked_request
from aiohttp.web_exceptions import NotAppKeyWarning

from kailash.trust.auth import aiohttp as auth
from kailash.trust.auth.jwt import JWTConfig, JWTValidator
from kailash.trust.auth.models import AuthenticatedUser

pytestmark = pytest.mark.regression

_SECRET = "aiohttp-request-keys-regression-secret-at-least-32-bytes"
_RECOMMENDATION = (
    "It is recommended to use web.RequestKey instances for keys.\n"
    "https://docs.aiohttp.org/en/stable/web_advanced.html#request-s-storage"
)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["jwt", "api_key_payload", "api_key_boolean"])
async def test_verified_identity_has_typed_and_legacy_keys(mode):
    def validate_key(key):
        if key != "regression-key":
            return False
        if mode == "api_key_payload":
            return {"sub": "key-user", "roles": ["reader"]}
        return True

    config = JWTConfig(
        secret=_SECRET,
        api_key_enabled=mode != "jwt",
        api_key_validator=validate_key,
    )
    expected_user = {
        "jwt": "jwt-user",
        "api_key_payload": "key-user",
        "api_key_boolean": "apikey",
    }[mode]
    reached = []

    async def handler(request):
        user = request[auth.AUTH_USER_KEY]
        payload = request[auth.AUTH_TOKEN_PAYLOAD_KEY]
        assert request["user"] is user
        assert request["token_payload"] is payload
        assert user.user_id == expected_user
        if mode == "api_key_boolean":
            assert payload == {"type": "api_key"}
        else:
            assert payload["sub"] == expected_user
        reached.append(user.user_id)
        return web.json_response({"user": user.user_id})

    app = web.Application(middlewares=[auth.build_jwt_auth_middleware(config)])
    app.router.add_get("/protected", handler)
    async with TestClient(TestServer(app)) as client:
        denied = await client.get(
            "/protected", headers={"Authorization": "Bearer invalid"}
        )
        assert denied.status == 401
        assert (await denied.json())["error"] == "invalid_token"
        assert not reached
        if mode == "jwt":
            token = JWTValidator(config).create_access_token(user_id=expected_user)
            headers = {"Authorization": f"Bearer {token}"}
        else:
            rejected_key = await client.get(
                "/protected", headers={config.api_key_header: "wrong-key"}
            )
            assert rejected_key.status == 401
            assert (await rejected_key.json())["error"] == "invalid_api_key"
            assert not reached
            headers = {config.api_key_header: "regression-key"}
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            accepted = await client.get("/protected", headers=headers)
            assert accepted.status == 200, await accepted.text()
            assert (await accepted.json())["user"] == expected_user
        assert reached == [expected_user]


def test_public_keys_match_the_installed_aiohttp_api():
    if hasattr(web, "RequestKey"):
        assert isinstance(auth.AUTH_USER_KEY, web.RequestKey)
        assert isinstance(auth.AUTH_TOKEN_PAYLOAD_KEY, web.RequestKey)
        assert auth.AUTH_USER_KEY != "user"
    else:
        assert auth.AUTH_USER_KEY == "user"
        assert auth.AUTH_TOKEN_PAYLOAD_KEY == "token_payload"


@pytest.mark.unit
@pytest.mark.parametrize(
    "message,category,typed_write",
    [
        ("different recommendation", NotAppKeyWarning, False),
        (_RECOMMENDATION, RuntimeWarning, False),
        (_RECOMMENDATION, NotAppKeyWarning, True),
    ],
)
def test_compatibility_filter_does_not_hide_other_warnings(
    monkeypatch, message, category, typed_write
):
    request = make_mocked_request("GET", "/protected")
    original = type(request).__setitem__
    reached = []

    def noisy_setitem(self, key, value):
        target = auth.AUTH_USER_KEY if typed_write else "user"
        if key == target:
            reached.append(key)
            warnings.warn(message, category, stacklevel=2)
        original(self, key, value)

    monkeypatch.setattr(type(request), "__setitem__", noisy_setitem)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        with pytest.raises(category) as exc:
            auth._publish_auth_state(request, AuthenticatedUser("control"), {})
    assert str(exc.value) == message
    assert reached


@pytest.mark.unit
def test_compatibility_filter_does_not_leak_to_handler_writes():
    request = make_mocked_request("GET", "/protected")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        auth._publish_auth_state(request, AuthenticatedUser("control"), {})
        with pytest.raises(NotAppKeyWarning) as exc:
            warnings.warn_explicit(
                _RECOMMENDATION,
                NotAppKeyWarning,
                filename=auth.__file__,
                lineno=1,
                module=auth.__name__,
                registry={},
            )
        assert str(exc.value) == _RECOMMENDATION


@pytest.mark.unit
def test_exact_legacy_alias_recommendation_is_the_only_quieted_warning(monkeypatch):
    request = make_mocked_request("GET", "/protected")
    original = type(request).__setitem__
    aliases = []

    def warning_setitem(self, key, value):
        if hasattr(web, "RequestKey") and isinstance(key, str):
            aliases.append(key)
            warnings.warn(_RECOMMENDATION, NotAppKeyWarning, stacklevel=2)
        original(self, key, value)

    monkeypatch.setattr(type(request), "__setitem__", warning_setitem)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        auth._publish_auth_state(request, AuthenticatedUser("control"), {})
    assert request[auth.AUTH_USER_KEY] is request["user"]
    assert request[auth.AUTH_TOKEN_PAYLOAD_KEY] is request["token_payload"]
    assert aliases == (["user", "token_payload"] if hasattr(web, "RequestKey") else [])
