"""Auto-discovery of workflows in the filesystem.

This module implements smart workflow discovery by scanning for common
workflow patterns in the current directory and subdirectories.
"""

import importlib.util
import logging
import os
from pathlib import Path
from typing import Any, Dict, List

from kailash.workflow import Workflow
from kailash.workflow.builder import WorkflowBuilder

logger = logging.getLogger(__name__)


class WorkflowDiscovery:
    """Discovers and loads workflows from the filesystem."""

    # Common workflow patterns to search for
    WORKFLOW_PATTERNS = [
        "workflows/*.py",
        "*.workflow.py",
        "workflow_*.py",
        "*_workflow.py",
        "src/workflows/*.py",
        "app/workflows/*.py",
    ]

    # Files to exclude from discovery
    EXCLUDE_FILES = {
        "__init__.py",
        "setup.py",
        "conftest.py",
        "__pycache__",
    }

    def __init__(self, base_path: str = None):
        """Initialize discovery with optional base path.

        Args:
            base_path: Directory to search from (defaults to current directory)
        """
        try:
            self.base_path = Path(base_path or os.getcwd())
        except (OSError, FileNotFoundError):
            # Fallback to a safe directory if current working directory is not accessible
            self.base_path = Path("/tmp")
            logger.warning(
                f"Could not access current directory, using fallback: {self.base_path}"
            )
        self._discovered_workflows: Dict[str, Workflow] = {}

    def discover(self) -> Dict[str, Workflow]:
        """Discover all workflows in the filesystem.

        Returns:
            Dictionary mapping workflow names to Workflow instances
        """
        logger.info(f"Starting workflow discovery from {self.base_path}")

        # Search for workflows using each pattern
        for pattern in self.WORKFLOW_PATTERNS:
            self._search_pattern(pattern)

        logger.info(f"Discovered {len(self._discovered_workflows)} workflows")
        return self._discovered_workflows

    def _search_pattern(self, pattern: str):
        """Search for workflows matching a specific pattern.

        Args:
            pattern: Glob pattern to search for
        """
        # Convert pattern to Path and search
        for path in self.base_path.glob(pattern):
            if path.is_file() and path.name not in self.EXCLUDE_FILES:
                self._load_workflow_from_file(path)

    def _load_workflow_from_file(self, file_path: Path):
        """Load workflows from a Python file.

        Args:
            file_path: Path to the Python file
        """
        try:
            # Load the module
            spec = importlib.util.spec_from_file_location(file_path.stem, file_path)
            if not spec or not spec.loader:
                return

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Look for workflow instances or builders
            for name, obj in vars(module).items():
                # Skip imported classes and private attributes
                if name.startswith("_") or name in {"WorkflowBuilder", "Workflow"}:
                    continue

                if self._is_workflow(obj):
                    workflow_name = self._generate_workflow_name(file_path, name)
                    self._discovered_workflows[workflow_name] = self._prepare_workflow(
                        obj
                    )
                    logger.info(f"Discovered workflow: {workflow_name}")

        except Exception as e:
            logger.warning(f"Failed to load workflows from {file_path}: {e}")

    def _is_workflow(self, obj: Any) -> bool:
        """Check if an object is a workflow.

        Args:
            obj: Object to check

        Returns:
            True if object is a workflow or workflow builder
        """
        # Direct workflow instance
        if isinstance(obj, Workflow):
            return True

        # WorkflowBuilder instance
        if isinstance(obj, WorkflowBuilder):
            return True

        # Callable that returns a workflow (factory pattern)
        if callable(obj):
            try:
                # Try calling with no args
                result = obj()
                return isinstance(result, (Workflow, WorkflowBuilder))
            except TypeError as e:
                # Function requires arguments - not a workflow factory
                logger.debug(
                    f"Callable {getattr(obj, '__name__', 'unknown')} requires arguments, not a workflow factory: {e}"
                )
            except Exception as e:
                # Other errors during execution
                logger.warning(
                    f"Error checking if {getattr(obj, '__name__', 'unknown')} is a workflow: {type(e).__name__}: {e}"
                )

        return False

    def _prepare_workflow(self, obj: Any) -> Workflow:
        """Prepare a workflow object for registration.

        Args:
            obj: Workflow, WorkflowBuilder, or factory function

        Returns:
            Workflow instance ready for use
        """
        # Already a workflow
        if isinstance(obj, Workflow):
            return obj

        # WorkflowBuilder - build it
        if isinstance(obj, WorkflowBuilder):
            return obj.build()

        # Factory function - call it and prepare result
        if callable(obj):
            result = obj()
            return self._prepare_workflow(result)

        raise ValueError(f"Cannot prepare workflow from {type(obj)}")

    def _generate_workflow_name(self, file_path: Path, obj_name: str) -> str:
        """Generate a unique workflow name.

        Args:
            file_path: Path to the file containing the workflow
            obj_name: Name of the workflow object in the file

        Returns:
            Unique workflow name
        """
        # Use file name without extension as base
        base_name = file_path.stem

        # If object name is generic, use file name
        if obj_name.lower() in {"workflow", "builder", "wf"}:
            return base_name

        # Otherwise combine for uniqueness
        return f"{base_name}.{obj_name}"


def discover_workflows(base_path: str = None) -> Dict[str, Workflow]:
    """Convenience function to discover workflows.

    Args:
        base_path: Directory to search from (defaults to current directory)

    Returns:
        Dictionary mapping workflow names to Workflow instances
    """
    discovery = WorkflowDiscovery(base_path)
    return discovery.discover()
