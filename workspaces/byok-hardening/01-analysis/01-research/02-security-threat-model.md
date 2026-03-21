# BYOK Security Threat Model -- Deferred Items D1 and D5

## Executive Summary

This analysis covers two deferred security findings from the BYOK (Bring Your Own Key) red team round 1. Both are credential leakage vulnerabilities with different attack surfaces:

- **D1 (CRITICAL)**: API keys stored in serializable `node_config` leak through 7+ distinct output paths including JSON export, YAML export, distributed queue transport, workflow persistence, logging, and debugging output.
- **D5 (HIGH)**: Provider error messages forwarded via `str(e)` can contain credentials, base URLs with embedded auth, internal infrastructure details, and API key prefixes. There are 28 distinct `except` blocks in `ai_providers.py` that re-raise with `str(e)`.

---

## D1: API Key in Serializable node_config -- Full Threat Model

### Threat Model Diagram

```
                          BYOK API Key Entry
                                |
                                v
                    +------------------------+
                    | LLMAgentNode.execute()  |
                    | reads from:             |
                    |  self.config["api_key"] |
                    |  kwargs["api_key"]      |
                    +------------------------+
                                |
                    config["api_key"] = "sk-..."
                                |
        +-----------------------+------------------------+
        |                       |                        |
        v                       v                        v
  NodeInstance(             graph.add_node(         node_instance.config
  config=actual_config)    config=actual_config)   dict in memory
        |                       |                        |
        v                       v                        v
  +----------+           +----------+             +-----------+
  | LEAK 1   |           | LEAK 2   |             | LEAK 3    |
  | Pydantic |           | NetworkX |             | In-memory |
  | model_   |           | node     |             | dict ref  |
  | dump()   |           | attrs    |             | exposed   |
  +----------+           +----------+             +-----------+
        |                       |                        |
        v                       v                        v
  +-----------+  +-----------+  +-----------+  +-----------+
  | to_dict() |  | to_json() |  | to_yaml() |  | save()    |
  | line 1220 |  | line 1243 |  | line 1251 |  | line 1264 |
  +-----------+  +-----------+  +-----------+  +-----------+
        |              |              |              |
        v              v              v              v
  +-----------+  +-----------+  +-----------+  +-----------+
  | LEAK 4    |  | LEAK 5    |  | LEAK 6    |  | LEAK 7    |
  | Distrib.  |  | Export    |  | Manifest  |  | Tracking  |
  | Runtime   |  | Utility   |  | Builder   |  | Manager   |
  | line 570  |  | line 936  |  | line 568  |  | line 77   |
  +-----------+  +-----------+  +-----------+  +-----------+
        |              |              |              |
        v              v              v              v
    Redis queue    Filesystem     YAML/JSON     SQLite/DB
    (plaintext)    (plaintext)    (plaintext)   (plaintext)
```

### Attack Surface Catalog

#### LEAK 1: `Workflow.to_dict()` -- Primary Serialization Path

**File**: `src/kailash/workflow/graph.py`, line 1220
**Code**: `nodes_dict[node_id] = node_data.model_dump()`
**Impact**: `NodeInstance` is a Pydantic `BaseModel`. `model_dump()` serializes the entire `config` dict, including any `api_key` field, into a plain Python dict. Every downstream consumer of `to_dict()` inherits this leak.

#### LEAK 2: `Workflow.to_json()` / `Workflow.to_yaml()`

**File**: `src/kailash/workflow/graph.py`, lines 1237-1251
**Code**: `json.dumps(self.to_dict(), indent=2)` / `yaml.dump(self.to_dict())`
**Impact**: Both call `to_dict()` and produce string output. If written to a log file, returned via an API, or displayed in a UI, the API key is in plaintext.

#### LEAK 3: `Workflow.save()`

**File**: `src/kailash/workflow/graph.py`, lines 1253-1270
**Code**: `with open(path, "w") as f: f.write(self.to_json())`
**Impact**: Writes the full serialized workflow (including API keys in node configs) to a filesystem path. Depending on file permissions, this is accessible to other processes and users on the system.

#### LEAK 4: Distributed Runtime Queue Serialization

**File**: `src/kailash/runtime/distributed.py`, line 570
**Code**: `return workflow.to_dict()`
**Impact**: Workflows are serialized for Redis queue transport. API keys travel over the network in plaintext JSON, stored in Redis (potentially without auth), and readable by any worker that dequeues tasks. Redis persistence (`RDB`/`AOF`) writes keys to disk.

