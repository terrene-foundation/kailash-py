"""Regression tests for the auth-module Rule 2 stub cleanup.

The Core SDK's ``SSOAuthenticationNode``, ``EnterpriseAuthProviderNode``,
``MultiFactorAuthNode``, and ``MiddlewareAuthManager`` shipped with seven
``raise NotImplementedError`` stubs reachable from documented public-API
surfaces. Per ``rules/zero-tolerance.md`` Rule 2 § "Fake dispatch" and
``rules/orphan-detection.md`` Rule 3, these were either deleted (orphans)
or replaced with documented no-op defaults / typed dispatcher errors.

These tests lock in the cleanup so a future refactor can't silently
re-introduce the stubs.
"""

from __future__ import annotations

import asyncio

import pytest


@pytest.mark.regression
def test_sso_default_providers_excludes_unimplemented_protocols():
    """SAML and LDAP are NOT in the Core SDK's advertised default providers.

    Pre-fix the default ``providers`` list was
    ``["saml", "oauth2", "oidc", "ldap"]`` — every default-config user
    configured SAML or LDAP only to crash at runtime with
    ``NotImplementedError``. The default now advertises only the protocols
    the Core SDK actually implements.
    """
    from kailash.nodes.auth.sso import SSOAuthenticationNode

    node = SSOAuthenticationNode()
    assert node.providers == ["oauth2", "oidc"]
    assert "saml" not in node.providers
    assert "ldap" not in node.providers


@pytest.mark.regression
def test_sso_callback_rejects_saml_and_ldap_with_value_error():
    """``_handle_callback`` rejects unimplemented providers with a typed error.

    Pre-fix calling ``_handle_callback("saml", ...)`` raised
    ``NotImplementedError`` from a private helper. The dispatcher now raises
    ``ValueError`` with a message that names the override path.
    """
    from kailash.nodes.auth.sso import SSOAuthenticationNode

    node = SSOAuthenticationNode()
    for provider in ("saml", "ldap"):
        with pytest.raises(ValueError, match=f"SSO provider {provider!r}"):
            asyncio.run(node._handle_callback(provider, {}))


@pytest.mark.regression
def test_sso_no_orphan_saml_or_ldap_helpers():
    """The deleted SAML/LDAP helper methods MUST stay deleted.

    ``_validate_saml_response``, ``_authenticate_ldap``,
    ``_handle_saml_callback``, ``_handle_ldap_callback``, and
    ``_extract_saml_attributes`` were orphans after the dispatcher was
    tightened. They were deleted; this test guards against revival.
    """
    import kailash.nodes.auth.sso as sso_module
    from kailash.nodes.auth.sso import SSOAuthenticationNode

    assert not hasattr(sso_module, "_validate_saml_response")
    node = SSOAuthenticationNode()
    for orphan in (
        "_authenticate_ldap",
        "_handle_saml_callback",
        "_handle_ldap_callback",
        "_extract_saml_attributes",
    ):
        assert not hasattr(node, orphan), (
            f"{orphan} should be deleted (Rule 2 stub cleanup); "
            "if you re-added it, also implement the protocol-specific path."
        )


@pytest.mark.regression
def test_enterprise_auth_default_methods_excludes_passwordless_and_certificate():
    """Default ``enabled_methods`` does NOT advertise unimplemented methods.

    Pre-fix the default included ``passwordless`` (every default-config
    user got a broken auth method advertised). The default now lists only
    methods the Core SDK actually implements.
    """
    from kailash.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode

    node = EnterpriseAuthProviderNode()
    assert "passwordless" not in node.enabled_methods
    assert "certificate" not in node.enabled_methods
    assert node.enabled_methods == [
        "sso",
        "mfa",
        "directory",
        "social",
        "api_key",
        "jwt",
    ]


@pytest.mark.regression
def test_enterprise_auth_dispatcher_rejects_passwordless_and_certificate():
    """``_perform_authentication`` rejects unimplemented methods with ValueError."""
    from kailash.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode

    node = EnterpriseAuthProviderNode()
    for method in ("passwordless", "certificate"):
        with pytest.raises(ValueError, match=f"Authentication method {method!r}"):
            asyncio.run(node._perform_authentication(method, {}, "user-1", {}))


