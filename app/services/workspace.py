import asyncio
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
from secrets import token_urlsafe
from time import monotonic

from telethon import utils

from app.services.management import MEDIA_TYPES, PRIVACY_KEYS
from app.services.cleanup import Cleanup
from app.services.autoread import AutoRead
from app.utils import search_key


CHAT_KINDS = {"all", "c", "g", "p", "b", "a", "favorites", "tagged"}
SIZE = 8


class Workspace:
    def __init__(self, control):
        self.control = control
        self.management = control.management
        self.service = self.management.service
        self.store = self.management.store
        self.backups = control.backups
        self.refs = {}
        self.authorized = False
        self.syncing = False
        self.backup_lock = asyncio.Lock()
        self.cleanup = Cleanup(self)
        self.auto_read = AutoRead(self)

    def ref(self, kind, value):
        now = monotonic()
        if len(self.refs) >= 512:
            self.refs = {key: entry for key, entry in self.refs.items() if entry[2] > now}
        if len(self.refs) >= 512:
            self.refs.pop(next(iter(self.refs)))
        token = token_urlsafe(12)
        self.refs[token] = kind, value, now + 600
        return token

    def resolve(self, token, kind):
        entry = self.refs.get(token)
        if not entry or entry[0] != kind or entry[2] <= monotonic():
            raise LookupError
        return entry[1]

    async def overview(self):
        channels, groups, dialogs = await asyncio.to_thread(self.store.counts)
        return {"channels": channels, "groups": groups, "dialogs": dialogs,
                **await asyncio.to_thread(self.store.dialog_stats),
                "contacts": self.management.contact_count,
                "connected": self.authorized and self.management.client.is_connected(),
                "synchronized": self.service.ready, "syncing": self.syncing,
                "activity": await asyncio.to_thread(self.store.activity, 0, 4)}

    async def sync(self):
        if self.syncing:
            return False
        self.syncing = True
        try:
            await self.service.synchronize()
        finally:
            self.syncing = False
        return True

    async def backup(self):
        async with self.backup_lock:
            raw = await asyncio.to_thread(self.store.preference, "backup_keep", "10")
            name = await asyncio.to_thread(self.backups.create, min(100, max(1, int(raw))))
        await self.management.record("backup", "ok")
        return name

    async def browse(self, section, page=0, query="", kind="all", privacy="all",
                     peer=None, mode="", sort="name", after="", before="", sender="", tag="", state=""):
        offset = page * SIZE
        if section == "chats":
            if not self.service.ready:
                return [], False
            if kind not in CHAT_KINDS:
                raise ValueError("Unknown chat filter")
            rows, actual, pages, _ = await asyncio.to_thread(
                self.store.page, kind, query, page, SIZE, privacy, sort, tag, state)
            return [self.chat_item(chat) for chat in rows], actual + 1 < pages
        if section == "folders":
            rows = await self.management.folders()
            if not mode:
                return self.window([{"title": getattr(item.title, "text", item.title),
                                     "mode": str(item.id)} for item in rows], offset)
            folder = next((item for item in rows if str(item.id) == mode), None)
            if folder is None:
                raise LookupError
            return self.window([self.chat_item(item) for item in
                                self.management.folder_chats(folder, query)], offset)
        if section == "contacts":
            rows = await self.management.contacts()
            matches = sorted((user for user in rows if search_key(query) in search_key(
                f"{utils.get_display_name(user)} {user.username or ''}")),
                             key=lambda user: search_key(utils.get_display_name(user)))
            return self.window([{"title": utils.get_display_name(user) or str(user.id),
                                 "info": user.username or "", "id": str(user.id)}
                                for user in matches], offset)
        if section == "drafts":
            rows = await self.management.drafts()
            items = []
            for row in rows:
                peer_id = utils.get_peer_id(row.peer)
                chat = self.service.chat(peer_id)
                items.append({"title": chat.title if chat else str(peer_id),
                              "info": row.draft.message[:320], "id": str(peer_id)})
            return self.window(items, offset)
        if section in ("messages", "media"):
            selected = mode or "history"
            if selected not in {"history", "scheduled", *MEDIA_TYPES}:
                raise ValueError("Unknown message filter")
            if not peer and not query and not sender and selected not in MEDIA_TYPES:
                return [], False
            lower = datetime.fromisoformat(after).replace(tzinfo=timezone.utc) if after else None
            upper = (datetime.fromisoformat(before).replace(tzinfo=timezone.utc) +
                     timedelta(days=1)) if before else None
            if lower and upper and lower >= upper:
                raise ValueError
            rows = await self.management.message_page(selected, peer, query, offset, SIZE,
                                                       after=lower, before=upper, sender=sender or None)
            items = [self.message_item(item, peer, selected) for item in rows.entries]
            if selected in MEDIA_TYPES and selected != "pinned":
                observations = [(message.chat_id, message.id, selected, item["bytes"] or 0)
                                for item, message in zip(items, rows.entries, strict=True)
                                if item["bytes"] is not None and message.chat_id]
                if observations:
                    await asyncio.to_thread(self.store.observe_media, observations)
            return items, rows.more
        if section == "sessions":
            rows, _ = await self.management.sessions()
            return self.window([{
                "title": item.device_model or item.app_name,
                "info": " · ".join(filter(None, (item.app_name, item.platform, item.country))),
                "id": self.ref("session", item),
                "current": bool(item.current),
                "date": item.date_active.isoformat() if item.date_active else None,
            } for item in rows], offset)
        if section == "blocked":
            rows, more = await self.management.blocked(offset, SIZE)
            return [{"title": utils.get_display_name(entity) or str(entity.id),
                     "info": getattr(entity, "username", "") or "",
                     "id": self.ref("blocked", entity), "date": date.isoformat()}
                    for entity, date in rows if entity is not None], more
        if section == "activity":
            rows = await asyncio.to_thread(self.store.activity, offset, SIZE + 1)
            return self.window([{"title": op, "info": status, "date": when}
                                for when, op, status in rows], 0)
        if section == "backups":
            rows = await asyncio.to_thread(self.backups.list)
            return self.window([{"title": item["name"], "bytes": item["bytes"], "id": item["name"]}
                                for item in rows], offset)
        raise LookupError

    @staticmethod
    def window(items, offset):
        return items[offset:offset + SIZE], len(items) > offset + SIZE

    def chat_item(self, chat):
        fields = asdict(chat)
        fields.update(title=chat.title, info=chat.username or "", id=str(chat.peer),
                      peer=str(chat.peer), archived=chat.peer in self.service.archived)
        fields["entity_id"] = str(chat.entity_id)
        return fields

    def message_item(self, message, peer, mode):
        protected = bool(getattr(message, "noforwards", False))
        source = self.service.chat(message.chat_id) if message.chat_id else None
        entity = self.service.entities.get(message.chat_id) or getattr(message, "chat", None)
        protected = protected or bool(getattr(entity, "noforwards", False))
        file = message.file
        actual_peer = peer or message.chat_id
        if actual_peer not in self.service.entities and actual_peer != "me":
            actual_peer = None
        reference = self.ref("message", (message, actual_peer, mode))
        text = "" if protected else (message.message or "")
        return {"title": source.title if source else str(message.chat_id or message.id),
                "info": text[:240], "id": reference,
                "date": message.date.isoformat() if message.date else None,
                "file": getattr(file, "name", None) if file else None,
                "bytes": getattr(file, "size", None) if file else None,
                "mime": getattr(file, "mime_type", None) if file else None,
                "protected": protected, "has_media": bool(file and not protected),
                "deletable": bool(actual_peer and (actual_peer == "me" or mode == "scheduled"
                                                   or getattr(message, "out", False)))}

    async def chat_detail(self, peer):
        chat = self.service.chat(peer)
        if not chat:
            raise LookupError
        details = await self.service.details(peer)
        organization = await asyncio.to_thread(self.store.organize, peer, viewed=True)
        row = self.service.dialog_rows.get(peer)
        return {**self.chat_item(chat), **organization, "about": details.about,
                "auto_read": await self.auto_read.get(peer) if chat.kind in {"c", "g"} else None,
                "invite": details.invite, "count": details.count, "photo": bool(details.photo),
                "pinned": bool(getattr(row, "pinned", False)),
                "unread": getattr(row, "unread_count", None),
                "last_message": row.date.isoformat() if row and row.date else None}

    async def profile(self):
        me, full = await self.management.profile()
        return {"id": str(me.id), "first_name": me.first_name or "", "last_name": me.last_name or "",
                "username": me.username or "", "about": full.about or "",
                "premium": bool(me.premium), "photo": bool(me.photo)}

    async def security(self):
        return {"two_factor": await self.management.two_factor_enabled(),
                "privacy": list(PRIVACY_KEYS)}
