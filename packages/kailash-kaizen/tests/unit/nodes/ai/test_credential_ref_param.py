"""Tier-1 unit tests for issue #900 — credential_ref NodeParameter declaration.

WorkflowGenerator writes ``credential_ref`` into LLMAgentNode config to plumb
CredentialStore references (BYOK security model). LLMAgentNode reads it back
at execution time. Both ends agreed on the contract, but ``get_parameters()``
did not declare ``credential_ref``, so Kailash's runtime validator
(``src/kailash/nodes/base.py:1018``) flagged it as an "Unknown parameter" on
every ``run_async`` invocation.

The fix declares ``credential_ref`` as ``type=str``, ``required=False`` in
``LLMAgentNode.get_parameters()``. These Tier-1 tests pin the declaration
(structural) and pin the no-warning behavior (logger capture).
"""

from __future__ import annotations

import logging

import pytest

from kaizen.nodes.ai import LLMAgentNode


@pytest.mark.regression
def test_credential_ref_is_declared_in_get_parameters() -> None:
    """Structural: ``credential_ref`` MUST appear in declared parameters.

    Locks the contract between WorkflowGenerator (writer) and LLMAgentNode
    (reader). If this declaration is dropped in a future refactor, the
    runtime validator will resume flagging "Unknown parameter".
    """
    node = LLMAgentNode()
    params = node.get_parameters()

    assert "credential_ref" in params, (
        "credential_ref MUST be declared in LLMAgentNode.get_parameters() — "
        "WorkflowGenerator writes it into node_config and llm_agent.py:848 "
        "reads it back to resolve from get_credential_store()."
    )

    param = params["credential_ref"]
    assert param.type is str, (
        f"credential_ref MUST be type=str (got {param.type}); "
        "the value is a reference ID like 'cred_a1b2c3d4e5f6'."
    )
    assert param.required is False, (
        "credential_ref MUST be required=False — only present when "
        "BaseAgentConfig was constructed with api_key/base_url overrides."
    )


@pytest.mark.regression
def test_run_async_with_credential_ref_emits_no_unknown_parameter_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Behavioral: validate_inputs MUST NOT log "Unknown parameter" for credential_ref.

    The Kailash runtime validator (`src/kailash/nodes/base.py:_validate_inputs`)
    emits a WARNING on the ``kailash.nodes.base`` logger when a config key is
    not declared in ``get_parameters()``. Calling ``execute()`` with a config
    containing ``credential_ref`` MUST NOT trigger that warning now that the
    parameter is declared.

    This is a structural test: the validator's log line is a stable runtime
    contract documented at base.py:1017-1031. No regex over assistant prose;
    we capture the structured log record and assert by field membership.
    """
    # Capture warnings from the kailash.nodes.base validator logger.
    caplog.set_level(logging.WARNING, logger="kailash.nodes.base")

    node = LLMAgentNode(
        provider="mock",
        model="mock-model",
        credential_ref="cred_abcdef123456",
    )

    # execute() merges self.config into runtime_inputs and runs validate_inputs.
    # With provider=mock the credential_ref resolution branch (line 848) is not
    # taken, but the validator runs first — that's the surface we're testing.
    result = node.execute(
        messages=[{"role": "user", "content": "hello"}],
    )
    assert (
        result.get("success") is True
    ), f"mock provider execution should succeed; got: {result.get('error')}"

    # Surface every WARNING record from kailash.nodes.base. None of them
    # should reference credential_ref as an unknown parameter.
    unknown_param_warnings = [
        rec
        for rec in caplog.records
        if rec.name == "kailash.nodes.base"
        and rec.levelno >= logging.WARNING
        and "Unknown parameter" in rec.getMessage()
        and "credential_ref" in rec.getMessage()
    ]

    assert not unknown_param_warnings, (
        "validate_inputs() emitted 'Unknown parameter' warning for "
        "credential_ref despite it being declared in get_parameters(). "
        "Captured records:\n"
        + "\n".join(f"  - {r.getMessage()}" for r in unknown_param_warnings)
    )


@pytest.mark.regression
def test_run_async_without_credential_ref_still_clean(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Baseline: nodes WITHOUT credential_ref also emit no warning.

    Guards against a regression where adding the declaration accidentally
    raises a different warning for the un-passed case (e.g. required=True
    by mistake).
    """
    caplog.set_level(logging.WARNING, logger="kailash.nodes.base")

    node = LLMAgentNode(provider="mock", model="mock-model")
    result = node.execute(messages=[{"role": "user", "content": "ping"}])
    assert result.get("success") is True

    unknown_param_warnings = [
        rec
        for rec in caplog.records
        if rec.name == "kailash.nodes.base"
        and rec.levelno >= logging.WARNING
        and "Unknown parameter" in rec.getMessage()
    ]
    assert not unknown_param_warnings, (
        "Baseline mock execution without credential_ref should not emit "
        "any Unknown-parameter warnings. Captured:\n"
        + "\n".join(f"  - {r.getMessage()}" for r in unknown_param_warnings)
    )
