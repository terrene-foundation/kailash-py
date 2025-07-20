# Docker infrastructure configuration
# Standardized test environment configuration
# Use ./test-env script to manage Docker services
import os

# PostgreSQL configuration - using Docker container on port 5434
DATABASE_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5434")),
    "database": os.getenv("DB_NAME", "kailash_test"),
    "user": os.getenv("DB_USER", "test_user"),
    "password": os.getenv("DB_PASSWORD", "test_password"),
}

# Redis configuration - using test Redis on port 6380
REDIS_CONFIG = {
    "host": os.getenv("REDIS_HOST", "localhost"),
    "port": int(os.getenv("REDIS_PORT", "6380")),
}

# MongoDB configuration
MONGODB_CONFIG = {
    "host": os.getenv("MONGO_HOST", "localhost"),
    "port": int(os.getenv("MONGO_PORT", "27017")),
    "username": os.getenv("MONGO_USER", "kailash"),
    "password": os.getenv("MONGO_PASSWORD", "kailash123"),
}

# Kafka configuration
KAFKA_CONFIG = {
    "bootstrap_servers": os.getenv("KAFKA_SERVERS", "localhost:9092"),
}

# MySQL configuration - using test MySQL on port 3307
MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "localhost"),
    "port": int(os.getenv("MYSQL_PORT", "3307")),
    "database": os.getenv("MYSQL_DATABASE", "kailash_test"),
    "user": os.getenv("MYSQL_USER", "kailash_test"),
    "password": os.getenv("MYSQL_PASSWORD", "test_password"),
}

# Ollama configuration - using test Ollama on port 11435
OLLAMA_CONFIG = {
    "host": os.getenv("OLLAMA_HOST", "localhost"),
    "port": int(os.getenv("OLLAMA_PORT", "11435")),
    "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11435"),
}

# OAuth2 configuration
OAUTH2_CONFIG = {
    "host": os.getenv("OAUTH2_HOST", "http://localhost:8080"),
}

# Qdrant configuration
QDRANT_CONFIG = {
    "host": os.getenv("QDRANT_HOST", "localhost"),
    "port": int(os.getenv("QDRANT_PORT", "6333")),
}

# Mock API configuration - Port 8888 (LOCKED-IN)
MOCK_API_CONFIG = {
    "host": os.getenv("MOCK_API_HOST", "localhost"),
    "port": int(os.getenv("MOCK_API_PORT", "8888")),
    "base_url": os.getenv("MOCK_API_BASE_URL", "http://localhost:8888"),
}

# Kubernetes configuration - using kind in Docker on port 6443
KUBERNETES_CONFIG = {
    "host": os.getenv("KUBERNETES_HOST", "localhost"),
    "port": int(os.getenv("KUBERNETES_PORT", "6443")),
    "api_server": os.getenv("KUBERNETES_API_SERVER", "https://localhost:6443"),
    "namespace": os.getenv("KUBERNETES_NAMESPACE", "default"),
    "config_path": os.getenv("KUBECONFIG"),  # Path to kubeconfig file if available
}


# Connection string helpers
def get_postgres_connection_string(database=None):
    """Get PostgreSQL connection string for the Docker setup."""
    db = database or DATABASE_CONFIG["database"]
    return (
        f"postgresql://{DATABASE_CONFIG['user']}:{DATABASE_CONFIG['password']}"
        f"@{DATABASE_CONFIG['host']}:{DATABASE_CONFIG['port']}/{db}"
    )


def get_mongodb_connection_string(database="kailash"):
    """Get MongoDB connection string for the Docker setup."""
    return (
        f"mongodb://{MONGODB_CONFIG['username']}:{MONGODB_CONFIG['password']}"
        f"@{MONGODB_CONFIG['host']}:{MONGODB_CONFIG['port']}/{database}"
    )


def get_redis_url():
    """Get Redis URL for the Docker setup."""
    return f"redis://{REDIS_CONFIG['host']}:{REDIS_CONFIG['port']}"


def get_redis_connection_params():
    """Get Redis connection parameters for direct client setup."""
    return REDIS_CONFIG


def get_mysql_connection_string(database=None):
    """Get MySQL connection string for the Docker setup."""
    db = database or MYSQL_CONFIG["database"]
    return (
        f"mysql://{MYSQL_CONFIG['user']}:{MYSQL_CONFIG['password']}"
        f"@{MYSQL_CONFIG['host']}:{MYSQL_CONFIG['port']}/{db}"
    )


def get_mock_api_url():
    """Get Mock API URL for the Docker setup."""
    return MOCK_API_CONFIG["base_url"]


def get_kubernetes_config():
    """Get Kubernetes configuration for the Docker setup."""
    return KUBERNETES_CONFIG


def get_kubernetes_api_server():
    """Get Kubernetes API server URL for the Docker setup."""
    return KUBERNETES_CONFIG["api_server"]


# Test database names
TEST_DATABASES = {
    "admin": "kailash_admin",
    "test": "kailash_test",
    "enterprise": "kailash_enterprise",
    "dev": "kailash_dev",
}


