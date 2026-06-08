import pytest
from types import SimpleNamespace

from toaster import commands_impl
from toaster.scheduler import ScheduleRegistry


class DummyChannel:
    def __init__(self):
        self.sent = []
        self.id = 1

    async def send(self, message):
        self.sent.append(message)


class DummyBot:
    async def fetch_user(self, uid):
        return None


@pytest.mark.asyncio
async def test_scheduled_reboot(monkeypatch):
    # Intercept subprocess.Popen call in commands_impl
    popped = {}

    def fake_popen(args, *a, **kw):
        popped['args'] = args
        class P: pass
        return P()

    monkeypatch.setattr(commands_impl, 'subprocess', SimpleNamespace(Popen=fake_popen))

    # Make sys.exit raise SystemExit so we can assert it was called
    def fake_exit(code=0):
        raise SystemExit(code)

    monkeypatch.setattr(commands_impl, 'sys', SimpleNamespace(exit=fake_exit))

    registry = ScheduleRegistry()
    schedule = {
        "name": "test_reboot",
        "message": "$reboot",
        "channel_id": 1,
        "type": "weekly",
        "time": "00:00",
        "weekdays": [1],
        "allow_reboot": True,
        "enabled": True,
        "last_sent": None,
    }

    channel = DummyChannel()
    bot = DummyBot()

    with pytest.raises(SystemExit):
        await registry._execute_scheduled_command("$reboot", channel, bot, schedule)

    assert 'args' in popped
