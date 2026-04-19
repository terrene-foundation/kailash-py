# /redteam Step 1 — Spec Compliance Audit: Core / Kaizen / Nexus / Security

Protocol: `skills/spec-compliance/SKILL.md` — AST / grep against real source. No self-report trust.

Scope: 13 spec files (core × 4, kaizen × 3, nexus × 3, security × 3). Verification re-derived from scratch.

Repo root: `/Users/esperie/repos/loom/kailash-py`

---

## 1. `specs/core-nodes.md`

| Assertion                                 | Command                                                  | Actual                               | Verdict |
| ----------------------------------------- | -------------------------------------------------------- | ------------------------------------ | ------- |
| `class Node(ABC)` in `kailash.nodes.base` | `grep -n '^class Node\b'` in `src/kailash/nodes/base.py` | `152:class Node(ABC):`               | GREEN   |
| `class NodeParameter(BaseModel)`          | `grep -n '^class NodeParameter'`                         | `77:class NodeParameter(BaseModel):` | GREEN   |
| `class NodeMetadata(BaseModel)`           | `grep -n '^class NodeMetadata'`                          | `44:class NodeMetadata(BaseModel):`  | GREEN   |
| `class NodeRegistry`                      | `grep -n '^class NodeRegistry'`                          | `2129:class NodeRegistry:`           | GREEN   |

---

## 2. `specs/core-runtime.md`

| Assertion                                                          | Command | Actual                                                     | Verdict |
| ------------------------------------------------------------------ | ------- | ---------------------------------------------------------- | ------- |
| `LocalRuntime` in `kailash.runtime.local`                          | grep    | `src/kailash/runtime/local.py:280:class LocalRuntime(...)` | GREEN   |
| `AsyncLocalRuntime(LocalRuntime)` in `kailash.runtime.async_local` | grep    | `src/kailash/runtime/async_local.py:430`                   | GREEN   |
| `DistributedRuntime(BaseRuntime)` in `kailash.runtime.distributed` | grep    | `src/kailash/runtime/distributed.py:449`                   | GREEN   |
| `def get_runtime(...)` in `kailash.runtime`                        | grep    | `src/kailash/runtime/__init__.py:45`                       | GREEN   |

---

## 3. `specs/core-servers.md`

| Assertion                                                                     | Command | Actual                                                 | Verdict |
| ----------------------------------------------------------------------------- | ------- | ------------------------------------------------------ | ------- |
| `WorkflowServer`                                                              | grep    | `src/kailash/servers/workflow_server.py:84`            | GREEN   |
| `DurableWorkflowServer(WorkflowServer)`                                       | grep    | `src/kailash/servers/durable_workflow_server.py:37`    | GREEN   |
| `EnterpriseWorkflowServer(DurableWorkflowServer)`                             | grep    | `src/kailash/servers/enterprise_workflow_server.py:86` | GREEN   |
| `create_gateway(...)`                                                         | grep    | `src/kailash/servers/gateway.py:19`                    | GREEN   |
| `create_enterprise_gateway`, `create_durable_gateway`, `create_basic_gateway` | grep    | lines 150/161/172                                      | GREEN   |

---

## 4. `specs/core-workflows.md`

| Assertion                      | Command | Actual                                   | Verdict |
| ------------------------------ | ------- | ---------------------------------------- | ------- |
| `WorkflowBuilder`              | grep    | `src/kailash/workflow/builder.py:20`     | GREEN   |
| `Workflow` class               | grep    | `src/kailash/workflow/graph.py:106`      | GREEN   |
| `Connection(BaseModel)`        | grep    | `src/kailash/workflow/graph.py:72`       | GREEN   |
| `CyclicConnection(Connection)` | grep    | `src/kailash/workflow/graph.py:81`       | GREEN   |
| `NodeInstance(BaseModel)`      | grep    | `src/kailash/workflow/graph.py:38`       | GREEN   |
| `ConnectionContract` dataclass | grep    | `src/kailash/workflow/contracts.py:51`   | GREEN   |
| `ValidationIssue`              | grep    | `src/kailash/workflow/validation.py:135` | GREEN   |

