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

logger = logging.getLogger(__name__)


class LlmClient:
    """Uniform client over an `LlmDeployment`.

    The client holds the deployment by reference; the deployment is frozen
    so the client cannot mutate its own configuration post-construction.
    """

    def __init__(self, deployment: Optional[LlmDeployment] = None) -> None:
        self._deployment = deployment
        logger.debug(
            "llm_client.constructed",
            extra={
                "has_deployment": deployment is not None,
                "wire": str(deployment.wire) if deployment is not None else None,
            },
        )

    @property
    def deployment(self) -> Optional[LlmDeployment]:
        return self._deployment

    @classmethod
    def from_deployment(cls, deployment: LlmDeployment) -> "LlmClient":
        """Construct a client for the given deployment."""
        if not isinstance(deployment, LlmDeployment):
            raise TypeError(
                "LlmClient.from_deployment requires an LlmDeployment; "
                f"got {type(deployment).__name__}"
            )
        return cls(deployment=deployment)

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
        return LlmClient(deployment=deployment)

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
