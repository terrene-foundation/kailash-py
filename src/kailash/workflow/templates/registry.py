"""
Workflow template registry for centralized template management.

This module provides a singleton registry for discovering, registering, and
managing workflow templates across the SDK. The registry enables template
reuse, versioning, and discovery.

Design Philosophy:
    The registry acts as a central repository for all workflow templates,
    enabling teams to share and reuse common workflow patterns. It supports
    categorization, search, and version management.

Example:
    >>> # Get the singleton registry instance
    >>> registry = WorkflowTemplateRegistry()
    >>>
    >>> # Register a custom template
    >>> template = WorkflowTemplate(
    ...     template_id="data_pipeline",
    ...     name="Data Processing Pipeline",
    ...     description="ETL workflow for data processing",
    ...     category="data_processing"
    ... )
    >>> registry.register(template)
    >>>
    >>> # Retrieve a template
    >>> etl_template = registry.get("data_pipeline")
    >>>
    >>> # List all templates in a category
    >>> data_templates = registry.list_templates(category="data_processing")
    >>> for t in data_templates:
    ...     print(f"{t.template_id}: {t.name}")
    >>>
    >>> # Search templates
    >>> ml_templates = registry.search("machine learning")
    >>>
    >>> # Check if template exists
    >>> if registry.has_template("hierarchical_rag"):
    ...     rag_template = registry.get("hierarchical_rag")
"""

from typing import Dict, List, Optional, Set

from kailash.sdk_exceptions import KailashNotFoundException
from kailash.workflow.templates.base import WorkflowTemplate


