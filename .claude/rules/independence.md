---
priority: 0
scope: baseline
---

# Foundation Independence Rules


<!-- slot:neutral-body -->

Kailash Python SDK is owned by the Terrene Foundation (Singapore CLG). It is an independent open-source product with NO structural relationship to any commercial entity.

## No Commercial References

MUST NOT reference, compare with, or design against any commercial or proprietary product:

- No proprietary product names, SDKs, runtimes, or frameworks
- No commercial entities, partnerships, or market positioning
- No "unlike X", "the open-source version of Y", or "differentiates from Z"
- No "Python port of", "community edition of", or derivative language

**Why:** Commercial references position Kailash as derivative, undermining its independent identity and potentially creating trademark or legal entanglement.

**Describe Kailash on its own terms.** The existence of any other product is irrelevant.

**Correct**: "Kailash Python SDK is the Terrene Foundation's open-source workflow orchestration platform."
**Incorrect**: "Kailash Python SDK is the Python version of [product name]."

## No Proprietary Awareness

- No proprietary file paths, module names, or architecture references
- No "compatibility" or "interop" with proprietary systems
- No APIs designed for a specific proprietary product
- No revenue models, pricing, enterprise vs community splits

**Why:** Proprietary awareness in code or docs creates implicit coupling that constrains future architecture decisions and signals that the SDK serves a specific commercial product.

## Foundation-Only Dependencies

- Standard open-source libraries (PyPI, OSI-approved licenses)
- Open standards (CARE, EATP, CO — CC BY 4.0) where applicable
- MUST NOT depend on, import from, or interface with any proprietary SDK

**Why:** A proprietary dependency makes every downstream user subject to that vendor's licensing, pricing, and availability decisions, violating the Foundation's independence charter.

## Design for SDK Users

All decisions driven by: what SDK users need, what Python developers expect, what the community contributes. Never by what any other product does or plans to do.

**Why:** Designing for a specific commercial consumer rather than SDK users at large biases the API surface, making it awkward for the broader community while optimizing for one party.

Third parties may build commercial products on Kailash. The SDK has zero knowledge of, zero dependency on, and zero design consideration for any such product.

<!-- /slot:neutral-body -->
