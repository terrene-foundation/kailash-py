"""#2047 — MultiFactorAuthNode authorizes the (actor, action, subject) triple.

Every test here drives the PUBLIC surface (``run`` / ``async_run``), never a
private helper. That is deliberate: #2026's coverage tested helpers directly,
which is how correct-but-unreachable code shipped -- the helper was fixed
while the dispatcher that reached it was not.

Fail-first evidence, measured on this branch before the fix landed: every test
in ``TestCallerSuppliedAdminOverrideIsNotAuthority`` and
``TestActorIsRequired`` PASSES the pre-fix code's behaviour into a failure,
because pre-fix the node returned ``success: True`` for exactly the calls
asserted denied here. The suite is discriminating in both directions -- the
``TestAuthorizedActorsCanAct`` class fails if the gate is merely
"deny everything".
"""

import asyncio
import warnings

import pytest

from kailash.nodes.auth._actor import (
    MFA_ADMIN_CAPABILITY,
    MFAActor,
    NullActorResolver,
    SessionActorResolver,
    StaticActorResolver,
)
from kailash.nodes.auth.mfa import MultiFactorAuthNode

ALICE_SESSION = "sess-alice"
ADMIN_SESSION = "sess-admin"


def _node(**kwargs):
    """A node wired with two issued sessions: an end user and an admin."""
    resolver = StaticActorResolver(
        {
            ALICE_SESSION: MFAActor(user_id="alice"),
            ADMIN_SESSION: MFAActor(
                user_id="root", capabilities={MFA_ADMIN_CAPABILITY}
            ),
        }
    )
    kwargs.setdefault("actor_resolver", resolver)
    return MultiFactorAuthNode(name="mfa_2047", **kwargs)


def _enrol_verified(node, user_id):
    """Give ``user_id`` a VERIFIED factor, through the public surface."""
    node.run(
        action="setup", user_id=user_id, method="totp", actor_session_id=ADMIN_SESSION
    )
    node.user_mfa_data[user_id]["methods"]["totp"]["verified"] = True


# ---------------------------------------------------------------------------
# The bypass the five review rounds kept re-finding
# ---------------------------------------------------------------------------


class TestCallerSuppliedAdminOverrideIsNotAuthority:
    """`admin_override` was a request field. A request field is not authority."""

    @pytest.mark.parametrize("action", ["revoke", "disable", "reset"])
    def test_admin_override_does_not_authorize_a_destructive_action(self, action):
        """THE regression for #2047.

        Pre-fix this exact call returned ``success: True`` and destroyed the
        victim's second factor, because the only gate was a boolean the caller
        typed. An end user with a perfectly valid session of their OWN must
        not be able to reach it by asserting admin-ness.
        """
        node = _node()
        _enrol_verified(node, "victim")

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            result = node.run(
                action=action,
                user_id="victim",
                admin_override=True,
                actor_session_id=ALICE_SESSION,
            )

        assert result["success"] is False, result
        assert result["authorized"] is False, result
        assert "victim" in node.user_mfa_data, "the factor was destroyed anyway"
        assert node.user_mfa_data["victim"]["methods"]["totp"]["verified"] is True

    def test_admin_override_does_not_authorize_acting_on_another_subject(self):
        """`status` discloses which factors an account holds."""
        node = _node()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            result = node.run(
                action="status",
                user_id="victim",
                admin_override=True,
                actor_session_id=ALICE_SESSION,
            )
        assert result["success"] is False
        assert result["authorized"] is False

    def test_admin_override_does_not_authorize_reenrolment_over_a_verified_factor(self):
        """The setup-overwrite takeover: replace a victim's secret, keep the
        fresh backup codes. Pre-fix `admin_override=True` was sufficient."""
        node = _node()
        _enrol_verified(node, "alice")
        original = node.user_mfa_data["alice"]["methods"]["totp"]["secret"]

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            result = node.run(
                action="setup",
                user_id="alice",
                method="totp",
                admin_override=True,
                actor_session_id=ALICE_SESSION,
            )

        assert result["success"] is False, result
        assert node.user_mfa_data["alice"]["methods"]["totp"]["secret"] == original

    def test_admin_override_does_not_authorize_admin_recovery(self):
        node = _node()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            result = node.run(
                action="initiate_recovery",
                user_id="alice",
                recovery_method="admin",
                admin_override=True,
                actor_session_id=ALICE_SESSION,
            )
        assert result["success"] is False
        assert result["authorized"] is False

    def test_admin_override_raises_a_deprecation_warning(self):
        node = _node()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            node.run(
                action="status",
                user_id="alice",
                admin_override=True,
                actor_session_id=ALICE_SESSION,
            )
        messages = [
            str(w.message) for w in caught if issubclass(w.category, DeprecationWarning)
        ]
        assert any("admin_override is deprecated" in m for m in messages), messages
        assert any(MFA_ADMIN_CAPABILITY in m for m in messages), messages

    def test_not_passing_admin_override_raises_nothing(self):
        """No-false-positive: the warning fires for callers that use it only."""
        node = _node()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            node.run(action="status", user_id="alice", actor_session_id=ALICE_SESSION)
        assert not [w for w in caught if issubclass(w.category, DeprecationWarning)], [
            str(w.message) for w in caught
        ]


