import asyncio
import hashlib
import hmac
import json
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet
from telethon import functions, types

from app.database import Chat, Store
from app.security.webapp import verify_init_data
from app.services.backups import Backups
from app.services.control import Control
from app.services.cleanup import Cleanup
from app.handlers.panel import Panel
from app.services.integrations import organizer_import_rows
from app.services.jobs import daily
from app.services.management import Management
from app.web import create_app


def sign(token, owner, date):
    fields = {"user": json.dumps({"id": owner}, separators=(",", ":")), "auth_date": str(date)}
    signed = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, signed.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


class DataTests(unittest.TestCase):
    def test_chat_filters_use_real_snapshot_flags_and_exact_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "chat.sqlite3")
            rows = [Chat(-17, 17, "g", "group", "First", "example"),
                    Chat(88, 88, "p", "private", "Second", None)]
            store.replace(rows, 2, flags={-17: (2, 0, 1, None), 88: (7, 0, 0, None)})
            self.assertEqual(store.page("all", "17", 0, 8)[0], rows[:1])
            self.assertEqual(store.page("all", "@example", 0, 8)[0], rows[:1])
            self.assertEqual(store.page("all", "", 0, 8, state="pinned")[0], rows[:1])
            self.assertEqual(store.page("all", "", 0, 8, sort="unread")[0], rows[::-1])
            self.assertEqual(store.dialog_stats()["unread_messages"], 9)

    def test_upgrade_preserves_legacy_database_and_archived_listing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "old.sqlite3"
            with closing(sqlite3.connect(path)) as db, db:
                db.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value INTEGER)")
                db.execute("""CREATE TABLE chats (peer INTEGER PRIMARY KEY, entity_id INTEGER,
                           kind TEXT, subtype TEXT, title TEXT, username TEXT, search TEXT)""")
                db.execute("INSERT INTO settings VALUES ('dialogs',1)")
                db.execute("INSERT INTO chats VALUES (1,1,'c','channel','Sample','sample','sample')")
            store = Store(path)
            self.assertEqual(store.counts(), (1, 0, 1))
            self.assertEqual(store.page("c", "sample", 0, 8)[3], 1)
            store.replace([Chat(2, 2, "p", "private", "Dialog", None)], 1, {2})
            self.assertEqual(store.page("a", "", 0, 8)[3], 1)
            self.assertEqual(store.analytics()["kinds"], {"p": 1})

    def test_backup_is_encrypted_and_can_restore_into_separate_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = Store(root / "metadata.sqlite3")
            store.replace([Chat(1, 1, "c", "channel", "PRIVATE_TITLE", None)], 1)
            store.set_preference("language", "en")
            backups = Backups(root, Fernet(Fernet.generate_key()))
            name = backups.create()
            self.assertNotIn(b"PRIVATE_TITLE", backups.path(name).read_bytes())
            self.assertEqual(backups.inspect(name)["chats"], 1)
            restored = root / "restored.sqlite3"
            backups.inspect(name, target=restored)
            self.assertEqual(Store(restored).preference("language", "fa"), "en")
            self.assertEqual(Store(restored).counts(), (1, 0, 1))

    def test_organizer_and_stats_have_no_cross_database_state(self):
        with tempfile.TemporaryDirectory() as directory:
            left = Store(Path(directory) / "a.sqlite3")
            right = Store(Path(directory) / "b.sqlite3")
            rows = [Chat(3, 3, "p", "private", "Example", "test_name")]
            left.replace(rows, 1)
            right.replace(rows, 1)
            left.organize(3, favorite=True, tag="work", viewed=True)
            self.assertEqual(left.page("favorites", "test_name", 0, 8)[3], 1)
            self.assertEqual(right.page("favorites", "", 0, 8)[3], 0)
            self.assertEqual(left.page("tagged", "", 0, 8)[3], 1)
            self.assertEqual(left.collections(), [("work", 1)])
            self.assertEqual(left.page("all", "", 0, 8, tag="work")[3], 1)
            left.observe_media([(3, 1, "photo", 30), (3, 1, "photo", 31)])
            self.assertEqual(left.analytics()["observed_media"], [("photo", 1, 31)])
            self.assertEqual(right.analytics()["observed_media"], [])

    def test_import_is_limited_to_matching_dialog_ids(self):
        rows = organizer_import_rows({"version": 1, "organizer": [
            {"peer": "4", "tag": "work", "favorite": True},
            {"peer": "9", "tag": "other", "favorite": True},
        ]})
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "database.sqlite3")
            store.replace([Chat(4, 4, "p", "private", "Sample", None)], 1)
            self.assertEqual(store.organizer_import(rows), 1)
            self.assertEqual(store.collections(), [("work", 1)])

    def test_init_data_rejects_tampering_non_owner_expiration_and_duplicate_fields(self):
        signed = sign("bot-token", 42, 2000)
        self.assertTrue(verify_init_data(signed, "bot-token", 42, now=2030))
        self.assertFalse(verify_init_data(signed, "bot-token", 999, now=2030))
        self.assertFalse(verify_init_data(signed, "bot-token", 42, now=6001))
        self.assertFalse(verify_init_data(signed.replace("2000", "2001"), "bot-token", 42, now=2030))
        self.assertFalse(verify_init_data(signed + "&auth_date=2000", "bot-token", 42, now=2030))


