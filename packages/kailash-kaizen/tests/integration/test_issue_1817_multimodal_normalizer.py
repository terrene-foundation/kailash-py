"""Tier-2 integration tests for issue #1817: file-path multimodal normalizer.

These tests write REAL image + audio files to disk and run them through the
AsyncSingleShotStrategy multimodal classifier / message builder end-to-end.
The vision/audio encoding primitives (encode_image / encode_audio /
validate_* / get_*_media_type) are exercised for real -- NO mocking of the
encoders (testing.md Tier 2).  The assertions verify the emitted provider
wire-block shape a real LLM call would receive.
"""

import base64

import pytest

from kaizen.strategies.async_single_shot import (
    AsyncSingleShotStrategy,
    _classify_input_value,
)


def _make_agent(input_fields):
    """Minimal duck-typed agent for _create_messages_from_inputs.

    NOT a mock of any encoder -- just a plain object carrying the signature
    input_fields the message builder reads.
    """

    class _Sig:
        pass

    class _Cfg:
        pass

    class _Agent:
        pass

    sig = _Sig()
    sig.input_fields = input_fields
    agent = _Agent()
    agent.signature = sig
    agent.config = _Cfg()  # no response_format attribute -> plain text path
    return agent


# A minimal-but-valid PNG (1x1) and a small WAV header, written to real files.
_PNG_1x1 = base64.b64decode(
    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    b"+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
_WAV_BYTES = b"RIFF" + (36).to_bytes(4, "little") + b"WAVE" b"fmt " + (16).to_bytes(
    4, "little"
) + (1).to_bytes(2, "little") + (1).to_bytes(2, "little") + (8000).to_bytes(
    4, "little"
) + (
    8000
).to_bytes(
    4, "little"
) + (
    1
).to_bytes(
    2, "little"
) + (
    8
).to_bytes(
    2, "little"
) + b"data" + (
    0
).to_bytes(
    4, "little"
)


@pytest.mark.integration
def test_real_image_file_emits_image_url_wire_block(tmp_path):
    """A real PNG on disk normalizes to a base64 image_url data-URI block."""
    img = tmp_path / "picture.png"
    img.write_bytes(_PNG_1x1)

    block = _classify_input_value({"type": "image", "path": str(img)}, "Pic", {})

    assert block["type"] == "image_url"
    url = block["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    # Real round-trip: the encoded payload decodes back to the on-disk bytes.
    payload = base64.b64decode(url.split(",", 1)[1])
    assert payload == _PNG_1x1


@pytest.mark.integration
def test_real_audio_file_emits_input_audio_wire_block(tmp_path):
    """A real WAV on disk normalizes to an input_audio block with 'wav' format."""
    clip = tmp_path / "sound.wav"
    clip.write_bytes(_WAV_BYTES)

    block = _classify_input_value({"type": "audio", "path": str(clip)}, "Snd", {})

    assert block["type"] == "input_audio"
    assert block["input_audio"]["format"] == "wav"
    assert base64.b64decode(block["input_audio"]["data"]) == _WAV_BYTES


@pytest.mark.integration
def test_real_files_compose_into_multimodal_message(tmp_path):
    """End-to-end: a text prompt + image file + audio file build one user message
    whose content list carries a text part, an image_url part, and an
    input_audio part -- the full shape a provider receives."""
    img = tmp_path / "frame.png"
    img.write_bytes(_PNG_1x1)
    clip = tmp_path / "voice.wav"
    clip.write_bytes(_WAV_BYTES)

    strategy = AsyncSingleShotStrategy()
    agent = _make_agent(
        {
            "prompt": {"desc": "Instruction"},
            "image": {"desc": "An image"},
            "audio": {"desc": "An audio clip"},
        }
    )
    inputs = {
        "prompt": "Describe the scene and transcribe the audio",
        "image": {"type": "image", "path": str(img)},
        "audio": {"type": "audio", "path": str(clip)},
    }

    messages = strategy._create_messages_from_inputs(agent, inputs)

    assert len(messages) == 1
    content = messages[0]["content"]
    assert isinstance(content, list)
    types = [part["type"] for part in content]
    assert "text" in types
    assert "image_url" in types
    assert "input_audio" in types

    img_part = next(p for p in content if p["type"] == "image_url")
    assert img_part["image_url"]["url"].startswith("data:image/png;base64,")

    audio_part = next(p for p in content if p["type"] == "input_audio")
    assert audio_part["input_audio"]["format"] == "wav"
    assert base64.b64decode(audio_part["input_audio"]["data"]) == _WAV_BYTES


@pytest.mark.integration
def test_missing_real_file_fails_closed(tmp_path):
    """A path pointing at no file fails CLOSED with a typed ValueError -- the
    classifier never silently degrades a broken image path to text."""
    missing = tmp_path / "does_not_exist.png"
    with pytest.raises(ValueError, match="failed size validation"):
        _classify_input_value({"type": "image", "path": str(missing)}, "X", {})
