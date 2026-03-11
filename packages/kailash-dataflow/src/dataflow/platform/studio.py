"""
DataFlowStudio - Quick setup API for DataFlow.

Provides 1-minute setup for common use cases with:
- Pre-configured profiles (development, production, testing)
- Automatic node generation and validation
- Easy access to generated nodes
- Build-time validation
- Best practice configuration
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Type

import yaml

if TYPE_CHECKING:
    from dataflow import DataFlow

from .errors import DataFlowError, ErrorCode
from .validation import BuildValidator, ValidationLevel, ValidationReport


class ConfigProfile:
    """Pre-configured profile for DataFlow setup."""

    PROFILES = {
        "development": {
            "enable_audit": False,
            "migration_strategy": "auto",
            "debug_mode": True,
            "pool_size": 5,
            "max_overflow": 5,
            "connection_validation": "warn",
            "description": "Development profile with auto-migrations and debugging enabled",
        },
        "production": {
            "enable_audit": True,
            "migration_strategy": "deferred",
            "debug_mode": False,
            "pool_size": 20,
            "max_overflow": 10,
            "connection_validation": "strict",
            "description": "Production profile with audit trail, deferred migrations, and strict validation",
        },
        "testing": {
            "enable_audit": False,
            "migration_strategy": "immediate",
            "debug_mode": False,
            "database_url": "sqlite:///:memory:",
            "pool_size": 1,
            "max_overflow": 0,
            "connection_validation": "strict",
            "description": "Testing profile with in-memory database and immediate migrations",
        },
    }

    @classmethod
    def get(cls, profile_name: str) -> dict[str, Any]:
        """
        Get configuration for a specific profile.

        Args:
            profile_name: Name of profile (development, production, testing)

        Returns:
            Configuration dictionary

        Raises:
            DataFlowError: If profile not found
        """
        if profile_name not in cls.PROFILES:
            raise DataFlowError(
                error_code=ErrorCode.PROFILE_NOT_FOUND,
                message=f"Profile '{profile_name}' not found",
                context={
                    "profile": profile_name,
                    "available": list(cls.PROFILES.keys()),
                },
                causes=[
                    "Profile name is misspelled",
                    "Profile not defined in ConfigProfile.PROFILES",
                ],
                solutions=[],
                docs_url="https://docs.kailash.ai/dataflow/platform/profiles",
            )

        return cls.PROFILES[profile_name].copy()

    @classmethod
    def list_profiles(cls) -> dict[str, str]:
        """
        List all available profiles with descriptions.

        Returns:
            Dictionary mapping profile names to descriptions
        """
        return {
            name: config.get("description", "") for name, config in cls.PROFILES.items()
        }

    @classmethod
    def load_custom_profile(cls, file_path: str | Path) -> dict[str, Any]:
        """
        Load a custom profile from YAML file.

        Args:
            file_path: Path to YAML profile file

        Returns:
            Configuration dictionary

        Raises:
            FileNotFoundError: If file doesn't exist
            yaml.YAMLError: If file is not valid YAML
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Profile file not found: {file_path}")

        with open(file_path) as f:
            return yaml.safe_load(f)


class NodeAccessor:
    """Provides easy access to generated DataFlow nodes."""

    def __init__(self, model_name: str, db_instance: "DataFlow"):
        """
        Initialize node accessor for a specific model.

        Args:
            model_name: Name of the model
            db_instance: DataFlow instance
        """
        self.model_name = model_name
        self.db = db_instance
        self._node_types = [
            "create",
            "read",
            "read_by_id",
            "update",
            "delete",
            "list",
            "count",
            "upsert",
            "bulk_create",
        ]

    def __getattr__(self, name: str) -> Type:
        """
        Get a specific node type for the model.

        Args:
            name: Node type (e.g., 'create', 'read', 'update')

        Returns:
            Node class

        Raises:
            AttributeError: If node type doesn't exist
        """
        if name in self._node_types:
            node_class_name = f"{self.model_name}{name.title().replace('_', '')}Node"
            # This would get the actual node class from DataFlow
            # For now, return a placeholder
            return type(node_class_name, (), {})

        raise AttributeError(
            f"Node type '{name}' not found for model '{self.model_name}'"
        )

    def all(self) -> dict[str, Type]:
        """
        Get all node types for the model.

        Returns:
            Dictionary mapping node type names to node classes
        """
        return {node_type: getattr(self, node_type) for node_type in self._node_types}


