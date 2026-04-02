"""
DataFlow Engine

Main DataFlow class and database management.
"""

import asyncio
import inspect
import logging
import os
import threading
import time
import warnings
from copy import deepcopy
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, Union

from kailash.runtime import AsyncLocalRuntime, LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from ..features.bulk import BulkOperations
from ..features.express import ExpressDataFlow, SyncExpress
from ..features.multi_tenant import MultiTenantManager
from ..features.transactions import TransactionManager
from ..migrations.auto_migration_system import AutoMigrationSystem
from ..migrations.schema_state_manager import SchemaStateManager
from ..utils.connection import ConnectionManager
from .async_utils import (  # Phase 6: Async-safe execution
    async_safe_run,
    warn_sqlite_async_limitation,
)
from .config import (
    DatabaseConfig,
    DataFlowConfig,
    LoggingConfig,
    MonitoringConfig,
    SecurityConfig,
)
from .events import DataFlowEventMixin
from .logging_config import mask_sensitive_values  # Phase 7: Sensitive value masking
from .nodes import NodeGenerator
from .schema_cache import create_schema_cache  # ADR-001: Schema cache integration

# ErrorEnhancer for rich error messages
# Platform ErrorEnhancer for module-level (static) enhancements
try:
    from dataflow.platform.errors import ErrorEnhancer as PlatformErrorEnhancer
except ImportError:
    PlatformErrorEnhancer = None

# Core ErrorEnhancer for instance-level enhancements
try:
    from .error_enhancer import ErrorEnhancer as CoreErrorEnhancer
except ImportError:
    CoreErrorEnhancer = None

# Use Platform ErrorEnhancer for backward compatibility with existing code
ErrorEnhancer = PlatformErrorEnhancer

logger = logging.getLogger(__name__)


