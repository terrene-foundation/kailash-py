# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Proxy module: kaizen.agents.multi_modal.transcription_agent

Re-exports from kaizen_agents.agents.multi_modal.transcription_agent
so that mock.patch targets resolve correctly.
"""

from kaizen_agents.agents.multi_modal.transcription_agent import *  # noqa: F401, F403
from kaizen_agents.agents.multi_modal.transcription_agent import (
    TranscriptionAgent,
    TranscriptionSignature,
)

# Re-import WhisperProcessor so patch("kaizen.agents.multi_modal.transcription_agent.WhisperProcessor") works
from kaizen.audio.whisper_processor import WhisperProcessor  # noqa: F401
