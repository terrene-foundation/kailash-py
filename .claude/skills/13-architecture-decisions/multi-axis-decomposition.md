---
name: multi-axis-decomposition
description: "Architectural pattern for complex integrations. Use when designing a new SDK abstraction for multi-variant external systems (LLM providers, auth strategies, storage backends, API gateways)."
---

# Multi-Axis Decomposition — When the Shape Is Wrong, Fix the Shape

When an SDK abstraction lumps multiple independent concerns into one identifier (a monolithic enum, a provider name, a "backend type"), adding the 11th variant is exponentially harder than adding the 10th. The fix is to decompose the identifier along its real axes and ship trait-/protocol-based extensibility — NOT to keep adding enum variants.

This skill captures the generalizable pattern distilled from two architecture decisions that share the same rationale:

- **LLM deployment-target abstraction.** Old: `LlmProvider` enum (OpenAi, Anthropic, Google, …). New: `LlmDeployment { wire × auth × endpoint × grammar }`.
- **Nexus handler extractor pattern.** Old: magic-named `raw_body` params. New: a `FromRequest` extractor protocol with composable extractors.

## The Rejection Rationale (Three Reasons)

Both decisions rejected the narrow-fix design for the same three reasons. Any new abstraction that looks like a closed set of identifiers MUST pass all three, or it is the wrong shape.

### 1. Closed Set

A named-variant enum (or magic-name-matched param list) requires a code change for every new real-world variant. LLM providers ship monthly; handler extraction dimensions accrue per middleware; storage backends proliferate. The closed set loses.

```python
# DO NOT — closed set, every Bedrock model requires a new variant
class LlmProvider(Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    BEDROCK_CLAUDE = "bedrock_claude"   # new
    BEDROCK_LLAMA = "bedrock_llama"     # new
    BEDROCK_MISTRAL = "bedrock_mistral" # new
    # ... 15 more as AWS ships

# DO — protocol/trait-based composition, 3-line preset per new target
class LlmDeployment:
    @classmethod
    def bedrock_claude(cls, region: str, auth: AuthStrategy) -> "LlmDeployment":
        return cls.from_parts(
            wire=AnthropicMessages(),
            auth=auth,
            endpoint=Endpoint(bedrock_host(region)),
            grammar=BedrockClaudeGrammar(),
        )
```

```rust
// Rust equivalent — same shape, native trait dispatch
impl LlmDeployment {
    pub fn bedrock_claude(region: &str, auth: impl AuthStrategy) -> Self {
        Self::from_parts(WireProtocol::AnthropicMessages, auth, /* endpoint */, /* grammar */)
    }
}
```

**Why:** The closed set's maintenance cost scales linearly with real-world variance; the trait/protocol-based shape scales with the number of distinct axes (usually 3–5, constant). Evidence: third-party multi-provider shims exist precisely because provider-centric enums fail.

### 2. No Type Safety

A name/string/enum that conflates independent axes loses type-level guarantees. The compiler/checker can't reject "Bedrock with OpenAI wire" because `Provider.BEDROCK` is just an opaque tag.

```python
# DO NOT — type conflates wire with auth with endpoint
provider = LlmProvider.BEDROCK  # what wire? what auth? what region?

# DO — each axis has its own type; static analysis enforces consistency
deployment = LlmDeployment.from_parts(
    wire=AnthropicMessages(),                      # wire axis
    auth=AwsBearerToken.from_env(),                # auth axis
    endpoint=Endpoint(bedrock_host(region)),       # endpoint axis (SSRF-gated)
    grammar=BedrockClaudeGrammar(),                # grammar axis
)
```

**Why:** Type-safe decomposition moves the "is this combination valid" check from runtime (a crash or wrong-URL error) to compile/check time. Same reason `Endpoint` keeps its host private — the SSRF gate lives in the constructor, not on the struct.

### 3. No Composition

The closed-set shape doesn't layer. You can't say "take this wire protocol, add that auth, swap the endpoint for a caching proxy" because the variant identity fuses those dimensions. Trait/protocol-based shapes compose — `AuthStrategy` can be wrapped by `CachedAuth`; `Endpoint` can be wrapped by `LoadBalancedEndpoint`; grammars stack.