#### LEAK 5: Export Utility `_prepare_export_data()`

**File**: `src/kailash/utils/export.py`, line 936
**Code**: `"config": deepcopy(node_instance.config)`
**Impact**: The export system deep-copies the entire node config including credentials. Exported files (YAML, JSON, Terraform, Docker Compose) contain plaintext API keys. These files are often committed to version control or shared.

#### LEAK 6: Manifest Builder

**File**: `src/kailash/manifest.py`, lines 568, 654-655
**Code**: `yaml.dump(workflow.to_dict())` / `json.dumps(workflow.to_dict(), indent=2)`
**Impact**: Manifests are designed for sharing and deployment. API keys in manifests defeat the purpose of per-request credential isolation.

#### LEAK 7: Tracking and Task Persistence

**File**: `src/kailash/tracking/manager.py`, line 77
**Code**: `create_run(workflow_name=self.name, metadata={"inputs": inputs})`
**Impact**: The `metadata` dict may include node overrides containing API keys. These are persisted to SQLite or other storage backends for audit/tracking purposes. The data outlives the request.

#### LEAK 8: Debug Print Statements (Active in Production Code)

**File**: `src/kailash/workflow/graph.py`, lines 1104-1143
**Code**: Multiple `print(f"CONNECTION DEBUG: ...")` and `print(f"MAPPING DEBUG: ...")` statements
**Impact**: These print statements output `edge_data` and `source_results` which include node config data. In production deployments with stdout captured to logging aggregators (CloudWatch, Datadog, etc.), API keys appear in searchable log indices.

**File**: `packages/kailash-kaizen/src/kaizen/nodes/ai/llm_agent.py`, line 842-843
**Code**: `print(f"DEBUG: Using _provider_llm_response path for provider={provider}")`
**Impact**: While this specific print does not leak the key, it indicates a pattern of leaving debug output in production code. The tool-calling debug prints on lines 1089-1095 output tool definitions which could contain sensitive context.

#### LEAK 9: `NodeConfigurationError` Messages

**File**: `src/kailash/workflow/graph.py`, line 203
**Code**: `f"Failed to create node '{node_id}' of type '{node_class.__name__}': {e}. Constructor signature: {sig}. Config: {config}"`
**Impact**: If node creation fails, the full `config` dict (including `api_key`) is embedded in the exception message. This exception propagates up the call stack and may be logged, returned to the user, or stored in error tracking systems.

#### LEAK 10: `provider_config_to_dict()`

**File**: `packages/kailash-kaizen/src/kaizen/config/providers.py`, lines 671-698
**Code**: `if config.api_key is not None: config_dict["api_key"] = config.api_key`
**Impact**: This function explicitly includes the API key in its dict output. The dict is intended for "agent configuration" and is likely persisted or logged.

### Risk Assessment

| Vector                             | Likelihood | Impact   | Risk         |
| ---------------------------------- | ---------- | -------- | ------------ |
| Workflow JSON/YAML export with key | HIGH       | CRITICAL | **CRITICAL** |
| Redis queue transport              | HIGH       | CRITICAL | **CRITICAL** |
| Filesystem save()                  | MEDIUM     | CRITICAL | **HIGH**     |
| Debug print to stdout/logs         | HIGH       | HIGH     | **HIGH**     |
| NodeConfigurationError messages    | MEDIUM     | HIGH     | **HIGH**     |
| Export utility file generation     | MEDIUM     | CRITICAL | **HIGH**     |
| Tracking/audit persistence         | MEDIUM     | HIGH     | **HIGH**     |
| provider_config_to_dict            | LOW        | HIGH     | **MEDIUM**   |

### Why Pydantic SecretStr Does Not Work Here

`NodeInstance.config` is typed as `dict[str, Any]`. The node_config is a plain Python dict, not a Pydantic model with typed fields. `SecretStr` only works as a declared field type on a Pydantic model -- it cannot retroactively protect arbitrary dict values.

Even if we changed `config` to a Pydantic model with `api_key: SecretStr`, the existing serialization paths (`model_dump()`) would still include it unless we explicitly passed `exclude` or used `model_dump(mode="json")` with custom serializers -- and every call site would need updating.

### Recommended Fix: Runtime Credential Store

**Architecture**: Separate credentials from node config entirely.