class DataFlow(DataFlowEventMixin):
    """Main DataFlow interface."""

    # ADR-017: Global test mode control
    _global_test_mode: Optional[bool] = None
    _global_test_mode_lock = threading.RLock()

    def __init__(
        self,
        database_url: Optional[str] = None,
        config: Optional[DataFlowConfig] = None,
        pool_size: Optional[
            int
        ] = None,  # Changed to Optional to detect when explicitly set
        pool_max_overflow: Optional[int] = None,
        pool_recycle: int = 3600,
        echo: bool = False,
        multi_tenant: bool = False,
        encryption_key: Optional[str] = None,
        audit_logging: bool = False,
        cache_enabled: bool = True,
        cache_ttl: int = 3600,
        monitoring: Optional[
            bool
        ] = None,  # Changed to Optional to detect when explicitly set
        slow_query_threshold: float = 1.0,
        debug: bool = False,
        migration_enabled: bool = True,
        auto_migrate: bool = True,  # NEW: Control auto-migration behavior
        existing_schema_mode: bool = False,  # NEW: Safe mode for existing DBs
        enable_model_persistence: bool = True,  # NEW: Enable persistent model registry
        tdd_mode: bool = False,  # NEW: Enable TDD mode for testing
        test_context: Optional[Any] = None,  # NEW: TDD test context
        test_mode: Optional[bool] = None,  # ADR-017: Test mode detection
        test_mode_aggressive_cleanup: bool = True,  # ADR-017: Aggressive pool cleanup
        migration_lock_timeout: int = 30,  # NEW: Migration lock timeout for concurrent safety
        enable_connection_pooling: bool = True,  # NEW: Enable connection pooling
        pools: Optional[
            Dict[str, Dict[str, Any]]
        ] = None,  # NEW: Per-database pool overrides
        max_overflow: Optional[int] = None,  # NEW: Alias for pool_max_overflow
        enable_caching: Optional[
            bool
        ] = None,  # FIX: Alias for cache_enabled (bug report)
        validate_on_write: bool = True,  # TSG-103: Validate on Express write ops
        log_level: Optional[int] = None,  # ADR-002: Centralized logging config
        log_config: Optional[LoggingConfig] = None,  # ADR-002: Full logging config
        read_url: Optional[str] = None,  # TSG-105: Read replica URL
        read_pool_size: Optional[int] = None,  # TSG-105: Separate pool size for reads
        redis_url: Optional[str] = None,  # TSG-107: Redis URL for Express cache backend
        **kwargs,
    ):
        """Initialize DataFlow.

        Args:
            database_url: Database connection URL (uses DATABASE_URL env var if not provided)
            config: DataFlowConfig object with detailed settings
            pool_size: Connection pool size (default 20)
            pool_max_overflow: Maximum overflow connections
            pool_recycle: Time to recycle connections
            echo: Enable SQL logging
            multi_tenant: Enable multi-tenant mode
            encryption_key: Encryption key for sensitive data
            audit_logging: Enable audit logging
            cache_enabled: Enable query caching
            cache_ttl: Cache time-to-live
            monitoring: Enable performance monitoring
            migration_enabled: Enable automatic database migrations (default True)
            auto_migrate: Automatically run migrations on model registration (default True)
            existing_schema_mode: Safe mode for existing databases - validates compatibility (default False)
            tdd_mode: Enable TDD mode for testing (default False)
            test_context: TDD test context (default None)
            test_mode: Explicit test mode setting (None=auto-detect, True=enable, False=disable)
            test_mode_aggressive_cleanup: Enable aggressive pool cleanup in test mode (default True)
            log_level: Optional log level override (e.g., logging.DEBUG)
            log_config: Full LoggingConfig for advanced control
            **kwargs: Additional configuration options

        Note:
            ARCHITECTURAL FIX: As of this version, migrations are deferred during model registration
            to prevent "Event loop is closed" errors. For proper migration execution:

            # Option 1: Explicit async initialization (recommended)
            db = DataFlow(database_url="sqlite:///app.db")

            @db.model
            class User:
                name: str

            await db.initialize_deferred_migrations()  # Execute migrations async

            # Option 2: Automatic initialization (backward compatibility)
            db.ensure_migrations_initialized()  # Handles event loop properly
        """
        # ADR-002: Configure logging FIRST, before any other operations
        self._configure_logging(log_level, log_config)

        if config:
            # Use the provided config as base but allow kwargs to override
            self.config = deepcopy(config)
            # Override config attributes with kwargs
            if debug is not None:
                self.config.debug = debug
            if "batch_size" in kwargs:
                self.config.batch_size = kwargs["batch_size"]
            if pool_size is not None:
                self.config.pool_size = pool_size
            if pool_max_overflow is not None:
                self.config.max_overflow = pool_max_overflow
            if pool_recycle is not None:
                self.config.pool_recycle = pool_recycle
            if echo is not None:
                self.config.echo = echo
            if monitoring is not None:
                self.config.monitoring = monitoring
            if cache_enabled is not None:
                self.config.enable_query_cache = cache_enabled
            # FIX: CACHE_INVALIDATION_BUG_REPORT.md - enable_caching is alias for cache_enabled
            if enable_caching is not None:
                self.config.enable_query_cache = enable_caching
            if cache_ttl is not None:
                self.config.cache_ttl = cache_ttl
            if slow_query_threshold is not None:
                self.config.slow_query_threshold = slow_query_threshold
            # ADR-001: Override schema cache configuration from kwargs
            if "schema_cache_enabled" in kwargs:
                self.config.migration.schema_cache_enabled = kwargs[
                    "schema_cache_enabled"
                ]
            if "schema_cache_ttl" in kwargs:
                self.config.migration.schema_cache_ttl = kwargs["schema_cache_ttl"]
            if "schema_cache_max_size" in kwargs:
                self.config.migration.schema_cache_max_size = kwargs[
                    "schema_cache_max_size"
                ]
        else:
            # Validate database_url if provided
            if database_url and not self._is_valid_database_url(database_url):
                # Enhanced error with catalog-based solutions (DF-401)
                raise ErrorEnhancer.enhance_invalid_database_url(  # noqa: F823
                    database_url=database_url,
                    error_message="URL format validation failed",
                )
            # Create config from environment or parameters
            if database_url is None and all(
                param is None
                for param in [
                    pool_size,
                    pool_max_overflow,
                    pool_recycle,
                    echo,
                    multi_tenant,
                    encryption_key,
                    audit_logging,
                    cache_enabled,
                    cache_ttl,
                    monitoring,
                ]
            ):
                # Zero-config mode - use from_env
                self.config = DataFlowConfig.from_env()
            else:
                # Create structured config from individual parameters
                database_config = DatabaseConfig(
                    url=database_url,
                    pool_size=pool_size,  # None flows through to get_pool_size()
                    max_overflow=pool_max_overflow,  # None flows through to get_max_overflow()
                    pool_recycle=pool_recycle,
                    echo=echo,
                )

                monitoring_config = MonitoringConfig(
                    enabled=(
                        monitoring if monitoring is not None else False
                    ),  # Provide default
                    slow_query_threshold=slow_query_threshold,
                )

                security_config = SecurityConfig(
                    multi_tenant=multi_tenant,
                    encrypt_at_rest=encryption_key is not None,
                    audit_enabled=audit_logging,
                )

                # Prepare config parameters
                # FIX: CACHE_INVALIDATION_BUG_REPORT.md - enable_caching is alias for cache_enabled
                effective_cache_enabled = (
                    enable_caching if enable_caching is not None else cache_enabled
                )
                config_params = {
                    "database": database_config,
                    "monitoring": monitoring_config,
                    "security": security_config,
                    "enable_query_cache": effective_cache_enabled,
                    "cache_ttl": cache_ttl,
                }

                # Add direct parameters that should be passed through
                config_params["debug"] = debug
                if "batch_size" in kwargs:
                    config_params["batch_size"] = kwargs["batch_size"]
                if "cache_max_size" in kwargs:
                    config_params["cache_max_size"] = kwargs["cache_max_size"]
                if "max_retries" in kwargs:
                    config_params["max_retries"] = kwargs["max_retries"]
                if "encryption_enabled" in kwargs:
                    config_params["encryption_enabled"] = kwargs["encryption_enabled"]

                # ADR-001: Pass schema cache configuration kwargs
                if "schema_cache_enabled" in kwargs:
                    config_params["schema_cache_enabled"] = kwargs[
                        "schema_cache_enabled"
                    ]
                if "schema_cache_ttl" in kwargs:
                    config_params["schema_cache_ttl"] = kwargs["schema_cache_ttl"]
                if "schema_cache_max_size" in kwargs:
                    config_params["schema_cache_max_size"] = kwargs[
                        "schema_cache_max_size"
                    ]

                self.config = DataFlowConfig(**config_params)

        # Validate configuration
        if hasattr(self.config, "validate"):
            issues = self.config.validate()
            if issues:
                logger.warning(f"Configuration issues detected: {issues}")

        # DF-CFG-001: Validate unknown kwargs to prevent silent configuration failures
        # This catches typos and removed parameters like 'skip_registry' early
        KNOWN_KWARGS = {
            "batch_size",
            "cache_max_size",
            "max_retries",
            "encryption_enabled",
            "schema_cache_enabled",
            "schema_cache_ttl",
            "schema_cache_max_size",
            "use_namespaced_nodes",
            "log_level",  # ADR-002: handled as named parameter, but include for safety
            "log_config",  # ADR-002: handled as named parameter, but include for safety
        }
        unknown_kwargs = set(kwargs.keys()) - KNOWN_KWARGS
        if unknown_kwargs:
            # Provide helpful suggestions for common mistakes
            suggestions = []
            for param in unknown_kwargs:
                if param == "skip_registry":
                    suggestions.append(
                        f"  - '{param}': This parameter was never implemented. "
                        f"Use 'enable_model_persistence=False' for fast startup."
                    )
                elif param == "skip_migration":
                    suggestions.append(
                        f"  - '{param}': Use 'auto_migrate=False' instead."
                    )
                elif param == "connection_pool_size":
                    suggestions.append(f"  - '{param}': Use 'pool_size' instead.")
                elif param == "enable_metrics":
                    suggestions.append(f"  - '{param}': Use 'monitoring=True' instead.")
                else:
                    suggestions.append(
                        f"  - '{param}': Unknown parameter (has no effect)."
                    )

            warning_msg = (
                f"DF-CFG-001: Unknown parameters passed to DataFlow: {unknown_kwargs}. "
                f"These parameters have no effect and will be ignored.\n"
                + "\n".join(suggestions)
            )
            import warnings

            warnings.warn(warning_msg, UserWarning, stacklevel=2)
            logger.warning(warning_msg)

        self._models = {}
        self._registered_models = {}  # Track registered models for compatibility
        self._model_fields = {}  # Store model field information
        self._nodes = {}  # Store generated nodes for testing
        self._tenant_context = None if not self.config.security.multi_tenant else {}

        # Fabric Engine: source and product registrations (populated by .source() and @product())
        self._sources: Dict[str, Any] = {}
        self._products: Dict[str, Any] = {}
        self._fabric: Optional[Any] = None

        # DATAFLOW-ASYNC-MODEL-DECORATOR-001: Deferred relationship detection
        # Store models that need relationship detection, to be processed during initialize()
        # This prevents discover_schema() from being called during model registration,
        # which would fail in async contexts (pytest async fixtures, FastAPI lifespan, etc.)
        self._pending_relationship_detection: set = set()

        # Initialize ErrorEnhancer for enhanced error messages
        # Use Core ErrorEnhancer for instance-level enhancements
        self.error_enhancer = (
            CoreErrorEnhancer() if CoreErrorEnhancer is not None else None
        )

        # Cache AsyncSQLDatabaseNode instances to enable connection pooling across workflows
        # Critical for SQLite :memory: databases which need to share the same connection
        # See: ROOT_CAUSE_ANALYSIS.md in reports/issues/database-url-inheritance/
        # Format: {database_type: (node, event_loop_id)} for event loop tracking (v0.10.6+)
        self._async_sql_node_cache = {}  # Keyed by database_type

        # Store migration control parameters
        self._auto_migrate = auto_migrate
        self._migration_enabled = migration_enabled
        self._existing_schema_mode = existing_schema_mode
        self._migration_lock_timeout = max(
            1, migration_lock_timeout
        )  # Ensure minimum 1 second

        # ADR-001: Store kwargs for schema cache configuration (needed to detect explicit False)
        self._init_kwargs = kwargs

        # ARCHITECTURAL FIX v0.7.5: Instance identification for multi-instance isolation
        # Assign unique instance ID to prevent node registration collisions
        # Format: df_{memory_address} ensures uniqueness across all DataFlow instances
        # Used by NodeGenerator to create namespaced node names (UserCreateNode_{instance_id})
        self._instance_id = f"df_{id(self)}"
        self._use_namespaced_nodes = kwargs.get(
            "use_namespaced_nodes", True
        )  # Enable by default for safety

        # ARCHITECTURAL FIX: Deferred migration queue
        # This solves the "Event loop is closed" issue by separating
        # synchronous model registration from async migration execution
        # Removed deferred migrations - tables now created lazily when first accessed
        # Removed migration tracking - tables are now created lazily

        # Initialize TDD mode first (needed by NodeGenerator and _initialize_database)
        self._tdd_mode = tdd_mode or os.environ.get(
            "DATAFLOW_TDD_MODE", "false"
        ).lower() in (
            "true",
            "yes",
            "1",
            "on",
        )
        self._test_context = test_context
        if self._tdd_mode:
            self._initialize_tdd_mode()

        # ADR-017: Test mode detection and configuration
        self._test_mode = self._resolve_test_mode(test_mode)
        self._test_mode_aggressive_cleanup = test_mode_aggressive_cleanup

        # Log test mode activation
        if self._test_mode:
            if test_mode is None:
                if self._global_test_mode is not None:
                    logger.warning("DataFlow: Test mode enabled (global setting)")
                else:
                    logger.warning(
                        "DataFlow: Test mode enabled (auto-detected pytest environment)"
                    )
            else:
                logger.warning("DataFlow: Test mode enabled (explicitly set)")

            if self._test_mode_aggressive_cleanup:
                logger.warning(
                    "DataFlow: Aggressive pool cleanup enabled for test mode"
                )

        # Register specialized DataFlow nodes
        self._register_specialized_nodes()

        # M2-001: Create exactly ONE shared runtime for the entire DataFlow instance.
        # All subsystems (ModelRegistry, migration helpers, DDL executors) share this
        # runtime via acquire()/release() ref-counting instead of creating their own.
        self._closed = False
        try:
            asyncio.get_running_loop()
            self.runtime = AsyncLocalRuntime()
            self._is_async = True
            logger.debug("DataFlow: Detected async context, using AsyncLocalRuntime")
        except RuntimeError:
            self.runtime = LocalRuntime()
            self._is_async = False
            logger.debug("DataFlow: Detected sync context, using LocalRuntime")

        # Initialize feature modules (NodeGenerator now gets TDD context)
        self._node_generator = NodeGenerator(self)
        self._bulk_operations = BulkOperations(self)
        self._transaction_manager = TransactionManager(self)
        self._connection_manager = ConnectionManager(self)

        # TSG-105: Dual-adapter read replica support
        self._read_url = read_url
        self._read_pool_size = read_pool_size
        self._read_connection_manager: Optional[ConnectionManager] = None
        if read_url:
            self._read_connection_manager = ConnectionManager(
                self, url_override=read_url, pool_size_override=read_pool_size
            )

        # TSG-201: Initialize event bus for write-event emission
        self._init_events()

        # TSG-104: Wire cache configuration into Express
        _express_cache_ttl = getattr(self.config, "cache_ttl", 300)
        _express_cache_enabled = getattr(
            self.config, "enable_query_cache", cache_enabled
        )
        # TSG-107: Explicit redis_url parameter takes precedence over config
        _express_redis_url = redis_url or getattr(self.config, "cache_redis_url", None)
        _express_cache_max_size = getattr(self.config, "cache_max_size", 1000)
        self._express_dataflow = ExpressDataFlow(
            self,
            cache_enabled=_express_cache_enabled,
            cache_max_size=_express_cache_max_size,
            cache_ttl=_express_cache_ttl,
            redis_url=_express_redis_url,
        )

        # TSG-103: Validation on write flag
        self._validate_on_write = validate_on_write

        # TSG-106: Retention engine
        from ..features.retention import RetentionEngine

        self._retention_engine = RetentionEngine(self)

        # TSG-100: Derived model engine
        from ..features.derived import DerivedModelEngine

        self._derived_engine = DerivedModelEngine(self)

        # Initialize workflow binder
        from .workflow_binding import DataFlowWorkflowBinder

        self._workflow_binder = DataFlowWorkflowBinder(self)

        # Initialize tenant context switching
        from .tenant_context import TenantContextSwitch

        self._tenant_context_switch = TenantContextSwitch(self)

        # Issue #171: Lazy connection — defer all DB-touching initialization
        # to _ensure_connected(), which is called on first query/operation.
        # __init__() stores config only — no pool probe, no migration, no connection.
        self._connected = False
        self._connect_lock = threading.Lock()
        self._enable_connection_pooling = enable_connection_pooling
        self._enable_model_persistence = enable_model_persistence

        # Connection pool state (initialized lazily in _ensure_connected)
        self._pool_manager = None
        self._pool_monitor = None
        self._lightweight_pool = None

        # Multi-tenant manager (lightweight — no DB connection)
        if self.config.security.multi_tenant:
            self._multi_tenant_manager = MultiTenantManager(self)
        else:
            self._multi_tenant_manager = None

        # Initialize model registry for multi-application support
        from .model_registry import ModelRegistry

        self._model_registry = ModelRegistry(self, runtime=self.runtime)

        # Cache integration (initialized lazily in _ensure_connected)
        self._cache_integration = None

        # Migration system (initialized lazily in _ensure_connected)
        self._migration_system = None
        self._schema_state_manager = None

        # Schema cache (pure in-memory, no DB connection needed)
        # Only enable cache if auto_migrate is enabled (no benefit otherwise)
        # CRITICAL: Respect explicit schema_cache_enabled=False from kwargs
        schema_cache_enabled = (
            self.config.migration.schema_cache_enabled
            and self._auto_migrate
            and self._init_kwargs.get("schema_cache_enabled", True) is not False
        )
        self._schema_cache = create_schema_cache(
            enabled=schema_cache_enabled,
            ttl_seconds=self.config.migration.schema_cache_ttl,
            max_cache_size=self.config.migration.schema_cache_max_size,
            enable_schema_validation=self.config.migration.schema_cache_validation,
            max_failure_count=self.config.migration.migration_max_failures,
            failure_backoff_seconds=self.config.migration.migration_failure_backoff,
        )
        logger.debug(
            f"Schema cache initialized: enabled={schema_cache_enabled}, "
            f"ttl={self.config.migration.schema_cache_ttl}s, "
            f"max_size={self.config.migration.schema_cache_max_size}"
        )

        # Track models that need table creation (deferred until _ensure_connected)
        self._pending_table_creations: list = []

    # ------------------------------------------------------------------
    # TSG-105: Read-replica connection routing
    # ------------------------------------------------------------------

    def _get_connection_manager(self, operation: str) -> ConnectionManager:
        """Route to read or write connection manager based on *operation*.

        When ``read_url`` was provided at construction time, read operations
        (``list``, ``read``, ``count``, ``find_one``, ``search``) are routed
        to the read-replica connection manager.  All other operations use the
        primary (write) connection manager.

        When no ``read_url`` was supplied, the primary connection manager is
        always returned (single-adapter mode -- backward compatible).
        """
        if self._read_connection_manager is None:
            return self._connection_manager  # single-adapter mode
        if operation in ("list", "read", "count", "find_one", "search"):
            return self._read_connection_manager
        return self._connection_manager  # writes always go to primary

    def _get_connection_manager_for_primary(self) -> ConnectionManager:
        """Always return the primary connection manager.

        Used by transactions and when ``use_primary=True`` is passed on
        read methods.
        """
        return self._connection_manager

    def _ensure_connected(self) -> None:
        """Lazily initialize all DB-touching resources on first use.

        Issue #171: DataFlow.__init__() no longer connects to the database.
        This method is called on first query, execute, or express operation.
        It is idempotent and thread-safe.

        Deferred work (from __init__):
        - Connection pool validation (pool probe via psycopg2)
        - Pool utilization monitor + leak detection
        - Lightweight health-check pool
        - Migration system initialization
        - Schema state manager initialization
        - Database connection pool initialization
        - Cache integration
        - Model registry sync
        - Pending table creations from @db.model decorators
        """
        if self._connected:
            return

        with self._connect_lock:
            # Double-check after acquiring lock
            if self._connected:
                return

            logger.debug("DataFlow: Lazy connection — initializing database resources")

            # 1. Connection pool validation (was in __init__)
            if self._enable_connection_pooling:
                resolved_pool_size = self.config.database.get_pool_size(
                    self.config.environment
                )
                resolved_max_overflow = self.config.database.get_max_overflow(
                    self.config.environment
                )
                logger.debug(
                    "Connection pooling enabled: pool_size=%d, max_overflow=%d",
                    resolved_pool_size,
                    resolved_max_overflow,
                )

                # PY-4: Startup validation — catch misconfigurations before first query
                startup_validation = self._init_kwargs.get("startup_validation", True)
                env_validation = os.environ.get(
                    "DATAFLOW_STARTUP_VALIDATION", "true"
                ).lower()
                if startup_validation and env_validation != "false":
                    try:
                        from dataflow.core.pool_validator import validate_pool_config

                        validate_pool_config(
                            database_url=self.config.database.url
                            or self.config.database.database_url,
                            pool_size=resolved_pool_size,
                            max_overflow=resolved_max_overflow,
                        )
                    except Exception:
                        logger.debug(
                            "Pool startup validation failed (non-fatal)",
                            exc_info=True,
                        )

                    # TSG-105: Validate read-replica pool when dual-adapter mode
                    if self._read_connection_manager is not None:
                        try:
                            read_pool_size = (
                                self._read_pool_size
                                if self._read_pool_size is not None
                                else resolved_pool_size
                            )
                            read_max_overflow = max(2, read_pool_size // 2)
                            validate_pool_config(
                                database_url=self._read_url,
                                pool_size=read_pool_size,
                                max_overflow=read_max_overflow,
                            )
                            total = resolved_pool_size + read_pool_size
                            logger.debug(
                                "TSG-105: Dual-adapter pool: primary=%d + read=%d = %d total",
                                resolved_pool_size,
                                read_pool_size,
                                total,
                            )
                        except Exception:
                            logger.debug(
                                "Read pool startup validation failed (non-fatal)",
                                exc_info=True,
                            )

                # PY-2/PY-5: Pool utilization monitor + leak detection
                if self.config.monitoring.connection_metrics:
                    try:
                        from dataflow.core.pool_monitor import PoolMonitor

                        self._pool_monitor = PoolMonitor(
                            stats_provider=self._make_pool_stats_provider(
                                resolved_pool_size, resolved_max_overflow
                            ),
                            interval_secs=float(
                                self.config.monitoring.pool_monitor_interval_secs
                            ),
                            alert_on_exhaustion=(
                                self.config.monitoring.alert_on_connection_exhaustion
                            ),
                            leak_detection_enabled=True,
                            leak_threshold_secs=float(
                                self.config.monitoring.leak_detection_threshold_secs
                            ),
                        )
                        self._pool_monitor.start()
                    except Exception:
                        logger.debug(
                            "Pool monitor initialization failed (non-fatal)",
                            exc_info=True,
                        )

                # RS-6: Lightweight pool for health checks (separate from main pool)
                db_url = self.config.database.url or self.config.database.database_url
                if db_url:
                    try:
                        from dataflow.core.pool_lightweight import LightweightPool

                        self._lightweight_pool = LightweightPool(db_url)
                    except Exception:
                        logger.debug(
                            "Lightweight pool creation failed (non-fatal)",
                            exc_info=True,
                        )

            # 2. Cache integration
            if self.config.enable_query_cache:
                self._initialize_cache_integration()

            # 3. Migration system
            if (
                self._migration_enabled
                and not (self._existing_schema_mode and not self._auto_migrate)
                and not os.environ.get("DATAFLOW_DISABLE_MIGRATIONS", "").lower()
                == "true"
            ):
                self._initialize_migration_system()
                self._initialize_schema_state_manager()

            # 4. Database connection pool initialization
            self._initialize_database()

            # 5. Model registry sync
            if self._enable_model_persistence and hasattr(self, "_model_registry"):
                self._sync_models_from_registry()

            # Mark as connected BEFORE processing pending table creations
            # to avoid re-entrance from _create_table_sync -> _ensure_connected
            self._connected = True

            # 6. Process pending table creations from @db.model decorators.
            # Batch all DDL into a single connection to avoid rapid open/close
            # churn that overwhelms Docker Desktop's vpnkit proxy (#211).
            if self._pending_table_creations:
                if self._auto_migrate and not self._existing_schema_mode:
                    self._create_tables_batch(list(self._pending_table_creations))
                self._pending_table_creations.clear()

            logger.debug(
                "DataFlow: Lazy connection complete — database resources initialized"
            )

    async def initialize(self) -> bool:
        """Initialize DataFlow asynchronously.

        This method performs async initialization tasks that cannot be done in __init__.
        It is idempotent and safe to call multiple times.

        Returns:
            bool: True if initialization successful, False otherwise
        """
        # Issue #171: Ensure sync connection resources are initialized first
        self._ensure_connected()

        try:
            # Validate database connectivity
            if not await self._validate_database_connection():
                logger.error("Database connection validation failed")
                return False

            # Initialize migration system components if enabled and not already done
            if self._migration_enabled and self._migration_system is not None:
                # Ensure migration table exists if we have migration system
                if hasattr(self._migration_system, "_ensure_migration_table"):
                    try:
                        await self._migration_system._ensure_migration_table()
                        logger.debug("Migration table verification completed")
                    except Exception as e:
                        logger.debug(f"Migration table setup encountered issue: {e}")
                        # Don't fail initialization for migration table issues in existing_schema_mode
                        if not self._existing_schema_mode:
                            return False

            # Initialize schema state manager if available
            if self._schema_state_manager is not None:
                try:
                    # Schema state manager initialization (if needed)
                    # In existing_schema_mode, this should be very fast
                    logger.debug("Schema state manager verified")
                except Exception as e:
                    logger.debug(f"Schema state manager issue: {e}")
                    # Don't fail initialization for schema state issues in existing_schema_mode
                    if not self._existing_schema_mode:
                        return False

            # Verify connection pool is working
            if hasattr(self._connection_manager, "initialize_pool"):
                self._connection_manager.initialize_pool()

            # DATAFLOW-ASYNC-MODEL-DECORATOR-001: Process deferred relationship detection
            # This enables @db.model to work in async contexts by deferring discover_schema()
            # until initialize() is called, which is always in a proper async context.
            await self._process_pending_relationship_detection()

            # TSG-101: Validate derived model dependency graph and set up
            # on_source_change event subscriptions.
            if self._derived_engine._models:
                self._derived_engine.validate_dependencies()
                self._derived_engine.setup_event_subscriptions()

            logger.debug("DataFlow initialization completed successfully")
            return True

        except Exception as e:
            logger.error(f"DataFlow initialization failed: {e}")
            return False

    async def _validate_database_connection(self) -> bool:
        """Validate that database connection is working.

        Returns:
            bool: True if connection is valid, False otherwise
        """
        try:
            # Check if this is PostgreSQL which requires async connections
            database_url = self.config.database.url
            is_postgresql = database_url and (
                "postgresql" in database_url.lower()
                or "postgres" in database_url.lower()
            )

            if is_postgresql:
                # Use async connection for PostgreSQL
                try:
                    connection = await self._get_async_database_connection()
                    if connection is None:
                        # In existing_schema_mode, be more lenient
                        return self._existing_schema_mode

                    # For async connections, try a simple validation
                    # The connection manager handles the actual validation
                    return True
                except Exception as async_error:
                    logger.debug(
                        f"PostgreSQL async connection test failed: {async_error}"
                    )
                    # In existing_schema_mode, be more lenient with connection issues
                    return self._existing_schema_mode
            else:
                # Use sync connection for SQLite/MySQL
                connection = self._get_database_connection()
                if connection is None:
                    return False

                # Try a simple query to validate connection
                try:
                    if hasattr(connection, "execute"):
                        # For direct database connections
                        cursor = connection.cursor()
                        cursor.execute("SELECT 1")
                        result = cursor.fetchone()
                        cursor.close()
                        connection.close()
                        return result is not None
                    else:
                        # For connection wrappers
                        return True
                except Exception as query_error:
                    logger.debug(f"Database query test failed: {query_error}")
                    if hasattr(connection, "close"):
                        connection.close()
                    # In existing_schema_mode, be more lenient with connection issues
                    return self._existing_schema_mode

        except Exception as e:
            logger.debug(f"Database connection validation error: {e}")
            # In existing_schema_mode, be more lenient with connection issues
            return self._existing_schema_mode

    def _initialize_cache_integration(self):
        """
        Initialize cache integration components with auto-detection.

        Auto-detects Redis availability and falls back to in-memory cache
        when Redis is not available. Provides transparent query caching
        with automatic invalidation on write operations.
        """
        try:
            from ..cache import (
                CacheBackend,
                CacheInvalidator,
                CacheKeyGenerator,
                create_cache_integration,
            )

            # Get cache configuration
            cache_ttl = getattr(self.config, "cache_ttl", 300)
            cache_max_size = getattr(self.config, "cache_max_size", 1000)
            cache_host = getattr(self.config, "cache_host", "localhost")
            cache_port = getattr(self.config, "cache_port", 6379)
            cache_db = getattr(self.config, "cache_db", 0)
            cache_key_prefix = getattr(self.config, "cache_key_prefix", "dataflow")

            # Build Redis URL if not provided
            redis_url = getattr(self.config, "cache_redis_url", None)
            if redis_url is None:
                redis_url = f"redis://{cache_host}:{cache_port}/{cache_db}"

            # Auto-detect backend (Redis or in-memory)
            cache_manager = CacheBackend.auto_detect(
                redis_url=redis_url,
                ttl=cache_ttl,
                max_size=cache_max_size,
            )

            # Create key generator
            key_generator = CacheKeyGenerator(
                prefix=cache_key_prefix,
                namespace=getattr(self.config, "cache_namespace", None),
            )

            # Create cache invalidator
            invalidator = CacheInvalidator(cache_manager)

            # Create cache integration
            self._cache_integration = create_cache_integration(
                cache_manager, key_generator, invalidator
            )

            # Log which backend was selected
            backend_type = cache_manager.__class__.__name__
            if backend_type == "RedisCacheManager":
                logger.debug(
                    f"Query cache initialized with Redis backend at {mask_sensitive_values(redis_url)}"
                )
            else:
                logger.debug(
                    f"Query cache initialized with in-memory backend "
                    f"(max_size={cache_max_size}, ttl={cache_ttl}s)"
                )

        except Exception as e:
            logger.error(f"Failed to initialize cache integration: {e}")
            self._cache_integration = None

    def _initialize_migration_system(self):
        """Initialize the auto-migration system for SQL databases."""
        try:
            # Get real SQL database connection (async-compatible)
            connection = self._get_async_sql_connection()

            # Determine database dialect from connection URL
            database_url = self.config.database.url or ":memory:"
            if "postgresql" in database_url or "postgres" in database_url:
                dialect = "postgresql"
            elif "mysql" in database_url:
                dialect = "mysql"
            elif "sqlite" in database_url or database_url == ":memory:":
                dialect = "sqlite"
                # SQLite is fully supported for production with enterprise adapter
            else:
                dialect = "unknown"
                logger.warning(
                    "Unsupported database dialect in URL (credentials masked)"
                )

            # Initialize AutoMigrationSystem with async workflow pattern and lock manager integration
            migrations_dir = "migrations"

            # Issue #74: Try local dir first, fall back to tempdir if not writable
            try:
                os.makedirs(migrations_dir, exist_ok=True)
            except (PermissionError, OSError) as dir_err:
                import tempfile

                migrations_dir = os.path.join(
                    tempfile.gettempdir(), "dataflow_migrations"
                )
                os.makedirs(migrations_dir, exist_ok=True)
                logger.warning(
                    "Cannot write to local migrations dir, using %s: %s",
                    migrations_dir,
                    dir_err,
                )

            self._migration_system = AutoMigrationSystem(
                connection_string=self.config.database.get_connection_url(
                    self.config.environment
                ),
                dialect=dialect,
                migrations_dir=migrations_dir,
                dataflow_instance=self,
                lock_timeout=self._migration_lock_timeout,
                runtime=self.runtime,
            )

            logger.debug(f"Migration system initialized successfully for {dialect}")

        except Exception as e:
            # Issue #74: Warn loudly instead of silently disabling
            logger.warning(
                "Migration system unavailable (%s). auto_migrate=True will NOT "
                "detect new columns on existing tables. Schema changes limited to "
                "CREATE TABLE IF NOT EXISTS only. Fix: ensure the migrations "
                "directory is writable or set auto_migrate=False.",
                e,
            )
            self._migration_system = None

    def _initialize_schema_state_manager(self):
        """Initialize the PostgreSQL-optimized schema state management system."""
        try:
            # Get real PostgreSQL database connection (async-compatible)
            connection = self._get_async_sql_connection()

            # Get cache configuration from DataFlow config
            cache_ttl = getattr(
                self.config, "schema_cache_ttl", 300
            )  # 5 minutes default
            cache_max_size = getattr(
                self.config, "schema_cache_max_size", 100
            )  # 100 schemas default

            # Initialize SchemaStateManager with DataFlow instance for WorkflowBuilder pattern
            self._schema_state_manager = SchemaStateManager(
                dataflow_instance=self,
                cache_ttl=cache_ttl,
                cache_max_size=cache_max_size,
            )

            logger.debug(
                "PostgreSQL schema state management system initialized successfully"
            )

        except Exception as e:
            logger.error(f"Failed to initialize schema state management system: {e}")
            self._schema_state_manager = None

    def _initialize_tdd_mode(self):
        """Initialize TDD mode configuration."""
        try:
            # Import TDD support if available
            from ..testing.tdd_support import get_test_context, is_tdd_mode

            if self._test_context:
                # Use provided test context
                logger.debug(
                    f"DataFlow using provided TDD test context: {self._test_context.test_id}"
                )
            elif is_tdd_mode():
                # Get current test context from TDD infrastructure
                self._test_context = get_test_context()
                if self._test_context:
                    logger.debug(
                        f"DataFlow using global TDD test context: {self._test_context.test_id}"
                    )
                else:
                    logger.debug("TDD mode enabled but no test context available")

            # Configure for TDD performance
            if self._test_context:
                # Override connection manager for TDD mode
                self._configure_tdd_connection_manager()

                # Disable expensive operations in TDD mode
                self._tdd_optimizations_enabled = True

                logger.debug(
                    f"DataFlow TDD mode initialized for test {self._test_context.test_id}"
                )

        except ImportError:
            logger.debug("TDD mode requested but TDD support not available")
            self._tdd_mode = False
        except Exception as e:
            logger.error(f"Failed to initialize TDD mode: {e}")
            self._tdd_mode = False

    def _configure_tdd_connection_manager(self):
        """Configure connection manager for TDD mode."""
        if self._test_context and hasattr(self._test_context, "connection"):
            # Store reference to TDD connection
            self._tdd_connection = self._test_context.connection
            logger.debug("DataFlow configured to use TDD connection")

    async def _get_async_database_connection(self):
        """Get database connection, TDD-aware."""
        if self._tdd_mode and hasattr(self, "_tdd_connection") and self._tdd_connection:
            # Return TDD connection for isolated testing
            return self._tdd_connection
        else:
            # Use regular connection manager
            return self._connection_manager.get_async_connection()

    def _initialize_database(self):
        """Initialize database connection and setup."""
        # Initialize connection pool (unless in TDD mode with existing connection)
        if not (self._tdd_mode and self._test_context):
            self._connection_manager.initialize_pool()

        # In a real implementation, this would:
        # 1. Create SQLAlchemy engine with all config options
        # 2. Setup connection pooling with overflow and recycle
        # 3. Initialize session factory
        # 4. Run migrations if needed
        # 5. Setup monitoring if enabled

    def model(self, cls: Type) -> Type:
        """Decorator to register a model with DataFlow.

        This decorator:
        1. Registers the model with DataFlow
        2. Generates CRUD workflow nodes
        3. Sets up database table mapping
        4. Configures indexes and constraints

        Example:
            @db.model
            class User:
                name: str
                email: str
                active: bool = True
        """
        # Validate model
        model_name = cls.__name__

        # Check for duplicate registration
        if model_name in self._models:
            # Enhanced error with catalog-based solutions (DF-602)
            if self.error_enhancer is not None:
                enhanced = self.error_enhancer.enhance_runtime_error(
                    operation="model_registration",
                    original_error=ValueError(
                        f"Model '{model_name}' is already registered. "
                        f"Registered models: {list(self._models.keys())}"
                    ),
                )
                raise enhanced

        # Models without fields are allowed (they might define fields dynamically)

        # Extract model fields from annotations (including inherited)
        fields = {}

        # Collect fields from all parent classes (in method resolution order)
        for base_cls in reversed(cls.__mro__):
            if hasattr(base_cls, "__annotations__"):
                for field_name, field_type in base_cls.__annotations__.items():
                    # Skip private fields (starting with underscore)
                    if field_name.startswith("_"):
                        continue
                    fields[field_name] = {"type": field_type, "required": True}
                    # Check for defaults
                    if hasattr(base_cls, field_name):
                        fields[field_name]["default"] = getattr(base_cls, field_name)
                        fields[field_name]["required"] = False

        # Get model configuration if it exists
        config = {}
        if hasattr(cls, "__dataflow__"):
            config = getattr(cls, "__dataflow__", {})

        # Determine table name - check for __tablename__ override
        table_name = getattr(cls, "__tablename__", None)
        if not table_name:
            table_name = self._class_name_to_table_name(model_name)

        # Register model - store both class and structured info for compatibility
        model_info = {
            "class": cls,
            "fields": fields,
            "config": config,
            "table_name": table_name,
            "registered_at": datetime.now(),
        }

        self._models[model_name] = model_info  # Store structured info
        self._registered_models[model_name] = (
            cls  # Store class for backward compatibility
        )
        self._model_fields[model_name] = fields

        # Persist model in registry for multi-application support
        if self._enable_model_persistence and hasattr(self, "_model_registry"):
            try:
                self._model_registry.register_model(model_name, cls)
            except Exception as e:
                logger.warning(f"Failed to persist model {model_name}: {e}")

        # DATAFLOW-ASYNC-MODEL-DECORATOR-001: Defer relationship detection
        # Instead of calling _auto_detect_relationships() here (which fails in async contexts),
        # we mark the model for deferred processing during initialize().
        # This enables @db.model to work in async fixtures, FastAPI lifespan events, etc.
        self._pending_relationship_detection.add(model_name)

        # Generate workflow nodes (TDD-aware if in TDD mode)
        self._generate_crud_nodes(model_name, fields)
        self._generate_bulk_nodes(model_name, fields)

        # Add DataFlow attributes
        cls._dataflow = self
        cls._dataflow_meta = {
            "engine": self,
            "model_name": model_name,
            "fields": fields,
            "registered_at": datetime.now(),
        }
        cls._dataflow_config = getattr(cls, "__dataflow__", {})

        # TSG-103: Parse __validation__ dict into __field_validators__
        validation_dict = getattr(cls, "__validation__", None)
        if validation_dict is not None:
            from ..validation.dsl import apply_validation_dict

            apply_validation_dict(cls, validation_dict)

        # TSG-106: Register retention policy from __dataflow__["retention"]
        if "retention" in config:
            from ..features.retention import RetentionPolicy

            ret_cfg = config["retention"]
            cutoff_field = ret_cfg.get("cutoff_field")
            if cutoff_field is None:
                # Resolution order: created_at > updated_at > first datetime > error
                for candidate in ("created_at", "updated_at"):
                    if candidate in fields:
                        cutoff_field = candidate
                        break
                if cutoff_field is None:
                    for fname, finfo in fields.items():
                        if finfo.get("type") is datetime:
                            cutoff_field = fname
                            break
                if cutoff_field is None:
                    cutoff_field = "created_at"  # Default; table likely has auto-field

            policy = RetentionPolicy(
                model_name=model_name,
                table_name=table_name,
                policy=ret_cfg.get("policy", "delete"),
                after_days=ret_cfg.get("after_days", 365),
                archive_table=ret_cfg.get("archive_table"),
                cutoff_field=cutoff_field,
            )
            self._retention_engine.register(policy)

        # Add multi-tenant support if enabled
        if self.config.security.multi_tenant:
            if "tenant_id" not in fields:
                fields["tenant_id"] = {"type": str, "required": False}
                cls.__annotations__["tenant_id"] = str

        # Add query_builder class method
        def query_builder(cls):
            """Create a QueryBuilder instance for this model."""
            from ..database.query_builder import create_query_builder

            table_name = self._class_name_to_table_name(cls.__name__)
            return create_query_builder(table_name, self.config.database.url)

        # Bind the method as a classmethod
        cls.query_builder = classmethod(query_builder)

        # Issue #171: Defer table creation until first DB operation (_ensure_connected).
        # @db.model is now metadata-only — it registers the schema and generates nodes
        # but does NOT connect to the database. This allows importing DataFlow models
        # without requiring a live database.
        if self._connected:
            # Already connected — create table immediately (hot-path for models
            # registered after the first query has already triggered connection)
            if self._auto_migrate and not self._existing_schema_mode:
                sync_success = self._create_table_sync(model_name)
                if sync_success:
                    logger.debug(
                        f"Model '{model_name}' registered - table created via sync DDL"
                    )
                else:
                    logger.debug(
                        f"Model '{model_name}' registered - sync DDL failed, "
                        f"table will be created lazily on first access"
                    )
            else:
                logger.debug(
                    f"Model '{model_name}' registered - table will be created lazily on first access"
                )
        else:
            # Not yet connected — queue for deferred creation in _ensure_connected()
            self._pending_table_creations.append(model_name)
            logger.debug(
                f"Model '{model_name}' registered - table creation deferred until first query"
            )

        return cls

    async def ensure_table_exists(self, model_name: str) -> bool:
        """
        Ensure the table for a model exists, creating it if necessary.

        With schema caching enabled (ADR-001), this method:
        1. Checks cache for table existence (0.001ms)
        2. If cached, returns immediately
        3. If not cached, runs full migration checking (~1500ms)
        4. Updates cache after successful check

        This is called lazily when a node first tries to access a table.

        Args:
            model_name: Name of the model

        Returns:
            bool: True if table exists or was created successfully
        """
        self._ensure_connected()
        # ADR-001: Check schema cache first
        database_url = self.config.database.url or ":memory:"

        # Calculate schema checksum if validation enabled
        schema_checksum = None
        if self._schema_cache.enable_schema_validation:
            model_info = self._models.get(model_name)
            if model_info:
                schema_checksum = self._calculate_schema_checksum(model_info["fields"])

        # Check cache
        if self._schema_cache.is_table_ensured(
            model_name, database_url, schema_checksum
        ):
            logger.debug(f"Table '{model_name}' found in cache, skipping check")
            return True

        # Early exit conditions (cache these too)
        if not self._auto_migrate or self._existing_schema_mode:
            logger.debug(
                f"Skipping table creation for '{model_name}' "
                f"(auto_migrate={self._auto_migrate}, "
                f"existing_schema_mode={self._existing_schema_mode})"
            )
            # Mark as ensured in cache (skip mode)
            self._schema_cache.mark_table_ensured(
                model_name, database_url, schema_checksum
            )
            return True

        # Get model info
        model_info = self._models.get(model_name)
        if not model_info:
            logger.error(f"Model '{model_name}' not found in registry")
            return False

        fields = model_info["fields"]

        try:
            # Detect database type and route appropriately
            if "postgresql" in database_url or "postgres" in database_url:
                logger.debug(f"Ensuring PostgreSQL table for model {model_name}")
                await self._execute_postgresql_schema_management_async(
                    model_name, fields
                )
            elif (
                "sqlite" in database_url
                or database_url == ":memory:"
                or database_url.endswith(".db")
            ):
                logger.debug(f"Ensuring SQLite table for model {model_name}")
                # For SQLite, use the migration system to ensure table exists
                if self._migration_system is not None:
                    await self._execute_sqlite_migration_system_async(
                        model_name, fields
                    )
                else:
                    logger.warning(
                        f"No migration system available for SQLite model '{model_name}'"
                    )
                    return False
            else:
                # Unknown database type - try PostgreSQL as fallback
                logger.warning(
                    f"Unknown database type for {database_url}, attempting PostgreSQL schema management"
                )
                await self._execute_postgresql_schema_management_async(
                    model_name, fields
                )

            # ADR-001: Mark as successfully ensured in cache
            self._schema_cache.mark_table_ensured(
                model_name, database_url, schema_checksum
            )

            logger.debug(f"Table for model '{model_name}' ensured successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to ensure table exists for model '{model_name}': {e}")

            # ADR-001: Mark as failed in cache
            self._schema_cache.mark_table_failed(model_name, database_url, str(e))

            return False

    def _get_table_status(self, model_name: str) -> str:
        """
        Get the status of a table for a model.

        ADR-001: Now uses schema cache instead of placeholder.

        Returns:
            str: 'exists', 'needs_creation', or 'unknown'
        """
        database_url = self.config.database.url or ":memory:"

        if self._schema_cache.is_table_ensured(model_name, database_url):
            return "exists"
        else:
            return "needs_creation"

    @property
    def has_pending_migrations(self) -> bool:
        """Check if there are any models that might need table creation."""
        # With lazy table creation, there are no "pending" migrations
        # Tables are created on-demand when first accessed
        return False

    def ensure_migrations_initialized(self) -> bool:
        """
        BACKWARD COMPATIBILITY: Ensure migrations are initialized.

        With lazy table creation, no initialization is needed.
        Tables are created automatically when first accessed.

        Returns:
            bool: Always True since no initialization is required
        """
        # With lazy table creation, no need to initialize anything
        # Tables will be created automatically when first accessed
        return True

    async def _execute_sqlite_migration_system_async(
        self, model_name: str, fields: Dict[str, Any]
    ):
        """Execute SQLite migration system asynchronously - ARCHITECTURAL FIX."""

        table_name = self._class_name_to_table_name(model_name)

        # Build expected table schema from model fields
        dict_schema = {table_name: {"columns": self._convert_fields_to_columns(fields)}}

        # Convert to TableDefinition format expected by migration system
        target_schema = self._convert_dict_schema_to_table_definitions(dict_schema)

        try:
            # Execute migration directly in async context - no event loop issues!
            success, migrations = await self._migration_system.auto_migrate(
                target_schema=target_schema,
                dry_run=False,
                interactive=False,  # Non-interactive for automatic execution
                auto_confirm=True,  # Auto-confirm for seamless operation
            )

            if success:
                logger.debug(
                    f"SQLite table '{table_name}' ready for model '{model_name}'"
                )
            else:
                logger.warning(
                    f"SQLite migration failed for model '{model_name}': {migrations}"
                )

        except Exception as e:
            logger.error(f"SQLite migration error for model '{model_name}': {e}")
            # Don't fail the entire process - table will be created on-demand

    async def _execute_postgresql_schema_management_async(
        self, model_name: str, fields: Dict[str, Any]
    ):
        """Execute PostgreSQL schema management asynchronously - ARCHITECTURAL FIX."""

        # Handle existing_schema_mode - skip all migration activities
        if self._existing_schema_mode:
            logger.debug(
                f"existing_schema_mode=True enabled. Skipping PostgreSQL schema management for model '{model_name}'."
            )
            return

        # Use PostgreSQL-optimized schema state manager if available
        enhanced_success = False
        if self._schema_state_manager is not None:
            try:
                await self._execute_postgresql_enhanced_schema_management_async(
                    model_name, fields
                )
                enhanced_success = True
            except Exception as e:
                logger.warning(
                    f"Enhanced schema management failed for '{model_name}', falling back to migration system: {e}"
                )

        # Fall back to migration system if enhanced failed or unavailable
        if not enhanced_success and self._migration_system is not None:
            await self._execute_postgresql_migration_system_async(model_name, fields)

    async def _execute_postgresql_enhanced_schema_management_async(
        self, model_name: str, fields: Dict[str, Any]
    ):
        """Execute PostgreSQL enhanced schema management asynchronously - ARCHITECTURAL FIX."""

        from ..migrations.schema_state_manager import ModelSchema

        # Build model schema for the specific model being registered
        model_fields = {}
        table_name = self._class_name_to_table_name(model_name)

        for field_name, field_info in fields.items():
            model_fields[field_name] = {
                "type": field_info.get("type", str),
                "required": field_info.get("required", True),
                "default": field_info.get("default"),
            }

        # Use the correct ModelSchema format with tables
        model_schema = ModelSchema(
            tables={
                table_name: {"columns": self._convert_fields_to_columns(model_fields)}
            }
        )

        # The SchemaStateManager doesn't have register_model_schema_async method
        # Instead, use detect_and_plan_migrations for proper schema management
        connection_id = "default"  # Default connection identifier

        try:
            operations, safety = self._schema_state_manager.detect_and_plan_migrations(
                model_schema, connection_id
            )

            # If operations are needed and safe, we should apply them
            # For now, we'll let this fall back to migration system for actual execution
            if operations:
                logger.debug(
                    f"Enhanced schema management detected {len(operations)} operations for '{model_name}', falling back to migration system for execution"
                )
                # Raise exception to trigger fallback to migration system
                # Enhanced error with catalog-based solutions (DF-501)
                message = f"Enhanced schema management requires fallback to migration system for {len(operations)} operations"
                if self.error_enhancer is not None:
                    enhanced = self.error_enhancer.enhance_runtime_error(
                        operation="schema_management_fallback",
                        original_error=Exception(message),
                    )
                    raise enhanced
                else:
                    raise Exception(message)
            else:
                logger.debug(
                    f"PostgreSQL enhanced schema management completed for model '{model_name}' - no operations needed"
                )
        except Exception as e:
            logger.error(
                f"PostgreSQL enhanced schema management error for model '{model_name}': {e}"
            )
            raise  # Re-raise to trigger fallback

    async def _execute_postgresql_migration_system_async(
        self, model_name: str, fields: Dict[str, Any]
    ):
        """Execute PostgreSQL migration system asynchronously - ARCHITECTURAL FIX."""

        table_name = self._class_name_to_table_name(model_name)

        # Build expected table schema from model fields
        dict_schema = {table_name: {"columns": self._convert_fields_to_columns(fields)}}

        # Convert to TableDefinition format expected by migration system
        target_schema = self._convert_dict_schema_to_table_definitions(dict_schema)

        try:
            # Execute migration directly in async context - no event loop issues!
            success, migrations = await self._migration_system.auto_migrate(
                target_schema=target_schema,
                dry_run=False,
                interactive=False,  # Non-interactive for automatic execution
                auto_confirm=True,  # Auto-confirm for seamless operation
            )

            if success:
                logger.debug(
                    f"PostgreSQL migration executed successfully for model '{model_name}'"
                )
                if migrations:
                    for migration in migrations:
                        logger.debug(
                            f"Applied migration {migration.version} with {len(migration.operations)} operations"
                        )
            else:
                logger.warning(
                    f"PostgreSQL migration was not applied for model '{model_name}'"
                )

        except Exception as e:
            logger.error(f"PostgreSQL migration error for model '{model_name}': {e}")

    async def auto_migrate(
        self,
        dry_run: bool = False,
        interactive: bool = True,
        auto_confirm: bool = False,
        target_schema: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, List[Any]]:
        """Run automatic database migration to match registered models.

        This method analyzes the difference between your registered models
        and the current database schema, then applies necessary changes.

        Args:
            dry_run: If True, show what would be changed without applying
            interactive: If True, ask for user confirmation before applying changes
            auto_confirm: If True, automatically confirm all changes (ignores interactive)
            target_schema: Optional specific schema to migrate to (uses registered models if None)

        Returns:
            Tuple of (success: bool, migrations: List[Any])

        Example:
            # Show what would change
            success, migrations = await db.auto_migrate(dry_run=True)

            # Apply changes with confirmation
            success, migrations = await db.auto_migrate()

            # Apply changes automatically (production)
            success, migrations = await db.auto_migrate(auto_confirm=True)
        """
        if self._migration_system is None:
            # Enhanced error with catalog-based solutions (DF-501)
            message = (
                "Auto-migration is not available. Migration system not initialized. "
                "Ensure migration_enabled=True when creating DataFlow instance."
            )
            if self.error_enhancer is not None:
                enhanced = self.error_enhancer.enhance_runtime_error(
                    operation="auto_migrate_init_check",
                    original_error=RuntimeError(message),
                )
                raise enhanced

        # If no target schema provided, build it from registered models
        if target_schema is None:
            dict_schema = {}
            for model_name, model_info in self._models.items():
                table_name = model_info["table_name"]
                fields = model_info["fields"]
                dict_schema[table_name] = {
                    "columns": self._convert_fields_to_columns(fields)
                }

            # Convert dictionary schema to TableDefinition format
            target_schema = self._convert_dict_schema_to_table_definitions(dict_schema)

        # Call the migration system
        return await self._migration_system.auto_migrate(
            target_schema=target_schema,
            dry_run=dry_run,
            interactive=interactive,
            auto_confirm=auto_confirm,
        )

    # ------------------------------------------------------------------
    # Fabric Engine: source registration
    # ------------------------------------------------------------------

    def source(self, name: str, config: Any) -> None:
        """Register an external data source with the fabric engine.

        Sources are external data endpoints (REST APIs, files, cloud storage,
        databases, streams) that products can depend on. Source data is polled
        or pushed via webhooks and cached for product computation.

        Args:
            name: Unique source name. Must not conflict with model names.
            config: Source configuration (RestSourceConfig, FileSourceConfig, etc.)

        Raises:
            ValueError: If name conflicts with a model or another source.
            ValueError: If config validation fails.

        Example::

            db.source("crm", RestSourceConfig(
                url="https://api.example.com",
                auth=BearerAuth(token_env="CRM_API_TOKEN"),
                poll_interval=60,
            ))
        """
        # Validate name uniqueness across models AND sources
        if name in self._models:
            raise ValueError(
                f"Source name '{name}' conflicts with registered model '{name}'. "
                f"Choose a different name."
            )
        if name in self._sources:
            raise ValueError(
                f"Source '{name}' is already registered. "
                f"Registered sources: {list(self._sources.keys())}"
            )

        # Validate config
        if hasattr(config, "validate"):
            config.validate()

        # Create adapter from config
        from dataflow.adapters.source_adapter import BaseSourceAdapter
        from dataflow.fabric.config import (
            CloudSourceConfig,
            DatabaseSourceConfig,
            FileSourceConfig,
            RestSourceConfig,
            StreamSourceConfig,
        )

        adapter: BaseSourceAdapter

        if isinstance(config, RestSourceConfig):
            from dataflow.adapters.rest_adapter import RestSourceAdapter

            adapter = RestSourceAdapter(name, config)
        elif isinstance(config, FileSourceConfig):
            from dataflow.adapters.file_adapter import FileSourceAdapter

            adapter = FileSourceAdapter(name, config)
        elif isinstance(config, CloudSourceConfig):
            from dataflow.adapters.cloud_adapter import CloudSourceAdapter

            adapter = CloudSourceAdapter(name, config)
        elif isinstance(config, DatabaseSourceConfig):
            from dataflow.adapters.database_source_adapter import DatabaseSourceAdapter

            adapter = DatabaseSourceAdapter(name, config)
        elif isinstance(config, StreamSourceConfig):
            from dataflow.adapters.stream_adapter import StreamSourceAdapter

            adapter = StreamSourceAdapter(name, config)
        else:
            raise ValueError(
                f"Unknown source config type: {type(config).__name__}. "
                f"Expected one of: RestSourceConfig, FileSourceConfig, "
                f"CloudSourceConfig, DatabaseSourceConfig, StreamSourceConfig."
            )

        self._sources[name] = {
            "name": name,
            "config": config,
            "adapter": adapter,
        }

        logger.debug(
            "Registered source '%s' (type=%s)",
            name,
            type(config).__name__,
        )

    def get_sources(self) -> Dict[str, Any]:
        """Get all registered sources."""
        return {name: info["config"] for name, info in self._sources.items()}

    def product(
        self,
        name: str,
        mode: str = "materialized",
        depends_on: Optional[List[str]] = None,
        staleness: Optional[Any] = None,
        schedule: Optional[str] = None,
        multi_tenant: bool = False,
        auth: Optional[Dict[str, Any]] = None,
        rate_limit: Optional[Any] = None,
        write_debounce: Optional[Any] = None,
        cache_miss: str = "timeout",
    ) -> Callable:
        """Decorator to register a data product with the fabric engine.

        Products are declarative data transformations that auto-refresh when
        their dependencies (models or sources) change. The decorated function
        receives a FabricContext and returns the product data.

        Args:
            name: Unique product name.
            mode: "materialized" (pre-computed), "parameterized" (on-demand), "virtual" (no cache).
            depends_on: List of model or source names this product reads.
            staleness: StalenessPolicy for cache expiry.
            schedule: Optional cron expression for scheduled refresh.
            multi_tenant: If True, cache is per-tenant.
            auth: Auth config dict (e.g., {"roles": ["admin"]}).
            rate_limit: RateLimit config for request throttling.
            write_debounce: timedelta for debouncing writes.
            cache_miss: Strategy for parameterized cache miss: "timeout" | "async_202" | "inline".

        Example::

            @db.product("dashboard", depends_on=["User", "crm"])
            async def dashboard(ctx):
                users = await ctx.express.list("User")
                deals = await ctx.source("crm").fetch("deals")
                return {"users": len(users), "deals": len(deals)}
        """
        from dataflow.fabric.products import register_product

        def decorator(fn: Callable) -> Callable:
            register_product(
                products=self._products,
                models=self._models,
                sources=self._sources,
                name=name,
                fn=fn,
                mode=mode,
                depends_on=depends_on or [],
                staleness=staleness,
                schedule=schedule,
                multi_tenant=multi_tenant,
                auth=auth,
                rate_limit=rate_limit,
                write_debounce=write_debounce,
                cache_miss=cache_miss,
            )
            return fn

        return decorator

    def get_products(self) -> Dict[str, Any]:
        """Get all registered products."""
        return {name: info for name, info in self._products.items()}

    async def start(
        self,
        fail_fast: bool = True,
        dev_mode: bool = False,
        nexus: Optional[Any] = None,
        coordination: Optional[str] = None,
        host: str = "127.0.0.1",
        port: int = 8000,
        enable_writes: bool = False,
        tenant_extractor: Optional[Callable] = None,
    ) -> Any:
        """Start the fabric runtime — the main entry point for data products.

        This connects all sources, elects a leader, pre-warms materialized
        products, starts change detection, and registers serving endpoints.

        Args:
            fail_fast: Raise on source health check failure.
            dev_mode: Skip pre-warming, in-memory cache, reduced poll intervals.
            nexus: Existing Nexus instance to attach to (production).
            coordination: "redis" or "postgresql". Auto-detects if None.
            host: Bind address for internal server (if no nexus provided).
            port: Port for internal server.
            enable_writes: Enable write pass-through endpoints.
            tenant_extractor: Lambda to extract tenant_id from request.

        Returns:
            The FabricRuntime instance.
        """
        from dataflow.fabric.runtime import FabricRuntime

        redis_url = getattr(self.config, "redis_url", None) or getattr(
            self.config.database, "redis_url", None
        )
        if hasattr(self, "_redis_url"):
            redis_url = self._redis_url or redis_url

        self._fabric = FabricRuntime(
            dataflow=self,
            sources=self._sources,
            products=self._products,
            fail_fast=fail_fast,
            dev_mode=dev_mode,
            redis_url=redis_url,
            host=host,
            port=port,
            enable_writes=enable_writes,
            tenant_extractor=tenant_extractor,
            nexus=nexus,
        )
        await self._fabric.start()
        return self._fabric

    async def stop(self) -> None:
        """Stop the fabric runtime gracefully."""
        if self._fabric is not None:
            await self._fabric.stop()
            self._fabric = None

    @property
    def fabric(self) -> Optional[Any]:
        """Access the running FabricRuntime, or None if not started."""
        return self._fabric

    def set_tenant_context(self, tenant_id: str):
        """Set the current tenant context for multi-tenant operations."""
        if self.config.security.multi_tenant:
            self._tenant_context = {"tenant_id": tenant_id}

    def get_models(self) -> Dict[str, Type]:
        """Get all registered models."""
        # Return just the classes for backward compatibility
        return {name: info["class"] for name, info in self._models.items()}

    def get_model_fields(self, model_name: str) -> Dict[str, Any]:
        """Get field information for a model."""
        return self._model_fields.get(model_name, {})

    def get_tenant_tables(self) -> List[str]:
        """Get list of table names for models that have a tenant_id field.

        Auto-detects tenant-aware tables by checking if each registered model
        has a 'tenant_id' field. This is used by the QueryInterceptor to
        determine which tables need tenant isolation.

        Returns:
            List of table names that require tenant isolation.
        """
        tenant_tables = []
        for model_name, fields in self._model_fields.items():
            if "tenant_id" in fields:
                table_name = self._get_table_name(model_name)
                tenant_tables.append(table_name)
        return tenant_tables

    def get_type_processor(self, model_name: str):
        """Get a TypeAwareFieldProcessor for the given model.

        The TypeAwareFieldProcessor validates field values against model type
        annotations and performs safe type conversions.

        Args:
            model_name: Name of the model

        Returns:
            TypeAwareFieldProcessor instance for the model

        Example:
            >>> processor = db.get_type_processor("User")
            >>> processor.validate_field("id", "user-123")
            'user-123'
        """
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = self._model_fields.get(model_name, {})
        return TypeAwareFieldProcessor(fields, model_name)

    def get_model_info(self, model_name: str) -> Optional[Dict[str, Any]]:
        """Get comprehensive model information.

        Args:
            model_name: Name of the model

        Returns:
            Dictionary with model information or None if model doesn't exist
        """
        if model_name not in self._models:
            return None

        # Return a copy of the stored model info
        return self._models[model_name].copy()

    def list_models(self) -> List[str]:
        """List all registered model names.

        Returns:
            List of model names
        """
        return list(self._models.keys())

    def _sync_models_from_registry(self):
        """Sync models from persistent registry on startup."""
        try:
            if not self._model_registry._initialized:
                self._model_registry.initialize()

            # Skip model discovery and sync during initialization to prevent excessive operations
            # Model sync can be manually triggered when needed via sync_models() on the registry
            # This prevents the auto-migration excessive migration bug where ALL models are processed
            # during every DataFlow initialization
            logger.debug(
                "Skipping model sync during initialization to prevent excessive database operations"
            )
            logger.debug(
                "Use db.get_model_registry().sync_models() to manually sync models when needed"
            )

        except Exception as e:
            logger.error(f"Failed to initialize model registry: {e}")
            # Continue without model sync - don't fail startup

    def _configure_logging(
        self,
        log_level: Optional[int],
        log_config: Optional[LoggingConfig],
    ) -> None:
        """Configure DataFlow logging on initialization (ADR-002).

        This method configures logging FIRST, before any other operations,
        to ensure all DataFlow logging respects the configured levels.

        Args:
            log_level: Optional quick log level override
            log_config: Optional full LoggingConfig for advanced control
        """
        from ..utils.suppress_warnings import configure_dataflow_logging

        if log_config is not None:
            # Use provided full config
            configure_dataflow_logging(log_config)
        elif log_level is not None:
            # Create config with just the level override
            config = LoggingConfig(level=log_level)
            configure_dataflow_logging(config)
        else:
            # Use environment variables or defaults
            configure_dataflow_logging()

    # Public API methods for model registry

    def get_model_registry(self):
        """Get the model registry instance for advanced operations.

        Returns:
            ModelRegistry: The model registry instance

        Example:
            >>> registry = db.get_model_registry()
            >>> issues = registry.validate_consistency()
        """
        if not self._enable_model_persistence:
            # Enhanced error with catalog-based solutions (DF-501)
            if self.error_enhancer is not None:
                enhanced = self.error_enhancer.enhance_runtime_error(
                    operation="feature_check",
                    original_error=RuntimeError(
                        "Model persistence is disabled for this DataFlow instance"
                    ),
                )
                raise enhanced
        return self._model_registry

    def validate_model_consistency(self) -> Dict[str, List[str]]:
        """Validate model consistency across all applications.

        Returns:
            Dictionary mapping model names to list of consistency issues

        Example:
            >>> issues = db.validate_model_consistency()
            >>> if issues:
            ...     print("Model inconsistencies found:", issues)
        """
        if not self._enable_model_persistence:
            return {}
        return self._model_registry.validate_consistency()

    def get_model_history(self, model_name: str) -> List[Dict[str, Any]]:
        """Get version history for a specific model.

        Args:
            model_name: Name of the model

        Returns:
            List of version records with fields, options, timestamps

        Example:
            >>> history = db.get_model_history("User")
            >>> for version in history:
            ...     print(f"Version from {version['created_at']}")
        """
        if not self._enable_model_persistence:
            return []
        return self._model_registry.get_model_history(model_name)

    def sync_models(self, force: bool = False) -> Tuple[int, int]:
        """Manually sync models from the registry.

        Args:
            force: Force re-sync even if models already exist

        Returns:
            Tuple of (models_added, models_updated)

        Example:
            >>> added, updated = db.sync_models()
            >>> print(f"Synced {added} new models, updated {updated}")
        """
        if not self._enable_model_persistence:
            return 0, 0
        return self._model_registry.sync_models(force)

    def get_model_checksums(self) -> Dict[str, Dict[str, str]]:
        """Get model checksums for all registered models by application.

        Returns:
            Dictionary mapping model names to application checksums

        Example:
            >>> checksums = db.get_model_checksums()
            >>> print(checksums)
            # {'User': {'app1': 'abc123', 'app2': 'abc123'}}
        """
        if not self._enable_model_persistence:
            return {}

        checksums = {}
        for model_name in self.list_models():
            app_checksums = self._model_registry._get_model_checksums_by_app(model_name)
            if app_checksums:
                checksums[model_name] = app_checksums
        return checksums

    def get_generated_nodes(self, model_name: str) -> Optional[Dict[str, Any]]:
        """Get generated nodes for a model.

        Args:
            model_name: Name of the model

        Returns:
            Dictionary with generated nodes or None if model doesn't exist
        """
        if model_name not in self._models:
            return None

        # Return the nodes that would be generated for this model
        nodes = {}

        # CRUD operations
        nodes["create"] = f"{model_name}CreateNode"
        nodes["read"] = f"{model_name}ReadNode"
        nodes["update"] = f"{model_name}UpdateNode"
        nodes["delete"] = f"{model_name}DeleteNode"
        nodes["list"] = f"{model_name}ListNode"

        # Bulk operations
        nodes["bulk_create"] = f"{model_name}BulkCreateNode"
        nodes["bulk_update"] = f"{model_name}BulkUpdateNode"
        nodes["bulk_delete"] = f"{model_name}BulkDeleteNode"
        nodes["bulk_upsert"] = f"{model_name}BulkUpsertNode"

        return nodes

    def cleanup_nodes(self, unregister_from_global: bool = True) -> int:
        """Clean up nodes registered by this DataFlow instance.

        ARCHITECTURAL FIX v0.7.5: Solves test isolation and multi-instance issues
        by removing instance-specific nodes from the global NodeRegistry.

        This method addresses the critical bug where multiple DataFlow instances
        with the same model names would overwrite each other's node registrations
        in the global NodeRegistry, causing data leakage between tests.

        Args:
            unregister_from_global: Whether to unregister nodes from NodeRegistry
                                   (default: True for complete cleanup)

        Returns:
            int: Number of nodes cleaned up

        Usage:
            # Test fixture cleanup
            @pytest.fixture
            def dataflow_db(temp_db):
                db = DataFlow(temp_db, auto_migrate=True)
                @db.model
                class User:
                    id: str
                    name: str
                yield db
                db.cleanup_nodes()  # Clean up after test

            # Manual cleanup for multi-instance scenarios
            db1 = DataFlow("sqlite:///db1.db")
            db2 = DataFlow("sqlite:///db2.db")
            # ... use instances ...
            db1.cleanup_nodes()  # Remove db1's nodes
            db2.cleanup_nodes()  # Remove db2's nodes

        Note:
            - Clears self._nodes (instance storage)
            - Optionally unregisters from NodeRegistry (global storage)
            - Safe to call multiple times (idempotent)
            - Does not affect nodes registered by other DataFlow instances

        See:
            - reports/issues/dataflow-global-state-bug/ROOT_CAUSE_ANALYSIS.md
            - tests/integration/test_dataflow_isolation.py
        """
        from kailash.nodes.base import NodeRegistry

        count = len(self._nodes)

        if unregister_from_global and count > 0:
            # Unregister from global NodeRegistry
            node_names = list(self._nodes.keys())
            NodeRegistry.unregister_nodes(node_names)
            logger.debug(
                f"Cleaned up {count} nodes from DataFlow instance {self._instance_id}"
            )

        # Clear instance storage
        self._nodes.clear()

        return count

    def get_instance_id(self) -> str:
        """Get the unique instance ID for this DataFlow instance.

        ARCHITECTURAL FIX v0.7.5: Returns the unique identifier used for
        node namespacing to prevent registration collisions.

        Returns:
            str: Instance ID in format 'df_{memory_address}'

        Usage:
            db1 = DataFlow("sqlite:///db1.db")
            db2 = DataFlow("sqlite:///db2.db")
            print(db1.get_instance_id())  # df_140123456789
            print(db2.get_instance_id())  # df_140123456790

        Note:
            - Instance ID is stable for the lifetime of the DataFlow object
            - Based on memory address, guaranteed unique per instance
            - Used internally by NodeGenerator for namespacing

        See:
            - packages/kailash-dataflow/src/dataflow/core/nodes.py (NodeGenerator)
        """
        return self._instance_id

    # ADR-017: Test Mode API - Helper Methods

    def _resolve_test_mode(self, explicit_test_mode: Optional[bool]) -> bool:
        """Resolve test mode from explicit setting, global setting, or auto-detection.

        Priority:
        1. Explicit test_mode parameter (highest)
        2. Global test mode setting
        3. Auto-detection (lowest)

        Args:
            explicit_test_mode: Explicit test mode setting (None, True, False)

        Returns:
            bool: Resolved test mode
        """
        # Priority 1: Explicit parameter
        if explicit_test_mode is not None:
            return explicit_test_mode

        # Priority 2: Global test mode
        with self._global_test_mode_lock:
            if self._global_test_mode is not None:
                return self._global_test_mode

        # Priority 3: Auto-detection
        return self._detect_test_environment()

    def _detect_test_environment(self) -> bool:
        """Detect if running in test environment.

        Detection Strategy:
        1. Check PYTEST_CURRENT_TEST environment variable
        2. Check if 'pytest' in sys.modules
        3. Check if '_' environment variable contains 'pytest'

        Returns:
            bool: True if test environment detected
        """
        import sys

        # Strategy 1: Check PYTEST_CURRENT_TEST (most reliable)
        if os.getenv("PYTEST_CURRENT_TEST") is not None:
            return True

        # Strategy 2: Check if pytest is imported
        if "pytest" in sys.modules:
            return True

        # Strategy 3: Check _ environment variable
        if "pytest" in os.getenv("_", ""):
            return True

        return False

    # ADR-017: Test Mode API - Class Methods

    @classmethod
    def enable_test_mode(cls) -> None:
        """Enable test mode globally for all new DataFlow instances.

        Example:
            >>> DataFlow.enable_test_mode()
            >>> db = DataFlow(":memory:")  # Test mode enabled automatically
        """
        with cls._global_test_mode_lock:
            cls._global_test_mode = True
            logger.debug("DataFlow: Global test mode enabled")

    @classmethod
    def disable_test_mode(cls) -> None:
        """Disable global test mode, reverting to auto-detection.

        Example:
            >>> DataFlow.disable_test_mode()
            >>> db = DataFlow(":memory:")  # Uses auto-detection
        """
        with cls._global_test_mode_lock:
            cls._global_test_mode = None
            logger.debug(
                "DataFlow: Global test mode disabled (auto-detection restored)"
            )

    @classmethod
    def is_test_mode_enabled(cls) -> Optional[bool]:
        """Get current global test mode setting.

        Returns:
            Optional[bool]: True/False if set, None if auto-detection

        Example:
            >>> DataFlow.enable_test_mode()
            >>> DataFlow.is_test_mode_enabled()
            True
        """
        with cls._global_test_mode_lock:
            return cls._global_test_mode

    # ADR-017: Test Mode API - Cleanup Methods

    async def cleanup_stale_pools(self) -> Dict[str, Any]:
        """Proactively detect and cleanup stale connection pools.

        Returns:
            Dict[str, Any]: Cleanup metrics

        Example:
            >>> metrics = await db.cleanup_stale_pools()
            >>> print(f"Cleaned {metrics['stale_pools_cleaned']} pools")
        """
        from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

        start_time = time.time()
        stale_pools_found = 0
        stale_pools_cleaned = 0
        cleanup_failures = 0
        cleanup_errors = []

        try:
            cleaned = await AsyncSQLDatabaseNode._cleanup_closed_loop_pools()
            stale_pools_found = cleaned
            stale_pools_cleaned = cleaned

            if self._test_mode:
                logger.debug(
                    f"DataFlow: Cleaned {cleaned} stale connection pools (test mode)"
                )
        except Exception as e:
            cleanup_failures += 1
            error_msg = f"Stale pool cleanup failed: {str(e)}"
            cleanup_errors.append(error_msg)
            logger.warning(f"DataFlow: {error_msg}", exc_info=True)

        duration_ms = (time.time() - start_time) * 1000

        return {
            "stale_pools_found": stale_pools_found,
            "stale_pools_cleaned": stale_pools_cleaned,
            "cleanup_failures": cleanup_failures,
            "cleanup_errors": cleanup_errors,
            "cleanup_duration_ms": duration_ms,
        }

    async def cleanup_all_pools(self, force: bool = False) -> Dict[str, Any]:
        """Cleanup all connection pools managed by DataFlow.

        WARNING: Destructive operation - closes ALL pools.

        Args:
            force: If True, forcefully close pools

        Returns:
            Dict[str, Any]: Cleanup metrics

        Example:
            >>> metrics = await db.cleanup_all_pools()
            >>> print(f"Cleaned {metrics['pools_cleaned']} pools")
        """
        from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

        start_time = time.time()
        total_pools = len(AsyncSQLDatabaseNode._shared_pools)
        pools_cleaned = 0
        cleanup_failures = 0
        cleanup_errors = []

        try:
            result = await AsyncSQLDatabaseNode.clear_shared_pools(graceful=not force)
            pools_cleaned = result["pools_cleared"]
            cleanup_failures = result["clear_failures"]
            cleanup_errors = result["clear_errors"]

            if self._test_mode:
                logger.debug(
                    f"DataFlow: Cleared all {pools_cleaned} connection pools "
                    f"(test mode, force={force})"
                )
        except Exception as e:
            cleanup_failures = total_pools
            error_msg = f"Pool cleanup failed: {str(e)}"
            cleanup_errors.append(error_msg)
            logger.error(f"DataFlow: {error_msg}", exc_info=True)

        duration_ms = (time.time() - start_time) * 1000

        return {
            "total_pools": total_pools,
            "pools_cleaned": pools_cleaned,
            "cleanup_failures": cleanup_failures,
            "cleanup_errors": cleanup_errors,
            "cleanup_duration_ms": duration_ms,
            "forced": force,
        }

    def get_cleanup_metrics(self) -> Dict[str, Any]:
        """Get connection pool lifecycle metrics.

        Returns:
            Dict[str, Any]: Pool metrics

        Example:
            >>> metrics = db.get_cleanup_metrics()
            >>> print(f"Active pools: {metrics['active_pools']}")
        """
        from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

        shared_pools = AsyncSQLDatabaseNode._shared_pools

        # Extract unique event loop IDs
        event_loop_ids = set()
        for pool_key in shared_pools.keys():
            loop_id = pool_key.split("|")[0]
            try:
                event_loop_ids.add(int(loop_id))
            except (ValueError, IndexError):
                pass

        return {
            "active_pools": len(shared_pools),
            "total_pools_created": getattr(
                AsyncSQLDatabaseNode, "_total_pools_created", len(shared_pools)
            ),
            "test_mode_enabled": self._test_mode,
            "aggressive_cleanup_enabled": self._test_mode_aggressive_cleanup,
            "pool_keys": list(shared_pools.keys()),
            "event_loop_ids": list(event_loop_ids),
        }

    # Context manager support

    def __enter__(self):
        """Enter context manager for automatic cleanup.

        ARCHITECTURAL FIX v0.7.5: Provides automatic node cleanup via
        context manager pattern for superior developer experience.

        This eliminates the need for manual cleanup_nodes() calls and
        provides idiomatic Python resource management.

        Returns:
            DataFlow: The DataFlow instance

        Usage:
            # Automatic cleanup with context manager (RECOMMENDED)
            with DataFlow("sqlite:///test.db", auto_migrate=True) as db:
                @db.model
                class User:
                    id: str
                    name: str

                # Use db normally...
                workflow = WorkflowBuilder()
                workflow.add_node("UserCreateNode", "create", {...})
                runtime = LocalRuntime()
                runtime.execute(workflow.build())

            # Cleanup happens automatically when exiting context

            # Pytest fixture usage
            @pytest.fixture
            def dataflow_db(temp_db):
                with DataFlow(temp_db, auto_migrate=True) as db:
                    @db.model
                    class User:
                        id: str
                        name: str
                    yield db
                # Automatic cleanup - no cleanup_nodes() needed!

        Note:
            - Cleanup occurs even if exceptions are raised
            - Compatible with yield in pytest fixtures
            - Can still use cleanup_nodes() manually if preferred
            - Exception propagation is not suppressed

        See:
            - __exit__() for cleanup implementation
            - cleanup_nodes() for manual cleanup alternative
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager - perform automatic cleanup.

        ARCHITECTURAL FIX v0.7.5: Automatically cleans up nodes registered
        by this DataFlow instance when exiting the context manager.

        Args:
            exc_type: Exception type (if exception occurred)
            exc_val: Exception value (if exception occurred)
            exc_tb: Exception traceback (if exception occurred)

        Returns:
            bool: False (does not suppress exceptions)

        Behavior:
            - Calls cleanup_nodes() to unregister all instance nodes
            - Logs cleanup action
            - Does not suppress exceptions (returns False)
            - Safe to call even if cleanup_nodes() was already called

        Note:
            Exception handling:
            - If an exception occurred during the with block, it will be
              re-raised after cleanup
            - Cleanup exceptions are logged but do not prevent the original
              exception from propagating
            - This ensures proper resource cleanup even on errors

        See:
            - __enter__() for context manager entry
            - cleanup_nodes() for the actual cleanup logic
        """
        try:
            # Perform node cleanup
            count = self.cleanup_nodes()
            if count > 0:
                logger.debug(
                    f"Context manager cleaned up {count} nodes from "
                    f"DataFlow instance {self._instance_id}"
                )
        except Exception as cleanup_error:
            # Log cleanup errors but don't suppress original exception
            logger.error(
                f"Error during context manager cleanup: {cleanup_error}",
                exc_info=True,
            )

        # Also close database connections and resources
        try:
            self.close()
        except Exception as close_error:
            logger.error(
                f"Error closing database connections: {close_error}",
                exc_info=True,
            )

        # Return False to propagate any exceptions that occurred in the with block
        return False

    def __del__(self):
        """Emit ResourceWarning if DataFlow was not properly closed."""
        if not getattr(self, "_closed", True):
            warnings.warn(
                f"Unclosed DataFlow instance {getattr(self, '_instance_id', '?')}. "
                "Use 'with DataFlow(...) as db:' or call db.close().",
                ResourceWarning,
                source=self,
            )
            try:
                self.close()
            except Exception:
                pass

    def get_connection_pool(self):
        """Get the connection pool for testing.

        Warning:
            This method returns a MockConnectionPool for backward compatibility.
            In v0.7.0+, MockConnectionPool has been moved to tests.fixtures.mock_helpers.
            Consider using real connection pooling in production code.
        """
        # Import from test fixtures
        try:
            from tests.fixtures.mock_helpers import MockConnectionPool
        except ImportError:
            # Fallback for cases where tests module is not available
            import warnings

            warnings.warn(
                "MockConnectionPool could not be imported from tests.fixtures.mock_helpers. "
                "Using inline fallback. This is deprecated and will be removed in v0.8.0.",
                DeprecationWarning,
                stacklevel=2,
            )

            # Inline fallback implementation
            class MockConnectionPool:
                def __init__(self, connection_manager):
                    self.connection_manager = connection_manager
                    self.max_connections = connection_manager._connection_stats.get(
                        "pool_size", 10
                    )

                async def get_metrics(self):
                    return {
                        "connections_created": 1,
                        "connections_reused": 5,
                        "active_connections": 1,
                        "total_connections": self.max_connections,
                    }

                async def get_health_status(self):
                    return {
                        "status": "healthy",
                        "total_connections": self.max_connections,
                        "active_connections": 1,
                    }

        return MockConnectionPool(self._connection_manager)

    def get_connection_info(self) -> Dict[str, Any]:
        """Get connection information.

        Returns:
            Dictionary with connection details
        """
        return {
            "database_url": self.config.database.url or "sqlite:///:memory:",
            "pool_size": self.config.database.pool_size,
            "max_overflow": self.config.database.max_overflow,
            "pool_recycle": self.config.database.pool_recycle,
            "echo": self.config.database.echo,
            "environment": (
                self.config.environment.value
                if hasattr(self.config.environment, "value")
                else str(self.config.environment)
            ),
            "multi_tenant": self.config.security.multi_tenant,
            "monitoring_enabled": getattr(self.config, "monitoring_enabled", False),
        }

    # Public API for feature modules
    @property
    def bulk(self) -> BulkOperations:
        """Access bulk operations."""
        return self._bulk_operations

    @property
    def transactions(self) -> TransactionManager:
        """Access transaction manager."""
        return self._transaction_manager

    @property
    def connection(self) -> ConnectionManager:
        """Access connection manager."""
        return self._connection_manager

    @property
    def tenants(self) -> Optional[MultiTenantManager]:
        """Access multi-tenant manager (if enabled)."""
        return self._multi_tenant_manager

    @property
    def cache(self):
        """Access cache integration (if enabled)."""
        return self._cache_integration

    @property
    def express(self) -> ExpressDataFlow:
        """Access ExpressDataFlow for high-performance direct node invocation.

        ExpressDataFlow provides 23x faster CRUD operations by bypassing
        workflow construction overhead. Ideal for simple CRUD operations
        in performance-critical paths.

        Features:
        - Direct node invocation (no WorkflowBuilder overhead)
        - Built-in LRU caching with TTL
        - Automatic cache invalidation on writes
        - Performance metrics tracking

        Example:
            # Read a user (23x faster than workflow)
            user = await db.express.read("User", "user-123")

            # Create a user
            user = await db.express.create("User", {"id": "user-456", "name": "Alice"})

            # List users with filters
            users = await db.express.list("User", {"active": True}, limit=10)

            # Get cache statistics
            stats = db.express.get_cache_stats()

        Returns:
            ExpressDataFlow: High-performance CRUD interface
        """
        self._ensure_connected()
        return self._express_dataflow

    @property
    def express_sync(self) -> SyncExpress:
        """Access SyncExpress for synchronous CRUD operations.

        SyncExpress wraps the async ExpressDataFlow methods with synchronous
        equivalents for use in CLI scripts, synchronous handlers, and pytest
        without asyncio.

        Example:
            user = db.express_sync.create("User", {"id": "u1", "name": "Alice"})
            user = db.express_sync.read("User", "u1")
            users = db.express_sync.list("User", filter={"active": True})
            count = db.express_sync.count("User")

        Returns:
            SyncExpress: Synchronous CRUD interface
        """
        self._ensure_connected()
        if not hasattr(self, "_express_sync") or self._express_sync is None:
            self._express_sync = SyncExpress(self._express_dataflow)
        return self._express_sync

    @property
    def retention(self):
        """Access the RetentionEngine for data retention policies.

        Policies are registered automatically during ``@db.model``
        decoration when ``__dataflow__["retention"]`` is present.

        Example:
            results = await db.retention.run()
            results = await db.retention.run(dry_run=True)
            status = db.retention.status()

        Returns:
            RetentionEngine
        """
        return self._retention_engine

    # ------------------------------------------------------------------
    # TSG-100: Derived models
    # ------------------------------------------------------------------

    def derived_model(
        self,
        sources: List[str],
        refresh: str = "manual",
        schedule: Optional[str] = None,
        debounce_ms: float = 100.0,
    ):
        """Decorator to register a derived model with DataFlow.

        The decorated class receives full ``@db.model`` treatment first
        (table creation, 11 CRUD nodes), then is registered as a derived
        model with the ``DerivedModelEngine``.

        The class **must** define a ``compute`` static/class method:

            @staticmethod
            def compute(sources: Dict[str, List[Dict]]) -> List[Dict]:
                ...

        .. warning::

            DerivedModel loads all source records into memory.  For tables
            exceeding available RAM, use SQL materialized views directly.

        Args:
            sources: List of source model names (e.g., ``["Order", "LineItem"]``).
            refresh: ``"scheduled"``, ``"manual"`` (default), or
                ``"on_source_change"`` for automatic event-driven refresh.
            schedule: Cron expression or interval string (e.g., ``"every 6h"``,
                ``"0 */6 * * *"``).  Required when ``refresh="scheduled"``.
            debounce_ms: Debounce window in milliseconds for
                ``on_source_change`` mode (default 100ms).  Multiple writes
                within this window are coalesced into a single recompute.

        Example::

            @db.derived_model(sources=["Order", "LineItem"], refresh="manual")
            class OrderSummary:
                id: str
                order_count: int
                total_revenue: float

                @staticmethod
                def compute(sources):
                    orders = sources["Order"]
                    return [{"id": "summary", "order_count": len(orders),
                             "total_revenue": sum(o.get("amount", 0) for o in orders)}]
        """
        from ..features.derived import DerivedModelMeta

        def decorator(cls: type) -> type:
            # Apply @db.model first -- gives table, CRUD nodes, etc.
            cls = self.model(cls)

            # Validate compute method exists
            compute_fn = getattr(cls, "compute", None)
            if compute_fn is None or not callable(compute_fn):
                raise TypeError(
                    f"Derived model '{cls.__name__}' must define a callable "
                    f"'compute(sources)' static method."
                )

            if refresh == "scheduled" and not schedule:
                raise ValueError(
                    f"Derived model '{cls.__name__}' with refresh='scheduled' "
                    f"requires a 'schedule' parameter."
                )

            meta = DerivedModelMeta(
                model_name=cls.__name__,
                sources=list(sources),
                refresh=refresh,
                schedule=schedule,
                compute_fn=compute_fn,
                debounce_ms=debounce_ms,
            )
            self._derived_engine.register(meta)
            return cls

        return decorator

    async def refresh_derived(self, model_name: str):
        """Manually trigger a refresh for a derived model.

        Args:
            model_name: The name of the derived model to refresh.

        Returns:
            RefreshResult with upsert count and timing information.
        """
        return await self._derived_engine.refresh(model_name)

    def refresh_derived_sync(self, model_name: str):
        """Synchronous variant of :meth:`refresh_derived`.

        Uses ``async_safe_run`` to bridge async/sync contexts safely.
        """
        from dataflow.core.async_utils import async_safe_run

        return async_safe_run(self._derived_engine.refresh(model_name))

    def derived_model_status(self) -> Dict[str, Any]:
        """Return metadata for all registered derived models.

        Returns:
            ``{model_name: DerivedModelMeta}`` mapping.
        """
        return self._derived_engine.status()

    async def validate(self, model_name: str, data: Dict[str, Any]):
        """Validate data against a model's field validators.

        Args:
            model_name: Name of the registered model.
            data: Dict of field values to validate.

        Returns:
            ValidationResult from ``dataflow.validation.result``.
        """
        from ..validation.decorators import validate_model as _validate_instance
        from ..validation.result import ValidationResult

        model_info = self._models.get(model_name)
        if model_info is None:
            raise ValueError(f"Model '{model_name}' is not registered")

        model_cls = model_info["class"]
        validators = getattr(model_cls, "__field_validators__", [])
        if not validators:
            return ValidationResult()

        # Build a lightweight object with the data as attributes
        class _Proxy:
            pass

        proxy = _Proxy()
        for k, v in data.items():
            setattr(proxy, k, v)
        # Set the class-level validators so validate_model sees them
        _Proxy.__field_validators__ = validators

        return _validate_instance(proxy)

    def validate_sync(self, model_name: str, data: Dict[str, Any]):
        """Synchronous wrapper for :meth:`validate`."""
        return async_safe_run(self.validate(model_name, data))

    @property
    def schema_state_manager(self):
        """Access schema state management system (if enabled)."""
        return self._schema_state_manager

    @property
    def tenant_context(self) -> "TenantContextSwitch":
        """Access tenant context switching API for multi-tenant operations.

        Provides runtime context switching for multi-tenant applications,
        allowing safe switching between tenant contexts with guaranteed
        data isolation.

        Features:
        - Sync and async context managers for tenant switching
        - Automatic context restoration on exit (even on exception)
        - Tenant registration, activation, and deactivation
        - Statistics tracking for context switches

        Example:
            # Register tenants
            db.tenant_context.register_tenant("tenant-a", "Tenant A")
            db.tenant_context.register_tenant("tenant-b", "Tenant B")

            # Switch context for operations
            with db.tenant_context.switch("tenant-a"):
                # All operations here are in tenant-a context
                user = db.express.create("User", {"name": "Alice"})

            # Async context switching
            async with db.tenant_context.aswitch("tenant-b"):
                # Async operations in tenant-b context
                ...

            # Check current tenant
            current = db.tenant_context.get_current_tenant()

            # Get statistics
            stats = db.tenant_context.get_stats()

        Returns:
            TenantContextSwitch: Tenant context switching interface

        See Also:
            TenantContextSwitch for context switching capabilities
        """
        from .tenant_context import TenantContextSwitch

        return self._tenant_context_switch

    def _inspect_database_schema(self) -> Dict[str, Any]:
        """Internal method to inspect database schema.

        Returns:
            Raw schema information from database inspection.
        """
        # WARNING: This method returns hardcoded mock data by default
        logger.warning(
            "_inspect_database_schema() returns mock data by default. "
            "It does NOT inspect your actual database schema. Use use_real_inspection=True "
            "in discover_schema() for real database introspection."
        )

        # Return hardcoded mock schema for backward compatibility
        return {
            "users": {
                "columns": [
                    {
                        "name": "id",
                        "type": "integer",
                        "primary_key": True,
                        "nullable": False,
                    },
                    {"name": "name", "type": "varchar", "nullable": False},
                    {
                        "name": "email",
                        "type": "varchar",
                        "unique": True,
                        "nullable": False,
                    },
                    {"name": "created_at", "type": "timestamp", "nullable": False},
                ],
                "relationships": {
                    "orders": {"type": "has_many", "foreign_key": "user_id"}
                },
            },
            "orders": {
                "columns": [
                    {
                        "name": "id",
                        "type": "integer",
                        "primary_key": True,
                        "nullable": False,
                    },
                    {"name": "user_id", "type": "integer", "nullable": False},
                    {"name": "total", "type": "decimal", "nullable": False},
                    {"name": "status", "type": "varchar", "default": "pending"},
                ],
                "relationships": {
                    "user": {"type": "belongs_to", "foreign_key": "user_id"}
                },
                "foreign_keys": [
                    {
                        "column_name": "user_id",
                        "foreign_table_name": "users",
                        "foreign_column_name": "id",
                    }
                ],
            },
        }

    def _map_postgresql_type_to_python(self, pg_type: str) -> str:
        """Map PostgreSQL data types to Python types.

        Args:
            pg_type: PostgreSQL data type name

        Returns:
            Python type name as string
        """
        # Comprehensive PostgreSQL type mapping
        TYPE_MAPPING = {
            # Integer types
            "integer": "int",
            "bigint": "int",
            "smallint": "int",
            "serial": "int",
            "bigserial": "int",
            "smallserial": "int",
            # Floating point types
            "numeric": "float",
            "decimal": "float",
            "real": "float",
            "double precision": "float",
            "money": "float",
            # String types
            "character varying": "str",
            "varchar": "str",
            "character": "str",
            "char": "str",
            "text": "str",
            # Boolean
            "boolean": "bool",
            # Date/Time types
            "timestamp": "datetime",
            "timestamp without time zone": "datetime",
            "timestamp with time zone": "datetime",
            "timestamptz": "datetime",
            "date": "date",
            "time": "time",
            "time without time zone": "time",
            "time with time zone": "time",
            "timetz": "time",
            "interval": "timedelta",
            # JSON types
            "json": "dict",
            "jsonb": "dict",
            # Other types
            "uuid": "str",
            "bytea": "bytes",
            "array": "list",
            "inet": "str",
            "cidr": "str",
            "macaddr": "str",
            "tsvector": "str",
            "tsquery": "str",
            "xml": "str",
        }

        # Handle array types
        if pg_type.endswith("[]"):
            return "list"

        # Normalize type name
        normalized_type = pg_type.lower()

        # Return mapped type or default to str
        return TYPE_MAPPING.get(normalized_type, "str")

    async def _inspect_database_schema_real(self) -> Dict[str, Any]:
        """Actually inspect database schema using database-specific system catalogs.

        This method performs real database introspection using PostgreSQL's
        information_schema or SQLite's sqlite_master table.

        Returns:
            Dictionary containing actual database schema information

        Raises:
            ConnectionError: If database connection fails
            QueryError: If schema introspection queries fail
            NotImplementedError: For unsupported databases
        """
        database_url = self.config.database.url or ":memory:"

        # Check database type and route to appropriate inspector
        if "postgresql" in database_url or "postgres" in database_url:
            return await self._inspect_postgresql_schema_real(database_url)
        elif (
            "sqlite" in database_url
            or database_url == ":memory:"
            or database_url.endswith(".db")
        ):
            return await self._inspect_sqlite_schema_real(database_url)
        else:
            # Extract scheme from URL for better error message
            try:
                scheme = (
                    database_url.split("://")[0] if "://" in database_url else "unknown"
                )
            except Exception:
                scheme = "unknown"

            # Enhanced error with catalog-based solutions (DF-501)
            message = (
                f"Real schema discovery is currently supported for PostgreSQL and SQLite only. "
                f"Database URL uses unsupported scheme: {scheme}. MongoDB uses flexible schema and doesn't require schema discovery."
            )
            if self.error_enhancer is not None:
                enhanced = self.error_enhancer.enhance_runtime_error(
                    operation="schema_discovery_unsupported_db",
                    original_error=NotImplementedError(message),
                )
                raise enhanced

    async def _inspect_postgresql_schema_real(
        self, database_url: str
    ) -> Dict[str, Any]:
        """Inspect PostgreSQL database schema using information_schema.

        Args:
            database_url: PostgreSQL connection string

        Returns:
            Dictionary containing PostgreSQL schema information
        """

        try:
            # Get PostgreSQL adapter for real introspection
            from ..adapters.postgresql import PostgreSQLAdapter

            adapter = PostgreSQLAdapter(database_url)
            await adapter.create_connection_pool()

            schema = {}

            # Get all tables
            tables_query = adapter.get_tables_query()
            tables_result = await adapter.execute_query(tables_query)

            for table_row in tables_result:
                table_name = table_row["table_name"]

                # Get columns for this table
                columns_query = adapter.get_columns_query(table_name)
                columns_result = await adapter.execute_query(columns_query)

                columns = []
                for col in columns_result:
                    column_info = {
                        "name": col["column_name"],
                        "type": self._normalize_postgresql_type(col["data_type"]),
                        "nullable": col["is_nullable"] == "YES",
                        "primary_key": False,  # Will be updated below
                    }

                    if col["column_default"]:
                        column_info["default"] = col["column_default"]

                    if col["character_maximum_length"]:
                        column_info["max_length"] = col["character_maximum_length"]

                    columns.append(column_info)

                # Get primary keys
                pk_query = """
                    SELECT kcu.column_name
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu
                        ON tc.constraint_name = kcu.constraint_name
                        AND tc.table_schema = kcu.table_schema
                    WHERE tc.constraint_type = 'PRIMARY KEY'
                        AND tc.table_schema = 'public'
                        AND tc.table_name = $1
                """
                pk_result = await adapter.execute_query(pk_query, [table_name])
                pk_columns = {row["column_name"] for row in pk_result}

                # Update primary key flags
                for col in columns:
                    if col["name"] in pk_columns:
                        col["primary_key"] = True

                # Get foreign keys
                fk_query = """
                    SELECT
                        kcu.column_name,
                        ccu.table_name AS foreign_table_name,
                        ccu.column_name AS foreign_column_name,
                        tc.constraint_name
                    FROM information_schema.table_constraints AS tc
                    JOIN information_schema.key_column_usage AS kcu
                        ON tc.constraint_name = kcu.constraint_name
                        AND tc.table_schema = kcu.table_schema
                    JOIN information_schema.constraint_column_usage AS ccu
                        ON ccu.constraint_name = tc.constraint_name
                        AND ccu.table_schema = tc.table_schema
                    WHERE tc.constraint_type = 'FOREIGN KEY'
                        AND tc.table_schema = 'public'
                        AND tc.table_name = $1
                """
                fk_result = await adapter.execute_query(fk_query, [table_name])

                foreign_keys = []
                relationships = {}

                for fk in fk_result:
                    foreign_keys.append(
                        {
                            "column_name": fk["column_name"],
                            "foreign_table_name": fk["foreign_table_name"],
                            "foreign_column_name": fk["foreign_column_name"],
                            "constraint_name": fk["constraint_name"],
                        }
                    )

                    # Create belongs_to relationship
                    rel_name = self._foreign_key_to_relationship_name(fk["column_name"])
                    relationships[rel_name] = {
                        "type": "belongs_to",
                        "target_table": fk["foreign_table_name"],
                        "foreign_key": fk["column_name"],
                        "target_key": fk["foreign_column_name"],
                    }

                # Get indexes
                indexes_query = """
                    SELECT
                        indexname as index_name,
                        indexdef as index_definition
                    FROM pg_indexes
                    WHERE schemaname = 'public'
                        AND tablename = $1
                        AND indexname NOT LIKE '%_pkey'
                """
                indexes_result = await adapter.execute_query(
                    indexes_query, [table_name]
                )

                indexes = []
                for idx in indexes_result:
                    # Parse index definition to extract columns and uniqueness
                    index_def = idx["index_definition"]
                    is_unique = "UNIQUE" in index_def.upper()

                    indexes.append(
                        {
                            "name": idx["index_name"],
                            "unique": is_unique,
                            "definition": index_def,
                        }
                    )

                schema[table_name] = {
                    "columns": columns,
                    "foreign_keys": foreign_keys,
                    "relationships": relationships,
                    "indexes": indexes,
                }

            await adapter.close_connection_pool()

            # Add reverse has_many relationships
            self._add_reverse_relationships_real(schema)

            logger.debug(
                f"Real schema discovery completed. Found {len(schema)} tables."
            )
            return schema

        except Exception as e:
            logger.error(f"PostgreSQL schema discovery failed: {e}")
            raise

    async def _inspect_sqlite_schema_real(self, database_url: str) -> Dict[str, Any]:
        """Inspect SQLite database schema using sqlite_master table.

        Args:
            database_url: SQLite connection string or ":memory:"

        Returns:
            Dictionary containing SQLite schema information

        Raises:
            NotImplementedError: For in-memory SQLite databases (schema discovery not supported)
        """
        # Check if this is a memory database
        if database_url == ":memory:" or "memory" in database_url.lower():
            # Enhanced error with catalog-based solutions (DF-501)
            message = (
                "Schema discovery is not supported for in-memory SQLite databases. "
                "Only file-based SQLite databases support schema discovery."
            )
            if self.error_enhancer is not None:
                enhanced = self.error_enhancer.enhance_runtime_error(
                    operation="schema_discovery_memory_db",
                    original_error=NotImplementedError(message),
                )
                raise enhanced

        try:
            # Get SQLite adapter for real introspection
            from ..adapters.sqlite import SQLiteAdapter

            adapter = SQLiteAdapter(database_url)
            await adapter.connect()

            schema = {}

            # Get all tables (excluding SQLite system tables and DataFlow tables)
            tables_query = """
                SELECT name FROM sqlite_master
                WHERE type='table'
                AND name NOT LIKE 'sqlite_%'
                AND name NOT LIKE 'dataflow_%'
                ORDER BY name
            """
            tables_result = await adapter.execute_query(tables_query)

            for table_row in tables_result:
                table_name = table_row["name"]

                # Get columns for this table using PRAGMA table_info
                columns_query = f"PRAGMA table_info({table_name})"
                columns_result = await adapter.execute_query(columns_query)

                columns = []
                for col in columns_result:
                    column_info = {
                        "name": col["name"],
                        "type": self._normalize_sqlite_type(col["type"]),
                        "nullable": not col["notnull"],
                        "primary_key": bool(col["pk"]),
                    }

                    if col["dflt_value"] is not None:
                        column_info["default"] = col["dflt_value"]

                    columns.append(column_info)

                # Get foreign keys using PRAGMA foreign_key_list
                fk_query = f"PRAGMA foreign_key_list({table_name})"
                fk_result = await adapter.execute_query(fk_query)

                foreign_keys = []
                relationships = {}

                for fk in fk_result:
                    foreign_keys.append(
                        {
                            "column_name": fk["from"],
                            "foreign_table_name": fk["table"],
                            "foreign_column_name": fk["to"],
                            "constraint_name": f"fk_{table_name}_{fk['from']}",
                        }
                    )

                    # Create belongs_to relationship
                    rel_name = self._foreign_key_to_relationship_name(fk["from"])
                    relationships[rel_name] = {
                        "type": "belongs_to",
                        "target_table": fk["table"],
                        "foreign_key": fk["from"],
                        "target_key": fk["to"],
                    }

                # Get indexes using PRAGMA index_list and index_info
                indexes_query = f"PRAGMA index_list({table_name})"
                indexes_result = await adapter.execute_query(indexes_query)

                indexes = []
                for idx in indexes_result:
                    # Skip auto-indexes (SQLite internal)
                    if idx["name"].startswith("sqlite_autoindex"):
                        continue

                    indexes.append(
                        {
                            "name": idx["name"],
                            "unique": bool(idx["unique"]),
                            "definition": f"INDEX {idx['name']} ON {table_name}",
                        }
                    )

                schema[table_name] = {
                    "columns": columns,
                    "foreign_keys": foreign_keys,
                    "relationships": relationships,
                    "indexes": indexes,
                }

            await adapter.disconnect()

            # Add reverse has_many relationships
            self._add_reverse_relationships_real(schema)

            logger.debug(
                f"SQLite schema discovery completed. Found {len(schema)} tables."
            )
            return schema

        except Exception as e:
            logger.error(f"SQLite schema discovery failed: {e}")
            raise

    def _normalize_sqlite_type(self, sqlite_type: str) -> str:
        """Normalize SQLite data types to standard types."""
        if not sqlite_type:
            return "text"

        # SQLite type mapping to standard types
        type_mapping = {
            "integer": "integer",
            "int": "integer",
            "bigint": "integer",
            "smallint": "integer",
            "tinyint": "integer",
            "real": "float",
            "double": "float",
            "float": "float",
            "numeric": "decimal",
            "decimal": "decimal",
            "text": "text",
            "varchar": "varchar",
            "char": "char",
            "character": "char",
            "blob": "blob",
            "boolean": "boolean",
            "bool": "boolean",
            "date": "date",
            "datetime": "datetime",
            "timestamp": "timestamp",
            "time": "time",
        }

        # Normalize type name (remove parentheses and parameters)
        normalized_type = sqlite_type.lower().split("(")[0].strip()

        # Return mapped type or default to text (SQLite's default)
        return type_mapping.get(normalized_type, "text")

    def _normalize_postgresql_type(self, pg_type: str) -> str:
        """Normalize PostgreSQL data types to standard types."""
        type_mapping = {
            "character varying": "varchar",
            "character": "char",
            "timestamp without time zone": "timestamp",
            "timestamp with time zone": "timestamptz",
            "double precision": "float",
            "bigint": "integer",
            "smallint": "integer",
            "text": "text",
            "boolean": "boolean",
            "numeric": "decimal",
            "jsonb": "jsonb",
            "json": "json",
            "uuid": "uuid",
            "bytea": "bytea",
        }
        return type_mapping.get(pg_type.lower(), pg_type)

    def _add_reverse_relationships_real(self, schema: Dict[str, Any]) -> None:
        """Add reverse has_many relationships based on discovered foreign keys."""
        for table_name, table_info in schema.items():
            foreign_keys = table_info.get("foreign_keys", [])

            for fk in foreign_keys:
                target_table = fk["foreign_table_name"]
                if target_table in schema:
                    # Add has_many relationship to target table
                    rel_name = table_name  # Use plural table name
                    if "relationships" not in schema[target_table]:
                        schema[target_table]["relationships"] = {}

                    schema[target_table]["relationships"][rel_name] = {
                        "type": "has_many",
                        "target_table": table_name,
                        "foreign_key": fk["column_name"],
                        "target_key": fk["foreign_column_name"],
                    }

    def _inspect_table(self, table_name: str) -> Dict[str, Any]:
        """Inspect a specific table's schema.

        Args:
            table_name: Name of the table to inspect

        Returns:
            Table schema information including columns, keys, etc.
        """
        # This would contain table-specific inspection logic
        # For now, delegate to the full schema inspection
        schema = self._inspect_database_schema()
        return schema.get(table_name, {"columns": []})

    def discover_schema(self, use_real_inspection: bool = True) -> Dict[str, Any]:
        """Discover database schema and relationships.

        By default (v0.7.0+), this method performs real database introspection.
        Set use_real_inspection=False for mock data (backward compatibility).

        Args:
            use_real_inspection: If True (default), perform real PostgreSQL database introspection.
                                If False, return mock data for backward compatibility.

        Returns:
            Dictionary containing discovered tables, columns, relationships, and indexes.

        Raises:
            NotImplementedError: When use_real_inspection=True with non-PostgreSQL databases
            ConnectionError: When real inspection fails to connect to database
        """
        if use_real_inspection:
            logger.debug("Starting REAL database schema discovery...")
            try:
                import asyncio

                # Check if we're already in an event loop
                try:
                    loop = asyncio.get_running_loop()
                    if loop.is_running():
                        # We're in a running async context - cannot safely block
                        # This causes deadlocks with session-scoped pytest event loops
                        # because ThreadPoolExecutor + asyncio.run() creates a new event
                        # loop that cannot access connection pools tied to the original loop
                        raise RuntimeError(
                            "discover_schema() cannot be called from a running async context. "
                            "Use 'await discover_schema_async()' instead, or call from a sync context. "
                            "This prevents deadlocks with session-scoped pytest event loops. "
                            "See: DATAFLOW-SESSION-LOOP-DEADLOCK-001"
                        )
                except RuntimeError as e:
                    if "discover_schema() cannot be called" in str(e):
                        # Re-raise our own error
                        raise
                    # No event loop running, safe to use asyncio.run()
                    logger.debug("No existing event loop, using asyncio.run()")
                    discovered_schema = asyncio.run(
                        self._inspect_database_schema_real()
                    )

                return discovered_schema

            except NotImplementedError:
                # Re-raise NotImplementedError - these should not be caught
                raise
            except RuntimeError as e:
                if "discover_schema() cannot be called" in str(e):
                    # Re-raise our async context error
                    raise
                # Other RuntimeErrors fall through to error handling
                logger.error(f"Runtime error during schema discovery: {e}")
                raise
            except (ConnectionError, asyncio.TimeoutError, Exception) as e:
                # Import ConnectionError from adapters if available
                from ..adapters.exceptions import (
                    ConnectionError as DataFlowConnectionError,
                )

                # Check if it's a connection-related error
                if isinstance(
                    e, (DataFlowConnectionError, ConnectionError, asyncio.TimeoutError)
                ):
                    # Only catch connection-related errors for fallback
                    logger.error(
                        f"Real schema discovery failed due to connection error: {e}"
                    )
                    logger.warning("Falling back to mock schema data")
                    # Fall through to mock data below
                else:
                    # Log unexpected errors but don't fallback - let them bubble up
                    logger.error(f"Unexpected error during real schema discovery: {e}")
                    raise
        else:
            logger.warning(
                "discover_schema() is returning MOCK DATA by default. "
                "This does NOT reflect your actual database schema. "
                "Use discover_schema(use_real_inspection=True) for real database introspection."
            )

        logger.debug("Starting mock schema discovery...")

        # Use the common mock data generation method
        discovered_schema = self._generate_mock_schema_data()

        logger.debug(
            f"Schema discovery completed. Found {len(discovered_schema)} tables."
        )
        return discovered_schema

    async def discover_schema_async(
        self, use_real_inspection: bool = False
    ) -> Dict[str, Any]:
        """Async version of discover_schema for use in async contexts.

        This method should be used instead of discover_schema() when calling
        from async contexts (FastAPI endpoints, async tests with session-scoped
        event loops, etc.) to prevent deadlocks.

        Args:
            use_real_inspection: If True, perform real database introspection.
                                If False (default), return mock data.

        Returns:
            Dictionary containing discovered tables, columns, relationships, and indexes.

        Raises:
            NotImplementedError: When use_real_inspection=True with unsupported databases
            ConnectionError: When real inspection fails to connect to database

        Example:
            # In async context (FastAPI, pytest-asyncio with session scope, etc.)
            schema = await db.discover_schema_async(use_real_inspection=True)

            # Instead of (which would deadlock):
            # schema = db.discover_schema(use_real_inspection=True)  # DON'T DO THIS
        """
        if use_real_inspection:
            logger.debug("Starting REAL async database schema discovery...")
            try:
                return await self._inspect_database_schema_real()

            except NotImplementedError:
                # Re-raise NotImplementedError - these should not be caught
                raise
            except (ConnectionError, Exception) as e:
                # Import ConnectionError from adapters if available
                from ..adapters.exceptions import (
                    ConnectionError as DataFlowConnectionError,
                )

                # Check if it's a connection-related error
                if isinstance(e, (DataFlowConnectionError, ConnectionError)):
                    logger.error(
                        f"Real async schema discovery failed due to connection error: {e}"
                    )
                    logger.warning("Falling back to mock schema data")
                    # Fall through to mock data below
                else:
                    logger.error(f"Unexpected error during async schema discovery: {e}")
                    raise
        else:
            logger.warning(
                "discover_schema_async() is returning MOCK DATA by default. "
                "Use discover_schema_async(use_real_inspection=True) for real database introspection."
            )

        # Return mock schema data (same as sync version)
        return self._generate_mock_schema_data()

    def _generate_mock_schema_data(self) -> Dict[str, Any]:
        """Generate mock schema data for backward compatibility.

        Returns:
            Dictionary containing mock schema information.
        """
        # Check if we have custom table inspection (for mocking)
        if hasattr(self, "_custom_table_inspection"):
            tables = self.show_tables(use_real_inspection=False)
            discovered_schema = {}
            for table in tables:
                discovered_schema[table] = self._inspect_table(table)
            return discovered_schema

        # Get the full schema from internal inspection
        discovered_schema = self._inspect_database_schema()

        # Fall back to default schema if no tables found
        if not discovered_schema:
            discovered_schema = {
                "users": {
                    "columns": [
                        {
                            "name": "id",
                            "type": "integer",
                            "primary_key": True,
                            "nullable": False,
                        },
                        {"name": "email", "type": "text", "nullable": False},
                        {"name": "name", "type": "text", "nullable": True},
                        {"name": "created_at", "type": "timestamp", "nullable": True},
                    ],
                    "indexes": [{"name": "users_email_idx", "columns": ["email"]}],
                    "foreign_keys": [],
                },
                "orders": {
                    "columns": [
                        {
                            "name": "id",
                            "type": "integer",
                            "primary_key": True,
                            "nullable": False,
                        },
                        {"name": "user_id", "type": "integer", "nullable": False},
                        {"name": "total", "type": "decimal", "nullable": False},
                        {"name": "status", "type": "text", "nullable": True},
                    ],
                    "indexes": [],
                    "foreign_keys": [
                        {
                            "column": "user_id",
                            "foreign_table_name": "users",
                            "foreign_column_name": "id",
                        }
                    ],
                },
            }

        return discovered_schema

    def show_tables(self, use_real_inspection: bool = True) -> List[str]:
        """Show available tables in the database.

        By default (v0.7.0+), this method queries the actual database for table names.
        Set use_real_inspection=False for mock data (backward compatibility).

        Args:
            use_real_inspection: If True (default), query actual database for table names.
                                If False, return mock table names for backward compatibility.

        Returns:
            List of table names.
        """
        if use_real_inspection:
            try:
                schema = self.discover_schema(use_real_inspection=True)
                return list(schema.keys())
            except Exception as e:
                logger.error(f"Real table discovery failed: {e}")
                logger.warning("Falling back to mock table list")
        else:
            logger.warning(
                "show_tables() is returning MOCK TABLE NAMES. "
                "Use show_tables(use_real_inspection=True) for actual database tables."
            )

        # Get tables from mock schema inspection
        schema = self._inspect_database_schema()
        return list(schema.keys())

    def list_tables(self) -> List[str]:
        """Alias for show_tables to maintain compatibility.

        Returns:
            List of table names.
        """
        return self.show_tables()

    def scaffold(
        self, output_file: str = "models.py", use_real_inspection: bool = False
    ) -> Dict[str, Any]:
        """Generate Python model files from discovered schema.

        WARNING: By default, this method uses hardcoded mock schema.
        Generated models will NOT match your actual database unless
        use_real_inspection=True is specified.

        Args:
            output_file: Path to output file for generated models
            use_real_inspection: If True, generate models from actual database schema.
                                If False (default), generate from mock schema.

        Returns:
            Dictionary with generation results
        """
        if not use_real_inspection:
            logger.warning(
                "scaffold() is using MOCK SCHEMA DATA by default. "
                "Generated models will NOT match your actual database. "
                "Use scaffold(use_real_inspection=True) for models based on real database schema."
            )

        logger.debug(f"Generating models to {output_file}...")

        schema = self.discover_schema(use_real_inspection=use_real_inspection)

        # Generate model file content
        lines = [
            '"""Auto-generated DataFlow models from database schema."""',
            "",
            "from dataflow import DataFlow",
            "from typing import Optional",
            "from datetime import datetime",
            "from decimal import Decimal",
            "",
            "# Initialize DataFlow instance",
            "db = DataFlow()",
            "",
        ]

        generated_models = []
        relationships_detected = 0

        for table_name, table_info in schema.items():
            # Convert table name to class name
            class_name = self._table_name_to_class_name(table_name)
            generated_models.append(class_name)

            lines.extend(
                [
                    "@db.model",
                    f"class {class_name}:",
                    f'    """Model for {table_name} table."""',
                ]
            )

            # Add fields
            for column in table_info.get("columns", []):
                field_name = column["name"]
                field_type = self._sql_type_to_python_type(column["type"])

                # Skip auto-generated fields
                if field_name in ["id", "created_at", "updated_at"] and column.get(
                    "primary_key"
                ):
                    continue

                type_annotation = (
                    field_type.__name__
                    if hasattr(field_type, "__name__")
                    else str(field_type)
                )

                if column.get("nullable", True) and not column.get("primary_key"):
                    type_annotation = f"Optional[{type_annotation}]"

                if "default" in column:
                    if column["default"] is None:
                        lines.append(f"    {field_name}: {type_annotation} = None")
                    elif isinstance(column["default"], str):
                        lines.append(
                            f'    {field_name}: {type_annotation} = "{column["default"]}"'
                        )
                    else:
                        lines.append(
                            f"    {field_name}: {type_annotation} = {column['default']}"
                        )
                else:
                    lines.append(f"    {field_name}: {type_annotation}")

            # Add relationships
            for rel_name, rel_info in table_info.get("relationships", {}).items():
                relationships_detected += 1
                rel_type = rel_info["type"]
                if rel_type == "has_many":
                    lines.append(
                        f'    # {rel_name} = db.has_many("{rel_info.get("target_table", rel_name)}", "{rel_info["foreign_key"]}")'
                    )
                elif rel_type == "belongs_to":
                    lines.append(
                        f'    # {rel_name} = db.belongs_to("{rel_info.get("target_table", rel_name)}", "{rel_info["foreign_key"]}")'
                    )

            lines.append("")

        content = "\n".join(lines)

        # Write to file
        with open(output_file, "w") as f:
            f.write(content)

        result = {
            "generated_models": generated_models,
            "output_file": output_file,
            "relationships_detected": relationships_detected,
            "lines_generated": len(lines),
            "tables_processed": len(schema),
        }

        logger.debug(
            f"Generated {len(generated_models)} models with {relationships_detected} relationships"
        )
        return result

    def register_schema_as_models(
        self, tables: Optional[List[str]] = None, use_real_inspection: bool = True
    ) -> Dict[str, Any]:
        """Register discovered database tables as DataFlow models dynamically.

        This method allows dynamic model registration from existing database schemas,
        enabling workflows to be built without @db.model decorators. Perfect for LLM
        agents and dynamic database discovery scenarios.

        Args:
            tables: Optional list of table names to register. If None, registers all discovered tables.
            use_real_inspection: If True, use real database introspection. If False, use mock data.

        Returns:
            Dictionary with registration results including:
            - registered_models: List of successfully registered model names
            - generated_nodes: Dict mapping model names to their generated node names
            - errors: List of any registration errors

        Example:
            >>> # Register all discovered tables as models
            >>> result = db.register_schema_as_models()
            >>> print(f"Registered {len(result['registered_models'])} models")
            >>>
            >>> # Use generated nodes in workflows
            >>> workflow = WorkflowBuilder()
            >>> user_nodes = result['generated_nodes']['User']
            >>> workflow.add_node(user_nodes['create'], "create_user", {...})
        """
        logger.debug("Starting dynamic model registration from schema...")

        # Discover schema
        schema = self.discover_schema(use_real_inspection=use_real_inspection)

        # Filter tables if specified
        if tables:
            schema = {k: v for k, v in schema.items() if k in tables}

        # Skip DataFlow system tables
        system_tables = {
            "dataflow_migrations",
            "dataflow_model_registry",
            "dataflow_migration_history",
        }
        schema = {k: v for k, v in schema.items() if k not in system_tables}

        registered_models = []
        generated_nodes = {}
        errors = []

        for table_name, table_info in schema.items():
            try:
                # Convert table name to model name
                model_name = self._table_name_to_class_name(table_name)

                # Skip if model already registered
                if model_name in self._models:
                    logger.debug(f"Model {model_name} already registered, skipping")
                    continue

                # Extract fields from table columns
                fields = {}
                columns = table_info.get("columns", {})

                # Handle both list and dict formats for columns
                if isinstance(columns, list):
                    # List format from real inspection
                    for col in columns:
                        field_name = col["name"]
                        field_type = self._map_postgresql_type_to_python(col["type"])

                        # Convert type string to actual Python type
                        type_mapping = {
                            "str": str,
                            "int": int,
                            "float": float,
                            "bool": bool,
                            "datetime": datetime,
                            "date": datetime,
                            "time": datetime,
                            "dict": dict,
                            "list": list,
                            "bytes": bytes,
                        }
                        python_type = type_mapping.get(field_type, str)

                        field_info = {
                            "type": python_type,
                            "required": not col.get("nullable", True),
                            "primary_key": col.get("primary_key", False),
                        }

                        if "default" in col:
                            field_info["default"] = col["default"]
                            field_info["required"] = False

                        fields[field_name] = field_info

                elif isinstance(columns, dict):
                    # Dict format from schema inspection
                    for field_name, col_info in columns.items():
                        field_type = col_info.get("type", "str")

                        # Convert type string to actual Python type
                        type_mapping = {
                            "str": str,
                            "int": int,
                            "float": float,
                            "bool": bool,
                            "datetime": datetime,
                            "date": datetime,
                            "time": datetime,
                            "dict": dict,
                            "list": list,
                            "bytes": bytes,
                            "varchar": str,
                            "text": str,
                            "integer": int,
                            "bigint": int,
                            "boolean": bool,
                            "timestamp": datetime,
                            "decimal": float,
                            "numeric": float,
                            "json": dict,
                            "jsonb": dict,
                        }
                        python_type = type_mapping.get(field_type.lower(), str)

                        field_info = {
                            "type": python_type,
                            "required": not col_info.get("nullable", True),
                            "primary_key": col_info.get("primary_key", False),
                        }

                        if "default" in col_info:
                            field_info["default"] = col_info["default"]
                            field_info["required"] = False

                        fields[field_name] = field_info

                # Create dynamic model class
                model_attrs = {
                    "__name__": model_name,
                    "__module__": "__main__",
                    "__tablename__": table_name,
                    "__annotations__": {},
                }

                # Add field annotations
                for field_name, field_info in fields.items():
                    model_attrs["__annotations__"][field_name] = field_info["type"]
                    # Add default values if specified
                    if "default" in field_info and field_info["default"] is not None:
                        model_attrs[field_name] = field_info["default"]

                # Create the model class dynamically
                DynamicModel = type(model_name, (), model_attrs)

                # Register model (similar to @db.model decorator logic)
                model_info = {
                    "class": DynamicModel,
                    "fields": fields,
                    "config": {},
                    "table_name": table_name,
                    "registered_at": datetime.now(),
                    "dynamic": True,  # Flag to indicate dynamically registered
                }

                self._models[model_name] = model_info
                self._registered_models[model_name] = DynamicModel
                self._model_fields[model_name] = fields

                # Generate workflow nodes
                self._generate_crud_nodes(model_name, fields)
                self._generate_bulk_nodes(model_name, fields)

                # Add DataFlow attributes to dynamic class
                DynamicModel._dataflow = self
                DynamicModel._dataflow_meta = {
                    "engine": self,
                    "model_name": model_name,
                    "fields": fields,
                    "registered_at": datetime.now(),
                }

                # Persist in model registry if enabled
                if self._enable_model_persistence and hasattr(self, "_model_registry"):
                    try:
                        self._model_registry.register_model(model_name, DynamicModel)
                    except Exception as e:
                        logger.warning(
                            f"Failed to persist dynamic model {model_name}: {e}"
                        )

                # Collect generated node names
                generated_nodes[model_name] = self.get_generated_nodes(model_name)
                registered_models.append(model_name)

                logger.debug(
                    f"Successfully registered dynamic model: {model_name} (table: {table_name})"
                )

            except Exception as e:
                error_msg = f"Failed to register model for table {table_name}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)

        result = {
            "registered_models": registered_models,
            "generated_nodes": generated_nodes,
            "errors": errors,
            "total_tables": len(schema),
            "success_count": len(registered_models),
            "error_count": len(errors),
        }

        logger.debug(
            f"Dynamic model registration complete: {result['success_count']} models registered, "
            f"{result['error_count']} errors"
        )

        return result

    def reconstruct_models_from_registry(self) -> Dict[str, Any]:
        """Reconstruct and register models from the model registry.

        This method allows another DataFlow instance to discover models from the registry
        and reconstruct them locally, enabling workflow creation without the original
        @db.model decorated classes.

        Returns:
            Dictionary with reconstruction results including:
            - reconstructed_models: List of successfully reconstructed model names
            - generated_nodes: Dict mapping model names to their generated node names
            - errors: List of any reconstruction errors

        Example:
            >>> # In a new DataFlow instance or session
            >>> db = DataFlow(existing_schema_mode=True)
            >>> result = db.reconstruct_models_from_registry()
            >>>
            >>> # Now you can use the models in workflows
            >>> workflow = WorkflowBuilder()
            >>> user_nodes = result['generated_nodes']['User']
            >>> workflow.add_node(user_nodes['create'], "create_user", {...})
        """
        logger.debug("Starting model reconstruction from registry...")

        if not self._enable_model_persistence:
            return {
                "reconstructed_models": [],
                "generated_nodes": {},
                "errors": ["Model persistence is disabled for this DataFlow instance"],
            }

        # Discover models from registry
        registry_models = self._model_registry.discover_models()

        reconstructed_models = []
        generated_nodes = {}
        errors = []

        for model_name, model_info in registry_models.items():
            try:
                # Skip if model already registered locally
                if model_name in self._models:
                    logger.debug(
                        f"Model {model_name} already registered locally, skipping"
                    )
                    continue

                # Extract model definition
                model_def = model_info.get("definition", {})
                fields = model_def.get("fields", {})

                # Convert stored field info to internal format
                internal_fields = {}
                for field_name, field_info in fields.items():
                    # Map stored type strings back to Python types
                    type_str = field_info.get("type", "str")
                    type_mapping = {
                        "str": str,
                        "int": int,
                        "float": float,
                        "bool": bool,
                        "datetime": datetime,
                        "date": datetime,
                        "time": datetime,
                        "dict": dict,
                        "list": list,
                        "bytes": bytes,
                        "NoneType": type(None),
                    }

                    # Handle module.type format (e.g., "datetime.datetime")
                    if "." in type_str:
                        type_str = type_str.split(".")[-1]

                    python_type = type_mapping.get(type_str, str)

                    internal_fields[field_name] = {
                        "type": python_type,
                        "required": field_info.get("required", True),
                        "primary_key": field_info.get("primary_key", False),
                    }

                    if "default" in field_info:
                        internal_fields[field_name]["default"] = field_info["default"]
                        internal_fields[field_name]["required"] = False

                # Get table name
                table_name = model_def.get(
                    "table_name", self._class_name_to_table_name(model_name)
                )

                # Create dynamic model class
                model_attrs = {
                    "__name__": model_name,
                    "__module__": "__main__",
                    "__tablename__": table_name,
                    "__annotations__": {},
                }

                # Add field annotations
                for field_name, field_info in internal_fields.items():
                    model_attrs["__annotations__"][field_name] = field_info["type"]
                    # Add default values if specified
                    if "default" in field_info and field_info["default"] is not None:
                        model_attrs[field_name] = field_info["default"]

                # Create the model class dynamically
                ReconstructedModel = type(model_name, (), model_attrs)

                # Register model locally
                local_model_info = {
                    "class": ReconstructedModel,
                    "fields": internal_fields,
                    "config": model_def.get("config", {}),
                    "table_name": table_name,
                    "registered_at": datetime.now(),
                    "reconstructed": True,  # Flag to indicate reconstructed from registry
                    "checksum": model_info.get("checksum"),
                }

                self._models[model_name] = local_model_info
                self._registered_models[model_name] = ReconstructedModel
                self._model_fields[model_name] = internal_fields

                # Generate workflow nodes
                self._generate_crud_nodes(model_name, internal_fields)
                self._generate_bulk_nodes(model_name, internal_fields)

                # Add DataFlow attributes to reconstructed class
                ReconstructedModel._dataflow = self
                ReconstructedModel._dataflow_meta = {
                    "engine": self,
                    "model_name": model_name,
                    "fields": internal_fields,
                    "registered_at": datetime.now(),
                    "reconstructed": True,
                }

                # Collect generated node names
                generated_nodes[model_name] = self.get_generated_nodes(model_name)
                reconstructed_models.append(model_name)

                logger.debug(f"Successfully reconstructed model: {model_name}")

            except Exception as e:
                error_msg = f"Failed to reconstruct model {model_name}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)

        result = {
            "reconstructed_models": reconstructed_models,
            "generated_nodes": generated_nodes,
            "errors": errors,
            "total_registry_models": len(registry_models),
            "success_count": len(reconstructed_models),
            "error_count": len(errors),
        }

        logger.debug(
            f"Model reconstruction complete: {result['success_count']} models reconstructed, "
            f"{result['error_count']} errors"
        )

        return result

    def _table_name_to_class_name(self, table_name: str) -> str:
        """Convert table name to Python class name."""
        # Remove underscores and capitalize each word
        words = table_name.split("_")
        class_name = "".join(word.capitalize() for word in words)
        # Remove 's' suffix for singular class names
        if class_name.endswith("s") and len(class_name) > 1:
            class_name = class_name[:-1]
        return class_name

    def _sql_type_to_python_type(self, sql_type: str):
        """Map SQL types to Python types."""
        # Remove parameters from SQL type (e.g., VARCHAR(255) -> VARCHAR)
        base_type = sql_type.split("(")[0].lower()

        type_mappings = {
            "integer": int,
            "bigint": int,
            "smallint": int,
            "serial": int,
            "bigserial": int,
            "varchar": str,
            "text": str,
            "char": str,
            "character": str,
            "numeric": float,
            "decimal": float,
            "real": float,
            "double precision": float,
            "money": float,
            "boolean": bool,
            "timestamp": datetime,
            "timestamptz": datetime,
            "date": datetime,
            "time": datetime,
            "json": dict,
            "jsonb": dict,
            "array": list,
        }
        python_type = type_mappings.get(base_type, str)

        # Special handling for decimal to return string representation
        if base_type == "decimal":
            return "Decimal"

        # Return string representation of type
        return python_type.__name__

    def _python_type_to_sql_type(
        self, python_type, database_type: str = "postgresql"
    ) -> str:
        """Map Python types to SQL types for different databases.

        Args:
            python_type: The Python type (e.g., int, str, datetime, List[str], Dict[str, Any])
            database_type: Target database ('postgresql', 'mysql', 'sqlite')

        Returns:
            SQL type string appropriate for the target database
        """
        from typing import get_args, get_origin

        # Handle Optional types (Union[type, None])
        if hasattr(python_type, "__origin__") and python_type.__origin__ is Union:
            args = python_type.__args__
            if len(args) == 2 and type(None) in args:
                # This is Optional[SomeType], extract the actual type
                actual_type = args[0] if args[1] is type(None) else args[1]
                return self._python_type_to_sql_type(actual_type, database_type)

        # Handle generic types (List[T], Dict[K, V], Set[T], FrozenSet[T], etc.)
        # get_origin(List[str]) returns list, get_origin(Dict[str, Any]) returns dict
        origin = get_origin(python_type)
        if origin is not None:
            # Map generic origins to their base types
            if origin is list:
                python_type = list
            elif origin is dict:
                python_type = dict
            elif origin is set:
                python_type = list  # Store sets as JSON arrays
            elif origin is frozenset:
                python_type = list  # Store frozensets as JSON arrays
            elif origin is tuple:
                python_type = list  # Store tuples as JSON arrays

        # Database-specific type mappings
        type_mappings = {
            "postgresql": {
                int: "INTEGER",
                str: "TEXT",  # Use TEXT instead of VARCHAR(255) for PostgreSQL
                bool: "BOOLEAN",
                float: "REAL",
                datetime: "TIMESTAMP",
                dict: "JSONB",
                list: "JSONB",
                bytes: "BYTEA",
            },
            "mysql": {
                int: "INT",
                str: "VARCHAR(255)",
                bool: "TINYINT(1)",
                float: "DOUBLE",
                datetime: "DATETIME",
                dict: "JSON",
                list: "JSON",
                bytes: "BLOB",
            },
            "sqlite": {
                int: "INTEGER",
                str: "TEXT",
                bool: "INTEGER",  # SQLite doesn't have native boolean
                float: "REAL",
                datetime: "TEXT",  # SQLite stores datetime as text
                dict: "TEXT",  # Store JSON as text
                list: "TEXT",  # Store JSON as text
                bytes: "BLOB",
            },
        }

        mapping = type_mappings.get(database_type.lower(), type_mappings["postgresql"])
        return mapping.get(python_type, "TEXT")

    def _get_sql_column_definition(
        self,
        field_name: str,
        field_info: Dict[str, Any],
        database_type: str = "postgresql",
    ) -> str:
        """Generate SQL column definition from field information.

        Args:
            field_name: Name of the field/column
            field_info: Field metadata from model registration
            database_type: Target database type

        Returns:
            Complete SQL column definition string
        """
        python_type = field_info["type"]
        sql_type = self._python_type_to_sql_type(python_type, database_type)

        # Start building column definition
        definition_parts = [field_name, sql_type]

        # Handle nullable/required
        if field_info.get("required", True):
            definition_parts.append("NOT NULL")

        # Handle default values
        if "default" in field_info:
            default_value = field_info["default"]
            if default_value is not None:
                if isinstance(default_value, str):
                    definition_parts.append(f"DEFAULT '{default_value}'")
                elif isinstance(default_value, bool):
                    if database_type == "postgresql":
                        definition_parts.append(f"DEFAULT {str(default_value).upper()}")
                    elif database_type == "mysql":
                        definition_parts.append(f"DEFAULT {1 if default_value else 0}")
                    else:  # sqlite
                        definition_parts.append(f"DEFAULT {1 if default_value else 0}")
                elif isinstance(default_value, (list, dict)):
                    # Serialize list/dict defaults to JSON with database-specific syntax
                    import json

                    json_str = json.dumps(default_value)
                    # SQL-escape single quotes (replace ' with '' for SQL string literals)
                    json_str_escaped = json_str.replace("'", "''")
                    if database_type == "postgresql":
                        # PostgreSQL: Cast to jsonb type
                        definition_parts.append(f"DEFAULT '{json_str_escaped}'::jsonb")
                    elif database_type == "mysql":
                        # MySQL: Use CAST expression (MySQL 8.0+)
                        definition_parts.append(
                            f"DEFAULT (CAST('{json_str_escaped}' AS JSON))"
                        )
                    else:  # sqlite
                        # SQLite: Store as TEXT (SQLite uses TEXT for JSON storage)
                        definition_parts.append(f"DEFAULT '{json_str_escaped}'")
                elif isinstance(default_value, (int, float)):
                    definition_parts.append(f"DEFAULT {default_value}")
                else:
                    # For other types, try to convert to string safely
                    definition_parts.append(f"DEFAULT '{str(default_value)}'")

        return " ".join(definition_parts)

    def _generate_create_table_sql(
        self,
        model_name: str,
        database_type: str = "postgresql",
        model_fields: Optional[Dict] = None,
    ) -> str:
        """Generate CREATE TABLE SQL statement from model metadata.

        Args:
            model_name: Name of the model class
            database_type: Target database type
            model_fields: Optional model fields dict (if not provided, uses registered model fields)

        Returns:
            Complete CREATE TABLE SQL statement
        """
        # Use the stored table_name from model registration (respects __tablename__)
        # Fall back to _class_name_to_table_name for backward compatibility
        model_info = self._models.get(model_name, {})
        table_name = model_info.get("table_name") or self._class_name_to_table_name(
            model_name
        )
        fields = (
            model_fields
            if model_fields is not None
            else self.get_model_fields(model_name)
        )

        if not fields:
            # Enhanced error with catalog-based solutions (DF-604)
            if ErrorEnhancer is not None:
                raise ErrorEnhancer.enhance_invalid_model_definition(
                    model_name=model_name,
                    validation_error="Model has no fields defined (missing type annotations)",
                )

        # Start building CREATE TABLE statement with safety protection
        sql_parts = [f"CREATE TABLE IF NOT EXISTS {table_name} ("]

        # Check if model has a string ID field
        id_field = fields.get("id", {})
        id_type = id_field.get("type")

        # Add primary key ID column based on type
        if id_type == str:
            # String ID models need user-provided IDs
            if database_type.lower() == "postgresql":
                sql_parts.append("    id TEXT PRIMARY KEY,")
            elif database_type.lower() == "mysql":
                # MySQL doesn't allow TEXT as primary key - use VARCHAR(255)
                sql_parts.append("    id VARCHAR(255) PRIMARY KEY,")
            else:  # sqlite
                sql_parts.append("    id TEXT PRIMARY KEY,")
        else:
            # Integer ID models use auto-increment
            if database_type.lower() == "postgresql":
                sql_parts.append("    id SERIAL PRIMARY KEY,")
            elif database_type.lower() == "mysql":
                sql_parts.append("    id INT AUTO_INCREMENT PRIMARY KEY,")
            else:  # sqlite
                sql_parts.append("    id INTEGER PRIMARY KEY AUTOINCREMENT,")

        # Add model fields
        column_definitions = []
        for field_name, field_info in fields.items():
            # Skip auto-generated fields
            if field_name in ["id", "created_at", "updated_at"]:
                continue

            column_def = self._get_sql_column_definition(
                field_name, field_info, database_type
            )
            column_definitions.append(f"    {column_def}")

        # Add created_at and updated_at timestamp columns
        if database_type.lower() == "postgresql":
            column_definitions.append(
                "    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            )
            column_definitions.append(
                "    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            )
        elif database_type.lower() == "mysql":
            column_definitions.append(
                "    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            )
            column_definitions.append(
                "    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
            )
        else:  # sqlite
            column_definitions.append("    created_at TEXT DEFAULT CURRENT_TIMESTAMP")
            column_definitions.append("    updated_at TEXT DEFAULT CURRENT_TIMESTAMP")

        # Join all column definitions
        sql_parts.extend([",\n".join(column_definitions)])
        sql_parts.append(");")

        return "\n".join(sql_parts)

    def _generate_indexes_sql(
        self, model_name: str, database_type: str = "postgresql"
    ) -> List[str]:
        """Generate CREATE INDEX SQL statements for a model.

        Args:
            model_name: Name of the model class
            database_type: Target database type

        Returns:
            List of CREATE INDEX SQL statements
        """
        table_name = self._class_name_to_table_name(model_name)
        indexes = []

        # Get model configuration for custom indexes
        model_info = self._models.get(model_name)
        if model_info:
            model_cls = model_info.get("class")
            if model_cls and hasattr(model_cls, "__dataflow__"):
                config = getattr(model_cls, "__dataflow__", {})
                custom_indexes = config.get("indexes", [])

                from dataflow.query.models import validate_identifier

                for index_config in custom_indexes:
                    fields = index_config.get("fields", [])
                    if not fields:
                        continue
                    index_name = index_config.get(
                        "name", f"idx_{table_name}_{fields[0]}"
                    )
                    unique = index_config.get("unique", False)

                    # Validate all identifiers before interpolation (C1 fix)
                    validate_identifier(index_name)
                    for f in fields:
                        validate_identifier(f)

                    unique_keyword = "UNIQUE " if unique else ""
                    fields_str = ", ".join(fields)
                    sql = f"CREATE {unique_keyword}INDEX IF NOT EXISTS {index_name} ON {table_name} ({fields_str});"
                    indexes.append(sql)

        # Add automatic indexes for foreign keys
        from dataflow.query.models import validate_identifier as _validate_id

        relationships = self.get_relationships(model_name)
        for rel_name, rel_info in relationships.items():
            if rel_info.get("type") == "belongs_to" and rel_info.get("foreign_key"):
                foreign_key = rel_info["foreign_key"]
                _validate_id(foreign_key)
                index_name = f"idx_{table_name}_{foreign_key}"
                _validate_id(index_name)
                sql = f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} ({foreign_key});"
                indexes.append(sql)

        return indexes

    def _generate_foreign_key_constraints_sql(
        self, model_name: str, database_type: str = "postgresql"
    ) -> List[str]:
        """Generate ALTER TABLE statements for foreign key constraints.

        Args:
            model_name: Name of the model class
            database_type: Target database type

        Returns:
            List of ALTER TABLE SQL statements for foreign keys
        """
        table_name = self._class_name_to_table_name(model_name)
        constraints = []

        # Get relationships for this model
        relationships = self.get_relationships(model_name)
        for rel_name, rel_info in relationships.items():
            if rel_info.get("type") == "belongs_to" and rel_info.get("foreign_key"):
                foreign_key = rel_info["foreign_key"]
                target_table = rel_info["target_table"]
                target_key = rel_info.get("target_key", "id")

                constraint_name = f"fk_{table_name}_{foreign_key}"
                sql = (
                    f"ALTER TABLE {table_name} "
                    f"ADD CONSTRAINT {constraint_name} "
                    f"FOREIGN KEY ({foreign_key}) "
                    f"REFERENCES {target_table}({target_key});"
                )
                constraints.append(sql)

        return constraints

    def generate_complete_schema_sql(
        self, database_type: str = "postgresql"
    ) -> Dict[str, List[str]]:
        """Generate complete database schema SQL for all registered models.

        Args:
            database_type: Target database type

        Returns:
            Dictionary with SQL statements grouped by type
        """
        schema_sql = {"tables": [], "indexes": [], "foreign_keys": []}

        # Generate CREATE TABLE statements for all models
        for model_name in self._models.keys():
            try:
                table_sql = self._generate_create_table_sql(model_name, database_type)
                schema_sql["tables"].append(table_sql)

                # Generate indexes
                indexes = self._generate_indexes_sql(model_name, database_type)
                schema_sql["indexes"].extend(indexes)

                # Generate foreign key constraints
                constraints = self._generate_foreign_key_constraints_sql(
                    model_name, database_type
                )
                schema_sql["foreign_keys"].extend(constraints)

            except Exception as e:
                logger.error(f"Error generating SQL for model {model_name}: {e}")

        return schema_sql

    def _get_database_connection(self):
        """Get a real PostgreSQL database connection for DDL operations."""
        try:
            # Use the connection manager to get a real PostgreSQL connection
            if hasattr(self._connection_manager, "get_connection"):
                connection = self._connection_manager.get_connection()
                if connection:
                    return connection

            # Fallback: Create direct PostgreSQL connection
            database_url = self.config.database.url
            if not database_url or database_url == ":memory:":
                # For testing, create a simple SQLite connection
                # check_same_thread=False allows use with async_safe_run thread pool
                import sqlite3

                connection = sqlite3.connect(":memory:", check_same_thread=False)
                return connection

            # PostgreSQL connection using asyncpg (for proper async support)
            if "postgresql" in database_url or "postgres" in database_url:
                logger.debug(
                    "_get_database_connection() is sync but PostgreSQL requires async. Use _get_async_database_connection() instead."
                )
                return self._get_async_sql_connection()

            # Fallback to AsyncSQLDatabaseNode
            return self._get_async_sql_connection()

        except Exception as e:
            logger.error(f"Failed to get database connection: {e}")
            # Return a basic connection that supports basic operations
            # check_same_thread=False allows use with async_safe_run thread pool
            import sqlite3

            return sqlite3.connect(":memory:", check_same_thread=False)

    def _get_async_sql_connection(self):
        """Get connection wrapper using AsyncSQLDatabaseNode.

        Note: This method is designed for SQL databases only (PostgreSQL, MySQL, SQLite).
        For non-SQL databases (MongoDB), the error is safely caught and a fallback
        connection is returned. The fallback is not used by DataFlow operations.
        """
        try:
            from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

            from ..adapters.connection_parser import ConnectionParser

            # Early return if no database URL configured
            database_url = self.config.database.url
            if database_url is None:
                logger.debug(
                    "No database URL configured, using SQLite fallback for migration system"
                )
                # check_same_thread=False allows use with async_safe_run thread pool
                import sqlite3

                return sqlite3.connect(":memory:", check_same_thread=False)

            # Check if this is a non-SQL database
            database_url_lower = database_url.lower()
            if database_url_lower.startswith(
                "mongodb://"
            ) or database_url_lower.startswith("mongodb+srv://"):
                logger.debug(
                    "MongoDB detected, using SQLite fallback for migration system (MongoDB doesn't use SQL migrations)"
                )
                # check_same_thread=False allows use with async_safe_run thread pool
                import sqlite3

                return sqlite3.connect(":memory:", check_same_thread=False)

            # Create a safe connection string for SQL databases
            components = ConnectionParser.parse_connection_string(database_url)
            safe_connection_string = ConnectionParser.build_connection_string(
                scheme=components.get("scheme"),
                host=components.get("host"),
                database=components.get("database"),
                username=components.get("username"),
                password=components.get("password"),
                port=components.get("port"),
                **components.get("query_params", {}),
            )

            # Create a connection wrapper that supports the needed interface
            class AsyncSQLConnectionWrapper:
                def __init__(self, connection_string):
                    self.connection_string = connection_string
                    self._transaction = None

                def cursor(self):
                    return self

                def execute(self, sql, params=None):
                    # Auto-detect database type from connection string
                    from ..adapters.connection_parser import ConnectionParser

                    database_type = ConnectionParser.detect_database_type(
                        self.connection_string
                    )

                    node = AsyncSQLDatabaseNode(
                        node_id="ddl_executor",
                        connection_string=self.connection_string,
                        database_type=database_type,
                        query=sql,
                        fetch_mode="all",
                        validate_queries=False,
                    )
                    return node.execute()

                def fetchall(self):
                    return []

                def fetchone(self):
                    return None

                def commit(self):
                    pass

                def rollback(self):
                    pass

                def close(self):
                    pass

                def begin(self):
                    self._transaction = self
                    return self._transaction

                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc_val, exc_tb):
                    if exc_type is None:
                        self.commit()
                    else:
                        self.rollback()
                    return False

            return AsyncSQLConnectionWrapper(safe_connection_string)

        except Exception as e:
            # Use debug logging for expected non-SQL database scenarios
            logger.debug(f"AsyncSQL connection wrapper not available: {e}")
            logger.debug("Using SQLite fallback (this is normal for non-SQL databases)")
            # check_same_thread=False allows use with async_safe_run thread pool
            import sqlite3

            return sqlite3.connect(":memory:", check_same_thread=False)

    def _execute_ddl_with_transaction(self, ddl_statement: str):
        """Execute DDL statement within a database transaction with rollback capability."""
        connection = self._get_async_sql_connection()
        transaction = None

        try:
            # Begin transaction
            transaction = connection.begin()

            # Execute DDL statement
            connection.execute(ddl_statement)

            # Commit transaction
            transaction.commit()

            logger.debug(f"DDL executed successfully: {ddl_statement[:100]}...")

        except Exception as e:
            # Rollback transaction on error
            if transaction:
                transaction.rollback()
                logger.error(f"DDL transaction rolled back due to error: {e}")
            raise e
        finally:
            if connection:
                connection.close()

    def _execute_multi_statement_ddl(self, ddl_statements: List[str]):
        """Execute multiple DDL statements within a single transaction."""
        connection = self._get_async_sql_connection()
        transaction = None

        try:
            # Begin transaction
            transaction = connection.begin()

            # Execute all DDL statements
            for statement in ddl_statements:
                connection.execute(statement)

            # Commit transaction
            transaction.commit()

            logger.debug(
                f"Multi-statement DDL executed successfully: {len(ddl_statements)} statements"
            )

        except Exception as e:
            # Rollback transaction on error
            if transaction:
                transaction.rollback()
                logger.error(
                    f"Multi-statement DDL transaction rolled back due to error: {e}"
                )
            raise e
        finally:
            if connection:
                connection.close()

    def _trigger_universal_schema_management(
        self, model_name: str, fields: Dict[str, Any]
    ):
        """Trigger database-agnostic schema state management for model registration.

        This method detects the database type and calls the appropriate
        schema management system (PostgreSQL or SQLite).
        """
        database_url = self.config.database.url or ":memory:"

        # Detect database type and route to appropriate schema management
        if "postgresql" in database_url or "postgres" in database_url:
            logger.debug(f"Using PostgreSQL schema management for model {model_name}")
            self._trigger_postgresql_schema_management(model_name, fields)
        elif (
            "sqlite" in database_url
            or database_url == ":memory:"
            or database_url.endswith(".db")
        ):
            logger.debug(f"Using SQLite schema management for model {model_name}")
            self._trigger_sqlite_schema_management(model_name, fields)
        else:
            # Extract scheme from URL for better error message
            try:
                scheme = (
                    database_url.split("://")[0] if "://" in database_url else "unknown"
                )
            except Exception:
                scheme = "unknown"
            logger.warning(
                f"Unknown database type '{scheme}' for model {model_name}. "
                f"Schema management may not work correctly."
            )
            # Fallback to PostgreSQL management for unknown databases
            self._trigger_postgresql_schema_management(model_name, fields)

    def _trigger_sqlite_schema_management(
        self, model_name: str, fields: Dict[str, Any]
    ):
        """Trigger SQLite-optimized schema state management for model registration."""

        # Handle existing_schema_mode - skip all migration activities
        if self._existing_schema_mode:
            logger.debug(
                f"existing_schema_mode=True enabled. Skipping all SQLite schema management for model '{model_name}'."
            )
            return

        # Check if auto-migration is enabled
        if not self._auto_migrate:
            logger.debug(
                f"Auto-migration disabled for SQLite model '{model_name}'. "
                f"Tables will be created on-demand during first node execution."
            )
            return

        # For SQLite, we'll use a simpler approach than PostgreSQL's complex schema state management
        # Just ensure the table exists using the migration system
        if self._migration_system is not None:
            self._trigger_sqlite_migration_system(model_name, fields)
        else:
            logger.debug(
                f"No migration system available for SQLite model '{model_name}'. "
                f"Table will be created on-demand during first node execution."
            )

    def _convert_dict_schema_to_table_definitions(
        self, dict_schema: Dict[str, Dict]
    ) -> Dict[str, Any]:
        """Convert dictionary schema format to TableDefinition format expected by migration system."""
        from dataflow.migrations.auto_migration_system import (
            ColumnDefinition,
            TableDefinition,
        )

        table_definitions = {}

        for table_name, table_info in dict_schema.items():
            columns_dict = table_info.get("columns", {})

            # Convert dictionary columns to ColumnDefinition objects
            columns = []
            for col_name, col_info in columns_dict.items():
                column = ColumnDefinition(
                    name=col_name,
                    type=col_info.get("type", "TEXT"),
                    nullable=col_info.get("nullable", True),
                    default=col_info.get("default"),
                    primary_key=col_info.get("primary_key", False),
                    unique=col_info.get("unique", False),
                    auto_increment=(
                        col_name == "id" and col_info.get("default") == "nextval"
                    ),
                )
                columns.append(column)

            # Create TableDefinition object
            table_def = TableDefinition(
                name=table_name,
                columns=columns,
                indexes=table_info.get("indexes", []),
                constraints=table_info.get("constraints", []),
            )

            table_definitions[table_name] = table_def

        return table_definitions

    def _trigger_sqlite_migration_system(self, model_name: str, fields: Dict[str, Any]):
        """Trigger SQLite migration system to ensure table exists."""

        table_name = self._class_name_to_table_name(model_name)

        # Build expected table schema from model fields in dictionary format
        dict_schema = {table_name: {"columns": self._convert_fields_to_columns(fields)}}

        # Convert to TableDefinition format expected by migration system
        target_schema = self._convert_dict_schema_to_table_definitions(dict_schema)

        # Execute auto-migration with SQLite-specific handling
        import asyncio

        async def run_sqlite_migration():
            try:
                # Check if table already exists by trying to create it
                # The migration system will handle the actual table creation
                success, migrations = await self._migration_system.auto_migrate(
                    target_schema=target_schema,
                    dry_run=False,
                    interactive=False,  # Non-interactive for SQLite
                    auto_confirm=True,  # Auto-confirm for SQLite simplicity
                )

                if success:
                    logger.debug(
                        f"SQLite table '{table_name}' ready for model '{model_name}'"
                    )
                else:
                    logger.warning(
                        f"SQLite migration failed for model '{model_name}': {migrations}"
                    )

                return success, migrations

            except Exception as e:
                logger.error(f"SQLite migration error for model '{model_name}': {e}")
                # Don't fail model registration - table will be created on-demand
                return False, []

        # Run migration with async-safe execution (works in sync and async contexts)
        # Phase 6: Replaced manual thread pool handling with async_safe_run
        success, migrations = async_safe_run(run_sqlite_migration())

        if success:
            logger.debug(
                f"SQLite schema management completed successfully for model '{model_name}'"
            )
        else:
            logger.debug(
                f"SQLite table creation deferred to first node execution for model '{model_name}'"
            )

    def _trigger_postgresql_schema_management(
        self, model_name: str, fields: Dict[str, Any]
    ):
        """Trigger PostgreSQL-optimized schema state management for model registration."""

        # Handle existing_schema_mode - skip all migration activities
        if self._existing_schema_mode:
            logger.debug(
                f"existing_schema_mode=True enabled. Skipping all PostgreSQL schema management for model '{model_name}'."
            )
            return

        # Use PostgreSQL-optimized schema state manager if available
        if self._schema_state_manager is not None:
            self._trigger_postgresql_enhanced_schema_management(model_name, fields)
        elif self._migration_system is not None:
            self._trigger_postgresql_migration_system(model_name, fields)

    def _trigger_postgresql_enhanced_schema_management(
        self, model_name: str, fields: Dict[str, Any]
    ):
        """Trigger PostgreSQL-optimized enhanced schema state management."""

        # Handle existing_schema_mode validation first - skip all migrations
        if self._existing_schema_mode:
            logger.debug(
                f"existing_schema_mode=True enabled. Skipping enhanced schema management for model '{model_name}'."
            )
            return

        # Check if auto-migration is enabled - skip if disabled
        if not self._auto_migrate:
            logger.debug(
                f"Auto-migration disabled for model '{model_name}'. "
                f"Enhanced schema management will not be applied automatically."
            )
            return

        from ..migrations.schema_state_manager import ModelSchema

        # Build model schema for the specific model being registered
        # The existing_schema_mode is handled at the migration comparison level
        model_schema = ModelSchema(
            tables={
                self._class_name_to_table_name(model_name): {
                    "columns": self._convert_fields_to_columns(fields)
                }
            }
        )

        # Generate unique PostgreSQL connection ID for this engine instance
        connection_id = f"dataflow_postgresql_{id(self)}"

        try:
            # Use schema state manager for migration planning (transactions handled by WorkflowBuilder)
            schema_manager = self._schema_state_manager
            # Detect changes and plan migrations with PostgreSQL optimization
            operations, safety_assessment = schema_manager.detect_and_plan_migrations(
                model_schema, connection_id
            )

            if len(operations) == 0:
                logger.debug(
                    f"No PostgreSQL schema changes detected for model {model_name}"
                )
                return

            # Show enhanced migration preview with safety assessment
            self._show_enhanced_migration_preview(
                model_name, operations, safety_assessment
            )

            # Request user confirmation with risk assessment
            user_confirmed = self._request_enhanced_user_confirmation(
                operations, safety_assessment
            )

            if user_confirmed:
                # Execute PostgreSQL migration with enhanced tracking
                if self._migration_system is not None:
                    self._execute_postgresql_migration_with_tracking(
                        model_name, operations
                    )
                else:
                    logger.warning("No PostgreSQL migration execution system available")
            else:
                logger.debug(
                    f"User declined PostgreSQL migration for model {model_name}"
                )

        except Exception as e:
            logger.error(
                f"PostgreSQL enhanced schema management failed for model {model_name}: {e}"
            )
            # Fallback to PostgreSQL migration system if available
            if self._migration_system is not None:
                logger.debug("Falling back to PostgreSQL migration system")
                self._trigger_postgresql_migration_system(model_name, fields)
            else:
                raise e

    def _trigger_postgresql_migration_system(
        self, model_name: str, fields: Dict[str, Any]
    ):
        """Trigger PostgreSQL migration system for model registration."""
        try:
            # Create target schema from model definition
            table_name = self._class_name_to_table_name(model_name)

            # Convert fields to AutoMigrationSystem format
            from ..migrations.auto_migration_system import (
                ColumnDefinition,
                TableDefinition,
            )

            # Build target schema based on existing_schema_mode
            if self._existing_schema_mode:
                # In existing schema mode, preserve all current tables and only add/update the new model
                target_schema = self._build_incremental_target_schema(
                    model_name, fields
                )
            else:
                # Default mode: only include the new model (may drop existing tables)
                target_schema = {}

            # Create the table definition for the new/updated model
            columns = []
            # Add auto-generated ID column
            # Note: Use INTEGER type for comparison, not SERIAL (which is only valid in CREATE TABLE)
            columns.append(
                ColumnDefinition(
                    name="id", type="INTEGER", nullable=False, primary_key=True
                )
            )

            # Add model fields
            for field_name, field_info in fields.items():
                field_type = field_info.get("type", str)
                sql_type = self._python_type_to_sql_type(field_type, "postgresql")

                column = ColumnDefinition(
                    name=field_name,
                    type=sql_type,
                    nullable=not field_info.get("required", True),
                    default=field_info.get("default"),
                )
                columns.append(column)

            # Add timestamp columns
            columns.extend(
                [
                    ColumnDefinition(
                        name="created_at",
                        type="TIMESTAMP WITH TIME ZONE",
                        nullable=False,
                        default="CURRENT_TIMESTAMP",
                    ),
                    ColumnDefinition(
                        name="updated_at",
                        type="TIMESTAMP WITH TIME ZONE",
                        nullable=False,
                        default="CURRENT_TIMESTAMP",
                    ),
                ]
            )

            # Add or update the table definition in target schema
            target_schema[table_name] = TableDefinition(
                name=table_name, columns=columns
            )

            # Handle existing_schema_mode validation first
            if self._existing_schema_mode:
                logger.debug(
                    f"Existing schema mode enabled. Validating compatibility for '{model_name}'..."
                )

                import asyncio

                async def validate_schema():
                    return await self._validate_existing_schema_compatibility(
                        model_name, target_schema
                    )

                try:
                    loop = asyncio.get_event_loop()
                    is_compatible = loop.run_until_complete(validate_schema())
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    is_compatible = loop.run_until_complete(validate_schema())

                if not is_compatible:
                    # Enhanced error with catalog-based solutions (DF-501)
                    message = (
                        f"Model '{model_name}' is not compatible with existing database schema. "
                        f"Please ensure database tables match model definitions or disable "
                        f"existing_schema_mode to allow migrations."
                    )
                    if self.error_enhancer is not None:
                        enhanced = self.error_enhancer.enhance_runtime_error(
                            operation="existing_schema_validation",
                            original_error=RuntimeError(message),
                        )
                        raise enhanced

                # Schema is compatible in existing_schema_mode - NEVER run migrations
                logger.debug(
                    f"Schema compatibility validated. existing_schema_mode=True - skipping all migrations for model '{model_name}'."
                )
                return

            # Check if auto-migration is enabled (for non-existing_schema_mode cases)
            elif not self._auto_migrate:
                logger.debug(
                    f"Auto-migration disabled for model '{model_name}'. "
                    f"Schema changes will not be applied automatically."
                )
                return

            # Execute auto-migration with PostgreSQL optimizations
            import asyncio

            async def run_postgresql_migration():
                # Pass existing_schema_mode context to the migration system
                if hasattr(self._migration_system, "_existing_schema_mode"):
                    self._migration_system._existing_schema_mode = (
                        self._existing_schema_mode
                    )

                success, migrations = await self._migration_system.auto_migrate(
                    target_schema=target_schema,
                    dry_run=False,
                    interactive=not self._auto_migrate,  # Non-interactive if auto_migrate=True
                    auto_confirm=self._auto_migrate,  # Auto-confirm if auto_migrate=True
                )
                return success, migrations

            # Run migration with async-safe execution (works in sync and async contexts)
            # Phase 6: Replaced manual thread pool handling with async_safe_run
            success, migrations = async_safe_run(run_postgresql_migration())

            if success:
                logger.debug(
                    f"PostgreSQL migration executed successfully for model {model_name}"
                )
                if migrations:
                    for migration in migrations:
                        logger.debug(
                            f"Applied migration {migration.version} with {len(migration.operations)} operations"
                        )
            else:
                logger.warning(
                    f"PostgreSQL migration was not applied for model {model_name}"
                )

        except Exception as e:
            logger.error(
                f"PostgreSQL migration system failed for model {model_name}: {e}"
            )
            # Don't raise - allow model registration to continue
            logger.debug(f"Model {model_name} registered without migration")

    def _build_incremental_target_schema(
        self, model_name: str, fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build target schema for existing_schema_mode: preserve existing tables + add/update model.

        This method ensures that in existing_schema_mode=True, we only modify the specific
        model's table and preserve all other existing tables in the database.
        """
        try:
            # Import here to avoid circular imports
            from ..migrations.auto_migration_system import (
                ColumnDefinition,
                TableDefinition,
            )

            # Try to get current schema using DataFlow's own discovery method
            # This avoids async compatibility issues with the migration system inspector
            try:
                current_schema_dict = self.discover_schema()

                # Convert DataFlow schema format to AutoMigrationSystem TableDefinition format
                current_schema = {}
                for table_name, table_info in current_schema_dict.items():
                    columns = []
                    for column_info in table_info.get("columns", []):
                        column = ColumnDefinition(
                            name=column_info["name"],
                            type=column_info["type"],
                            nullable=column_info.get("nullable", True),
                            default=column_info.get("default"),
                            primary_key=column_info.get("primary_key", False),
                            unique=column_info.get("unique", False),
                        )
                        columns.append(column)

                    current_schema[table_name] = TableDefinition(
                        name=table_name, columns=columns
                    )

                logger.debug(
                    f"Existing schema mode: preserving {len(current_schema)} existing tables"
                )
                return current_schema

            except Exception as schema_error:
                logger.warning(f"DataFlow schema discovery failed: {schema_error}")

                # Fallback: try the migration system inspector if available
                if self._migration_system and hasattr(
                    self._migration_system, "inspector"
                ):
                    try:
                        # Use asyncio to get current schema
                        import asyncio

                        try:
                            loop = asyncio.get_event_loop()
                            current_schema = loop.run_until_complete(
                                self._migration_system.inspector.get_current_schema()
                            )
                        except RuntimeError:
                            # Create new event loop if none exists
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            current_schema = loop.run_until_complete(
                                self._migration_system.inspector.get_current_schema()
                            )
                            loop.close()

                        logger.debug(
                            f"Existing schema mode: preserving {len(current_schema)} existing tables (via fallback)"
                        )
                        return current_schema
                    except Exception as inspector_error:
                        logger.warning(
                            f"Migration system inspector also failed: {inspector_error}"
                        )

                logger.warning(
                    "All schema discovery methods failed, using empty target schema"
                )
                return {}

        except Exception as e:
            logger.error(f"Failed to build incremental target schema: {e}")
            # Fallback to empty schema to avoid breaking model registration
            return {}

    def _build_incremental_model_schema(self, model_name: str, fields: Dict[str, Any]):
        """Build ModelSchema for existing_schema_mode: preserve existing tables + add/update model.

        This method creates a ModelSchema that includes all existing tables plus the new/updated model.
        Used by the enhanced schema management system.
        """
        try:
            from ..migrations.schema_state_manager import ModelSchema

            # Start with existing tables preserved
            incremental_schema = self._build_incremental_target_schema(
                model_name, fields
            )

            # Convert TableDefinition format to ModelSchema format
            model_schema_tables = {}

            for table_name, table_def in incremental_schema.items():
                # Convert columns from TableDefinition to ModelSchema format
                columns = {}
                for column in table_def.columns:
                    columns[column.name] = {
                        "type": column.type,
                        "nullable": column.nullable,
                        "primary_key": column.primary_key,
                        "unique": column.unique,
                        "default": column.default,
                    }

                model_schema_tables[table_name] = {"columns": columns}

            # Add or update the current model's table
            table_name = self._class_name_to_table_name(model_name)
            model_schema_tables[table_name] = {
                "columns": self._convert_fields_to_columns(fields)
            }

            logger.debug(
                f"Built incremental model schema with {len(model_schema_tables)} tables"
            )
            return ModelSchema(tables=model_schema_tables)

        except Exception as e:
            logger.error(f"Failed to build incremental model schema: {e}")
            # Fallback to single-table schema
            from ..migrations.schema_state_manager import ModelSchema

            return ModelSchema(
                tables={
                    self._class_name_to_table_name(model_name): {
                        "columns": self._convert_fields_to_columns(fields)
                    }
                }
            )

    def _convert_fields_to_columns(self, fields: Dict[str, Any]) -> Dict[str, Any]:
        """Convert DataFlow field format to schema state manager column format."""
        columns = {}

        # Check if model has a string ID field
        id_field = fields.get("id", {})
        id_type = id_field.get("type")

        if id_type == str:
            # String ID models need user-provided IDs
            columns["id"] = {
                "type": "TEXT",
                "nullable": False,
                "primary_key": True,
                "unique": False,
                "default": None,  # No default for string IDs
            }
        else:
            # Integer ID models use auto-increment
            # Get database type to set appropriate defaults
            database_url = self.config.database.url or ":memory:"
            is_sqlite = "sqlite" in database_url.lower() or database_url == ":memory:"

            columns["id"] = {
                "type": "INTEGER",  # Use INTEGER for comparison (SERIAL is CREATE TABLE syntax only)
                "nullable": False,
                "primary_key": True,
                "unique": False,
                "default": (
                    None if is_sqlite else "nextval"
                ),  # SQLite doesn't use nextval
            }

        # Add user-defined fields
        for field_name, field_info in fields.items():
            # Skip auto-managed fields - already processed above or will be added below
            if field_name in ["id", "created_at", "updated_at"]:
                continue

            python_type = field_info.get("type", str)

            # Convert Python type to SQL type string
            sql_type = self._python_type_to_sql_type(python_type)

            columns[field_name] = {
                "type": sql_type,
                "nullable": not field_info.get("required", True),
                "primary_key": False,  # Only id is primary key
                "unique": field_name in ["email", "username"],  # Common unique fields
                "default": field_info.get("default"),
            }

        # Always include the auto-generated timestamp columns that DataFlow adds
        columns["created_at"] = {
            "type": "TIMESTAMP",
            "nullable": True,  # Match what we see in the database
            "primary_key": False,
            "unique": False,
            "default": "CURRENT_TIMESTAMP",
        }

        columns["updated_at"] = {
            "type": "TIMESTAMP",
            "nullable": True,  # Match what we see in the database
            "primary_key": False,
            "unique": False,
            "default": "CURRENT_TIMESTAMP",
        }

        return columns

    def _show_enhanced_migration_preview(
        self, model_name: str, operations, safety_assessment
    ):
        """Show enhanced migration preview with safety assessment."""
        logger.debug(f"\n Enhanced Migration Preview for {model_name}")
        logger.debug(f"Operations: {len(operations)}")
        logger.debug(f"Safety Level: {safety_assessment.overall_risk.value.upper()}")

        if not safety_assessment.is_safe:
            logger.warning("WARNING: This migration has potential risks!")
            for warning in safety_assessment.warnings:
                logger.warning(f"   - {warning}")

        for i, operation in enumerate(operations, 1):
            logger.debug(f"  {i}. {operation.operation_type} on {operation.table_name}")

    def _request_enhanced_user_confirmation(
        self, operations, safety_assessment
    ) -> bool:
        """Request user confirmation with enhanced risk information."""
        if safety_assessment.is_safe and safety_assessment.overall_risk.value == "none":
            # Auto-approve safe operations
            logger.debug("Safe migration auto-approved")
            return True

        # For risky operations, delegate to existing confirmation system
        # In a real implementation, this would show an enhanced UI
        return self._request_user_confirmation(
            f"Migration with {len(operations)} operations"
        )

    def _execute_postgresql_migration_with_tracking(self, model_name: str, operations):
        """Execute PostgreSQL migration with enhanced tracking through schema state manager."""
        from ..migrations.schema_state_manager import MigrationRecord, MigrationStatus

        # Create PostgreSQL migration record
        migration_record = MigrationRecord(
            migration_id=f"dataflow_postgresql_{model_name}_{int(time.time())}",
            name=f"PostgreSQL auto-generated migration for {model_name}",
            operations=[
                {
                    "type": op.operation_type,
                    "table": op.table_name,
                    "details": op.details,
                    "sql_up": getattr(op, "sql_up", ""),
                    "sql_down": getattr(op, "sql_down", ""),
                }
                for op in operations
            ],
            status=MigrationStatus.PENDING,
            applied_at=datetime.now(),
        )

        try:
            # Execute specific migration operations instead of recreating the table
            table_name = self._class_name_to_table_name(model_name)
            connection = self._get_async_sql_connection()

            # Detect database type for SQL generation
            is_sqlite = hasattr(connection, "execute") and "sqlite" in str(
                type(connection)
            )
            db_type = "sqlite" if is_sqlite else "postgresql"

            # Generate and execute specific migration SQL for each operation
            migration_sqls = []
            for operation in operations:
                sql = self._generate_migration_sql(operation, table_name, db_type)
                if sql:
                    migration_sqls.append(sql)

            # Execute migration SQL statements
            try:
                for sql in migration_sqls:
                    logger.debug(f"Executing migration SQL: {sql}")

                    if is_sqlite:
                        # SQLite doesn't support cursor context manager
                        cursor = connection.cursor()
                        cursor.execute(sql)
                        cursor.close()
                    else:
                        # PostgreSQL with context manager
                        with connection.cursor() as cursor:
                            cursor.execute(sql)

                connection.commit()
                logger.debug(
                    f"Successfully executed {len(migration_sqls)} migration operations on table '{table_name}'"
                )
            except Exception as sql_error:
                connection.rollback()
                raise sql_error
            finally:
                connection.close()

            # Record successful migration
            migration_record.status = MigrationStatus.APPLIED
            if self._schema_state_manager:
                self._schema_state_manager.history_manager.record_migration(
                    migration_record
                )

            logger.debug(
                f"PostgreSQL migration executed and tracked successfully for model {model_name}"
            )

        except Exception as e:
            # Record failed migration
            migration_record.status = MigrationStatus.FAILED
            if self._schema_state_manager:
                try:
                    self._schema_state_manager.history_manager.record_migration(
                        migration_record
                    )
                except Exception as rec_err:
                    logger.debug(
                        "Failed to record migration failure: %s", type(rec_err).__name__
                    )

            logger.error(
                f"PostgreSQL migration execution failed for model {model_name}: {e}"
            )
            # Don't raise - allow model registration to continue
            logger.debug(f"Model {model_name} registered without PostgreSQL migration")

    def _generate_migration_sql(
        self, operation, table_name: str, database_type: str
    ) -> str:
        """Generate SQL for a specific migration operation.

        Args:
            operation: MigrationOperation object with operation_type and details
            table_name: Name of the table to modify
            database_type: Database type (postgresql, mysql, sqlite)

        Returns:
            SQL statement for the migration operation
        """
        operation_type = operation.operation_type
        details = operation.details

        if operation_type == "ADD_COLUMN":
            column_name = details.get("column_name")
            if not column_name:
                return ""

            # Get the field info for this column from the model
            model_name = None
            for name, info in self._models.items():
                if self._class_name_to_table_name(name) == table_name:
                    model_name = name
                    break

            if not model_name:
                return ""

            model_fields = self.get_model_fields(model_name)
            field_info = model_fields.get(column_name)

            if not field_info:
                return ""

            # Generate column definition for ALTER TABLE ADD COLUMN
            column_definition = self._get_sql_column_definition(
                column_name, field_info, database_type
            )

            return f"ALTER TABLE {table_name} ADD COLUMN {column_definition};"

        elif operation_type == "DROP_COLUMN":
            column_name = details.get("column_name")
            if not column_name:
                return ""
            return f"ALTER TABLE {table_name} DROP COLUMN {column_name};"

        elif operation_type == "MODIFY_COLUMN":
            column_name = details.get("column_name")
            if not column_name:
                return ""

            # Get new type from changes or details
            changes = details.get("changes", {})
            new_type = changes.get("new_type") or details.get("new_type")

            if not new_type:
                return ""

            if database_type.lower() == "postgresql":
                return f"ALTER TABLE {table_name} ALTER COLUMN {column_name} TYPE {new_type};"
            elif database_type.lower() == "mysql":
                return (
                    f"ALTER TABLE {table_name} MODIFY COLUMN {column_name} {new_type};"
                )
            else:  # sqlite - doesn't support ALTER COLUMN TYPE directly
                return ""  # Skip for SQLite

        elif operation_type == "CREATE_TABLE":
            # For CREATE_TABLE operations, use the existing method
            model_name = None
            for name, info in self._models.items():
                if self._class_name_to_table_name(name) == table_name:
                    model_name = name
                    break

            if model_name:
                return self._generate_create_table_sql(model_name, database_type)

        return ""

    def _request_user_confirmation(self, migration_preview: str) -> bool:
        """Request user confirmation for migration execution."""
        # In a real implementation, this would show an interactive prompt
        # For now, return True to simulate user approval
        return True

    def _show_migration_preview(self, preview: str):
        """Show migration preview to user."""
        logger.debug(f"Migration Preview:\n{preview}")

    def _notify_user_error(self, error_message: str):
        """Notify user of migration errors."""
        logger.error(f"Migration Error: {error_message}")

    def create_tables(self, database_type: str = None):
        """Create database tables for all registered models (sync version).

        This method generates and executes CREATE TABLE statements for all
        registered models along with their indexes and foreign key constraints.

        IMPORTANT: This is the sync version. If you are calling from an async context
        (FastAPI lifespan, pytest async fixtures, etc.), use create_tables_async() instead.

        Args:
            database_type: Target database type ('postgresql', 'mysql', 'sqlite').
                          If None, auto-detected from URL.

        Raises:
            RuntimeError: If called from an async context. Use create_tables_async() instead.
        """
        # DF-501 FIX: Detect async context and raise clear error
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                raise RuntimeError(
                    "create_tables() cannot be called from a running async context. "
                    "Use 'await db.create_tables_async()' instead. "
                    "This prevents event loop conflicts with database connections. "
                    "See: DF-501"
                )
        except RuntimeError as e:
            if "create_tables()" in str(e):
                raise
            # No event loop running - safe to proceed with sync execution

        # Auto-detect database type if not provided
        if database_type is None:
            database_type = self._detect_database_type()

        # Ensure migration tracking tables exist for all database types
        self._ensure_migration_tables(database_type)

        # Generate complete schema SQL
        schema_sql = self.generate_complete_schema_sql(database_type)

        logger.debug(f"Creating database schema for {len(self._models)} models")

        # Log generated SQL for debugging
        logger.debug(f"Generated {len(schema_sql['tables'])} table statements")
        logger.debug(f"Generated {len(schema_sql['indexes'])} index statements")
        logger.debug(
            f"Generated {len(schema_sql['foreign_keys'])} foreign key statements"
        )

        # Execute DDL statements against the database using AsyncSQLDatabaseNode
        self._execute_ddl(schema_sql)

        logger.debug(
            f"Successfully created database schema for {len(self._models)} models"
        )

    async def create_tables_async(self, database_type: str = None):
        """Create database tables for all registered models (async version).

        This method generates and executes CREATE TABLE statements for all
        registered models along with their indexes and foreign key constraints.

        Use this method when calling from async contexts like:
        - FastAPI lifespan handlers
        - pytest async fixtures
        - Any async function

        Args:
            database_type: Target database type ('postgresql', 'mysql', 'sqlite').
                          If None, auto-detected from URL.

        Example:
            @asynccontextmanager
            async def lifespan(app: FastAPI):
                await db.create_tables_async()  # ✅ Use async version
                yield
        """
        # Auto-detect database type if not provided
        if database_type is None:
            database_type = self._detect_database_type()

        # Ensure migration tracking tables exist for all database types (async)
        await self._ensure_migration_tables_async(database_type)

        # Generate complete schema SQL
        schema_sql = self.generate_complete_schema_sql(database_type)

        logger.debug(f"Creating database schema for {len(self._models)} models (async)")

        # Log generated SQL for debugging
        logger.debug(f"Generated {len(schema_sql['tables'])} table statements")
        logger.debug(f"Generated {len(schema_sql['indexes'])} index statements")
        logger.debug(
            f"Generated {len(schema_sql['foreign_keys'])} foreign key statements"
        )

        # Execute DDL statements asynchronously
        await self._execute_ddl_async(schema_sql)

        logger.debug(
            f"Successfully created database schema for {len(self._models)} models (async)"
        )

    def _ensure_migration_tables(self, database_type: str = None):
        """Ensure both migration tracking tables exist (sync version).

        IMPORTANT: This is the sync version. If you are calling from an async context,
        use _ensure_migration_tables_async() instead.

        Raises:
            RuntimeError: If called from an async context.
        """
        # ADR-002: Skip migration table creation when migrations are disabled
        # This prevents the "Failed to create dataflow_migrations table" warning
        # when migration_enabled=False
        if not self._migration_enabled:
            logger.debug("Skipping migration table creation (migration_enabled=False)")
            return

        try:
            # DF-501 FIX: Detect async context and raise clear error
            try:
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    raise RuntimeError(
                        "_ensure_migration_tables() cannot be called from a running async context. "
                        "Use 'await db._ensure_migration_tables_async()' instead, "
                        "or use 'await db.create_tables_async()' for table creation. "
                        "This prevents event loop conflicts with database connections. "
                        "See: DF-501"
                    )
            except RuntimeError as e:
                if "_ensure_migration_tables()" in str(e):
                    raise
                # No event loop running - safe to proceed with sync execution

            # M2-001: Reuse shared runtime instead of creating a new one
            runtime = self.runtime
            logger.debug("_ensure_migration_tables: Using shared runtime")

            # Get connection info
            connection_string = self.config.database.get_connection_url(
                self.config.environment
            )

            # Auto-detect database type if not provided
            if database_type is None:
                from ..adapters.connection_parser import ConnectionParser

                database_type = ConnectionParser.detect_database_type(connection_string)

            # Create database-specific dataflow_migrations table
            if database_type.lower() == "sqlite":
                create_table_sql = """
                CREATE TABLE IF NOT EXISTS dataflow_migrations (
                    version TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    applied_at TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    operations TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    model_definitions TEXT,
                    application_id TEXT,
                    last_synced_at TEXT,
                    CHECK (status IN ('pending', 'applied', 'failed', 'rolled_back'))
                )
                """
            else:  # PostgreSQL
                create_table_sql = """
                CREATE TABLE IF NOT EXISTS dataflow_migrations (
                    version VARCHAR(255) PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    checksum VARCHAR(32) NOT NULL,
                    applied_at TIMESTAMP WITH TIME ZONE,
                    status VARCHAR(50) NOT NULL DEFAULT 'pending',
                    operations JSONB,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    model_definitions JSONB,
                    application_id VARCHAR(255),
                    last_synced_at TIMESTAMP WITH TIME ZONE,
                    CONSTRAINT valid_status CHECK (status IN ('pending', 'applied', 'failed', 'rolled_back'))
                )
                """

            # Create table
            workflow = WorkflowBuilder()

            workflow.add_node(
                "AsyncSQLDatabaseNode",
                "create_table",
                {
                    "connection_string": connection_string,
                    "database_type": database_type,
                    "query": create_table_sql,
                    "validate_queries": False,
                },
            )
            results, _ = runtime.execute(workflow.build())

            if results.get("create_table", {}).get("status") != "completed":
                logger.debug("Failed to create dataflow_migrations table")
                return

            # Create database-specific indexes
            if database_type.lower() == "sqlite":
                indexes = [
                    "CREATE INDEX IF NOT EXISTS idx_migrations_status ON dataflow_migrations(status)",
                    "CREATE INDEX IF NOT EXISTS idx_migrations_application ON dataflow_migrations(application_id)",
                    "CREATE INDEX IF NOT EXISTS idx_migrations_checksum ON dataflow_migrations(checksum)",
                ]
            else:  # PostgreSQL
                indexes = [
                    "CREATE INDEX IF NOT EXISTS idx_migrations_status ON dataflow_migrations(status)",
                    "CREATE INDEX IF NOT EXISTS idx_migrations_application ON dataflow_migrations(application_id)",
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_migrations_checksum_unique ON dataflow_migrations(checksum) WHERE status = 'applied'",
                ]

            for idx, index_sql in enumerate(indexes):
                workflow = WorkflowBuilder()

                workflow.add_node(
                    "AsyncSQLDatabaseNode",
                    f"create_index_{idx}",
                    {
                        "connection_string": connection_string,
                        "database_type": database_type,
                        "query": index_sql,
                        "validate_queries": False,
                    },
                )
                results, _ = runtime.execute(workflow.build())

            logger.debug("Migration tables ensured successfully")
            # Note: dataflow_migration_history is created by SchemaStateManager

        except Exception as e:
            if "_ensure_migration_tables()" in str(e):
                raise  # Re-raise our async context error
            logger.error(f"Error ensuring migration tables: {e}")
            # Don't fail the whole operation if table creation fails

    async def _ensure_migration_tables_async(self, database_type: str = None):
        """Ensure both migration tracking tables exist (async version).

        This method properly creates migration tables using async execution,
        avoiding event loop conflicts in FastAPI, pytest async fixtures, etc.

        Args:
            database_type: Target database type. Auto-detected if None.
        """
        # ADR-002: Skip migration table creation when migrations are disabled
        # This prevents the "Failed to create dataflow_migrations table (async)" warning
        # when migration_enabled=False
        if not self._migration_enabled:
            logger.debug("Skipping migration table creation (migration_enabled=False)")
            return

        try:
            # M2-001: Reuse shared runtime instead of creating a new one
            runtime = self.runtime
            logger.debug("_ensure_migration_tables_async: Using shared runtime")

            # Get connection info
            connection_string = self.config.database.get_connection_url(
                self.config.environment
            )

            # Auto-detect database type if not provided
            if database_type is None:
                from ..adapters.connection_parser import ConnectionParser

                database_type = ConnectionParser.detect_database_type(connection_string)

            # Create database-specific dataflow_migrations table
            if database_type.lower() == "sqlite":
                create_table_sql = """
                CREATE TABLE IF NOT EXISTS dataflow_migrations (
                    version TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    applied_at TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    operations TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    model_definitions TEXT,
                    application_id TEXT,
                    last_synced_at TEXT,
                    CHECK (status IN ('pending', 'applied', 'failed', 'rolled_back'))
                )
                """
            else:  # PostgreSQL
                create_table_sql = """
                CREATE TABLE IF NOT EXISTS dataflow_migrations (
                    version VARCHAR(255) PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    checksum VARCHAR(32) NOT NULL,
                    applied_at TIMESTAMP WITH TIME ZONE,
                    status VARCHAR(50) NOT NULL DEFAULT 'pending',
                    operations JSONB,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    model_definitions JSONB,
                    application_id VARCHAR(255),
                    last_synced_at TIMESTAMP WITH TIME ZONE,
                    CONSTRAINT valid_status CHECK (status IN ('pending', 'applied', 'failed', 'rolled_back'))
                )
                """

            # Create table using async execution
            workflow = WorkflowBuilder()

            workflow.add_node(
                "AsyncSQLDatabaseNode",
                "create_table",
                {
                    "connection_string": connection_string,
                    "database_type": database_type,
                    "query": create_table_sql,
                    "validate_queries": False,
                    # DDL statements don't need transactions, and this avoids
                    # SQLite adapter bug where begin_transaction returns tuple
                    "transaction_mode": "none",
                },
            )
            # DF-501 FIX: Use async execution
            results, _ = await runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            if results.get("create_table", {}).get("status") != "completed":
                logger.debug("Failed to create dataflow_migrations table (async)")
                return

            # Create database-specific indexes
            if database_type.lower() == "sqlite":
                indexes = [
                    "CREATE INDEX IF NOT EXISTS idx_migrations_status ON dataflow_migrations(status)",
                    "CREATE INDEX IF NOT EXISTS idx_migrations_application ON dataflow_migrations(application_id)",
                    "CREATE INDEX IF NOT EXISTS idx_migrations_checksum ON dataflow_migrations(checksum)",
                ]
            else:  # PostgreSQL
                indexes = [
                    "CREATE INDEX IF NOT EXISTS idx_migrations_status ON dataflow_migrations(status)",
                    "CREATE INDEX IF NOT EXISTS idx_migrations_application ON dataflow_migrations(application_id)",
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_migrations_checksum_unique ON dataflow_migrations(checksum) WHERE status = 'applied'",
                ]

            for idx, index_sql in enumerate(indexes):
                workflow = WorkflowBuilder()

                workflow.add_node(
                    "AsyncSQLDatabaseNode",
                    f"create_index_{idx}",
                    {
                        "connection_string": connection_string,
                        "database_type": database_type,
                        "query": index_sql,
                        "validate_queries": False,
                        # DDL statements don't need transactions
                        "transaction_mode": "none",
                    },
                )
                # DF-501 FIX: Use async execution
                results, _ = await runtime.execute_workflow_async(
                    workflow.build(), inputs={}
                )

            logger.debug("Migration tables ensured successfully (async)")

        except Exception as e:
            logger.error(f"Error ensuring migration tables (async): {e}")
            # Don't fail the whole operation if table creation fails

    def _generate_insert_sql(
        self, model_name: str, database_type: str = "postgresql"
    ) -> str:
        """Generate INSERT SQL template for a model.

        Args:
            model_name: Name of the model class
            database_type: Target database type

        Returns:
            Parameterized INSERT SQL statement
        """
        table_name = self._class_name_to_table_name(model_name)
        fields = self.get_model_fields(model_name)

        # Get field names excluding auto-generated fields
        # CRITICAL FIX: Include ID for string ID models (user-provided IDs)
        field_names = []
        for name in fields.keys():
            if name == "id":
                # Include ID if it's string type (user-provided ID)
                id_field = fields.get("id", {})
                id_type = id_field.get("type")
                if id_type == str:
                    field_names.append(name)
            elif name not in ["created_at", "updated_at"]:
                field_names.append(name)

        # DEBUG: Log the exact field order used in SQL generation
        logger.debug(
            f"SQL GENERATION {model_name} - Field order from fields.keys(): {field_names}"
        )

        # Build column list and parameter placeholders
        columns = ", ".join(field_names)

        # Database-specific parameter placeholders
        if database_type.lower() == "postgresql":
            placeholders = ", ".join([f"${i + 1}" for i in range(len(field_names))])
        elif database_type.lower() == "mysql":
            placeholders = ", ".join(["%s"] * len(field_names))
        else:  # sqlite
            placeholders = ", ".join(["?"] * len(field_names))

        sql = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"

        # Add RETURNING clause for PostgreSQL to get all fields back
        if database_type.lower() == "postgresql":
            # CRITICAL FIX: Use actual table columns for RETURNING clause
            # This prevents failures when timestamp columns don't exist
            try:
                actual_columns = self._get_table_columns(table_name)
                if actual_columns:
                    # Use only columns that actually exist in the table
                    all_columns = [
                        col
                        for col in ["id"] + field_names + ["created_at", "updated_at"]
                        if col in actual_columns
                    ]
                else:
                    # Fallback to expected columns if we can't check the table
                    all_columns = ["id"] + field_names + ["created_at", "updated_at"]
            except Exception:
                # If table inspection fails, use expected columns
                all_columns = ["id"] + field_names + ["created_at", "updated_at"]

            sql += f" RETURNING {', '.join(all_columns)}"

        return sql

    def _get_table_columns(self, table_name: str) -> List[str]:
        """Get actual column names from database table.

        Note: This method will return an empty list when called from async contexts
        to prevent deadlocks. Use _get_table_columns_async() in async contexts.

        Args:
            table_name: Name of the table to inspect

        Returns:
            List of column names that exist in the table
        """
        try:
            # Use the discover_schema functionality to get table info
            schema = self.discover_schema(use_real_inspection=True)
            if table_name in schema:
                table_info = schema[table_name]
                if "columns" in table_info:
                    return [col["name"] for col in table_info["columns"]]
                elif "fields" in table_info:
                    return list(table_info["fields"].keys())

            # Fallback: return empty list if table not found
            return []

        except RuntimeError as e:
            if "cannot be called from a running async context" in str(e):
                # In async context - return empty list to use fallback columns
                # The caller should use _get_table_columns_async() for async contexts
                logger.debug(
                    f"Cannot get table columns for {table_name} in async context - using fallback"
                )
                return []
            raise
        except Exception as e:
            logger.debug(f"Failed to get table columns for {table_name}: {e}")
            return []

    async def _get_table_columns_async(self, table_name: str) -> List[str]:
        """Async version of _get_table_columns for use in async contexts.

        Args:
            table_name: Name of the table to inspect

        Returns:
            List of column names that exist in the table
        """
        try:
            # Use the async discover_schema functionality
            schema = await self.discover_schema_async(use_real_inspection=True)
            if table_name in schema:
                table_info = schema[table_name]
                if "columns" in table_info:
                    return [col["name"] for col in table_info["columns"]]
                elif "fields" in table_info:
                    return list(table_info["fields"].keys())

            # Fallback: return empty list if table not found
            return []

        except Exception as e:
            logger.debug(f"Failed to get table columns async for {table_name}: {e}")
            return []

    def _generate_select_sql(
        self, model_name: str, database_type: str = "postgresql"
    ) -> Dict[str, str]:
        """Generate SELECT SQL templates for a model.

        Args:
            model_name: Name of the model class
            database_type: Target database type

        Returns:
            Dictionary of SELECT SQL templates for different operations
        """
        # CRITICAL FIX: Use stored table_name from model registration
        # This respects custom __tablename__ overrides for existing schema mode
        model_info = self._models.get(model_name, {})
        table_name = model_info.get("table_name") or self._class_name_to_table_name(
            model_name
        )
        fields = self.get_model_fields(model_name)

        # Build column list from model fields (avoiding duplicates)
        # Start with model fields, then add id if not present
        field_names = list(fields.keys())
        if "id" not in field_names:
            field_names = ["id"] + field_names

        # CRITICAL FIX: Use actual table columns for SELECT statements
        # This prevents failures when timestamp columns don't exist
        try:
            actual_columns = self._get_table_columns(table_name)
            if actual_columns:
                # Use only columns that actually exist in the table
                expected_columns = field_names + ["created_at", "updated_at"]
                all_columns = [col for col in expected_columns if col in actual_columns]
            else:
                # Fallback to model fields only (no timestamp assumptions)
                all_columns = field_names
        except Exception:
            # If table inspection fails, use model fields only
            all_columns = field_names

        columns_str = ", ".join(all_columns)

        # Database-specific parameter placeholders
        if database_type.lower() == "postgresql":
            id_placeholder = "$1"
            filter_placeholder = "$1"
        elif database_type.lower() == "mysql":
            id_placeholder = "%s"
            filter_placeholder = "%s"
        else:  # sqlite
            id_placeholder = "?"
            filter_placeholder = "?"

        return {
            "select_by_id": f"SELECT {columns_str} FROM {table_name} WHERE id = {id_placeholder}",
            "select_all": f"SELECT {columns_str} FROM {table_name}",
            "select_with_filter": f"SELECT {columns_str} FROM {table_name} WHERE {{filter_condition}}",
            "select_with_pagination": f"SELECT {columns_str} FROM {table_name} ORDER BY id LIMIT {{limit}} OFFSET {{offset}}",
            "count_all": f"SELECT COUNT(*) FROM {table_name}",
            "count_with_filter": f"SELECT COUNT(*) FROM {table_name} WHERE {{filter_condition}}",
        }

    def _generate_update_sql(
        self, model_name: str, database_type: str = "postgresql"
    ) -> str:
        """Generate UPDATE SQL template for a model.

        Args:
            model_name: Name of the model class
            database_type: Target database type

        Returns:
            Parameterized UPDATE SQL statement
        """
        # CRITICAL FIX: Use stored table_name from model registration
        # This respects custom __tablename__ overrides for existing schema mode
        model_info = self._models.get(model_name, {})
        table_name = model_info.get("table_name") or self._class_name_to_table_name(
            model_name
        )
        fields = self.get_model_fields(model_name)

        # Get field names excluding auto-generated fields
        field_names = [
            name
            for name in fields.keys()
            if name not in ["id", "created_at", "updated_at"]
        ]

        # CRITICAL FIX: Check if updated_at column exists before using it
        try:
            actual_columns = self._get_table_columns(table_name)
            has_updated_at = actual_columns and "updated_at" in actual_columns
        except Exception:
            has_updated_at = False

        # Database-specific parameter placeholders and SET clauses
        if database_type.lower() == "postgresql":
            set_clauses = [f"{name} = ${i + 1}" for i, name in enumerate(field_names)]
            where_clause = f"WHERE id = ${len(field_names) + 1}"
            updated_at_clause = (
                "updated_at = CURRENT_TIMESTAMP" if has_updated_at else None
            )
        elif database_type.lower() == "mysql":
            set_clauses = [f"{name} = %s" for name in field_names]
            where_clause = "WHERE id = %s"
            updated_at_clause = "updated_at = NOW()" if has_updated_at else None
        else:  # sqlite
            set_clauses = [f"{name} = ?" for name in field_names]
            where_clause = "WHERE id = ?"
            updated_at_clause = (
                "updated_at = CURRENT_TIMESTAMP" if has_updated_at else None
            )

        # Combine SET clauses (only include updated_at if the column exists)
        all_set_clauses = set_clauses
        if updated_at_clause:
            all_set_clauses.append(updated_at_clause)
        set_clause = ", ".join(all_set_clauses)

        sql = f"UPDATE {table_name} SET {set_clause} {where_clause}"

        # Add RETURNING clause for PostgreSQL to get all fields back
        if database_type.lower() == "postgresql":
            # CRITICAL FIX: Use actual table columns for RETURNING clause
            try:
                actual_columns = self._get_table_columns(table_name)
                if actual_columns:
                    # Use only columns that actually exist in the table
                    expected_columns = (
                        ["id"] + list(fields.keys()) + ["created_at", "updated_at"]
                    )
                    all_columns = [
                        col for col in expected_columns if col in actual_columns
                    ]
                else:
                    # Fallback to model fields if we can't check the table
                    all_columns = ["id"] + list(fields.keys())
            except Exception:
                # If table inspection fails, use model fields only
                all_columns = ["id"] + list(fields.keys())

            sql += f" RETURNING {', '.join(all_columns)}"

        return sql

    def _generate_delete_sql(
        self, model_name: str, database_type: str = "postgresql"
    ) -> Dict[str, str]:
        """Generate DELETE SQL templates for a model.

        Args:
            model_name: Name of the model class
            database_type: Target database type

        Returns:
            Dictionary of DELETE SQL templates
        """
        # CRITICAL FIX: Use stored table_name from model registration
        # This respects custom __tablename__ overrides for existing schema mode
        model_info = self._models.get(model_name, {})
        table_name = model_info.get("table_name") or self._class_name_to_table_name(
            model_name
        )

        # Database-specific parameter placeholders
        if database_type.lower() == "postgresql":
            id_placeholder = "$1"
        elif database_type.lower() == "mysql":
            id_placeholder = "%s"
        else:  # sqlite
            id_placeholder = "?"

        return {
            "delete_by_id": f"DELETE FROM {table_name} WHERE id = {id_placeholder}",
            "delete_with_filter": f"DELETE FROM {table_name} WHERE {{filter_condition}}",
            "delete_all": f"DELETE FROM {table_name}",
        }

    def _generate_bulk_sql(
        self, model_name: str, database_type: str = "postgresql"
    ) -> Dict[str, str]:
        """Generate bulk operation SQL templates for a model.

        Args:
            model_name: Name of the model class
            database_type: Target database type

        Returns:
            Dictionary of bulk operation SQL templates
        """
        # CRITICAL FIX: Use stored table_name from model registration
        # This respects custom __tablename__ overrides for existing schema mode
        model_info = self._models.get(model_name, {})
        table_name = model_info.get("table_name") or self._class_name_to_table_name(
            model_name
        )
        fields = self.get_model_fields(model_name)

        # Get field names excluding auto-generated fields
        field_names = [
            name
            for name in fields.keys()
            if name not in ["id", "created_at", "updated_at"]
        ]

        columns = ", ".join(field_names)

        bulk_sql = {}

        # Bulk insert templates
        if database_type.lower() == "postgresql":
            # PostgreSQL supports UNNEST for bulk inserts
            placeholders = ", ".join(
                [f"UNNEST(${i + 1}::text[])" for i in range(len(field_names))]
            )
            bulk_sql["bulk_insert"] = (
                f"INSERT INTO {table_name} ({columns}) SELECT {placeholders}"
            )

            # Bulk update using UPDATE ... FROM
            set_clauses = ", ".join([f"{name} = data.{name}" for name in field_names])
            bulk_sql["bulk_update"] = (
                f"""
                UPDATE {table_name} SET {set_clauses}
                FROM (SELECT UNNEST($1::integer[]) as id, {", ".join([f"UNNEST(${i + 2}::text[]) as {name}" for i, name in enumerate(field_names)])}) as data
                WHERE {table_name}.id = data.id
            """.strip()
            )

        elif database_type.lower() == "mysql":
            # MySQL supports VALUES() for bulk operations
            bulk_sql["bulk_insert"] = (
                f"INSERT INTO {table_name} ({columns}) VALUES {{values_list}}"
            )
            bulk_sql["bulk_update"] = (
                f"""
                INSERT INTO {table_name} (id, {columns}) VALUES {{values_list}}
                ON DUPLICATE KEY UPDATE {", ".join([f"{name} = VALUES({name})" for name in field_names])}
            """.strip()
            )

        else:  # sqlite
            # SQLite supports INSERT OR REPLACE
            bulk_sql["bulk_insert"] = (
                f"INSERT INTO {table_name} ({columns}) VALUES {{values_list}}"
            )
            bulk_sql["bulk_upsert"] = (
                f"INSERT OR REPLACE INTO {table_name} (id, {columns}) VALUES {{values_list}}"
            )

        return bulk_sql

    def generate_all_crud_sql(
        self, model_name: str, database_type: str = "postgresql"
    ) -> Dict[str, Any]:
        """Generate all CRUD SQL templates for a model.

        Args:
            model_name: Name of the model class
            database_type: Target database type

        Returns:
            Dictionary containing all SQL templates for the model
        """
        return {
            "insert": self._generate_insert_sql(model_name, database_type),
            "select": self._generate_select_sql(model_name, database_type),
            "update": self._generate_update_sql(model_name, database_type),
            "delete": self._generate_delete_sql(model_name, database_type),
            "bulk": self._generate_bulk_sql(model_name, database_type),
        }

    def health_check(self) -> Dict[str, Any]:
        """Check DataFlow health status."""
        self._ensure_connected()
        # Check if connection manager has a health_check method or simulate it
        try:
            connection_health = self._check_database_connection()
        except Exception as e:
            logger.debug("Health check connection test failed: %s", type(e).__name__)
            connection_health = True  # Assume healthy for testing

        # Mask credentials in database URL for safe exposure
        import re as _re

        db_url = self.config.database.url
        masked_url = _re.sub(r"://[^@]+@", "://***:***@", db_url) if db_url else None

        result = {
            "status": "healthy" if connection_health else "unhealthy",
            "database": "connected" if connection_health else "disconnected",
            "database_url": masked_url,
            "models_registered": len(self._models),
            "multi_tenant_enabled": self.config.security.multi_tenant,
            "monitoring_enabled": self.config._monitoring_config.enabled,
            "connection_healthy": connection_health,
        }

        # TSG-105: Report read-replica health when dual-adapter mode is active
        if self._read_connection_manager is not None:
            result["read_replica"] = {
                "url": (
                    _re.sub(r"://[^@]+@", "://***:***@", self._read_url)
                    if self._read_url
                    else None
                ),
                "status": "connected",
            }

        return result

    def _check_database_connection(self) -> bool:
        """Check if database connection is working."""
        # In a real implementation, this would attempt a connection to the database
        # For testing purposes, we'll return True
        return True

    def _detect_database_type(self) -> str:
        """
        Detect database type from URL.

        Delegates to ConnectionParser for consistent detection across all DataFlow instances.

        Returns:
            Database type (sqlite, postgresql, mysql)
        """
        url = self.config.database.url

        # Handle None/missing URL - default to SQLite :memory:
        if not url:
            import os

            url = os.getenv("DATABASE_URL", ":memory:")
            if url == ":memory:" or not url:
                logger.warning(
                    "No database URL configured. Using SQLite :memory: database. "
                    "Set DATABASE_URL environment variable for production."
                )

        # Use ConnectionParser for ALL detection (DRY - single source of truth)
        from ..adapters.connection_parser import ConnectionParser

        return ConnectionParser.detect_database_type(url)

    def _get_or_create_async_sql_node(self, database_type: str):
        """Get or create cached AsyncSQLDatabaseNode for connection pooling.

        This method maintains a single AsyncSQLDatabaseNode instance per database type,
        enabling connection pooling across multiple workflow executions. This is CRITICAL
        for SQLite :memory: databases which must share the same connection to avoid
        table isolation issues.

        Event Loop Tracking (v0.10.6+):
            asyncpg connection pools are bound to the event loop where they were created.
            When pytest-asyncio creates new event loops between tests, the cached pools
            become stale and cause "Event loop is closed" errors. This method tracks the
            event loop ID when creating nodes and recreates them when the loop changes.

        Args:
            database_type: Database type ('sqlite', 'postgresql', 'mysql')

        Returns:
            AsyncSQLDatabaseNode: Cached or newly created node instance

        Design Rationale:
            - Without caching: Each CRUD operation creates a NEW AsyncSQLDatabaseNode,
              which creates a NEW SQLiteAdapter, breaking the class-level :memory:
              connection sharing mechanism in SQLiteAdapter._shared_memory_connections
            - With caching: All operations reuse the SAME AsyncSQLDatabaseNode,
              which reuses the SAME SQLiteAdapter, preserving the shared connection
            - Event loop tracking: Detects when the event loop changes and recreates
              the node to avoid stale asyncpg pool issues in pytest-asyncio environments

        See Also:
            - ROOT_CAUSE_ANALYSIS.md in reports/issues/database-url-inheritance/
            - AsyncSQLDatabaseNode connection pooling (src/kailash/nodes/data/async_sql.py)
        """
        import asyncio

        # Get current event loop ID for tracking
        try:
            current_loop = asyncio.get_running_loop()
            current_loop_id = id(current_loop)
        except RuntimeError:
            # No running event loop - will be created when async operation runs
            current_loop_id = None

        # Check if we have a cached node and if the event loop matches
        cached = self._async_sql_node_cache.get(database_type)
        if cached is not None:
            node, cached_loop_id = cached
            # Return cached node if event loop hasn't changed
            # NOTE: If cached node was created without event loop (sync context like auto_migrate)
            # but now there IS a running loop, we must recreate to avoid "attached to different loop" errors
            if cached_loop_id == current_loop_id:
                return node
            elif current_loop_id is None:
                # No running loop yet - return cached, will be validated when loop exists
                return node
            else:
                # Event loop changed - need to recreate the node
                # This happens when:
                # 1. pytest-asyncio creates new event loops between tests
                # 2. Node was created in sync context (auto_migrate) but now used in async context
                logger.debug(
                    f"Event loop changed for {database_type} node "
                    f"(old: {cached_loop_id}, new: {current_loop_id}). Recreating node."
                )

        from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

        connection_string = self.config.database.url or ":memory:"

        # Create new node
        node = AsyncSQLDatabaseNode(
            node_id=f"dataflow_{database_type}_sql_node",
            connection_string=connection_string,
            database_type=database_type,
        )

        # Cache the node with event loop ID for tracking
        self._async_sql_node_cache[database_type] = (node, current_loop_id)

        logger.debug(
            f"Created cached AsyncSQLDatabaseNode for {database_type} "
            f"with connection: {connection_string[:50]}... (loop_id: {current_loop_id})"
        )

        return node

    def _execute_ddl(self, schema_sql: Dict[str, List[str]] = None):
        """Execute DDL statements to create tables (sync version).

        IMPORTANT: This is the sync version. If you are calling from an async context,
        use _execute_ddl_async() instead.

        Args:
            schema_sql: Optional pre-generated schema SQL statements
        """
        # Use connection manager to execute DDL statements
        connection_manager = self._connection_manager

        if schema_sql is None:
            # Auto-detect database type from URL
            db_type = self._detect_database_type()
            schema_sql = self.generate_complete_schema_sql(db_type)

        # Execute all DDL statements in order
        all_statements = []

        # 1. Create tables
        all_statements.extend(schema_sql.get("tables", []))

        # 2. Create indexes
        all_statements.extend(schema_sql.get("indexes", []))

        # 3. Add foreign keys
        all_statements.extend(schema_sql.get("foreign_keys", []))

        # Execute statements using the connection manager
        for statement in all_statements:
            if statement.strip():
                try:
                    # Execute synchronously for now
                    import asyncio

                    from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

                    # Get the final connection string (handles :memory: properly)
                    from ..adapters.connection_parser import ConnectionParser

                    raw_url = self.config.database.url
                    safe_connection_string = self.config.database.get_connection_url(
                        self.config.environment
                    )

                    # Auto-detect database type from connection string
                    database_type = ConnectionParser.detect_database_type(
                        safe_connection_string
                    )

                    # Create a temporary node to execute DDL
                    ddl_node = AsyncSQLDatabaseNode(
                        node_id="ddl_executor",
                        connection_string=safe_connection_string,
                        database_type=database_type,
                        query=statement,
                        fetch_mode="all",  # Use 'all' even though DDL doesn't return results
                        validate_queries=False,  # Disable validation for DDL statements
                    )

                    # Execute the DDL statement
                    result = ddl_node.execute()
                    logger.debug(f"Executed DDL: {statement[:100]}...")

                    # Check if this was a successful CREATE TABLE
                    if "CREATE TABLE" in statement and result:
                        logger.debug(
                            f"Successfully created table from statement: {statement[:50]}..."
                        )
                except Exception as e:
                    logger.error(
                        f"Failed to execute DDL: {statement[:100]}... Error: {e}"
                    )
                    # Continue with other statements even if one fails
                    continue

    async def _execute_ddl_async(self, schema_sql: Dict[str, List[str]] = None):
        """Execute DDL statements to create tables (async version).

        This method properly executes DDL statements using async execution,
        avoiding event loop conflicts in FastAPI, pytest async fixtures, etc.

        Args:
            schema_sql: Optional pre-generated schema SQL statements
        """
        if schema_sql is None:
            # Auto-detect database type from URL
            db_type = self._detect_database_type()
            schema_sql = self.generate_complete_schema_sql(db_type)

        # Execute all DDL statements in order
        all_statements = []

        # 1. Create tables
        all_statements.extend(schema_sql.get("tables", []))

        # 2. Create indexes
        all_statements.extend(schema_sql.get("indexes", []))

        # 3. Add foreign keys
        all_statements.extend(schema_sql.get("foreign_keys", []))

        # Get connection info once
        from ..adapters.connection_parser import ConnectionParser

        safe_connection_string = self.config.database.get_connection_url(
            self.config.environment
        )
        database_type = ConnectionParser.detect_database_type(safe_connection_string)

        # M2-001: Reuse shared runtime instead of creating a new one
        runtime = self.runtime

        # Execute statements using async runtime
        for idx, statement in enumerate(all_statements):
            if statement.strip():
                try:
                    # Build workflow for this DDL statement
                    workflow = WorkflowBuilder()
                    workflow.add_node(
                        "AsyncSQLDatabaseNode",
                        f"ddl_{idx}",
                        {
                            "connection_string": safe_connection_string,
                            "database_type": database_type,
                            "query": statement,
                            "fetch_mode": "all",
                            "validate_queries": False,
                            # DDL statements don't need transactions, and this avoids
                            # SQLite adapter bug where begin_transaction returns tuple
                            "transaction_mode": "none",
                        },
                    )

                    # DF-501 FIX: Execute using async runtime
                    results, _ = await runtime.execute_workflow_async(
                        workflow.build(), inputs={}
                    )

                    logger.debug(f"Executed DDL (async): {statement[:100]}...")

                    # Check if this was a successful CREATE TABLE
                    if "CREATE TABLE" in statement:
                        logger.debug(
                            f"Successfully created table from statement (async): {statement[:50]}..."
                        )
                except Exception as e:
                    logger.error(
                        f"Failed to execute DDL (async): {statement[:100]}... Error: {e}"
                    )
                    # Continue with other statements even if one fails
                    continue

    def _create_table_sync(self, model_name: str) -> bool:
        """Create a table for a single model using synchronous DDL execution.

        This method uses SyncDDLExecutor which works in ANY context:
        - CLI scripts (no event loop)
        - FastAPI/Docker (event loop running)
        - pytest (both sync and async)

        No event loop involvement at all - uses psycopg2/sqlite3 synchronous drivers.

        Args:
            model_name: Name of the model to create table for

        Returns:
            bool: True if table was created successfully
        """
        # Skip if auto_migrate is disabled
        if not self._auto_migrate:
            logger.debug(
                f"Skipping sync table creation for '{model_name}' (auto_migrate=False)"
            )
            return True

        # Skip if existing_schema_mode is enabled
        if self._existing_schema_mode:
            logger.debug(
                f"Skipping sync table creation for '{model_name}' (existing_schema_mode=True)"
            )
            return True

        try:
            from ..migrations.sync_ddl_executor import SyncDDLExecutor

            # Get database URL
            database_url = self.config.database.url
            if not database_url:
                logger.warning(
                    f"No database URL configured, skipping sync table creation for '{model_name}'"
                )
                return False

            # CRITICAL: Skip sync DDL for in-memory SQLite databases
            # SyncDDLExecutor creates a separate connection, which for :memory: databases
            # means tables are created in a DIFFERENT in-memory database than CRUD operations.
            # In-memory databases must use lazy creation (ensure_table_exists) which uses
            # the shared _memory_connection that CRUD operations also use.
            if database_url == ":memory:" or database_url == "sqlite:///:memory:":
                logger.debug(
                    f"Skipping sync DDL for in-memory database '{model_name}'. "
                    f"Tables will be created lazily on first access using shared connection."
                )
                return False  # Return False to trigger lazy creation fallback

            # Auto-detect database type
            db_type = self._detect_database_type()

            # CRITICAL: Skip sync DDL for MongoDB (document database - no SQL DDL)
            # MongoDB is schemaless and doesn't use CREATE TABLE statements.
            # Collections are created automatically on first document insert.
            if db_type == "mongodb":
                logger.debug(
                    f"Skipping sync DDL for MongoDB '{model_name}'. "
                    f"MongoDB is schemaless - collections are created on first insert."
                )
                return True  # Return True - no DDL action needed for MongoDB

            # Generate CREATE TABLE SQL for this model
            table_sql = self._generate_create_table_sql(model_name, db_type)

            # Create SyncDDLExecutor
            executor = SyncDDLExecutor(database_url)

            # Execute CREATE TABLE
            result = executor.execute_ddl(table_sql)

            if result.get("success"):
                logger.debug(
                    f"Sync DDL: Created table for model '{model_name}' successfully"
                )

                # Also create indexes if any
                indexes = self._generate_indexes_sql(model_name, db_type)
                for index_sql in indexes:
                    idx_result = executor.execute_ddl(index_sql)
                    if not idx_result.get("success"):
                        logger.warning(
                            f"Failed to create index for '{model_name}': {idx_result.get('error')}"
                        )

                # Mark as ensured in cache
                schema_checksum = None
                model_info = self._models.get(model_name)
                if model_info and self._schema_cache.enable_schema_validation:
                    schema_checksum = self._calculate_schema_checksum(
                        model_info["fields"]
                    )
                self._schema_cache.mark_table_ensured(
                    model_name, database_url, schema_checksum
                )

                return True
            else:
                # Check if it's "table already exists" - that's OK
                error = result.get("error", "")
                if "already exists" in error.lower():
                    logger.debug(f"Table for model '{model_name}' already exists (OK)")
                    # Mark as ensured in cache
                    self._schema_cache.mark_table_ensured(
                        model_name, database_url, None
                    )
                    return True

                logger.warning(f"Sync DDL failed for model '{model_name}': {error}")
                return False

        except ImportError as e:
            # psycopg2 not installed - fall back to deferred creation
            logger.warning(
                f"SyncDDLExecutor not available ({e}). "
                f"Table for '{model_name}' will be created on first access."
            )
            return False

        except Exception as e:
            logger.warning(
                f"Sync table creation failed for '{model_name}': {e}. "
                f"Table will be created on first access."
            )
            return False

    def _create_tables_batch(self, model_names: list) -> None:
        """Create tables for multiple models in a single database connection.

        Uses SyncDDLExecutor.execute_ddl_batch() to run all CREATE TABLE and
        CREATE INDEX statements through one connection. This eliminates the
        rapid open/close churn that overwhelms Docker Desktop's vpnkit proxy
        when creating tables for many models (e.g., 21 models = 63+ connections
        reduced to 1 connection).

        Falls back to per-model _create_table_sync() if batching fails.

        Args:
            model_names: List of model names to create tables for.
        """
        if not model_names:
            return

        database_url = self.config.database.url
        if not database_url:
            return

        # Skip batch for in-memory SQLite (needs shared connection for CRUD)
        if database_url == ":memory:" or database_url == "sqlite:///:memory:":
            for name in model_names:
                self._create_table_sync(name)
            return

        # Skip for MongoDB
        db_type = self._detect_database_type()
        if db_type == "mongodb":
            return

        try:
            from ..migrations.sync_ddl_executor import SyncDDLExecutor

            # Collect all DDL statements
            all_sql: list = []
            model_sql_map: dict = {}  # model_name -> (start_idx, count)
            for model_name in model_names:
                start = len(all_sql)
                table_sql = self._generate_create_table_sql(model_name, db_type)
                all_sql.append(table_sql)
                index_sqls = self._generate_indexes_sql(model_name, db_type)
                all_sql.extend(index_sqls)
                model_sql_map[model_name] = (start, len(all_sql) - start)

            if not all_sql:
                return

            # Execute all DDL in one connection
            executor = SyncDDLExecutor(database_url)
            result = executor.execute_ddl_batch(all_sql)

            if result.get("success"):
                logger.debug(
                    "Batch DDL: created %d tables + indexes in single connection",
                    len(model_names),
                )
                # Mark all as ensured in cache
                for model_name in model_names:
                    schema_checksum = None
                    model_info = self._models.get(model_name)
                    if model_info and self._schema_cache.enable_schema_validation:
                        schema_checksum = self._calculate_schema_checksum(
                            model_info["fields"]
                        )
                    self._schema_cache.mark_table_ensured(
                        model_name, database_url, schema_checksum
                    )
            else:
                error = result.get("error", "")
                executed = result.get("executed_count", 0)
                if "already exists" in error.lower():
                    logger.debug(
                        "Batch DDL: some tables already exist (OK), "
                        "executed %d/%d statements",
                        executed,
                        len(all_sql),
                    )
                    # Mark all as ensured (they exist either way)
                    for model_name in model_names:
                        self._schema_cache.mark_table_ensured(
                            model_name, database_url, None
                        )
                else:
                    logger.warning(
                        "Batch DDL failed at statement %d: %s. "
                        "Falling back to per-model creation.",
                        executed + 1,
                        error,
                    )
                    # Fallback: try each model individually
                    for model_name in model_names:
                        self._create_table_sync(model_name)

        except ImportError:
            # SyncDDLExecutor not available — fall back to per-model
            for model_name in model_names:
                self._create_table_sync(model_name)
        except Exception as e:
            logger.warning(
                "Batch DDL failed: %s. Falling back to per-model creation.", e
            )
            for model_name in model_names:
                self._create_table_sync(model_name)

    def create_tables_sync(self, database_type: str = None):
        """Create database tables for all registered models using synchronous DDL.

        This method uses SyncDDLExecutor which works in ANY context:
        - CLI scripts (no event loop)
        - FastAPI/Docker (event loop running) - CRITICAL FIX!
        - pytest (both sync and async)

        No event loop involvement - uses psycopg2/sqlite3 synchronous drivers.

        This is the recommended method for Docker/FastAPI deployments where
        event loop boundary issues make async table creation problematic.

        Args:
            database_type: Target database type ('postgresql', 'mysql', 'sqlite').
                          If None, auto-detected from URL.

        Returns:
            bool: True if all tables were created successfully
        """
        self._ensure_connected()
        try:
            from ..migrations.sync_ddl_executor import SyncDDLExecutor

            # Get database URL
            database_url = self.config.database.url
            if not database_url:
                logger.warning(
                    "No database URL configured, skipping sync table creation"
                )
                return False

            # CRITICAL: In-memory SQLite databases cannot use sync DDL
            # SyncDDLExecutor creates a separate connection, so tables would be
            # in a different in-memory database than CRUD operations.
            if database_url == ":memory:" or database_url == "sqlite:///:memory:":
                logger.warning(
                    "create_tables_sync() does not support in-memory databases. "
                    "Use await db.create_tables_async() instead for :memory: databases."
                )
                return False

            # Auto-detect database type if not provided
            if database_type is None:
                database_type = self._detect_database_type()

            # CRITICAL: MongoDB doesn't use SQL DDL - collections are created on first insert
            if database_type == "mongodb":
                logger.debug(
                    "create_tables_sync() not needed for MongoDB. "
                    "MongoDB is schemaless - collections are created automatically on first insert."
                )
                return True  # Return True - no action needed

            # Generate complete schema SQL
            schema_sql = self.generate_complete_schema_sql(database_type)

            logger.debug(
                f"Creating database schema for {len(self._models)} models using sync DDL"
            )

            # Create SyncDDLExecutor
            executor = SyncDDLExecutor(database_url)

            # Collect all DDL statements
            all_statements = []
            all_statements.extend(schema_sql.get("tables", []))
            all_statements.extend(schema_sql.get("indexes", []))
            all_statements.extend(schema_sql.get("foreign_keys", []))

            # Execute all DDL statements
            success_count = 0
            for statement in all_statements:
                if statement.strip():
                    result = executor.execute_ddl(statement)
                    if result.get("success"):
                        success_count += 1
                        logger.debug(f"Sync DDL executed: {statement[:60]}...")
                    else:
                        error = result.get("error", "")
                        # "already exists" is OK
                        if "already exists" in error.lower():
                            success_count += 1
                            logger.debug(
                                f"Table/index already exists (OK): {statement[:60]}..."
                            )
                        else:
                            logger.warning(f"Sync DDL failed: {error}")

            logger.debug(
                f"Sync DDL: Successfully executed {success_count}/{len(all_statements)} statements"
            )

            # Mark all models as ensured in cache
            for model_name in self._models:
                self._schema_cache.mark_table_ensured(model_name, database_url, None)

            return True

        except ImportError as e:
            logger.error(
                f"SyncDDLExecutor not available: {e}. "
                f"Install psycopg2-binary for PostgreSQL sync DDL support."
            )
            return False

        except Exception as e:
            logger.error(f"Sync table creation failed: {e}")
            return False

    def _register_specialized_nodes(self):
        """Register DataFlow specialized nodes."""
        try:
            from kailash.nodes.base import NodeRegistry

            if not hasattr(NodeRegistry, "register"):
                return  # kailash 3.x: node registration not supported
        except ImportError:
            return  # kailash 3.x: node registration not supported

        try:
            from ..nodes import (
                MigrationNode,
                SchemaModificationNode,
                TransactionCommitNode,
                TransactionRollbackNode,
                TransactionScopeNode,
            )
        except ImportError:
            return  # nodes not available in this kailash version

        # Register transaction nodes
        NodeRegistry.register(TransactionScopeNode, alias="TransactionScopeNode")
        NodeRegistry.register(TransactionCommitNode, alias="TransactionCommitNode")
        NodeRegistry.register(TransactionRollbackNode, alias="TransactionRollbackNode")

        # Register schema nodes
        NodeRegistry.register(SchemaModificationNode, alias="SchemaModificationNode")
        NodeRegistry.register(MigrationNode, alias="MigrationNode")

        # Store in _nodes for testing
        self._nodes["TransactionScopeNode"] = TransactionScopeNode
        self._nodes["TransactionCommitNode"] = TransactionCommitNode
        self._nodes["TransactionRollbackNode"] = TransactionRollbackNode
        self._nodes["SchemaModificationNode"] = SchemaModificationNode
        self._nodes["MigrationNode"] = MigrationNode

    def _generate_crud_nodes(self, model_name: str, fields: Dict[str, Any]):
        """Generate CRUD nodes for a model."""
        # Delegate to node generator - it handles all storage in _nodes
        # NodeGenerator is TDD-aware and will use test connections if available
        nodes = self._node_generator.generate_crud_nodes(model_name, fields)

        # The NodeGenerator already stores nodes in self._nodes, so we don't need fallback
        if not nodes:
            logger.warning(f"Failed to generate CRUD nodes for model {model_name}")
            # Enhanced error with catalog-based solutions (DF-703)
            if ErrorEnhancer is not None:
                raise ErrorEnhancer.enhance_node_generation_failed(
                    model_name=model_name,
                    generation_error="CRUD node generation returned empty result",
                )

        # Log TDD context if active
        if self._tdd_mode and self._test_context:
            logger.debug(
                f"Generated TDD-aware CRUD nodes for model {model_name} in test {self._test_context.test_id}"
            )

    def _generate_bulk_nodes(self, model_name: str, fields: Dict[str, Any]):
        """Generate bulk operation nodes for a model."""
        # Delegate to node generator - it handles all storage in _nodes
        # NodeGenerator is TDD-aware and will use test connections if available
        nodes = self._node_generator.generate_bulk_nodes(model_name, fields)

        # The NodeGenerator already stores nodes in self._nodes, so we don't need fallback
        if not nodes:
            logger.warning(f"Failed to generate bulk nodes for model {model_name}")
            # Enhanced error with catalog-based solutions (DF-703)
            if ErrorEnhancer is not None:
                raise ErrorEnhancer.enhance_node_generation_failed(
                    model_name=model_name,
                    generation_error="Bulk node generation returned empty result",
                )

        # Log TDD context if active
        if self._tdd_mode and self._test_context:
            logger.debug(
                f"Generated TDD-aware bulk nodes for model {model_name} in test {self._test_context.test_id}"
            )

    def _auto_detect_relationships(self, model_name: str, fields: Dict[str, Any]):
        """Auto-detect relationships from database schema foreign keys.

        This method analyzes the discovered schema and automatically creates
        relationship definitions based on foreign key constraints.
        """
        # Skip schema discovery for SQLite databases (not supported for in-memory)
        database_url = self.config.database.url or ":memory:"
        if database_url == ":memory:" or "sqlite" in database_url.lower():
            # For SQLite, skip relationship auto-detection
            logger.debug(
                f"Skipping relationship auto-detection for SQLite database: {database_url}"
            )
            return

        # Get the discovered schema for PostgreSQL
        schema = self.discover_schema()
        table_name = self._class_name_to_table_name(model_name)

        # Initialize relationships storage if not exists
        if not hasattr(self, "_relationships"):
            self._relationships = {}

        if table_name not in self._relationships:
            self._relationships[table_name] = {}

        # Check if this table has foreign keys in the schema
        if table_name in schema:
            table_info = schema[table_name]
            foreign_keys = table_info.get("foreign_keys", [])

            # Process each foreign key to create relationships
            for fk in foreign_keys:
                rel_name = self._foreign_key_to_relationship_name(fk["column_name"])

                # Create belongs_to relationship
                self._relationships[table_name][rel_name] = {
                    "type": "belongs_to",
                    "target_table": fk["foreign_table_name"],
                    "foreign_key": fk["column_name"],
                    "target_key": fk["foreign_column_name"],
                    "auto_detected": True,
                }

                logger.debug(
                    f"Auto-detected relationship: {table_name}.{rel_name} -> {fk['foreign_table_name']}"
                )

            # Also create reverse has_many relationships
            self._create_reverse_relationships(table_name, schema)

    async def _auto_detect_relationships_async(
        self, model_name: str, fields: Dict[str, Any]
    ) -> None:
        """Async version of _auto_detect_relationships for use in async contexts.

        DATAFLOW-ASYNC-MODEL-DECORATOR-001: This method is used during initialize()
        to process deferred relationship detection for models registered via @db.model.

        This method analyzes the discovered schema and automatically creates
        relationship definitions based on foreign key constraints.

        Args:
            model_name: Name of the model to detect relationships for
            fields: Model field definitions
        """
        database_url = self.config.database.url or ":memory:"

        # Skip for SQLite (no foreign key introspection for in-memory)
        if database_url == ":memory:" or "sqlite" in database_url.lower():
            logger.debug(
                f"Skipping async relationship auto-detection for SQLite database: {database_url}"
            )
            return

        # Skip for MongoDB (document databases don't have foreign keys)
        if "mongodb" in database_url.lower():
            logger.debug(
                f"Skipping async relationship auto-detection for MongoDB: {database_url}"
            )
            return

        try:
            # Use async schema discovery to avoid blocking
            schema = await self.discover_schema_async(use_real_inspection=True)
        except Exception as e:
            # If schema discovery fails, log and continue without relationships
            # This is non-fatal - models work fine without auto-detected relationships
            logger.debug(
                f"Async relationship auto-detection skipped for {model_name}: {e}"
            )
            return

        table_name = self._class_name_to_table_name(model_name)

        # Initialize relationships storage if not exists
        if not hasattr(self, "_relationships"):
            self._relationships = {}

        if table_name not in self._relationships:
            self._relationships[table_name] = {}

        # Check if this table has foreign keys in the schema
        if table_name in schema:
            table_info = schema[table_name]
            foreign_keys = table_info.get("foreign_keys", [])

            # Process each foreign key to create relationships
            for fk in foreign_keys:
                rel_name = self._foreign_key_to_relationship_name(fk["column_name"])

                # Create belongs_to relationship
                self._relationships[table_name][rel_name] = {
                    "type": "belongs_to",
                    "target_table": fk["foreign_table_name"],
                    "foreign_key": fk["column_name"],
                    "target_key": fk["foreign_column_name"],
                    "auto_detected": True,
                }

                logger.debug(
                    f"Auto-detected relationship (async): {table_name}.{rel_name} -> {fk['foreign_table_name']}"
                )

            # Also create reverse has_many relationships
            self._create_reverse_relationships(table_name, schema)

    async def _process_pending_relationship_detection(self) -> None:
        """Process all pending relationship detections asynchronously.

        DATAFLOW-ASYNC-MODEL-DECORATOR-001: This method is called during initialize()
        to process models that were marked for deferred relationship detection.

        This enables @db.model to work in async contexts (pytest async fixtures,
        FastAPI lifespan events, etc.) without failing.
        """
        if not self._pending_relationship_detection:
            return

        pending_models = list(self._pending_relationship_detection)
        self._pending_relationship_detection.clear()

        logger.debug(
            f"Processing deferred relationship detection for {len(pending_models)} models"
        )

        for model_name in pending_models:
            if model_name in self._model_fields:
                fields = self._model_fields[model_name]
                await self._auto_detect_relationships_async(model_name, fields)

        logger.debug("Deferred relationship detection completed")

    async def _validate_existing_schema_compatibility(
        self, model_name: str, target_schema: Dict[str, Any]
    ) -> bool:
        """
        Validate that existing database schema is compatible with DataFlow models.

        This prevents destructive migrations on existing databases by checking:
        1. All model fields exist in database (or have defaults)
        2. Field types are compatible
        3. No required fields are missing

        Returns:
            True if schemas are compatible, False otherwise
        """
        if not self._migration_system:
            logger.warning("Migration system not initialized, cannot validate schema")
            return False

        try:
            # Use the schema state manager to get current database schema via WorkflowBuilder
            if hasattr(self._migration_system, "_schema_state_manager"):
                schema_manager = self._migration_system._schema_state_manager
                current_schema_obj = schema_manager._fetch_fresh_schema()
                current_schema = current_schema_obj.tables
            else:
                # Fallback: get schema via WorkflowBuilder pattern
                current_schema = await self._get_current_schema_via_workflow()

            # Check each table in target schema
            for table_name, table_def in target_schema.items():
                if table_name not in current_schema:
                    logger.error(
                        f"Table '{table_name}' does not exist in database. "
                        f"Cannot use existing_schema_mode without required tables."
                    )
                    return False

                # Perform compatibility check
                if not self._check_table_compatibility(
                    current_schema[table_name], table_def, table_name
                ):
                    logger.error(
                        f"Table '{table_name}' schema is not compatible with model. "
                        f"Required fields may be missing or types may not match."
                    )
                    return False

            logger.debug(
                f"Schema validation passed for model '{model_name}'. "
                f"Existing database is compatible."
            )
            return True

        except Exception as e:
            logger.error(f"Schema validation failed: {e}")
            return False

    async def _get_current_schema_via_workflow(self) -> Dict[str, Any]:
        """Get current database schema using WorkflowBuilder pattern."""
        from kailash.workflow.builder import WorkflowBuilder

        workflow = WorkflowBuilder()
        connection_string = self.config.database.get_connection_url(
            self.config.environment
        )

        # Auto-detect database type from connection string
        from ..adapters.connection_parser import ConnectionParser

        database_type = ConnectionParser.detect_database_type(connection_string)

        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "get_schema",
            {
                "connection_string": connection_string,
                "database_type": database_type,
                "query": """
                SELECT
                    t.table_name,
                    c.column_name,
                    c.data_type,
                    c.is_nullable,
                    c.column_default,
                    CASE WHEN pk.column_name IS NOT NULL THEN true ELSE false END as is_primary_key
                FROM information_schema.tables t
                LEFT JOIN information_schema.columns c ON t.table_name = c.table_name
                LEFT JOIN (
                    SELECT ku.column_name, ku.table_name
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage ku ON tc.constraint_name = ku.constraint_name
                    WHERE tc.constraint_type = 'PRIMARY KEY'
                ) pk ON c.table_name = pk.table_name AND c.column_name = pk.column_name
                WHERE t.table_schema = 'public'
                  AND t.table_type = 'BASE TABLE'
                  AND t.table_name NOT LIKE 'dataflow_%'
                ORDER BY t.table_name, c.ordinal_position
            """,
            },
        )

        # M2-001: Reuse shared runtime instead of creating a new one
        runtime = self.runtime
        logger.debug("_get_current_schema_via_workflow: Using shared runtime")

        results, _ = runtime.execute(workflow.build())

        if results.get("get_schema", {}).get("error"):
            logger.error(f"Failed to fetch schema: {results['get_schema']['error']}")
            return {}

        # Extract data from results
        if (
            "result" in results["get_schema"]
            and "data" in results["get_schema"]["result"]
        ):
            data = results["get_schema"]["result"]["data"]
        elif "data" in results["get_schema"]:
            data = results["get_schema"]["data"]
        else:
            data = []

        # Parse schema data into table structure
        tables = {}
        if data:
            current_table = None
            for row in data:
                table_name = row.get("table_name")
                if table_name and table_name != current_table:
                    tables[table_name] = {"columns": {}}
                    current_table = table_name

                column_name = row.get("column_name")
                if column_name:
                    tables[table_name]["columns"][column_name] = {
                        "type": row.get("data_type"),
                        "nullable": row.get("is_nullable") == "YES",
                        "default": row.get("column_default"),
                        "primary_key": row.get("is_primary_key", False),
                    }

        return tables

    def _check_table_compatibility(
        self, current_table: Dict[str, Any], target_table_def, table_name: str
    ) -> bool:
        """Check if current table schema is compatible with target model definition."""
        current_columns = current_table.get("columns", {})

        # If target_table_def is a TableDefinition object, extract columns
        if hasattr(target_table_def, "columns"):
            target_columns = {col.name: col for col in target_table_def.columns}
        else:
            # Assume it's a dictionary
            target_columns = target_table_def.get("columns", {})

        # Check if all required model fields exist in database
        for field_name, field_def in target_columns.items():
            if field_name not in current_columns:
                # Check if field has a default value
                has_default = False
                if hasattr(field_def, "default") and field_def.default is not None:
                    has_default = True
                elif (
                    isinstance(field_def, dict) and field_def.get("default") is not None
                ):
                    has_default = True

                if not has_default:
                    logger.error(
                        f"Required field '{field_name}' missing from table '{table_name}' "
                        f"and has no default value"
                    )
                    return False
                else:
                    logger.debug(
                        f"Field '{field_name}' missing from table '{table_name}' "
                        f"but has default value - compatible"
                    )

        # Basic type compatibility could be added here
        # For now, we just check field existence
        return True

    def get_connection(self):
        """Get database connection context manager.

        Returns:
            Context manager that yields async database connection
        """
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def connection_context():
            """Context manager for database connections."""
            import asyncpg

            # Get database URL
            db_url = self.config.database.get_connection_url(self.config.environment)

            # Create connection
            connection = await asyncpg.connect(db_url)

            try:
                yield connection
            finally:
                await connection.close()

        return connection_context()

    async def _get_async_database_connection(self):
        """Get async database connection for validation or testing."""
        # Check if we're in TDD mode and have a test context
        from ..testing.tdd_support import (
            get_database_manager,
            get_test_context,
            is_tdd_mode,
        )

        if is_tdd_mode():
            test_context = get_test_context()
            if test_context and test_context.connection:
                # Return existing test connection for isolation
                return test_context.connection
            elif test_context:
                # Get connection through TDD infrastructure
                db_manager = get_database_manager()
                return await db_manager.get_test_connection(test_context)

        # Default production behavior - create new connection
        db_url = self.config.database.url
        if db_url is None:
            raise ValueError("Database URL is not configured")

        # Database-aware connection handling
        if db_url.startswith("postgresql://"):
            import asyncpg

            if db_url.startswith("postgresql://"):
                db_url = db_url.replace("postgresql://", "")
            return await asyncpg.connect(f"postgresql://{db_url}")
        elif db_url.startswith("sqlite://") or db_url == ":memory:":
            import aiosqlite

            if db_url == ":memory:":
                # Use URI shared-cache so multiple connections see the same
                # in-memory database (each aiosqlite.connect(":memory:") would
                # create a SEPARATE database otherwise).
                if not hasattr(self, "_memory_db_uri"):
                    self._memory_db_uri = (
                        f"file:engine_{id(self)}?mode=memory&cache=shared"
                    )
                return await aiosqlite.connect(self._memory_db_uri, uri=True)
            else:
                # Extract file path from sqlite:///path/to/file.db
                file_path = db_url.replace("sqlite:///", "/")
                return await aiosqlite.connect(file_path)
        else:
            # Enhanced error with catalog-based solutions (DF-401)
            if ErrorEnhancer is not None:
                raise ErrorEnhancer.enhance_invalid_database_url(
                    database_url=db_url,
                    error_message="Database type not supported (only PostgreSQL, MySQL, SQLite)",
                )

    def _get_table_name(self, model_name: str) -> str:
        """Get the table name for a model, respecting __tablename__ override.

        This method first checks if the model has a custom table_name stored
        in the model registry (from __tablename__ attribute), and falls back
        to the default class_name_to_table_name conversion if not found.

        Args:
            model_name: The model name (e.g., "User")

        Returns:
            The table name to use for database operations
        """
        # Check if model is registered with a custom table name
        if model_name in self._models:
            model_info = self._models[model_name]
            if isinstance(model_info, dict) and "table_name" in model_info:
                return model_info["table_name"]

        # Fall back to default conversion
        return self._class_name_to_table_name(model_name)

    # Comprehensive irregular plurals map for English nouns
    # Source: https://github.com/sindresorhus/irregular-plurals
    # Used for accurate table name pluralization
    IRREGULAR_PLURALS = {
        # Common irregular plurals (most likely to appear in model names)
        "person": "people",
        "man": "men",
        "woman": "women",
        "child": "children",
        "foot": "feet",
        "tooth": "teeth",
        "goose": "geese",
        "mouse": "mice",
        "louse": "lice",
        "ox": "oxen",
        "die": "dice",
        "penny": "pennies",
        "self": "selves",
        "leaf": "leaves",
        "half": "halves",
        "knife": "knives",
        "wife": "wives",
        "life": "lives",
        "elf": "elves",
        "loaf": "loaves",
        "thief": "thieves",
        "shelf": "shelves",
        "calf": "calves",
        "wolf": "wolves",
        "scarf": "scarves",
        "wharf": "wharves",
        "hoof": "hooves",
        # Latin/Greek endings
        "analysis": "analyses",
        "basis": "bases",
        "crisis": "crises",
        "diagnosis": "diagnoses",
        "ellipsis": "ellipses",
        "hypothesis": "hypotheses",
        "oasis": "oases",
        "paralysis": "paralyses",
        "parenthesis": "parentheses",
        "synopsis": "synopses",
        "synthesis": "syntheses",
        "thesis": "theses",
        "nemesis": "nemeses",
        "neurosis": "neuroses",
        "prognosis": "prognoses",
        "axis": "axes",
        "appendix": "appendixes",
        "index": "indexes",
        "matrix": "matrices",
        "vertex": "vertices",
        "vortex": "vortices",
        "apex": "apexes",
        "cortex": "cortices",
        "latex": "latexes",
        "simplex": "simplexes",
        "codex": "codices",
        # Latin -um → -a
        "datum": "data",
        "medium": "media",
        "bacterium": "bacteria",
        "curriculum": "curricula",
        "memorandum": "memoranda",
        "millennium": "millennia",
        "symposium": "symposia",
        "stadium": "stadiums",
        "aquarium": "aquariums",
        "compendium": "compendiums",
        "consortium": "consortia",
        "referendum": "referendums",
        "forum": "forums",
        "museum": "museums",
        "spectrum": "spectra",
        "stratum": "strata",
        "addendum": "addenda",
        "erratum": "errata",
        "ovum": "ova",
        "quantum": "quanta",
        "ultimatum": "ultimatums",
        "vacuum": "vacuums",
        # Latin -us → -i
        "alumnus": "alumni",
        "cactus": "cactuses",
        "focus": "focuses",
        "fungus": "fungi",
        "nucleus": "nuclei",
        "radius": "radii",
        "stimulus": "stimuli",
        "syllabus": "syllabuses",
        "campus": "campuses",
        "census": "censuses",
        "corpus": "corpora",
        "genus": "genera",
        "status": "statuses",
        "virus": "viruses",
        "bonus": "bonuses",
        "bus": "buses",
        "octopus": "octopuses",
        "platypus": "platypuses",
        "prospectus": "prospectuses",
        "apparatus": "apparatuses",
        "nexus": "nexuses",
        "plexus": "plexuses",
        "sinus": "sinuses",
        "hiatus": "hiatuses",
        "impetus": "impetuses",
        # Latin -a → -ae
        "alumna": "alumnae",
        "antenna": "antennas",
        "formula": "formulas",
        "larva": "larvae",
        "vertebra": "vertebrae",
        "nebula": "nebulas",
        "aurora": "auroras",
        # Greek -on → -a
        "criterion": "criteria",
        "phenomenon": "phenomena",
        "automaton": "automatons",
        # Animals (same singular/plural)
        "deer": "deer",
        "fish": "fish",
        "sheep": "sheep",
        "moose": "moose",
        "bison": "bison",
        "salmon": "salmon",
        "trout": "trout",
        "shrimp": "shrimp",
        "swine": "swine",
        "buffalo": "buffalo",
        "elk": "elk",
        "squid": "squid",
        "tuna": "tuna",
        "cod": "cod",
        "pike": "pike",
        # Other unchanged plurals
        "series": "series",
        "species": "species",
        "aircraft": "aircraft",
        "spacecraft": "spacecraft",
        "hovercraft": "hovercraft",
        "watercraft": "watercraft",
        "offspring": "offspring",
        "means": "means",
        "news": "news",
        "headquarters": "headquarters",
        "barracks": "barracks",
        "gallows": "gallows",
        "corps": "corps",
        "chassis": "chassis",
        "innings": "innings",
        "reindeer": "reindeer",
        "wildebeest": "wildebeest",
        # Uncountable nouns (keep singular)
        "equipment": "equipment",
        "information": "information",
        "knowledge": "knowledge",
        "furniture": "furniture",
        "luggage": "luggage",
        "software": "software",
        "hardware": "hardware",
        "firmware": "firmware",
        "malware": "malware",
        "data": "data",
        "media": "media",  # Already plural (singular is "medium")
        "criteria": "criteria",  # Already plural (singular is "criterion")
        "bacteria": "bacteria",  # Already plural (singular is "bacterium")
        "phenomena": "phenomena",  # Already plural (singular is "phenomenon")
        "advice": "advice",
        "research": "research",
        "progress": "progress",
        "traffic": "traffic",
        "music": "music",
        "weather": "weather",
        "money": "money",
        "evidence": "evidence",
        "homework": "homework",
        "housework": "housework",
        "feedback": "feedback",
        "metadata": "metadata",
        "analytics": "analytics",
        "economics": "economics",
        "physics": "physics",
        "mathematics": "mathematics",
        "statistics": "statistics",
        "athletics": "athletics",
        "politics": "politics",
        "ethics": "ethics",
        "logistics": "logistics",
        "genetics": "genetics",
        "linguistics": "linguistics",
        # -o endings (common ones that take -es)
        "hero": "heroes",
        "potato": "potatoes",
        "tomato": "tomatoes",
        "echo": "echoes",
        "embargo": "embargoes",
        "veto": "vetoes",
        "torpedo": "torpedoes",
        "volcano": "volcanoes",
        "tornado": "tornadoes",
        # -o endings (that take -s, not -es)
        "photo": "photos",
        "piano": "pianos",
        "memo": "memos",
        "video": "videos",
        "audio": "audio",
        "radio": "radios",
        "ratio": "ratios",
        "scenario": "scenarios",
        "studio": "studios",
        "portfolio": "portfolios",
        "duo": "duos",
        "trio": "trios",
        "solo": "solos",
        "auto": "autos",
        "zoo": "zoos",
        "tattoo": "tattoos",
        "kangaroo": "kangaroos",
        "embryo": "embryos",
        "manifesto": "manifestos",
        "fiasco": "fiascos",
        "ghetto": "ghettos",
        "inferno": "infernos",
        # -man/-woman compounds
        "businessman": "businessmen",
        "businesswoman": "businesswomen",
        "gentleman": "gentlemen",
        "policeman": "policemen",
        "policewoman": "policewomen",
        "fireman": "firemen",
        "salesman": "salesmen",
        "saleswoman": "saleswomen",
        "spokesman": "spokesmen",
        "spokeswoman": "spokeswomen",
        "chairman": "chairmen",
        "chairwoman": "chairwomen",
        "craftsman": "craftsmen",
        "serviceman": "servicemen",
        "servicewoman": "servicewomen",
        # Compound nouns with irregular plurals
        "passerby": "passersby",
        "mother-in-law": "mothers-in-law",
        "father-in-law": "fathers-in-law",
        "sister-in-law": "sisters-in-law",
        "brother-in-law": "brothers-in-law",
        "attorney-general": "attorneys-general",
        "court-martial": "courts-martial",
        # Tech/database common terms
        "schema": "schemas",
        "alias": "aliases",
        "cache": "caches",
        "batch": "batches",
        "patch": "patches",
        "match": "matches",
        "search": "searches",
        "fetch": "fetches",
        "dispatch": "dispatches",
        "flash": "flashes",
        "crash": "crashes",
        "hash": "hashes",
        "stash": "stashes",
        "mesh": "meshes",
        "reflex": "reflexes",
        "complex": "complexes",
        "prefix": "prefixes",
        "suffix": "suffixes",
        "affix": "affixes",
        "annex": "annexes",
        "fax": "faxes",
        "tax": "taxes",
        "box": "boxes",
        "fox": "foxes",
        "mix": "mixes",
        "fix": "fixes",
        "flux": "fluxes",
        "crux": "cruxes",
        "hoax": "hoaxes",
        "relax": "relaxes",
        "wax": "waxes",
        "quiz": "quizzes",
        "buzz": "buzzes",
        "fizz": "fizzes",
        "jazz": "jazzes",
        "fuzz": "fuzzes",
        # Common business/domain terms
        "company": "companies",
        "industry": "industries",
        "category": "categories",
        "story": "stories",
        "history": "histories",
        "inventory": "inventories",
        "factory": "factories",
        "territory": "territories",
        "accessory": "accessories",
        "directory": "directories",
        "repository": "repositories",
        "query": "queries",
        "inquiry": "inquiries",
        "entry": "entries",
        "delivery": "deliveries",
        "discovery": "discoveries",
        "recovery": "recoveries",
        "gallery": "galleries",
        "salary": "salaries",
        "summary": "summaries",
        "boundary": "boundaries",
        "library": "libraries",
        "entity": "entities",
        "identity": "identities",
        "property": "properties",
        "activity": "activities",
        "facility": "facilities",
        "ability": "abilities",
        "capability": "capabilities",
        "visibility": "visibilities",
        "availability": "availabilities",
        "utility": "utilities",
        "opportunity": "opportunities",
        "community": "communities",
        "priority": "priorities",
        "authority": "authorities",
        "security": "securities",
        "policy": "policies",
        "strategy": "strategies",
        "legacy": "legacies",
        "agency": "agencies",
        "currency": "currencies",
        "frequency": "frequencies",
        "emergency": "emergencies",
        "dependency": "dependencies",
        "efficiency": "efficiencies",
        "deficiency": "deficiencies",
        "tendency": "tendencies",
        "consistency": "consistencies",
        "redundancy": "redundancies",
        "occupancy": "occupancies",
        "warranty": "warranties",
        "anomaly": "anomalies",
        "assembly": "assemblies",
        "supply": "supplies",
        "reply": "replies",
        "copy": "copies",
        "proxy": "proxies",
        "body": "bodies",
        "everybody": "everybodies",
        "somebody": "somebodies",
        "nobody": "nobodies",
        "study": "studies",
        "duty": "duties",
        "party": "parties",
        "city": "cities",
        "quality": "qualities",
        "quantity": "quantities",
        "variety": "varieties",
        "specialty": "specialties",
        "penalty": "penalties",
        "loyalty": "loyalties",
        "royalty": "royalties",
        "casualty": "casualties",
        "treaty": "treaties",
        "academy": "academies",
        "pharmacy": "pharmacies",
        "embassy": "embassies",
        "fantasy": "fantasies",
    }

    def _pluralize(self, word: str) -> str:
        """
        Convert a singular English word to its plural form.

        Uses comprehensive rules and irregular plural mappings for accurate pluralization.
        This is used for generating table names from model class names.

        Args:
            word: Singular word to pluralize (lowercase)

        Returns:
            Plural form of the word
        """
        # Check irregular plurals first (case-insensitive lookup)
        word_lower = word.lower()
        if word_lower in self.IRREGULAR_PLURALS:
            return self.IRREGULAR_PLURALS[word_lower]

        # Handle compound words with underscores (e.g., "user_activity" -> "user_activities")
        if "_" in word:
            parts = word.rsplit("_", 1)
            if len(parts) == 2:
                return parts[0] + "_" + self._pluralize(parts[1])

        # Rule 1: Words ending in 's', 'x', 'z', 'ch', 'sh' → add 'es'
        if word_lower.endswith(("s", "x", "z", "ch", "sh")):
            return word + "es"

        # Rule 2: Words ending in 'y' preceded by a consonant → change 'y' to 'ies'
        if word_lower.endswith("y") and len(word) > 1:
            # Check if preceded by a consonant (not a, e, i, o, u)
            if word[-2].lower() not in "aeiou":
                return word[:-1] + "ies"

        # Rule 3: Words ending in 'f' or 'fe' → change to 'ves'
        # (Only for common words not already in irregular map)
        if word_lower.endswith("fe"):
            return word[:-2] + "ves"
        if word_lower.endswith("f") and not word_lower.endswith("ff"):
            # Check if it's a word that follows this rule
            # Most -f words that change to -ves are already in IRREGULAR_PLURALS
            # For unknown words ending in -f, we'll add -s (safer default)
            pass

        # Rule 4: Words ending in 'o' preceded by a consonant
        # This is complex - some take -es, some take -s
        # Most common ones are handled in IRREGULAR_PLURALS
        # Default to -s for unknown -o words (safer for technical terms)

        # Default rule: add 's'
        return word + "s"

    def _class_name_to_table_name(self, class_name: str) -> str:
        """
        Convert class name to table name with proper pluralization.

        Handles:
        - CamelCase to snake_case conversion
        - Proper English pluralization rules
        - Irregular plurals (person → people, etc.)
        - Words ending in y, s, x, z, ch, sh, f, fe, o

        Examples:
            User → users
            Person → people
            Category → categories
            Summary → summaries
            UserActivity → user_activities
            OrderStatus → order_statuses
            Child → children
        """
        import re

        # First, handle sequences of capitals followed by lowercase (e.g., 'XMLParser' -> 'XML_Parser')
        s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", class_name)
        # Then handle remaining transitions from lowercase to uppercase
        s2 = re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1)
        # Convert to lowercase
        snake_case = s2.lower()

        # Apply proper English pluralization
        table_name = self._pluralize(snake_case)
        return table_name

    def _foreign_key_to_relationship_name(self, foreign_key_column: str) -> str:
        """Convert foreign key column name to relationship name."""
        # Remove '_id' suffix to get relationship name
        if foreign_key_column.endswith("_id"):
            return foreign_key_column[:-3]
        return foreign_key_column

    def _create_reverse_relationships(self, table_name: str, schema: Dict[str, Any]):
        """Create reverse has_many relationships for foreign keys pointing to this table."""
        for other_table, table_info in schema.items():
            if other_table == table_name:
                continue

            foreign_keys = table_info.get("foreign_keys", [])
            for fk in foreign_keys:
                if fk["foreign_table_name"] == table_name:
                    # This foreign key points to our table, create reverse relationship
                    if other_table not in self._relationships:
                        self._relationships[other_table] = {}

                    # Create has_many relationship name (pluralize the referencing table)
                    rel_name = (
                        other_table  # Use table name as-is since it's already plural
                    )

                    self._relationships[table_name][rel_name] = {
                        "type": "has_many",
                        "target_table": other_table,
                        "foreign_key": fk["column_name"],
                        "target_key": fk["foreign_column_name"],
                        "auto_detected": True,
                    }

                    logger.debug(
                        f"Auto-detected reverse relationship: {table_name}.{rel_name} -> {other_table}"
                    )

    def get_relationships(self, model_name: str = None) -> Dict[str, Any]:
        """Get relationship definitions for a model or all models."""
        if not hasattr(self, "_relationships"):
            return {}

        if model_name:
            table_name = self._class_name_to_table_name(model_name)
            return self._relationships.get(table_name, {})

        return self._relationships

    def health_check(self) -> Dict[str, Any]:
        """Perform a health check on the DataFlow system.

        Returns:
            Dictionary with health status information
        """
        self._ensure_connected()
        from datetime import datetime

        health_status = {
            "timestamp": datetime.utcnow().isoformat(),
            "status": "healthy",
            "database": "connected",
            "models_registered": len(self._models),
            "components": {},
        }

        try:
            # Test database connection
            if self._test_database_connection():
                health_status["database"] = "connected"
                health_status["components"]["database"] = "ok"
            else:
                health_status["status"] = "unhealthy"
                health_status["database"] = "disconnected"
                health_status["components"]["database"] = "failed"
        except Exception as e:
            health_status["status"] = "unhealthy"
            health_status["database"] = "error"
            health_status["components"]["database"] = f"error: {type(e).__name__}"
            logger.warning("Health check database error: %s", type(e).__name__)
            logger.debug("Health check database error details", exc_info=True)

        # Test other components
        try:
            health_status["components"]["bulk_operations"] = (
                "ok" if self._bulk_operations else "not_initialized"
            )
            health_status["components"]["transaction_manager"] = (
                "ok" if self._transaction_manager else "not_initialized"
            )
            health_status["components"]["connection_manager"] = (
                "ok" if self._connection_manager else "not_initialized"
            )
        except Exception as e:
            health_status["components"]["general"] = f"error: {type(e).__name__}"
            logger.warning("Health check general error: %s", e, exc_info=True)

        # Pool utilization stats (from real pool when available)
        if self._pool_monitor is not None:
            try:
                stats = self._pool_monitor.get_stats()
                health_status["pool"] = stats
                utilization = stats.get("utilization", 0)
                if utilization >= 0.95:
                    health_status["status"] = "degraded"
                    health_status["components"]["pool"] = "exhaustion_imminent"
                elif utilization >= 0.80:
                    health_status["components"]["pool"] = "high_utilization"
                else:
                    health_status["components"]["pool"] = "ok"
            except Exception:
                health_status["components"]["pool"] = "error"

        # TSG-105: Report read-replica health when dual-adapter mode is active
        if self._read_connection_manager is not None:
            import re as _re

            health_status["read_replica"] = {
                "url": (
                    _re.sub(r"://[^@]+@", "://***:***@", self._read_url)
                    if self._read_url
                    else None
                ),
                "status": "connected",
            }

        return health_status

    async def cleanup_test_tables(self) -> None:
        """Clean up test tables for testing purposes.

        This method is used in integration tests to clean up any test data
        and ensure a clean state between tests.
        """
        logger.debug("Test table cleanup called")

        try:
            # Get database connection
            conn = await self._get_async_database_connection()

            # Clean up any tables that look like test tables
            test_table_patterns = [
                "connection_tests%",
                "test_%",
                "%_test_%",
                "load_test%",
                "bulk_item%",
                "article%",
            ]

            for pattern in test_table_patterns:
                try:
                    # Use PostgreSQL-specific query to find and drop test tables
                    result = await conn.fetch(
                        """
                        SELECT schemaname, tablename
                        FROM pg_tables
                        WHERE schemaname = 'public'
                        AND tablename LIKE $1
                    """,
                        pattern.lower(),
                    )

                    for row in result:
                        table_name = row["tablename"]
                        if table_name:  # Ensure table_name is not None or empty
                            try:
                                await conn.execute(
                                    f'DROP TABLE IF EXISTS "{table_name}" CASCADE'
                                )
                                logger.debug(f"Dropped test table: {table_name}")
                            except Exception as e:
                                logger.debug(
                                    f"Failed to drop test table {table_name}: {e}"
                                )
                except Exception as e:
                    logger.debug(
                        f"Failed to query test tables with pattern {pattern}: {e}"
                    )

            await conn.close()
        except Exception as e:
            logger.debug(f"Test table cleanup failed: {e}")
            # Don't raise - cleanup failures shouldn't break tests

    def _test_database_connection(self) -> bool:
        """Test if the database connection is working.

        Returns:
            True if connection is working, False otherwise
        """
        try:
            # Basic connection test - returns True if engine can connect
            return True
        except Exception as e:
            logger.debug("Database connection test failed: %s", type(e).__name__)
            return False

    def _make_pool_stats_provider(
        self, pool_size: int, max_overflow: int
    ) -> "Callable[[], Dict[str, Any]]":
        """Create a stats provider that reads from the real connection pool.

        The provider lazily discovers the actual asyncpg/SQLAlchemy pool
        from AsyncSQLDatabaseNode._shared_pools and reads live stats.
        Falls back to configured sizes with active=0 when no pool exists yet.

        Thread safety: The daemon monitor thread calls this provider. We snapshot
        _shared_pools with list() to prevent RuntimeError on concurrent mutation.
        The provider is scoped to this DataFlow instance's database URL to avoid
        reading stats from unrelated pools in multi-database setups.
        """
        from dataflow.core.pool_monitor import pool_stats_dict

        # Scope to this instance's database URL
        db_url = self.config.database.url or self.config.database.database_url or ""

        def _provider() -> Dict[str, Any]:
            try:
                from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

                # Snapshot to prevent RuntimeError on concurrent dict mutation
                pools_snapshot = list(AsyncSQLDatabaseNode._shared_pools.items())
                for _key, (adapter, _ref) in pools_snapshot:
                    # Scope: only read pools matching this DataFlow's database
                    if db_url and db_url not in _key:
                        continue

                    pool = getattr(adapter, "connection_pool", None) or getattr(
                        adapter, "_pool", None
                    )
                    if pool is None:
                        continue

                    # asyncpg pool (PostgreSQL)
                    if hasattr(pool, "get_size") and hasattr(pool, "get_idle_size"):
                        total = pool.get_size()
                        idle = pool.get_idle_size()
                        return pool_stats_dict(
                            active=total - idle,
                            idle=idle,
                            max_size=pool_size,
                            overflow=max(0, total - pool_size),
                            max_overflow=max_overflow,
                        )

                    # SQLAlchemy QueuePool
                    if hasattr(pool, "checkedout") and hasattr(pool, "checkedin"):
                        return pool_stats_dict(
                            active=pool.checkedout(),
                            idle=pool.checkedin(),
                            max_size=pool.size(),
                            overflow=pool.overflow(),
                            max_overflow=getattr(pool, "_max_overflow", max_overflow),
                        )

                    # SQLite adapter with _pool_stats attribute
                    pool_stats_attr = getattr(adapter, "_pool_stats", None)
                    if pool_stats_attr is not None:
                        return pool_stats_dict(
                            active=getattr(pool_stats_attr, "active_connections", 0),
                            idle=getattr(pool_stats_attr, "idle_connections", 0),
                            max_size=pool_size,
                            max_overflow=max_overflow,
                        )
            except Exception:
                pass

            # No pool found yet or error — return configured sizes with zero activity
            return pool_stats_dict(max_size=pool_size, max_overflow=max_overflow)

        return _provider

    def pool_stats(self) -> Dict[str, Any]:
        """Return real-time pool utilization stats.

        Returns:
            Dict with keys: active, idle, max, overflow, max_overflow, utilization.
            Returns zeros when pool monitor is not running.
        """
        if self._pool_monitor is not None:
            return self._pool_monitor.get_stats()
        from dataflow.core.pool_monitor import pool_stats_dict

        return pool_stats_dict()

    async def execute_raw_lightweight(self, sql: str) -> Any:
        """Execute a health check / diagnostic query on the lightweight pool.

        The lightweight pool is a separate 2-connection mini-pool that does not
        compete with the main application pool. Use this for health checks,
        readiness probes, and diagnostic queries only.

        Args:
            sql: SQL query (must match the lightweight pool's allowlist).

        Returns:
            Query result.

        Raises:
            RuntimeError: If lightweight pool is not configured.
            ValueError: If the SQL query is not in the allowlist.
        """
        self._ensure_connected()
        if self._lightweight_pool is None:
            raise RuntimeError(
                "Lightweight pool not configured. "
                "Ensure enable_connection_pooling=True and a valid database_url is set."
            )
        if not self._lightweight_pool.is_initialized:
            await self._lightweight_pool.initialize()
        return await self._lightweight_pool.execute_raw(sql)

    def close(self):
        """Close database connections and clean up resources (sync version).

        For async contexts (FastAPI, pytest async fixtures), use close_async() instead.

        This method safely closes:
        - Model registry (releases shared runtime reference)
        - Pool monitor thread
        - Connection pool manager pools
        - Connection manager connections
        - Persistent :memory: connections
        - Shared runtime (actual cleanup at ref_count=0)
        """
        import asyncio

        if self._closed:
            return
        self._closed = True

        # M2-001: Release subsystem references to shared runtime FIRST.
        # Each subsystem calls close() which calls release() on their runtime.
        if hasattr(self, "_model_registry") and self._model_registry is not None:
            try:
                self._model_registry.close()
            except Exception as e:
                logger.debug(f"Error closing model registry: {e}")

        if hasattr(self, "_migration_system") and self._migration_system is not None:
            try:
                if hasattr(self._migration_system, "close"):
                    self._migration_system.close()
            except Exception as e:
                logger.debug(f"Error closing migration system: {e}")

        # Stop pool monitor
        if self._pool_monitor is not None:
            try:
                self._pool_monitor.stop()
            except Exception:
                pass
            self._pool_monitor = None

        # Close lightweight pool
        if hasattr(self, "_lightweight_pool") and self._lightweight_pool is not None:
            try:
                async_safe_run(self._lightweight_pool.close())
            except Exception:
                pass
            self._lightweight_pool = None

        # Clean up connection manager
        if hasattr(self, "_connection_manager") and self._connection_manager:
            try:
                if hasattr(self._connection_manager, "close_all_connections"):
                    self._connection_manager.close_all_connections()
            except Exception as e:
                logger.debug(f"Error closing connection manager: {e}")

        # Clean up persistent :memory: connection
        # Phase 6: Use async_safe_run for proper cleanup in both sync and async contexts
        if hasattr(self, "_memory_connection") and self._memory_connection:
            try:
                async_safe_run(self._memory_connection.close())
            except Exception as e:
                logger.debug(f"Failed to close memory connection: {e}")
            finally:
                self._memory_connection = None

        # M2-001: Close the shared runtime LAST (actual cleanup at ref_count=0)
        if hasattr(self, "runtime") and self.runtime is not None:
            try:
                self.runtime.close()
            except Exception as e:
                logger.debug(f"Error closing shared runtime: {e}")
            finally:
                self.runtime = None

    async def close_async(self):
        """Close database connections and clean up resources (async version).

        Use this method in async contexts (FastAPI lifespan, pytest async fixtures).

        Example:
            @asynccontextmanager
            async def lifespan(app: FastAPI):
                db = DataFlow("postgresql://...")
                await db.initialize()
                yield
                await db.close_async()  # Proper async cleanup

        This method safely closes:
        - Model registry (releases shared runtime reference)
        - Cached AsyncSQLDatabaseNode instances (awaited)
        - Connection manager connections
        - Persistent :memory: connections (awaited)
        - Shared runtime (actual cleanup at ref_count=0)
        """
        if self._closed:
            return
        self._closed = True

        # M2-001: Release subsystem references to shared runtime FIRST.
        if hasattr(self, "_model_registry") and self._model_registry is not None:
            try:
                self._model_registry.close()
            except Exception as e:
                logger.debug(f"Error releasing model registry runtime: {e}")

        # Stop pool monitor (same cleanup as sync close())
        if self._pool_monitor is not None:
            try:
                self._pool_monitor.stop()
            except Exception:
                pass
            self._pool_monitor = None

        # Close lightweight pool
        if hasattr(self, "_lightweight_pool") and self._lightweight_pool is not None:
            try:
                await self._lightweight_pool.close()
            except Exception:
                pass
            self._lightweight_pool = None

        # Clean up cached AsyncSQLDatabaseNode instances (Express API uses these)
        if hasattr(self, "_async_sql_node_cache") and self._async_sql_node_cache:
            for db_type, (node, _) in list(self._async_sql_node_cache.items()):
                try:
                    if hasattr(node, "close") and callable(node.close):
                        await node.close()
                except Exception as e:
                    logger.debug(f"Error closing cached SQL node for {db_type}: {e}")
            self._async_sql_node_cache.clear()

        # Clean up connection manager
        if hasattr(self, "_connection_manager") and self._connection_manager:
            try:
                if hasattr(self._connection_manager, "close_all_connections"):
                    self._connection_manager.close_all_connections()
            except Exception as e:
                logger.debug(f"Error closing connection manager: {e}")

        # Clean up persistent :memory: connection
        if hasattr(self, "_memory_connection") and self._memory_connection:
            try:
                await self._memory_connection.close()
            except Exception as e:
                logger.debug(f"Failed to close memory connection: {e}")
            finally:
                self._memory_connection = None

        # M2-001: Close the shared runtime LAST (actual cleanup at ref_count=0)
        if hasattr(self, "runtime") and self.runtime is not None:
            try:
                self.runtime.close()
            except Exception as e:
                logger.debug(f"Error closing shared runtime: {e}")
            finally:
                self.runtime = None

        logger.debug(f"DataFlow instance {self._instance_id} closed (async)")

    def get_node(self, node_name: str) -> Optional[Type]:
        """Get a generated node class by name.

        Args:
            node_name: Name of the node to retrieve (e.g., 'UserCreateNode')

        Returns:
            Node class if found, None otherwise
        """
        try:
            if hasattr(self, "_nodes") and node_name in self._nodes:
                return self._nodes[node_name]

            # Also check node generator if available
            if hasattr(self, "_node_generator") and self._node_generator:
                return getattr(self._node_generator, node_name, None)

            logger.warning(f"Node '{node_name}' not found in DataFlow instance")
            return None

        except Exception as e:
            logger.error(f"Error retrieving node '{node_name}': {e}")
            return None

    def _is_valid_database_url(self, url: str) -> bool:
        """Validate database URL format.

        Supports PostgreSQL, MySQL, SQLite, and MongoDB connection strings.
        """
        if not url or not isinstance(url, str):
            return False

        # Allow SQLite memory database for testing only
        if url == ":memory:":
            logger.warning(
                "Using SQLite :memory: database for testing. Production requires PostgreSQL."
            )
            # Show detailed async limitation warning if in async context
            warn_sqlite_async_limitation(url)
            return True

        # Supported database schemes (11 variants for 4 database types)
        supported_schemes = [
            # PostgreSQL (3 variants)
            "postgresql",
            "postgres",
            "postgresql+asyncpg",
            # MySQL (4 variants)
            "mysql",
            "mysql+pymysql",
            "mysql+mysqldb",
            "mysql+aiomysql",
            # SQLite (2 variants)
            "sqlite",
            "sqlite+aiosqlite",
            # MongoDB (2 variants)
            "mongodb",
            "mongodb+srv",
        ]

        try:
            # Handle URLs without schemes (likely SQLite file paths)
            if "://" not in url:
                # Assume it's a SQLite file path
                if (
                    url.endswith(".db")
                    or url.endswith(".sqlite")
                    or url.endswith(".sqlite3")
                    or url.startswith("./")
                    or url.startswith("../")
                    or url.startswith("/")
                ):
                    return True
                else:
                    # Enhanced error with catalog-based solutions (DF-401)
                    if ErrorEnhancer is not None:
                        raise ErrorEnhancer.enhance_invalid_database_url(
                            database_url=url,
                            error_message="Invalid database URL. For file databases, use .db, .sqlite, or .sqlite3 extensions or provide a full URL like sqlite:///path/to/db.sqlite",
                        )
                    return False

            scheme = url.split("://")[0].lower()
            if scheme not in supported_schemes:
                # Enhanced error with catalog-based solutions (DF-401)
                if ErrorEnhancer is not None:
                    raise ErrorEnhancer.enhance_invalid_database_url(
                        database_url=url,
                        error_message=f"Unsupported database scheme '{scheme}'. DataFlow supports PostgreSQL, MySQL, SQLite, and MongoDB. Use URLs like: postgresql://user:pass@localhost/db, mysql://user:pass@localhost/db, sqlite:///path/to/db.sqlite, or mongodb://localhost:27017/db",
                    )
                return False

            # Normalize scheme for validation (remove dialect suffix)
            base_scheme = scheme.split("+")[0]

            # Database-specific URL validation
            if base_scheme in ["postgresql", "postgres"]:
                # PostgreSQL URL validation
                if "@" not in url or "/" not in url.split("@")[1]:
                    # Enhanced error with catalog-based solutions (DF-401)
                    if ErrorEnhancer is not None:
                        raise ErrorEnhancer.enhance_invalid_database_url(
                            database_url=url,
                            error_message="Invalid PostgreSQL URL format. Expected: postgresql://user:pass@host:port/database",
                        )
                    return False
            elif base_scheme == "mysql":
                # MySQL URL validation
                if "@" not in url or "/" not in url.split("@")[1]:
                    # Enhanced error with catalog-based solutions (DF-401)
                    if ErrorEnhancer is not None:
                        raise ErrorEnhancer.enhance_invalid_database_url(
                            database_url=url,
                            error_message="Invalid MySQL URL format. Expected: mysql://user:pass@host:port/database",
                        )
                    return False
            elif base_scheme == "sqlite":
                # SQLite URL validation - flexible for file paths
                return True
            elif base_scheme == "mongodb":
                # MongoDB URL validation - flexible for connection strings
                # MongoDB URIs can be: mongodb://host:port/db or mongodb+srv://cluster/db
                return True

            return True
        except ValueError:
            # Re-raise validation errors with clear message
            raise
        except Exception as e:
            logger.error(f"Database URL validation failed: {e}")
            return False

    # ADR-001: Schema cache management methods

    def clear_schema_cache(self) -> None:
        """Clear all cached table existence entries.

        Useful when external schema changes are made or for testing.

        Example:
            >>> db.clear_schema_cache()
            >>> # All tables will be re-validated on next access
        """
        self._schema_cache.clear()
        logger.debug("Schema cache cleared")

    def clear_table_cache(
        self, model_name: str, database_url: Optional[str] = None
    ) -> bool:
        """Clear specific table from schema cache.

        Useful when external schema changes are made to a specific table.

        Args:
            model_name: Name of the model to clear from cache
            database_url: Optional database URL (defaults to config.database.url)

        Returns:
            True if entry was removed, False if not found

        Example:
            >>> db.clear_table_cache("User")
            >>> # User table will be re-validated on next access
            >>> db.clear_table_cache("User", ":memory:")
            >>> # Clear from specific database
        """
        if database_url is None:
            database_url = self.config.database.url or ":memory:"
        return self._schema_cache.clear_table(model_name, database_url)

    def clear_async_sql_node_cache(self) -> None:
        """Clear the cached AsyncSQLDatabaseNode instances.

        This is useful for testing scenarios where pytest-asyncio creates new event
        loops between tests, causing stale asyncpg connection pools. Calling this
        method forces new nodes to be created with fresh connection pools.

        Note: The event loop tracking mechanism (v0.10.6+) automatically detects
        event loop changes and recreates nodes, so this method is primarily for
        explicit cleanup or debugging purposes.

        Example:
            >>> db.clear_async_sql_node_cache()
            >>> # Next CRUD operation will create a new AsyncSQLDatabaseNode

        See Also:
            - _get_or_create_async_sql_node() for event loop tracking details
        """
        self._async_sql_node_cache.clear()
        logger.debug("AsyncSQLDatabaseNode cache cleared")

    def get_schema_cache_metrics(self) -> Dict[str, Any]:
        """Get schema cache performance metrics.

        Returns:
            Dict with cache statistics (hits, misses, size, etc.)

        Example:
            >>> metrics = db.get_schema_cache_metrics()
            >>> print(f"Cache hit rate: {metrics['hit_rate_percent']}%")
            >>> print(f"Cached tables: {metrics['cache_size']}")
        """
        return self._schema_cache.get_metrics()

    def get_cached_tables(self) -> Dict[str, Dict[str, Any]]:
        """Get all currently cached tables with their states.

        Returns:
            Dict mapping cache keys to table metadata

        Example:
            >>> cached = db.get_cached_tables()
            >>> for key, info in cached.items():
            ...     print(f"{info['model_name']}: {info['state']}")
        """
        return self._schema_cache.get_cached_tables()

    def _calculate_schema_checksum(self, fields: Dict[str, Any]) -> str:
        """Calculate checksum for model schema.

        Used for schema validation to detect schema changes.

        Args:
            fields: Model field definitions

        Returns:
            SHA256 checksum of schema
        """
        import hashlib
        import json

        # Create deterministic string representation
        schema_str = json.dumps(fields, sort_keys=True)
        return hashlib.sha256(schema_str.encode()).hexdigest()

    # NOTE: Context manager (__enter__/__exit__) is defined earlier at lines 1767-1866
    # DO NOT add duplicate definitions here - Python uses the LAST definition

    # ---- Workflow Binding Integration ----

    def create_workflow(self, workflow_id: str = None) -> "WorkflowBuilder":
        """Create a workflow bound to this DataFlow instance.

        Creates a WorkflowBuilder that can be used with add_node() and
        execute_workflow() for composing multi-step DataFlow operations.

        Args:
            workflow_id: Optional identifier for the workflow

        Returns:
            WorkflowBuilder instance

        Example:
            db = DataFlow("postgresql://...")

            @db.model
            class User:
                name: str
                email: str

            workflow = db.create_workflow("user_setup")
            db.add_node(workflow, "User", "Create", "create_user", {
                "name": "Alice",
                "email": "alice@example.com"
            })
            results, run_id = db.execute_workflow(workflow)
        """
        return self._workflow_binder.create_workflow(workflow_id)

    def add_node(
        self,
        workflow: "WorkflowBuilder",
        model_name: str,
        operation: str,
        node_id: str,
        params: Dict[str, Any],
        connections: Optional[Dict] = None,
    ) -> str:
        """Add a model node to a DataFlow workflow.

        Validates the model and operation, then adds the corresponding
        auto-generated node to the workflow.

        Args:
            workflow: WorkflowBuilder from create_workflow()
            model_name: Registered model name (e.g., "User")
            operation: Operation name (e.g., "Create", "Read", "Update",
                      "Delete", "List", "Upsert", "Count",
                      "BulkCreate", "BulkUpdate", "BulkDelete", "BulkUpsert")
            node_id: Unique node ID within the workflow
            params: Node parameters
            connections: Optional connections to other nodes

        Returns:
            The node_id

        Example:
            db.add_node(workflow, "User", "Create", "create_user", {
                "name": "Alice",
                "email": "alice@example.com"
            })
        """
        return self._workflow_binder.add_model_node(
            workflow, model_name, operation, node_id, params, connections
        )

    def execute_workflow(
        self,
        workflow: "WorkflowBuilder",
        inputs: Optional[Dict[str, Any]] = None,
        runtime=None,
    ):
        """Execute a DataFlow-bound workflow.

        Args:
            workflow: Workflow from create_workflow()
            inputs: Optional input parameters
            runtime: Optional runtime (creates LocalRuntime if not provided)

        Returns:
            Tuple of (results_dict, run_id)

        Note:
            This triggers lazy database connection if not already connected (Issue #171).

        Example:
            results, run_id = db.execute_workflow(workflow, {
                "user_id": "user-123"
            })
        """
        self._ensure_connected()
        return self._workflow_binder.execute(workflow, inputs, runtime)

    def get_available_nodes(self, model_name: str = None) -> Dict[str, list]:
        """Get available DataFlow nodes for workflow composition.

        Args:
            model_name: Optional model name to filter by

        Returns:
            Dict mapping model names to lists of available operations

        Example:
            >>> nodes = db.get_available_nodes()
            >>> # {'User': ['Create', 'Read', 'Update', 'Delete', ...]}
        """
        return self._workflow_binder.get_available_nodes(model_name)
