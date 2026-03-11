# JSON Schemas

EATP provides JSON Schema definitions (draft 2020-12) for all wire format records.

## Schema Files

Located in `schemas/` at the package root:

- `genesis-record.schema.json`
- `capability-attestation.schema.json`
- `delegation-record.schema.json`
- `audit-anchor.schema.json`
- `constraint-envelope.schema.json`
- `verification-verdict.schema.json`
- `signed-envelope.schema.json`

## Usage

Validate records against schemas:

```python
import json
import jsonschema

with open("schemas/genesis-record.schema.json") as f:
    schema = json.load(f)

record = {
    "id": "gen-12345678-1234-1234-1234-123456789012",
    "agent_id": "agent-001",
    "authority_id": "org-acme",
    "authority_type": "organization",
    "created_at": "2025-01-15T10:30:00+00:00",
    "signature": "base64-encoded-signature",
    "signature_algorithm": "Ed25519",
}

jsonschema.validate(record, schema)  # Raises if invalid
```

## Schema Design

- All schemas use `"additionalProperties": false` to reject unknown fields
- Optional fields use `"type": ["string", "null"]`
- Enums constrain valid values (e.g., authority_type, capability_type, result)
- IDs follow format patterns (e.g., `^gen-[0-9a-f-]+$`)
