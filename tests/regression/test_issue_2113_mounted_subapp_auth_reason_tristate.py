# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #2113 -- mounted_subapp_auth_kwargs asserted a
WARN that never fired when the parent used external_auth_reason.

``kailash.utils.server_auth.mounted_subapp_auth_kwargs`` renders a declaration
for the sub-app a ``WorkflowServer`` / ``WorkflowAPIGateway`` mounts. Before
this fix the declaration was binary on ``parent_is_authenticated``, but
``parent_is_authenticated=False`` collapses TWO distinct situations:

1. ``require_auth=False`` -- an explicit opt-out. The parent logs a loud
   ``server_auth.disabled`` WARN, exactly once, at its own construction.
2. ``external_auth_reason=...`` -- authentication is installed by something
   OUTSIDE this server (Nexus's own JWT middleware, an authenticating proxy).
   The parent logs an INFO ``server_auth.external``. No WARN is ever emitted,
   and authentication is not disabled -- it is provided elsewhere.

Both branches produced ``_auth_config is None``, so both rendered the
identical "which has authentication explicitly disabled; it logged that
exposure once at its own construction" text -- a false claim in case 2, since
no WARN was ever logged and the mount IS authenticated, just not by this
server's own gate.

Fix: ``mounted_subapp_auth_kwargs`` now accepts an additional
``parent_external_auth_reason`` keyword. Both ``WorkflowServer`` and
``WorkflowAPIGateway`` already track this value (``self._external_auth_reason``,
set from the SAME ``external_auth_reason`` argument that decided
``resolve_server_auth``'s branch) and now pass it through.

This file asserts the RENDERED STRING per branch directly against the pure
function -- no ASGI stack needed, the defect is a string, not a route. Then
confirms both real call sites (``WorkflowServer`` / ``WorkflowAPIGateway``)
actually plumb the parent's own ``external_auth_reason`` through to the
mounted sub-app, which is the part a caller checking only
``self._auth_config is not None`` could not see.
"""

from unittest.mock import Mock, patch

import pytest

from kailash.utils.server_auth import mounted_subapp_auth_kwargs
from kailash.workflow.graph import Workflow

pytestmark = pytest.mark.regression


class TestMountedSubappAuthKwargsPerBranch:
    """Three states, three renderings -- verified directly on the pure function."""

    def test_parent_authenticated_by_its_own_gate(self):
        """parent_is_authenticated=True renders the own-gate declaration."""
        result = mounted_subapp_auth_kwargs(
            parent_label="Server(title='X')",
            parent_is_authenticated=True,
        )
        reason = result["external_auth_reason"]
        assert "authenticates every request before routing to this mount" in reason
        assert "explicitly disabled" not in reason
        assert "installs no gate of its own" not in reason

    def test_parent_explicitly_disabled_auth(self):
        """require_auth=False (no parent_external_auth_reason) renders the
        disabled declaration -- the WARN genuinely fired for this branch, so
        this is the ONE branch where "explicitly disabled" is an honest claim.
        """
        result = mounted_subapp_auth_kwargs(
            parent_label="Server(title='X')",
            parent_is_authenticated=False,
            parent_external_auth_reason=None,
        )
        reason = result["external_auth_reason"]
        assert "explicitly disabled" in reason
        assert "logged that exposure once at its own construction" in reason

    def test_parent_externally_authenticated_does_not_claim_a_warn_that_never_fired(
        self,
    ):
        """The load-bearing regression assertion (#2113): the external-auth
        branch must NOT render the disabled-case text. No WARN was ever
        logged for this branch -- only an INFO server_auth.external -- and
        authentication is not disabled, it is installed elsewhere. A future
        change that collapses this branch back into the disabled-text
        rendering must fail HERE.
        """
        result = mounted_subapp_auth_kwargs(
            parent_label="Server(title='X')",
            parent_is_authenticated=False,
            parent_external_auth_reason=("nexus installs nexus.auth.jwt.JWTMiddleware"),
        )
        reason = result["external_auth_reason"]
        assert "explicitly disabled" not in reason
        assert "logged that exposure once at its own construction" not in reason
        assert "nexus installs nexus.auth.jwt.JWTMiddleware" in reason


class TestRealCallSitesPlumbTheExternalReasonThrough:
    """Both #2072 call sites already track ``self._external_auth_reason``;
    confirm both now forward it to the mounted sub-app, not just the pure
    function in isolation.
    """

    def test_workflow_server_mounts_sub_app_naming_the_real_external_reason(self):
        from kailash.servers.workflow_server import WorkflowServer

        workflow = Mock(spec=Workflow)
        workflow.workflow_id = "wf1"
        workflow.version = "1.0.0"

        server = WorkflowServer(
            external_auth_reason="nexus installs nexus.auth.jwt.JWTMiddleware",
            title="Regression Server",
        )
        with patch("kailash.servers.workflow_server.WorkflowAPI") as mock_workflow_api:
            server.register_workflow(name="wf1", workflow=workflow)
            reason = mock_workflow_api.call_args.kwargs["external_auth_reason"]

        assert "explicitly disabled" not in reason
        assert "nexus installs nexus.auth.jwt.JWTMiddleware" in reason

    def test_workflow_api_gateway_mounts_sub_app_naming_the_real_external_reason(
        self,
    ):
        from kailash.api.gateway import WorkflowAPIGateway

        workflow = Mock(spec=Workflow)
        workflow.workflow_id = "wf1"
        workflow.version = "1.0.0"

        gateway = WorkflowAPIGateway(
            external_auth_reason="nexus installs nexus.auth.jwt.JWTMiddleware",
            title="Regression Gateway",
        )
        with patch("kailash.api.gateway.WorkflowAPI") as mock_workflow_api:
            gateway.register_workflow(name="wf1", workflow=workflow, description="d")
            reason = mock_workflow_api.call_args.kwargs["external_auth_reason"]

        assert "explicitly disabled" not in reason
        assert "nexus installs nexus.auth.jwt.JWTMiddleware" in reason

    def test_workflow_server_disabled_case_still_names_the_real_warn(self):
        """Control: the genuinely-disabled branch is untouched by this fix."""
        from kailash.servers.workflow_server import WorkflowServer

        workflow = Mock(spec=Workflow)
        workflow.workflow_id = "wf1"
        workflow.version = "1.0.0"

        server = WorkflowServer(require_auth=False, title="Disabled Server")
        with patch("kailash.servers.workflow_server.WorkflowAPI") as mock_workflow_api:
            server.register_workflow(name="wf1", workflow=workflow)
            reason = mock_workflow_api.call_args.kwargs["external_auth_reason"]

        assert "explicitly disabled" in reason
