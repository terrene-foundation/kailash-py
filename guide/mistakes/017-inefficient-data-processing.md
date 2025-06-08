# Mistake #017: Inefficient Data Processing

## Problem
Processing large datasets in memory without streaming.

### Bad Example
```python
# BAD - Load entire dataset
def process_large_file(file_path):
    data = pd.read_csv(file_path)  # Loads all data
    return data.process()

# GOOD - Streaming processing
def process_large_file(file_path):
    for chunk in pd.read_csv(file_path, chunksize=1000):
        yield chunk.process()

```

## Solution


## Lesson Learned
Always consider memory usage for large data processing.

---
