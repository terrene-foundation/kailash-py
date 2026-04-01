# kailash-align Authority Docs

Navigation guide for the authority documentation that agents and developers preload when working with `kailash-align`.

## Contents

| File                   | Purpose                                                                                                                                                                                                                                         |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [CLAUDE.md](CLAUDE.md) | Preloaded instructions for AI agents working with kailash-align. Covers package architecture, supported methods, key classes, config hierarchy, security constraints, and dependencies. Load this before any kailash-align development session. |

## When to Use

- **Starting a session**: Load `CLAUDE.md` to establish context about kailash-align's architecture, the 12 supported alignment methods, and the security-critical reward function registry.
- **Adding a new method**: `CLAUDE.md` describes the MethodRegistry pattern and the four method categories. Follow this pattern for any new trainer integration.
- **Choosing a method**: See `../01-method-selection-guide.md` for the decision tree and comparison table.
- **Debugging training issues**: `CLAUDE.md` documents the config hierarchy (AlignmentConfig -> method-specific configs -> TRL configs) and the pipeline flow.

## Related Docs

| Location                          | Content                                                                       |
| --------------------------------- | ----------------------------------------------------------------------------- |
| `../01-method-selection-guide.md` | Decision tree for choosing the right alignment method based on available data |
| `../../README.md`                 | Package README with installation, quick start, and full method reference      |
| `../../src/kailash_align/`        | Source code (single source of truth for API details)                          |
