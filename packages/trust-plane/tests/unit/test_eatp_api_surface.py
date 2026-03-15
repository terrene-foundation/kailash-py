# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""EATP public API surface smoke tests for trust-plane.

Verifies that every EATP symbol imported by trust-plane resolves correctly.
Each test imports a single symbol and asserts it is not None. Grouped by
source module to match the EATP import map
(packages/trust-plane/docs/eatp-import-map.md).

These tests catch breakage when EATP renames, moves, or removes symbols
that trust-plane depends on.
"""

import pytest


# ---------------------------------------------------------------------------
# eatp (root) -- 3 symbols
# ---------------------------------------------------------------------------


class TestEATPRoot:
    """Symbols imported from the eatp root package."""

    def test_capability_request(self):
        from eatp import CapabilityRequest

        assert CapabilityRequest is not None

    def test_trust_key_manager(self):
        from eatp import TrustKeyManager

        assert TrustKeyManager is not None

    def test_trust_operations(self):
        from eatp import TrustOperations

        assert TrustOperations is not None


# ---------------------------------------------------------------------------
# eatp.authority -- 2 symbols
# ---------------------------------------------------------------------------


class TestEATPAuthority:
    """Symbols imported from eatp.authority."""

    def test_authority_permission(self):
        from eatp.authority import AuthorityPermission

        assert AuthorityPermission is not None

    def test_organizational_authority(self):
        from eatp.authority import OrganizationalAuthority

        assert OrganizationalAuthority is not None


# ---------------------------------------------------------------------------
# eatp.chain -- 4 symbols
# ---------------------------------------------------------------------------


class TestEATPChain:
    """Symbols imported from eatp.chain."""

    def test_action_result(self):
        from eatp.chain import ActionResult

        assert ActionResult is not None

    def test_authority_type(self):
        from eatp.chain import AuthorityType

        assert AuthorityType is not None

    def test_capability_type(self):
        from eatp.chain import CapabilityType

        assert CapabilityType is not None

    def test_verification_result(self):
        from eatp.chain import VerificationResult

        assert VerificationResult is not None


# ---------------------------------------------------------------------------
# eatp.crypto -- 1 symbol
# ---------------------------------------------------------------------------


class TestEATPCrypto:
    """Symbols imported from eatp.crypto."""

    def test_generate_keypair(self):
        from eatp.crypto import generate_keypair

        assert generate_keypair is not None


# ---------------------------------------------------------------------------
# eatp.enforce.shadow -- 1 symbol
# ---------------------------------------------------------------------------


class TestEATPEnforceShadow:
    """Symbols imported from eatp.enforce.shadow."""

    def test_shadow_enforcer(self):
        from eatp.enforce.shadow import ShadowEnforcer

        assert ShadowEnforcer is not None


# ---------------------------------------------------------------------------
# eatp.enforce.strict -- 3 symbols
# ---------------------------------------------------------------------------


class TestEATPEnforceStrict:
    """Symbols imported from eatp.enforce.strict."""

    def test_held_behavior(self):
        from eatp.enforce.strict import HeldBehavior

        assert HeldBehavior is not None

    def test_strict_enforcer(self):
        from eatp.enforce.strict import StrictEnforcer

        assert StrictEnforcer is not None

    def test_verdict(self):
        from eatp.enforce.strict import Verdict

        assert Verdict is not None


# ---------------------------------------------------------------------------
# eatp.postures -- 3 symbols
# ---------------------------------------------------------------------------


class TestEATPPostures:
    """Symbols imported from eatp.postures."""

    def test_posture_state_machine(self):
        from eatp.postures import PostureStateMachine

        assert PostureStateMachine is not None

    def test_posture_transition_request(self):
        from eatp.postures import PostureTransitionRequest

        assert PostureTransitionRequest is not None

    def test_trust_posture(self):
        from eatp.postures import TrustPosture

        assert TrustPosture is not None


# ---------------------------------------------------------------------------
# eatp.reasoning -- 2 symbols
# ---------------------------------------------------------------------------


class TestEATPReasoning:
    """Symbols imported from eatp.reasoning."""

    def test_confidentiality_level(self):
        from eatp.reasoning import ConfidentialityLevel

        assert ConfidentialityLevel is not None

    def test_reasoning_trace(self):
        from eatp.reasoning import ReasoningTrace

        assert ReasoningTrace is not None


# ---------------------------------------------------------------------------
# eatp.store.filesystem -- 1 symbol
# ---------------------------------------------------------------------------


class TestEATPStoreFilesystem:
    """Symbols imported from eatp.store.filesystem."""

    def test_filesystem_store(self):
        from eatp.store.filesystem import FilesystemStore

        assert FilesystemStore is not None
