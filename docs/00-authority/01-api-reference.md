# Trust-Plane API Reference

## TrustProject

The main API class. All operations on a trust-plane project go through this.

### Create a New Project

```python
from trustplane.project import TrustProject

project = await TrustProject.create(
    trust_dir=".trust-plane",
    name="My Research Project",
    author="Dr. Smith",
)
```

Creates the `.trust-plane/` directory, generates an Ed25519 keypair, creates the genesis attestation, and initializes the default SQLite store.

### Load an Existing Project

```python
project = await TrustProject.load(".trust-plane")
```

### Record a Decision

```python
from trustplane.models import DecisionType

await project.record_decision(
    decision_type=DecisionType.SCOPE,
    description="Focus analysis on dataset A",
    confidence=0.9,
)
```

Decision types: `SCOPE`, `METHODOLOGY`, `DATA_SELECTION`, `ANALYSIS`, `INTERPRETATION`, `PUBLICATION`, `RESOURCE_ALLOCATION`, `COLLABORATION`, `ETHICS`, `GENERAL`.

### Record a Milestone

```python
await project.record_milestone(
    version="v0.1",
    description="Initial data processing complete",
    files=["data/processed.csv"],
)
```

### Check Constraints

```python
verdict = await project.check(action="write_file", resource="/src/main.py")
# Returns: Verdict.AUTO_APPROVED | FLAGGED | HELD | BLOCKED
```

### Verify Chain Integrity

```python
result = await project.verify()
# 4-level verification: anchors, signatures, linkage, delegation
```

## Store Backends

### SQLite (Default)

```python
from trustplane.store.sqlite import SqliteTrustPlaneStore

store = SqliteTrustPlaneStore(".trust-plane/trust.db")
store.initialize()  # Creates tables, enables WAL mode

# Pass to TrustProject
project = await TrustProject.create(trust_dir, name, author, tp_store=store)
```

### Filesystem

```python
from trustplane.store.filesystem import FileSystemTrustPlaneStore

store = FileSystemTrustPlaneStore(Path(".trust-plane"))
store.initialize()
```

### PostgreSQL

```python
from trustplane.store.postgres import PostgresTrustPlaneStore

store = PostgresTrustPlaneStore("postgresql://user:pass@host/db")
store.initialize()
```

Requires `pip install trust-plane[postgres]`.

## Encryption at Rest

```python
from trustplane.crypto_utils import encrypt_record, decrypt_record, derive_encryption_key

# Derive a key from a passphrase
key = derive_encryption_key(passphrase=b"my-secret", salt=b"project-salt")

# Encrypt a record dict
ciphertext = encrypt_record(record_dict, key)

# Decrypt
plaintext_dict = decrypt_record(ciphertext, key)
```

Requires `pip install trust-plane[encryption]`.

## RBAC

```python
from trustplane.rbac import RBACManager, Role

rbac = RBACManager(trust_dir=Path(".trust-plane"))

# Assign a role
rbac.assign_role(user_id="alice", role=Role.ADMIN)

# Check permission
allowed = rbac.check_permission(user_id="alice", operation="record_decision")

# List assignments
assignments = rbac.list_assignments()
```

Roles: `ADMIN` (full access), `AUDITOR` (read + verify), `DELEGATE` (scoped operations), `OBSERVER` (read-only).

## Key Management

### Local Ed25519 (Default)

```python
from trustplane.key_manager import LocalFileKeyManager

km = LocalFileKeyManager(key_dir=Path(".trust-plane/keys"))
signature = km.sign(b"data to sign")
pub_key = km.get_public_key()
```

### AWS KMS

```python
from trustplane.key_managers.aws_kms import AwsKmsKeyManager

km = AwsKmsKeyManager(key_id="arn:aws:kms:us-east-1:123:key/abc")
```

Requires `pip install trust-plane[aws]`.

### Azure Key Vault

```python
from trustplane.key_managers.azure_keyvault import AzureKeyVaultKeyManager

km = AzureKeyVaultKeyManager(vault_url="https://myvault.vault.azure.net", key_name="trust-key")
```

Requires `pip install trust-plane[azure]`.

### HashiCorp Vault

```python
from trustplane.key_managers.vault import VaultKeyManager

km = VaultKeyManager(vault_addr="https://vault.example.com", key_name="trust-key")
```

Requires `pip install trust-plane[vault]`.

## OIDC Identity Verification

```python
from trustplane.identity import OIDCVerifier, IdentityProvider

provider = IdentityProvider(
    name="okta",
    issuer="https://dev-123.okta.com/oauth2/default",
    client_id="my-client-id",
)

verifier = OIDCVerifier(provider)
claims = verifier.verify_token(jwt_token)
```

Requires `pip install trust-plane[sso]`.

## Shadow Mode

Zero-config observation of AI activity. No `attest init` required.

```python
from trustplane.shadow import ShadowObserver, ShadowSession

observer = ShadowObserver()
session = ShadowSession(session_id="s1")

observer.record(session, action="Read", resource="/src/main.py")
observer.record(session, action="Write", resource="/src/utils.py")

report = observer.generate_report(session)
```

## SIEM Integration

```python
from trustplane.siem import format_cef, format_ocsf

# CEF v0 for Splunk/QRadar
cef_line = format_cef(decision_record, project_name="my-project")

# OCSF 1.1 for CrowdStrike/Sentinel
ocsf_event = format_ocsf(decision_record, project_name="my-project")
```

## Compliance Export

```python
from trustplane.compliance import export_soc2_evidence, export_iso27001_evidence

# SOC2 CSV export
soc2_csv = export_soc2_evidence(store, format="csv")

# ISO 27001 JSON export
iso_json = export_iso27001_evidence(store, format="json")
```

## Dashboard

```python
from trustplane.dashboard import serve_dashboard

# Starts on localhost:8080 (never 0.0.0.0)
serve_dashboard(trust_dir=".trust-plane", port=8080)
```

Or via CLI: `attest dashboard --port 8080`
