# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Canonical governance errors without trust-package initialization dependencies."""

from __future__ import annotations

from typing import Any


class PactError(Exception):
    """Base class for all PACT governance errors.

    Attributes:
        details: Structured context about the error (e.g., addresses,
            constraint values, envelope IDs). Defaults to an empty dict.
    """

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class UngovernedEgressRefused(PactError):
    """Raised when the ``governance_required`` posture is active and a bare,
    un-governed client/agent would make a real LLM call with no governance
    attached (#1779, EATP D6 parity).

    The message names BOTH remedies verbatim — route egress through a governed
    path, or opt out with ``ungoverned=True``. It interpolates ONLY the
    construction surface name (``LlmClient`` / ``Agent``); no URL, API key, or
    model is ever placed in the message (invariant 7: no secrets in the error).
    """

    def __init__(
        self,
        surface: str = "LlmClient",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            f"KAILASH_GOVERNANCE_REQUIRED is active and this {surface} would make "
            "a real LLM call with no governance attached. Either (1) route egress "
            "through a governed path — the legacy GovernedProvider wrapper governs "
            "the legacy provider API — or (2) pass ungoverned=True to explicitly "
            "opt out (the concrete opt-out for the four-axis LlmClient / Agent / "
            "LLMAgentNode surface). An installed process-global interceptor does "
            "NOT govern the four-axis LlmClient and does not waive this refusal.",
            details=details,
        )


PactError.__module__ = "kailash.trust.pact.exceptions"
PactError.__init__.__module__ = "kailash.trust.pact.exceptions"
UngovernedEgressRefused.__module__ = "kailash.trust.pact.exceptions"
UngovernedEgressRefused.__init__.__module__ = "kailash.trust.pact.exceptions"
