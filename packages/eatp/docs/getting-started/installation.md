# Installation

## Python

```bash
pip install eatp
```

### Optional Dependencies

For PostgreSQL-backed trust store:

```bash
pip install eatp[postgres]
```

### Requirements

- Python 3.11+
- PyNaCl (Ed25519 cryptography)

## Verify Installation

```python
import eatp
print(eatp.__version__)  # 0.1.0
```

## Development Installation

```bash
git clone https://github.com/terrene-foundation/eatp-python.git
cd eatp-python
pip install -e ".[dev]"
pytest
```
