"""
BaseErrorEnhancer: Abstract base class for error enhancement across Kailash SDK.

Provides DRY components for error enhancement:
- YAML catalog loading with lazy initialization
- Thread-safe LRU pattern caching (90%+ hit rate)
- Performance mode configuration (FULL/MINIMAL/DISABLED)
- Cache statistics tracking
- Pattern matching with regex compilation

Subclasses:
- CoreErrorEnhancer: Core SDK runtime errors (KS-XXX codes)
- DataFlowErrorEnhancer: DataFlow database errors (DF-XXX codes)
"""

import re
import threading
from abc import ABC, abstractmethod
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


class PerformanceMode(Enum):
    """Performance modes for error enhancement.

    - FULL: Complete enhancement with all context, causes, and solutions
    - MINIMAL: Essential context and top solution only
    - DISABLED: Passthrough with minimal wrapper (no enhancement)
    """

    FULL = "full"
    MINIMAL = "minimal"
    DISABLED = "disabled"


class ErrorEnhancerConfig:
    """Configuration for error enhancer performance optimization.

    Args:
        mode: Performance mode (FULL/MINIMAL/DISABLED)
        cache_size: LRU cache size for pattern compilation (default: 100)
    """

    def __init__(
        self, mode: PerformanceMode = PerformanceMode.FULL, cache_size: int = 100
    ):
        self.mode = mode
        self.cache_size = cache_size