class ManagementTests(unittest.IsolatedAsyncioTestCase):
    async def test_blocked_listing_and_unblock_use_telegram_rpc(self):
        user = types.User(42, first_name="Blocked", access_hash=10)
        moment = SimpleNamespace()
        self.client.side_effect = [SimpleNamespace(chats=[], users=[user], count=2,
            blocked=[SimpleNamespace(peer_id=types.PeerUser(42), date=moment)]), True]
        items, more = await self.manager.blocked(0, 1)
        self.assertEqual(items, [(user, moment)])
        self.assertTrue(more)
        self.assertTrue(await self.manager.unblock(user))
        self.assertIsInstance(self.client.await_args.args[0], functions.contacts.UnblockRequest)
    async def test_bot_cleanup_selects_and_runs_through_shared_queue(self):
        chat = Chat(-7, 7, "g", "group", "Example group", None)
        cleanup = SimpleNamespace(start=Mock())
        workspace = SimpleNamespace(management=None, store=None, cleanup=cleanup,
                                    service=SimpleNamespace(chat=lambda peer: chat if peer == -7 else None),
                                    resolve=Mock(return_value=("g", 2, "Example")))
        panel = Panel(SimpleNamespace(), workspace)
        panel.cleanup_screen = AsyncMock()
        panel.cleanup_report = AsyncMock()
        self.assertTrue(await panel.callback("uctick", "view:-7", 42))
        panel.cleanup_screen.assert_awaited_once_with("g", 2, 42, "Example")
        cleanup.start.assert_not_called()
        self.assertTrue(await panel.callback("ucrun", "", 42))
        cleanup.start.assert_called_once_with([-7])
        self.assertFalse(panel.cleanup_selection)
        panel.cleanup_report.assert_awaited_once_with(0, 42)

    async def test_cleanup_accepts_more_than_thirty_explicit_selections(self):
        peers = list(range(1, 42))
        chats = {peer: Chat(peer, peer, "b", "bot", f"Bot {peer}", None) for peer in peers}
        service = SimpleNamespace(chat=chats.get, ready=True)
        workspace = SimpleNamespace(
            backups=Backups(Path("unused"), Fernet(Fernet.generate_key())), service=service,
            management=SimpleNamespace(account=None))
        cleanup = Cleanup(workspace)
        cleanup._run = AsyncMock()
        self.assertEqual(len(cleanup.start(peers)["items"]), len(peers))
        await cleanup.task
        self.assertEqual([item.peer for item in cleanup._run.await_args.args[0]], peers)

    async def test_cleanup_archives_before_departing_and_resyncs_once(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            chat = Chat(-7, 7, "g", "گروه", "Example", "example_group")
            account = SimpleNamespace(full_info=AsyncMock(return_value=SimpleNamespace(
                full_chat=SimpleNamespace(about="Description", participants_count=9))))
            service = SimpleNamespace(chat=lambda peer: chat if peer == -7 else None,
                                      entities={-7: object()}, lock=asyncio.Lock(), ready=True,
                                      _synchronize=AsyncMock())
            workspace = SimpleNamespace(
                backups=Backups(base, Fernet(Fernet.generate_key())), service=service,
                management=SimpleNamespace(account=account),
                control=SimpleNamespace(lock=asyncio.Lock()))
            cleanup = Cleanup(workspace)

            async def leave(selected):
                self.assertEqual(selected, chat)
                saved = cleanup.read_backup(cleanup.list_backups()[0])["items"][0]
                self.assertEqual(saved["public_url"], "https://t.me/example_group")
                return "left"

            service.leave_one = AsyncMock(side_effect=leave)
            cleanup.start([-7])
            with self.assertRaises(ValueError):
                cleanup.start([-7])
            await cleanup.task
            self.assertEqual(cleanup.status()["items"][0]["status"], "left")
            service._synchronize.assert_awaited_once()

    def setUp(self):
        self.client = AsyncMock()
        async def direct(operation):
            return await operation()
        self.account = SimpleNamespace(client=self.client, read=direct, request=direct, owner_id=42)
        self.store = SimpleNamespace(record=Mock())
        self.manager = Management(SimpleNamespace(account=self.account, store=self.store,
                                                   entities={}))

    async def test_contacts_and_verified_deletion(self):
        user = types.User(42, first_name="Contact", access_hash=10)
        self.client.side_effect = [
            SimpleNamespace(contacts=[SimpleNamespace(user_id=42)], users=[user]),
            True, SimpleNamespace(contacts=[], users=[]),
        ]
        self.assertEqual(await self.manager.contacts(), (user,))
        self.assertTrue(await self.manager.delete_contact(user.id))
        request = self.client.await_args_list[1].args[0]
        self.assertIsInstance(request, functions.contacts.DeleteContactsRequest)
        self.assertEqual([item.user_id for item in request.id], [42])

    async def test_saved_message_delete_is_local_and_verified(self):
        self.client.return_value = True
        self.client.get_messages.return_value = None
        self.assertTrue(await self.manager.delete_message("me", 41))
        request = self.client.await_args.args[0]
        self.assertIsInstance(request, functions.messages.DeleteMessagesRequest)
        self.assertFalse(request.revoke)

    async def test_profile_and_protected_media(self):
        self.client.side_effect = [True, SimpleNamespace(
            users=[SimpleNamespace(id=42, first_name="New")], full_user=SimpleNamespace(about=""))]
        self.assertTrue(await self.manager.set_profile("first_name", "New"))
        self.assertIsInstance(self.client.await_args_list[0].args[0], functions.account.UpdateProfileRequest)
        protected = SimpleNamespace(noforwards=True)
        self.assertIsNone(await self.manager.media(protected))
        self.client.download_media.assert_not_awaited()

    async def test_current_session_is_never_revoked_and_confirmations_are_one_time(self):
        self.client.return_value = SimpleNamespace(
            authorizations=[SimpleNamespace(hash=123, current=True)])
        with self.assertRaises(LookupError):
            await self.manager.revoke(123)
        control = Control(SimpleNamespace(delete_contact=AsyncMock(return_value=True)), None)
        token = control.prepare("contact_delete", 42, "Sample")
        self.assertTrue(await control.confirm(token))
        with self.assertRaises(LookupError):
            await control.confirm(token)
        control.management.delete_contact.assert_awaited_once_with(42)

    async def test_api_enforces_owner_before_accessing_workspace(self):
        service = SimpleNamespace(ready=True)
        workspace = SimpleNamespace(service=service, management=SimpleNamespace(),
                                    control=SimpleNamespace(), store=SimpleNamespace(),
                                    authorized=True, overview=AsyncMock(return_value={"dialogs": 2}))
        config = SimpleNamespace(bot_token="bot-token", owner_id=42)
        asgi = create_app(workspace, config)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=asgi),
                                    base_url="http://test") as client:
            response = await client.get("/api/overview")
            self.assertEqual(response.status_code, 403)
            response = await client.get("/api/overview", headers={
                "X-Telegram-Init-Data": sign(config.bot_token, 999, int(time.time())),
            })
            self.assertEqual(response.status_code, 403)
            workspace.overview.assert_not_awaited()
            response = await client.get("/api/overview", headers={
                "X-Telegram-Init-Data": sign(config.bot_token, 42, int(time.time())),
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"dialogs": 2})
            self.assertEqual(response.headers["Cache-Control"], "no-store")

    async def test_daily_job_is_run_once_after_success(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "metadata.sqlite3")
            workspace = SimpleNamespace(store=store)
            operation = AsyncMock()
            await daily(workspace, "workflow", "2026-01-01", operation)
            await daily(workspace, "workflow", "2026-01-01", operation)
            operation.assert_awaited_once()
            self.assertEqual(store.preference("workflow", ""), "2026-01-01")