# ---------------------------------------------------------------------------
# An actor is required, and it is resolved server-side
# ---------------------------------------------------------------------------


class TestActorIsRequired:
    @pytest.mark.parametrize(
        "action",
        [
            "setup",
            "verify",
            "status",
            "generate_backup_codes",
            "trust_device",
            "revoke",
        ],
    )
    def test_no_actor_session_id_denies(self, action):
        node = _node()
        result = node.run(action=action, user_id="alice")
        assert result["success"] is False, result
        assert result["authorized"] is False
        assert "actor_session_id is required" in result["error"]

    def test_an_unissued_session_id_denies(self):
        """The caller cannot mint its own proof."""
        node = _node()
        result = node.run(
            action="status", user_id="alice", actor_session_id="i-made-this-up"
        )
        assert result["success"] is False
        assert result["error"] == "Unrecognised or expired actor_session_id."

    def test_the_default_resolver_denies_everything(self):
        """An unwired authorizer is a refusal, not an open door."""
        node = MultiFactorAuthNode(name="mfa_unwired")
        assert isinstance(node.actor_resolver, NullActorResolver)
        result = node.run(
            action="status", user_id="alice", actor_session_id=ALICE_SESSION
        )
        assert result["success"] is False
        assert result["authorized"] is False

    def test_a_resolver_that_raises_denies_rather_than_crashing(self):
        class Exploding:
            def resolve_actor(self, actor_session_id):
                raise RuntimeError("session store is down")

        node = MultiFactorAuthNode(name="mfa_boom", actor_resolver=Exploding())
        result = node.run(
            action="status", user_id="alice", actor_session_id=ALICE_SESSION
        )
        assert result["success"] is False
        assert result["authorized"] is False

    def test_a_resolver_returning_a_lookalike_object_denies(self):
        """A duck-typed actor would put `has_capability` under host control."""

        class FakeActor:
            user_id = "alice"

            def has_capability(self, capability):
                return True

        class Sneaky:
            def resolve_actor(self, actor_session_id):
                return FakeActor()

        node = MultiFactorAuthNode(name="mfa_fake", actor_resolver=Sneaky())
        result = node.run(
            action="reset", user_id="victim", actor_session_id=ALICE_SESSION
        )
        assert result["success"] is False
        assert result["authorized"] is False


# ---------------------------------------------------------------------------
# Discrimination in the other direction: authorized actors CAN act
# ---------------------------------------------------------------------------