```python
# New module: src/kailash/workflow/credentials.py

import threading
from typing import Optional

class CredentialStore:
    """Thread-safe, non-serializable credential store for workflow execution."""

    _SENSITIVE_KEYS = frozenset({"api_key", "base_url", "token", "secret",
                                  "password", "credential", "auth"})

    def __init__(self):
        self._store: dict[str, dict[str, str]] = {}
        self._lock = threading.Lock()

    def set(self, node_id: str, key: str, value: str) -> None:
        with self._lock:
            if node_id not in self._store:
                self._store[node_id] = {}
            self._store[node_id][key] = value

    def get(self, node_id: str, key: str) -> Optional[str]:
        with self._lock:
            return self._store.get(node_id, {}).get(key)

    def clear(self, node_id: Optional[str] = None) -> None:
        """Clear credentials. Call after execution completes."""
        with self._lock:
            if node_id:
                self._store.pop(node_id, None)
            else:
                self._store.clear()

    @classmethod
    def extract_sensitive(cls, config: dict) -> tuple[dict, dict]:
        """Split config into (safe_config, sensitive_config).

        Returns a config dict with sensitive keys removed,
        and a dict of the extracted sensitive values.
        """
        safe = {}
        sensitive = {}
        for k, v in config.items():
            if k in cls._SENSITIVE_KEYS:
                sensitive[k] = v
            else:
                safe[k] = v
        return safe, sensitive
```

**Integration points**:

1. `Workflow.add_node()`: Call `CredentialStore.extract_sensitive()` before creating `NodeInstance`. Store sensitive values in `CredentialStore`, pass only safe config to `NodeInstance`.
2. `LLMAgentNode.execute()`: Read credentials from `CredentialStore` instead of `self.config`.
3. `Workflow.to_dict()` / `to_json()` / `to_yaml()` / `save()`: Automatically safe because credentials never entered `NodeInstance.config`.
4. Distributed runtime: Credentials must be provided by the worker environment, not serialized in the queue payload.

**Interim mitigation** (until architectural fix ships):
Add a `_redact_config()` method that strips sensitive keys from config dicts before serialization, and call it in `to_dict()`, `_prepare_export_data()`, `_serialize_workflow()`, and all `NodeConfigurationError` messages.

---

## D5: Error Message Credential Leakage -- Full Catalog

### Catalog of `str(e)` Re-raise Points

I identified **28 distinct `except` blocks** in `ai_providers.py` that re-raise with `str(e)` embedded in the error message. Additionally, there are **3 more** in `llm_agent.py`.

