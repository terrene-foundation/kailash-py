"""Compatibility shim -- re-exports from eatp.

This module re-exports all public names from the EATP SDK.
Import directly from ``eatp.messaging.envelope`` for new code.
"""
from eatp.messaging.envelope import *  # noqa: F401,F403
