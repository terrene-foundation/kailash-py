# Release v0.9.3 - Final Instructions

## ✅ Completed Steps

1. **Version Updated**: v0.9.2 → v0.9.3 in `pyproject.toml` and `src/kailash/__init__.py`
2. **Changelog Created**: `sdk-users/6-reference/changelogs/releases/v0.9.3-2025-01-30.md`
3. **Changelog README Updated**: v0.9.3 marked as current version
4. **Release Branch Created**: `release/v0.9.3` pushed to remote
5. **Distribution Built**: 
   - `dist/kailash-0.9.3-py3-none-any.whl` (1.9MB)
   - `dist/kailash-0.9.3.tar.gz` (1.7MB)
6. **Package Validation**: ✅ Passed `twine check`
7. **Installation Testing**: ✅ Works correctly in clean environment

## 🚀 Final Step: Upload to PyPI

To complete the release, run:

```bash
# Upload to PyPI (requires PyPI credentials)
python -m twine upload dist/kailash-0.9.3*

# Or upload to Test PyPI first
python -m twine upload --repository testpypi dist/kailash-0.9.3*
```

## 📋 Release Summary

**Version**: 0.9.3  
**Type**: Patch Release  
**Date**: 2025-01-30  

### Key Changes
- Fixed misleading `test_parallel_execution_with_merge` to use actual ParallelRuntime instead of LocalRuntime
- Improved test accuracy for parallel execution validation
- Enhanced documentation of parallel vs sequential execution behavior

### Files Changed
- `tests/integration/runtime/test_local_runtime_docker.py` - Fixed test to use ParallelRuntime
- Version files updated to v0.9.3
- Changelog and documentation updated

### Verification
- All TODO-128 cycle convergence work remains stable ✅
- Basic workflow execution tested ✅
- Package installation verified ✅
- Test suite compatibility confirmed ✅

## 📝 Notes

This patch release maintains full backward compatibility while improving test accuracy. The fix ensures that parallel execution tests actually demonstrate true parallel behavior rather than sequential execution with misleading names.

All existing functionality remains unchanged - this is purely an infrastructure improvement for better testing and validation of parallel execution features.