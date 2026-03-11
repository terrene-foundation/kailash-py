# Phase 7: Centralized Logging Configuration

## Overview

DataFlow Phase 7 introduces a comprehensive logging configuration system that addresses two critical production concerns:

1. **Reducing Excessive Warnings**: Operational messages (node execution, schema checks) moved from INFO to DEBUG, keeping production logs clean while preserving diagnostic capability
2. **Sensitive Data Protection**: Regex-based masking automatically redacts credentials, API keys, and secrets from log messages

The centralized logging system provides:

- Environment variable configuration for 12-factor app compliance
- Category-specific log levels (core, node execution, migrations)
- Production-ready sensitive pattern matching (17 default patterns)
- Context managers for temporary logging changes
- Integration with DataFlow engine initialization

## LoggingConfig

The core configuration dataclass at `src/dataflow/core/logging_config.py` provides flexible, security-aware logging configuration.

### Configuration Fields

```python
from dataflow.core.logging_config import LoggingConfig
import logging

config = LoggingConfig(
    level=logging.WARNING,          # Global log level (DEBUG/INFO/WARNING/ERROR/CRITICAL)
    format="...",                   # Log format string
    mask_sensitive=True,            # Enable sensitive data masking
    mask_patterns=[...],            # Regex patterns for sensitive data
    mask_replacement="***MASKED***",# Replacement string for masked values
    loggers={},                     # Dict of logger name to level overrides
    propagate=True                  # Propagate logs to parent loggers
)
```

**Key Attributes**:

- **level**: Default log level for all DataFlow loggers (defaults to WARNING for production safety)
- **format**: Standard Python log format string (defaults to `"%(asctime)s - %(name)s - %(levelname)s - %(message)s"`)
- **mask_sensitive**: Boolean flag to enable/disable masking (defaults to True)
- **mask_patterns**: List of regex patterns to match sensitive data (defaults to 17 production-ready patterns)
- **mask_replacement**: String used to replace matched sensitive data (defaults to `"***MASKED***"`)
- **loggers**: Dictionary for per-logger level overrides (advanced usage)
- **propagate**: Whether to propagate logs to parent loggers (defaults to True)

### Environment-Based Configuration

The `from_env()` classmethod creates configuration from environment variables, ideal for containerized deployments:

```python
from dataflow.core.logging_config import LoggingConfig

# Read configuration from environment
config = LoggingConfig.from_env()

# With custom prefix
config = LoggingConfig.from_env(prefix="MY_APP")
```

**Environment Variables** (default prefix: `DATAFLOW_`):

- `DATAFLOW_LOG_LEVEL`: Log level (DEBUG/INFO/WARNING/ERROR/CRITICAL)
- `DATAFLOW_LOG_FORMAT`: Log format string
- `DATAFLOW_LOG_MASK_SENSITIVE`: Enable masking (true/false/yes/no/1/0/on/off)
- `DATAFLOW_LOG_MASK_PATTERNS`: Comma-separated additional regex patterns

The environment config automatically combines custom patterns with the 17 default patterns.

### Configuration Presets

Three convenience presets for common scenarios:

```python
from dataflow.core.logging_config import LoggingConfig

# Production: WARNING level, masking enabled
config = LoggingConfig.production()

# Development: DEBUG level, masking enabled (see all operations)
config = LoggingConfig.development()

# Quiet: ERROR level only (minimal output)
config = LoggingConfig.quiet()
```

### Category-Level Logging

DataFlow organizes loggers into categories for fine-grained control:

**Categories**:

- `core`: Core engine operations (dataflow.core, dataflow.utils)
- `node_execution`: Node execution and bulk operations (dataflow.core.nodes, dataflow.features.bulk)
- `migration`: Database migrations (dataflow.migrations.\*)

The `get_level_for_category()` method (inherited from `dataflow.core.config.LoggingConfig`) resolves category-specific levels:

```python
from dataflow.core.config import LoggingConfig

config = LoggingConfig(
    level=logging.WARNING,      # Default for all categories
    node_execution=logging.DEBUG,  # Override for node execution
)

# Get level for a category
level = config.get_level_for_category("node_execution")  # Returns DEBUG
level = config.get_level_for_category("core")           # Returns WARNING
```

