# Milestone 1: Foundation — Adapter Protocol & Source Registration

These todos build the base layer that everything else depends on.

---

## TODO-01: Build BaseSourceAdapter abstract class

**Layer**: 1-2 (adapters)
**File**: `packages/kailash-dataflow/src/dataflow/adapters/source_adapter.py`

Implement `BaseSourceAdapter(BaseAdapter)` with all abstract methods defined in doc 10 (integration-spec):

- `detect_change() -> bool` — cheap change detection
- `fetch(path, params) -> Any` — single request
- `fetch_all(path, page_size, max_records) -> list` — auto-paginate with memory guard (default 100K records)
- `fetch_pages(path, page_size) -> AsyncIterator` — stream pages
- `read() -> Any` — alias for `fetch("")`
- `list(prefix, limit) -> list` — list items
- `write(path, data) -> Any` — write (raises NotImplementedError if read-only)
- `last_successful_data(path) -> Optional[Any]` — last known good for graceful degradation

State machine: registered → connecting → active → paused → error (doc 10, lines 305-333).
Circuit breaker with configurable `CircuitBreakerConfig(failure_threshold=3, probe_interval=30)`.

**Test**: Tier 1 — test abstract contract, state transitions, circuit breaker logic.

---

## TODO-02: Build source config types

**Layer**: 3 (configuration)
**File**: `packages/kailash-dataflow/src/dataflow/fabric/config.py`

Implement typed config dataclasses (doc 08, doc 13):

- `BaseSourceConfig` — base with `validate()` method (checks env vars, URL format)
- `RestSourceConfig(url, auth, poll_interval, endpoints, webhook, circuit_breaker, timeout)`
- `FileSourceConfig(path, watch, parser)`
- `CloudSourceConfig(bucket, provider, prefix, poll_interval)`
- `DatabaseSourceConfig(url, tables, read_only, poll_interval)`
- `StreamSourceConfig(broker, topic, group_id)`
- `StalenessPolicy(max_age, on_stale, on_source_error)`
- `CircuitBreakerConfig(failure_threshold, probe_interval)`
- `RateLimit(max_requests, max_unique_params)`
- `WebhookConfig(path, secret_env, events)`

Auth types (doc 08, lines 43-48):
- `BearerAuth(token_env)` — reads env var per-request (doc 04, Resolution 8)
- `ApiKeyAuth(key_env, header)`
- `OAuth2Auth(client_id_env, client_secret_env, token_url)` — auto-refresh lifecycle
- `BasicAuth(username_env, password_env)`

Eager validation: env vars checked at construction, URL format validated, required fields enforced.

**Test**: Tier 1 — validate config construction, env var checking, error messages.

---

## TODO-03: Build RestSourceAdapter

**Layer**: 2 (adapters)
**File**: `packages/kailash-dataflow/src/dataflow/adapters/rest_adapter.py`

Implement `RestSourceAdapter(BaseSourceAdapter)`:

- `connect()` — create `httpx.AsyncClient` with auth, base URL, timeouts
- `disconnect()` — close client
- `health_check()` — HEAD request to base URL
- `detect_change()` — conditional GET with `If-None-Match`/`If-Modified-Since` → 304 = no change. Auto-detect conditional support on first request (doc runtime-redteam RT-5). Content-hash fallback for APIs without ETag.
- `fetch(path, params)` — `GET {base_url}/{path}` → parse JSON
- `fetch_all(path, page_size, max_records)` — auto-paginate (follow `next` links, increment offset). Memory guard: raise if exceeds `max_records`.
- `fetch_pages(path, page_size)` — async iterator yielding pages
- `write(path, data)` — `POST {base_url}/{path}` with JSON body
- Auth handling: BearerAuth (token from env per-request), ApiKeyAuth (header), OAuth2Auth (auto-refresh), BasicAuth

SSRF protection (doc 01-redteam H4): validate URLs against private IP ranges, path normalization.

**Test**: Tier 2 — test against real httpbin.org or local test HTTP server. ETag detection, pagination, auth, circuit breaker. No mocking.

---

## TODO-04: Build FileSourceAdapter

**Layer**: 2 (adapters)
**File**: `packages/kailash-dataflow/src/dataflow/adapters/file_adapter.py`