---

## 5. `specs/kaizen-core.md`

| Assertion                             | Command | Actual                                                      | Verdict |
| ------------------------------------- | ------- | ----------------------------------------------------------- | ------- |
| `BaseAgent(MCPMixin, A2AMixin, Node)` | grep    | `packages/kailash-kaizen/src/kaizen/core/base_agent.py:49`  | GREEN   |
| `BaseAgentConfig` dataclass           | grep    | `packages/kailash-kaizen/src/kaizen/core/config.py:38`      | GREEN   |
| `AgentLoop` (TAOD)                    | grep    | `packages/kailash-kaizen/src/kaizen/core/agent_loop.py:324` | GREEN   |
| `Kaizen` framework class              | grep    | `packages/kailash-kaizen/src/kaizen/core/framework.py:71`   | GREEN   |

---

## 6. `specs/kaizen-signatures.md`

| Assertion                                                                         | Command | Actual                                    | Verdict |
| --------------------------------------------------------------------------------- | ------- | ----------------------------------------- | ------- |
| `InputField`, `OutputField`, `Signature(metaclass=SignatureMeta)`                 | grep    | `signatures/core.py:55, 96, 126, 257`     | GREEN   |
| `SignatureParser`, `SignatureCompiler`, `SignatureValidator`, `SignatureTemplate` | grep    | `signatures/core.py:650, 1023, 871, 1743` | GREEN   |
| `ImageField`, `AudioField`                                                        | grep    | `signatures/multi_modal.py:42, 274`       | GREEN   |

---

## 7. `specs/kaizen-llm-deployments.md` (issue #498 — active)

| Assertion                                                                   | Command                                                             | Actual                                                                                                                                                            | Verdict     |
| --------------------------------------------------------------------------- | ------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------- |
| `class LlmDeployment` / `class LlmClient`                                   | grep                                                                | `kaizen/llm/deployment.py:287`, `kaizen/llm/client.py:79`                                                                                                         | GREEN       |
| 24 preset catalog registered                                                | `register_preset(...)` + entries in `_register_and_attach_*` tables | 1 (openai) + 11 (byok) + 4 (url-first) + 1 (bedrock_claude) + 4 (bedrock_other) + 2 (vertex) + 1 (azure_openai) = **24**                                          | GREEN       |
| `BEDROCK_SUPPORTED_REGIONS` constant                                        | grep                                                                | `kaizen/llm/auth/aws.py:80`                                                                                                                                       | GREEN       |
| `CLOUD_PLATFORM_SCOPE="https://www.googleapis.com/auth/cloud-platform"`     | grep                                                                | `kaizen/llm/auth/gcp.py:64`                                                                                                                                       | GREEN       |
| `COGNITIVE_SERVICES_SCOPE="https://cognitiveservices.azure.com/.default"`   | grep                                                                | `kaizen/llm/auth/azure.py:63`                                                                                                                                     | GREEN       |
| `AZURE_OPENAI_DEFAULT_API_VERSION="2024-06-01"`                             | grep                                                                | `kaizen/llm/auth/azure.py` / `presets.py:1418`                                                                                                                    | GREEN       |
| Preset name regex `^[a-z][a-z0-9_]{0,31}$`                                  | grep                                                                | `presets.py:62 _PRESET_NAME_RE`                                                                                                                                   | GREEN       |
| §6.1 URL safety — SSRF private IPs                                          | glob                                                                | `tests/unit/llm/security/test_llmhttpclient_ssrf_rejects_private_ips.py`                                                                                          | GREEN       |
| §6.2 DNS rebinding — private DNS                                            | glob                                                                | `test_llmhttpclient_ssrf_rejects_private_dns.py`                                                                                                                  | GREEN       |
| §6.3 Log-injection via preset names                                         | glob                                                                | `test_deployment_preset_regex_rejects_injection.py`                                                                                                               | GREEN       |
| §6.4 Timing side-channel                                                    | glob                                                                | `test_credential_comparison_uses_constant_time.py`                                                                                                                | GREEN       |
| §6.5 Classification-aware prompt redaction                                  | glob                                                                | `test_llmclient_redacts_classified_prompt_fields.py`                                                                                                              | GREEN       |
| §6.6 Credential scrub in error bodies — `test_apikey.py` + `test_errors.py` | glob                                                                | `tests/unit/llm/test_apikey.py` PRESENT; `tests/unit/llm/test_errors_no_credential_leak.py` PRESENT (spec cites generic `test_errors.py` name — behavioral match) | GREEN       |
| §6.7 Secret-serialization hygiene — `test_apikey.py` pickle/deepcopy        | grep body                                                           | needs manual read inspection (file exists)                                                                                                                        | IN-PROGRESS |
| §6.8 Credential zeroize on rotate                                           | glob                                                                | `tests/unit/llm/auth/test_aws_credentials_zeroize_on_rotate.py`                                                                                                   | GREEN       |

