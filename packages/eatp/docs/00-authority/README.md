# EATP Authority Documents

These documents provide full situational awareness for developers and codegen working with the EATP SDK.

## Documents

| File                               | Purpose                                |
| ---------------------------------- | -------------------------------------- |
| [CLAUDE.md](CLAUDE.md)             | Preloaded instructions for Claude Code |
| [architecture.md](architecture.md) | Core architecture and module map       |

## Quick Orientation

EATP (Enterprise Agent Trust Protocol) is a standalone SDK for cryptographic trust chains, delegation, and verification in AI agent systems.

- **Package**: `pip install eatp`
- **License**: Apache 2.0 (Terrene Foundation)
- **Source**: `packages/eatp/src/eatp/`
- **Tests**: `packages/eatp/tests/` (1557 tests)
- **Docs**: `packages/eatp/docs/` (mkdocs-material)

## Core Concepts

1. **Trust Chain**: Genesis → Capabilities → Delegations → Constraints → Audit
2. **4 Operations**: ESTABLISH, DELEGATE, VERIFY, AUDIT
3. **5 Postures**: Pseudo-Agent, Supervised, Shared Planning, Continuous Insight, Delegated (SDK enum: `TrustPosture.{DELEGATED, CONTINUOUS_INSIGHT, SHARED_PLANNING, SUPERVISED, PSEUDO_AGENT}`)
4. **6 Interop Formats**: JWT, W3C VC, DID, UCAN, SD-JWT, Biscuit
5. **3 Enforcement Modes**: StrictEnforcer, ShadowEnforcer, Decorators
6. **Reasoning Traces**: Optional structured reasoning (decision, rationale, confidentiality) on delegations and audit anchors with dual-binding crypto verification
