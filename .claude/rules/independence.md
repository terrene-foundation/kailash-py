# Foundation Independence Rules

## Scope

These rules apply to ALL files in this repository — code, documentation, configuration, comments, commit messages, and agent conversations.

## MUST Rules

### 1. Kailash Python SDK Is a Standalone Foundation Product

Kailash Python SDK is owned by the Terrene Foundation (Singapore CLG). It is an independent open-source product. All design decisions must be made on the SDK's own merits — what is best for its users and the open-source community.

### 2. No Commercial References

MUST NOT reference, discuss, compare with, or design against any commercial or proprietary product in any file in this repository. This includes:

- Proprietary product names (do not name them, do not compare against them)
- Proprietary SDKs or runtimes (do not reference Rust SDKs or proprietary frameworks)
- Commercial entities (no company names, no commercial partnerships)
- Market positioning or competitive differentiation (not a concern of this project)
- Commercial deployment models (managed hosting, enterprise pricing, SaaS)

**Why**: Kailash Python SDK is Foundation-owned and irrevocably open. It has no structural relationship with any commercial entity. Introducing commercial references — even for comparison — creates implicit coupling and suggests a relationship that does not exist.

**How to apply**: If you find yourself writing "unlike X" or "the open-source version of Y" or "differentiates from Z" — stop. Describe what the Kailash Python SDK does on its own terms. If a feature is good for SDK users, build it. If it isn't, don't. The existence or non-existence of any other product is irrelevant.

### 3. Foundation-Only Dependencies

Kailash Python SDK MUST depend only on:

- **Standard open-source libraries**: From PyPI, with OSI-approved licenses
- **Open standards**: CARE, EATP, CO (CC BY 4.0) where applicable

MUST NOT depend on, import from, or interface with any proprietary SDK, runtime, or API.

### 4. No "Open-Source Version Of" Language

MUST NOT describe Kailash Python SDK as:

- "The open-source version of [anything]"
- "The Python port of [anything]"
- "The community edition of [anything]"

Kailash Python SDK IS the product. It is not a derivative, port, counterpart, or edition of something else.

**Correct**: "Kailash Python SDK is the Terrene Foundation's open-source workflow orchestration platform."
**Incorrect**: "Kailash Python SDK is the Python version of [product name]."

### 5. Design for SDK Users

All feature decisions, architectural choices, and roadmap priorities must be driven by:

- What SDK users need
- What Python developers expect from a workflow orchestration SDK
- What the open-source community contributes

Never by what any other product does, doesn't do, or plans to do.

## MUST NOT Rules

### 1. No Proprietary Codebase Awareness

Code, comments, and documentation MUST NOT demonstrate awareness of any proprietary codebase. Do not:

- Reference proprietary file paths, module names, or architecture patterns
- Suggest "compatibility" or "interop" with proprietary systems
- Design APIs "so that [proprietary product] can also use them"

### 2. No Commercial Strategy Discussion

MUST NOT discuss in any file:

- Revenue models, pricing, or monetization
- Enterprise vs community feature splits
- Commercial licensing considerations
- Market competition or positioning

### 3. No Cross-Codebase Coupling

MUST NOT:

- Share code, interfaces, or protocols designed for a specific proprietary product
- Create abstractions whose primary purpose is proprietary product compatibility
- Design extension points that assume a specific proprietary implementation

## Clarification

Third parties — anyone, anywhere — may build commercial products on top of the Kailash Python SDK and Foundation standards. That is the intended open-source model. But the SDK itself has zero knowledge of, zero dependency on, and zero design consideration for any such product. If someone builds on Kailash, they adapt to Kailash — not the other way around.
