# Mistake 069: NumPy Version Compatibility Issues

## Problem
PythonCodeNode fails with AttributeError when using NumPy types that don't exist on all platforms or were removed in NumPy 2.0.

## Example Errors
```python
# Platform-specific type error:
AttributeError: module 'numpy' has no attribute 'float128'

# NumPy 2.0 removal:
AttributeError: `np.string_` was removed in the NumPy 2.0 release. Use `np.bytes_` instead.

# Deprecated in NumPy:
AttributeError: module 'numpy' has no attribute 'matrix'
```

## Root Cause
1. **Platform differences**: Some NumPy types (float128, complex256) only exist on certain platforms
2. **NumPy 2.0 breaking changes**: Removed np.string_, np.unicode_, and others
3. **Deprecations**: np.matrix was deprecated and removed in favor of ndarray
4. **Hard-coded type lists**: Security module and node implementations assumed all types exist

## Solution
Always check for type availability before using:

```python
# In security.py or type checking code:
import numpy as np

numpy_types = [
    np.ndarray,
    np.int8, np.int16, np.int32, np.int64,
    np.float16, np.float32, np.float64,
    np.complex64, np.complex128,
    np.bool_, np.object_,
    np.datetime64, np.timedelta64
]

# Platform-specific types
if hasattr(np, 'float128'):
    numpy_types.append(np.float128)
if hasattr(np, 'complex256'):
    numpy_types.append(np.complex256)

# Version-specific handling
if hasattr(np, 'string_'):
    numpy_types.append(np.string_)
elif hasattr(np, 'bytes_'):
    numpy_types.append(np.bytes_)

if hasattr(np, 'unicode_'):
    numpy_types.append(np.unicode_)
elif hasattr(np, 'str_'):
    numpy_types.append(np.str_)

# Deprecated types
if hasattr(np, 'matrix'):
    numpy_types.append(np.matrix)
```

## NumPy 2.0 Migration Guide

### String Types
```python
# NumPy 1.x
arr = np.array(['hello'], dtype=np.string_)    # ❌ Removed
arr = np.array(['hello'], dtype=np.unicode_)   # ❌ Removed

# NumPy 2.0+
arr = np.array(['hello'], dtype=np.bytes_)     # ✓ For byte strings
arr = np.array(['hello'], dtype=np.str_)       # ✓ For unicode strings
arr = np.array(['hello'], dtype='S10')         # ✓ Fixed-length byte string
arr = np.array(['hello'], dtype='U10')         # ✓ Fixed-length unicode
```

### Matrix vs Array
```python
# NumPy 1.x (deprecated)
m = np.matrix([[1, 2], [3, 4]])    # ❌ Removed
result = m * m                      # Matrix multiplication

# NumPy 2.0+
m = np.array([[1, 2], [3, 4]])     # ✓ Use ndarray
result = m @ m                      # ✓ Matrix multiplication with @
result = np.dot(m, m)               # ✓ Or use dot()
```

### Generic Type Checking
```python
# Instead of checking specific types, use generic
if hasattr(np, 'generic'):
    # This catches all NumPy scalar types
    if isinstance(value, np.generic):
        return True
```

## Platform-Specific Types

### Float128 (Long Double)
```python
# Only available on some platforms (Linux x86_64, etc.)
# Not available on: Windows, macOS ARM64

# Safe usage:
if hasattr(np, 'float128'):
    high_precision_type = np.float128
else:
    high_precision_type = np.float64  # Fallback
```

### Complex256
```python
# Also platform-specific
if hasattr(np, 'complex256'):
    complex_types = [np.complex64, np.complex128, np.complex256]
else:
    complex_types = [np.complex64, np.complex128]
```

## Best Practices

### 1. Version Detection
```python
import numpy as np

numpy_version = tuple(map(int, np.__version__.split('.')[:2]))
if numpy_version >= (2, 0):
    # NumPy 2.0+ specific code
    string_type = np.bytes_
else:
    # NumPy 1.x code
    string_type = np.string_
```

### 2. Defensive Type Checking
```python
# In PythonCodeNode or security checks
def is_numpy_type(value):
    """Check if value is any NumPy type safely."""
    try:
        import numpy as np
        # Use generic check first
        if hasattr(np, 'generic') and isinstance(value, np.generic):
            return True
        # Check for ndarray
        if isinstance(value, np.ndarray):
            return True
        # Check for masked arrays
        if hasattr(np, 'ma') and isinstance(value, np.ma.MaskedArray):
            return True
    except ImportError:
        pass
    return False
```

### 3. Type Conversion Patterns
```python
# Convert platform-specific types to portable ones
def make_portable(arr):
    """Convert array to portable types."""
    if arr.dtype.name == 'float128':
        return arr.astype(np.float64)
    elif arr.dtype.name == 'complex256':
        return arr.astype(np.complex128)
    return arr
```

## Prevention
1. Always use `hasattr()` checks for platform-specific types
2. Test on multiple platforms (Linux, macOS, Windows)
3. Pin NumPy version in requirements if using deprecated features
4. Use generic type checks when possible
5. Document platform requirements if using extended precision

## Related
- [052-pytorch-model-eval-false-positive.md](052-pytorch-model-eval-false-positive.md) - Similar platform issues
- [068-pythoncode-dataframe-serialization.md](068-pythoncode-dataframe-serialization.md) - Serialization of NumPy arrays
- Security module's type checking implementation
