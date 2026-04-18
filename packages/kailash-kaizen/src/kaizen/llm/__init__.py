"""
LLM Module for Kaizen Agent Framework.

Provides LLM routing, capability management, intelligent model selection,
LLM-first reasoning helpers, and the four-axis LLM deployment abstraction
(introduced in #498 Session 1).
"""

# Import presets to register openai and attach the classmethod onto LlmDeployment.
from kaizen.llm import presets as _presets  # noqa: F401
from kaizen.llm.auth import AuthStrategy, Custom
from kaizen.llm.auth.aws import (
    BEDROCK_SUPPORTED_REGIONS,
    AwsBearerToken,
    AwsCredentials,
    AwsSigV4,
    ClockSkew,
    RegionNotAllowed,
)
from kaizen.llm.auth.bearer import ApiKey, ApiKeyBearer, ApiKeyHeaderKind, StaticNone
from kaizen.llm.client import LlmClient
from kaizen.llm.deployment import (
    CompletionRequest,
    EmbedOptions,
    Endpoint,
    LlmDeployment,
    ResolvedModel,
    RetryConfig,
    StreamingConfig,
    WireProtocol,
)
from kaizen.llm.errors import (
    AuthError,
    EndpointError,
    LlmClientError,
    LlmError,
    ModelGrammarError,
    ModelRequired,
)
from kaizen.llm.grammar.bedrock import (
    BedrockClaudeGrammar,
    BedrockCohereGrammar,
    BedrockLlamaGrammar,
    BedrockMistralGrammar,
    BedrockTitanGrammar,
)
from kaizen.llm.http_client import LlmHttpClient, SafeDnsResolver
from kaizen.llm.reasoning import (
    CapabilityMatchAgent,
    CapabilityMatchSignature,
    TextSimilarityAgent,
    TextSimilaritySignature,
    clear_reasoning_cache,
    get_capability_match_agent,
    get_text_similarity_agent,
    llm_capability_match,
    llm_text_similarity,
)
from kaizen.llm.routing import (  # Capabilities; Task Analysis; Routing
    MODEL_REGISTRY,
    FallbackRouter,
    LLMCapabilities,
    LLMRouter,
    RoutingRule,
    RoutingStrategy,
    TaskAnalysis,
    TaskAnalyzer,
    TaskComplexity,
    TaskType,
    get_model_capabilities,
    list_models,
    register_model,
)
from kaizen.llm.url_safety import check_url

__all__ = [
    # Four-axis deployment abstraction (#498)
    "LlmDeployment",
    "WireProtocol",
    "Endpoint",
    "ResolvedModel",
    "EmbedOptions",
    "CompletionRequest",
    "StreamingConfig",
    "RetryConfig",
    "LlmClient",
    # Auth strategies
    "AuthStrategy",
    "Custom",
    "ApiKey",
    "ApiKeyBearer",
    "ApiKeyHeaderKind",
    "StaticNone",
    # AWS auth (#498 S4a + S4b-i)
    "AwsBearerToken",
    "AwsCredentials",
    "AwsSigV4",
    "BEDROCK_SUPPORTED_REGIONS",
    "RegionNotAllowed",
    "ClockSkew",
    # Grammar (#498 S4a + S4b-ii)
    "BedrockClaudeGrammar",
    "BedrockLlamaGrammar",
    "BedrockTitanGrammar",
    "BedrockMistralGrammar",
    "BedrockCohereGrammar",
    # HTTP client + SafeDnsResolver (#498 S4c)
    "LlmHttpClient",
    "SafeDnsResolver",
    # SSRF guard
    "check_url",
    # Error taxonomy
    "LlmClientError",
    "LlmError",
    "AuthError",
    "EndpointError",
    "ModelGrammarError",
    "ModelRequired",
    # Capabilities
    "LLMCapabilities",
    "MODEL_REGISTRY",
    "get_model_capabilities",
    "register_model",
    "list_models",
    # Task Analysis
    "TaskComplexity",
    "TaskType",
    "TaskAnalysis",
    "TaskAnalyzer",
    # Routing
    "RoutingStrategy",
    "RoutingRule",
    "LLMRouter",
    "FallbackRouter",
    # LLM-first reasoning
    "TextSimilaritySignature",
    "CapabilityMatchSignature",
    "TextSimilarityAgent",
    "CapabilityMatchAgent",
    "llm_text_similarity",
    "llm_capability_match",
    "get_text_similarity_agent",
    "get_capability_match_agent",
    "clear_reasoning_cache",
]
