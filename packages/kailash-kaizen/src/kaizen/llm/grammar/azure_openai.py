# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Azure OpenAI deployment-name grammar (#498 S6).

Azure OpenAI does not use upstream OpenAI model ids on the wire. Instead,
every request addresses a *deployment name* that the operator created in
the Azure portal. The deployment name is free-form (Azure's validation
allows `[a-zA-Z0-9_-]{1,64}`) and maps to a specific model version +
region on the Azure side.

`AzureOpenAIGrammar.resolve(caller_model)` validates the deployment name
against the Azure allowlist regex and returns it unchanged. There is NO
alias-to-canonical mapping (unlike Bedrock / Vertex) because Azure
deployment names are caller-chosen and vary per operator.

Cross-SDK parity: the validation regex + `grammar_kind()` label are
byte-identical to `kailash-rs/crates/kailash-kaizen/src/llm/grammar/azure.rs`.
"""

from __future__ import annotations

import re

from kaizen.llm.errors import ModelGrammarInvalid


# Azure deployment-name allowlist: letters, digits, underscore, hyphen.
# Length 1-64 matches Azure's documented constraint. Deliberately rejects
# CRLF, control chars, spaces, unicode, and any URL-special char that
# could be an injection vector if interpolated into a request path.
_AZURE_DEPLOYMENT_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


class AzureOpenAIGrammar:
    """Validate Azure OpenAI deployment names.

    `resolve(caller_model)` returns the deployment name unchanged on
    success; raises `ModelGrammarInvalid` otherwise. The raw value is
    NOT echoed in the error message (log-injection defense).
    """

    __slots__ = ()

    def resolve(self, caller_model: str) -> str:
        if not isinstance(caller_model, str) or not caller_model:
            raise ModelGrammarInvalid(
                "AzureOpenAI deployment name must be a non-empty string"
            )
        if not _AZURE_DEPLOYMENT_NAME_RE.match(caller_model):
            raise ModelGrammarInvalid(
                "AzureOpenAI deployment name failed validation against "
                f"^[a-zA-Z0-9_-]{{1,64}}$ (length={len(caller_model)})"
            )
        return caller_model

    def grammar_kind(self) -> str:
        return "azure_openai"


__all__ = ["AzureOpenAIGrammar"]