## Sensitive Value Masking

DataFlow's sensitive value masking protects against credential leaks in logs, preventing accidental exposure of passwords, API keys, and tokens.

### The mask_sensitive_values() Function

Core masking function that applies regex-based pattern matching:

```python
from dataflow.core.logging_config import mask_sensitive_values, LoggingConfig

# Basic usage with defaults
safe_msg = mask_sensitive_values("postgresql://user:secret@localhost/db")
# Result: "postgresql://user:***MASKED***@localhost/db"

# With custom config
config = LoggingConfig(mask_patterns=["custom_secret=([^\\s]+)"])
safe_msg = mask_sensitive_values("custom_secret=12345", config)
# Result: "custom_secret=***MASKED***"

# Disable masking
config = LoggingConfig(mask_sensitive=False)
safe_msg = mask_sensitive_values("api_key=sk-12345", config)
# Result: "api_key=sk-12345" (unchanged)
```

**How It Works**:

1. Compiles all regex patterns on config initialization (cached for performance)
2. Applies each pattern to the message
3. For patterns with capture groups, replaces only captured groups
4. For patterns without groups, replaces entire match
5. Returns the masked message

### SensitiveMaskingFilter

A `logging.Filter` subclass that automatically masks log records before emission:

```python
import logging
from dataflow.core.logging_config import LoggingConfig, SensitiveMaskingFilter

# Create logger and handler
logger = logging.getLogger("my_app")
handler = logging.StreamHandler()

# Add masking filter
config = LoggingConfig()
handler.addFilter(SensitiveMaskingFilter(config))
logger.addHandler(handler)

# Sensitive data is automatically masked
logger.info("Connecting to postgresql://user:password@localhost/db")
# Output: Connecting to postgresql://user:***MASKED***@localhost/db
```

**Features**:

- Masks both `record.msg` (string messages) and `record.args` (format arguments)
- Handles dict and tuple args correctly
- Always returns True (allows record through after masking)
- Zero performance impact when masking is disabled

### DEFAULT_SENSITIVE_PATTERNS

DataFlow includes 17 production-ready regex patterns covering common secret formats:

```python
from dataflow.core.logging_config import DEFAULT_SENSITIVE_PATTERNS

# Patterns automatically mask:
# 1. Database URLs: postgresql://user:password@host/db
# 2. Password parameters: password=secret, pwd=secret
# 3. API keys: api_key=..., apikey=...
# 4. Bearer tokens: Bearer abc123, Authorization: Bearer ...
# 5. AWS credentials: aws_access_key_id=..., AKIAIOSFODNN7EXAMPLE
# 6. Generic secrets: secret_key=..., private_key=...
# 7. Tokens: token=..., auth_token=..., access_token=...
# 8. Connection strings: password=..., passwd=...
```

**All 17 Patterns**:

1. `(postgresql|postgres|mysql|mariadb|mssql|oracle)://[^:]+:([^@]+)@` - Database URLs
2. `password=([^\s&;]+)` - Generic password parameter
3. `api[_-]?key[=:\s]+([^\s,;"']+)` - API keys (various formats)
4. `apikey[=:\s]+([^\s,;"']+)` - API key (no separator)
5. `bearer\s+([^\s,;"']+)` - Bearer token (case insensitive)
6. `authorization[=:\s]+bearer\s+([^\s,;"']+)` - Authorization header
7. `aws[_-]?access[_-]?key[_-]?id[=:\s]+([^\s,;"']+)` - AWS access key
8. `aws[_-]?secret[_-]?access[_-]?key[=:\s]+([^\s,;"']+)` - AWS secret key
9. `AKIA[A-Z0-9]{16}` - AWS access key ID format
10. `secret[_-]?key[=:\s]+([^\s,;"']+)` - Generic secret key
11. `private[_-]?key[=:\s]+([^\s,;"']+)` - Private key
12. `token[=:\s]+([^\s,;"']+)` - Generic token
13. `credential[s]?[=:\s]+([^\s,;"']+)` - Credentials
14. `auth[_-]?token[=:\s]+([^\s,;"']+)` - Auth token
15. `access[_-]?token[=:\s]+([^\s,;"']+)` - Access token
16. `refresh[_-]?token[=:\s]+([^\s,;"']+)` - Refresh token
17. `(password|pwd|passwd)[=:\s]+([^\s,;"']+)` - Password variants

