# Kaizen Agent Manifest & Deploy

Declarative agent identity, governance metadata, and local/remote deployment.

## Overview

The Agent Manifest system provides:

- **TOML-based declaration**: Describe agents declaratively with `[agent]` and `[governance]` sections
- **Runtime introspection**: Extract manifest metadata from live `BaseAgent` classes
- **Local-first deployment**: Persist manifests to `FileRegistry` on disk with atomic writes
- **Remote deployment**: Optional POST to a CARE Platform API endpoint
- **A2A interop**: Convert manifests to A2A-compatible Agent Cards

**Source modules**:


---

## TOML Manifest Format

Every agent manifest is a TOML file with two sections: `[agent]` (required) and `[governance]` (optional).

```toml
[agent]
manifest_version = "1.0"
name = "market-analyzer"
module = "agents.market_analyzer"
class_name = "MarketAnalyzer"
description = "Analyzes market trends and produces investment insights"
capabilities = ["market-analysis", "financial-data"]
tools = ["http_get", "read_file"]
supported_models = ["gpt-4", "claude-3-opus"]

[governance]
purpose = "Automated market trend analysis for investment reports"
risk_level = "medium"
data_access_needed = ["market-data", "financial-reports"]
suggested_posture = "supervised"
max_budget_microdollars = 5000000
```

### Field Reference

**`[agent]` section** (all strings unless noted):

| Field              | Required | Default | Description                                               |
| ------------------ | -------- | ------- | --------------------------------------------------------- |
| `manifest_version` | No       | `"1.0"` | Schema version. Must be `"1.0"` (only supported version). |
| `name`             | Yes      | --      | Unique agent identifier. Non-empty string.                |
| `module`           | Yes      | --      | Python dotted module path.                                |
| `class_name`       | Yes      | --      | Agent class name inside the module.                       |
| `description`      | No       | `""`    | Human-readable summary.                                   |
| `capabilities`     | No       | `[]`    | List of capability tags (e.g. `["pii-detection"]`).       |
| `tools`            | No       | `[]`    | Tool identifiers the agent may invoke.                    |
| `supported_models` | No       | `[]`    | LLM model identifiers the agent can work with.            |

**`[governance]` section** (optional):

| Field                     | Required | Default        | Description                                                                                             |
| ------------------------- | -------- | -------------- | ------------------------------------------------------------------------------------------------------- |
| `purpose`                 | No       | `""`           | Why this agent exists.                                                                                  |
| `risk_level`              | No       | `"medium"`     | One of: `low`, `medium`, `high`, `critical`.                                                            |
| `data_access_needed`      | No       | `[]`           | Data categories the agent requires access to.                                                           |
| `suggested_posture`       | No       | `"supervised"` | EATP trust posture: `pseudo_agent`, `supervised`, `shared_planning`, `continuous_insight`, `delegated`. |
| `max_budget_microdollars` | No       | `None`         | Spending cap in microdollars (1 USD = 1,000,000).                                                       |

---

## AgentManifest API

### Creating from TOML

```python
from kaizen.manifest.agent import AgentManifest

# From a file on disk
manifest = AgentManifest.from_toml("agents/market-analyzer.toml")

# From an in-memory TOML string
manifest = AgentManifest.from_toml_str("""
[agent]
manifest_version = "1.0"
name = "market-analyzer"
module = "agents.market_analyzer"
class_name = "MarketAnalyzer"
description = "Analyzes market trends"
capabilities = ["market-analysis"]

[governance]
purpose = "Market trend analysis"
risk_level = "medium"
suggested_posture = "supervised"
max_budget_microdollars = 5000000
""")
```

### Creating Programmatically

```python
from kaizen.manifest.agent import AgentManifest
from kaizen.manifest.governance import GovernanceManifest

governance = GovernanceManifest(
    purpose="Automated market analysis",
    risk_level="medium",
    data_access_needed=["market-data"],
    suggested_posture="supervised",
    max_budget_microdollars=5_000_000,
)

manifest = AgentManifest(
    name="market-analyzer",
    module="agents.market_analyzer",
    class_name="MarketAnalyzer",
    description="Analyzes market trends",
    capabilities=["market-analysis", "financial-data"],
    tools=["http_get"],
    supported_models=["gpt-4"],
    governance=governance,
)
```

### Serialization

```python
# To TOML string (for writing to file)
toml_str = manifest.to_toml()

# To dict (for JSON serialization, API payloads)
manifest_dict = manifest.to_dict()

# From dict (inverse of to_dict)
restored = AgentManifest.from_dict(manifest_dict)

# To A2A Agent Card (for agent-to-agent discovery)
card = manifest.to_agent_card()
# Returns: {"name": "...", "protocols": ["a2a/1.0", "kaizen-manifest/1.0"], ...}
```

### Validation

`AgentManifest.__post_init__()` validates on construction:

- `name`, `module`, `class_name` must be non-empty strings
- `manifest_version` must be `"1.0"` (from `_SUPPORTED_VERSIONS`)

`GovernanceManifest.__post_init__()` validates:

