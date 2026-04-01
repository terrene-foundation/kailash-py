# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for exception hierarchy."""
from __future__ import annotations

from kailash_align.exceptions import (
    AdapterNotFoundError,
    AlignmentError,
    CacheNotFoundError,
    EvaluationError,
    GGUFConversionError,
    MergeError,
    OllamaNotAvailableError,
    ServingError,
    TrainingError,
)


class TestExceptionHierarchy:
    def test_all_inherit_from_alignment_error(self):
        """Every custom exception must inherit from AlignmentError."""
        exceptions = [
            AdapterNotFoundError,
            TrainingError,
            ServingError,
            GGUFConversionError,
            OllamaNotAvailableError,
            EvaluationError,
            CacheNotFoundError,
            MergeError,
        ]
        for exc_class in exceptions:
            assert issubclass(
                exc_class, AlignmentError
            ), f"{exc_class.__name__} does not inherit from AlignmentError"

    def test_serving_subtypes(self):
        """GGUFConversionError and OllamaNotAvailableError are ServingErrors."""
        assert issubclass(GGUFConversionError, ServingError)
        assert issubclass(OllamaNotAvailableError, ServingError)

    def test_alignment_error_is_exception(self):
        assert issubclass(AlignmentError, Exception)

    def test_can_raise_and_catch(self):
        with __import__("pytest").raises(AlignmentError):
            raise AdapterNotFoundError("adapter xyz not found")

    def test_message_preserved(self):
        exc = TrainingError("loss diverged")
        assert str(exc) == "loss diverged"
