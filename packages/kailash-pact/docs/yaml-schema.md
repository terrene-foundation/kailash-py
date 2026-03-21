# YAML Organization Schema

The PACT YAML format defines an entire organization -- structure, clearances, envelopes, bridges, and knowledge share policies -- in a single file. This document covers every field and every validation rule.

## Minimal Example

```yaml
org_id: "my-org"
name: "My Organization"

departments:
  - id: d-main
    name: Main Department

roles:
  - id: r-lead
    name: Lead
    heads: d-main
```

## Full Example

See `tests/unit/governance/fixtures/university-org.yaml` for a complete example with all features.

## Top-Level Fields

| Field       | Type   | Required | Description                             |
| ----------- | ------ | -------- | --------------------------------------- |
| org_id      | string | yes      | Unique identifier for this organization |
| name        | string | yes      | Human-readable name                     |
| departments | list   | no       | Department definitions                  |
| teams       | list   | no       | Team definitions                        |
| roles       | list   | no       | Role definitions (the people/agents)    |
| clearances  | list   | no       | Clearance assignments                   |
| envelopes   | list   | no       | Operating envelope configurations       |
| bridges     | list   | no       | Cross-Functional Bridge definitions     |
| ksps        | list   | no       | Knowledge Share Policy definitions      |

**Validation errors**:

- Missing `org_id`: `Required field 'org_id' is missing from YAML org definition`
- Missing `name`: `Required field 'name' is missing from YAML org definition`
- Non-dict root: `YAML org definition must be a mapping (dict), got {type}`

---

## departments

Each department entry creates an organizational unit (D node) in the compiled org.

```yaml
departments:
  - id: d-engineering
    name: School of Engineering
  - id: d-administration
    name: Administration
```

| Field | Type   | Required | Description                                                    |
| ----- | ------ | -------- | -------------------------------------------------------------- |
| id    | string | yes      | Unique department identifier (used in role `heads` references) |
| name  | string | no       | Human-readable name (defaults to id if omitted)                |

**Validation errors**:

- Missing `id`: `Department entry {i} is missing required 'id' field`
- Not a dict: `Department entry {i} must be a mapping, got {type}`

---

## teams

Each team entry creates a team unit (T node) in the compiled org.

```yaml
teams:
  - id: t-cs-dept
    name: CS Department
  - id: t-finance
    name: Finance
```

| Field | Type   | Required | Description                                              |
| ----- | ------ | -------- | -------------------------------------------------------- |
| id    | string | yes      | Unique team identifier (used in role `heads` references) |
| name  | string | no       | Human-readable name (defaults to id if omitted)          |

**Validation errors**:

- Missing `id`: `Team entry {i} is missing required 'id' field`
- Not a dict: `Team entry {i} must be a mapping, got {type}`

---

## roles

Roles are the core of the D/T/R grammar. They define the accountability chain (who reports to whom) and which units they head.

```yaml
roles:
  - id: r-president
    name: President
    heads: d-president-office

  - id: r-provost
    name: Provost
    reports_to: r-president
    heads: d-academic-affairs

  - id: r-cs-faculty
    name: CS Faculty Member
    reports_to: r-cs-chair

  - id: r-irb-director
    name: IRB Director
    reports_to: r-dean-med
    heads: t-research-lab
    agent: agent-irb
```

| Field      | Type   | Required | Description                                                                                                 |
| ---------- | ------ | -------- | ----------------------------------------------------------------------------------------------------------- |
| id         | string | yes      | Unique role identifier                                                                                      |
| name       | string | no       | Human-readable name (defaults to id)                                                                        |
| reports_to | string | no       | role id of the supervisor. Root roles omit this.                                                            |
| heads      | string | no       | department or team id this role heads. Every D or T must have exactly one role with `heads` pointing to it. |
| agent      | string | no       | Agent ID for roles occupied by AI agents                                                                    |

**Key rules**:

- Every `reports_to` must reference an existing role id
- Every `heads` must reference an existing department or team id
- Role ids must be unique (duplicates raise an error)
- Circular `reports_to` chains are detected and rejected

**Validation errors**:

- Missing `id`: `Role entry {i} is missing required 'id' field`
- Duplicate id: `Duplicate role ID '{id}'`
- Bad `reports_to` ref: `Role '{id}' has reports_to='{ref}', but '{ref}' was not found`
- Bad `heads` ref: `Role '{id}' references unit '{unit}' via 'heads' field, but '{unit}' was not found`

---

## clearances

Clearance assignments control who can access what classification level of information. Clearance is independent of authority -- a junior specialist can hold higher clearance than a senior executive.

```yaml
clearances:
  - role: r-president
    level: secret
    nda_signed: true

  - role: r-irb-director
    level: secret
    compartments: [human-subjects]
    nda_signed: true

  - role: r-cs-faculty
    level: restricted
```

| Field        | Type            | Required | Description                                                  |
| ------------ | --------------- | -------- | ------------------------------------------------------------ |
| role         | string          | yes      | Role id to assign clearance to                               |
| level        | string          | yes      | One of: public, restricted, confidential, secret, top_secret |
| compartments | list of strings | no       | Named compartments for compartmented access (default: [])    |
| nda_signed   | boolean         | no       | Whether NDA is signed (default: false)                       |

**Validation errors**:

- Missing `role`: `Clearance entry {i} is missing required 'role' field`
- Bad role ref: `Clearance entry {i} references role '{id}' which was not found`
- Invalid level: `Clearance entry {i} has invalid level '{level}'. Valid levels: [...]`

---

## envelopes

Envelopes define operating boundaries -- spending limits, allowed actions, and other constraint dimensions.