```python
# DO — composed auth: outer retry wraps inner bearer
base = AwsBearerToken.from_env()
auth = RetryingAuth(inner=base, retry_policy=...)
deployment = LlmDeployment.bedrock_claude(region, auth)

# DO NOT — enum dispatch blocks the retry wrapper
if provider == LlmProvider.BEDROCK:
    apply_bearer_and_maybe_retry_no_way_to_layer()
```

**Why:** Composition is the emergent property that makes a trait/protocol-based design generative. Once the axes are separated, new real-world combinations are 3-line presets, not 300-line adapters.

## Applying The Pattern

When you encounter an abstraction that "just needs one more variant":

1. **Enumerate the real-world variants** the abstraction is meant to cover. Include the next 12–24 months of roadmap, not just the current set.
2. **Factor by shared axes.** If every variant is `(wire, auth, endpoint, grammar)` with each axis having 2–5 choices, the monolithic enum is O(N⁴). The four traits are O(4).
3. **Each axis becomes a trait/protocol.** The trait is narrow — one method, one contract. `WireProtocol` has `format_request` + `parse_response`; `AuthStrategy` has `apply(request)`; `Endpoint` has `url()` + private fields for SSRF-gating.
4. **Presets compose the axes.** A "preset" is a 3-line builder that picks one impl per axis and names it. Bedrock-Claude, Vertex-Gemini, Azure-OpenAI are presets; each is 3 lines.
5. **Ship the trait/protocol-based core + 5–10 presets in one release.** Don't ship the trait without presets (nobody adopts); don't ship the presets without the trait (the same closed-set problem returns).

## Related Decisions

- **PACT envelope decomposition** — envelope = `(clearance × operating_posture × scope × delegation)`. Same four-axis pattern applied to authorization. PACT avoids the "role-based" closed-set trap by factoring access on trait axes.
- **DataFlow dialect factoring** — dialect = `(identifier_quoting × type_mapping × placeholder_style × feature_support)`. The dialect abstraction is the same pattern at the SQL layer. Adding a new database is a 4-method trait/class impl, not a 300-LOC adapter.
- **Kaizen signature decomposition** — signature = `(inputs × reasoning × outputs × tool_bindings)`. Agent design uses four-axis decomposition at the LLM-reasoning layer.

## When The Pattern Does NOT Apply

Not every abstraction needs multi-axis decomposition. The trigger is real-world variance along ≥2 independent axes. If the variance is along ONE axis, an enum is fine.

- `LogLevel` — one axis (severity). Enum is correct.
- `HttpMethod` — one axis (GET/POST/…). Enum is correct.
- `DatabaseType` (postgresql/mysql/sqlite without factoring further) — questionable. Kailash chose to factor further into dialect because dialect is where real-world variance lives.

## Anti-Pattern: Just Add Another Variant

The recurring bug that this skill is meant to prevent. Manifests as:

- "We just need to add a `Bedrock` variant to `LlmProvider`" — misses that Bedrock = Anthropic wire + AWS auth + Bedrock endpoint + Bedrock grammar, each with variance.
- "We just need a `header_signature` param on the handler" — misses that HMAC signatures are one of N composable request-authentication patterns.
- "We just need a `redis_cluster: bool` flag" — misses that Redis variance is `(deployment-topology × ACL × persistence-config)`.

Each "just add one more" arrives with 3 reasons it's the right fix. The three reasons above (closed set, no type safety, no composition) are the institutional response.

## Rule References

- `rules/framework-first.md` — default to Engines (composed primitives) over Raw (closed-set implementations). Multi-axis decomposition is how you build an Engine.
- `rules/orphan-detection.md` — the reverse failure: a trait/protocol without a production call site is also wrong. Ship trait + presets + wiring in one release.

Origin: Generalized from two concurrent SDK design decisions that rejected narrow-fix designs with identical rationale (LLM deployment 4-axis decomposition + Nexus extractor protocol). Codified as an architecture skill 2026-04-19.