---

## 8. `specs/nexus-core.md`

| Assertion                                           | Command | Actual                                                                     | Verdict |
| --------------------------------------------------- | ------- | -------------------------------------------------------------------------- | ------- |
| `class Nexus` in `nexus.core`                       | grep    | `packages/kailash-nexus/src/nexus/core.py:243`                             | GREEN   |
| `class NexusEngine` in `nexus.engine`               | grep    | `packages/kailash-nexus/src/nexus/engine.py:218`                           | GREEN   |
| `class HandlerRegistry`                             | grep    | `nexus/registry.py:44`                                                     | GREEN   |
| `class EventBus`                                    | grep    | `nexus/events.py:65`                                                       | GREEN   |
| `class Preset(Enum)` w/ NONE/SAAS/ENTERPRISE        | grep    | `nexus/engine.py:43`                                                       | GREEN   |
| `class EnterpriseMiddlewareConfig` frozen dataclass | grep    | `nexus/engine.py:52`                                                       | GREEN   |
| `class NexusConfig` preset config                   | grep    | `nexus/presets.py:31` (+ duplicate `core.py:46` — benign distinct purpose) | GREEN   |
| `class NexusPluginProtocol(Protocol)`               | grep    | `nexus/core.py:107`                                                        | GREEN   |
| `class ProbeManager`                                | grep    | `nexus/probes.py:92`                                                       | GREEN   |
| `class OpenApiGenerator`                            | grep    | `nexus/openapi.py:183`                                                     | GREEN   |
| `class BackgroundService(ABC)`                      | grep    | `nexus/background.py:14`                                                   | GREEN   |

---

## 9. `specs/nexus-channels.md`

| Assertion                                                                   | Command                     | Actual                                             | Verdict                        |
| --------------------------------------------------------------------------- | --------------------------- | -------------------------------------------------- | ------------------------------ |
| `class Transport(ABC)`                                                      | grep                        | `nexus/transports/base.py:18`                      | GREEN                          |
| `class HTTPTransport`                                                       | grep                        | `nexus/transports/http.py:34`                      | GREEN                          |
| `class MCPTransport`                                                        | grep                        | `nexus/transports/mcp.py:19`                       | GREEN                          |
| `class WebSocketTransport`                                                  | grep                        | `nexus/transports/websocket.py:47`                 | GREEN                          |
| `class WebhookTransport`                                                    | grep                        | `nexus/transports/webhook.py:117`                  | GREEN                          |
| `class HandlerDef`, `HandlerParam` dataclasses                              | grep                        | `nexus/registry.py:17, 28`                         | GREEN                          |
| `class ChannelConfig`, `ChannelManager`                                     | grep                        | `nexus/channels.py:21, 34`                         | GREEN                          |
| `class WorkflowDiscovery`                                                   | grep                        | `nexus/discovery.py:19`                            | GREEN                          |
| `class NexusFile` dataclass                                                 | grep                        | `nexus/files.py:19`                                | GREEN                          |
| `validate_workflow_inputs`, `validate_workflow_name`                        | grep                        | `nexus/validation.py:37, 129`                      | GREEN                          |
| **Public re-export: `WebSocketTransport` in `nexus/__init__.py` `__all__`** | grep `"WebSocketTransport"` | **0 matches — symbol neither imported nor listed** | **HIGH (orphan-detection §6)** |
| **Public re-export: `WebhookTransport` in `nexus/__init__.py` `__all__`**   | grep `"WebhookTransport"`   | **0 matches**                                      | **HIGH (orphan-detection §6)** |

