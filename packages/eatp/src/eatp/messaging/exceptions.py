# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Messaging Module Exceptions.

Custom exceptions for secure messaging operations.
"""

from typing import Optional


class MessagingError(Exception):
    """Base exception for messaging errors."""

    def __init__(self, message: str, cause: Optional[Exception] = None):
        super().__init__(message)
        self.cause = cause


class SigningError(MessagingError):
    """Raised when message signing fails."""

    def __init__(
        self,
        agent_id: str,
        reason: str,
        cause: Optional[Exception] = None,
    ):
        super().__init__(f"Failed to sign message for agent {agent_id}: {reason}", cause)
        self.agent_id = agent_id
        self.reason = reason


class VerificationError(MessagingError):
    """Raised when message verification fails critically."""

    def __init__(
        self,
        message_id: str,
        reason: str,
        cause: Optional[Exception] = None,
    ):
        super().__init__(f"Message verification failed for {message_id}: {reason}", cause)
        self.message_id = message_id
        self.reason = reason


class ReplayDetectedError(MessagingError):
    """Raised when a message replay attack is detected."""

    def __init__(
        self,
        message_id: str,
        nonce: str,
    ):
        super().__init__(f"Replay attack detected: message {message_id} with nonce {nonce[:16]}...")
        self.message_id = message_id
        self.nonce = nonce


class MessageExpiredError(MessagingError):
    """Raised when a message has expired."""

    def __init__(
        self,
        message_id: str,
        expired_at: str,
    ):
        super().__init__(f"Message {message_id} expired at {expired_at}")
        self.message_id = message_id
        self.expired_at = expired_at


class PublicKeyNotFoundError(MessagingError):
    """Raised when a sender's public key cannot be found."""

    def __init__(
        self,
        agent_id: str,
    ):
        super().__init__(f"Public key not found for agent {agent_id}")
        self.agent_id = agent_id


class ChannelError(MessagingError):
    """Raised when a channel operation fails."""

    def __init__(
        self,
        operation: str,
        reason: str,
        cause: Optional[Exception] = None,
    ):
        super().__init__(f"Channel operation '{operation}' failed: {reason}", cause)
        self.operation = operation
        self.reason = reason
