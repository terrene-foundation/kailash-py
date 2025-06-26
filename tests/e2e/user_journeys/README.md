# E2E User Journey Tests

This directory contains end-to-end tests that simulate complete user journeys through the system.

## Journey Categories

### Developer Journeys
- Creating and deploying workflows
- Debugging and monitoring workflows
- Performance optimization flows
- Integration with external systems

### Data Analyst Journeys
- Building data pipelines
- Creating reports and dashboards
- Running ad-hoc analyses
- Scheduling automated jobs

### System Administrator Journeys
- User and role management
- System configuration
- Security policy implementation
- Audit and compliance workflows

### Business User Journeys
- Running pre-built workflows
- Viewing results and reports
- Requesting data access
- Collaborating on analyses

## Test Requirements

Each journey test should:
1. Represent a realistic user scenario
2. Include multiple workflow steps
3. Use actual UI/API interactions where applicable
4. Validate user-visible outcomes
5. Test error handling from user perspective

## Running Journey Tests

```bash
# All user journeys
pytest tests/e2e/user_journeys/ -m e2e

# Specific user type
pytest tests/e2e/user_journeys/ -k "developer"
pytest tests/e2e/user_journeys/ -k "analyst"
pytest tests/e2e/user_journeys/ -k "admin"
```
