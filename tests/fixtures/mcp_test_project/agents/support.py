# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Kaizen SupportAgent fixture for MCP integration tests."""

from kaizen.core import BaseAgent, Signature, InputField, OutputField


class SupportAgent(BaseAgent):
    """Customer support agent for handling queries."""

    class Sig(Signature):
        query: str = InputField(description="Customer support query")
        response: str = OutputField(description="Support response")
        confidence: float = OutputField(description="Confidence score")
