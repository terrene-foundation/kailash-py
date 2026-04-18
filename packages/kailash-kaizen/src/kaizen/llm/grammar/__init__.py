# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Model-grammar adapters for each provider's on-the-wire model identifier.

A "grammar" converts the caller-supplied model id (typically a short alias
the developer types: `claude-sonnet-4-6`) into the on-wire identifier the
provider expects (for Bedrock: `anthropic.claude-sonnet-4-6-v1:0`).

Grammars are provider-specific because on-wire IDs diverge by provider
even for the same underlying model -- OpenAI uses `gpt-4o`, Bedrock uses
`anthropic.claude-3-5-sonnet-20240620-v1:0`, Azure uses the deployment
name, Vertex uses `publishers/anthropic/models/claude-sonnet-4-5@001`.

Session 3 ships the Bedrock Claude grammar. Subsequent sessions add the
other four Bedrock families (Llama, Titan, Mistral, Cohere) plus the
inference-profile grammars for Vertex and Azure.
"""

from kaizen.llm.grammar.bedrock import BedrockClaudeGrammar

__all__ = ["BedrockClaudeGrammar"]