def is_docker_available():
    """Check if Docker daemon is available."""
    try:
        import subprocess

        result = subprocess.run(["docker", "info"], capture_output=True, timeout=5)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        return False


def is_postgres_available():
    """Check if PostgreSQL service is available."""
    try:
        import psycopg2

        conn = psycopg2.connect(
            host=DATABASE_CONFIG["host"],
            port=DATABASE_CONFIG["port"],
            database=DATABASE_CONFIG["database"],
            user=DATABASE_CONFIG["user"],
            password=DATABASE_CONFIG["password"],
            connect_timeout=3,
        )
        conn.close()
        return True
    except Exception:
        return False


def is_redis_available():
    """Check if Redis service is available."""
    try:
        import redis

        r = redis.Redis(**REDIS_CONFIG, socket_connect_timeout=3)
        r.ping()
        return True
    except Exception:
        return False


def is_ollama_available():
    """Check if Ollama service is available."""
    try:
        import requests

        response = requests.get(
            f"http://{OLLAMA_CONFIG['host']}:{OLLAMA_CONFIG['port']}/api/tags",
            timeout=3,
        )
        return response.status_code == 200
    except Exception:
        return False


def is_kubernetes_available():
    """Check if Kubernetes service is available."""
    try:
        import subprocess

        # Check if kubectl is available
        kubectl_result = subprocess.run(
            ["kubectl", "version", "--client"], capture_output=True, timeout=5
        )
        if kubectl_result.returncode != 0:
            return False

        # Check if we can connect to the cluster
        cluster_result = subprocess.run(
            ["kubectl", "cluster-info", "--request-timeout=3s"],
            capture_output=True,
            timeout=5,
        )
        return cluster_result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        return False


async def ensure_docker_services():
    """Ensure essential Docker services are available."""
    import asyncio

    import httpx

    try:
        # Check PostgreSQL (REQUIRED)
        import asyncpg

        conn = await asyncpg.connect(get_postgres_connection_string())
        await conn.close()

        # Check Redis (REQUIRED)
        import redis

        r = redis.Redis(**REDIS_CONFIG)
        r.ping()

        # Optional services - log warnings but don't fail
        warnings = []

        # Check MySQL (OPTIONAL)
        try:
            import pymysql

            conn = pymysql.connect(
                host=MYSQL_CONFIG["host"],
                port=MYSQL_CONFIG["port"],
                user=MYSQL_CONFIG["user"],
                password=MYSQL_CONFIG["password"],
                database=MYSQL_CONFIG["database"],
            )
            conn.close()
        except Exception:
            warnings.append("MySQL not available (some tests may skip)")

        # Check Ollama (OPTIONAL)
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"http://{OLLAMA_CONFIG['host']}:{OLLAMA_CONFIG['port']}/api/tags",
                    timeout=5.0,
                )
                if response.status_code != 200:
                    warnings.append("Ollama not responding (AI tests may skip)")
        except Exception:
            warnings.append("Ollama not available (AI tests may skip)")

        # Check Mock API (OPTIONAL)
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{MOCK_API_CONFIG['base_url']}/health",
                    timeout=5.0,
                )
                if response.status_code != 200:
                    warnings.append("Mock API not responding (some tests may skip)")
        except Exception:
            warnings.append("Mock API not available (some tests may skip)")

        # Print warnings but don't fail
        if warnings:
            print("Service warnings:")
            for warning in warnings:
                print(f"  - {warning}")

        return True
    except Exception as e:
        print(f"Essential Docker services check failed: {e}")
        return False


# Pytest decorators for E2E tests
def requires_docker(func):
    """Decorator to mark tests that require Docker services."""
    import pytest

    return pytest.mark.requires_docker(
        pytest.mark.skipif(not is_docker_available(), reason="Docker not available")(
            func
        )
    )


def requires_postgres(func):
    """Decorator to mark tests that require PostgreSQL service."""
    import pytest

    return pytest.mark.requires_postgres(
        pytest.mark.skipif(
            not is_postgres_available(), reason="PostgreSQL not available"
        )(func)
    )


def requires_redis(func):
    """Decorator to mark tests that require Redis service."""
    import pytest

    return pytest.mark.requires_redis(
        pytest.mark.skipif(not is_redis_available(), reason="Redis not available")(func)
    )


def requires_ollama(func):
    """Decorator to mark tests that require Ollama service."""
    import pytest

    return pytest.mark.requires_ollama(
        pytest.mark.skipif(not is_ollama_available(), reason="Ollama not available")(
            func
        )
    )


# Combined skip conditions for common scenarios
def skip_if_no_postgres():
    """Skip test if PostgreSQL is not available."""
    import pytest

    return pytest.mark.skipif(
        not is_postgres_available(), reason="PostgreSQL not available"
    )


def skip_if_no_docker():
    """Skip test if Docker is not available."""
    import pytest

    return pytest.mark.skipif(not is_docker_available(), reason="Docker not available")


def skip_if_no_ollama():
    """Skip test if Ollama is not available."""
    import pytest

    return pytest.mark.skipif(not is_ollama_available(), reason="Ollama not available")
