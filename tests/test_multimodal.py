"""read_image / read_audio with a fake provider."""
from __future__ import annotations

from pathlib import Path

import pytest

from ai_agent.models.base import ChatMessage, ChatResponse, ModelProvider
from ai_agent.models.router import ModelRouter
from ai_agent.tools.audio import ReadAudio
from ai_agent.tools.base import ToolContext
from ai_agent.tools.vision import ReadImage


class _CapturingProvider(ModelProvider):
    """Records the messages it was given so we can verify images/audio survived."""
    name = "capturing"

    def __init__(self, reply: str = "a description"):
        self.reply = reply
        self.last_messages: list[ChatMessage] = []
        self.last_model_override: str | None = None

    async def chat(self, messages, *, tools=None, temperature=0.2, max_tokens=None, on_content=None, model_override=None):
        self.last_messages = list(messages)
        self.last_model_override = model_override
        return ChatResponse(content=self.reply, tool_calls=[], finish_reason="stop")

    async def stream_chat(self, *_a, **_k):
        if False:
            yield ""

    async def list_models(self):
        return ["cap-1"]


class _DummyLogger:
    def __getattr__(self, _):
        def f(*_a, **_k): ...
        return f


# Smallest possible valid PNG (1x1 transparent).
_PNG_1x1 = bytes.fromhex(
    "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C489"
    "0000000D49444154789C6300010000000500010D0A2DB40000000049454E44AE426082"
)

# Smallest valid WAV (44-byte header, 0 samples).
_WAV_EMPTY = (
    b"RIFF" + (36).to_bytes(4, "little") + b"WAVE"
    + b"fmt " + (16).to_bytes(4, "little")
    + (1).to_bytes(2, "little") + (1).to_bytes(2, "little")
    + (44100).to_bytes(4, "little") + (88200).to_bytes(4, "little")
    + (2).to_bytes(2, "little") + (16).to_bytes(2, "little")
    + b"data" + (0).to_bytes(4, "little")
)


@pytest.fixture
def ctx_with_router(tmp_path: Path):
    provider = _CapturingProvider(reply="this is a 1x1 transparent pixel")
    router = ModelRouter(provider)
    return ToolContext(
        workspace=tmp_path,
        settings=None,
        logger=_DummyLogger(),
        extra={"router": router},
    ), provider


async def test_read_image_attaches_base64(ctx_with_router):
    ctx, provider = ctx_with_router
    img = ctx.workspace / "tiny.png"
    img.write_bytes(_PNG_1x1)

    r = await ReadImage().run({"path": "tiny.png"}, ctx)
    assert r.success, r.error
    assert r.output == "this is a 1x1 transparent pixel"
    assert len(provider.last_messages) == 1
    msg = provider.last_messages[0]
    assert msg.role == "user"
    assert len(msg.images) == 1
    # base64 of the PNG
    import base64
    assert base64.b64decode(msg.images[0]) == _PNG_1x1


async def test_read_image_rejects_unknown_extension(ctx_with_router):
    ctx, _ = ctx_with_router
    (ctx.workspace / "x.txt").write_text("not an image", encoding="utf-8")
    r = await ReadImage().run({"path": "x.txt"}, ctx)
    assert not r.success
    assert "unsupported" in (r.error or "").lower()


async def test_read_image_rejects_missing_file(ctx_with_router):
    ctx, _ = ctx_with_router
    r = await ReadImage().run({"path": "nope.png"}, ctx)
    assert not r.success
    assert "not found" in (r.error or "").lower()


async def test_read_audio_attaches_base64(ctx_with_router):
    ctx, provider = ctx_with_router
    provider.reply = "(silence)"
    a = ctx.workspace / "empty.wav"
    a.write_bytes(_WAV_EMPTY)

    r = await ReadAudio().run({"path": "empty.wav"}, ctx)
    assert r.success, r.error
    assert r.output == "(silence)"
    msg = provider.last_messages[0]
    assert len(msg.audio) == 1
    import base64
    assert base64.b64decode(msg.audio[0]) == _WAV_EMPTY


async def test_read_image_surfaces_empty_reply(ctx_with_router):
    ctx, provider = ctx_with_router
    provider.reply = ""
    img = ctx.workspace / "tiny.png"
    img.write_bytes(_PNG_1x1)
    r = await ReadImage().run({"path": "tiny.png"}, ctx)
    assert not r.success
    assert "empty" in (r.error or "").lower()


def test_chatmessage_serialises_images_as_openai_parts():
    m = ChatMessage(role="user", content="describe", images=["AAA"])
    d = m.to_provider_dict()
    assert isinstance(d["content"], list)
    assert d["content"][0] == {"type": "text", "text": "describe"}
    assert d["content"][1]["type"] == "image_url"
    assert "base64,AAA" in d["content"][1]["image_url"]["url"]


def test_chatmessage_no_attachments_keeps_string_content():
    m = ChatMessage(role="user", content="hello")
    d = m.to_provider_dict()
    assert d["content"] == "hello"


# --- model override resolution ----------------------------------------------

class _SettingsStub:
    """Mimic the slice of Settings the tools actually read."""
    def __init__(self, vision_model=None, audio_model=None):
        from ai_agent.config import MultimodalConfig
        self.multimodal = MultimodalConfig(vision_model=vision_model, audio_model=audio_model)


async def test_read_image_arg_beats_config(tmp_path):
    provider = _CapturingProvider("desc")
    router = ModelRouter(provider)
    ctx = ToolContext(
        workspace=tmp_path,
        settings=_SettingsStub(vision_model="config-vision"),
        logger=_DummyLogger(),
        extra={"router": router},
    )
    img = tmp_path / "x.png"
    img.write_bytes(_PNG_1x1)

    await ReadImage().run({"path": "x.png", "model": "arg-vision"}, ctx)
    assert provider.last_model_override == "arg-vision"


async def test_read_image_falls_back_to_config(tmp_path):
    provider = _CapturingProvider("desc")
    router = ModelRouter(provider)
    ctx = ToolContext(
        workspace=tmp_path,
        settings=_SettingsStub(vision_model="config-vision"),
        logger=_DummyLogger(),
        extra={"router": router},
    )
    img = tmp_path / "x.png"
    img.write_bytes(_PNG_1x1)

    await ReadImage().run({"path": "x.png"}, ctx)
    assert provider.last_model_override == "config-vision"


async def test_read_image_no_override_when_nothing_set(tmp_path):
    provider = _CapturingProvider("desc")
    router = ModelRouter(provider)
    ctx = ToolContext(
        workspace=tmp_path,
        settings=_SettingsStub(),  # vision_model=None
        logger=_DummyLogger(),
        extra={"router": router},
    )
    img = tmp_path / "x.png"
    img.write_bytes(_PNG_1x1)

    await ReadImage().run({"path": "x.png"}, ctx)
    assert provider.last_model_override is None


async def test_read_audio_uses_audio_model_config(tmp_path):
    provider = _CapturingProvider("ok")
    router = ModelRouter(provider)
    ctx = ToolContext(
        workspace=tmp_path,
        settings=_SettingsStub(audio_model="audio-default"),
        logger=_DummyLogger(),
        extra={"router": router},
    )
    a = tmp_path / "x.wav"
    a.write_bytes(_WAV_EMPTY)

    await ReadAudio().run({"path": "x.wav"}, ctx)
    assert provider.last_model_override == "audio-default"
