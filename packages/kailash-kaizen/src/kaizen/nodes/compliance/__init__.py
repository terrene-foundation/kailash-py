"""
Kaizen Compliance Nodes

AI-enhanced compliance nodes for GDPR, CCPA, and other regulatory frameworks.

This module provides AI-powered compliance nodes that extend Core SDK's
rule-based compliance checking with intelligent analysis and recommendations.

For rule-based compliance only, use the Core SDK versions:
    from kailash.nodes.compliance import GDPRComplianceNode
"""

from .gdpr import GDPRComplianceNode

__all__ = ["GDPRComplianceNode"]