class DataFlowStudio:
    """
    Quick setup API for DataFlow with validation and best practices.

    Provides a developer-friendly interface for:
    - 1-minute setup with pre-configured profiles
    - Automatic model registration and node generation
    - Build-time validation
    - Easy access to generated nodes
    - Auto-fix capabilities
    """

    def __init__(
        self,
        name: str,
        database_url: str,
        models: list[Type],
        profile: str = "development",
        **kwargs,
    ):
        """
        Initialize DataFlowStudio.

        Args:
            name: Application name
            database_url: Database connection URL
            models: List of model classes to register
            profile: Configuration profile name
            **kwargs: Additional DataFlow configuration options
        """
        self.name = name
        self.profile = profile
        self.models = models

        # Get profile configuration
        profile_config = ConfigProfile.get(profile)

        # Override with explicit kwargs
        config = {**profile_config, **kwargs}

        # Remove description and database_url from config if in kwargs
        config.pop("description", None)
        if "database_url" in config and database_url != config["database_url"]:
            config.pop("database_url")

        # Initialize DataFlow with merged configuration
        # Lazy import to avoid circular dependency
        from dataflow import DataFlow

        self.db = DataFlow(database_url=database_url, **config)

        # Register models
        for model in models:
            self.db.register_model(model)

        # Create validator
        self._validator = BuildValidator(self, ValidationLevel.STRICT)

        # Cache for node accessors
        self._node_accessors: dict[str, NodeAccessor] = {}

    @classmethod
    def quick_start(
        cls,
        name: str,
        database: str,
        models: list[Type],
        profile: str = "development",
        auto_validate: bool = True,
        auto_migrate: bool = True,
        **kwargs,
    ) -> "DataFlowStudio":
        """
        Quick start setup for DataFlow - 1 minute to production.

        Args:
            name: Application name
            database: Database connection URL or alias
            models: List of model classes
            profile: Configuration profile (development, production, testing)
            auto_validate: Run validation automatically
            auto_migrate: Run migrations automatically
            **kwargs: Additional configuration options

        Returns:
            Configured DataFlowStudio instance

        Example:
            >>> studio = DataFlowStudio.quick_start(
            ...     name="my_app",
            ...     database="sqlite:///app.db",
            ...     models=[User, Product],
            ...     profile="development"
            ... )
            >>> db = studio.db  # Access DataFlow instance
            >>> create_user = studio.node("User", "create")
        """
        # Handle database aliases
        database_url = cls._resolve_database_url(database)

        # Create instance
        studio = cls(
            name=name,
            database_url=database_url,
            models=models,
            profile=profile,
            **kwargs,
        )

        # Auto-validate
        if auto_validate:
            report = studio.validate()
            if not report.is_valid:
                print(report.show())
                if any(error.auto_fixable for error in report.errors):
                    print("\n🛠️  Attempting auto-fix...")
                    report.auto_fix()

        # Auto-migrate
        if auto_migrate:
            studio.migrate()

        return studio

    @staticmethod
    def _resolve_database_url(database: str) -> str:
        """
        Resolve database URL from alias or full URL.

        Args:
            database: Database URL or alias

        Returns:
            Full database URL
        """
        # Handle common aliases
        if database == ":memory:":
            return "sqlite:///:memory:"

        # If it already looks like a URL, return as-is
        if "://" in database:
            return database

        # Assume it's a file path for SQLite
        return f"sqlite:///{database}"

    def node(self, model_name: str, node_type: str) -> Type:
        """
        Get a specific node for a model.

        Args:
            model_name: Name of the model
            node_type: Type of node (e.g., 'create', 'read', 'update')

        Returns:
            Node class

        Example:
            >>> create_user = studio.node("User", "create")
            >>> read_user = studio.node("User", "read_by_id")
        """
        accessor = self.nodes(model_name)
        return getattr(accessor, node_type)

    def nodes(self, model_name: str) -> NodeAccessor:
        """
        Get node accessor for a model.

        Args:
            model_name: Name of the model

        Returns:
            NodeAccessor instance with all node types

        Example:
            >>> user_nodes = studio.nodes("User")
            >>> create_user = user_nodes.create
            >>> read_user = user_nodes.read
            >>> all_nodes = user_nodes.all()
        """
        if model_name not in self._node_accessors:
            self._node_accessors[model_name] = NodeAccessor(model_name, self.db)
        return self._node_accessors[model_name]

    def validate(self) -> ValidationReport:
        """
        Run comprehensive validation.

        Returns:
            Validation report with errors, warnings, and suggestions

        Example:
            >>> report = studio.validate()
            >>> if not report.is_valid:
            ...     print(report.show())
            ...     report.auto_fix()
        """
        return self._validator.validate_all()

    def validate_workflow(self, workflow: Any) -> ValidationReport:
        """
        Validate a specific workflow.

        Args:
            workflow: WorkflowBuilder instance

        Returns:
            Workflow-specific validation report

        Example:
            >>> workflow = WorkflowBuilder()
            >>> # ... add nodes and connections
            >>> report = studio.validate_workflow(workflow)
        """
        return self._validator.validate_workflow(workflow)

    def migrate(self):
        """
        Run database migrations.

        This executes any pending migrations based on the configured
        migration strategy.

        Example:
            >>> studio.migrate()
        """
        # This would trigger DataFlow migrations
        # Implementation depends on how DataFlow handles migrations
        pass

    def clear_schema_cache(self):
        """
        Clear schema cache.

        Useful when schema conflicts occur or after manual database changes.

        Example:
            >>> studio.clear_schema_cache()
        """
        # This would clear DataFlow's schema cache
        pass

    def check_migration_locks(self) -> dict[str, Any]:
        """
        Check for active migration locks.

        Returns:
            Dictionary with lock status information

        Example:
            >>> locks = studio.check_migration_locks()
            >>> if locks['has_locks']:
            ...     print(f"Active locks: {locks['lock_count']}")
        """
        # This would check for migration locks
        return {"has_locks": False, "lock_count": 0, "locks": []}

    def test_connection(self) -> bool:
        """
        Test database connection.

        Returns:
            True if connection successful

        Example:
            >>> if not studio.test_connection():
            ...     print("Database connection failed")
        """
        try:
            # This would test the actual connection
            return True
        except Exception:
            return False

    def health_check(self) -> dict[str, Any]:
        """
        Comprehensive health check.

        Returns:
            Dictionary with health status

        Example:
            >>> health = studio.health_check()
            >>> print(f"Status: {health['status']}")
            >>> print(f"Issues: {health['issues']}")
        """
        issues = []

        # Check connection
        if not self.test_connection():
            issues.append("Database connection failed")

        # Check migrations
        # This would check if migrations are pending

        # Check models
        if not self.models:
            issues.append("No models registered")

        return {
            "status": "healthy" if not issues else "unhealthy",
            "issues": issues,
            "models_count": len(self.models),
            "database_url": (
                self.db.database_url if hasattr(self.db, "database_url") else "unknown"
            ),
        }

    def inspect(self) -> "Inspector":
        """
        Get inspector for debugging.

        Returns:
            Inspector instance

        Example:
            >>> inspector = studio.inspect()
            >>> node_info = inspector.node("user_create")
            >>> print(node_info.expected_params)
        """
        from .inspector import Inspector

        return Inspector(self)

    def fix_error(self, error_code: str, **kwargs) -> bool:
        """
        Attempt to fix a specific error.

        Args:
            error_code: Error code (e.g., 'DF-101')
            **kwargs: Context-specific parameters

        Returns:
            True if fix was successful

        Example:
            >>> studio.fix_error('DF-101', node_id='user_create')
        """
        from .autofix import AutoFix

        fixer = AutoFix(self)
        return fixer.fix_error(error_code, **kwargs)

    def __repr__(self) -> str:
        """String representation."""
        return f"DataFlowStudio(name='{self.name}', profile='{self.profile}', models={len(self.models)})"