Implement `FileSourceAdapter(BaseSourceAdapter)`:

- `connect()` — verify path exists, start watchdog observer if `watch=True`
- `disconnect()` — stop watchdog observer
- `health_check()` — `os.path.exists(path)` + readable
- `detect_change()` — `os.stat(path).st_mtime` comparison (sub-ms)
- `fetch()` — read file, auto-parse based on extension (.json → json.load, .yaml → yaml.safe_load, .csv → csv.DictReader, .xlsx → openpyxl)
- `write(path, data)` — write file

Watchdog integration (doc runtime-redteam RT-7): thread-to-async bridge via `asyncio.run_coroutine_threadsafe()`. Pass event loop reference to adapter.

File path security (doc 01-redteam M4): resolve to absolute path, reject `..`, validate within allowed directory.

**Test**: Tier 2 — test with real temp files (.json, .yaml, .csv). Watchdog change detection. No mocking.

---

## TODO-05: Build CloudSourceAdapter

**Layer**: 2 (adapters)
**File**: `packages/kailash-dataflow/src/dataflow/adapters/cloud_adapter.py`

Implement `CloudSourceAdapter(BaseSourceAdapter)`:

- `connect()` — create cloud client (boto3 for S3, gcs for GCS). Lazy import.
- `detect_change()` — `ListObjectsV2` (S3) / `list_blobs` (GCS) metadata comparison (LastModified, ETag)
- `fetch(path)` — `GetObject` → parse content
- `list(prefix, limit)` — list objects with prefix
- `write(path, data)` — `PutObject`

Provider abstraction: `provider` field selects S3/GCS/Azure. Each provider has its own client initialization and API calls, abstracted behind the common `BaseSourceAdapter` interface.

**Test**: Tier 2 — test against localstack (S3 emulator) or real S3 bucket. No mocking.

---

## TODO-06: Build DatabaseSourceAdapter

**Layer**: 2 (adapters)
**File**: `packages/kailash-dataflow/src/dataflow/adapters/database_source_adapter.py`

Implement `DatabaseSourceAdapter(BaseSourceAdapter)`:

- `connect()` — create connection pool via existing DataFlow `DatabaseAdapter`
- `detect_change()` — three strategies in order (doc 02-competitor-refinements):
  1. Change counter table (`_fabric_changes`) if available
  2. `MAX(updated_at)` if table has `updated_at` column
  3. `COUNT(*)` as fallback
- `fetch(path)` — `SELECT * FROM {path}` (path = table name). Validate identifier per `infrastructure-sql.md`.
- `list()` — list available tables
- `write()` — INSERT/UPDATE via parameterized queries (if not `read_only`)

Reuses existing DataFlow adapter infrastructure — NOT a reimplementation.

**Test**: Tier 2 — test against real SQLite in-memory database.

---

## TODO-07: Build StreamSourceAdapter

**Layer**: 2 (adapters)
**File**: `packages/kailash-dataflow/src/dataflow/adapters/stream_adapter.py`

Implement `StreamSourceAdapter(BaseSourceAdapter)`:

- `connect()` — create Kafka consumer / WebSocket connection. Lazy import.
- `detect_change()` — always True (stream is continuous)
- `fetch()` — consume batch of messages from topic
- `write()` — produce messages to topic

Consumer group management, offset tracking.

**Test**: Tier 2 — test with in-memory mock broker or local Kafka if available.

---

## TODO-08: Wire source registration into DataFlow core

**Layer**: 6 (core engine)
**Files**: `packages/kailash-dataflow/src/dataflow/core/engine.py`, `packages/kailash-dataflow/src/dataflow/fabric/__init__.py`

Add to `DataFlow.__init__`:
```python
self._sources: Dict[str, SourceRegistration] = {}
self._products: Dict[str, ProductRegistration] = {}
self._fabric: Optional[FabricRuntime] = None
```

Add `DataFlow.source(name, config)` method (doc 10, lines 38-70):
- Validate name uniqueness across models AND sources
- Validate config (env vars, URL format)
- Store in `self._sources`

Verify: existing `@db.model` code works unchanged (backward compatibility).

**Test**: Tier 1 — test source registration, name conflicts with models, config validation errors. Tier 2 — test alongside real `@db.model` usage.
