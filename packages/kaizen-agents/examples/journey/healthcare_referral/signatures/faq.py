"""
FAQ Signature - Question Answering

Answers patient questions about the healthcare referral process
while offering to return to the main flow.
"""

from typing import Any, Dict

from kaizen.signatures import InputField, OutputField, Signature


class FAQSignature(Signature):
    """
    Answer patient questions about the referral process.

    This signature is used for the FAQ detour pathway, which can be triggered
    from any other pathway when the patient has questions. After answering,
    the journey returns to the previous pathway.

    Key Features:
        - Answers questions clearly and concisely
        - Stays within scope (healthcare referral process)
        - Offers to return to the booking process when ready
        - Does not make medical recommendations

    Example:
        >>> agent = FAQAgent(config)
        >>> result = agent.run(
        ...     question="What's the difference between an orthopedist and a chiropractor?",
        ...     current_context={"symptoms": ["back pain"], "current_pathway": "booking"}
        ... )
        >>> print(result["answer"])
        "An orthopedist is a medical doctor who specializes in..."
    """

    __intent__ = (
        "Provide helpful answers to patient questions about healthcare referrals"
    )

    __guidelines__ = [
        "Answer questions clearly and concisely",
        "If the question is outside scope, politely explain limitations",
        "Offer to return to the booking process when ready",
        "Do not make specific medical recommendations - refer to specialists",
        "Use simple language, avoiding medical jargon where possible",
        "If you're unsure, say so and suggest consulting with a specialist",
        "Keep answers focused and not overly long",
    ]

    # Inputs
    question: str = InputField(
        desc="Patient's question about the referral process or healthcare"
    )
    current_context: Dict[str, Any] = InputField(
        desc="Current journey context for relevant, personalized answers"
    )

    # Outputs
    answer: str = OutputField(desc="Clear, helpful answer to the patient's question")
    question_resolved: bool = OutputField(
        desc="Whether the question has been fully answered (True) or needs follow-up (False)"
    )
    response: str = OutputField(
        desc="Full response including the answer and offer to continue with the booking process"
    )
