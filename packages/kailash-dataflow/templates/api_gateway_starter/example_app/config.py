"""
Configuration for API Gateway Example Application.

Environment variable based configuration with Pydantic validation.
"""

import os
from typing import List

from pydantic import BaseModel, Field


class Settings(BaseModel):
    """
    Application settings loaded from environment variables.

    Environment Variables:
        DATABASE_URL: Database connection URL (default: ":memory:")
        JWT_SECRET: Secret key for JWT token signing (required in production)
        ALLOWED_ORIGINS: Comma-separated list of allowed CORS origins (default: "*")
        RATE_LIMIT_REQUESTS: Maximum requests per window (default: 1000)
        RATE_LIMIT_WINDOW: Time window in seconds (default: 3600)
        DEBUG: Enable debug mode (default: False)

    Example:
        >>> from dotenv import load_dotenv
        >>> load_dotenv()
        >>> settings = Settings()
        >>> print(settings.database_url)
        postgresql://localhost/mydb
    """

    database_url: str = Field(
        default=os.getenv("DATABASE_URL", ":memory:"),
        description="Database connection URL",
    )

    jwt_secret: str = Field(
        default=os.getenv("JWT_SECRET", "change-this-secret-in-production"),
        description="Secret key for JWT tokens",
    )

    allowed_origins: List[str] = Field(
        default_factory=lambda: os.getenv("ALLOWED_ORIGINS", "*").split(","),
        description="Allowed CORS origins",
    )

    rate_limit_requests: int = Field(
        default=int(os.getenv("RATE_LIMIT_REQUESTS", "1000")),
        description="Maximum requests per rate limit window",
    )

    rate_limit_window: int = Field(
        default=int(os.getenv("RATE_LIMIT_WINDOW", "3600")),
        description="Rate limit window in seconds",
    )

    debug: bool = Field(
        default=os.getenv("DEBUG", "false").lower() == "true",
        description="Enable debug mode",
    )

    class Config:
        """Pydantic configuration."""

        env_file = ".env"
        case_sensitive = False


def get_settings() -> Settings:
    """
    Get application settings instance.

    Returns:
        Settings instance with loaded configuration

    Example:
        >>> settings = get_settings()
        >>> print(settings.database_url)
    """
    return Settings()