class WorkflowTemplateRegistry:
    """
    Singleton registry for workflow templates.

    The registry provides centralized management of workflow templates,
    enabling discovery, versioning, and categorization of reusable
    workflow patterns.

    Design Features:
        1. Singleton pattern for global access
        2. Template categorization and tagging
        3. Version management support
        4. Search and discovery capabilities
        5. Built-in template loading

    Example:
        >>> # Access the singleton registry
        >>> registry = WorkflowTemplateRegistry()
        >>>
        >>> # Register a new template
        >>> from kailash.workflow.templates.base import WorkflowTemplate, TemplateParameter
        >>>
        >>> template = WorkflowTemplate(
        ...     template_id="customer_analysis",
        ...     name="Customer Analysis Pipeline",
        ...     description="Analyze customer data and generate insights",
        ...     category="analytics",
        ...     tags=["customer", "analytics", "insights"]
        ... )
        >>>
        >>> # Add parameters
        >>> template.add_parameter(TemplateParameter(
        ...     name="data_source",
        ...     type=str,
        ...     description="Path to customer data"
        ... ))
        >>>
        >>> # Register the template
        >>> registry.register(template)
        >>>
        >>> # List templates by category
        >>> analytics_templates = registry.list_templates(category="analytics")
        >>> print(f"Found {len(analytics_templates)} analytics templates")
        >>>
        >>> # Search by tags
        >>> customer_templates = registry.search_by_tags(["customer"])
        >>>
        >>> # Get template with error handling
        >>> try:
        ...     template = registry.get("customer_analysis")
        ...     workflow = template.instantiate(data_source="customers.csv")
        ... except KailashNotFoundException:
        ...     print("Template not found")
        >>>
        >>> # Remove a template
        >>> registry.unregister("old_template")
        >>>
        >>> # Get all categories
        >>> categories = registry.get_categories()
        >>> print(f"Available categories: {categories}")
    """

    _instance = None

    def __new__(cls):
        """Ensure singleton instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.templates: Dict[str, WorkflowTemplate] = {}
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize registry and load built-in templates."""
        if not self._initialized:
            self._load_builtin_templates()
            self._initialized = True

    def _load_builtin_templates(self) -> None:
        """Load built-in workflow templates."""
        try:
            # Import built-in templates
            from .hierarchical_rag import (
                create_hierarchical_rag_template,
                create_simple_rag_template,
            )

            # Register built-in templates
            self.register(create_hierarchical_rag_template())
            self.register(create_simple_rag_template())

            # Add more built-in templates as they are created
            # from .etl import create_etl_template
            # from .ml_pipeline import create_ml_pipeline_template
            # etc.

        except ImportError:
            # Built-in templates not available yet
            pass

    def register(self, template: WorkflowTemplate) -> None:
        """
        Register a workflow template.

        Args:
            template: WorkflowTemplate to register

        Raises:
            ValueError: If template with same ID already exists

        Example:
            >>> registry = WorkflowTemplateRegistry()
            >>> template = WorkflowTemplate("my_template", "My Template", "Description")
            >>> registry.register(template)
        """
        if template.template_id in self.templates:
            existing = self.templates[template.template_id]
            if existing.version != template.version:
                raise ValueError(
                    f"Template '{template.template_id}' already exists with version "
                    f"{existing.version}. New version: {template.version}"
                )
            else:
                raise ValueError(
                    f"Template '{template.template_id}' already registered"
                )

        self.templates[template.template_id] = template

    def unregister(self, template_id: str) -> None:
        """
        Remove a template from the registry.

        Args:
            template_id: ID of template to remove

        Example:
            >>> registry.unregister("obsolete_template")
        """
        if template_id in self.templates:
            del self.templates[template_id]

    def get(self, template_id: str) -> WorkflowTemplate:
        """
        Get a template by ID.

        Args:
            template_id: Template identifier

        Returns:
            WorkflowTemplate instance

        Raises:
            KailashNotFoundException: If template not found

        Example:
            >>> template = registry.get("hierarchical_rag")
            >>> workflow = template.instantiate(document_content="...", query="...")
        """
        if template_id not in self.templates:
            raise KailashNotFoundException(
                f"Template '{template_id}' not found. "
                f"Available templates: {list(self.templates.keys())}"
            )
        return self.templates[template_id]

    def has_template(self, template_id: str) -> bool:
        """
        Check if a template exists.

        Args:
            template_id: Template identifier

        Returns:
            True if template exists

        Example:
            >>> if registry.has_template("data_pipeline"):
            ...     template = registry.get("data_pipeline")
        """
        return template_id in self.templates

    def list_templates(
        self, category: Optional[str] = None, tags: Optional[List[str]] = None
    ) -> List[WorkflowTemplate]:
        """
        List available templates with optional filtering.

        Args:
            category: Filter by category
            tags: Filter by tags (matches ANY tag)

        Returns:
            List of matching templates

        Example:
            >>> # All templates
            >>> all_templates = registry.list_templates()
            >>>
            >>> # By category
            >>> ai_templates = registry.list_templates(category="ai/document_processing")
            >>>
            >>> # By tags
            >>> rag_templates = registry.list_templates(tags=["rag", "retrieval"])
        """
        templates = list(self.templates.values())

        if category:
            templates = [t for t in templates if t.category == category]

        if tags:
            tag_set = set(tags)
            templates = [t for t in templates if tag_set.intersection(set(t.tags))]

        return templates

    def search(self, query: str) -> List[WorkflowTemplate]:
        """
        Search templates by query string.

        Searches in template name, description, and tags.

        Args:
            query: Search query (case-insensitive)

        Returns:
            List of matching templates

        Example:
            >>> # Search for machine learning templates
            >>> ml_templates = registry.search("machine learning")
            >>>
            >>> # Search for RAG templates
            >>> rag_templates = registry.search("rag")
        """
        query_lower = query.lower()
        results = []

        for template in self.templates.values():
            # Search in name
            if query_lower in template.name.lower():
                results.append(template)
                continue

            # Search in description
            if query_lower in template.description.lower():
                results.append(template)
                continue

            # Search in tags
            for tag in template.tags:
                if query_lower in tag.lower():
                    results.append(template)
                    break

        return results

    def search_by_tags(
        self, tags: List[str], match_all: bool = False
    ) -> List[WorkflowTemplate]:
        """
        Search templates by tags.

        Args:
            tags: Tags to search for
            match_all: If True, template must have ALL tags. If False, ANY tag.

        Returns:
            List of matching templates

        Example:
            >>> # Find templates with ANY of these tags
            >>> templates = registry.search_by_tags(["rag", "document"], match_all=False)
            >>>
            >>> # Find templates with ALL of these tags
            >>> templates = registry.search_by_tags(["ai", "validated"], match_all=True)
        """
        tag_set = set(tags)
        results = []

        for template in self.templates.values():
            template_tags = set(template.tags)

            if match_all:
                # Template must have all requested tags
                if tag_set.issubset(template_tags):
                    results.append(template)
            else:
                # Template must have at least one requested tag
                if tag_set.intersection(template_tags):
                    results.append(template)

        return results

    def get_categories(self) -> Set[str]:
        """
        Get all unique categories.

        Returns:
            Set of category names

        Example:
            >>> categories = registry.get_categories()
            >>> for category in sorted(categories):
            ...     print(f"- {category}")
        """
        return {t.category for t in self.templates.values()}

    def get_all_tags(self) -> Set[str]:
        """
        Get all unique tags across all templates.

        Returns:
            Set of all tags

        Example:
            >>> tags = registry.get_all_tags()
            >>> print(f"Available tags: {sorted(tags)}")
        """
        all_tags = set()
        for template in self.templates.values():
            all_tags.update(template.tags)
        return all_tags

    def clear(self) -> None:
        """
        Clear all templates from registry.

        Warning: This removes all templates including built-ins.

        Example:
            >>> # Clear for testing
            >>> registry.clear()
            >>> assert len(registry.list_templates()) == 0
            >>>
            >>> # Reload built-ins
            >>> registry._load_builtin_templates()
        """
        self.templates.clear()

    def __repr__(self) -> str:
        """String representation."""
        return f"WorkflowTemplateRegistry(templates={len(self.templates)})"

    def __len__(self) -> int:
        """Number of registered templates."""
        return len(self.templates)
