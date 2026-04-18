# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 2 wiring: GcpOauth constructs via preset facade (#498 S5, MED-1).

Per `rules/facade-manager-detection.md` §2, manager-shape classes
(`GcpOauth`) MUST have a Tier 2 wiring file whose absence is grep-able
by the predictable name `test_gcpoauth_wiring.py`.

Structural test always runs; live-credential test gated on
`GOOGLE_APPLICATION_CREDENTIALS` env so CI without GCP creds still
exercises the wiring contract.
"""

from __future__ import annotations

import os

import pytest

from kaizen.llm.auth.gcp import GcpOauth
from kaizen.llm.deployment import LlmDeployment


@pytest.mark.integration
def test_vertex_claude_preset_constructs_gcp_oauth_auth() -> None:
    """Structural: vertex_claude preset composes a real GcpOauth auth."""
    d = LlmDeployment.vertex_claude(
        "/fake/service-account.json",
        "my-project-1234",
        "us-central1",
        "claude-3-opus",
    )
    assert isinstance(d.auth, GcpOauth)
    assert d.auth.auth_strategy_kind() == "gcp_oauth"


@pytest.mark.integration
def test_vertex_gemini_preset_constructs_gcp_oauth_auth() -> None:
    """Structural: vertex_gemini preset composes a real GcpOauth auth."""
    d = LlmDeployment.vertex_gemini(
        "/fake/service-account.json",
        "my-project-1234",
        "us-central1",
        "gemini-1.5-pro",
    )
    assert isinstance(d.auth, GcpOauth)


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"),
    reason="Requires GOOGLE_APPLICATION_CREDENTIALS pointing at a real service-account key",
)
def test_gcpoauth_from_env_builds_instance() -> None:
    """Live-gated: from_env constructs a valid GcpOauth from GAC env var."""
    auth = GcpOauth.from_env()
    assert auth.auth_strategy_kind() == "gcp_oauth"
