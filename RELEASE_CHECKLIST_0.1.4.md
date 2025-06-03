# Release Checklist for v0.1.4

## Pre-release Checks ✅

- [x] All tests passing (753/753)
- [x] All examples working (46/46)
- [x] Documentation builds without errors
- [x] Code formatting (black, isort, ruff) complete
- [x] Version updated in:
  - [x] pyproject.toml (0.1.4)
  - [x] setup.py (0.1.4)
  - [x] src/kailash/__init__.py (0.1.4)
- [x] CHANGELOG.md updated with v0.1.4 entry
- [x] Release notes created (RELEASE_NOTES_0.1.4.md)
- [x] README badges updated (753 tests)

## Breaking Changes Notice 🚨

This release contains **breaking changes**:
- All node classes renamed to end with "Node" suffix
- Users must update their imports and class references
- Migration guide available in ADR-0020

## Release Steps 📦

1. **Final Testing**
   ```bash
   # Run all tests one more time
   pytest
   
   # Run all examples
   cd examples && python _utils/test_all_examples.py
   
   # Build documentation
   cd docs && python build_docs.py
   ```

2. **Git Operations**
   ```bash
   # Add all changes
   git add -A
   
   # Commit with descriptive message
   git commit -m "Release v0.1.4: Node naming convention standardization"
   
   # Create annotated tag
   git tag -a v0.1.4 -m "Release v0.1.4: Node naming convention standardization"
   
   # Push to repository
   git push origin main
   git push origin v0.1.4
   ```

3. **PyPI Release**
   ```bash
   # Clean previous builds
   rm -rf dist/ build/ *.egg-info
   
   # Build distribution
   python -m build
   
   # Upload to PyPI (test first)
   python -m twine upload --repository testpypi dist/*
   
   # If test is successful, upload to PyPI
   python -m twine upload dist/*
   ```

4. **GitHub Release**
   - Go to https://github.com/terrene-foundation/kailash-py/releases
   - Click "Create a new release"
   - Choose tag: v0.1.4
   - Title: "v0.1.4 - Node Naming Convention Standardization"
   - Copy content from RELEASE_NOTES_0.1.4.md
   - Attach distribution files from dist/
   - Mark as pre-release if appropriate
   - Publish release

5. **Post-release**
   - Verify installation: `pip install kailash==0.1.4`
   - Test basic functionality with new version
   - Update any external documentation
   - Notify users about breaking changes

## Communication Template 📢

### Announcement Message
```
🚀 Kailash Python SDK v0.1.4 Released!

⚠️ BREAKING CHANGES: All node classes now end with "Node" suffix for consistency.

Key changes:
• CSVReader → CSVReaderNode
• JSONWriter → JSONWriterNode  
• Switch → SwitchNode
• And more...

✨ Also includes:
• Doctest-formatted examples
• 753 tests passing
• Improved documentation

📚 Migration guide: https://github.com/terrene-foundation/kailash-py/blob/main/guide/adr/0020-node-naming-convention.md

📦 Install: pip install kailash==0.1.4
```

## Rollback Plan 🔄

If issues are discovered:
1. `pip install kailash==0.1.3` to revert users
2. Fix issues in a patch release (0.1.4.1)
3. Or prepare 0.1.5 with fixes

## Notes
- This is a breaking change release
- Emphasize migration guide in all communications
- Consider deprecation warnings in future for smoother transitions