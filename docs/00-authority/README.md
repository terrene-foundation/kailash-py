# Authority Documents

Authoritative references for the trust-plane package. Developers and codegen agents read these first for full situational awareness.

## Index

| Document | Purpose |
|----------|---------|
| [CLAUDE.md](./CLAUDE.md) | Preloaded instructions for Claude Code sessions touching trust-plane |
| [00-architecture.md](./00-architecture.md) | System architecture, module map, and data flow |
| [01-api-reference.md](./01-api-reference.md) | Public API surface with usage examples |
| [02-store-backends.md](./02-store-backends.md) | Store protocol, backend implementations, security contract |
| [03-security-model.md](./03-security-model.md) | Threat model, hardened patterns, encryption, RBAC, key management |
| [04-enterprise-features.md](./04-enterprise-features.md) | SIEM, compliance, dashboard, shadow mode, multi-tenancy |
| [05-cli-reference.md](./05-cli-reference.md) | CLI commands and configuration |

## Cross-References

- Package-level CLAUDE.md: `src/kailash/trust/plane/CLAUDE.md` (security patterns, store contract, red team convergence)
- EATP SDK rules: `.claude/rules/eatp.md`
- Trust integration guides: `docs/trust/`
