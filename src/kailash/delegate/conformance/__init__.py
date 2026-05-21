"""kailash.delegate.conformance -- shared conformance vectors with kailash-rs.

Per #1035 F1 invariant: this subpackage MUST have ZERO engine dependencies.
The lint at ``tools/lint-delegate-fences.py`` enforces this; vectors load
from JSON fixtures and validate via dataclass schemas only.
"""

__all__: list[str] = []
