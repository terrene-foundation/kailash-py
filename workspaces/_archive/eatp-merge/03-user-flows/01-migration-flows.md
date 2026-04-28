# User Migration Flows — EATP + Trust-Plane Merge

## Overview

Three user personas are affected by this merge. Each has a distinct migration path.

---

## Flow 1: EATP SDK User (External)

**Persona**: Developer who `pip install eatp` and uses the EATP SDK for trust chain management.

### Before (current)

```bash
pip install eatp
```

```python
from eatp import TrustOperations, TrustKeyManager, CapabilityRequest
from eatp.chain import GenesisRecord, DelegationRecord, TrustLineageChain
from eatp.crypto import generate_keypair, sign, verify_signature
from eatp.store.memory import InMemoryTrustStore
from eatp.enforce.strict import StrictEnforcer, Verdict
```

### During transition (shim period)

```bash
pip install eatp>=0.3.0  # Pulls in kailash[trust] automatically
```

```python
# OLD imports still work but emit DeprecationWarning
from eatp import TrustOperations  # Warning: use kailash.trust instead

# User sees:
# DeprecationWarning: The 'eatp' package is deprecated.
# Use 'from kailash.trust import ...' instead.
# Install: pip install kailash[trust]
```

### After (migrated)

```bash
pip install kailash[trust]
```

```python
from kailash.trust import TrustOperations, TrustKeyManager, CapabilityRequest
from kailash.trust.chain import GenesisRecord, DelegationRecord, TrustLineageChain
from kailash.trust.signing.crypto import generate_keypair, sign, verify_signature
from kailash.trust.chain_store.memory import InMemoryTrustStore
from kailash.trust.enforce.strict import StrictEnforcer, Verdict
```

### Migration effort

- **Install**: Change `eatp` to `kailash[trust]` in requirements.txt
- **Imports**: Find-and-replace `from eatp` to `from kailash.trust` (with store/crypto path adjustments)
- **Code changes**: Zero — all APIs are identical, only import paths change
- **Timeline**: Immediate — shims work on day 1

---

## Flow 2: Trust-Plane User (External)

**Persona**: Developer who `pip install trust-plane` and uses TrustProject for governance.

### Before (current)

```bash
pip install trust-plane
```

```python
from trustplane import TrustProject, DecisionRecord, DecisionType
from trustplane.store.sqlite import SqliteTrustPlaneStore
from trustplane.models import ConstraintEnvelope, OperationalConstraints
```

### During transition (shim period)

```bash
pip install trust-plane>=0.3.0  # Pulls in kailash[trust] automatically
```

```python
# OLD imports still work but emit DeprecationWarning
from trustplane import TrustProject  # Warning: use kailash.trust.plane instead
```

### After (migrated)

```bash
pip install kailash[trust]
```

```python
from kailash.trust.plane import TrustProject, DecisionRecord, DecisionType
from kailash.trust.plane.store.sqlite import SqliteTrustPlaneStore
from kailash.trust.plane.models import ConstraintEnvelope, OperationalConstraints
```

### Migration effort

- **Install**: Change `trust-plane` to `kailash[trust]` in requirements.txt
- **Imports**: Find-and-replace `from trustplane` to `from kailash.trust.plane`
- **Code changes**: Zero — all APIs are identical
- **Timeline**: Immediate — shims work on day 1

---

## Flow 3: Kaizen User (Internal + External)

**Persona**: Developer using kailash-kaizen for AI agents with trust integration.

### Before (current)

```bash
pip install kailash-kaizen  # Pulls in kailash + eatp
```

```python
from kaizen.trust import TrustOperations  # Re-exported from eatp
from kaizen.trust.crypto import generate_keypair
from kaizen import TrustedAgent
```

### After (migrated)

```bash
pip install kailash-kaizen>=2.0.0  # Pulls in kailash>=2.0.0 (includes trust)
```

```python
# Both paths work — kaizen re-export layer preserved
from kaizen.trust import TrustOperations  # Still works (now from kailash.trust)
from kailash.trust import TrustOperations  # Also works (canonical path)
from kaizen import TrustedAgent  # Unchanged
```