```yaml
envelopes:
  - target: r-cs-chair
    defined_by: r-dean-eng
    financial:
      max_spend_usd: 10000
      requires_approval_above_usd: 5000
      api_cost_budget_usd: 200
    operational:
      allowed_actions: [read, write, approve]
      blocked_actions: [deploy]
      max_actions_per_day: 100
    temporal:
      active_hours_start: "09:00"
      active_hours_end: "17:00"
      timezone: "America/New_York"
    data_access:
      read_paths: ["/data/public", "/data/department"]
      write_paths: ["/data/department"]
    communication:
      internal_only: true
      allowed_channels: [email, slack]
```

| Field         | Type   | Required | Description                           |
| ------------- | ------ | -------- | ------------------------------------- |
| target        | string | yes      | Role id the envelope applies to       |
| defined_by    | string | yes      | Role id of the supervisor defining it |
| financial     | object | no       | Financial constraints (see below)     |
| operational   | object | no       | Operational constraints (see below)   |
| temporal      | object | no       | Temporal constraints (see below)      |
| data_access   | object | no       | Data access constraints (see below)   |
| communication | object | no       | Communication constraints (see below) |

### financial

| Field                       | Type    | Default | Description                         |
| --------------------------- | ------- | ------- | ----------------------------------- |
| max_spend_usd               | float   | 0.0     | Maximum spending limit in USD       |
| api_cost_budget_usd         | float   | null    | Optional API cost budget            |
| requires_approval_above_usd | float   | null    | Threshold for human approval        |
| reasoning_required          | boolean | false   | Whether reasoning trace is required |

### operational

| Field                | Type            | Default | Description                           |
| -------------------- | --------------- | ------- | ------------------------------------- |
| allowed_actions      | list of strings | []      | Explicit allow list (empty = all)     |
| blocked_actions      | list of strings | []      | Explicit block list (overrides allow) |
| max_actions_per_day  | int             | null    | Daily rate limit                      |
| max_actions_per_hour | int             | null    | Hourly rate limit                     |
| reasoning_required   | boolean         | false   | Whether reasoning trace is required   |

### temporal

| Field              | Type            | Default | Description                            |
| ------------------ | --------------- | ------- | -------------------------------------- |
| active_hours_start | string          | null    | Start time (HH:MM format)              |
| active_hours_end   | string          | null    | End time (HH:MM format)                |
| timezone           | string          | "UTC"   | Timezone name                          |
| blackout_periods   | list of strings | []      | ISO date ranges when action is blocked |

### data_access

| Field              | Type            | Default | Description                        |
| ------------------ | --------------- | ------- | ---------------------------------- |
| read_paths         | list of strings | []      | Allowed read paths                 |
| write_paths        | list of strings | []      | Allowed write paths                |
| blocked_data_types | list of strings | []      | Data types that are always blocked |

### communication

| Field                      | Type            | Default | Description                         |
| -------------------------- | --------------- | ------- | ----------------------------------- |
| internal_only              | boolean         | false   | Block all external communication    |
| allowed_channels           | list of strings | []      | Permitted communication channels    |
| external_requires_approval | boolean         | false   | Require approval for external comms |

---

## bridges

Cross-Functional Bridges connect two roles across organizational boundaries. They are role-level (not unit-level) access paths.

```yaml
bridges:
  - id: bridge-provost-vpadmin
    role_a: r-provost
    role_b: r-vp-admin
    type: standing
    max_classification: restricted
    bilateral: false

  - id: bridge-eng-med-research
    role_a: r-dean-eng
    role_b: r-dean-med
    type: scoped
    max_classification: confidential
    bilateral: true
```

| Field              | Type    | Required | Description                                  |
| ------------------ | ------- | -------- | -------------------------------------------- |
| id                 | string  | yes      | Unique bridge identifier                     |
| role_a             | string  | yes      | First role id in the bridge                  |
| role_b             | string  | yes      | Second role id in the bridge                 |
| type               | string  | yes      | One of: standing, scoped, ad_hoc             |
| max_classification | string  | yes      | Maximum classification accessible via bridge |
| bilateral          | boolean | no       | Both roles get mutual access (default: true) |

**bilateral=false**: Only role_a can access role_b's data. Role_b cannot access role_a's data through this bridge.

---

## ksps

Knowledge Share Policies are directional unit-level access grants (unlike bridges which are role-level).

```yaml
ksps:
  - id: ksp-acad-to-hr
    source: d-academic-affairs
    target: t-hr
    max_classification: restricted
```

| Field              | Type   | Required | Description                                 |
| ------------------ | ------ | -------- | ------------------------------------------- |
| id                 | string | yes      | Unique KSP identifier                       |
| source             | string | yes      | Department or team id that shares knowledge |
| target             | string | yes      | Department or team id that receives access  |
| max_classification | string | yes      | Maximum classification level shared         |

**Direction**: The source shares with the target. This is one-way. If Academic Affairs shares with HR, HR can read Academic data at the specified classification level, but Academic Affairs does NOT gain access to HR data through this KSP.

---

## Loading in Python

```python
from pact.governance.yaml_loader import load_org_yaml, ConfigurationError

try:
    loaded = load_org_yaml("my-org.yaml")
except ConfigurationError as e:
    print(f"Invalid config: {e}")

# loaded.org_definition  -- OrgDefinition ready for GovernanceEngine
# loaded.clearances      -- list of ClearanceSpec
# loaded.envelopes       -- list of EnvelopeSpec
# loaded.bridges         -- list of BridgeSpec
# loaded.ksps            -- list of KspSpec
```

## CLI Validation

```bash
python -m pact.governance.cli validate my-org.yaml
```

This loads the YAML, compiles the org, and reports any errors without starting a server.
