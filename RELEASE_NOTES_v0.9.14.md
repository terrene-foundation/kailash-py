# Kailash Core SDK v0.9.14 Release Notes

## 🐛 Bug Fixes

### Code Quality & Formatting
- **Fixed**: Applied black code formatting to resolve CI formatting failures
- **Fixed**: Resolved quote style inconsistencies and trailing whitespace issues
- **Impact**: Ensures consistent code formatting across the entire codebase
- **File**: `src/kailash/workflow/validation.py`

## 📈 Improvements

### Updated Dependencies
- **Updated**: DataFlow dependency from `>=0.3.1` to `>=0.4.6` 
- **Updated**: Nexus dependency from `>=1.0.3` to `>=1.0.6`
- **Benefit**: Users can now access latest enterprise-grade DataFlow migration features

### Enterprise DataFlow Integration
This release ensures compatibility with DataFlow v0.4.6, which includes:
- 8 Enterprise Migration Engines
- 350+ tests with 100% success rate
- NOT NULL column addition with 6 default value strategies
- Advanced column removal with dependency analysis
- FK-aware operations with referential integrity protection

## 🔧 Technical Details

- Enhanced CI compatibility by fixing formatting issues
- No breaking changes - fully backward compatible
- Updated dependency specifications for better integration with latest framework versions
- Maintains all existing API contracts and functionality

## 📦 Installation

```bash
# Core SDK only
pip install kailash==0.9.14

# With DataFlow (recommended for database applications)
pip install kailash[dataflow]==0.9.14

# With Nexus (recommended for multi-channel platforms)
pip install kailash[nexus]==0.9.14

# All framework components
pip install kailash[all]==0.9.14
```

## 🔗 Related Releases

- **DataFlow v0.4.6**: Released with enterprise migration capabilities
- **Nexus v1.0.6**: Current stable release with multi-channel support

## 🤝 Contributors

- Fixed code formatting for improved CI stability
- Updated dependency specifications for better framework integration
- Maintained 100% backward compatibility

---

*This release focuses on code quality improvements and ensures compatibility with the latest DataFlow enterprise features.*