# kailash-trust

EATP trust plane integration for the [Kailash platform](https://github.com/terrene-foundation/kailash-py).

This package re-exports the primary trust surface from `kailash.trust` for
consumers who prefer the standalone install path.

## Install

```bash
pip install kailash-trust
```

## Usage

```python
from kailash_trust import TrustOperations, GenesisRecord, TrustStore

# Equivalent to: from kailash.trust import TrustOperations, GenesisRecord, TrustStore
```

The complete trust plane documentation is available in the
[Kailash SDK docs](https://docs.terrene.foundation/kailash-trust).

## License

Apache 2.0 — Terrene Foundation