class TestAuthorizedActorsCanAct:
    def test_an_actor_may_act_on_itself(self):
        node = _node()
        result = node.run(
            action="setup",
            user_id="alice",
            method="totp",
            actor_session_id=ALICE_SESSION,
        )
        assert result["success"] is True, result

    def test_an_admin_may_act_on_another_subject(self):
        node = _node()
        result = node.run(
            action="status", user_id="victim", actor_session_id=ADMIN_SESSION
        )
        assert result["success"] is True, result

    @pytest.mark.parametrize("action", ["revoke", "disable", "reset"])
    def test_an_admin_may_take_a_destructive_action(self, action):
        node = _node()
        _enrol_verified(node, "victim")
        result = node.run(
            action=action, user_id="victim", actor_session_id=ADMIN_SESSION
        )
        assert result["success"] is True, result

    def test_an_admin_may_reenrol_over_a_verified_factor(self):
        node = _node()
        _enrol_verified(node, "alice")
        result = node.run(
            action="setup",
            user_id="alice",
            method="totp",
            actor_session_id=ADMIN_SESSION,
        )
        assert result["success"] is True, result


# ---------------------------------------------------------------------------
# ONE dispatcher: the async surface is not a way around the gate
# ---------------------------------------------------------------------------


class TestBothSurfacesShareOneDispatcher:
    @pytest.mark.parametrize("action", ["revoke", "disable", "reset"])
    def test_async_run_enforces_the_same_gate(self, action):
        """A gate present in one dispatcher and absent in the other is not a
        gate. #2026 found that twice on this node."""
        node = _node()
        _enrol_verified(node, "victim")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            result = asyncio.run(
                node.async_run(
                    action=action,
                    user_id="victim",
                    admin_override=True,
                    actor_session_id=ALICE_SESSION,
                )
            )
        assert result["success"] is False, result
        assert result["authorized"] is False

    @pytest.mark.parametrize(
        "action",
        [
            "setup",
            "enroll",
            "verify",
            "verify_backup",
            "status",
            "get_methods",
            "list_methods",
            "generate_backup_codes",
            "set_preference",
            "check_device_trust",
            "revoke",
            "disable",
            "reset",
            "initiate_recovery",
        ],
    )
    def test_every_action_is_dispatchable_on_both_surfaces(self, action):
        """The two dispatchers had different ACTION SETS -- `verify_backup`
        and `list_methods` were async-only, nine others sync-only -- so a
        caller's available vocabulary depended on the entry point.

        Discrimination: this asserts NOT "unknown action" rather than
        "success", because most of these legitimately fail on an unenrolled
        subject. Run against the pre-fix code it reports `verify_backup` and
        `list_methods` unknown on run(), and nine unknown on async_run().
        """
        node = _node()
        sync = node.run(action=action, user_id="alice", actor_session_id=ALICE_SESSION)
        api = asyncio.run(
            node.async_run(
                action=action, user_id="alice", actor_session_id=ALICE_SESSION
            )
        )
        for surface, result in (("run", sync), ("async_run", api)):
            assert f"Unknown action: {action}" not in (
                result.get("error") or ""
            ), f"{surface} does not know {action}: {result}"

    def test_one_trusted_device_store(self):
        """`trust_device` wrote to two different stores depending on the entry
        point, so a trust granted through one was invisible to the code that
        clears the other.

        Drives the two SPELLINGS the surfaces used -- `device_info` and
        `device_fingerprint` -- and asserts a single store holds both, and
        that `revoke` clears both.
        """
        node = _node()
        node.run(
            action="trust_device",
            user_id="alice",
            device_info={"device_id": "laptop"},
            actor_session_id=ALICE_SESSION,
        )
        asyncio.run(
            node.async_run(
                action="trust_device",
                user_id="alice",
                device_fingerprint="phone",
                actor_session_id=ALICE_SESSION,
            )
        )

        stored = {d["device_id"] for d in node.trusted_devices.get("alice", [])}
        assert stored == {"laptop", "phone"}, stored
        # The legacy second store must not have been written at all.
        assert not node.user_mfa_data.get("alice", {}).get("trusted_devices")

    def test_a_trust_from_either_spelling_is_checkable_and_revocable(self):
        node = _node()
        granted = asyncio.run(
            node.async_run(
                action="trust_device",
                user_id="alice",
                device_fingerprint="phone",
                actor_session_id=ALICE_SESSION,
            )
        )
        token = granted["trust_token"]

        checked = node.run(
            action="check_device_trust",
            user_id="alice",
            device_info={"device_id": "phone"},
            trust_token=token,
            actor_session_id=ALICE_SESSION,
        )
        assert checked["trusted"] is True, checked

        node.run(action="reset", user_id="alice", actor_session_id=ADMIN_SESSION)
        after = node.run(
            action="check_device_trust",
            user_id="alice",
            device_info={"device_id": "phone"},
            trust_token=token,
            actor_session_id=ALICE_SESSION,
        )
        assert after["trusted"] is False, after

    def test_trusting_a_device_does_not_enrol_an_unenrolled_subject(self):
        """The fingerprint path CREATED an MFA record as a side effect."""
        node = _node()
        asyncio.run(
            node.async_run(
                action="trust_device",
                user_id="alice",
                device_fingerprint="phone",
                actor_session_id=ALICE_SESSION,
            )
        )
        assert "alice" not in node.user_mfa_data


