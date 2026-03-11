"""
Learning mechanisms for Kaizen memory system.

Provides pattern recognition, preference learning, memory promotion,
and error correction to enable the memory system to learn and adapt over time.
"""

from .error_correction import ErrorCorrectionLearner
from .memory_promotion import MemoryPromoter
from .pattern_recognition import PatternRecognizer
from .preference_learning import PreferenceLearner

__all__ = [
    "PatternRecognizer",
    "PreferenceLearner",
    "MemoryPromoter",
    "ErrorCorrectionLearner",
]
