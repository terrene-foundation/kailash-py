"""
Workflow template system for reusable workflow patterns.

This module provides a comprehensive template system that allows users to:
1. Define reusable workflow patterns with parameters
2. Compose workflows as building blocks for larger workflows
3. Package and distribute workflow templates
4. Discover and search available templates

Design Philosophy:
    Templates solve the problem of workflow reusability by providing parameterized
    workflow factories that can be instantiated with different configurations.
    This enables sharing of best practices and common patterns across teams.

Architecture:
    - WorkflowTemplate: Core template class with parameterization
    - TemplateRegistry: Central registry for template discovery
    - TemplatePackage: Distribution and packaging system
    - SubWorkflow: Node wrapper for embedding templates in workflows

Usage Patterns:
    1. Create templates for common workflow patterns
    2. Register templates in the central registry
    3. Instantiate templates with specific parameters
    4. Compose templates into larger workflows
    5. Package and distribute template collections
"""

from .base import TemplateParameter, WorkflowTemplate
from .composer import SubWorkflow, WorkflowComposer
from .discovery import TemplateDiscovery
from .package import TemplatePackage
from .registry import WorkflowTemplateRegistry

__all__ = [
    "WorkflowTemplate",
    "TemplateParameter",
    "WorkflowTemplateRegistry",
    "SubWorkflow",
    "WorkflowComposer",
    "TemplatePackage",
    "TemplateDiscovery",
]
