# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Internal decorators for kailash-ml."""
from __future__ import annotations

import functools
import warnings
from typing import Any, TypeVar

T = TypeVar("T", bound=type)


class ExperimentalWarning(UserWarning):
    """Warning emitted when an experimental (P2) engine or agent is used.

    Experimental APIs may change or be removed in future minor versions
    without a deprecation period.
    """

    pass


_warned_classes: set[str] = set()


def experimental(cls: T) -> T:
    """Mark a class as experimental (P2 quality tier).

    Emits :class:`ExperimentalWarning` on first instantiation per class
    per interpreter session.  Subsequent instantiations of the same class
    are silent.
    """
    original_init = cls.__init__

    @functools.wraps(original_init)
    def new_init(self: Any, *args: Any, **kwargs: Any) -> None:
        class_name = cls.__name__
        if class_name not in _warned_classes:
            warnings.warn(
                f"{class_name} is experimental (P2). API may change in future versions. "
                f"Use in production at your own risk.",
                ExperimentalWarning,
                stacklevel=2,
            )
            _warned_classes.add(class_name)
        original_init(self, *args, **kwargs)

    cls.__init__ = new_init  # type: ignore[attr-defined]
    cls._quality_tier = "P2"  # type: ignore[attr-defined]
    return cls
