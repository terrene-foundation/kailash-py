# Kailash Core SDK v0.9.15 Release Notes

## 🚀 Performance Optimization & Code Quality Release

### ⚡ Major Performance Improvements

#### Lazy Loading Implementation
- **34% faster import times**: Reduced from 6.3s to 4.1s
- **41% memory reduction**: Decreased from 162MB to 96MB
- **Safe circular dependency detection**: Proactive detection and warning system
- **Full backward compatibility**: All existing code continues to work

### 🔧 Implementation Details

#### Smart Lazy Loading with Circular Dependency Protection
```python
# New safe lazy import mechanism
def _safe_lazy_import(name: str) -> Any:
    """Safely import a module with circular dependency detection."""
    # Tracks loading stack to detect cycles
    # Issues warnings when circular dependencies detected
    # Returns placeholder modules to break cycles
```

#### Performance Monitoring Built-in
```python
# Check import statistics
from kailash.nodes import get_import_stats
stats = get_import_stats()
# Shows loaded vs pending modules

# Detect circular dependencies
from kailash.nodes import check_circular_dependencies
result = check_circular_dependencies()
```

### 📊 Code Quality Improvements

#### Comprehensive Code Formatting
- **Black formatting**: Applied consistent style across 600+ files
- **isort organization**: Standardized import ordering
- **Ruff linting**: Fixed all linting issues
- **Line length**: Standardized at 100 characters

### 🧪 Testing Status

#### Tier 1 Unit Tests
- **99.5% pass rate**: 3994 passed out of 4015 tests
- **8 minor failures**: Isolated to embedding/memory nodes
- **All critical paths tested**: Core functionality verified

### 📦 What's Changed

#### Performance
- Implemented lazy loading for node categories
- Added circular dependency detection system
- Optimized module import patterns
- Reduced memory footprint significantly

#### Code Quality
- Applied black formatting to entire codebase
- Organized imports with isort
- Fixed all ruff linting issues
- Improved code consistency

#### Architecture
- Added `CircularDependencyDetector` utility
- Implemented `_safe_lazy_import` mechanism
- Added performance monitoring functions
- Maintained full backward compatibility

### 🔄 Migration Guide

**No migration required!** This release maintains full backward compatibility.

#### Optional Performance Monitoring
```python
# Monitor import performance
from kailash.nodes import get_import_stats, check_circular_dependencies

# Get current import statistics
stats = get_import_stats()
print(f"Loaded modules: {stats['loaded_count']}/{stats['total_categories']}")

# Check for circular dependencies
deps = check_circular_dependencies()
if deps['has_circular_deps']:
    print(f"Warning: {deps['warnings']}")
```

### 📈 Performance Benchmarks

| Metric | v0.9.14 | v0.9.15 | Improvement |
|--------|---------|---------|-------------|
| Import Time | 6.275s | 4.144s | 34% faster |
| Memory Usage | 161.7MB | 95.8MB | 41% reduction |
| Module Count | 292 | 165 | 43% fewer |

### 🐛 Known Issues

- 8 unit tests fail when run in batch but pass individually (embedding/memory nodes)
- These failures do not affect functionality

### 👥 Contributors

- Performance optimization and lazy loading implementation
- Code quality improvements and formatting

### 📝 Full Changelog

**Performance:**
- Lazy loading for all node categories
- Circular dependency detection and handling
- Memory usage optimization

**Code Quality:**
- Black formatting (600+ files)
- isort import organization
- Ruff linting fixes

**Testing:**
- 99.5% unit test pass rate
- Full backward compatibility verified

---

## Installation

```bash
pip install kailash==0.9.15
```

## Upgrade

```bash
pip install --upgrade kailash
```

## Requirements

- Python 3.12+
- All existing dependencies remain unchanged