# ---------------------------------------------------------------------------
# The audit trail can now say BY WHOM
# ---------------------------------------------------------------------------


class TestAuditRecordsNameTheActor:
    def test_the_record_carries_the_resolved_principal(self):
        """#2066 shipped `"actor": None` as a tripwire. This is what closes it."""
        node = _node()
        written = []
        node.audit_log_node.execute = lambda **kw: written.append(kw) or {
            "logged": True
        }

        node.run(action="revoke", user_id="victim", actor_session_id=ADMIN_SESSION)

        assert written, "revoke wrote no audit record"
        assert written[0]["event_data"]["actor"] == "root", written[0]
        assert written[0]["user_id"] == "victim", "the SUBJECT must still be recorded"

    def test_a_refused_attempt_is_recorded(self):
        """A rejected privilege escalation is the record an auditor wants most.
        A denial that returned before the audit call would be invisible."""
        node = _node()
        written = []
        node.audit_log_node.execute = lambda **kw: written.append(kw) or {
            "logged": True
        }

        node.run(action="reset", user_id="victim", actor_session_id=ALICE_SESSION)

        assert written, "the refused attempt wrote no audit record"
        record = written[0]["event_data"]
        assert record["actor"] == "alice", record
        assert record["success"] is False
        assert record["result"]["authorized"] is False, record

    def test_an_unresolvable_actor_is_recorded_without_a_fabricated_identity(self):
        node = _node()
        written = []
        node.audit_log_node.execute = lambda **kw: written.append(kw) or {
            "logged": True
        }

        node.run(action="reset", user_id="victim", actor_session_id="not-a-session")

        assert written
        assert written[0]["event_data"]["actor"] is None, written[0]


# ---------------------------------------------------------------------------
# The opt-out is explicit and LOUD
# ---------------------------------------------------------------------------


class TestRequireActorFalseIsLoud:
    def test_it_warns_once_per_process_naming_the_wiring(self, caplog):
        import kailash.nodes.auth.mfa as mfa_mod

        mfa_mod._WARNED_ONCE.clear()
        with caplog.at_level("WARNING"):
            MultiFactorAuthNode(name="a", require_actor=False)
            MultiFactorAuthNode(name="b", require_actor=False)

        hits = [r for r in caplog.records if "require_actor=False" in r.message]
        assert len(hits) == 1, [r.message for r in hits]
        assert hits[0].levelname == "WARNING"
        assert "actor_resolver=" in hits[0].message
        assert "actor_session_id" in hits[0].message

    def test_enforcing_construction_emits_no_such_warning(self, caplog):
        """No-false-positive polarity."""
        import kailash.nodes.auth.mfa as mfa_mod

        mfa_mod._WARNED_ONCE.clear()
        with caplog.at_level("WARNING"):
            _node()
        assert not [r for r in caplog.records if "require_actor=False" in r.message]

    def test_the_opt_out_restores_the_documented_legacy_contract(self):
        node = MultiFactorAuthNode(name="legacy", require_actor=False)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            assert node.run(action="status", user_id="alice")["success"] is True
            assert (
                node.run(action="revoke", user_id="alice")["success"] is False
            ), "the destructive gate must still hold under the opt-out"