- `risk_level` must be one of `{low, medium, high, critical}`
- `suggested_posture` must be one of `{pseudo_agent, supervised, shared_planning, continuous_insight, delegated}`
- `max_budget_microdollars` must be non-negative if provided

Errors raise `ManifestValidationError` (from `kaizen.manifest.errors`).

---

## Runtime Introspection

Extract manifest metadata from a live Python agent class without instantiating it.

```python
from kaizen.deploy.introspect import introspect_agent
from kaizen.manifest.agent import AgentManifest

# Introspect a class by module path and class name
info = introspect_agent(
    module="agents.market_analyzer",
    class_name="MarketAnalyzer",
)
# info = {"name": "MarketAnalyzer", "module": "agents.market_analyzer",
#         "class_name": "MarketAnalyzer", "description": "...",
#         "capabilities": [...], "tools": [...], "input_schema": {...}, ...}

# Convert to AgentManifest
manifest = AgentManifest.from_introspection(info)
```

**What gets extracted**:

- `signature` class attribute: docstring becomes description, `__annotations__` split into input/output schemas
- `tools` class attribute: list of tool identifiers
- `capabilities` class attribute: list of capability tags
- `supported_models` class attribute: list of model identifiers
- Falls back to class docstring if no signature attribute

**Security note**: `introspect_agent()` uses `importlib.import_module()` which executes module-level code. It is intended for CLI and Python API use only -- NOT safe for MCP exposure.

---

## Deployment

### Local Deployment (Default)

Persists the manifest as a JSON file in `~/.kaizen/registry/`.

```python
from kaizen.deploy.client import deploy, deploy_local

# Option 1: deploy_local() for explicit local deployment
result = deploy_local(manifest.to_dict())
# result.status == "registered"
# result.mode == "local"
# result.agent_name == "market-analyzer"

# Option 2: deploy() with no target_url falls back to local
result = deploy(manifest.to_dict())

# Custom registry directory
result = deploy_local(manifest.to_dict(), registry_dir="/path/to/registry")
```

### Remote Deployment (CARE Platform)

POSTs the manifest to a CARE Platform API at `{target_url}/api/v1/agents`.

```python
from kaizen.deploy.client import deploy

result = deploy(
    manifest.to_dict(),
    target_url="https://care.example.com",
    api_key="your-bearer-token",
    timeout=30,
)
# result.mode == "remote"
# result.governance_match == True/False  (from platform policy)
```

**Error handling**:

- `DeployAuthError` on HTTP 401/403
- `DeployError` on connection failures or other HTTP errors

### FileRegistry

The local registry stores agent manifests as JSON files with atomic writes.

```python
from kaizen.deploy.registry import FileRegistry

registry = FileRegistry()  # Default: ~/.kaizen/registry/
registry = FileRegistry(registry_dir="/custom/path")

# Register
result = registry.register(manifest.to_dict())

# List all agents
agents = registry.list_agents()  # List[Dict]

# Get by name
agent = registry.get_agent("market-analyzer")  # Dict or None

# Remove
removed = registry.deregister("market-analyzer")  # bool
```

**Security**: Agent names are validated against `[a-zA-Z0-9_-]+` to prevent path traversal. Writes use temp-file + fsync + `os.replace()` for crash safety. On POSIX, files are chmod'd to `0o600` (owner-only).

---

## End-to-End Workflow

```python
from kaizen.deploy.introspect import introspect_agent
from kaizen.manifest.agent import AgentManifest
from kaizen.manifest.governance import GovernanceManifest
from kaizen.deploy.client import deploy

# 1. Introspect a live agent class
info = introspect_agent("agents.market_analyzer", "MarketAnalyzer")

# 2. Add governance metadata
info["governance"] = GovernanceManifest(
    purpose="Market trend analysis",
    risk_level="medium",
    suggested_posture="supervised",
    max_budget_microdollars=5_000_000,
).to_dict()

# 3. Create manifest
manifest = AgentManifest.from_introspection(info)

# 4. Write TOML to disk for version control
with open("agents/market-analyzer.toml", "w") as f:
    f.write(manifest.to_toml())

# 5. Deploy locally
result = deploy(manifest.to_dict())
assert result.status == "registered"
```

---

## Critical Rules

- **ALWAYS** validate manifest before deployment -- `AgentManifest.__post_init__` handles this
- **ALWAYS** use `FileRegistry` or `deploy_local()` for local persistence -- not raw file writes
- **NEVER** expose `introspect_agent()` via MCP -- it executes `importlib.import_module()` which runs arbitrary module code
- **NEVER** hardcode model names in manifests -- use `.env` for API keys per project rules
- `manifest_version` must be `"1.0"` -- no other versions are supported
- `GovernanceManifest` risk levels and postures have fixed allowed values -- see validation above

## References

- **Source**: `kaizen/manifest/agent.py`
- **Source**: `kaizen/manifest/governance.py`
- **Source**: `kaizen/deploy/client.py`
- **Source**: `kaizen/deploy/registry.py`
- **Source**: `kaizen/deploy/introspect.py`
