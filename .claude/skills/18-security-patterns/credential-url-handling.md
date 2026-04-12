---
name: credential-url-handling
description: "Canonical pattern for encoding, decoding, and masking credentials in DATABASE_URL-style connection strings. Use when implementing a new database adapter, modifying credential parsing, or adding connection-string logging."
---

# Credential URL Handling -- Canonical Pipeline

## The Pipeline

Three helpers compose the credential lifecycle. They live in two
modules because core SDK and DataFlow have separate dependency graphs,
but the contract is the same.

### 1. `preencode_password_special_chars(url)` -- Input Sanitization

Lives in: `src/kailash/config/database_config.py` (builder methods)

Handles raw user-provided URLs that contain unencoded `# $ @ ? :`
in the password segment. Returns a URL with those characters
percent-encoded so that `urlparse` splits correctly.

### 2. `decode_userinfo_or_raise(parsed_url)` -- Output Decoding

Lives in: each adapter's connect path (to be consolidated into
`kailash.utils.url_credentials` when that module is promoted)

Takes a `ParseResult`, calls `unquote()` on username and password,
and rejects null bytes after decoding. Returns `(user, password)`.

```python
from urllib.parse import urlparse, unquote

def decode_userinfo_or_raise(parsed):
    user = unquote(parsed.username or "")
    password = unquote(parsed.password or "")
    if "\x00" in user or "\x00" in password:
        raise ValueError(
            "Null byte in decoded credentials -- possible auth bypass"
        )
    return user, password
```

**Null-byte defense**: A crafted `mysql://user:%00bypass@host/db`
decodes to `\x00bypass`. The MySQL C client truncates at the first
null byte and the driver sends an empty password, matching any
`mysql.user` row with an empty `authentication_string`.

### 3. `mask_url(url)` -- Log-Safe Form

Lives in: `packages/kailash-dataflow/src/dataflow/utils/masking.py`

Replaces the entire userinfo segment with `***` while preserving
scheme, host, port, path, and non-sensitive query params. Sensitive
query keys (`password`, `sslpassword`, `sslkey`, `authtoken`,
`token`, `apikey`) are masked individually.

Canonical output form: `scheme://***@host[:port]/path`

```python
# Correct output examples
"postgresql://***@db.internal:5432/kailash"
"redis://***@cache:6379/0"
"mongodb://***@rs0:27017,rs1:27017/kailash?replicaSet=rs0"
```

## Standard Adapter Pattern

```python
from urllib.parse import urlparse

class MySQLAdapter:
    def __init__(self, connection_string: str):
        self._url = connection_string

    async def connect(self):
        parsed = urlparse(self._url)
        user, password = decode_userinfo_or_raise(parsed)
        host = parsed.hostname
        port = parsed.port or 3306
        db = parsed.path.lstrip("/")

        logger.info("mysql.connect", url=mask_url(self._url))
        self._conn = await aiomysql.connect(
            host=host, port=port, user=user, password=password, db=db
        )
```

## Sanitizer Barriers for CodeQL

`mask_url` and `safe_log_value` are declared as taint barriers in
`.github/codeql/sanitizers/sanitizers.model.yml`. Routing log values
through them prevents `py/clear-text-logging-sensitive-data` false
positives on adapter init log lines.

If you add a new masking helper, it MUST be registered in the
sanitizer model file or CodeQL will flag every log line that uses it.

## Sensitive-Key Set

Six keys are masked in query strings across 4 sites:

```python
SENSITIVE_QUERY_KEYS = {"password", "sslpassword", "sslkey", "authtoken", "token", "apikey"}
```

Sites: `database_config.py`, `dataflow/utils/masking.py`,
`trust/rate_limit/backends/redis.py`,
`nexus/auth/rate_limit/backends/redis.py`.

Parametrized regression tests at
`tests/regression/test_arbor_database_url_special_chars.py`
verify all four sites mask the same key set.

## Origin

`workspaces/arbor-upstream-fixes/.session-notes` (2026-04-12)
