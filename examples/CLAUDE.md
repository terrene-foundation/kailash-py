# KailashSDK - Workflow and Test Structure

# 📂Differences between examples, workflows, and tests - What goes where?
**Single source** for all business-value workflows

**Production Workflows** (`sdk-users/workflows/`):
- **Single source** for all business-value workflows
- **by-industry/** - Finance, healthcare, manufacturing, professional services
- **by-pattern/** - Data processing, AI/ML, API integration, file processing, security
- **quickstart/** - 5-minute success stories (planned)
- **integrations/** - Third-party platform connections (planned)
- **production-ready/** - Enterprise deployment patterns (planned)

**SDK Development** (`examples/`):
- Feature Validation and development testing only
- **feature_examples/** - SDK component testing (folders end with `_examples`)
- **utils/** - Development utilities and shared tools
- **test-harness/** - Testing infrastructure

**Quality Validation** (`tests/`):
- **unit/** - Fast, isolated component tests
- **integration/** - Component interaction tests
- **e2e/** - End-to-end scenario tests