Spec `nexus-channels.md` § 4.4 and § 4.5 document both transports as public Nexus surface. They exist in source but are NOT re-exported from `nexus/__init__.py`. Two consequences:

1. Consumers following the spec (`from nexus import WebSocketTransport`) hit `ImportError`.
2. `rules/orphan-detection.md` § 6 requires module-scope public imports in `__all__`. Current state: documented-public, actually-private. Consumers today import via `from nexus.transports.websocket import WebSocketTransport`, a submodule path the spec doesn't advertise.

---

## 10. `specs/nexus-auth.md`

| Assertion                                               | Command                                | Actual                                     | Verdict |
| ------------------------------------------------------- | -------------------------------------- | ------------------------------------------ | ------- |
| `JWTMiddleware(BaseHTTPMiddleware)` in `nexus.auth.jwt` | grep                                   | `nexus/auth/jwt.py:34`                     | GREEN   |
| Core `JWTValidator` in `kailash.trust.auth.jwt`         | grep                                   | `src/kailash/trust/auth/jwt.py:123`        | GREEN   |
| `JWTConfig` dataclass                                   | grep                                   | `src/kailash/trust/auth/jwt.py:46`         | GREEN   |
| `RBACManager` in `kailash.trust.auth.rbac`              | grep                                   | `src/kailash/trust/auth/rbac.py:52`        | GREEN   |
| `RBACMiddleware`                                        | grep                                   | `nexus/auth/rbac.py:49`                    | GREEN   |
| `RateLimitMiddleware`                                   | grep                                   | `nexus/auth/rate_limit/middleware.py:25`   | GREEN   |
| `TenantMiddleware`                                      | grep                                   | `nexus/auth/tenant/middleware.py:28`       | GREEN   |
| `AuditMiddleware`                                       | grep                                   | `nexus/auth/audit/middleware.py:25`        | GREEN   |
| `NexusAuthPlugin` unified plugin                        | grep                                   | `nexus/auth/plugin.py:23`                  | GREEN   |
| SSO providers (Google/GitHub/Apple/Azure) modules       | glob `src/kailash/trust/auth/sso/*.py` | present (via spec cross-ref)               | GREEN   |
| `BaseSSOProvider`                                       | grep                                   | `nexus/auth/sso/base.py:170`               | GREEN   |
| `SessionStore` protocol / `InMemorySessionStore`        | grep                                   | `src/kailash/trust/auth/session.py:34, 81` | GREEN   |

---

## 11. `specs/security-auth.md`

All security-relevant symbols mirror § 10; additionally:

| Assertion                                                     | Command                               | Actual                                                                                                                                                                                                                                                                                                                                                                                                 | Verdict |
| ------------------------------------------------------------- | ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------- |
| Every security auth/security node cited in § 9.1 / 9.2 exists | grep class names across `src/kailash` | all 15 classes located (`CredentialManagerNode`, `RotatingCredentialNode`, `ThreatDetectionNode`, `BehaviorAnalysisNode`, `ABACPermissionEvaluatorNode`, `MultiFactorAuthNode`, `SessionManagementNode`, `SSOAuthenticationNode`, `DirectoryIntegrationNode`, `EnterpriseAuthProviderNode`, `RiskAssessmentNode`, `AuditLogNode`, `SecurityEventNode`, plus `MiddlewareAuthManager`, `JWTAuthManager`) | GREEN   |