All patterns are case-insensitive and use capture groups to preserve context.

### Adding Custom Patterns

Extend the default patterns for application-specific secrets:

```python
from dataflow.core.logging_config import LoggingConfig, DEFAULT_SENSITIVE_PATTERNS

# Add custom patterns
custom_patterns = DEFAULT_SENSITIVE_PATTERNS.copy()
custom_patterns.extend([
    r"x-api-token:\s*([^\s,;]+)",       # Custom header
    r"client_secret=([^\s&;]+)",        # OAuth secret
    r"SESSION_ID=([A-Fa-f0-9]{32})",    # Session token
])

config = LoggingConfig(mask_patterns=custom_patterns)
```

**Pattern Design Tips**:

- Use capture groups `(...)` to preserve context (e.g., `password=` prefix)
- Match non-whitespace with `[^\s,;"']+` to avoid over-matching
- Test patterns against real log messages
- Consider case-insensitivity (patterns compiled with `re.IGNORECASE`)

## Logging Utilities

The utilities module at `src/dataflow/utils/suppress_warnings.py` provides high-level functions for managing DataFlow logging.

### configure_dataflow_logging()

Central configuration function that applies settings to all DataFlow loggers:

```python
from dataflow.utils.suppress_warnings import configure_dataflow_logging
from dataflow.core.logging_config import LoggingConfig
import logging

# Use environment variables (reads DATAFLOW_LOG_* env vars)
configure_dataflow_logging()

# Use explicit config
config = LoggingConfig(level=logging.DEBUG)
configure_dataflow_logging(config)

# Use explicit level parameter (overrides config.level)
configure_dataflow_logging(level=logging.DEBUG)

# Combine config with level override
config = LoggingConfig(mask_sensitive=True)
configure_dataflow_logging(config, level=logging.INFO)
```

**What It Does**:

1. Stores original logger state (level, handlers, propagate, filters)
2. Sets log levels for all DataFlow loggers based on config
3. Applies category-specific levels (core, node_execution, migration)
4. Adds `SensitiveMaskingFilter` to all handlers if masking is enabled
5. Suppresses Core SDK warnings (node registration, resource factory)
6. Logs configuration applied at DEBUG level

**Precedence Rules**:

- Explicit `level` parameter overrides `config.level`
- Category-specific levels from config override global level
- Environment variables used only if no config or level provided

### restore_dataflow_logging()

Restores all DataFlow loggers to their original state:

```python
from dataflow.utils.suppress_warnings import (
    configure_dataflow_logging,
    restore_dataflow_logging,
)
import logging

# Change logging
configure_dataflow_logging(level=logging.DEBUG)

# ... do something with debug logging ...

# Restore original levels
restore_dataflow_logging()
```

**What It Restores**:

- Original log levels for all DataFlow loggers
- Original propagation settings
- Removes `SensitiveMaskingFilter` from all handlers
- Restores Core SDK warning levels
- Clears internal state tracking

Safe to call multiple times, even if configuration wasn't changed.

### get_dataflow_logger()

Helper function for consistent logger naming across DataFlow:

```python
from dataflow.utils.suppress_warnings import get_dataflow_logger

# Get component-specific logger
logger = get_dataflow_logger("my_module")
# Returns: logging.getLogger("dataflow.my_module")

# Get root dataflow logger
logger = get_dataflow_logger("")
# Returns: logging.getLogger("dataflow")

# Already prefixed names work too
logger = get_dataflow_logger("dataflow.core.nodes")
# Returns: logging.getLogger("dataflow.core.nodes")
```

**Benefits**:

- Ensures all loggers use "dataflow." prefix
- Idempotent (safe to call with already-prefixed names)
- Centralizes logger naming logic
- Enables category-based configuration

### dataflow_logging_context()

Context manager for temporary logging configuration changes:

