"""
ErrorEnhancer: Transparent middleware for enhancing DataFlow exceptions

Catches standard Python exceptions and enriches them with:
- Error codes (DF-XXX)
- Contextual information
- Possible causes
- Actionable solutions with code examples
- Documentation links

Performance Optimization (Phase 1C):
- Three performance modes: FULL, MINIMAL, DISABLED
- LRU pattern caching for 90%+ hit rate
- Thread-safe concurrent access
- <5ms FULL, <1ms MINIMAL, <0.1ms DISABLED

Usage:
    from dataflow.core.config import ErrorEnhancerConfig, PerformanceMode

    # Default FULL mode
    enhancer = ErrorEnhancer()

    # Minimal mode for production
    config = ErrorEnhancerConfig(mode=PerformanceMode.MINIMAL, cache_size=200)
    enhancer = ErrorEnhancer(config=config)

    try:
        # DataFlow operation
    except KeyError as e:
        enhanced = enhancer.enhance_parameter_error(
            node_id="user_create",
            parameter_name="data",
            original_error=e
        )
        raise enhanced from e
"""

import re
import threading
import traceback
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from dataflow.exceptions import EnhancedDataFlowError, ErrorSolution


class ErrorEnhancer:
    """Enhances standard Python exceptions into EnhancedDataFlowError instances.

    Performance-optimized with three modes:
    - FULL: Complete enhancement with all context and solutions
    - MINIMAL: Essential context and top solution only
    - DISABLED: Passthrough with minimal wrapper

    Thread-safe pattern caching for 90%+ hit rate on repeated errors.
    """

    BASE_DOCS_URL = "https://docs.kailash.ai/dataflow/errors"
    _ERROR_CATALOG: Optional[Dict] = None  # Lazy-loaded catalog

    def __init__(self, config: Optional["ErrorEnhancerConfig"] = None):
        """Initialize ErrorEnhancer with performance configuration.

        Args:
            config: ErrorEnhancerConfig instance (defaults to FULL mode with cache_size=100)
        """
        # Import here to avoid circular dependency
        from dataflow.core.config import ErrorEnhancerConfig, PerformanceMode

        self.config = config or ErrorEnhancerConfig()

        # Pattern cache with LRU eviction (thread-safe via functools.lru_cache)
        self._pattern_cache = lru_cache(maxsize=self.config.cache_size)(
            self._compile_pattern_cached
        )

        # Cache statistics (thread-safe with lock)
        self._cache_lock = threading.Lock()
        self._cache_hits = 0
        self._cache_misses = 0
        self._cache_evictions = 0

    @classmethod
    def _load_error_catalog(cls) -> Dict:
        """
        Load error catalog from YAML file.

        Returns:
            Dictionary with error code -> error definition mappings

        Note:
            Catalog is loaded once and cached for performance.
            To reload catalog, set cls._ERROR_CATALOG = None
        """
        if cls._ERROR_CATALOG is None:
            catalog_path = Path(__file__).parent / "error_catalog.yaml"

            if not catalog_path.exists():
                # Fallback to minimal catalog if file missing
                cls._ERROR_CATALOG = {}
                return cls._ERROR_CATALOG

            try:
                with open(catalog_path, "r") as f:
                    cls._ERROR_CATALOG = yaml.safe_load(f) or {}
            except Exception:
                cls._ERROR_CATALOG = {}

        return cls._ERROR_CATALOG

    @classmethod
    def _get_error_definition(cls, error_code: str) -> Optional[Dict]:
        """
        Get error definition from catalog.

        Args:
            error_code: Error code (e.g., "DF-101")

        Returns:
            Error definition dict or None if not found
        """
        catalog = cls._load_error_catalog()
        return catalog.get(error_code, None)

    @classmethod
    def _extract_context_from_exception(cls, exc: Exception) -> Dict[str, Any]:
        """
        Extract contextual information from exception and stack trace.

        Args:
            exc: Original exception

        Returns:
            Dictionary with extracted context

        Example:
            >>> try:
            ...     raise KeyError("data")
            ... except KeyError as e:
            ...     context = cls._extract_context_from_exception(e)
            >>> context['exception_type']
            'KeyError'
        """
        context = {
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
        }

        # Extract stack trace info
        tb_list = traceback.extract_tb(exc.__traceback__)
        if tb_list:
            last_frame = tb_list[-1]
            context["file"] = last_frame.filename
            context["line"] = last_frame.lineno
            context["function"] = last_frame.name

        return context

    def _compile_pattern_cached(self, pattern: str) -> re.Pattern:
        """Compile regex pattern (cached via LRU).

        Args:
            pattern: Regex pattern string

        Returns:
            Compiled regex pattern
        """
        return re.compile(pattern, re.IGNORECASE)

    def get_cache_hit_rate(self) -> float:
        """Get cache hit rate for performance monitoring.

        Returns:
            Hit rate as float (0.0 to 1.0)
        """
        with self._cache_lock:
            total = self._cache_hits + self._cache_misses
            return self._cache_hits / total if total > 0 else 0.0

    def get_cache_info(self) -> Dict[str, int]:
        """Get cache statistics.

        Returns:
            Dictionary with cache size, hits, misses, evictions
        """
        cache_info = self._pattern_cache.cache_info()
        with self._cache_lock:
            return {
                "size": cache_info.currsize,
                "hits": self._cache_hits,
                "misses": self._cache_misses,
                "evictions": self._cache_evictions,
                "maxsize": cache_info.maxsize,
            }

    def set_performance_mode(self, mode: "PerformanceMode"):
        """Switch performance mode at runtime.

        Args:
            mode: New PerformanceMode
        """
        from dataflow.core.config import PerformanceMode

        self.config.mode = mode

    def find_error_definition(self, exception: Exception) -> Optional[Dict]:
        """
        Find error definition by matching exception to catalog patterns.

        Uses LRU cache for pattern compilation to achieve 90%+ hit rate.

        Args:
            exception: The exception to match

        Returns:
            Error definition dict with 'code' key, or None if no match

        Example:
            >>> exc = KeyError("Parameter 'data' is missing")
            >>> error_def = enhancer.find_error_definition(exc)
            >>> error_def['code']
            'DF-101'
        """
        catalog = self._load_error_catalog()
        exception_str = f"{type(exception).__name__}: {str(exception)}"

        # Track cache statistics (before any pattern operations)
        cache_info_before = self._pattern_cache.cache_info()
        prev_size = cache_info_before.currsize

        for error_code, error_def in catalog.items():
            pattern = error_def.get("pattern", "")
            if pattern:
                # Use cached pattern compilation
                compiled_pattern = self._pattern_cache(pattern)
                if compiled_pattern.search(exception_str):
                    # Update cache stats after operation
                    cache_info_after = self._pattern_cache.cache_info()
                    with self._cache_lock:
                        # Track hits/misses based on cache_info changes
                        if cache_info_after.hits > cache_info_before.hits:
                            self._cache_hits += 1
                        else:
                            self._cache_misses += 1

                        # Detect evictions (size decreased unexpectedly)
                        # This happens when cache is full and new item added
                        if (
                            prev_size >= self.config.cache_size
                            and cache_info_after.currsize <= prev_size
                        ):
                            # Check if we added a new item but size stayed same/decreased
                            if cache_info_after.misses > cache_info_before.misses:
                                self._cache_evictions += 1

                    return {**error_def, "code": error_code}

        return None

    def enhance_parameter_error(
        self,
        node_id: str,
        node_type: Optional[str] = None,
        parameter_name: Optional[str] = None,
        expected_type: Optional[str] = None,
        received_value: Any = None,
        original_error: Optional[Exception] = None,
    ) -> EnhancedDataFlowError:
        """
        Enhance parameter-related errors with performance mode support.

        Performance modes:
        - FULL: All context, multiple causes, multiple solutions
        - MINIMAL: Essential context, top cause, top solution
        - DISABLED: Passthrough with generic wrapper

        Args:
            node_id: ID of the node with error
            node_type: Type of node (e.g., "UserCreateNode")
            parameter_name: Name of the missing/invalid parameter
            expected_type: Expected parameter type
            received_value: Actual value received
            original_error: Original exception

        Returns:
            EnhancedDataFlowError with context and solutions

        Example:
            >>> enhanced = enhancer.enhance_parameter_error(
            ...     node_id="user_create",
            ...     node_type="UserCreateNode",
            ...     parameter_name="data",
            ...     expected_type="dict",
            ...     received_value=None,
            ...     original_error=KeyError("data")
            ... )
        """
        from dataflow.core.config import PerformanceMode

        # DISABLED mode: Fast passthrough with minimal wrapper
        if self.config.mode == PerformanceMode.DISABLED:
            return EnhancedDataFlowError(
                error_code="DF-999",  # Generic passthrough code
                message=str(original_error) if original_error else "Error occurred",
                context={"node_id": node_id},
                causes=[],
                solutions=[],
                original_error=original_error,
            )
        # Determine error code based on error type
        error_code = "DF-101"  # Missing parameter by default

        if original_error:
            if isinstance(original_error, TypeError):
                error_code = "DF-102"  # Type mismatch
            elif "created_at" in str(original_error) or "updated_at" in str(
                original_error
            ):
                error_code = "DF-104"  # Auto-managed field
            elif (
                "id" in str(original_error) and "primary" in str(original_error).lower()
            ):
                error_code = "DF-105"  # Missing primary key

        # Get error definition from catalog
        error_def = self._get_error_definition(error_code)

        if not error_def:
            # Fallback error
            return EnhancedDataFlowError(
                error_code=error_code,
                message=f"Parameter error in node '{node_id}'",
                context={
                    "node_id": node_id,
                    "node_type": node_type or "Unknown",
                    "parameter": parameter_name or "Unknown",
                },
                original_error=original_error,
            )

        # Build context (mode-dependent)
        context = {
            "node_id": node_id,
        }

        # FULL mode: include all context
        if self.config.mode == PerformanceMode.FULL:
            context["node_type"] = node_type or "Unknown"

            if parameter_name:
                context["parameter"] = parameter_name
            if expected_type:
                context["expected_type"] = expected_type
            if received_value is not None:
                context["received_type"] = type(received_value).__name__
                context["received_value"] = str(received_value)[:100]  # Limit length
        # MINIMAL mode: essential context only
        elif self.config.mode == PerformanceMode.MINIMAL:
            if parameter_name:
                context["parameter"] = parameter_name
            if node_type:
                context["node_type"] = node_type

        # Extract causes from catalog (mode-dependent)
        causes = []
        if error_def.get("contexts"):
            first_context = error_def["contexts"][0]
            all_causes = first_context.get("causes", [])
            # MINIMAL mode: only first cause
            if self.config.mode == PerformanceMode.MINIMAL:
                causes = all_causes[:1] if all_causes else []
            else:  # FULL mode: all causes
                causes = all_causes

        # Extract solutions from catalog (mode-dependent)
        solutions = []
        if error_def.get("contexts"):
            first_context = error_def["contexts"][0]
            all_solutions = first_context.get("solutions", [])

            # MINIMAL mode: only top solution
            if self.config.mode == PerformanceMode.MINIMAL:
                solutions_to_process = all_solutions[:1]
            else:  # FULL mode: all solutions
                solutions_to_process = all_solutions

            for sol_def in solutions_to_process:
                solution = ErrorSolution(
                    priority=1,
                    description=sol_def.get("description", ""),
                    code_template=sol_def.get("code_template", ""),
                    auto_fixable=sol_def.get("auto_fixable", False),
                )
                solutions.append(solution)

        # Build message
        message = error_def.get("name", "Parameter Error")
        if parameter_name:
            message = f"{message}: '{parameter_name}'"
        if node_id:
            message = f"{message} in node '{node_id}'"

        # Build docs URL
        docs_url = f"{self.BASE_DOCS_URL}/{error_code.lower()}"

        return EnhancedDataFlowError(
            error_code=error_code,
            message=message,
            context=context,
            causes=causes,
            solutions=solutions,
            docs_url=docs_url,
            original_error=original_error,
        )

    def enhance_connection_error(
        self,
        source_node: str,
        target_node: str,
        source_param: Optional[str] = None,
        target_param: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> EnhancedDataFlowError:
        """
        Enhance connection-related errors.

        Args:
            source_node: Source node ID
            target_node: Target node ID
            source_param: Source parameter name
            target_param: Target parameter name
            original_error: Original exception

        Returns:
            EnhancedDataFlowError with connection-specific context

        Example:
            >>> enhanced = enhancer.enhance_connection_error(
            ...     source_node="input",
            ...     target_node="user_create",
            ...     source_param="user_data",
            ...     target_param="data"
            ... )
        """
        # Determine error code
        error_code = "DF-201"  # Invalid connection by default

        if original_error and "output" in str(original_error).lower():
            error_code = "DF-202"  # Missing source output

        # Get error definition
        error_def = self._get_error_definition(error_code)

        context = {
            "source_node": source_node,
            "target_node": target_node,
        }

        if source_param:
            context["source_param"] = source_param
        if target_param:
            context["target_param"] = target_param

        # Extract causes and solutions
        causes = []
        solutions = []

        if error_def and error_def.get("contexts"):
            first_context = error_def["contexts"][0]
            causes = first_context.get("causes", [])

            for sol_def in first_context.get("solutions", []):
                solution = ErrorSolution(
                    priority=1,
                    description=sol_def.get("description", ""),
                    code_template=sol_def.get("code_template", ""),
                    auto_fixable=sol_def.get("auto_fixable", False),
                )
                solutions.append(solution)

        message = f"Invalid connection from '{source_node}' to '{target_node}'"

        return EnhancedDataFlowError(
            error_code=error_code,
            message=message,
            context=context,
            causes=causes,
            solutions=solutions,
            docs_url=f"{self.BASE_DOCS_URL}/{error_code.lower()}",
            original_error=original_error,
        )

    def enhance_migration_error(
        self,
        model_name: str,
        operation: Optional[str] = None,
        details: Optional[Dict] = None,
        original_error: Optional[Exception] = None,
    ) -> EnhancedDataFlowError:
        """
        Enhance migration-related errors.

        Args:
            model_name: Name of the model
            operation: Migration operation (e.g., "create_table")
            details: Additional details about the error
            original_error: Original exception

        Returns:
            EnhancedDataFlowError with migration-specific context

        Example:
            >>> enhanced = enhancer.enhance_migration_error(
            ...     model_name="User",
            ...     operation="create_table",
            ...     original_error=Exception("Table creation failed")
            ... )
        """
        # Determine error code
        error_code = "DF-301"  # Migration failure by default

        if original_error:
            error_str = str(original_error).lower()
            if "schema" in error_str or "mismatch" in error_str:
                error_code = "DF-302"  # Schema mismatch
            elif "column" in error_str and "type" in error_str:
                error_code = "DF-303"  # Column type mismatch

        # Get error definition
        error_def = self._get_error_definition(error_code)

        context = {"model_name": model_name}

        if operation:
            context["operation"] = operation
        if details:
            context.update(details)

        # Extract causes and solutions
        causes = []
        solutions = []

        if error_def and error_def.get("contexts"):
            first_context = error_def["contexts"][0]
            causes = first_context.get("causes", [])

            for sol_def in first_context.get("solutions", []):
                solution = ErrorSolution(
                    priority=1,
                    description=sol_def.get("description", ""),
                    code_template=sol_def.get("code_template", ""),
                    auto_fixable=sol_def.get("auto_fixable", False),
                )
                solutions.append(solution)

        message = f"Migration failed for model '{model_name}'"
        if operation:
            message = f"{message} during operation '{operation}'"

        return EnhancedDataFlowError(
            error_code=error_code,
            message=message,
            context=context,
            causes=causes,
            solutions=solutions,
            docs_url=f"{self.BASE_DOCS_URL}/{error_code.lower()}",
            original_error=original_error,
        )

    def enhance_runtime_error(
        self,
        node_id: Optional[str] = None,
        node_type: Optional[str] = None,
        workflow_id: Optional[str] = None,
        operation: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> EnhancedDataFlowError:
        """
        Enhance runtime execution errors.

        Args:
            node_id: Node ID where error occurred
            node_type: Type of node
            workflow_id: Workflow ID
            operation: Operation being performed
            original_error: Original exception

        Returns:
            EnhancedDataFlowError with runtime-specific context

        Example:
            >>> enhanced = enhancer.enhance_runtime_error(
            ...     node_id="user_create",
            ...     node_type="UserCreateNode",
            ...     operation="execute",
            ...     original_error=RuntimeError("Database connection failed")
            ... )
        """
        # Determine error code
        error_code = "DF-501"  # Runtime execution error by default

        if original_error:
            error_str = str(original_error).lower()
            if "database" in error_str:
                error_code = "DF-502"  # Database operation failed
            elif "workflow" in error_str:
                error_code = "DF-503"  # Workflow execution failed

        # Get error definition
        error_def = self._get_error_definition(error_code)

        context = {}

        if node_id:
            context["node_id"] = node_id
        if node_type:
            context["node_type"] = node_type
        if workflow_id:
            context["workflow_id"] = workflow_id
        if operation:
            context["operation"] = operation

        # Extract causes and solutions
        causes = []
        solutions = []

        if error_def and error_def.get("contexts"):
            first_context = error_def["contexts"][0]
            causes = first_context.get("causes", [])

            for sol_def in first_context.get("solutions", []):
                solution = ErrorSolution(
                    priority=1,
                    description=sol_def.get("description", ""),
                    code_template=sol_def.get("code_template", ""),
                    auto_fixable=sol_def.get("auto_fixable", False),
                )
                solutions.append(solution)

        if node_id:
            message = f"Runtime error in node '{node_id}'"
        elif workflow_id:
            message = f"Runtime error in workflow '{workflow_id}'"
        else:
            message = "Runtime execution error"

        return EnhancedDataFlowError(
            error_code=error_code,
            message=message,
            context=context,
            causes=causes,
            solutions=solutions,
            docs_url=f"{self.BASE_DOCS_URL}/{error_code.lower()}",
            original_error=original_error,
        )

    def enhance_generic_error(
        self, exception: Exception, **context_kwargs
    ) -> Optional[EnhancedDataFlowError]:
        """
        Try to enhance any exception by matching patterns.

        Args:
            exception: Exception to enhance
            **context_kwargs: Additional context to include

        Returns:
            EnhancedDataFlowError if pattern matched, None otherwise

        Example:
            >>> try:
            ...     raise KeyError("data")
            ... except Exception as e:
            ...     enhanced = enhancer.enhance_generic_error(e)
        """
        error_def = self.find_error_definition(exception)

        if not error_def:
            return None

        error_code = error_def["code"]

        # Build context
        context = self._extract_context_from_exception(exception)
        context.update(context_kwargs)

        # Extract causes and solutions
        causes = []
        solutions = []

        if error_def.get("contexts"):
            first_context = error_def["contexts"][0]
            causes = first_context.get("causes", [])

            for sol_def in first_context.get("solutions", []):
                solution = ErrorSolution(
                    priority=1,
                    description=sol_def.get("description", ""),
                    code_template=sol_def.get("code_template", ""),
                    auto_fixable=sol_def.get("auto_fixable", False),
                )
                solutions.append(solution)

        message = error_def.get("name", str(exception))

        return EnhancedDataFlowError(
            error_code=error_code,
            message=message,
            context=context,
            causes=causes,
            solutions=solutions,
            docs_url=f"{self.BASE_DOCS_URL}/{error_code.lower()}",
            original_error=exception,
        )

    # ========================================================================
    # Auto-Fix Methods
    # ========================================================================

    def auto_fix_wrap_in_dict(self, parameter_name: str, value: Any) -> Dict:
        """
        Auto-fix type mismatch by wrapping value in dict.

        Args:
            parameter_name: Name of the parameter
            value: Value to wrap

        Returns:
            Dictionary with parameter_name as key

        Example:
            >>> enhancer.auto_fix_wrap_in_dict("data", "Alice")
            {'data': 'Alice'}
        """
        return {parameter_name: value}

    def auto_fix_remove_auto_managed_fields(self, data: Dict) -> Dict:
        """
        Auto-fix by removing auto-managed fields.

        Args:
            data: Data dictionary

        Returns:
            Data dictionary without auto-managed fields

        Example:
            >>> data = {"name": "Alice", "created_at": datetime.now()}
            >>> enhancer.auto_fix_remove_auto_managed_fields(data)
            {'name': 'Alice'}
        """
        auto_managed_fields = ["created_at", "updated_at"]
        return {k: v for k, v in data.items() if k not in auto_managed_fields}
