import asyncio
from dataclasses import dataclass
from time import monotonic

from telethon import errors, types

from app.telegram_client import classify


@dataclass(frozen=True)
class Details:
    about: str | None
    invite: str | None
    count: int | None
    photo: bytes | None
    partial: bool


class AccountService:
    def __init__(self, account, store):
        self.account = account
        self.store = store
        self.entities = {}
        self.dialog_rows = {}
        self.archived = set()
        self.ready = False
        self.cache = {}
        self.lock = asyncio.Lock()
        self.detail_lock = asyncio.Lock()

    async def synchronize(self):
        async with self.lock:
            try:
                await self._synchronize()
            except Exception:
                await asyncio.to_thread(self.store.record, "sync", "failed")
                raise

    async def _synchronize(self):
        dialogs = await self.account.snapshot()
        chats = [chat for entity in dialogs.values() if (chat := classify(entity))]
        archived = getattr(dialogs, "archived", set())
        dialog_rows = getattr(dialogs, "rows", {})
        dates = {peer: row.date.isoformat() for peer, row in dialog_rows.items()
                 if getattr(row, "date", None)}
        flags = {}
        for peer, row in dialog_rows.items():
            raw = row.dialog
            until = getattr(getattr(raw, "notify_settings", None), "mute_until", None)
            flags[peer] = (row.unread_count, bool(getattr(raw, "unread_mark", False)),
                           bool(row.pinned), until.isoformat() if until else None)
        await asyncio.to_thread(self.store.replace, chats, len(dialogs), archived, dates, flags)
        self.dialog_rows = dialog_rows
        self.archived = archived
        self.entities = {chat.peer: dialogs[chat.peer] for chat in chats}
        self.cache.clear()
        self.ready = True
        await asyncio.to_thread(self.store.record, "sync", "ok")

    def chat(self, peer):
        return classify(self.entities.get(peer))

    async def details(self, peer):
        async with self.detail_lock:
            entity = self.entities.get(peer)
            if entity is None:
                raise LookupError
            cached = self.cache.get(peer)
            if cached and cached[0] > monotonic():
                return cached[1]
            about = invite = None
            count = getattr(entity, "participants_count", None)
            partial = False
            try:
                if isinstance(entity, types.User):
                    from telethon import functions

                    full = (await self.account.read(lambda: self.account.client(
                        functions.users.GetFullUserRequest(entity)))).full_user
                else:
                    full = (await self.account.full_info(entity)).full_chat
                about = getattr(full, "about", None)
                exported = getattr(full, "exported_invite", None)
                if not getattr(exported, "revoked", False):
                    invite = getattr(exported, "link", None)
                count = getattr(full, "participants_count", count)
                participants = getattr(full, "participants", None)
                if isinstance(participants, types.ChatParticipants):
                    count = len(participants.participants)
            except (errors.ChannelPrivateError, errors.ChatAdminRequiredError):
                partial = True
            try:
                photo = await self.account.photo(entity)
            except (errors.ChannelPrivateError, errors.PhotoInvalidError):
                photo = None
                partial = True
            result = Details(about, invite, count, photo, partial)
            if self.entities.get(peer) is entity:
                if len(self.cache) >= 64:
                    self.cache.pop(next(iter(self.cache)))
                self.cache[peer] = monotonic() + 600, result
            return result

    async def leave(self, selected):
        async with self.lock:
            outcome = await self.leave_one(selected)
            if outcome not in ("left", "already_left"):
                return outcome
            try:
                await self._synchronize()
            except Exception:
                self.ready = False
                self.entities.pop(selected.peer, None)
                self.cache.pop(selected.peer, None)
                return "refresh_failed" if outcome == "left" else "already_refresh_failed"
            return outcome

    async def leave_one(self, selected):
        """Verify one departure. The caller holds the synchronization lock."""
        entity = self.entities.get(selected.peer)
        if not self.ready or selected.kind not in ("c", "g") or classify(entity) != selected:
            raise LookupError
        before = await self.account.membership(entity)
        if before is None:
            return "unknown"
        if not before:
            return "already_left"
        try:
            if await self.account.leave(entity):
                return "left"
        except (OSError, TimeoutError, errors.ServerError, errors.UserNotParticipantError):
            pass
        try:
            after = await self.account.membership(entity)
        except (OSError, TimeoutError, errors.ServerError, errors.ChannelPrivateError):
            return "unknown"
        return "left" if after is False else "still_member" if after else "unknown"
