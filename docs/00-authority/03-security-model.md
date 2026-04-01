# Trust-Plane Security Model

## Threat Model

TrustPlane protects against:

1. **Tampered records** — Cryptographic signatures (Ed25519) on all attestations
2. **Path traversal** — `validate_id()` regex `^[a-zA-Z0-9_-]+$` on all record IDs
3. **Symlink attacks** — `O_NOFOLLOW` flag on all file open operations
4. **Partial writes** — Atomic write (temp + fsync + rename) prevents corruption on crash
5. **Timing attacks** — `hmac.compare_digest()` for all hash/signature comparisons
6. **NaN/Inf bypass** — `math.isfinite()` on all numeric constraint fields
7. **Memory inspection** — Key material zeroized after use, `del` references
8. **Unbounded growth** — All collections bounded (`deque(maxlen=10000)`)
9. **Trust downgrade** — Monotonic escalation only (AUTO_APPROVED -> FLAGGED -> HELD -> BLOCKED)
10. **Mutable policy bypass** — `MultiSigPolicy` is `frozen=True` dataclass
11. **Malformed deserialization** — `from_dict()` validates all fields, no silent defaults

## Encryption at Rest

AES-256-GCM via the `cryptography` library.

```python
from kailash.trust.plane.encryption.crypto_utils import derive_encryption_key, encrypt_record, decrypt_record

key = derive_encryption_key(passphrase=b"secret", salt=b"project-salt")
ciphertext = encrypt_record({"decision_id": "d1", ...}, key)
plaintext = decrypt_record(ciphertext, key)
```

- Key derivation: HKDF-SHA256 with configurable salt
- Cipher: AES-256-GCM (authenticated encryption)
- Random 96-bit nonce per encryption
- Decryption failures raise `TrustDecryptionError`

Install: `pip install kailash` (included in base install)

## Role-Based Access Control (RBAC)

Four roles with predefined permission sets:

| Role         | Permissions                                                                            |
| ------------ | -------------------------------------------------------------------------------------- |
| **ADMIN**    | All 12 operations                                                                      |
| **AUDITOR**  | read_decisions, read_milestones, read_holds, read_delegates, verify, export_compliance |
| **DELEGATE** | read_decisions, read_milestones, record_decision, record_milestone                     |
| **OBSERVER** | read_decisions, read_milestones, read_holds                                            |

Operations: `record_decision`, `record_milestone`, `create_hold`, `resolve_hold`, `create_delegate`, `revoke_delegate`, `read_decisions`, `read_milestones`, `read_holds`, `read_delegates`, `verify`, `export_compliance`.

```python
from kailash.trust.plane.rbac import RBACManager, Role

rbac = RBACManager(trust_dir=Path(".trust-plane"))
rbac.assign_role("alice", Role.ADMIN)
rbac.check_permission("alice", "record_decision")  # True
```

## Key Management

### TrustPlaneKeyManager Protocol

```python
class TrustPlaneKeyManager(Protocol):
    def sign(self, data: bytes) -> bytes: ...
    def get_public_key(self) -> bytes: ...
    def key_id(self) -> str: ...
    def algorithm(self) -> str: ...
```

### Available Key Managers

| Manager                   | Algorithm         | Install Extra |
| ------------------------- | ----------------- | ------------- |
| `LocalFileKeyManager`     | Ed25519           | (none)        |
| `AwsKmsKeyManager`        | ECDSA P-256       | `[aws]`       |
| `AzureKeyVaultKeyManager` | EC P-256          | `[azure]`     |
| `VaultKeyManager`         | Ed25519 (Transit) | `[vault]`     |

**Algorithm mismatch note**: AWS KMS does not support Ed25519. When using `AwsKmsKeyManager`, signatures use ECDSA P-256 (SHA-256). This is a documented deviation from the default Ed25519 requirement per `.claude/rules/eatp.md`.

## OIDC Identity Verification

JWT token verification for identity-bound attestations.

```python
from kailash.trust.plane.identity import OIDCVerifier, IdentityProvider

provider = IdentityProvider(
    name="okta",
    issuer="https://dev-123.okta.com/oauth2/default",
    client_id="my-client-id",
)
verifier = OIDCVerifier(provider)
claims = verifier.verify_token(token)  # Raises on invalid/expired
```

Supported providers: `okta`, `azure_ad`, `google`, `generic_oidc`.

Default token expiry: 8 hours (configurable).

Install: `pip install kailash` (included in base install)

## File Permissions

- **POSIX**: Private keys and database files created with `0o600` (owner read/write only)
- **Windows**: `pywin32` DACL restricts access to current user's SID
- **Windows without pywin32**: Warning logged, file still written (degraded security)

Install for Windows: `pip install kailash[trust-windows]`