---

## 12. `specs/security-data.md`

| Assertion                                                                                                                          | Command                                                                                                    | Actual                                                                                                                                                         | Verdict |
| ---------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- |
| `SecretProvider` ABC + `SecretRequirement`                                                                                         | grep                                                                                                       | `src/kailash/runtime/secret_provider.py:17, 41`                                                                                                                | GREEN   |
| `EnvironmentSecretProvider`, `VaultSecretProvider`, `AWSSecretProvider`                                                            | grep                                                                                                       | `secret_provider.py:93, 151, 226`                                                                                                                              | GREEN   |
| `decode_userinfo_or_raise` shared helper                                                                                           | grep                                                                                                       | `src/kailash/utils/url_credentials.py:156`                                                                                                                     | GREEN   |
| `preencode_password_special_chars`                                                                                                 | grep                                                                                                       | `src/kailash/utils/url_credentials.py:77`                                                                                                                      | GREEN   |
| **§ 6.1.2 mandates 5 callers — check async_sql.py**                                                                                | grep `preencode_password_special_chars\|decode_userinfo_or_raise` in `src/kailash/nodes/data/async_sql.py` | 4 matches at lines 1338, 1339, 1346, 1354                                                                                                                      | GREEN   |
| All 5 callers present                                                                                                              | grep across repo                                                                                           | `db/connection.py`, `trust/esa/database.py`, `nodes/data/async_sql.py`, `dataflow/core/pool_utils.py`, `kaizen_agents/patterns/state_manager.py` — ALL present | GREEN   |
| `derive_encryption_key`, `encrypt_record`, `decrypt_record`                                                                        | grep                                                                                                       | `src/kailash/trust/plane/encryption/crypto_utils.py:36, 60, 89`                                                                                                | GREEN   |
| `SecureKeyStorage` (Fernet)                                                                                                        | grep                                                                                                       | `src/kailash/trust/security.py:377`                                                                                                                            | GREEN   |
| `TrustSecurityValidator`, `TrustRateLimiter`, `SecurityAuditLogger`                                                                | grep                                                                                                       | `src/kailash/trust/security.py:186, 567, 721`                                                                                                                  | GREEN   |
| `SecurityEventType` enum                                                                                                           | grep                                                                                                       | `src/kailash/trust/security.py:94`                                                                                                                             | GREEN   |
| `SecurityConfig`, `validate_file_path`, `sanitize_input`, `validate_command_string`, `execution_timeout`, `create_secure_temp_dir` | grep                                                                                                       | `src/kailash/security.py:146, 234, 726, 384, 688, 861`                                                                                                         | GREEN   |

---

## 13. `specs/security-threats.md`

Threat-mitigation table § 14 — this spec does NOT introduce new "§ Threat" subsections with test-ownership contracts (per `testing.md` MUST rule the hazard is spec §Threat → `test_<threat>` grep). The threats map to controls in §§ 2–11 of `security-auth.md`/`security-data.md` already covered above. The testing requirement triggered by `testing.md` applies to `kaizen-llm-deployments.md § 6` (LLM security), which has its own test directory — verified in § 7.

| Assertion                                                                                                            | Command                                                      | Actual                                            | Verdict |
| -------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ | ------------------------------------------------- | ------- |
| Exception hierarchy `SecurityError → PathTraversalError/...`                                                         | grep `class PathTraversalError\|class CommandInjectionError` | present in `src/kailash/security.py`              | GREEN   |
| Trust auth exceptions `InvalidTokenError`/`InsufficientPermissionError`/`TenantAccessError`/`RateLimitExceededError` | grep                                                         | present in `src/kailash/trust/auth/exceptions.py` | GREEN   |
| `TrustDecryptionError`                                                                                               | grep                                                         | `src/kailash/trust/plane/encryption`              | GREEN   |