| #   | Provider                | Method           | Line | Pattern                                                  | Risk         |
| --- | ----------------------- | ---------------- | ---- | -------------------------------------------------------- | ------------ |
| 1   | Ollama                  | `chat()`         | 562  | `f"Ollama error: {str(e)}"`                              | MEDIUM       |
| 2   | Ollama                  | `embed()`        | 619  | `f"Ollama embedding error: {str(e)}"`                    | MEDIUM       |
| 3   | OpenAI                  | `chat()`         | 1134 | `f"OpenAI API error: {str(e)}"`                          | **CRITICAL** |
| 4   | OpenAI                  | `chat()`         | 1136 | `f"OpenAI error: {str(e)}"`                              | **CRITICAL** |
| 5   | OpenAI                  | `chat_async()`   | 1342 | `f"OpenAI API error: {str(e)}"`                          | **CRITICAL** |
| 6   | OpenAI                  | `chat_async()`   | 1344 | `f"OpenAI error: {str(e)}"`                              | **CRITICAL** |
| 7   | OpenAI                  | `embed()`        | 1388 | `f"OpenAI embedding error: {str(e)}"`                    | **HIGH**     |
| 8   | OpenAI                  | `embed_async()`  | 1443 | `f"OpenAI embedding error: {str(e)}"`                    | **HIGH**     |
| 9   | Anthropic               | `chat()`         | 1657 | `f"Anthropic error: {str(e)}"`                           | **CRITICAL** |
| 10  | Cohere                  | `embed()`        | 1721 | `f"Cohere embedding error: {str(e)}"`                    | HIGH         |
| 11  | HuggingFace             | `_embed_api()`   | 1911 | `f"API error: {response.text}"`                          | **CRITICAL** |
| 12  | HuggingFace             | `_embed_api()`   | 1927 | `f"HuggingFace API error: {str(e)}"`                     | HIGH         |
| 13  | HuggingFace             | `_embed_local()` | 1987 | `f"HuggingFace local error: {str(e)}"`                   | LOW          |
| 14  | Azure                   | `chat()`         | 2741 | `f"Azure AI Foundry error: {str(e)}"`                    | **CRITICAL** |
| 15  | Azure                   | `chat_async()`   | 2838 | `f"Azure AI Foundry async error: {str(e)}"`              | **CRITICAL** |
| 16  | Azure                   | `embed()`        | 2868 | `f"Azure AI Foundry embedding error: {str(e)}"`          | HIGH         |
| 17  | Azure                   | `embed_async()`  | 2896 | `f"Azure AI Foundry async embedding error: {str(e)}"`    | HIGH         |
| 18  | Docker                  | `chat()`         | 3147 | `f"Docker Model Runner error: {str(e)}"`                 | MEDIUM       |
| 19  | Docker                  | `chat_async()`   | 3234 | `f"Docker Model Runner async error: {str(e)}"`           | MEDIUM       |
| 20  | Docker                  | `embed()`        | 3261 | `f"Docker Model Runner embedding error: {str(e)}"`       | MEDIUM       |
| 21  | Docker                  | `embed_async()`  | 3288 | `f"Docker Model Runner async embedding error: {str(e)}"` | MEDIUM       |
| 22  | Google                  | `chat()`         | 3787 | `f"Google Gemini error: {str(e)}"`                       | **CRITICAL** |
| 23  | Google                  | `chat_async()`   | 3916 | `f"Google Gemini async error: {str(e)}"`                 | **CRITICAL** |
| 24  | Google                  | `embed()`        | 3970 | `f"Google Gemini embedding error: {str(e)}"`             | HIGH         |
| 25  | Google                  | `embed_async()`  | 4019 | `f"Google Gemini async embedding error: {str(e)}"`       | HIGH         |
| 26  | Perplexity              | `chat()`         | 4514 | `f"Perplexity error: {error_msg}"`                       | **HIGH**     |
| 27  | Perplexity              | `chat_async()`   | 4570 | `f"Perplexity error: {error_msg}"`                       | **HIGH**     |
| 28  | get_available_providers | registry         | 4732 | `"error": str(e)`                                        | **HIGH**     |

**In `llm_agent.py`**:

| #   | Location                               | Line | Pattern                                  | Risk         |
| --- | -------------------------------------- | ---- | ---------------------------------------- | ------------ |
| 29  | `execute()`                            | 1049 | `"error": str(e)`                        | **CRITICAL** |
| 30  | `_provider_llm_response()`             | 2199 | `f"Provider {provider} error: {str(e)}"` | **CRITICAL** |
| 31  | `NodeConfigurationError` in `graph.py` | 203  | `Config: {config}` includes api_key      | **CRITICAL** |

### What Provider SDKs Include in Exception Messages

#### OpenAI SDK (`openai` Python package)

The OpenAI Python SDK exceptions include:

- **`AuthenticationError`**: Contains the API key prefix (e.g., `"Incorrect API key provided: sk-tenA...B12C"`) with partial masking. In BYOK, this reveals the tenant's key prefix to log aggregators.
- **`APIConnectionError`**: Contains the full `base_url` being connected to. If `base_url` contains embedded credentials (e.g., `https://user:password@proxy.example.com/v1`), the entire URL including credentials appears in `str(e)`.
- **`BadRequestError`**: Contains the full request body description including model name and parameter details.
- **`RateLimitError`**: Contains rate limit details and organization info.
- **`APIStatusError`**: Contains the HTTP response body, which may include internal error codes and infrastructure details.

#### Anthropic SDK (`anthropic` Python package)

- **`AuthenticationError`**: Contains the message from the API response, which may reference the API key.
- **`APIConnectionError`**: Contains the base URL and connection details.
- **`BadRequestError`**: Contains the full API error response body.

#### Google GenAI SDK (`google-genai` Python package)

- **`google.api_core.exceptions.InvalidArgument`**: Contains request parameter details.
- **`google.auth.exceptions.DefaultCredentialsError`**: Contains file paths to credential files.
- **`google.api_core.exceptions.PermissionDenied`**: May contain project ID and service account details.

#### Azure AI Inference SDK

- **`HttpResponseError`**: Contains the full HTTP response including headers that may contain `api-key` header values in certain error paths.
- **`ClientAuthenticationError`**: Contains endpoint URLs and credential type information.

