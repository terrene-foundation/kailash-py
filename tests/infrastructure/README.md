# Test Infrastructure

This directory contains Docker infrastructure definitions for testing.

## Contents

- `docker-compose.test.yml` - Defines all test services (PostgreSQL, MySQL, Redis, Ollama)
- `Dockerfile.test` - Test runner Docker image definition

## Usage

To start test infrastructure:
```bash
# From tests/utils directory
./start_docker_services.sh

# Or manually from this directory
docker-compose -f docker-compose.test.yml up -d
```

## Related Files

- Configuration: `tests/utils/docker_config.py`
- Setup scripts: `tests/utils/setup_local_docker.py`, `tests/utils/start_docker_services.sh`
- Validation: `tests/utils/validate_ci_environment.py`
- Tests: `tests/test_docker_infrastructure.py`
