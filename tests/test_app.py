import asyncio
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from cryptography.fernet import Fernet
from telethon import errors, types
from telethon.crypto import AuthKey

from app.auth import local_login, local_qr_login
from app.database import Chat, Store
from app.handlers import Bot
from app.keyboards import page_keys
from app.security import EncryptedSession
from app.services import AccountService
from app.telegram_client import FloodDelay, TelegramAccount, classify


NOW = datetime.now(timezone.utc)


def channel(id=21, **flags):
    return types.Channel(id, "عنوان", types.ChatPhotoEmpty(), NOW, **flags)


class StorageTests(unittest.TestCase):
    def test_session_never_written_before_approval_and_encrypted_after(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "account.fernet"
            cipher = Fernet(Fernet.generate_key())
            session = EncryptedSession(path, cipher)
            session.set_dc(2, "127.0.0.1", 443)
            session.auth_key = AuthKey(b"x" * 256)
            raw = session.save()
            self.assertFalse(path.exists())
            session.enable()
            self.assertNotIn(raw.encode(), path.read_bytes())
            self.assertEqual(EncryptedSession(path, cipher).save(), raw)
            session.invalidate()
            self.assertFalse(path.exists())

    def test_classification(self):
        self.assertEqual(classify(channel(broadcast=True)).kind, "c")
        self.assertEqual(classify(channel(megagroup=True, username="public")).username, "public")
        self.assertEqual(classify(channel(megagroup=True)).kind, "g")
        self.assertIsNone(classify(channel(broadcast=True, left=True)))
        group = types.Chat(21, "گروه", types.ChatPhotoEmpty(), 5, NOW, 1)
        self.assertEqual(classify(group).kind, "g")
        self.assertNotEqual(classify(group).peer, classify(channel(broadcast=True)).peer)

    def test_pagination_search_and_exact_button_title(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "meta.sqlite3")
            chats = [Chat(-i, i, "c", "کانال", f"كتاب يک {i:04}", None)
                     for i in range(1, 1004)]
            store.replace(chats + [Chat(-2000, 2000, "g", "گروه", "گروه", None)], 1020)
            self.assertEqual(store.counts(), (1003, 1, 1020))
            result, page, pages, total = store.page("c", "کتاب یک", 900, 8)
            self.assertEqual((len(result), page, pages, total), (3, 125, 126, 1003))
            rows = page_keys(result, "c", "view", page, pages)["inline_keyboard"]
            self.assertEqual([len(row) for row in rows[:3]], [2, 2, 2])
            self.assertEqual(rows[0][0]["text"], result[0].title)
            self.assertEqual(store.page("g", "", 0, 8)[3], 1)
            self.assertEqual(store.page("g", "%", 0, 8)[3], 0)
            self.assertEqual(store.page("c", "کتاب یک", 0, 8, "public")[3], 0)
            self.assertEqual(store.page("c", "کتاب یک", 0, 8, "private")[3], 1003)


class AccountTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_info_photo_and_actions_share_one_message(self):
        chat = Chat(-21, 21, "c", "کانال", "A < B", "public")
        api = SimpleNamespace(send_photo_card=AsyncMock(), send=AsyncMock())
        service = SimpleNamespace(details=AsyncMock(return_value=SimpleNamespace(
            photo=b"photo", count=8, about="Description", invite=None, partial=False)))
        await Bot(api, service).show_info(chat)
        api.send.assert_not_awaited()
        _, caption, markup = api.send_photo_card.await_args.args
        self.assertIn("A &lt; B", caption)
        self.assertEqual(markup["inline_keyboard"][0][0]["url"], "https://t.me/public")

    async def test_page_jump_accepts_persian_digits_and_keeps_the_original_view(self):
        api = SimpleNamespace(send=AsyncMock(return_value={"message_id": 17}))
        bot = Bot(api, SimpleNamespace())
        bot.authorized = True
        bot.show_list = AsyncMock()
        view = bot.new_view("c", "عنوان", "private")
        await bot.callback(f"jump:{view}", 12)
        await bot.message({"text": "۰", "reply_to_message": {"message_id": 17}})
        bot.show_list.assert_not_awaited()
        await bot.message({"text": "۱۲", "reply_to_message": {"message_id": 17}})
        bot.show_list.assert_awaited_once_with(view, 11, 12)

    async def test_qr_displays_after_wait_starts_and_refreshes_after_timeout(self):
        first = SimpleNamespace(url="tg://login?token=first", wait=AsyncMock(side_effect=TimeoutError))
        second = SimpleNamespace(url="tg://login?token=second", wait=AsyncMock(return_value="account"))
        client = SimpleNamespace(connect=AsyncMock(),
                                 qr_login=AsyncMock(side_effect=[first, second]))
        with patch("app.auth.sys.stdin.isatty", return_value=True), \
                patch("app.auth.sys.stdout.isatty", return_value=True), \
                patch("builtins.input", return_value=""), patch("builtins.print") as display:
            self.assertEqual(await local_qr_login(client), "account")
        client.connect.assert_awaited_once()
        first.wait.assert_awaited_once()
        second.wait.assert_awaited_once()
        self.assertIn("QR_LOGIN tg://login?token=second", display.call_args.args)

    async def test_password_flow(self):
        client = SimpleNamespace(
            connect=AsyncMock(),
            send_code_request=AsyncMock(return_value=SimpleNamespace(phone_code_hash="hash")),
            sign_in=AsyncMock(side_effect=[errors.SessionPasswordNeededError(None), "account"]),
        )
        with patch("app.auth.sys.stdin.isatty", return_value=True), \
                patch("builtins.input", return_value="+12345"), \
                patch("app.auth.secret", side_effect=["12345", "password"]):
            self.assertEqual(await local_login(client), "account")
        self.assertEqual(client.sign_in.await_args_list[0].kwargs["phone_code_hash"], "hash")
        client.sign_in.assert_awaited_with(password="password")

    async def test_phone_login_retries_after_telethon_migrates_data_center(self):
        client = SimpleNamespace(
            connect=AsyncMock(),
            session=SimpleNamespace(dc_id=4),
            send_code_request=AsyncMock(side_effect=[
                errors.PhoneMigrateError(None, capture=4),
                SimpleNamespace(phone_code_hash="hash"),
            ]),
            sign_in=AsyncMock(return_value="account"),
        )
        with patch("app.auth.sys.stdin.isatty", return_value=True), \
                patch("builtins.input", return_value="+12345"), \
                patch("app.auth.secret", return_value="12345"):
            self.assertEqual(await local_login(client), "account")
        self.assertEqual(client.send_code_request.await_count, 2)

    async def test_reconnect_retry_and_flood_wait(self):
        client = SimpleNamespace(is_connected=Mock(return_value=False), connect=AsyncMock())
        account = TelegramAccount(client, 1)
        operation = AsyncMock(side_effect=[OSError, "result"])
        with patch("app.telegram_client.asyncio.sleep", new_callable=AsyncMock):
            self.assertEqual(await account.read(operation), "result")
        self.assertEqual(client.connect.await_count, 2)
        operation.side_effect = errors.FloodWaitError(None, capture=30)
        with self.assertRaises(FloodDelay):
            await account.read(operation)
        calls = operation.await_count
        with self.assertRaises(FloodDelay):
            await account.read(operation)
        self.assertEqual(operation.await_count, calls)

    async def test_snapshot_iteration_and_profile_photo_request(self):
        photo = b"photo"
        entity = channel(broadcast=True)

        async def dialogs():
            yield SimpleNamespace(id=-10, entity=entity)
            yield SimpleNamespace(id=-20, entity=entity)

        client = SimpleNamespace(is_connected=Mock(return_value=True),
                                 iter_dialogs=Mock(side_effect=lambda **_: dialogs()),
                                 download_profile_photo=AsyncMock(return_value=photo))
        account = TelegramAccount(client, 1)
        self.assertEqual(await account.snapshot(), {-10: entity, -20: entity})
        client.iter_dialogs.assert_called_once_with(limit=None, ignore_migrated=False)
        self.assertEqual(await account.photo(entity), photo)
        client.download_profile_photo.assert_awaited_once_with(entity, file=bytes)

    async def test_snapshot_resumes_same_iterator_after_page_flood_wait(self):
        entity = channel(broadcast=True)
        iterator = AsyncMock()
        iterator.__anext__.side_effect = [
            SimpleNamespace(id=-10, entity=entity),
            errors.FloodWaitError(None, capture=25),
            SimpleNamespace(id=-20, entity=entity),
            StopAsyncIteration,
        ]
        client = SimpleNamespace(is_connected=Mock(return_value=True),
                                 iter_dialogs=Mock(return_value=iterator))
        with patch("app.telegram_client.asyncio.sleep", new_callable=AsyncMock) as wait:
            result = await TelegramAccount(client, 1).snapshot()
        self.assertEqual(set(result), {-10, -20})
        client.iter_dialogs.assert_called_once()
        wait.assert_awaited_once()

    async def test_synchronization_details_cache_confirmed_leave_and_refresh(self):
        entity = channel(broadcast=True)
        chat = classify(entity)
        user_peer = 55
        account = SimpleNamespace(
            snapshot=AsyncMock(side_effect=[{chat.peer: entity, user_peer: object()}, {}]),
            full_info=AsyncMock(return_value=SimpleNamespace(full_chat=SimpleNamespace(
                about="شرح", participants_count=8, exported_invite=SimpleNamespace(link="link")))),
            photo=AsyncMock(return_value=b"photo"),
            membership=AsyncMock(side_effect=[True, False]),
            leave=AsyncMock(side_effect=TimeoutError),
        )
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "meta.sqlite3")
            service = AccountService(account, store)
            await service.synchronize()
            self.assertEqual(store.counts(), (1, 0, 2))
            info = await service.details(chat.peer)
            self.assertEqual((info.about, info.count, info.invite, info.photo),
                             ("شرح", 8, "link", b"photo"))
            self.assertIs(await service.details(chat.peer), info)
            account.photo.assert_awaited_once()
            self.assertEqual(await service.leave(chat), "left")
            self.assertEqual(store.counts(), (0, 0, 0))
            with self.assertRaises(LookupError):
                await service.leave(chat)
            account.leave.assert_awaited_once()

    async def test_failed_scan_preserves_last_complete_snapshot(self):
        entity = channel(broadcast=True)
        chat = classify(entity)
        account = SimpleNamespace(snapshot=AsyncMock(side_effect=[{chat.peer: entity}, OSError]))
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "meta.sqlite3")
            service = AccountService(account, store)
            await service.synchronize()
            with self.assertRaises(OSError):
                await service.synchronize()
            self.assertEqual(store.counts(), (1, 0, 1))
            self.assertEqual(service.chat(chat.peer), chat)

    async def test_individual_confirmation_cancel_wrong_message_and_replay(self):
        chat = classify(channel(broadcast=True))
        api = SimpleNamespace(owner_id=12, send=AsyncMock(return_value={"message_id": 17}),
                              edit=AsyncMock())
        service = SimpleNamespace(ready=True, chat=Mock(return_value=chat),
                                  leave=AsyncMock(return_value="unknown"))
        bot = Bot(api, service)
        private = {"id": 12, "type": "private"}
        invite = {"message": {"from": {"id": 12}, "chat": private}}
        self.assertTrue(bot.allowed(invite))
        self.assertFalse(bot.allowed({"message": {"from": {"id": 13}, "chat": private}}))
        await bot.ask_leave(chat)
        token = next(iter(bot.confirmations))
        await bot.resolve_leave(token, 18, True)
        service.leave.assert_not_awaited()
        await bot.resolve_leave(token, 17, False)
        service.leave.assert_not_awaited()
        await bot.ask_leave(chat)
        token = next(iter(bot.confirmations))
        await asyncio.gather(*(bot.resolve_leave(token, 17, True) for _ in range(2)))
        service.leave.assert_awaited_once_with(chat)
