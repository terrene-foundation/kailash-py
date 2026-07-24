# CHANGELOG draft for kaizen 2.43.0 (paste at /release, verify version/symbols first)

Version anchors to bump 2.42.0 → 2.43.0 (MINOR — behavior change, per redteam):

- packages/kailash-kaizen/pyproject.toml:7
- packages/kailash-kaizen/src/kaizen/**init**.py:9

Release tag: `kaizen-v2.43.0` → OIDC publish-pypi.yml.

---

## [2.43.0] — <DATE> — LLMAgentNode fails loud on an unresolved provider (silent-mock class closed at the node)

### Changed (behavior — potentially breaking)

- **`LLMAgentNode` / `IterativeLLMAgentNode` now RAISE `ConfigurationError` when
  `provider` is unresolved (`None`) instead of silently dispatching the mock
  provider.** The `LLMAgentNode` `provider` NodeParameter default changed from
  `"mock"` to `None`; `run()` raises a typed `kaizen.config.providers.ConfigurationError`
  when the provider is unresolved. This structurally closes the silent-mock class
  that #1943 (2.41.0) and #1946 (2.42.0) patched site-by-site: a forgotten/new
  construction site now fails LOUD instead of returning fabricated content as a
  real model answer. `IterativeLLMAgentNode` (a public subclass) previously
  swallowed the inherited guard in its 6-phase loop and returned `success=True`
  with a hand-built template answer — it is now guarded at the top of `run()`.

  **Migration:** pass `provider="mock"` EXPLICITLY where you previously relied on
  the mock default (e.g. tests/dev harnesses); the mock provider remains reachable
  when requested explicitly. Production sites that resolve a provider from the
  environment (the `Agent` deployment surface, the RAG nodes) are unaffected.
  Under `node.execute()` / runtime dispatch the `ConfigurationError` surfaces
  wrapped in `NodeExecutionError` (as `__cause__`); direct `node.run()` raises it
  cleanly. Closes #1947.

### Notes

- Two same-class residuals on OTHER surfaces are tracked separately: the keyless
  `detect_provider_from_env()` → `"mock"` env fallback (Agent/RAG) and
  `EmbeddingGeneratorNode` (#1952); and a distinct runtime-error-masking pattern
  in `IterativeLLMAgentNode` synthesis (#1953).
