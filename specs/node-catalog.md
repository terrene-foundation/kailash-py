# Kailash SDK Node Catalog

Authoritative catalog of every node class in the Kailash Python SDK. Generated from source inspection of `src/kailash/nodes/`.

## Summary

| Category                            | Node Count | Description                                            |
| ----------------------------------- | ---------- | ------------------------------------------------------ |
| [Data](#data-30-nodes)              | 30         | File I/O, SQL, Redis, vector DB, streaming, retrieval  |
| [Edge](#edge-14-nodes)              | 14         | Edge computing, cloud, containers, resource management |
| [Monitoring](#monitoring-10-nodes)  | 10         | Health checks, metrics, anomaly detection, dashboards  |
| [Logic](#logic-10-nodes)            | 10         | Control flow, branching, merging, loops, convergence   |
| [API](#api-10-nodes)                | 10         | HTTP, REST, GraphQL, auth, rate limiting               |
| [Security](#security-7-nodes)       | 7          | Audit, credentials, threat detection, ABAC             |
| [Admin](#admin-5-nodes)             | 5          | User/role management, permissions, audit logging       |
| [Auth](#auth-6-nodes)               | 6          | SSO, MFA, session management, directory integration    |
| [Enterprise](#enterprise-6-nodes)   | 6          | Audit logging, batch processing, data lineage, MCP     |
| [Transaction](#transaction-5-nodes) | 5          | Saga, 2PC, distributed transactions                    |
| [Transform](#transform-8-nodes)     | 8          | Filtering, mapping, chunking, formatting               |
| [Cache](#cache-3-nodes)             | 3          | Caching, invalidation, Redis pool management           |
| [Code](#code-2-nodes)               | 2          | Python and async Python code execution                 |
| [Compliance](#compliance-2-nodes)   | 2          | GDPR, data retention                                   |
| [Validation](#validation-3-nodes)   | 3          | Code validation, workflow validation, test execution   |
| [System](#system-3-nodes)           | 3          | Command parsing, interactive shell, command routing    |
| [Testing](#testing-1-node)          | 1          | Credential testing                                     |
| [Alerts](#alerts-2-nodes)           | 2          | Alert dispatch, Discord notifications                  |
| [Governance](#governance-3-nodes)   | 3          | Secure governed base, enterprise, development nodes    |
| [Handler](#handler-1-node)          | 1          | Nexus request handler                                  |
| [Base / Mixins](#base--mixins)      | 7          | Base classes and mixins (not directly instantiated)    |
| **Total**                           | **138**    |                                                        |

---

## Data (30 nodes)

### CSVReaderNode

- **Purpose:** Reads tabular data from CSV files with automatic header detection and type inference.
- **Key Parameters:** `file_path` (str, required), `delimiter` (str, default `","`), `encoding` (str, default `"utf-8"`), `has_header` (bool, default `True`)
- **Outputs:** `{"data": list[dict|list], "headers": list, "row_count": int}`
- **Notes:** Handles both dict and list data structures; uses Python's `csv` module.

### JSONReaderNode

- **Purpose:** Reads structured data from JSON files with support for nested structures.
- **Key Parameters:** `file_path` (str, required), `encoding` (str, default `"utf-8"`)
- **Outputs:** `{"data": Any}` — preserves original JSON structure
- **Notes:** Handles arrays, objects, and nested JSON.

### TextReaderNode

- **Purpose:** Reads raw text content from files.
- **Key Parameters:** `file_path` (str, required), `encoding` (str, default `"utf-8"`)
- **Outputs:** `{"text": str, "lines": list[str], "char_count": int}`
- **Notes:** Supports multiple encodings.

### DocumentProcessorNode

- **Purpose:** Processes documents across multiple formats (PDF, DOCX, HTML, etc.) with content extraction.
- **Key Parameters:** `file_path` (str, required), `extract_metadata` (bool), `extract_images` (bool)
- **Outputs:** `{"content": str, "metadata": dict, "pages": int}`
- **Notes:** Handles various document formats with format-specific extraction.

### CSVWriterNode

- **Purpose:** Writes structured data to CSV files.
- **Key Parameters:** `file_path` (str, required), `data` (list), `headers` (bool), `delimiter` (str, default `","`)
- **Outputs:** `{"rows_written": int, "file_path": str}`
- **Notes:** Auto-detects dict vs list data format; validates file paths for security.

### JSONWriterNode

- **Purpose:** Writes JSON-serializable data to files with pretty printing.
- **Key Parameters:** `file_path` (str, required), `data` (Any), `indent` (int, default `2`)
- **Outputs:** `{"file_path": str}`
- **Notes:** Preserves Unicode characters; validates file paths.

### TextWriterNode

- **Purpose:** Writes text content to files with append support.
- **Key Parameters:** `file_path` (str, required), `text` (str, required), `encoding` (str, default `"utf-8"`), `append` (bool, default `False`)
- **Outputs:** `{"file_path": str, "bytes_written": int}`
- **Notes:** Supports both overwrite and append modes.

### SQLDatabaseNode

- **Purpose:** Synchronous SQL database operations with SQLAlchemy connection management.
- **Key Parameters:** `connection_string` (str), `database_type` (str), `query` (str), `params` (dict), `operation` (str)
- **Outputs:** `{"result": list[dict], "row_count": int}`
- **Notes:** Supports PostgreSQL, MySQL, SQLite; includes connection pooling and project config integration.

### AsyncSQLDatabaseNode

- **Purpose:** Asynchronous SQL database operations with connection pooling and retry logic.
- **Key Parameters:** `connection_string` (str), `database_type` (str), `query` (str), `params` (dict), `fetch_mode` (str), `timeout` (int)
- **Outputs:** `{"result": list[dict]|dict|int}`
- **Notes:** Supports asyncpg (PostgreSQL), aiomysql (MySQL), aiosqlite (SQLite); includes optimistic locking integration.

### RedisNode

- **Purpose:** Performs Redis operations including strings, hashes, lists, sets, and sorted sets.
- **Key Parameters:** `host` (str), `port` (int), `db` (int), `operation` (str, required), `key` (str), `value` (Any), `field` (str), `ttl` (int)
- **Outputs:** `{"result": Any, "success": bool}`
- **Notes:** Supports get/set, hget/hset/hgetall, lpush/rpush/lrange, sadd/smembers, zadd/zrange, exists, ping.

### EmbeddingNode

- **Purpose:** Generates text embeddings using multiple providers (OpenAI, HuggingFace, Cohere).
- **Key Parameters:** `model` (str, required), `model_name` (str, required), `api_key` (str), `batch_size` (int, default `100`), `normalize` (bool, default `True`)
- **Outputs:** `{"embeddings": list[list[float]], "model_info": dict, "count": int}`
- **Notes:** Handles batching and normalization automatically.

### VectorDatabaseNode

- **Purpose:** Unified interface for vector databases (Pinecone, Weaviate, Milvus, Qdrant, Chroma).
- **Key Parameters:** `provider` (str, required), `index_name` (str, required), `dimension` (int, required), `metric` (str, default `"cosine"`)
- **Outputs:** Operation-dependent: upsert status, query results with scores, deletion counts
- **Notes:** Supports upsert, query, delete, and fetch operations.

### TextSplitterNode

- **Purpose:** Splits text into chunks for embedding generation with multiple strategies.
- **Key Parameters:** `strategy` (str, default `"recursive"`), `chunk_size` (int, default `1000`), `chunk_overlap` (int, default `200`), `preserve_sentences` (bool, default `True`)
- **Outputs:** `{"chunks": list[str], "chunk_metadata": list[dict], "total_chunks": int}`
- **Notes:** Strategies: recursive, character, sentence, token.

### AsyncPostgreSQLVectorNode

- **Purpose:** High-performance PostgreSQL pgvector operations for AI/ML workflows.
- **Key Parameters:** `connection_string` (str), `table_name` (str, required), `operation` (str, required), `vector` (list), `dimension` (int), `distance_metric` (str), `index_type` (str)
- **Outputs:** Operation-dependent: search matches, insert counts, table/index creation status
- **Notes:** Supports HNSW and IVFFlat indexes; L2, cosine, and inner product distance metrics.

### KafkaConsumerNode

- **Purpose:** Consumes messages from Apache Kafka topics with consumer group support.
- **Key Parameters:** `bootstrap_servers` (str, required), `topic` (str, required), `group_id` (str, required), `auto_offset_reset` (str, default `"latest"`), `max_poll_records` (int, default `500`)
- **Outputs:** `{"messages": list[dict], "metadata": dict}`
- **Notes:** Supports offset management, deserialization, and SSL/SASL authentication.

### StreamPublisherNode

- **Purpose:** Publishes messages to streaming platforms (Kafka, RabbitMQ, WebSockets, SSE).
- **Key Parameters:** `protocol` (str, required), `endpoint` (str, required), `topic` (str, required), `batch_size` (int, default `100`), `compression` (str), `retry_count` (int, default `3`)
- **Outputs:** `{"published_count": int, "failed_messages": list, "metadata": dict}`
- **Notes:** Multi-protocol support with batching and retry logic.

### WebSocketNode

- **Purpose:** Bidirectional WebSocket client for real-time streaming communication.
- **Key Parameters:** `url` (str, required), `headers` (dict), `reconnect` (bool, default `True`), `ping_interval` (int, default `30`), `ssl_verify` (bool, default `True`)
- **Outputs:** Action-dependent: connection status, sent confirmation, received messages
- **Notes:** Actions: connect, send, receive, disconnect. Auto-reconnection support.

### EventStreamNode

- **Purpose:** Server-sent events (SSE) client for unidirectional real-time streaming.
- **Key Parameters:** `url` (str, required), `headers` (dict), `event_types` (list), `reconnect_time` (int, default `3000`), `timeout` (int, default `60`)
- **Outputs:** `{"events": list[dict], "status": str, "metadata": dict}`
- **Notes:** Supports event type filtering and Last-Event-ID tracking.

### DocumentSourceNode

- **Purpose:** Provides sample documents for hierarchical RAG processing demonstrations.
- **Key Parameters:** `sample_documents` (bool, default `True`)
- **Outputs:** `{"documents": list[dict]}`
- **Notes:** Built-in ML/NLP sample documents for testing pipelines.

### QuerySourceNode

- **Purpose:** Provides sample queries for RAG processing workflows.
- **Key Parameters:** `query` (str, default `"What are the main types of machine learning?"`)
- **Outputs:** `{"query": str}`
- **Notes:** Simple query injection point for RAG pipelines.

### RelevanceScorerNode

- **Purpose:** Scores document chunk relevance using similarity methods (cosine, BM25, TF-IDF).
- **Key Parameters:** `chunks` (list), `query_embedding` (list), `chunk_embeddings` (list), `similarity_method` (str, default `"cosine"`), `top_k` (int, default `3`)
- **Outputs:** `{"relevant_chunks": list[dict]}`
- **Notes:** Falls back to text matching when embeddings are unavailable; supports multiple embedding formats.

### HybridRetrieverNode

- **Purpose:** Combines dense and sparse retrieval using fusion strategies (RRF, linear, weighted).
- **Key Parameters:** `query` (str, required), `dense_results` (list, required), `sparse_results` (list, required), `fusion_strategy` (str, default `"rrf"`), `dense_weight` (float, default `0.6`), `top_k` (int, default `5`)
- **Outputs:** `{"hybrid_results": list[dict], "fusion_method": str, "fused_count": int}`
- **Notes:** RRF typically yields 20-30% better results than single methods.

### DirectoryReaderNode

- **Purpose:** Discovers and catalogs files in directories with metadata extraction.
- **Key Parameters:** `directory_path` (str, required), `recursive` (bool, default `False`), `file_patterns` (list), `exclude_patterns` (list), `include_hidden` (bool, default `False`)
- **Outputs:** `{"discovered_files": list[dict], "files_by_type": dict, "directory_stats": dict}`
- **Notes:** Extracts size, timestamps, MIME types; validates paths for security.

### FileDiscoveryNode

- **Purpose:** Advanced file discovery with filtering by size, date, patterns, and checksum calculation.
- **Key Parameters:** `search_paths` (list, required), `file_patterns` (list), `max_depth` (int, default `10`), `include_checksums` (bool), `min_size_mb` (float), `older_than_days` (int)
- **Outputs:** `{"discovered_files": list[dict], "discovery_summary": dict, "total_files": int}`
- **Notes:** Calculates MD5/SHA256 checksums; handles symlinks and permission errors gracefully.

### EventGeneratorNode

- **Purpose:** Generates realistic event streams for event-driven architecture testing.
- **Key Parameters:** `event_types` (list, required), `event_count` (int, default `10`), `aggregate_prefix` (str, default `"AGG"`), `custom_data_templates` (dict), `seed` (int)
- **Outputs:** `{"events": list[dict], "metadata": dict, "event_count": int}`
- **Notes:** Built-in generators for order, payment, shipping, and user events; deterministic with seed.

### OptimisticLockingNode

- **Purpose:** Version-based concurrency control with conflict detection and automatic retry.
- **Key Parameters:** `version_field` (str, default `"version"`), `max_retries` (int, default `3`), `retry_delay` (float, default `0.1`), `default_conflict_resolution` (ConflictResolution enum)
- **Outputs:** Action-dependent: version info, update status, lock metrics
- **Notes:** Strategies: fail_fast, retry, merge, last_writer_wins.

### BulkCreateNode

- **Purpose:** Optimized bulk insert operations with chunking and progress tracking.
- **Key Parameters:** `records` (list, required), `table_name` (str, required), `columns` (list), `chunk_size` (int, default `1000`), `error_strategy` (str)
- **Outputs:** `BulkOperationResult` with total/successful/failed counts
- **Notes:** Extends AsyncSQLDatabaseNode; strategies: fail_fast, continue, rollback.

### BulkUpdateNode

- **Purpose:** Bulk update operations with database-specific optimizations.
- **Key Parameters:** `records` (list, required), `table_name` (str, required), `key_columns` (list, required), `update_columns` (list), `chunk_size` (int, default `1000`)
- **Outputs:** `BulkOperationResult` with update counts
- **Notes:** Extends AsyncSQLDatabaseNode with BulkOperationMixin.

### BulkDeleteNode

- **Purpose:** Bulk delete operations with configurable error handling.
- **Key Parameters:** `record_ids` (list, required), `table_name` (str, required), `id_column` (str), `chunk_size` (int, default `1000`)
- **Outputs:** `BulkOperationResult` with deletion counts
- **Notes:** Extends AsyncSQLDatabaseNode with BulkOperationMixin.

### BulkUpsertNode

- **Purpose:** Bulk upsert (insert-or-update) operations.
- **Key Parameters:** `records` (list, required), `table_name` (str, required), `key_columns` (list, required), `update_columns` (list), `chunk_size` (int, default `1000`)
- **Outputs:** `BulkOperationResult` with upsert counts
- **Notes:** Extends AsyncSQLDatabaseNode with BulkOperationMixin.

### QueryPipelineNode

- **Purpose:** Batches multiple queries together to reduce round-trip latency.
- **Key Parameters:** `connection_pool` (str, required), `batch_size` (int, default `100`), `flush_interval` (float, default `0.1`), `strategy` (str: sequential/parallel/transactional/best_effort)
- **Outputs:** Batched query results
- **Notes:** Handles partial failures gracefully; optimizes throughput.

### QueryRouterNode

- **Purpose:** Intelligent query routing for optimal database performance based on query analysis.
- **Key Parameters:** `connection_pool` (str, required), `enable_read_write_split` (bool, default `True`), `cache_size` (int, default `1000`), `pattern_learning` (bool, default `True`)
- **Outputs:** Routed query results with performance metadata
- **Notes:** Async node; routes to replicas for reads, primary for writes.

### SharePointGraphReader

- **Purpose:** Reads files from SharePoint using Microsoft Graph API with MSAL authentication.
- **Key Parameters:** `auth_method` (str, default `"client_credentials"`), `tenant_id` (str), `client_id` (str), `client_secret` (str), `site_url` (str), `drive_path` (str)
- **Outputs:** `{"files": list[dict], "content": bytes}`
- **Notes:** Supports client_credentials, certificate, username_password, managed_identity, device_code auth.

### SharePointGraphWriter

- **Purpose:** Uploads files to SharePoint document libraries using Microsoft Graph API.
- **Key Parameters:** `tenant_id` (str), `client_id` (str), `client_secret` (str), `site_url` (str), `local_path` (str), `remote_folder` (str)
- **Outputs:** Upload status and metadata
- **Notes:** Supports folder structures and metadata.

### WorkflowConnectionPool

- **Purpose:** Workflow-scoped connection pool with health monitoring and lifecycle management.
- **Key Parameters:** `database_type` (str, required), `connection_string` (str), `host` (str), `port` (int), `min_connections` (int), `max_connections` (int)
- **Outputs:** Connection pool status and health metrics
- **Notes:** Async node; connections scoped to workflow lifecycle with production-grade features.

---

## Edge (14 nodes)

### EdgeNode (base)

- **Purpose:** Base edge-aware node with location awareness and compliance routing.
- **Key Parameters:** `location` (str), `compliance_zone` (str), `edge_id` (str)
- **Outputs:** Location-aware execution results
- **Notes:** Abstract base for all edge nodes; extends AsyncNode.

### CloudNode

- **Purpose:** Cloud integration for edge resource management across providers.
- **Key Parameters:** `provider` (str), `region` (str), `resource_type` (str), `operation` (str)
- **Outputs:** Cloud resource operation results
- **Notes:** Multi-cloud support for resource lifecycle management.

### EdgeCoordinationNode

- **Purpose:** Distributed consensus operations across edge nodes.
- **Key Parameters:** `consensus_algorithm` (str), `quorum_size` (int), `timeout` (float)
- **Outputs:** Consensus results and coordination status
- **Notes:** Handles leader election, distributed locking, and coordination.

### DockerNode

- **Purpose:** Docker container management for edge deployments.
- **Key Parameters:** `image` (str), `command` (str), `operation` (str), `container_name` (str)
- **Outputs:** Container operation results
- **Notes:** Supports container lifecycle operations at the edge.

### EdgeDataNode

- **Purpose:** Distributed data management with consistency guarantees across edge locations.
- **Key Parameters:** `consistency_level` (str), `replication_factor` (int), `data_key` (str)
- **Outputs:** Data operation results with consistency metadata
- **Notes:** Extends EdgeNode with data distribution capabilities.

### EdgeMigrationNode

- **Purpose:** Live workload migration between edge nodes with zero-downtime guarantees.
- **Key Parameters:** `source_node` (str), `target_node` (str), `migration_strategy` (str), `validate_after` (bool)
- **Outputs:** Migration status and validation results
- **Notes:** Enables zero-downtime migration of workloads and data.

### EdgeMonitoringNode

- **Purpose:** Comprehensive edge observability with metrics, health monitoring, and alerting.
- **Key Parameters:** `metrics_interval` (int), `health_check_interval` (int), `alert_thresholds` (dict)
- **Outputs:** Monitoring metrics, health status, alerts
- **Notes:** Provides analytics and anomaly detection for edge infrastructure.

### EdgeStateMachine

- **Purpose:** Distributed stateful operations with state persistence across edge nodes.
- **Key Parameters:** `initial_state` (str), `transitions` (dict), `persistence_backend` (str)
- **Outputs:** State transition results
- **Notes:** Extends EdgeNode with state machine capabilities.

### EdgeWarmingNode

- **Purpose:** Predictive edge node preparation based on usage patterns.
- **Key Parameters:** `prediction_model` (str), `warm_threshold` (float), `target_nodes` (list)
- **Outputs:** Warming status and prediction metrics
- **Notes:** ML-based pre-warming of edge nodes for low-latency responses.

### KubernetesNode

- **Purpose:** Kubernetes cluster management for edge resource orchestration.
- **Key Parameters:** `cluster` (str), `namespace` (str), `resource_type` (str), `operation` (str)
- **Outputs:** Kubernetes operation results
- **Notes:** Supports pods, deployments, services, and other K8s resources.

### PlatformNode

- **Purpose:** Unified platform integration across multiple infrastructure providers.
- **Key Parameters:** `platform` (str), `operation` (str), `config` (dict)
- **Outputs:** Platform operation results
- **Notes:** Abstracts differences between cloud, on-prem, and edge platforms.

### ResourceAnalyzerNode

- **Purpose:** Intelligent resource usage analysis with bottleneck detection.
- **Key Parameters:** `analysis_window` (int), `resource_types` (list), `threshold_config` (dict)
- **Outputs:** Resource analysis report with recommendations
- **Notes:** Provides insights into CPU, memory, network, and storage patterns.

### ResourceOptimizerNode

- **Purpose:** Multi-cloud cost optimization with resource right-sizing recommendations.
- **Key Parameters:** `optimization_target` (str), `budget_constraint` (float), `provider_preferences` (list)
- **Outputs:** Optimization recommendations and projected savings
- **Notes:** Analyzes spending patterns and recommends cost-effective configurations.

### ResourceScalerNode

- **Purpose:** Predictive edge resource scaling using ML-based demand prediction.
- **Key Parameters:** `scaling_policy` (str), `min_instances` (int), `max_instances` (int), `prediction_horizon` (int)
- **Outputs:** Scaling decisions and prediction accuracy metrics
- **Notes:** Proactive scaling based on historical patterns and demand forecasts.

---

## Monitoring (10 nodes)

### ConnectionDashboardNode

- **Purpose:** Real-time monitoring dashboard for database connection pools.
- **Key Parameters:** `pool_name` (str), `refresh_interval` (int), `metrics_history_size` (int)
- **Outputs:** Dashboard data with pool health, active/idle connections, wait times
- **Notes:** Provides visual connection pool monitoring data.

### DeadlockDetectorNode

- **Purpose:** Detects and resolves database deadlocks with automatic resolution strategies.
- **Key Parameters:** `detection_interval` (float), `resolution_strategy` (str), `max_wait_time` (float)
- **Outputs:** Deadlock detection results and resolution actions taken
- **Notes:** Async node; supports multiple resolution strategies.

### HealthCheckNode

- **Purpose:** Monitors service and dependency availability with configurable probes.
- **Key Parameters:** `targets` (list), `check_interval` (int), `timeout` (float), `failure_threshold` (int)
- **Outputs:** Health status per target with latency and error details
- **Notes:** Async node; supports HTTP, TCP, and custom health probes.

### LogProcessorNode

- **Purpose:** Comprehensive log analysis, aggregation, and pattern detection.
- **Key Parameters:** `log_sources` (list), `parse_format` (str), `filter_level` (str), `aggregation_window` (int)
- **Outputs:** Processed log entries with patterns and anomalies
- **Notes:** Async node; handles structured and unstructured logs.

### MetricsCollectorNode

- **Purpose:** Collects system and application metrics for monitoring dashboards.
- **Key Parameters:** `collection_interval` (int), `metric_types` (list), `exporters` (list)
- **Outputs:** Collected metrics with timestamps and labels
- **Notes:** Async node; integrates with Prometheus-compatible metric formats.

### PerformanceAnomalyNode

- **Purpose:** Detects performance anomalies using baseline learning and statistical analysis.
- **Key Parameters:** `baseline_window` (int), `sensitivity` (float), `anomaly_types` (list), `alert_threshold` (float)
- **Outputs:** Anomaly reports with severity, baseline comparisons, and root cause hints
- **Notes:** Async node; learns normal behavior and flags deviations.

### PerformanceBenchmarkNode

- **Purpose:** Runs performance benchmarks with statistical analysis and reporting.
- **Key Parameters:** `benchmark_name` (str), `iterations` (int), `warmup_iterations` (int), `target_metrics` (list)
- **Outputs:** Benchmark results with p50/p95/p99 latencies, throughput, and comparisons
- **Notes:** Uses SecurityMixin, PerformanceMixin, and LoggingMixin.

### RaceConditionDetectorNode

- **Purpose:** Detects and analyzes race conditions in concurrent operations.
- **Key Parameters:** `detection_mode` (str), `thread_count` (int), `operation_timeout` (float)
- **Outputs:** Race condition reports with reproduction steps and fix suggestions
- **Notes:** Async node; uses concurrent execution to surface timing-dependent bugs.

### TransactionMetricsNode

- **Purpose:** Collects and analyzes transaction-level performance metrics.
- **Key Parameters:** `transaction_types` (list), `collection_interval` (int), `histogram_buckets` (list)
- **Outputs:** Transaction metrics with latency distributions and error rates
- **Notes:** Async node; provides per-operation breakdowns.

### TransactionMonitorNode

- **Purpose:** Real-time transaction monitoring with distributed tracing support.
- **Key Parameters:** `trace_sampling_rate` (float), `slow_threshold_ms` (int), `alert_on_error` (bool)
- **Outputs:** Transaction traces with timing, status, and dependency graphs
- **Notes:** Async node; supports distributed tracing correlation.

---

## Logic (10 nodes)

### SwitchNode

- **Purpose:** Conditional branching based on input data evaluation.
- **Key Parameters:** `conditions` (dict, required), `default_output` (str)
- **Outputs:** Routes data to the matching branch output
- **Notes:** Evaluates conditions in order; first match wins.

### MergeNode

- **Purpose:** Merges data from multiple upstream branches into a single output.
- **Key Parameters:** `merge_strategy` (str), `wait_for_all` (bool)
- **Outputs:** Merged data from all or selected inputs
- **Notes:** Strategies include concat, deep merge, and first-available.

### AsyncSwitchNode

- **Purpose:** Asynchronous conditional branching for non-blocking workflows.
- **Key Parameters:** `conditions` (dict, required), `default_output` (str)
- **Outputs:** Routes data asynchronously to matching branch
- **Notes:** Async version of SwitchNode for concurrent workflows.

### AsyncMergeNode

- **Purpose:** Asynchronous merge of data from multiple concurrent branches.
- **Key Parameters:** `merge_strategy` (str), `timeout` (float)
- **Outputs:** Merged data from async branches
- **Notes:** Async version of MergeNode with timeout support.

### IntelligentMergeNode

- **Purpose:** AI-assisted data merging with conflict resolution across branches.
- **Key Parameters:** `merge_strategy` (str), `conflict_resolution` (str), `priority_order` (list)
- **Outputs:** Intelligently merged data with conflict resolution report
- **Notes:** Handles complex merge scenarios with configurable priorities.

### LoopNode

- **Purpose:** Iterates over data collections executing sub-workflows per item.
- **Key Parameters:** `items` (list), `max_iterations` (int), `break_condition` (str)
- **Outputs:** Aggregated results from all loop iterations
- **Notes:** Supports break conditions and iteration limits.

### ConvergenceCheckerNode

- **Purpose:** Checks whether cyclic workflow iterations have converged to a stable state.
- **Key Parameters:** `convergence_threshold` (float), `max_iterations` (int), `metric_field` (str)
- **Outputs:** `{"converged": bool, "iterations": int, "final_metric": float}`
- **Notes:** Extends CycleAwareNode; used in iterative optimization workflows.

### MultiCriteriaConvergenceNode

- **Purpose:** Multi-metric convergence checking for complex iterative workflows.
- **Key Parameters:** `criteria` (list[dict]), `require_all` (bool), `max_iterations` (int)
- **Outputs:** Per-criterion convergence status and overall convergence decision
- **Notes:** Extends CycleAwareNode; supports AND/OR convergence logic.

### SignalWaitNode

- **Purpose:** Pauses workflow execution until an external signal is received.
- **Key Parameters:** `signal_name` (str, required), `timeout` (float), `default_value` (Any)
- **Outputs:** Signal payload or default value on timeout
- **Notes:** Enables event-driven workflow orchestration.

### WorkflowNode

- **Purpose:** Embeds a sub-workflow within a parent workflow as a single node.
- **Key Parameters:** `workflow` (WorkflowBuilder), `input_mapping` (dict), `output_mapping` (dict)
- **Outputs:** Sub-workflow outputs mapped to parent namespace
- **Notes:** Enables workflow composition and reuse.

---

## API (10 nodes)

### HTTPRequestNode

- **Purpose:** Synchronous HTTP requests with configurable method, headers, and body.
- **Key Parameters:** `url` (str, required), `method` (str, default `"GET"`), `headers` (dict), `body` (Any), `timeout` (int)
- **Outputs:** `{"status_code": int, "headers": dict, "body": Any}`
- **Notes:** Supports all HTTP methods; handles JSON and form data.

### AsyncHTTPRequestNode

- **Purpose:** Asynchronous HTTP requests for concurrent API calls.
- **Key Parameters:** `url` (str, required), `method` (str), `headers` (dict), `body` (Any), `timeout` (int)
- **Outputs:** `{"status_code": int, "headers": dict, "body": Any}`
- **Notes:** Async version of HTTPRequestNode; uses aiohttp.

### RESTClientNode

- **Purpose:** Full-featured REST API client with CRUD convenience methods.
- **Key Parameters:** `base_url` (str, required), `auth` (dict), `default_headers` (dict), `retry_config` (dict)
- **Outputs:** REST response with parsed body and status
- **Notes:** Built-in retry logic, pagination support, and error handling.

### AsyncRESTClientNode

- **Purpose:** Asynchronous REST client for high-throughput API consumption.
- **Key Parameters:** `base_url` (str, required), `auth` (dict), `concurrency_limit` (int)
- **Outputs:** REST response with parsed body and status
- **Notes:** Async version with connection pooling and concurrency control.

### GraphQLClientNode

- **Purpose:** Synchronous GraphQL query and mutation execution.
- **Key Parameters:** `endpoint` (str, required), `query` (str, required), `variables` (dict), `headers` (dict)
- **Outputs:** `{"data": dict, "errors": list|None}`
- **Notes:** Supports queries, mutations, and variable interpolation.

### AsyncGraphQLClientNode

- **Purpose:** Asynchronous GraphQL operations with subscription support.
- **Key Parameters:** `endpoint` (str, required), `query` (str, required), `variables` (dict)
- **Outputs:** `{"data": dict, "errors": list|None}`
- **Notes:** Async version with subscription support.

### BasicAuthNode

- **Purpose:** HTTP Basic Authentication header generation.
- **Key Parameters:** `username` (str, required), `password` (str, required)
- **Outputs:** `{"auth_header": str}` — Base64-encoded credentials
- **Notes:** Generates Authorization header for downstream HTTP nodes.

### OAuth2Node

- **Purpose:** OAuth2 authentication flow management (client credentials, authorization code).
- **Key Parameters:** `client_id` (str, required), `client_secret` (str), `token_url` (str, required), `grant_type` (str), `scopes` (list)
- **Outputs:** `{"access_token": str, "token_type": str, "expires_in": int}`
- **Notes:** Handles token refresh and multiple grant types.

### APIKeyNode

- **Purpose:** API key authentication header generation.
- **Key Parameters:** `api_key` (str, required), `header_name` (str), `prefix` (str)
- **Outputs:** Authentication header with configured API key
- **Notes:** Supports custom header names and key prefixes.

### RateLimitedAPINode

- **Purpose:** API requests with built-in rate limiting and backoff.
- **Key Parameters:** `url` (str), `rate_limit` (int), `rate_window` (int), `retry_on_429` (bool)
- **Outputs:** API response with rate limit metadata
- **Notes:** Token bucket algorithm; respects Retry-After headers.

### AsyncRateLimitedAPINode

- **Purpose:** Async API requests with rate limiting for concurrent workloads.
- **Key Parameters:** `url` (str), `rate_limit` (int), `rate_window` (int), `max_concurrent` (int)
- **Outputs:** API response with rate limit metadata
- **Notes:** Async version with semaphore-based concurrency control.

### APIHealthCheckNode

- **Purpose:** Monitors API endpoint availability and response quality.
- **Key Parameters:** `endpoints` (list), `check_interval` (int), `expected_status` (int)
- **Outputs:** Health status per endpoint with latency and error details
- **Notes:** Validates response codes and optional body assertions.

### SecurityScannerNode

- **Purpose:** Scans API endpoints for common security vulnerabilities.
- **Key Parameters:** `target_url` (str), `scan_types` (list), `auth_config` (dict)
- **Outputs:** Security findings with severity ratings and remediation guidance
- **Notes:** Checks headers, CORS, authentication, and common OWASP issues.

---

## Security (7 nodes)

### AuditLogNode

- **Purpose:** Records security-relevant events for compliance and forensics.
- **Key Parameters:** `event_type` (str, required), `actor` (str), `resource` (str), `action` (str), `outcome` (str)
- **Outputs:** `{"audit_id": str, "timestamp": str, "logged": bool}`
- **Notes:** Immutable audit trail for security events.

### SecurityEventNode

- **Purpose:** Processes and classifies security events for incident response.
- **Key Parameters:** `event_data` (dict, required), `severity_threshold` (str), `classification_rules` (dict)
- **Outputs:** Classified event with severity, category, and recommended actions
- **Notes:** Supports custom classification rules and severity levels.

### CredentialManagerNode

- **Purpose:** Secure credential storage, retrieval, and lifecycle management.
- **Key Parameters:** `backend` (str), `operation` (str, required), `credential_name` (str), `credential_value` (str)
- **Outputs:** Credential operation results
- **Notes:** Supports multiple secret backends; handles rotation tracking.

### RotatingCredentialNode

- **Purpose:** Automatic credential rotation with zero-downtime transitions.
- **Key Parameters:** `credential_name` (str, required), `rotation_interval` (int), `rotation_strategy` (str)
- **Outputs:** Rotation status with new credential validity period
- **Notes:** Dual-credential overlap for zero-downtime rotation.

### ThreatDetectionNode

- **Purpose:** Real-time threat detection using behavioral analysis and rule matching.
- **Key Parameters:** `detection_rules` (list), `sensitivity` (str), `alert_channels` (list)
- **Outputs:** Threat assessment with risk score, indicators, and recommended response
- **Notes:** Uses SecurityMixin, PerformanceMixin, LoggingMixin.

### ABACPermissionEvaluatorNode

- **Purpose:** Attribute-Based Access Control (ABAC) policy evaluation.
- **Key Parameters:** `subject_attributes` (dict), `resource_attributes` (dict), `action` (str), `policy_set` (list)
- **Outputs:** `{"permitted": bool, "matching_policies": list, "denial_reason": str|None}`
- **Notes:** Uses SecurityMixin, PerformanceMixin, LoggingMixin; evaluates complex attribute policies.

### BehaviorAnalysisNode

- **Purpose:** Analyzes user and system behavior patterns for anomaly detection.
- **Key Parameters:** `behavior_data` (list), `baseline_period` (int), `anomaly_threshold` (float)
- **Outputs:** Behavior analysis report with anomaly scores and flagged patterns
- **Notes:** Uses SecurityMixin, PerformanceMixin, LoggingMixin.

---

## Admin (5 nodes)

### EnterpriseAuditLogNode

- **Purpose:** Enterprise-grade audit logging with compliance-ready formatting.
- **Key Parameters:** `event_type` (str), `actor` (str), `resource` (str), `action` (str), `compliance_standard` (str)
- **Outputs:** Formatted audit entry with compliance metadata
- **Notes:** Supports SOX, HIPAA, and GDPR compliance formatting.

### PermissionCheckNode

- **Purpose:** Checks user permissions against role-based access control policies.
- **Key Parameters:** `user_id` (str, required), `permission` (str, required), `resource` (str), `context` (dict)
- **Outputs:** `{"permitted": bool, "roles": list, "reason": str}`
- **Notes:** Integrates with RBAC and policy engines.

### RoleManagementNode

- **Purpose:** CRUD operations for roles and role assignments.
- **Key Parameters:** `operation` (str, required), `role_name` (str), `permissions` (list), `user_id` (str)
- **Outputs:** Role operation results with updated role state
- **Notes:** Operations: create, update, delete, assign, revoke.

### EnterpriseSecurityEventNode

- **Purpose:** Enterprise security event processing with SIEM integration.
- **Key Parameters:** `event_data` (dict), `severity` (str), `siem_target` (str), `correlation_rules` (list)
- **Outputs:** Processed security event with SIEM-compatible formatting
- **Notes:** Supports event correlation and SIEM forwarding.

### UserManagementNode

- **Purpose:** User account lifecycle management (create, update, disable, delete).
- **Key Parameters:** `operation` (str, required), `user_data` (dict), `user_id` (str)
- **Outputs:** User operation results with account state
- **Notes:** Handles account provisioning, updates, and deactivation.

---

## Auth (6 nodes)

### SSOAuthenticationNode

- **Purpose:** Single sign-on authentication with SAML and OIDC support.
- **Key Parameters:** `provider` (str, required), `callback_url` (str), `client_id` (str), `metadata_url` (str)
- **Outputs:** Authentication result with user identity and session token
- **Notes:** Uses SecurityMixin, PerformanceMixin, LoggingMixin.

### MultiFactorAuthNode

- **Purpose:** Multi-factor authentication with TOTP, SMS, and email verification.
- **Key Parameters:** `user_id` (str, required), `mfa_method` (str, required), `verification_code` (str)
- **Outputs:** MFA verification result with status and remaining attempts
- **Notes:** Uses SecurityMixin; supports TOTP, SMS, email, and push notification methods.

### SessionManagementNode

- **Purpose:** User session creation, validation, renewal, and invalidation.
- **Key Parameters:** `operation` (str, required), `session_id` (str), `user_id` (str), `ttl` (int)
- **Outputs:** Session state with expiry and metadata
- **Notes:** Uses SecurityMixin; supports sliding and absolute expiration.

### RiskAssessmentNode

- **Purpose:** Assesses authentication risk based on device, location, and behavior signals.
- **Key Parameters:** `user_id` (str, required), `login_context` (dict), `risk_factors` (list)
- **Outputs:** Risk score with contributing factors and recommended auth level
- **Notes:** Uses SecurityMixin; adaptive authentication based on risk signals.

### DirectoryIntegrationNode

- **Purpose:** Integrates with LDAP/Active Directory for user and group management.
- **Key Parameters:** `directory_url` (str, required), `bind_dn` (str), `bind_password` (str), `search_base` (str)
- **Outputs:** Directory query results with user/group attributes
- **Notes:** Uses SecurityMixin; supports LDAP search, bind, and modify operations.

### EnterpriseAuthProviderNode

- **Purpose:** Unified enterprise authentication provider supporting multiple identity sources.
- **Key Parameters:** `provider_type` (str, required), `config` (dict), `fallback_providers` (list)
- **Outputs:** Authentication result with provider metadata
- **Notes:** Uses SecurityMixin; aggregates LDAP, SAML, OIDC, and local auth.

---

## Enterprise (6 nodes)

### EnterpriseAuditLoggerNode

- **Purpose:** Structured audit event logging for enterprise compliance requirements.
- **Key Parameters:** `event` (dict), `audit_level` (str), `retention_policy` (str)
- **Outputs:** Logged audit entry with compliance tags
- **Notes:** Separate from admin audit; focused on application-level audit trails.

### BatchProcessorNode

- **Purpose:** Processes large datasets in configurable batch sizes with progress tracking.
- **Key Parameters:** `items` (list, required), `batch_size` (int), `processor_config` (dict), `error_handling` (str)
- **Outputs:** Processing results with batch-level statistics
- **Notes:** Handles partial failures and progress reporting.

### DataLineageNode

- **Purpose:** Tracks data provenance and transformation lineage across workflow steps.
- **Key Parameters:** `input_sources` (list), `transformations` (list), `data_classifications` (list)
- **Outputs:** Lineage graph with source-to-output traceability
- **Notes:** Supports compliance reporting and impact analysis.

### EnterpriseMLCPExecutorNode

- **Purpose:** Executes MCP (Model Context Protocol) tools within enterprise governance boundaries.
- **Key Parameters:** `tool_name` (str, required), `tool_input` (dict), `governance_policy` (dict), `audit_enabled` (bool)
- **Outputs:** Tool execution results with audit trail
- **Notes:** Wraps MCP execution with access control and logging.

### MCPServiceDiscoveryNode

- **Purpose:** Discovers available MCP services and tools in the network.
- **Key Parameters:** `discovery_endpoints` (list), `filter_capabilities` (list)
- **Outputs:** Available services with capabilities and connection info
- **Notes:** Enables dynamic MCP tool registration.

### TenantAssignmentNode

- **Purpose:** Assigns and manages tenant context for multi-tenant operations.
- **Key Parameters:** `tenant_id` (str, required), `assignment_strategy` (str), `isolation_level` (str)
- **Outputs:** Tenant assignment result with resource allocation details
- **Notes:** Supports shared, isolated, and hybrid tenancy models.

---

## Transaction (5 nodes)

### TransactionContextNode

- **Purpose:** Manages database transaction lifecycle (begin, commit, rollback) within workflows.
- **Key Parameters:** `isolation_level` (str), `timeout` (float), `savepoint_name` (str)
- **Outputs:** Transaction state with commit/rollback status
- **Notes:** Async node; supports nested transactions via savepoints.

### SagaCoordinatorNode

- **Purpose:** Orchestrates distributed saga transactions with compensation logic.
- **Key Parameters:** `saga_id` (str), `steps` (list[SagaStep]), `timeout` (float), `compensation_strategy` (str)
- **Outputs:** Saga execution result with per-step status
- **Notes:** Async node; uses NodeExecutor for step execution, not stubs.

### SagaStepNode

- **Purpose:** Individual step within a saga transaction with forward and compensation actions.
- **Key Parameters:** `step_name` (str, required), `forward_action` (dict), `compensate_action` (dict), `timeout` (float)
- **Outputs:** Step execution result with success/failure and compensation status
- **Notes:** Async node; paired forward/compensate for rollback capability.

### TwoPhaseCommitCoordinatorNode

- **Purpose:** Coordinates two-phase commit (2PC) protocol across distributed participants.
- **Key Parameters:** `participants` (list, required), `timeout` (float), `recovery_log` (str)
- **Outputs:** Commit/abort decision with per-participant vote status
- **Notes:** Async node; implements prepare-commit/abort protocol.

### DistributedTransactionManagerNode

- **Purpose:** Manages complex distributed transactions across multiple services.
- **Key Parameters:** `transaction_id` (str), `participants` (list), `timeout` (float), `retry_policy` (dict)
- **Outputs:** Transaction outcome with participant statuses and timing
- **Notes:** Async node; combines saga and 2PC patterns.

---

## Transform (8 nodes)

### FilterNode

- **Purpose:** Filters data collections based on configurable predicates.
- **Key Parameters:** `data` (list, required), `conditions` (dict), `mode` (str: include/exclude)
- **Outputs:** `{"filtered_data": list, "removed_count": int}`
- **Notes:** Supports field-level comparisons and compound conditions.

### Map

- **Purpose:** Applies a transformation function to each item in a data collection.
- **Key Parameters:** `data` (list, required), `transform` (str/callable), `output_field` (str)
- **Outputs:** `{"mapped_data": list}`
- **Notes:** Supports field extraction, renaming, and computed fields.

### DataTransformer

- **Purpose:** General-purpose data transformation with embedded Python expressions.
- **Key Parameters:** `data` (Any, required), `transform_code` (str, required), `input_vars` (dict)
- **Outputs:** Transformed data as specified by transform code
- **Notes:** Sandboxed execution; supports complex multi-step transformations.

### Sort

- **Purpose:** Sorts data collections by one or more fields.
- **Key Parameters:** `data` (list, required), `sort_by` (str/list), `reverse` (bool, default `False`)
- **Outputs:** `{"sorted_data": list}`
- **Notes:** Supports multi-key sorting and custom comparators.

### ContextualCompressorNode

- **Purpose:** Compresses context by extracting only relevant portions for downstream use.
- **Key Parameters:** `context` (str/list), `query` (str), `max_length` (int), `compression_method` (str)
- **Outputs:** `{"compressed_context": str, "compression_ratio": float}`
- **Notes:** Useful for RAG pipelines to reduce context window usage.

### HierarchicalChunkerNode

- **Purpose:** Splits documents into hierarchical chunks preserving document structure.
- **Key Parameters:** `documents` (list, required), `levels` (list), `chunk_size` (int)
- **Outputs:** `{"chunks": list[dict]}` with parent-child relationships
- **Notes:** Preserves heading/section hierarchy for better retrieval.

### SemanticChunkerNode

- **Purpose:** Splits text into semantically coherent chunks using embedding similarity.
- **Key Parameters:** `text` (str, required), `threshold` (float), `embedding_model` (str)
- **Outputs:** `{"chunks": list[str], "boundaries": list[int]}`
- **Notes:** Groups sentences by semantic similarity rather than fixed size.

### StatisticalChunkerNode

- **Purpose:** Splits text using statistical analysis of content boundaries.
- **Key Parameters:** `text` (str, required), `method` (str), `target_size` (int)
- **Outputs:** `{"chunks": list[str], "statistics": dict}`
- **Notes:** Uses sentence length, vocabulary, and topic shift signals.

### ChunkTextExtractorNode

- **Purpose:** Extracts plain text content from structured chunk objects.
- **Key Parameters:** `chunks` (list, required), `text_field` (str, default `"content"`)
- **Outputs:** `{"texts": list[str]}`
- **Notes:** Utility node for chunk pipeline interoperability.

### QueryTextWrapperNode

- **Purpose:** Wraps query text with context templates for embedding or LLM consumption.
- **Key Parameters:** `query` (str, required), `template` (str), `prefix` (str), `suffix` (str)
- **Outputs:** `{"wrapped_query": str}`
- **Notes:** Adds instruction prefixes for query-specific embeddings.

### ContextFormatterNode

- **Purpose:** Formats retrieved context chunks into a structured prompt-ready string.
- **Key Parameters:** `chunks` (list, required), `format_template` (str), `separator` (str), `max_context_length` (int)
- **Outputs:** `{"formatted_context": str}`
- **Notes:** Prepares context for LLM consumption with source attribution.

---

## Cache (3 nodes)

### CacheNode

- **Purpose:** Async caching operations with TTL, eviction policies, and backend abstraction.
- **Key Parameters:** `operation` (str, required), `key` (str), `value` (Any), `ttl` (int), `backend` (str)
- **Outputs:** Cache operation result (hit/miss, stored value, eviction count)
- **Notes:** Async node; supports get, set, delete, invalidate, and stats operations.

### CacheInvalidationNode

- **Purpose:** Pattern-based cache invalidation across cache backends.
- **Key Parameters:** `pattern` (str, required), `backend` (str), `scope` (str)
- **Outputs:** `{"invalidated_count": int, "pattern": str}`
- **Notes:** Async node; supports glob patterns and tenant-scoped invalidation.

### RedisPoolManagerNode

- **Purpose:** Manages Redis connection pools with health monitoring and failover.
- **Key Parameters:** `redis_url` (str, required), `pool_size` (int), `health_check_interval` (int)
- **Outputs:** Pool status with active/idle connections and health metrics
- **Notes:** Async node; provides managed Redis connections for other nodes.

---

## Code (2 nodes)

### PythonCodeNode

- **Purpose:** Executes sandboxed Python code within workflows for custom logic.
- **Key Parameters:** `code` (str, required), `input_vars` (dict), `allowed_modules` (list), `timeout` (float)
- **Outputs:** `{"result": Any}` — return value of executed code
- **Notes:** Safety checker validates code before execution; restricted module access.

### AsyncPythonCodeNode

- **Purpose:** Executes sandboxed async Python code for non-blocking custom logic.
- **Key Parameters:** `code` (str, required), `input_vars` (dict), `allowed_modules` (list), `timeout` (float)
- **Outputs:** `{"result": Any}` — return value of executed async code
- **Notes:** Async version; safety checker prevents dangerous operations.

---

## Compliance (2 nodes)

### GDPRComplianceNode

- **Purpose:** GDPR compliance operations including data subject requests and consent management.
- **Key Parameters:** `operation` (str, required), `data_subject_id` (str), `request_type` (str), `data_categories` (list)
- **Outputs:** Compliance operation result with audit trail
- **Notes:** Uses SecurityMixin; supports access, rectification, erasure, and portability requests.

### DataRetentionPolicyNode

- **Purpose:** Enforces data retention policies with automated archival and deletion.
- **Key Parameters:** `policy_name` (str, required), `retention_period` (int), `action` (str), `data_scope` (dict)
- **Outputs:** Retention enforcement results with records affected
- **Notes:** Uses SecurityMixin; supports archive-then-delete and immediate-delete strategies.

---

## Validation (3 nodes)

### CodeValidationNode

- **Purpose:** Validates Python code for syntax errors, style issues, and security problems.
- **Key Parameters:** `code` (str, required), `validation_level` (str), `rules` (list)
- **Outputs:** Validation results with findings by severity
- **Notes:** Checks imports, security patterns, and code quality.

### WorkflowValidationNode

- **Purpose:** Validates workflow structure for correctness (connections, cycles, parameters).
- **Key Parameters:** `workflow` (dict, required), `strict_mode` (bool), `check_types` (list)
- **Outputs:** Validation results with structural issues and warnings
- **Notes:** Detects disconnected nodes, invalid connections, and parameter mismatches.

### ValidationTestSuiteExecutorNode

- **Purpose:** Executes validation test suites against workflows or code.
- **Key Parameters:** `test_suite` (dict, required), `target` (str), `parallel` (bool)
- **Outputs:** Test execution results with pass/fail per test case
- **Notes:** Supports parameterized tests and parallel execution.

---

## System (3 nodes)

### CommandParserNode

- **Purpose:** Parses natural language or structured commands into executable actions.
- **Key Parameters:** `input_text` (str, required), `command_definitions` (dict), `fuzzy_match` (bool)
- **Outputs:** Parsed command with action, arguments, and confidence score
- **Notes:** Supports command aliases and fuzzy matching.

### InteractiveShellNode

- **Purpose:** Provides an interactive shell interface within workflow execution.
- **Key Parameters:** `prompt` (str), `allowed_commands` (list), `timeout` (float)
- **Outputs:** Shell session results with command history
- **Notes:** Sandboxed command execution with allowlist filtering.

### CommandRouterNode

- **Purpose:** Routes parsed commands to appropriate handler nodes.
- **Key Parameters:** `command` (dict, required), `handler_map` (dict, required), `fallback_handler` (str)
- **Outputs:** Routed command execution result
- **Notes:** Maps command types to handler node IDs.

---

## Testing (1 node)

### CredentialTestingNode

- **Purpose:** Tests credential validity against target services.
- **Key Parameters:** `credential_type` (str, required), `credential_value` (str, required), `target_service` (str)
- **Outputs:** `{"valid": bool, "service": str, "error": str|None}`
- **Notes:** Non-destructive credential validation.

---

## Alerts (2 nodes)

### AlertNode

- **Purpose:** Base alert dispatch node for sending notifications via configurable channels.
- **Key Parameters:** `alert_type` (str, required), `message` (str, required), `severity` (str), `channels` (list)
- **Outputs:** Alert delivery status per channel
- **Notes:** Base class for specialized alert nodes; supports multiple dispatch channels.

### DiscordAlertNode

- **Purpose:** Sends alert notifications to Discord channels via webhooks.
- **Key Parameters:** `webhook_url` (str, required), `message` (str, required), `embed` (dict), `mention_roles` (list)
- **Outputs:** Discord delivery status with message ID
- **Notes:** Extends AlertNode; supports rich embeds and role mentions.

---

## Compliance (2 nodes)

See [Compliance](#compliance-2-nodes) above.

---

## Governance (3 nodes)

### SecureGovernedNode

- **Purpose:** Abstract base node combining SecurityMixin, LoggingMixin, and PerformanceMixin for governed execution.
- **Key Parameters:** Inherits from all three mixins plus Node
- **Outputs:** Governed execution results with security and performance metadata
- **Notes:** Abstract base class; not directly instantiated. Provides audit, logging, and performance tracking.

### EnterpriseNode

- **Purpose:** Production-ready governed node with enterprise security defaults.
- **Key Parameters:** Inherits SecureGovernedNode defaults with strict security posture
- **Outputs:** Governed execution results
- **Notes:** Pre-configured for enterprise environments with mandatory audit logging.

### DevelopmentNode

- **Purpose:** Development-mode governed node with relaxed security for local testing.
- **Key Parameters:** Inherits SecureGovernedNode with permissive defaults
- **Outputs:** Governed execution results
- **Notes:** Relaxed security for development; not for production use.

---

## Handler (1 node)

### HandlerNode

- **Purpose:** Handles incoming Nexus requests and routes them to workflow execution.
- **Key Parameters:** `handler_type` (str), `route` (str), `methods` (list)
- **Outputs:** Request handling results
- **Notes:** Async node; bridge between Nexus HTTP layer and workflow engine.

---

## Base / Mixins

These are not workflow nodes but base classes and mixins used by the nodes above.

### Node (ABC)

- **Purpose:** Abstract base class for all synchronous nodes. Defines the `get_parameters()` and `run()` contract.

### AsyncNode

- **Purpose:** Abstract base class for all asynchronous nodes. Adds `async_run()` to the Node contract.

### TypedNode

- **Purpose:** Base class for nodes with typed input/output schemas using Python type hints.

### AsyncTypedNode

- **Purpose:** Async variant of TypedNode for typed asynchronous nodes.

### CycleAwareNode

- **Purpose:** Base class for nodes that participate in cyclic workflows and track iteration state.

### NodeWithAccessControl

- **Purpose:** Adds access control (ACL) enforcement to synchronous nodes.

### AsyncNodeWithAccessControl

- **Purpose:** Adds access control (ACL) enforcement to asynchronous nodes.

### EventAwareNode (mixin)

- **Purpose:** Mixin that adds event emission capabilities to any node.

---

_Catalog generated from source inspection of `src/kailash/nodes/` across 20 category directories._