# ---------------------------------------------------------------------------
# The actor type and the resolvers
# ---------------------------------------------------------------------------


class TestActorAndResolvers:
    def test_capabilities_are_matched_exactly_with_no_wildcard(self):
        actor = MFAActor(user_id="u", capabilities={"*", "mfa:read"})
        assert actor.has_capability("mfa:read") is True
        assert actor.has_capability(MFA_ADMIN_CAPABILITY) is False

    def test_an_actor_cannot_be_widened_after_resolution(self):
        actor = MFAActor(user_id="u")
        with pytest.raises((AttributeError, TypeError)):
            actor.capabilities = frozenset({MFA_ADMIN_CAPABILITY})

    def test_a_mutable_capability_set_is_copied_not_aliased(self):
        granted = {"mfa:read"}
        actor = MFAActor(user_id="u", capabilities=granted)
        granted.add(MFA_ADMIN_CAPABILITY)
        assert actor.has_capability(MFA_ADMIN_CAPABILITY) is False

    @pytest.mark.parametrize("bad", ["", "   ", None, 7])
    def test_an_actor_needs_a_real_user_id(self, bad):
        with pytest.raises(ValueError):
            MFAActor(user_id=bad)

    def test_session_actor_resolver_derives_identity_from_the_session_store(self):
        """Identity comes from the session record the node wrote at login --
        not from anything in the request."""
        from kailash.nodes.auth.session_management import SessionManagementNode

        sessions = SessionManagementNode(name="s_2047")
        created = sessions.run(
            action="create", user_id="alice", ip_address="10.0.0.1", device_info={}
        )
        resolver = SessionActorResolver(sessions)

        actor = resolver.resolve_actor(created["session_id"])
        assert actor is not None
        assert actor.user_id == "alice"
        # With no capability provider an actor holds nothing: it can act on
        # itself and on nobody else.
        assert actor.has_capability(MFA_ADMIN_CAPABILITY) is False

    def test_session_actor_resolver_rejects_an_unknown_session(self):
        from kailash.nodes.auth.session_management import SessionManagementNode

        resolver = SessionActorResolver(SessionManagementNode(name="s_2047b"))
        assert resolver.resolve_actor("nope") is None
        assert resolver.resolve_actor("") is None
        assert resolver.resolve_actor(None) is None

    def test_session_actor_resolver_grants_capabilities_from_the_server_side_hook(self):
        from kailash.nodes.auth.session_management import SessionManagementNode

        sessions = SessionManagementNode(name="s_2047c")
        created = sessions.run(
            action="create", user_id="root", ip_address="10.0.0.1", device_info={}
        )
        seen = []

        def caps(user_id):
            seen.append(user_id)
            return {MFA_ADMIN_CAPABILITY} if user_id == "root" else set()

        actor = SessionActorResolver(sessions, caps).resolve_actor(
            created["session_id"]
        )
        assert actor.has_capability(MFA_ADMIN_CAPABILITY) is True
        # The provider is asked about the SERVER-DERIVED id, never a request field.
        assert seen == ["root"]

    def test_a_failing_capability_provider_grants_nothing(self):
        from kailash.nodes.auth.session_management import SessionManagementNode

        sessions = SessionManagementNode(name="s_2047d")
        created = sessions.run(
            action="create", user_id="root", ip_address="10.0.0.1", device_info={}
        )

        def boom(user_id):
            raise RuntimeError("directory unavailable")

        actor = SessionActorResolver(sessions, boom).resolve_actor(
            created["session_id"]
        )
        assert actor is not None
        assert actor.has_capability(MFA_ADMIN_CAPABILITY) is False

    def test_static_resolver_only_knows_issued_sessions(self):
        resolver = StaticActorResolver()
        assert resolver.resolve_actor("s1") is None
        resolver.add("s1", MFAActor(user_id="alice"))
        assert resolver.resolve_actor("s1").user_id == "alice"
        resolver.revoke("s1")
        assert resolver.resolve_actor("s1") is None