```python
from dataflow.utils.suppress_warnings import dataflow_logging_context
from dataflow.core.logging_config import LoggingConfig
import logging

# Enable debug logging temporarily
with dataflow_logging_context(level=logging.DEBUG):
    # Debug logging active here
    logger.debug("This will be logged")
    # ... debug operations ...

# Original logging level restored here

# With config object
with dataflow_logging_context(config=LoggingConfig.development()):
    # Development logging active
    pass

# Safe even with exceptions
try:
    with dataflow_logging_context(level=logging.ERROR):
        raise ValueError("Something went wrong")
except ValueError:
    pass  # Logging is still restored
```

**Features**:

- Automatically restores original state on exit
- Safe with exceptions (uses try/finally internally)
- Supports nested contexts (each saves/restores independently)
- Accepts either `config` or `level` parameter

**Use Cases**:

- Debugging specific operations without affecting global config
- Testing with different log levels
- Temporarily enabling verbose logging for diagnostics

## DataFlow Integration

The logging configuration integrates seamlessly with DataFlow engine initialization.

### Basic Integration

Use `log_level` parameter for simple level control:

```python
from dataflow import DataFlow
import logging

# Default: WARNING level
db = DataFlow("postgresql://user:pass@localhost/mydb")

# Set explicit level
db = DataFlow(
    "postgresql://user:pass@localhost/mydb",
    log_level="DEBUG"  # String or int (logging.DEBUG)
)

# Quiet mode
db = DataFlow(url, log_level="ERROR")
```

**Supported log_level Values**:

- String: "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL" (case insensitive)
- Integer: `logging.DEBUG`, `logging.INFO`, etc.
- Default: "WARNING" (if not specified)

### Advanced Integration

Use `log_config` parameter for full control:

```python
from dataflow import DataFlow
from dataflow.core.logging_config import LoggingConfig
import logging

# Use preset
db = DataFlow(
    "postgresql://user:pass@localhost/mydb",
    log_config=LoggingConfig.production()
)

# Custom configuration
config = LoggingConfig(
    level=logging.INFO,
    mask_sensitive=True,
    mask_patterns=[...],  # Add custom patterns
)
db = DataFlow(url, log_config=config)

# Category-specific levels
from dataflow.core.config import LoggingConfig as ConfigLoggingConfig
config = ConfigLoggingConfig(
    level=logging.WARNING,
    node_execution=logging.DEBUG,  # Debug only node execution
)
db = DataFlow(url, log_config=config)
```

**Note**: Use `dataflow.core.config.LoggingConfig` for category-level configuration (has `get_level_for_category()` method).

### Environment Variable Precedence

DataFlow resolves logging configuration in this order:

1. **Explicit `log_config` parameter** (highest priority)
2. **Explicit `log_level` parameter**
3. **Environment variables** (`DATAFLOW_LOG_LEVEL`, etc.)
4. **Default** (WARNING level, masking enabled)

```python
from dataflow import DataFlow
from dataflow.core.logging_config import LoggingConfig
import os

# Set environment variable
os.environ["DATAFLOW_LOG_LEVEL"] = "DEBUG"

# Environment variable used (DEBUG level)
db = DataFlow(url)

# log_level overrides environment
db = DataFlow(url, log_level="WARNING")

# log_config overrides both
db = DataFlow(url, log_config=LoggingConfig.quiet())
```

### Complete Example

Production-ready DataFlow initialization with logging:

```python
from dataflow import DataFlow
from dataflow.core.logging_config import LoggingConfig
import logging
import os

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Create config from environment with custom patterns
config = LoggingConfig.from_env()
config.mask_patterns.extend([
    r"x-api-key:\s*([^\s,;]+)",      # Custom API key header
    r"session_id=([A-Fa-f0-9]+)",    # Session tokens
])

# Initialize DataFlow with logging config
db = DataFlow(
    os.environ["DATABASE_URL"],
    log_config=config,
)

# Logging is now configured:
# - Level from DATAFLOW_LOG_LEVEL (or WARNING default)
# - Sensitive values masked (database URL password, API keys, etc.)
# - All DataFlow loggers configured consistently
```

## Log Level Changes

Phase 7 recalibrated DataFlow's log levels to reduce production noise while preserving diagnostic capability.

### What Changed

**Operational Messages: INFO → DEBUG**
These messages moved to DEBUG level (silent at default WARNING level):

