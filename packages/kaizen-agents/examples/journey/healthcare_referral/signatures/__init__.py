"""
Healthcare Referral Signatures

Type-safe I/O contracts for each pathway in the healthcare referral journey.
Each signature defines the expected inputs, outputs, intent, and guidelines.
"""

from examples.journey.healthcare_referral.signatures.booking import BookingSignature
from examples.journey.healthcare_referral.signatures.confirmation import (
    ConfirmationSignature,
)
from examples.journey.healthcare_referral.signatures.faq import FAQSignature
from examples.journey.healthcare_referral.signatures.intake import IntakeSignature
from examples.journey.healthcare_referral.signatures.persuasion import (
    PersuasionSignature,
)

__all__ = [
    "IntakeSignature",
    "BookingSignature",
    "FAQSignature",
    "PersuasionSignature",
    "ConfirmationSignature",
]
