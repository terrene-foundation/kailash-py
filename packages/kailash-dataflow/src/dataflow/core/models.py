"""
DataFlow Models and Configuration

Core model classes and configuration management.
"""

import os
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class Environment(Enum):
    """Environment detection for automatic configuration"""

    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"

    @classmethod
    def detect(cls) -> "Environment":
        """Automatically detect current environment"""
        env = os.getenv("KAILASH_ENV", os.getenv("ENVIRONMENT", "development")).lower()

        # Common environment variable patterns
        if env in ["dev", "development", "local"]:
            return cls.DEVELOPMENT
        elif env in ["test", "testing", "ci"]:
            return cls.TESTING
        elif env in ["stage", "staging", "pre-prod"]:
            return cls.STAGING
        elif env in ["prod", "production", "live"]:
            return cls.PRODUCTION
        else:
            # Default to development for safety
            return cls.DEVELOPMENT


# Note: DataFlowConfig has been moved to config.py to avoid circular imports
# It's re-exported from there for backward compatibility


@dataclass
class DataFlowModel:
    """Base class for DataFlow models."""

    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self):
        """Convert model to dictionary."""
        result = {}
        for key, value in self.__dict__.items():
            if not key.startswith("_"):
                result[key] = value
        return result

    @classmethod
    def from_dict(cls, data: dict):
        """Create model from dictionary."""
        import inspect

        # Get the constructor signature to filter out extra fields
        signature = inspect.signature(cls.__init__)
        valid_params = set(signature.parameters.keys()) - {"self"}

        # Filter data to only include valid constructor parameters
        filtered_data = {k: v for k, v in data.items() if k in valid_params}

        return cls(**filtered_data)

    def __str__(self):
        """String representation of the model."""
        return f"{self.__class__.__name__}({', '.join(f'{k}={v}' for k, v in self.to_dict().items())})"

    def __repr__(self):
        """Representation of the model."""
        return self.__str__()