- Node execution: `"Executing node X with parameters..."`
- Schema checks: `"Model X already has table, skipping..."`
- Workflow progress: `"Step 1/5 complete"`
- Connection details: `"Connected to database"`
- Resource allocation: `"Allocated 10 threads for bulk operations"`

**Warnings Remain Warnings** (still visible at WARNING level):

- SQL injection detection: `"Suspicious pattern detected in input"`
- Auto-managed field stripping: `"Stripped created_at from input (auto-managed)"`
- Suspiciously long input: `"Input field exceeds 10000 chars"`
- Parse failures: `"Failed to parse date string"`
- Missing fields: `"Field 'email' missing from required fields"`

**Errors Remain Errors**:

- Connection failures
- Query errors
- Validation failures
- Constraint violations

### Why This Matters

**Before Phase 7** (noisy production logs):

```
INFO - Executing CreateUser node with parameters: {'name': 'Alice'}
INFO - Model User already has table, skipping migration check
INFO - Connecting to database: postgresql://user:pass@localhost/db
INFO - Executing BulkCreateProduct with 1000 items
WARNING - Stripped created_at from input (auto-managed field)
INFO - Workflow completed in 1.2s
```

**After Phase 7** (clean production logs):

```
WARNING - Stripped created_at from input (auto-managed field)
```

**For Debugging** (enable DEBUG level):

```
DEBUG - Executing CreateUser node with parameters: {'name': 'Alice'}
DEBUG - Model User already has table, skipping migration check
DEBUG - Connecting to database: postgresql://user:***MASKED***@localhost/db
DEBUG - Executing BulkCreateProduct with 1000 items
WARNING - Stripped created_at from input (auto-managed field)
DEBUG - Workflow completed in 1.2s
```

### Production Benefits

1. **Signal-to-Noise Ratio**: Logs contain only actionable warnings and errors
2. **Reduced Log Volume**: 80-90% reduction in log messages at WARNING level
3. **Cost Savings**: Lower log ingestion costs in cloud environments
4. **Faster Incident Response**: Warnings stand out clearly
5. **Preserved Diagnostics**: Full debug info available when needed

### Accessing Debug Logs

When you need operational details:

```python
from dataflow import DataFlow

# Enable debug logging for troubleshooting
db = DataFlow(url, log_level="DEBUG")

# Or temporarily
from dataflow.utils.suppress_warnings import dataflow_logging_context
import logging

with dataflow_logging_context(level=logging.DEBUG):
    # Detailed logs here
    db.execute(workflow)
```

## Environment Variables Reference

Complete reference for `DATAFLOW_LOG_*` environment variables.

### DATAFLOW_LOG_LEVEL

Sets the global log level for all DataFlow loggers.

**Values**: DEBUG, INFO, WARNING, ERROR, CRITICAL (case insensitive)
**Default**: WARNING
**Example**:

```bash
export DATAFLOW_LOG_LEVEL=DEBUG
export DATAFLOW_LOG_LEVEL=warning
export DATAFLOW_LOG_LEVEL=ERROR
```

### DATAFLOW_LOG_FORMAT

Sets the log format string (standard Python logging format).

**Default**: `"%(asctime)s - %(name)s - %(levelname)s - %(message)s"`
**Example**:

```bash
# Simple format
export DATAFLOW_LOG_FORMAT="%(levelname)s - %(message)s"

# JSON-like format
export DATAFLOW_LOG_FORMAT='{"time":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}'

# Include function name
export DATAFLOW_LOG_FORMAT="%(asctime)s [%(funcName)s] %(levelname)s: %(message)s"
```

### DATAFLOW_LOG_MASK_SENSITIVE

Enable or disable sensitive value masking.

**Values**: true, false, yes, no, 1, 0, on, off (case insensitive)
**Default**: true
**Example**:

```bash
# Disable masking (for local development only!)
export DATAFLOW_LOG_MASK_SENSITIVE=false

# Enable masking (production default)
export DATAFLOW_LOG_MASK_SENSITIVE=true
```

**Warning**: Disabling masking in production risks credential exposure.

### DATAFLOW_LOG_MASK_PATTERNS

