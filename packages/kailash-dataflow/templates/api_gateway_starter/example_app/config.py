"""
Configuration for API Gateway Example Application.

Environment variable based configuration with Pydantic validation.
"""

import os
from typing import List

from pydantic import BaseModel, Field

# JWT signing secret MUST come from the environment — fail loudly at import if
# unset so deployments cannot ship with a known hardcoded key. The shared
# envvar name is ``SAAS_STARTER_JWT_SECRET`` so api_gateway_starter and
# saas_starter (which exchange tokens) verify with the same key.
_JWT_SECRET_ENV = "SAAS_STARTER_JWT_SECRET"
_jwt_secret_raw = os.environ.get(_JWT_SECRET_ENV)
if not _jwt_secret_raw:
    raise RuntimeError(
        f"{_JWT_SECRET_ENV} environment variable is required. "
        f"Set a cryptographically random value (>=32 bytes) before importing "
        f"templates.api_gateway_starter.example_app.config. See README for "
        f"production deployment."
    )
_JWT_SECRET: str = _jwt_secret_raw


class Settings(BaseModel):
    """
    Application settings loaded from environment variables.

    Environment Variables:
        DATABASE_URL: Database connection URL (default: ":memory:")
        SAAS_STARTER_JWT_SECRET: Secret key for JWT token signing (REQUIRED,
            shared with saas_starter; fail-loud at import if unset)
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
        default=_JWT_SECRET,
        description="Secret key for JWT tokens (from SAAS_STARTER_JWT_SECRET)",
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
