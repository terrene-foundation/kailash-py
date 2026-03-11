"""
CARE-040: Adversarial Security Tests for Trust Framework.

This package contains security-focused adversarial tests that attempt to:
- Extract private key material from trust components
- Manipulate delegation chains to escalate privileges
- Bypass security controls in the trust framework

These tests verify that the trust framework is resistant to common
attack patterns and that sensitive data is properly protected.

Test modules:
- test_key_extraction.py: Tests that attempt to extract private keys
- test_delegation_manipulation.py: Tests that attempt to manipulate delegation chains
"""