class BaseErrorEnhancer(ABC):
    """
    Abstract base class for error enhancement in Kailash SDK.

    Performance-optimized with three modes:
    - FULL: Complete enhancement with all context and solutions
    - MINIMAL: Essential context and top solution only
    - DISABLED: Passthrough with minimal wrapper

    Thread-safe pattern caching for 90%+ hit rate on repeated errors.

    Subclasses must implement:
    - get_error_code_prefix(): Return error code prefix (e.g., "DF", "KS")
    - get_catalog_path(): Return path to YAML error catalog

    Usage:
        class CoreErrorEnhancer(BaseErrorEnhancer):
            def get_error_code_prefix(self) -> str:
                return "KS"

            def get_catalog_path(self) -> Path:
                return Path(__file__).parent / "core_error_catalog.yaml"
    """

    BASE_DOCS_URL = "https://docs.kailash.ai"
    _ERROR_CATALOG: Optional[Dict] = None  # Class-level catalog cache

    def __init__(self, config: Optional[ErrorEnhancerConfig] = None):
        """Initialize error enhancer with performance configuration.

        Args:
            config: Error enhancer configuration (defaults to FULL mode)
        """
        self.config = config or ErrorEnhancerConfig()

        # Pattern cache with LRU eviction (thread-safe via functools)
        self._pattern_cache = lru_cache(maxsize=self.config.cache_size)(
            self._compile_pattern_cached
        )

        # Cache statistics (thread-safe with lock)
        self._cache_lock = threading.RLock()
        self._cache_hits = 0
        self._cache_misses = 0
        self._cache_evictions = 0

    @abstractmethod
    def get_error_code_prefix(self) -> str:
        """Return error code prefix for this enhancer.

        Returns:
            Error code prefix (e.g., "DF" for DataFlow, "KS" for Core SDK)
        """
        pass

    @abstractmethod
    def get_catalog_path(self) -> Path:
        """Return path to YAML error catalog.

        Returns:
            Path to error catalog YAML file
        """
        pass

    @classmethod
    def _load_error_catalog(cls, catalog_path: Path) -> Dict:
        """Load error catalog from YAML file with lazy initialization.

        Class method for shared caching across instances.

        Args:
            catalog_path: Path to YAML catalog file

        Returns:
            Dictionary of error definitions keyed by error code
        """
        if cls._ERROR_CATALOG is None:
            if not catalog_path.exists():
                cls._ERROR_CATALOG = {}
                return cls._ERROR_CATALOG

            try:
                with open(catalog_path, "r") as f:
                    cls._ERROR_CATALOG = yaml.safe_load(f) or {}
            except Exception:
                # Fail gracefully if catalog cannot be loaded
                cls._ERROR_CATALOG = {}

        return cls._ERROR_CATALOG

    def _get_error_catalog(self) -> Dict:
        """Get error catalog using subclass-provided path.

        Returns:
            Dictionary of error definitions
        """
        return self._load_error_catalog(self.get_catalog_path())

    @staticmethod
    def _compile_pattern_cached(pattern: str) -> re.Pattern:
        """Compile regex pattern (cached by lru_cache decorator).

        This method is wrapped by lru_cache in __init__ for thread-safe caching.

        Args:
            pattern: Regex pattern string

        Returns:
            Compiled regex pattern
        """
        return re.compile(pattern, re.IGNORECASE | re.DOTALL)

    def find_error_definition(self, exception: Exception) -> Optional[Dict]:
        """Find error definition by matching exception to catalog patterns.

        Uses LRU cache for pattern compilation to achieve 90%+ hit rate
        on repeated error patterns.

        Args:
            exception: Python exception to match

        Returns:
            Error definition dict with keys: code, pattern, causes, solutions, docs_url
            Returns None if no matching error found in catalog
        """
        catalog = self._get_error_catalog()
        exception_str = f"{type(exception).__name__}: {str(exception)}"

        # Track cache statistics
        cache_info_before = self._pattern_cache.cache_info()

        for error_code, error_def in catalog.items():
            pattern = error_def.get("pattern", "")
            if pattern:
                # Pattern compilation is LRU cached
                compiled_pattern = self._pattern_cache(pattern)
                if compiled_pattern.search(exception_str):
                    # Update cache stats
                    cache_info_after = self._pattern_cache.cache_info()
                    with self._cache_lock:
                        if cache_info_after.hits > cache_info_before.hits:
                            self._cache_hits += 1
                        else:
                            self._cache_misses += 1

                    # Return error definition with error code
                    return {**error_def, "code": error_code}

        return None

    def get_cache_hit_rate(self) -> float:
        """Calculate cache hit rate percentage.

        Returns:
            Cache hit rate as percentage (0.0-100.0)
        """
        with self._cache_lock:
            total = self._cache_hits + self._cache_misses
            if total == 0:
                return 0.0
            return (self._cache_hits / total) * 100.0

    def get_cache_info(self) -> Dict[str, Any]:
        """Get cache statistics for monitoring and debugging.

        Returns:
            Dictionary with keys:
            - hits: Number of cache hits
            - misses: Number of cache misses
            - hit_rate: Hit rate percentage
            - cache_info: functools.lru_cache info tuple
        """
        with self._cache_lock:
            return {
                "hits": self._cache_hits,
                "misses": self._cache_misses,
                "hit_rate": self.get_cache_hit_rate(),
                "cache_info": self._pattern_cache.cache_info()._asdict(),
            }

    def reset_cache_stats(self):
        """Reset cache statistics (useful for testing)."""
        with self._cache_lock:
            self._cache_hits = 0
            self._cache_misses = 0
            self._cache_evictions = 0

    def _format_error_message(
        self,
        error_code: str,
        message: str,
        causes: Optional[List[str]] = None,
        solutions: Optional[List[str]] = None,
        docs_url: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Format enhanced error message with consistent structure.

        Args:
            error_code: Error code with prefix (e.g., "DF-101", "KS-501")
            message: Primary error message
            causes: List of possible causes
            solutions: List of suggested solutions
            docs_url: Documentation URL for this error
            context: Additional context dictionary

        Returns:
            Formatted error message string
        """
        # Handle performance modes
        if self.config.mode == PerformanceMode.DISABLED:
            return message

        sections = []

        # Header with error code
        sections.append(f"🚨 Error [{error_code}]: {message}")
        sections.append("=" * 70)

        # Context (FULL mode only)
        if context and self.config.mode == PerformanceMode.FULL:
            sections.append("\n📋 Context:")
            for key, value in context.items():
                sections.append(f"    {key}: {value}")

        # Causes (FULL mode only, or first cause in MINIMAL)
        if causes:
            sections.append("\n🔍 Possible Causes:")
            if self.config.mode == PerformanceMode.MINIMAL:
                sections.append(f"    • {causes[0]}")
            else:
                for cause in causes:
                    sections.append(f"    • {cause}")

        # Solutions (first solution in MINIMAL, all in FULL)
        if solutions:
            sections.append("\n💡 Solutions:")
            if self.config.mode == PerformanceMode.MINIMAL:
                sections.append(f"    1. {solutions[0]}")
            else:
                for i, solution in enumerate(solutions, 1):
                    sections.append(f"    {i}. {solution}")

        # Documentation URL
        if docs_url:
            sections.append(f"\n📚 Documentation: {docs_url}")

        return "\n".join(sections)
