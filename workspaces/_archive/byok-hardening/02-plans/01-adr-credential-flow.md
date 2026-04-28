# ADR-001: BYOK Credential Flow Architecture

## Status

**Accepted** — Credential Store approach selected by stakeholder decision.

## Context

The Kailash Kaizen framework supports BYOK (Bring Your Own Key) per-request API key overrides. Issue #12 implemented this by threading `api_key` and `base_url` through the provider chain via `node_config`.

Red team R1 found that `node_config` is serializable — API keys leak through 10+ paths including JSON export, Redis queue transport, filesystem save, debug logging, and error messages.

## Decision

**Use a runtime Credential Store that separates credentials from serializable workflow config.**

Credentials never enter `NodeInstance.config`. They flow through a non-serializable, request-scoped `CredentialStore` that the runtime injects into node execution context.

### Why Credential Store Over Redaction

The redaction approach (override `model_dump()` to filter `_SENSITIVE_KEYS`) was evaluated and rejected:

1. **Defense-in-depth is insufficient**: Redaction protects `model_dump()` but not `deepcopy()` (export.py:936), direct dict access, `repr()`, debugger inspection, or any new serialization path that bypasses `model_dump()`.
2. **10 leak vectors**: With 10 confirmed serialization paths, patching each one is error-prone. Missing one means a credential leak.
3. **Architectural clarity**: Credentials are a runtime concern. Mixing them into config (a build-time concern) creates a category error that redaction papers over.
4. **Long-term scalability**: As more credential types are added (refresh tokens, client secrets, mTLS certs), a `_SENSITIVE_KEYS` set becomes a maintenance liability. A credential store scales naturally.

### Architecture

```
BaseAgentConfig(api_key="sk-tenant-123")
  -> WorkflowGenerator.generate_signature_workflow()
    -> credential_ref = CredentialStore.register(api_key, base_url)
    -> node_config["_credential_ref"] = credential_ref    # Safe to serialize
    -> NodeInstance(config={"_credential_ref": "cred_abc123", ...})
      -> workflow.to_dict()  # SAFE: only contains reference, not key
      -> LLMAgentNode.process()
        -> creds = CredentialStore.resolve(self.config["_credential_ref"])
          -> provider.chat(..., api_key=creds.api_key)
            -> openai.OpenAI(api_key=creds.api_key)  # Used, then discarded
```

### CredentialStore Design

```python
# src/kailash/workflow/credentials.py

import hashlib
import threading
import uuid
from dataclasses import dataclass
from typing import ClassVar, Optional

@dataclass(frozen=True)
class Credential:
    """Immutable credential bundle."""
    api_key: Optional[str] = None
    base_url: Optional[str] = None

class CredentialStore:
    """Thread-safe, non-serializable credential store for workflow execution.

    Credentials are registered before execution and resolved during execution.
    The store is request-scoped — cleared after each workflow run.
    """

    _SENSITIVE_KEYS: ClassVar[frozenset] = frozenset({
        "api_key", "base_url", "api_secret", "token",
        "password", "credential", "auth",
    })

    def __init__(self):
        self._store: dict[str, Credential] = {}
        self._lock = threading.Lock()

    def register(self, api_key: str = None, base_url: str = None) -> str:
        """Register credentials and return a safe reference ID."""
        ref_id = f"cred_{uuid.uuid4().hex[:12]}"
        with self._lock:
            self._store[ref_id] = Credential(api_key=api_key, base_url=base_url)
        return ref_id

    def resolve(self, ref_id: str) -> Optional[Credential]:
        """Resolve a credential reference to actual credentials."""
        with self._lock:
            return self._store.get(ref_id)

    def clear(self, ref_id: str = None) -> None:
        """Clear credentials after execution completes."""
        with self._lock:
            if ref_id:
                self._store.pop(ref_id, None)
            else:
                self._store.clear()

    @classmethod
    def extract_sensitive(cls, config: dict) -> tuple[dict, dict]:
        """Split config into (safe_config, sensitive_values).

        Returns config with sensitive keys removed, plus the extracted values.
        """
        safe = {}
        sensitive = {}
        for k, v in config.items():
            if k in cls._SENSITIVE_KEYS:
                sensitive[k] = v
            else:
                safe[k] = v
        return safe, sensitive

# Module-level singleton for the current process
_credential_store = CredentialStore()

def get_credential_store() -> CredentialStore:
    return _credential_store
```

### Integration Points

1. **WorkflowGenerator**: Extract `api_key`/`base_url` from config, register with store, put `_credential_ref` in node_config instead.
2. **LLMAgentNode.process()**: Resolve `_credential_ref` from store, pass credentials to provider.
3. **Runtime**: Clear store after workflow execution completes.
4. **Distributed Runtime**: Credentials provided by worker environment or injected at dequeue time — never serialized in queue payload.

### Backward Compatibility

- `BaseAgentConfig(api_key=...)` API is unchanged.
- `WorkflowGenerator` handles the store registration internally.
- `LLMAgentNode` falls back to checking `self.config.get("api_key")` if no `_credential_ref` exists (backward compat with workflows built before this change).
- Serialized workflows with `"***REDACTED***"` or missing `api_key` require re-supplying credentials at runtime (intentional).

### Additional Safety Layers

Even with the credential store, add defense-in-depth:

1. `NodeInstance.model_dump()` redacts `_SENSITIVE_KEYS` as a safety net.
2. `NodeConfigurationError` messages strip config values.
3. Debug `print()` statements removed from production code.

## Consequences

### Positive

- Credentials architecturally separated from serializable state
- All 10 leak vectors eliminated at the source
- Scales to any credential type without maintaining key lists
- Thread-safe, request-scoped lifecycle
- Core SDK generic — any node type benefits

### Negative

- New abstraction (CredentialStore) to maintain
- Distributed runtime requires out-of-band credential transport
- Deserialized workflows need re-supplied credentials at runtime
- Slightly more complex flow in WorkflowGenerator

## Alternatives Considered

### Redaction at serialization boundary

Override `model_dump()` to strip sensitive keys. Simpler but fragile — any path that bypasses `model_dump()` (deepcopy, repr, direct access) still leaks. Rejected by stakeholder decision.

### Pydantic SecretStr

`NodeInstance.config` is `dict[str, Any]` — SecretStr cannot be enforced on untyped dict values. Rejected as architecturally incompatible.

### kwargs-only (no config storage)

Breaking change requiring users to know internal node IDs. Rejected for poor UX.