Add custom regex patterns for sensitive data matching (comma-separated).

**Default**: Empty (uses 17 built-in patterns)
**Format**: Comma-separated regex patterns
**Example**:

```bash
# Single custom pattern
export DATAFLOW_LOG_MASK_PATTERNS="x-api-token:\s*([^\s,;]+)"

# Multiple custom patterns
export DATAFLOW_LOG_MASK_PATTERNS="x-api-token:\s*([^\s,;]+),session_id=([A-Fa-f0-9]+),custom_secret=([^\s]+)"

# Complex pattern with escaped characters
export DATAFLOW_LOG_MASK_PATTERNS="oauth_token=([^\s&;\"']+)"
```

**Pattern Requirements**:

- Must be valid Python regex
- Use capture groups `(...)` to preserve context
- Avoid over-broad patterns that match non-sensitive data
- Test patterns before deploying

### DATAFLOW_LOG_MASK_REPLACEMENT

Sets the replacement string for masked values.

**Default**: `"***MASKED***"`
**Example**:

```bash
export DATAFLOW_LOG_MASK_REPLACEMENT="[REDACTED]"
export DATAFLOW_LOG_MASK_REPLACEMENT="<sensitive>"
export DATAFLOW_LOG_MASK_REPLACEMENT="XXX"
```

### Complete Environment Setup

Production-ready environment configuration:

```bash
# .env file for production
DATAFLOW_LOG_LEVEL=WARNING
DATAFLOW_LOG_MASK_SENSITIVE=true
DATAFLOW_LOG_MASK_PATTERNS=x-api-token:\s*([^\s,;]+),session_id=([A-Fa-f0-9]+)
DATAFLOW_LOG_FORMAT="%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Database connection (password will be masked in logs)
DATABASE_URL=postgresql://user:secret@localhost/mydb
```

```bash
# .env file for development
DATAFLOW_LOG_LEVEL=DEBUG
DATAFLOW_LOG_MASK_SENSITIVE=true  # Keep masking even in dev
DATAFLOW_LOG_FORMAT="%(levelname)s - %(message)s"
```

## Quick Start Examples

Practical examples for common logging scenarios.

### Basic: Simple Level Control

Just set the log level for quick debugging:

```python
from dataflow import DataFlow
import logging

# Production: WARNING only (default)
db = DataFlow("postgresql://user:pass@localhost/mydb")

# Development: See all operations
db = DataFlow(url, log_level="DEBUG")

# Quiet: Errors only
db = DataFlow(url, log_level="ERROR")

# Use logging constants
db = DataFlow(url, log_level=logging.INFO)
```

### Intermediate: Config Presets

Use presets for common scenarios:

```python
from dataflow import DataFlow
from dataflow.core.logging_config import LoggingConfig

# Production preset (WARNING, masking enabled)
db = DataFlow(
    "postgresql://user:pass@localhost/mydb",
    log_config=LoggingConfig.production()
)

# Development preset (DEBUG, masking enabled)
db = DataFlow(url, log_config=LoggingConfig.development())

# Quiet preset (ERROR only)
db = DataFlow(url, log_config=LoggingConfig.quiet())
```

### Advanced: Custom Patterns

Add application-specific sensitive patterns:

```python
from dataflow import DataFlow
from dataflow.core.logging_config import LoggingConfig, DEFAULT_SENSITIVE_PATTERNS

# Create config with custom patterns
custom_patterns = DEFAULT_SENSITIVE_PATTERNS.copy()
custom_patterns.extend([
    r"x-api-token:\s*([^\s,;]+)",        # Custom API header
    r"session_id=([A-Fa-f0-9]{32})",     # Session tokens
    r"client_secret=([^\s&;]+)",         # OAuth secrets
    r"STRIPE_KEY_[A-Z0-9]+",             # Stripe keys
])

config = LoggingConfig(
    level="INFO",
    mask_patterns=custom_patterns,
    mask_replacement="[REDACTED]",       # Custom mask string
)

db = DataFlow("postgresql://user:pass@localhost/mydb", log_config=config)

# Now all patterns are active
logger = logging.getLogger("dataflow")
logger.info("Using x-api-token: abc123")  # Logs: Using x-api-token: [REDACTED]
```

