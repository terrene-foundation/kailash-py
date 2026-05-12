"""Tier-2 integration test for issue #900 — credential_ref round-trip.

Exercises the full plumbing path that issue #900 fixes:

    BaseAgentConfig(api_key=..., base_url=...)
      → WorkflowGenerator.generate_signature_workflow()
      → CredentialStore.register() → 'cred_<uuid>' written to node_config
      → LocalRuntime.execute() → LLMAgentNode.execute()
      → LLMAgentNode reads self.config["credential_ref"] (llm_agent.py:848)
      → get_credential_store().resolve(credential_ref) returns Credential

NO MOCKING per rules/testing.md § Tier 2:

  * Uses the real ``provider="mock"`` LLM provider (a real implementation
    that returns a deterministic mock response — it is NOT a unittest.mock
    object). This satisfies the Protocol-Satisfying Deterministic Adapter
    exception documented in rules/testing.md.
  * Uses the real WorkflowGenerator, the real CredentialStore (in-process
    Python object — no network), the real WorkflowBuilder, the real
    LocalRuntime, and the real LLMAgentNode.
  * No ``@patch`` / ``MagicMock`` / ``unittest.mock`` anywhere.

The test asserts the round-trip behavior the issue's acceptance criteria
require: credential_ref survives end-to-end and the "Unknown parameter"
warning is NOT emitted.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator

import pytest
from kailash.runtime.local import LocalRuntime
from kailash.workflow.credentials import get_credential_store

from kaizen.core.config import BaseAgentConfig
from kaizen.core.workflow_generator import WorkflowGenerator
from kaizen.signatures import InputField, OutputField, Signature


class QASignature(Signature):
    """Minimal signature for the round-trip exercise."""

    question: str = InputField(desc="A question to answer")
    answer: str = OutputField(desc="The answer to the question")


@pytest.fixture(autouse=True)
def _clear_credential_store() -> Iterator[None]:
    """Per-test isolation — CredentialStore is process-global."""
    get_credential_store().clear()
    yield
    get_credential_store().clear()


@pytest.mark.integration
def test_credential_ref_round_trips_through_workflow_to_node(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """End-to-end: BaseAgentConfig → WorkflowGenerator → LLMAgentNode.

    Exercises the same plumbing chain a production user hits, with NO
    mocking. Asserts three contract properties:

      (a) WorkflowGenerator stored a credential_ref in node_config
          (security invariant — api_key MUST NOT live in node_config).
      (b) The store resolves the reference to the original api_key /
          base_url values.
      (c) Running the workflow through LocalRuntime does NOT emit any
          "Unknown parameter" WARNING on the kailash.nodes.base logger
          for credential_ref — this is the exact failure mode #900
          reports.
    """
    # Set provider env var so the workflow_generator does not raise on
    # configuration. The mock provider does not actually use this.
    os.environ.setdefault("OPENAI_API_KEY", "sk-test-noop")

    config = BaseAgentConfig(
        llm_provider="mock",
        model="mock-model",
        api_key="sk-issue-900-tenant-roundtrip",
        base_url="https://proxy.issue-900.example/v1",
    )
    generator = WorkflowGenerator(config=config, signature=QASignature())
    workflow = generator.generate_signature_workflow()

    # (a) Structural — credential_ref is in node_config; api_key is not.
    built = workflow.build()
    node = built.nodes.get("agent_exec")
    assert node is not None, "WorkflowGenerator must create agent_exec node"
    assert (
        "api_key" not in node.config
    ), "api_key MUST NOT live in serializable node_config (BYOK invariant)"
    assert (
        "base_url" not in node.config
    ), "base_url MUST NOT live in serializable node_config (BYOK invariant)"
    credential_ref = node.config.get("credential_ref")
    assert (
        credential_ref is not None
    ), "WorkflowGenerator MUST write credential_ref when api_key was provided"
    assert credential_ref.startswith(
        "cred_"
    ), f"credential_ref should be a 'cred_*' reference; got {credential_ref!r}"

    # (b) Round-trip — CredentialStore resolves the reference to original values.
    cred = get_credential_store().resolve(credential_ref)
    assert cred is not None, "credential_ref must resolve via get_credential_store"
    assert (
        cred.api_key == "sk-issue-900-tenant-roundtrip"
    ), f"api_key did not round-trip; got {cred.api_key!r}"
    assert (
        cred.base_url == "https://proxy.issue-900.example/v1"
    ), f"base_url did not round-trip; got {cred.base_url!r}"

    # (c) Behavioral — executing the workflow emits no Unknown-parameter
    #     warning for credential_ref. This is the exact stderr pollution
    #     the issue body documents.
    caplog.set_level(logging.WARNING, logger="kailash.nodes.base")

    runtime = LocalRuntime()
    results, _run_id = runtime.execute(
        built,
        parameters={
            "agent_exec": {
                "messages": [{"role": "user", "content": "What is 2+2?"}],
            }
        },
    )
    assert isinstance(results, dict), "Workflow execution must return a dict of results"

    unknown_param_warnings = [
        rec
        for rec in caplog.records
        if rec.name == "kailash.nodes.base"
        and rec.levelno >= logging.WARNING
        and "Unknown parameter" in rec.getMessage()
        and "credential_ref" in rec.getMessage()
    ]
    assert not unknown_param_warnings, (
        "Workflow execution emitted the issue-#900 Unknown-parameter warning "
        "for credential_ref. The NodeParameter declaration is missing or "
        "the validator no longer sees it. Captured records:\n"
        + "\n".join(f"  - {r.getMessage()}" for r in unknown_param_warnings)
    )


@pytest.mark.integration
def test_credential_ref_absent_when_no_api_key_provided() -> None:
    """Round-trip negative: no api_key/base_url → no credential_ref.

    Guards against the dual-mode silent-fallback pattern (Rule 3d). The
    workflow generator MUST only register credentials when the user
    actually supplied them; producing a phantom credential_ref otherwise
    would mask configuration bugs and bloat the CredentialStore.
    """
    config = BaseAgentConfig(llm_provider="mock", model="mock-model")
    generator = WorkflowGenerator(config=config, signature=QASignature())
    built = generator.generate_signature_workflow().build()
    node = built.nodes.get("agent_exec")
    assert node is not None
    assert (
        "credential_ref" not in node.config
    ), "credential_ref must NOT be written when no api_key/base_url supplied"
