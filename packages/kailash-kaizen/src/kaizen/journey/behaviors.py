"""
Journey Return Behaviors

Defines return behaviors for pathway navigation, enabling patterns like:
- ReturnToPrevious: Detour pathways (e.g., FAQ) that return to the previous pathway
- ReturnToSpecific: Explicit return to a named pathway

These behaviors control how the PathwayManager navigates after pathway completion.

Usage:
    class FAQPath(Pathway):
        __signature__ = FAQSignature
        __agents__ = ["faq_agent"]
        __return_behavior__ = ReturnToPrevious()  # Return to where user came from

    class PaymentPath(Pathway):
        __signature__ = PaymentSignature
        __agents__ = ["payment_agent"]
        __return_behavior__ = ReturnToSpecific(target_pathway="confirmation")
"""

from dataclasses import dataclass


@dataclass
class ReturnBehavior:
    """
    Base class for pathway return behaviors.

    Return behaviors define how the PathwayManager navigates after a pathway
    completes. They enable non-linear journey flows like detours and redirects.

    Subclasses:
        - ReturnToPrevious: Return to the pathway that triggered this one
        - ReturnToSpecific: Return to an explicitly named pathway
    """

    pass


@dataclass
class ReturnToPrevious(ReturnBehavior):
    """
    Return to the previous pathway after completion.

    Used for detour pathways like FAQ, help, or confirmation screens that
    should return the user to wherever they were before.

    Attributes:
        preserve_context: Whether to preserve accumulated context when returning.
                         Default True to maintain state across the detour.
        max_depth: Maximum detour depth to prevent infinite recursion.
                   Default 5 allows reasonable nesting while preventing loops.

    Example:
        class FAQPath(Pathway):
            \"\"\"Help pathway that returns to previous context.\"\"\"
            __signature__ = FAQSignature
            __agents__ = ["faq_agent"]
            __return_behavior__ = ReturnToPrevious(
                preserve_context=True,
                max_depth=3
            )

        # User flow:
        # 1. User is in BookingPath
        # 2. User triggers FAQ intent
        # 3. System navigates to FAQPath
        # 4. FAQPath completes
        # 5. System returns to BookingPath (preserved context)
    """

    preserve_context: bool = True
    max_depth: int = 5


@dataclass
class ReturnToSpecific(ReturnBehavior):
    """
    Return to a specific named pathway after completion.

    Used when a pathway should always navigate to a particular next pathway,
    regardless of where the user came from. Useful for workflows with
    mandatory confirmation or summary steps.

    Attributes:
        target_pathway: ID of the pathway to navigate to after completion.
                       Must be a valid pathway ID in the journey.
        preserve_context: Whether to preserve accumulated context when returning.
                         Default True to maintain state.

    Example:
        class PaymentPath(Pathway):
            \"\"\"Payment processing that always goes to confirmation.\"\"\"
            __signature__ = PaymentSignature
            __agents__ = ["payment_agent"]
            __return_behavior__ = ReturnToSpecific(
                target_pathway="confirmation",
                preserve_context=True
            )

        # User flow:
        # 1. User completes payment in PaymentPath
        # 2. System always navigates to ConfirmationPath
        # 3. Regardless of how user reached PaymentPath
    """

    target_pathway: str = ""
    preserve_context: bool = True


__all__ = [
    "ReturnBehavior",
    "ReturnToPrevious",
    "ReturnToSpecific",
]