@pytest.mark.regression
def test_enterprise_auth_no_orphan_passwordless_or_certificate_methods():
    """Deleted dispatch-target stubs MUST stay deleted."""
    from kailash.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode

    node = EnterpriseAuthProviderNode()
    for orphan in ("_authenticate_passwordless", "_authenticate_certificate"):
        assert not hasattr(node, orphan), (
            f"{orphan} should be deleted (Rule 2 stub cleanup); "
            "subclasses requiring this method should override "
            "_perform_authentication directly."
        )


@pytest.mark.regression
def test_enterprise_auth_assess_behavior_risk_returns_documented_default():
    """``_assess_behavior_risk`` is a documented override point with a no-op default.

    Pre-fix this method raised ``NotImplementedError`` on EVERY auth call
    that included a user_id (because ``_calculate_risk_score`` invoked it
    unconditionally). The top-level try/except converted the crash into a
    permanent auth failure with a misleading "behavioral analysis" error
    text. The fix replaces the stub with a zero-risk default that
    subclasses can override.
    """
    from kailash.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode

    node = EnterpriseAuthProviderNode()
    result = asyncio.run(node._assess_behavior_risk("user-1", {}))
    assert result == {"score": 0.0, "factors": []}


@pytest.mark.regression
def test_mfa_orphan_send_sms_method_is_deleted():
    """``MultiFactorAuthNode._send_sms`` orphan method is gone.

    Two ``_send_sms`` symbols existed: a working module-level helper
    (``mfa._send_sms`` — kept) and an orphan instance method that no
    production code called (deleted). This test guards against revival of
    the orphan method.
    """
    from kailash.nodes.auth.mfa import MultiFactorAuthNode

    node = MultiFactorAuthNode()
    bound = getattr(node, "_send_sms", None)
    # Module-level _send_sms is NOT a method on the instance.
    # If the instance method comes back, ``bound`` becomes a bound method.
    assert bound is None or not callable(bound) or not hasattr(bound, "__self__"), (
        "MultiFactorAuthNode._send_sms instance method should remain deleted "
        "(only the module-level kailash.nodes.auth.mfa._send_sms is kept)."
    )


@pytest.mark.regression
def test_mfa_module_level_send_sms_helper_still_exists():
    """The module-level ``_send_sms`` helper stays — it IS used (line 648)."""
    from kailash.nodes.auth import mfa

    assert callable(mfa._send_sms)
    assert mfa._send_sms("+15555550123", "test message") is True


@pytest.mark.regression
def test_middleware_require_auth_orphan_function_is_deleted():
    """``require_auth`` is gone — it was an orphan stub redirect.

    The function raised ``NotImplementedError`` pointing callers at
    ``MiddlewareAuthManager.get_current_user_dependency``; no code in the
    repo or downstream packages imported it. Per
    ``rules/orphan-detection.md`` Rule 3 (Removed = Deleted).
    """
    with pytest.raises(ImportError):
        from kailash.middleware.auth.auth_manager import require_auth  # noqa: F401


@pytest.mark.regression
def test_no_notimplementederror_in_auth_module_tree():
    """Repository-wide guard: no ``raise NotImplementedError`` in auth code.

    This is the structural defense against the stub-revival pattern. If a
    future refactor re-introduces a stub, this test fails loudly and forces
    the author to either implement it or delete the dispatch branch.
    """
    import pathlib

    repo_root = pathlib.Path(__file__).resolve().parents[2]
    auth_dirs = [
        repo_root / "src" / "kailash" / "nodes" / "auth",
        repo_root / "src" / "kailash" / "middleware" / "auth",
    ]

    offenders: list[str] = []
    for d in auth_dirs:
        if not d.is_dir():
            continue
        for py in d.rglob("*.py"):
            text = py.read_text()
            if "raise NotImplementedError" in text:
                offenders.append(str(py.relative_to(repo_root)))

    assert not offenders, (
        "Auth code MUST NOT raise NotImplementedError on documented public "
        "surfaces (rules/zero-tolerance.md Rule 2 § Fake dispatch). "
        f"Offenders: {offenders}. Either implement the method or delete "
        "the dispatch branch and remove the symbol from the default config."
    )
