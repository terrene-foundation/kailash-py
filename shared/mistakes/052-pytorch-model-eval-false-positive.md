# Mistake #052: PyTorch model.eval() False Positive

## Problem
Linting tools flagged `model.eval()` as dangerous eval() usage.

### Bad Example
```python
# This is NOT the Python eval() function!
model_obj.eval()  # PyTorch method to set model to evaluation mode

```

## Solution
Exclude file from eval() checks or add noqa comment.
**Learning**: Understand context before applying linting rules blindly.

---