### Credential-in-URL Attack Vector

If a user sets `base_url` to a URL with embedded credentials:

```python
# Attacker scenario: user passes a URL with embedded auth
config = get_provider_config(
    provider="openai",
    api_key="sk-legitimate",
    base_url="https://admin:s3cret@proxy.corp.com/v1"
)
```

When the connection fails, the OpenAI SDK raises:

```
openai.APIConnectionError: Connection error to https://admin:s3cret@proxy.corp.com/v1/chat/completions
```

This `str(e)` value is then re-raised as:

```
RuntimeError: OpenAI error: Connection error to https://admin:s3cret@proxy.corp.com/v1/chat/completions
```

In a multi-tenant system, this error message may be returned to a different tenant or logged in a shared system.

### Additional D5 Concern: LLMAgentNode Error Response

**File**: `packages/kailash-kaizen/src/kaizen/nodes/ai/llm_agent.py`, lines 1047-1060

```python
return {
    "success": False,
    "error": str(e),          # <-- Full provider error with potential credentials
    "error_type": type(e).__name__,
    "provider": provider,
    "model": model,
    ...
}
```

This error dict is a **node output**. It flows downstream in the workflow to other nodes, is stored in `results[node_id]`, and may be:

1. Returned via API endpoints to the calling user
2. Stored in execution logs
3. Displayed in monitoring dashboards
4. Passed to downstream error-handling nodes

The convergence fix at line 1034-1036 strips `api_key` and `base_url` from `kwargs` in the `error_context`, but the `str(e)` on line 1049 is the provider exception which may already contain credential information from the SDK.

### Recommended Fix: `sanitize_provider_error()` Function

```python
# packages/kailash-kaizen/src/kaizen/nodes/ai/error_sanitizer.py

import re
from typing import Optional

# Patterns that match credentials in error messages
_CREDENTIAL_PATTERNS = [
    # API key patterns (OpenAI, Anthropic, Google, Perplexity, Azure)
    re.compile(r'sk-[a-zA-Z0-9]{20,}', re.ASCII),           # OpenAI keys
    re.compile(r'sk-proj-[a-zA-Z0-9_-]{20,}', re.ASCII),    # OpenAI project keys
    re.compile(r'sk-ant-[a-zA-Z0-9_-]{20,}', re.ASCII),     # Anthropic keys
    re.compile(r'AIza[a-zA-Z0-9_-]{30,}', re.ASCII),        # Google API keys
    re.compile(r'pplx-[a-zA-Z0-9]{20,}', re.ASCII),         # Perplexity keys
    re.compile(r'[a-f0-9]{32}', re.ASCII),                   # Generic 32-char hex (Azure, etc.)

    # Bearer tokens in error messages
    re.compile(r'Bearer\s+[a-zA-Z0-9._-]+', re.ASCII),

    # Credentials embedded in URLs
    re.compile(r'://[^@\s]+:[^@\s]+@', re.ASCII),           # user:pass@host

    # Partial key exposure (OpenAI style: "sk-tenA...B12C")
    re.compile(r'sk-[a-zA-Z0-9]{3,4}\.\.\.[a-zA-Z0-9]{3,4}', re.ASCII),

    # Azure subscription/tenant IDs that could be sensitive
    re.compile(
        r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
        re.ASCII | re.IGNORECASE
    ),
]

# URL pattern for base_url sanitization
_URL_WITH_AUTH = re.compile(r'(https?://)([^@\s]+):([^@\s]+)@', re.ASCII)

# Internal path patterns
_INTERNAL_PATH_PATTERNS = [
    re.compile(r'/home/[a-zA-Z0-9_-]+/', re.ASCII),
    re.compile(r'/Users/[a-zA-Z0-9_-]+/', re.ASCII),
    re.compile(r'C:\\Users\\[a-zA-Z0-9_-]+\\', re.ASCII),
]


def sanitize_provider_error(
    error: Exception,
    provider_name: str,
    *,
    include_error_type: bool = True,
) -> str:
    """Sanitize a provider error message to remove credential patterns.

    This function strips API keys, bearer tokens, URL-embedded credentials,
    and internal paths from provider exception messages before they are
    exposed to callers or logged.

    Args:
        error: The caught exception from a provider SDK.
        provider_name: Name of the provider (for the generic message prefix).
        include_error_type: Whether to include the exception class name.

    Returns:
        A sanitized error string safe for multi-tenant exposure.
    """
    raw = str(error)
    sanitized = raw

    # Replace credential patterns with redaction markers
    for pattern in _CREDENTIAL_PATTERNS:
        sanitized = pattern.sub('[REDACTED]', sanitized)

    # Replace URL-embedded credentials
    sanitized = _URL_WITH_AUTH.sub(r'\1[REDACTED]:[REDACTED]@', sanitized)

    # Replace internal file paths
    for pattern in _INTERNAL_PATH_PATTERNS:
        sanitized = pattern.sub('[PATH]/', sanitized)

    # Build the final message
    parts = [f"{provider_name} error"]
    if include_error_type:
        parts.append(f"({type(error).__name__})")
    parts.append(f": {sanitized}")

    return "".join(parts)


def generic_provider_error(provider_name: str, error: Exception) -> str:
    """Return a fully generic error message, logging the real error server-side.

    For maximum safety in multi-tenant scenarios, this returns only
    the provider name and error class -- no message content at all.

    The caller is responsible for logging the full error server-side
    before calling this function.

    Args:
        provider_name: Name of the provider.
        error: The caught exception.

    Returns:
        A generic error string with no sensitive content.
    """
    return (
        f"{provider_name} request failed ({type(error).__name__}). "
        "Check server logs for details."
    )
```