### Advanced: Context Manager

Temporarily change logging for specific operations:

```python
from dataflow import DataFlow
from dataflow.utils.suppress_warnings import dataflow_logging_context
import logging

# Initialize with WARNING level
db = DataFlow("postgresql://user:pass@localhost/mydb")

# Normal operations (WARNING level)
db.execute(normal_workflow)

# Enable debug logging temporarily
with dataflow_logging_context(level=logging.DEBUG):
    # Detailed logs for this operation only
    db.execute(problematic_workflow)

# Back to WARNING level
db.execute(another_workflow)
```

### Advanced: Per-Category Levels

Control logging granularity by category:

```python
from dataflow import DataFlow
from dataflow.core.config import LoggingConfig
import logging

# Debug only node execution, warn everything else
config = LoggingConfig(
    level=logging.WARNING,              # Default for all
    node_execution=logging.DEBUG,       # Override for nodes
    migration=logging.ERROR,            # Suppress migration logs
)

db = DataFlow("postgresql://user:pass@localhost/mydb", log_config=config)

# You'll see:
# - Node execution in detail (DEBUG)
# - Core engine warnings only (WARNING)
# - Migration errors only (ERROR)
```

### Production: Environment-Based Config

Use environment variables for 12-factor app compliance:

```python
# .env file
# DATAFLOW_LOG_LEVEL=WARNING
# DATAFLOW_LOG_MASK_SENSITIVE=true
# DATAFLOW_LOG_MASK_PATTERNS=x-api-token:\s*([^\s,;]+)

from dataflow import DataFlow
from dataflow.core.logging_config import LoggingConfig
from dotenv import load_dotenv
import os

# Load environment
load_dotenv()

# Config from environment
config = LoggingConfig.from_env()

# Add runtime patterns
config.mask_patterns.append(r"session_id=([A-Fa-f0-9]+)")

# Initialize DataFlow
db = DataFlow(os.environ["DATABASE_URL"], log_config=config)

# All configuration is now externalized
```

### Testing: Custom Logger Setup

Get DataFlow logger for application code:

```python
from dataflow.utils.suppress_warnings import get_dataflow_logger

# Get properly namespaced logger
logger = get_dataflow_logger("my_module")
# Returns: logging.getLogger("dataflow.my_module")

# Use in application code
logger.debug("Operation started")
logger.info("Processing 1000 items")
logger.warning("Suspicious input detected")
logger.error("Failed to process item", exc_info=True)

# Logger inherits DataFlow logging config
# (level, masking, handlers, etc.)
```

### Advanced: Manual Configuration

Configure logging without DataFlow initialization:

```python
from dataflow.utils.suppress_warnings import configure_dataflow_logging
from dataflow.core.logging_config import LoggingConfig
import logging

# Configure early in application startup
configure_dataflow_logging(
    config=LoggingConfig(
        level=logging.DEBUG,
        mask_sensitive=True,
    )
)

# All DataFlow loggers now configured
logger = logging.getLogger("dataflow.core.engine")
logger.debug("This will be logged and masked")

# Later, restore original state
from dataflow.utils.suppress_warnings import restore_dataflow_logging
restore_dataflow_logging()
```

## Summary

Phase 7's centralized logging configuration provides:

1. **Production Safety**: WARNING default level keeps logs clean; masking protects credentials
2. **Flexibility**: Environment variables, presets, and custom configs support any deployment
3. **Security**: 17 default patterns plus custom pattern support mask sensitive data automatically
4. **Diagnostics**: DEBUG level and category-specific logging enable detailed troubleshooting
5. **Integration**: Seamless integration with DataFlow initialization and context managers

**Key Takeaways**:

- Use `log_level="WARNING"` for production (default)
- Enable DEBUG only for troubleshooting
- Trust default masking patterns (17 production-ready patterns)
- Add custom patterns for application-specific secrets
- Use environment variables for containerized deployments
- Leverage context managers for temporary logging changes

**Next Steps**:

- Review default sensitive patterns: `DEFAULT_SENSITIVE_PATTERNS`
- Add custom patterns for your application
- Configure environment variables for production
- Test masking with real log messages
- Use category-specific levels for fine-grained control
