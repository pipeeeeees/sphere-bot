import asyncio

from toaster.llm_agents.gemini import build_gemini_prompt, collect_message_attachments


class DummyAttachment:
    def __init__(self, filename, data, content_type=None):
        self.filename = filename
        self._data = data
        self.content_type = content_type

    async def read(self):
        return self._data


class DummyMessage:
    def __init__(self, content="", attachments=None, embeds=None):
        self.content = content
        self.attachments = attachments or []
        self.embeds = embeds or []


class DummyEmbed:
    def __init__(self, url):
        self.image = type("Image", (), {"url": url})()


def test_collect_message_attachments_reads_image_payloads():
    message = DummyMessage(
        content="Check this out",
        attachments=[DummyAttachment("cat.png", b"fake-image-bytes", "image/png")],
    )

    payloads = asyncio.run(collect_message_attachments([message]))

    assert len(payloads) == 1
    assert payloads[0]["mime_type"] == "image/png"
    assert payloads[0]["data"] == b"fake-image-bytes"
    assert payloads[0]["filename"] == "cat.png"


def test_build_gemini_prompt_enforces_consistent_discord_format_for_news_requests():
    prompt = build_gemini_prompt(
        history="",
        message="What's the latest news in Atlanta today?",
    )

    assert "at most 2 emojis" in prompt.lower()
    assert "bullet points" in prompt.lower()
    assert "discord" in prompt.lower()


def test_collect_message_attachments_reads_embedded_images(monkeypatch):
    class DummyResponse:
        def __init__(self):
            self.content = b"embedded-image-bytes"
            self.headers = {"content-type": "image/png"}

        def raise_for_status(self):
            return None

    monkeypatch.setattr("toaster.llm_agents.gemini.requests.get", lambda *args, **kwargs: DummyResponse())

    message = DummyMessage(
        content="Look at this",
        embeds=[DummyEmbed("https://example.com/embed.png")],
    )

    payloads = asyncio.run(collect_message_attachments([message]))

    assert len(payloads) == 1
    assert payloads[0]["mime_type"] == "image/png"
    assert payloads[0]["data"] == b"embedded-image-bytes"
    assert payloads[0]["filename"].endswith("embed.png")