**Usage in providers**:

```python
# Before (VULNERABLE):
except Exception as e:
    raise RuntimeError(f"OpenAI error: {str(e)}")

# After (SAFE -- option A: sanitized message):
except Exception as e:
    logger.error(f"OpenAI error (full): {e}", exc_info=True)  # Server-side only
    raise RuntimeError(sanitize_provider_error(e, "OpenAI"))

# After (SAFE -- option B: generic message for multi-tenant):
except Exception as e:
    logger.error(f"OpenAI error (full): {e}", exc_info=True)  # Server-side only
    raise RuntimeError(generic_provider_error("OpenAI", e))
```

**Usage in LLMAgentNode**:

```python
# Before (VULNERABLE):
return {
    "success": False,
    "error": str(e),
    ...
}

# After (SAFE):
return {
    "success": False,
    "error": sanitize_provider_error(e, provider),
    ...
}
```

### PR5 Compliance Note

Per production readiness pattern PR5: "API responses MUST NOT contain `str(e)`. Log full error server-side, return generic message to client." The current codebase violates PR5 in 31 locations across the BYOK credential flow. The `generic_provider_error()` function provides full PR5 compliance for multi-tenant deployments, while `sanitize_provider_error()` provides a balance between debuggability and safety for single-tenant use.

---

## Combined Risk Matrix

| ID     | Vulnerability                        | Severity | Exploitability         | Multi-tenant Impact     | Fix Complexity |
| ------ | ------------------------------------ | -------- | ---------------------- | ----------------------- | -------------- |
| D1-L1  | `model_dump()` serializes api_key    | CRITICAL | Easy (any export)      | Full key exposure       | Medium         |
| D1-L2  | `to_json()`/`to_yaml()` includes key | CRITICAL | Easy (save/export)     | Full key exposure       | Medium         |
| D1-L3  | `save()` writes key to filesystem    | HIGH     | Medium (needs access)  | Full key exposure       | Medium         |
| D1-L4  | Distributed runtime Redis transport  | CRITICAL | Easy (Redis access)    | Cross-tenant exposure   | High           |
| D1-L5  | Export utility deep-copies config    | HIGH     | Medium (export flow)   | Full key exposure       | Medium         |
| D1-L6  | Manifest builder includes config     | HIGH     | Medium (manifest flow) | Full key exposure       | Medium         |
| D1-L7  | Tracking persistence                 | HIGH     | Medium (DB access)     | Historical key exposure | Medium         |
| D1-L8  | Debug print statements in prod       | HIGH     | Easy (log access)      | Full key exposure       | Low            |
| D1-L9  | NodeConfigurationError messages      | HIGH     | Medium (error path)    | Full key exposure       | Low            |
| D1-L10 | `provider_config_to_dict()`          | MEDIUM   | Low (explicit call)    | Full key exposure       | Low            |
| D5-01  | OpenAI `str(e)` with key prefix      | CRITICAL | Easy (API error)       | Partial key + infra     | Low            |
| D5-02  | Anthropic `str(e)` with key ref      | CRITICAL | Easy (API error)       | Partial key + infra     | Low            |
| D5-03  | URL-embedded credentials in errors   | CRITICAL | Easy (connection err)  | Full proxy creds        | Low            |
| D5-04  | Azure `str(e)` with endpoint info    | HIGH     | Medium (API error)     | Infrastructure exposure | Low            |
| D5-05  | Google `str(e)` with project info    | HIGH     | Medium (API error)     | GCP project exposure    | Low            |
| D5-06  | `LLMAgentNode.execute()` error dict  | CRITICAL | Easy (any failure)     | Full error to caller    | Low            |
| D5-07  | `get_available_providers` error dict | HIGH     | Low (registry scan)    | Error detail exposure   | Low            |
| D5-08  | HuggingFace `response.text` in error | CRITICAL | Easy (API error)       | Raw API response leak   | Low            |