### Migration effort

- **Install**: Update version pin to `kailash-kaizen>=2.0.0`
- **Imports**: No change required — kaizen re-export layer preserved
- **Code changes**: Zero
- **Timeline**: After kaizen 2.0.0 is published

---

## Flow 4: Kailash Core User (No Trust)

**Persona**: Developer using kailash for workflow orchestration only.

### Impact

- `pip install kailash>=2.0.0` — installs normally, no pynacl
- `from kailash import Workflow, LocalRuntime` — works exactly as before
- `from kailash.trust.chain import GenesisRecord` — works (trust types are pure Python)
- `from kailash.trust.signing.crypto import generate_keypair` — raises `ImportError` with message: "Install kailash[trust]"

### Migration effort

- **Install**: Update version pin to `kailash>=2.0.0`
- **pydantic**: Must be on pydantic v2 (>=2.6). If still on v1, upgrade pydantic first.
- **Code changes**: Zero for non-trust users

---

## Flow 5: New User (Post-Merge)

**Persona**: Developer discovering kailash for the first time after the merge.

### Getting started with trust

```bash
pip install kailash[trust]
```

```python
from kailash.trust import TrustOperations, TrustKeyManager, generate_keypair
from kailash.trust.chain_store.memory import InMemoryTrustStore

# Create trust chain
ops = TrustOperations(store=InMemoryTrustStore())
key_mgr = TrustKeyManager()
```

### Getting started with trust-plane governance

```bash
pip install kailash[trust]
```

```python
from kailash.trust.plane import TrustProject, DecisionRecord
from kailash.trust.plane.store.sqlite import SqliteTrustPlaneStore

project = await TrustProject.create(
    trust_dir=Path(".trust"),
    project_name="My Project",
    author="Developer",
    tp_store=SqliteTrustPlaneStore(".trust/trust.db"),
)
```

### Discovery path

1. `pip install kailash` — core workflow SDK
2. Discover trust via docs: "Add trust to your workflows with `pip install kailash[trust]`"
3. `from kailash.trust import ...` — protocol-level trust
4. `from kailash.trust.plane import ...` — governance layer

---

## CLI User Flows

### EATP CLI

```bash
# Before
pip install eatp
eatp --help

# After (both work)
pip install kailash[trust]
eatp --help  # Same CLI, same commands

# Via shim
pip install eatp>=0.3.0  # Pulls in kailash[trust]
eatp --help  # Works with deprecation notice
```

### Trust-Plane CLI

```bash
# Before
pip install trust-plane
attest --help
trustplane-mcp  # Start MCP server

# After (both work)
pip install kailash[trust]
attest --help  # Same CLI
trustplane-mcp  # Same MCP server
```

---

## Deprecation Timeline

| Phase      | When                      | What Happens                                                                |
| ---------- | ------------------------- | --------------------------------------------------------------------------- |
| Day 0      | kailash 2.0.0 release     | Shim packages published. Old imports work with DeprecationWarning.          |
| +6 months  | kailash 2.1.0             | DeprecationWarning upgraded to FutureWarning (more visible)                 |
| +12 months | kailash 2.2.0+            | Shim packages stop publishing new versions. Existing versions stay on PyPI. |
| +18 months | kailash 3.0.0 (if needed) | Old import paths no longer supported. Shim packages yanked.                 |

---

## Common Migration Mistakes

### Mistake 1: Installing both eatp and kailash[trust]

```bash
pip install eatp kailash[trust]  # Redundant but harmless
# eatp 0.3.0 depends on kailash[trust] anyway
```

No harm — eatp 0.3.0 is a shim that depends on kailash[trust].

### Mistake 2: Pinning to old eatp version

```bash
pip install eatp==0.2.0 kailash>=2.0.0
# eatp 0.2.0 has its own code — CONFLICT with kailash.trust
```

This could cause import confusion. The shim eatp 0.3.0 resolves it.

### Mistake 3: Mixing old and new import paths

```python
from eatp import TrustOperations  # Shim path
from kailash.trust.chain import GenesisRecord  # New path
```

Works but ugly. The DeprecationWarning nudges toward full migration.
