from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock

from telethon import functions, types

from app.services.autoread import AutoRead


class AutoReadTests(IsolatedAsyncioTestCase):
    async def test_mentions_only_and_unconfigured_group(self):
        group = SimpleNamespace(kind="g")
        store = SimpleNamespace(preference=Mock(return_value="{}"), set_preference=Mock())
        subscribed = types.Dialog(types.PeerChat(3), 10, 1, 1, 5, 2, 0, 0, types.PeerNotifySettings())
        unconfigured = types.Dialog(types.PeerChat(4), 11, 1, 1, 4, 1, 0, 0, types.PeerNotifySettings())
        client = AsyncMock()
        client.side_effect = [SimpleNamespace(dialogs=[subscribed, unconfigured]), True]

        async def execute(operation):
            return await operation()

        account = SimpleNamespace(client=client, read=execute, request=execute)
        service = SimpleNamespace(account=account, ready=True, chat=lambda _: group,
                                  entities={-3: types.InputPeerChat(3), -4: types.InputPeerChat(4)},
                                  dialog_rows={})
        rules = AutoRead(SimpleNamespace(service=service, store=store, authorized=True))
        await rules.set(-3, "mentions", 60)
        await rules.tick()
        request = client.await_args.args[0]
        self.assertIsInstance(request, functions.messages.ReadMentionsRequest)
        self.assertEqual(request.peer.chat_id, 3)
        client.send_read_acknowledge.assert_not_awaited()
        await rules.set(-3, "off", 60)
        await rules.tick()
        self.assertEqual(client.await_count, 2)
