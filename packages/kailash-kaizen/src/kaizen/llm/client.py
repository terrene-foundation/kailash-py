# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""LlmClient — entry point for the four-axis deployment abstraction.

Additive API: introduces `LlmClient.from_deployment(...)` alongside the
existing `kaizen.providers.registry` surface. Registry consumers are
untouched (see the option-A decision journal in the #498 workspace).

Session 1 scope:

* `LlmClient.from_deployment(d)` returns a client carrying the deployment
  structurally; the concrete request-send path lands in S3.
* `LlmClient.from_env()` raises a typed `NotImplementedError` pointing at
  session 7 (S7) — actively-tracked iterative TODO per zero-tolerance
  Rule 2.
* `LlmClient()` (zero-arg) additive constructor — returns an empty client
  with `.with_deployment(d)` as the only path to a usable state.
"""

from __future__ import annotations

import logging
from typing import Optional

from kaizen.llm.deployment import LlmDeployment
from kaizen.llm.redaction import redact_messages

logger = logging.getLogger(__name__)


class LlmClient:
    """Uniform client over an `LlmDeployment`.

    The client holds the deployment by reference; the deployment is frozen
    so the client cannot mutate its own configuration post-construction.

    Optionally carries a DataFlow-compatible classification policy so
    every outbound `CompletionRequest.messages` payload is routed
    through `redact_messages` before wire-layer serialization. The
    policy is duck-typed on
    `apply_masking_to_record(model_name, record, caller_clearance)` --
    any class exposing that method works, but the DataFlow
    `ClassificationPolicy` is the canonical producer. See
    `rules/observability.md` § 8 and the §6.5 security test at
    `tests/unit/llm/security/test_llmclient_redacts_classified_prompt_fields.py`.
    """

    def __init__(
        self,
        deployment: Optional[LlmDeployment] = None,
        *,
        classification_policy: Optional[object] = None,
        caller_clearance: Optional[object] = None,
    ) -> None:
        self._deployment = deployment
        self._classification_policy = classification_policy
        self._caller_clearance = caller_clearance
        logger.debug(
            "llm_client.constructed",
            extra={
                "has_deployment": deployment is not None,
                "wire": str(deployment.wire) if deployment is not None else None,
                "has_classification_policy": classification_policy is not None,
            },
        )

    @property
    def deployment(self) -> Optional[LlmDeployment]:
        return self._deployment

    @property
    def classification_policy(self) -> Optional[object]:
        return self._classification_policy

    def redact_request_messages(
        self,
        messages,
        *,
        model_name: str = "LlmPromptMessage",
    ):
        """Apply the configured classification policy to outbound messages.

        Returns a NEW list; the input is not mutated. When no policy is
        installed this is a pure copy. Wire adapters (OpenAI / Bedrock /
        etc.) MUST call this helper before serializing the request
        payload so prompt PII is redacted at the boundary per §6.5.
        """
        return redact_messages(
            request_messages=messages,
            policy=self._classification_policy,
            model_name=model_name,
            caller_clearance=self._caller_clearance,
        )

    @classmethod
    def from_deployment(
        cls,
        deployment: LlmDeployment,
        *,
        classification_policy: Optional[object] = None,
        caller_clearance: Optional[object] = None,
    ) -> "LlmClient":
        """Construct a client for the given deployment."""
        if not isinstance(deployment, LlmDeployment):
            raise TypeError(
                "LlmClient.from_deployment requires an LlmDeployment; "
                f"got {type(deployment).__name__}"
            )
        return cls(
            deployment=deployment,
            classification_policy=classification_policy,
            caller_clearance=caller_clearance,
        )

    @classmethod
    def from_env(cls) -> "LlmClient":
        """Construct a client from environment variables.

        NOT YET IMPLEMENTED. Session 7 (S7) wires the env-loader precedence
        (dotenv + OS env + structured secret stores).
        """
        raise NotImplementedError(
            "LlmClient.from_env() — Implemented in session 7 (S7). "
            "For now use LlmClient.from_deployment(LlmDeployment.openai(...))."
        )

    def with_deployment(self, deployment: LlmDeployment) -> "LlmClient":
        """Return a NEW client configured with the given deployment."""
        if not isinstance(deployment, LlmDeployment):
            raise TypeError(
                "with_deployment requires an LlmDeployment; "
                f"got {type(deployment).__name__}"
            )
        return LlmClient(
            deployment=deployment,
            classification_policy=self._classification_policy,
            caller_clearance=self._caller_clearance,
        )

    async def complete(self, **kwargs: object) -> object:  # noqa: ARG002
        """Run a completion against the configured deployment.

        NOT YET IMPLEMENTED. Session 3 (S3) lands the OpenAI + Anthropic +
        Google wire adapters; subsequent sessions add Bedrock / Vertex /
        Azure. The method is declared here so Tier 2 wiring tests can grep
        for it.
        """
        raise NotImplementedError(
            "LlmClient.complete() — wire-layer send path implemented in "
            "session 3 (S3). Session 1 ships the structural abstraction only."
        )


__all__ = ["LlmClient"]
