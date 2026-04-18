# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""§6.5 -- Classification-aware prompt redaction.

LLM prompts are user-controlled text that routinely carries PII. Before
any wire adapter serializes a `CompletionRequest`, the messages MUST be
routed through the configured classification policy so declared-PII
fields are redacted at the boundary.

This test drives the contract via `LlmClient.redact_request_messages`,
which wraps `kaizen.llm.redaction.redact_messages`. Wire adapters in
Session 3 (S3) call that method before any on-wire serialization; this
structural test proves the hook is installed and the helper is wired.

Rust spec §6.5 parity: cross-SDK helper name is `redact_messages`; the
DataFlow ClassificationPolicy contract
(`apply_masking_to_record(model_name, record, caller_clearance)`) is
byte-identical across SDKs.
"""

from __future__ import annotations

from typing import Any, Optional


class _FakePolicy:
    """Minimal duck-typed policy that masks specific field names.

    Intentionally NOT using the DataFlow ClassificationPolicy directly
    -- the test is asserting that the `LlmClient.redact_request_messages`
    surface calls `apply_masking_to_record` generically on any object
    exposing that method. A DataFlow-specific test would live in the
    DataFlow integration tier.
    """

    def __init__(self, redact_keys: list[str]) -> None:
        self.redact_keys = set(redact_keys)
        self.calls: list[tuple[str, dict, Any]] = []

    def apply_masking_to_record(
        self,
        model_name: str,
        record: dict,
        caller_clearance: Optional[Any],
    ) -> dict:
        self.calls.append((model_name, dict(record), caller_clearance))
        out = dict(record)
        for k in list(out.keys()):
            if k in self.redact_keys:
                out[k] = "[REDACTED]"
        return out


def test_llmclient_with_policy_redacts_content_field() -> None:
    """A classified `content` field is replaced by the policy's masker."""
    from kaizen.llm.client import LlmClient

    policy = _FakePolicy(redact_keys=["content"])
    client = LlmClient(classification_policy=policy)
    messages = [
        {"role": "user", "content": "my email is alice@example.com"},
        {"role": "user", "content": "my ssn is 123-45-6789"},
    ]
    redacted = client.redact_request_messages(messages)

    assert redacted == [
        {"role": "user", "content": "[REDACTED]"},
        {"role": "user", "content": "[REDACTED]"},
    ]
    # Input list is untouched -- caller may retain references for retry.
    assert messages[0]["content"] == "my email is alice@example.com"


def test_llmclient_without_policy_passes_messages_through_unchanged() -> None:
    """When no classification policy is installed, messages pass through
    unchanged -- but the helper STILL returns a new list (defensive copy).
    """
    from kaizen.llm.client import LlmClient

    client = LlmClient()
    messages = [{"role": "user", "content": "plain prompt"}]
    redacted = client.redact_request_messages(messages)

    assert redacted == messages
    assert redacted is not messages  # new list
    assert redacted[0] is not messages[0]  # new inner dict


def test_llmclient_policy_sees_model_name_and_clearance() -> None:
    """The policy receives `model_name` and `caller_clearance` unchanged
    from the LlmClient constructor -- the forwarding contract is verified.
    """
    from kaizen.llm.client import LlmClient

    policy = _FakePolicy(redact_keys=[])
    client = LlmClient(classification_policy=policy, caller_clearance="PUBLIC")
    client.redact_request_messages(
        [{"role": "user", "content": "hi"}], model_name="MyChatTurn"
    )

    assert len(policy.calls) == 1
    model_name, record, clearance = policy.calls[0]
    assert model_name == "MyChatTurn"
    assert record == {"role": "user", "content": "hi"}
    assert clearance == "PUBLIC"


def test_llmclient_default_model_name_is_llm_prompt_message() -> None:
    """Cross-SDK parity: default `model_name` is the literal
    'LlmPromptMessage' (byte-match with the Rust helper).
    """
    from kaizen.llm.client import LlmClient

    policy = _FakePolicy(redact_keys=[])
    client = LlmClient(classification_policy=policy)
    client.redact_request_messages([{"role": "user", "content": "hi"}])

    assert policy.calls[0][0] == "LlmPromptMessage"


def test_llmclient_policy_without_apply_masking_gets_warn_and_passthrough(
    caplog,
) -> None:
    """A policy object without `apply_masking_to_record` is inert -- the
    helper emits a WARN and passes the messages through unchanged. This
    prevents a silent-policy-drift failure mode where a refactor renames
    the masking method and nothing catches it.
    """
    import logging

    from kaizen.llm.client import LlmClient

    class BrokenPolicy:
        pass

    client = LlmClient(classification_policy=BrokenPolicy())
    with caplog.at_level(logging.WARNING, logger="kaizen.llm.redaction"):
        redacted = client.redact_request_messages(
            [{"role": "user", "content": "secret"}]
        )
    assert redacted == [{"role": "user", "content": "secret"}]
    warns = [
        r
        for r in caplog.records
        if r.getMessage() == "llm.redaction.policy_missing_apply_masking_to_record"
    ]
    assert warns, "expected a WARN when policy lacks apply_masking_to_record"
    assert warns[0].policy_class == "BrokenPolicy"


def test_llmclient_classification_policy_is_preserved_across_with_deployment() -> None:
    """`LlmClient.with_deployment(d)` MUST propagate the classification
    policy -- dropping it silently on deployment swap would remove the
    redaction gate at exactly the moment a caller is reconfiguring.
    """
    from kaizen.llm.client import LlmClient
    from kaizen.llm.deployment import LlmDeployment

    policy = _FakePolicy(redact_keys=["content"])
    c1 = LlmClient(classification_policy=policy, caller_clearance="PUBLIC")

    d = LlmDeployment.openai("sk-test", model="gpt-4o-mini")
    c2 = c1.with_deployment(d)

    assert c2.classification_policy is policy
    redacted = c2.redact_request_messages([{"role": "user", "content": "x"}])
    assert redacted == [{"role": "user", "content": "[REDACTED]"}]