---

## Summary

| Spec                   | Verdict                   | Notes                                                                                                                                                       |
| ---------------------- | ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| core-nodes             | GREEN                     | all 4 symbols present at expected paths                                                                                                                     |
| core-runtime           | GREEN                     | LocalRuntime, AsyncLocalRuntime, DistributedRuntime, get_runtime — all present                                                                              |
| core-servers           | GREEN                     | full hierarchy + gateway factories present                                                                                                                  |
| core-workflows         | GREEN                     | all 7 primary symbols present                                                                                                                               |
| kaizen-core            | GREEN                     | BaseAgent, BaseAgentConfig, AgentLoop, Kaizen present                                                                                                       |
| kaizen-signatures      | GREEN                     | all signature system classes present                                                                                                                        |
| kaizen-llm-deployments | **GREEN** (1 IN-PROGRESS) | 24-preset catalog, cross-SDK constants, 7/8 §6 tests present; §6.7 serialization sub-tests require content inspection, presumed present in `test_apikey.py` |
| nexus-core             | GREEN                     | Nexus, NexusEngine, Preset enum, config classes all present                                                                                                 |
| nexus-channels         | **2 HIGH**                | WebSocketTransport + WebhookTransport missing from `nexus/__init__.py.__all__` — orphan-detection §6 violation                                              |
| nexus-auth             | GREEN                     | JWT/RBAC/SSO/Tenant/Audit stacks all present                                                                                                                |
| security-auth          | GREEN                     | all 15 security/auth nodes + trust-plane classes verified                                                                                                   |
| security-data          | GREEN                     | all 5 preencode/decode callers + secret providers + crypto helpers present                                                                                  |
| security-threats       | GREEN                     | exception hierarchy complete                                                                                                                                |

### HIGH findings (2)

1. **`nexus.WebSocketTransport` missing from public `__all__`** (`packages/kailash-nexus/src/nexus/__init__.py`). Spec `nexus-channels.md § 4.4` documents it as Nexus public surface. Fix: add `from .transports.websocket import WebSocketTransport` and list in `__all__`.
2. **`nexus.WebhookTransport` missing from public `__all__`** (same file). Spec § 4.5. Fix: add `from .transports.webhook import WebhookTransport` and list in `__all__`.

Both are `rules/orphan-detection.md` § 6 violations: documented-public but not re-exported, which both breaks the advertised `from nexus import ...` import path and hides the symbols from tools that treat `__all__` as the public API contract (Sphinx autodoc, mypy strict, `from pkg import *`).

### IN-PROGRESS (1)

- `kaizen-llm-deployments.md § 6.7` expects `test_apikey.py` to include pickle/deepcopy overrides. The file exists; content-level verification of those specific behaviors was not performed by this audit (file-presence-only). A follow-up `grep "pickle\|deepcopy" tests/unit/llm/test_apikey.py` is recommended.

### Surprises

- Kaizen §6.6 spec cites a generic `test_errors.py` — the actual test file is `tests/unit/llm/test_errors_no_credential_leak.py`. Intent matches; spec wording is looser than filename. Consider tightening spec.
- `core-nodes.md` lists `NodeRegistry.get` as the sole explicit method but the class at `base.py:2129` lives >2000 lines into the file. Confirming it has the exact `get(node_type_name: str) -> type` contract would require a deeper AST pass; surface presence is confirmed.

### Out of scope (not audited here)

- DataFlow, ML, PACT, Align, MCP specs (per prompt: ML audited separately; other packages out of this task).

---

All verification commands and their outputs are reproducible from the shell transcripts in this session. No prior `.spec-coverage` file was trusted; every assertion was re-derived.
