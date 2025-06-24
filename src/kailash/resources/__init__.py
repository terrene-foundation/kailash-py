"""
Kailash Resource Management System

This module provides centralized resource management for the Kailash SDK,
solving the fundamental problem of passing non-serializable resources (like
database connections, HTTP clients, etc.) through JSON APIs.

Key Components:
- ResourceRegistry: Central registry for all shared resources
- ResourceFactory: Abstract factory interface for creating resources
- Built-in factories for common resources (databases, HTTP clients, caches)
"""

from .factory import (
    CacheFactory,
    DatabasePoolFactory,
    HttpClientFactory,
    MessageQueueFactory,
    ResourceFactory,
)
from .health import HealthCheck, HealthStatus
from .reference import ResourceReference
from .registry import ResourceNotFoundError, ResourceRegistry

__all__ = [
    # Core
    "ResourceRegistry",
    "ResourceNotFoundError",
    # Factories
    "ResourceFactory",
    "DatabasePoolFactory",
    "HttpClientFactory",
    "CacheFactory",
    "MessageQueueFactory",
    # References
    "ResourceReference",
    # Health
    "HealthCheck",
    "HealthStatus",
]
