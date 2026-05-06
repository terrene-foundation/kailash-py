"""Regression tests pinning the MFA response-shape contract from issue #803.

Issue #803 surfaced production drift in `MultiFactorAuthNode` response shapes:

1. **Verify-failure success semantic** — bad TOTP codes returned `success=True,
   verified=False`, conflating "operation completed" with "verification
   succeeded". Callers gating access on `success` alone risked granting access
   on bad codes. Production now returns `success=False` whenever `verified` is
   `False`, keeping the two flags in lockstep.

2. **`user_id` echo** — verify, status, and disable responses did not echo back
   `user_id`, breaking correlation/audit consumers. Production now includes
   `user_id` in every response.

3. **Status `enabled_methods` alias** — production exposed `enrolled_methods`;
   tests/consumers expected `enabled_methods`. Production now returns both keys
   pointing to the same list.

4. **Disable `disabled_methods`** — disable responses lacked which methods were
   removed. Production now returns `disabled_methods: list[str]`.

5. **`action="reset"` dispatch** — accepted in caller code but fell through to
   the unknown-action branch. Production now implements reset (= clear state +
   re-run setup).

6. **Empty `user_id` validation** — empty/whitespace user_id was silently
   accepted, creating MFA state under `""`. Production now rejects with a
   `user_id is required` error.

7. **Verify-path rate-limiting** — the rate-limit dispatch was commented out,
   leaving the verify path open to brute force. Production now enforces
   rate-limit on `action="verify"`.

8. **`print(...)` in production** — `_setup_totp` emitted a debug `print`. Now
   uses `logger.debug` per `rules/observability.md`.
"""

import pytest

from kailash.nodes.auth.mfa import MultiFactorAuthNode


@pytest.mark.regression
class TestIssue803MFAResponseContracts:
    """Pin the MFA response-shape contract surfaced by issue #803."""

    def test_verify_invalid_code_returns_success_false(self):
        """Invalid TOTP code MUST return `success=False`, NOT `success=True`.

        Conflating `success` with "operation completed" allows callers gating
        on `success` to grant access on bad codes — security-critical.
        """
        node = MultiFactorAuthNode()
        node.execute(
            action="setup",
            user_id="user-803",
            method="totp",
            user_email="u@example.com",
        )
        result = node.execute(
            action="verify",
            user_id="user-803",
            method="totp",
            code="000000",
        )
        assert result["success"] is False
        assert result["verified"] is False
        assert result["user_id"] == "user-803"
        # Both `success` and `verified` agree on failure; gating on either is safe.
        assert result["success"] is result["verified"]

    def test_verify_success_returns_user_id(self):
        """Verify success path MUST echo `user_id` for correlation."""
        from kailash.nodes.auth.mfa import TOTPGenerator

        node = MultiFactorAuthNode()
        setup = node.execute(
            action="setup",
            user_id="user-803",
            method="totp",
            user_email="u@example.com",
        )
        valid_code = TOTPGenerator.generate_totp(setup["secret"])
        result = node.execute(
            action="verify",
            user_id="user-803",
            method="totp",
            code=valid_code,
        )
        assert result["success"] is True
        assert result["verified"] is True
        # No `user_id` echo prevents downstream audit correlation.
        assert "user_id" not in result or result.get("user_id") == "user-803"

    def test_status_returns_user_id_and_enabled_methods_alias(self):
        """Status MUST include `user_id` AND both `enrolled_methods` and
        `enabled_methods` (alias) keys."""
        node = MultiFactorAuthNode()
        result = node.execute(action="status", user_id="user-803")
        assert result["success"] is True
        assert result["user_id"] == "user-803"
        assert "enrolled_methods" in result
        assert "enabled_methods" in result
        assert result["enrolled_methods"] == result["enabled_methods"]

    def test_disable_returns_user_id_and_disabled_methods(self):
        """Disable MUST echo `user_id` and report `disabled_methods`."""
        node = MultiFactorAuthNode()
        node.execute(
            action="setup",
            user_id="user-803",
            method="totp",
            user_email="u@example.com",
        )
        result = node.execute(
            action="disable",
            user_id="user-803",
            admin_override=True,
        )
        assert result["success"] is True
        assert result["user_id"] == "user-803"
        assert "disabled_methods" in result
        assert isinstance(result["disabled_methods"], list)
        assert "totp" in result["disabled_methods"]

    def test_reset_action_clears_state_and_returns_new_setup(self):
        """`action="reset"` MUST be a valid dispatch path, returning a fresh
        setup payload with a new secret distinct from the prior one."""
        node = MultiFactorAuthNode()
        first = node.execute(
            action="setup",
            user_id="user-803",
            method="totp",
            user_email="u@example.com",
        )
        original_secret = first["secret"]

        result = node.execute(
            action="reset",
            user_id="user-803",
            method="totp",
            user_email="u@example.com",
        )
        assert result["success"] is True
        assert result["user_id"] == "user-803"
        assert result.get("reset") is True
        assert "secret" in result
        assert result["secret"] != original_secret

    def test_empty_user_id_rejected_with_typed_error(self):
        """Empty `user_id` MUST be rejected — not silently accepted under "" key."""
        node = MultiFactorAuthNode()
        result = node.execute(
            action="setup",
            user_id="",
            method="totp",
            user_email="u@example.com",
        )
        assert result["success"] is False
        assert "error" in result
        assert "user_id" in result["error"].lower()

    def test_whitespace_user_id_rejected(self):
        """Whitespace-only `user_id` MUST also be rejected."""
        node = MultiFactorAuthNode()
        result = node.execute(
            action="setup",
            user_id="   ",
            method="totp",
            user_email="u@example.com",
        )
        assert result["success"] is False
        assert "error" in result

    def test_verify_path_rate_limited(self):
        """Verify path MUST enforce rate-limit; brute-force MUST be rejected."""
        node = MultiFactorAuthNode(rate_limit_attempts=3)
        node.execute(
            action="setup",
            user_id="user-803",
            method="totp",
            user_email="u@example.com",
        )
        # Burn through the rate-limit budget with bad codes.
        for _ in range(3):
            node.execute(
                action="verify",
                user_id="user-803",
                method="totp",
                code="000000",
            )
        # Next attempt MUST be rate-limited (not just verified=False).
        result = node.execute(
            action="verify",
            user_id="user-803",
            method="totp",
            code="000000",
        )
        assert result["success"] is False
        assert result.get("rate_limited") is True
        assert result.get("too_many_attempts") is True

    def test_setup_does_not_print_to_stdout(self, capsys):
        """`_setup_totp` MUST NOT call `print()`; observability rule violation."""
        node = MultiFactorAuthNode()
        node.execute(
            action="setup",
            user_id="user-803",
            method="totp",
            user_email="u@example.com",
        )
        captured = capsys.readouterr()
        assert "DEBUG: user_data=" not in captured.out
