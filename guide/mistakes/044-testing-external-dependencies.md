# Mistake #044: Testing External Dependencies

## Problem
Tests failing due to external service dependencies.

### Bad Example
```python
# BAD - Depends on external service
def test_api_integration():
    response = requests.get("https://external-api.com/data")
    assert response.status_code == 200

# GOOD - Mock external dependencies
@patch('requests.get')
def test_api_integration(mock_get):
    mock_get.return_value.status_code = 200
    response = requests.get("https://external-api.com/data")
    assert response.status_code == 200

```

## Solution


## Fixed In
API integration testing

---

## Environment & Deployment Issues

## Categories
testing

---
