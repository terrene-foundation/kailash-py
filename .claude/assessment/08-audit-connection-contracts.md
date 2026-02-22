# Audit 08: Core SDK Connection Contracts

**Claim**: "Connection contracts are optional and validation skipped if contracts missing"
**Verdict**: **DESIGN CHOICE - Opt-in with full enforcement when configured**

---

## Evidence

### ConnectionContract Class

**File**: `src/kailash/workflow/contracts.py:49-214`

```python
@dataclass
class ConnectionContract:
    name: str
    description: str = ""
    source_schema: Optional[Dict[str, Any]] = None      # JSON Schema for source output
    target_schema: Optional[Dict[str, Any]] = None      # JSON Schema for target input
    security_policies: List[SecurityPolicy] = field(default_factory=list)
    transformations: Optional[Dict[str, Any]] = None
    audit_level: str = "normal"                          # 'none', 'normal', 'detailed'
    metadata: Dict[str, Any] = field(default_factory=dict)
```

Eight fields total. Uses JSON Schema (`Draft7Validator`) for both source and target validation.

### SecurityPolicy Enum

**File**: `src/kailash/workflow/contracts.py:27-46`

```python
class SecurityPolicy(Enum):
    NONE = "none"
    NO_PII = "no_pii"                # No personally identifiable information
    NO_CREDENTIALS = "no_credentials" # No passwords, tokens, or keys
    NO_SQL = "no_sql"                # No SQL queries (prevents injection)
    SANITIZED = "sanitized"          # Data must be sanitized/escaped
    ENCRYPTED = "encrypted"          # Data must be encrypted in transit
```

Security policy enforcement (`check_security_policies()`, lines 140-185) uses pattern matching:

- **NO_PII**: Detects `ssn`, `social security`, `credit card`, `passport`
- **NO_CREDENTIALS**: Detects `password`, `token`, `api_key`, `secret`, `private_key`
- **NO_SQL**: Detects `select `, `insert `, `update `, `delete `, `drop `, `union `

### Pre-Registered Contracts

**File**: `src/kailash/workflow/contracts.py:224-296`

The `ContractRegistry._initialize_common_contracts()` registers **5 contracts**:

| Contract       | Lines   | Description                          | Security Policies                        |
| -------------- | ------- | ------------------------------------ | ---------------------------------------- |
| `string_data`  | 227-234 | Basic string data contract           | None                                     |
| `numeric_data` | 237-244 | Numeric data contract                | None                                     |
| `file_path`    | 247-258 | File path validation (no null bytes) | `NO_SQL`                                 |
| `sql_query`    | 261-269 | SQL query with injection protection  | `SANITIZED`                              |
| `user_data`    | 272-296 | User data with PII protection        | `NO_CREDENTIALS`, audit_level=`detailed` |

### Validation Logic

**File**: `src/kailash/workflow/contracts.py:85-185`

- `__post_init__()` (lines 85-98): Validates schemas using `Draft7Validator.check_schema()`
- `validate_source()` (lines 100-118): JSON Schema validation on source data
- `validate_target()` (lines 120-138): JSON Schema validation on target data
- `check_security_policies()` (lines 140-185): Pattern-based policy enforcement

### ContractValidator

**File**: `src/kailash/workflow/contracts.py:327-405`

- `validate_connection()` (lines 333-375): Validates both source and target, checks security policies, accumulates errors
- `suggest_contract()` (lines 377-405): Auto-suggests contracts based on data type (email, file path, SQL, numeric, object with id/name)

### Validation Modes

**File**: `src/kailash/runtime/base.py:165`

```python
connection_validation: str = "warn"  # Default mode
# Valid modes: "strict", "warn", "off"
```

- **strict**: Raises validation errors for contract violations
- **warn**: Logs warnings but continues (DEFAULT)
- **off**: No connection validation

---

## Assessment

| Aspect                             | Status | Notes                                      |
| ---------------------------------- | ------ | ------------------------------------------ |
| Contract system exists             | YES    | Full dataclass with 8 fields               |
| JSON Schema validation             | YES    | Draft7Validator for source and target      |
| Security policy enforcement        | YES    | 6 policies with pattern matching           |
| Pre-populated contracts            | YES    | 5 common contracts pre-registered          |
| Contract suggestion                | YES    | Auto-suggests based on data type           |
| Validation enforced in strict mode | YES    | Raises errors on violations                |
| Default mode is "warn"             | YES    | Warns but continues (design choice)        |
| All nodes define contracts         | NO     | Not all 110+ nodes have explicit contracts |

### The "Optional" Claim is Nuanced

- Contracts ARE optional per-node (not every node defines one)
- But validation IS enforced when `connection_validation="strict"`
- The default "warn" mode is a deliberate design choice for developer experience
- This is similar to TypeScript's `strict` mode - available but not forced

**This is a design decision, not a missing feature.**
