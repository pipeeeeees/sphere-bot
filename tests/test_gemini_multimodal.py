import asyncio

from toaster.llm_agents.gemini import collect_message_attachments


class DummyAttachment:
    def __init__(self, filename, data, content_type=None):
        self.filename = filename
        self._data = data
        self.content_type = content_type

    async def read(self):
        return self._data


class DummyMessage:
    def __init__(self, content="", attachments=None):
        self.content = content
        self.attachments = attachments or []


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
