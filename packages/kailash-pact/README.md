# kailash-pact

**PACT governance framework** — D/T/R accountability grammar, operating envelopes, knowledge clearance, and verification gradient for AI agent organizations.

Part of the [Kailash](https://github.com/terrene-foundation/kailash-py) enterprise AI platform.

## Quick Start

```python
from pact.governance import GovernanceEngine

engine = GovernanceEngine.from_yaml("my-org.yaml")
verdict = engine.verify_action("D1-R1-T1-R1", "write_report", {"cost": 50.0})

if verdict.allowed:
    print("Approved:", verdict.reason)
else:
    print("Blocked:", verdict.reason)
```

## Installation

```bash
pip install kailash-pact
```

With Kaizen agent integration:
```bash
pip install kailash-pact[kaizen]
```

## Features

- **D/T/R Grammar Engine** — Accountability grammar (Department/Team/Role) with positional addressing
- **Three-Layer Envelopes** — Role (standing) + Task (ephemeral) = Effective (computed intersection)
- **Knowledge Clearance** — Five-level classification independent of authority/seniority
- **5-Step Access Enforcement** — Clearance → Classification → Compartment → Containment → Deny
- **GovernanceEngine** — Single facade composing all primitives
- **PactGovernedAgent** — Wrap any Kaizen agent with governance enforcement
- **SQLite/PostgreSQL Stores** — Persistent governance state
- **REST API** — 9 governance endpoints with auth and rate limiting
- **CLI** — `kailash-pact validate org.yaml`

## Documentation

- [Quickstart](docs/quickstart.md) — Zero to governance in 10 minutes
- [Architecture](docs/architecture.md) — How it all fits together
- [Vertical Guide](docs/vertical-guide.md) — Build your own governed platform
- [API Reference](docs/api.md) — REST endpoints
- [Cookbook](docs/cookbook.md) — Common patterns
- [YAML Schema](docs/yaml-schema.md) — Org definition format

## License

Apache 2.0 — Terrene Foundation