---

## Priority-Ordered Fix Recommendations

### P0 (Before any multi-tenant deployment)

1. **Implement `sanitize_provider_error()`** and apply to all 28 except blocks in `ai_providers.py` plus 3 in `llm_agent.py`. This is the lowest-effort, highest-impact fix. Estimated: 2-3 hours.

2. **Strip `api_key` and `base_url` from `NodeConfigurationError` messages** in `graph.py` lines 188-205. Replace `Config: {config}` with `Config keys: {list(config.keys())}`. Estimated: 30 minutes.

3. **Sanitize the `LLMAgentNode.execute()` error response** at line 1049. Replace `"error": str(e)` with `"error": sanitize_provider_error(e, provider)`. Estimated: 15 minutes.

4. **Remove debug print statements** from `graph.py` (lines 1104-1143) and `llm_agent.py` (lines 842-843, 1020-1025, 1089-1095). These are production code with `print()` statements that leak internal state. Estimated: 30 minutes.

### P1 (Before BYOK GA)

5. **Implement `CredentialStore`** and integrate with `Workflow.add_node()` to strip sensitive keys from `NodeInstance.config`. This is the architectural fix for D1. Estimated: 1-2 days.

6. **Add `_redact_config()` as interim defense-in-depth** in `to_dict()`, `_prepare_export_data()`, `_serialize_workflow()`. Even after CredentialStore ships, this provides a safety net. Estimated: 2-3 hours.

7. **Sanitize `provider_config_to_dict()`** -- either exclude `api_key` from the output or replace with a redacted sentinel value. Estimated: 30 minutes.

### P2 (Hardening)

8. **Add unit tests** for `sanitize_provider_error()` covering all known SDK error message formats.

9. **Add integration tests** verifying that `workflow.to_dict()` never contains values matching `_CREDENTIAL_PATTERNS`.

10. **Audit `get_available_providers()`** at line 4732 -- the `"error": str(e)` in the registry scan response should use `sanitize_provider_error()`.

---

## Files Referenced

- `/Users/esperie/repos/kailash/kailash-py/src/kailash/workflow/graph.py` -- `NodeInstance`, `Workflow.to_dict()`, `to_json()`, `to_yaml()`, `save()`, `NodeConfigurationError` messages, debug print statements
- `/Users/esperie/repos/kailash/kailash-py/packages/kailash-kaizen/src/kaizen/nodes/ai/ai_providers.py` -- 28 `except` blocks with `str(e)`, per-request BYOK client construction
- `/Users/esperie/repos/kailash/kailash-py/packages/kailash-kaizen/src/kaizen/nodes/ai/llm_agent.py` -- `LLMAgentNode.execute()` error response, `_provider_llm_response()` error re-raise, `self.config["api_key"]` access pattern
- `/Users/esperie/repos/kailash/kailash-py/packages/kailash-kaizen/src/kaizen/config/providers.py` -- `ProviderConfig` dataclass with `api_key` field, `provider_config_to_dict()`, `get_provider_config()`, `auto_detect_provider()`
- `/Users/esperie/repos/kailash/kailash-py/src/kailash/runtime/distributed.py` -- `_serialize_workflow()` sends full config to Redis
- `/Users/esperie/repos/kailash/kailash-py/src/kailash/utils/export.py` -- `_prepare_export_data()` deep-copies config to export files
- `/Users/esperie/repos/kailash/kailash-py/src/kailash/manifest.py` -- Manifest builder serializes workflow config
- `/Users/esperie/repos/kailash/kailash-py/src/kailash/tracking/manager.py` -- Task tracking persistence
