import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from time import monotonic

from telethon import functions, types, utils

from app.utils import search_key


@dataclass(frozen=True)
class MessagePage:
    entries: tuple
    more: bool


MEDIA_TYPES = {
    "photo": types.InputMessagesFilterPhotos,
    "video": types.InputMessagesFilterVideo,
    "file": types.InputMessagesFilterDocument,
    "audio": types.InputMessagesFilterMusic,
    "voice": types.InputMessagesFilterVoice,
    "pinned": types.InputMessagesFilterPinned,
}

PRIVACY_KEYS = {
    "phone": types.InputPrivacyKeyPhoneNumber,
    "seen": types.InputPrivacyKeyStatusTimestamp,
    "photo": types.InputPrivacyKeyProfilePhoto,
    "calls": types.InputPrivacyKeyPhoneCall,
    "invites": types.InputPrivacyKeyChatInvite,
    "forwards": types.InputPrivacyKeyForwards,
}
PRIVACY_RULES = {
    types.PrivacyValueAllowAll: "all",
    types.PrivacyValueDisallowAll: "nobody",
    types.PrivacyValueAllowContacts: "contacts",
    types.PrivacyValueDisallowContacts: "except_contacts",
    types.PrivacyValueAllowUsers: "allowed_users",
    types.PrivacyValueDisallowUsers: "blocked_users",
    types.PrivacyValueAllowChatParticipants: "allowed_chats",
    types.PrivacyValueDisallowChatParticipants: "blocked_chats",
}


class Management:
    def __init__(self, service):
        self.service = service
        self.account = service.account
        self.store = service.store
        self._contacts = None
        self._contacts_at = 0
        self._contact_lock = asyncio.Lock()
        self._writes = asyncio.Lock()
        self._known_sessions = None

    @property
    def client(self):
        return self.account.client

    async def rpc(self, request):
        return await self.account.read(lambda: self.client(request))

    async def record(self, operation, outcome):
        await asyncio.to_thread(self.store.record, operation, outcome)

    async def mutate(self, operation, request):
        async with self._writes:
            try:
                result = await self.account.request(lambda: self.client(request))
            except Exception:
                await self.record(operation, "unverified")
                raise
            await self.record(operation, "ok" if result is not False else "failed")
            return result

    async def contacts(self, *, refresh=False):
        async with self._contact_lock:
            if refresh or self._contacts is None or self._contacts_at <= monotonic():
                result = await self.rpc(functions.contacts.GetContactsRequest(hash=0))
                ids = {contact.user_id for contact in result.contacts}
                self._contacts = {user.id: user for user in result.users if user.id in ids}
                self._contacts_at = monotonic() + 300
            return tuple(self._contacts.values())

    @property
    def contact_count(self):
        return len(self._contacts) if self._contacts is not None else None

    async def contact(self, user_id):
        await self.contacts()
        if user_id not in self._contacts:
            raise LookupError
        return self._contacts[user_id]

    async def common_chats(self, user_id):
        user = await self.contact(user_id)
        result = await self.rpc(functions.messages.GetCommonChatsRequest(
            utils.get_input_user(user), max_id=0, limit=20))
        return [item.title for item in result.chats if hasattr(item, "title")]

    async def blocked(self, offset, limit):
        result = await self.rpc(functions.contacts.GetBlockedRequest(offset=offset, limit=limit))
        entities = {utils.get_peer_id(item): item for item in (*result.users, *result.chats)
                    if not isinstance(item, (types.UserEmpty, types.ChatEmpty))}
        items = [(entities.get(utils.get_peer_id(row.peer_id)), row.date)
                 for row in result.blocked]
        return items, getattr(result, "count", offset + len(items)) > offset + len(items)

    async def unblock(self, entity):
        return await self.mutate("unblock", functions.contacts.UnblockRequest(
            utils.get_input_peer(entity))) is True

    async def upsert_contact(self, first, last, *, username=None, user_id=None):
        if user_id is not None:
            user = await self.contact(user_id)
            phone = user.phone or ""
        else:
            user = await self.account.read(lambda: self.client.get_entity(username))
            if not isinstance(user, types.User) or user.bot or user.deleted or user.is_self:
                raise LookupError
            phone = ""
        result = await self.mutate("contact_save", functions.contacts.AddContactRequest(
            id=utils.get_input_user(user), first_name=first, last_name=last, phone=phone,
            add_phone_privacy_exception=False))
        self._contacts_at = 0
        contacts = await self.contacts(refresh=True)
        return any(item.id == user.id and (item.first_name or "") == first and
                   (item.last_name or "") == last for item in contacts) and result is not False

    async def delete_contact(self, user_id):
        user = await self.contact(user_id)
        await self.mutate("contact_delete", functions.contacts.DeleteContactsRequest(
            [utils.get_input_user(user)]))
        self._contacts_at = 0
        return all(user.id != user_id for user in await self.contacts(refresh=True))

    async def folders(self):
        result = await self.rpc(functions.messages.GetDialogFiltersRequest())
        return tuple(folder for folder in result.filters
                     if isinstance(folder, (types.DialogFilter, types.DialogFilterChatlist)))

    def folder_chats(self, folder, query=""):
        include = {utils.get_peer_id(peer) for peer in (*folder.include_peers, *folder.pinned_peers)}
        exclude = {utils.get_peer_id(peer) for peer in getattr(folder, "exclude_peers", ())}
        results = []
        for peer, entity in self.service.entities.items():
            if peer in exclude:
                continue
            dialog = self.service.dialog_rows.get(peer)
            chat = self.service.chat(peer)
            if peer not in include:
                is_contact = getattr(entity, "contact", False)
                category = {"c": "broadcasts", "g": "groups", "b": "bots",
                            "p": "contacts" if is_contact else "non_contacts"}[chat.kind]
                if not getattr(folder, category, False):
                    continue
                if getattr(folder, "exclude_archived", False) and peer in self.service.archived:
                    continue
                if getattr(folder, "exclude_read", False) and dialog and not (
                    dialog.unread_count or dialog.dialog.unread_mark
                ):
                    continue
                settings = getattr(getattr(dialog, "dialog", None), "notify_settings", None)
                muted_until = getattr(settings, "mute_until", None)
                if getattr(folder, "exclude_muted", False) and (
                    muted_until and muted_until > datetime.now(timezone.utc)
                ):
                    continue
            if search_key(query) in search_key(chat.title):
                results.append(chat)
        return sorted(results, key=lambda chat: (chat.peer not in include, search_key(chat.title)))

    def entity(self, peer):
        if peer == "me":
            return "me"
        entity = self.service.entities.get(peer)
        if entity is None:
            raise LookupError
        return entity

    async def message_page(self, mode, peer, search, offset, size=8, *, after=None, before=None,
                           sender=None):
        entity = self.entity(peer) if peer is not None else None
        if mode == "scheduled":
            result = await self.rpc(functions.messages.GetScheduledHistoryRequest(
                await self.account.read(lambda: self.client.get_input_entity(entity)), hash=0))
            rows = result.messages[offset:offset + size + 1]
        else:
            if entity is None and not search and mode not in MEDIA_TYPES and not sender:
                raise ValueError("Global message history requires a search or a media filter")
            kwargs = {"limit": size + 1, "add_offset": offset}
            if search:
                kwargs["search"] = search
            if before:
                kwargs["offset_date"] = before
            if sender:
                kwargs["from_user"] = sender
            if mode in MEDIA_TYPES:
                kwargs["filter"] = MEDIA_TYPES[mode]()
            if entity is None and offset:
                # Global SearchGlobal uses a composite cursor; Telethon handles it while iterating.
                rows = await self.account.read(lambda: self.client.get_messages(
                    entity, **{**kwargs, "limit": offset + size + 1, "add_offset": 0}))
                rows = rows[offset:]
            else:
                rows = await self.account.read(lambda: self.client.get_messages(entity, **kwargs))
        if after:
            rows = [item for item in rows if item.date and item.date >= after]
        return MessagePage(tuple(rows[:size]), len(rows) > size)

    async def drafts(self):
        result = await self.rpc(functions.messages.GetAllDraftsRequest())
        return tuple(update for update in result.updates
                     if isinstance(update, types.UpdateDraftMessage) and
                     isinstance(update.draft, types.DraftMessage))

    async def save_draft(self, peer, text):
        entity = self.entity(peer)
        target = await self.account.read(lambda: self.client.get_input_entity(entity))
        return await self.mutate("draft_save", functions.messages.SaveDraftRequest(
            peer=target, message=text))

    async def delete_message(self, peer, message_id, scheduled=False):
        entity = self.entity(peer)
        if scheduled:
            target = await self.account.read(lambda: self.client.get_input_entity(entity))
            await self.mutate("scheduled_delete", functions.messages.DeleteScheduledMessagesRequest(
                peer=target, id=[message_id]))
            result = await self.rpc(functions.messages.GetScheduledHistoryRequest(target, 0))
            return all(item.id != message_id for item in result.messages)
        if peer != "me":
            message = await self.account.read(lambda: self.client.get_messages(entity, ids=message_id))
            if not message or message.chat_id != peer or not message.out:
                raise LookupError
        request = (functions.channels.DeleteMessagesRequest(entity, [message_id])
                   if isinstance(entity, types.Channel) else functions.messages.DeleteMessagesRequest(
                       id=[message_id], revoke=False))
        await self.mutate("message_delete", request)
        current = await self.account.read(lambda: self.client.get_messages(entity, ids=message_id))
        return current is None or isinstance(current, types.MessageEmpty)

    async def media(self, message, limit=20 * 1024 * 1024):
        if getattr(message, "noforwards", False):
            return None
        if message.chat_id and message.chat_id != self.account.owner_id:
            chat = await self.account.read(message.get_chat)
            if chat is None or getattr(chat, "noforwards", False):
                return None
        file = message.file
        if not file or not file.size or file.size > limit:
            return None
        payload = await self.account.read(lambda: self.client.download_media(message, file=bytes))
        return payload if payload and len(payload) <= limit else None

    async def dialog_setting(self, peer, setting, enabled):
        entity = self.entity(peer)
        target = await self.account.read(lambda: self.client.get_input_entity(entity))
        if setting == "archive":
            request = functions.folders.EditPeerFoldersRequest([
                types.InputFolderPeer(target, 1 if enabled else 0)])
        else:
            request = functions.messages.ToggleDialogPinRequest(
                peer=types.InputDialogPeer(target), pinned=enabled)
        result = await self.mutate(f"dialog_{setting}", request)
        current = await self.rpc(functions.messages.GetPeerDialogsRequest([types.InputDialogPeer(target)]))
        dialog = next((item for item in current.dialogs
                       if isinstance(item, types.Dialog) and utils.get_peer_id(item.peer) == peer), None)
        if dialog is None:
            return False
        value = bool(dialog.folder_id) if setting == "archive" else bool(dialog.pinned)
        if result is False or value != enabled:
            return False
        if setting == "archive":
            self.service.archived.discard(peer)
            if enabled:
                self.service.archived.add(peer)
            await asyncio.to_thread(self.store.set_archived, peer, enabled)
        else:
            if row := self.service.dialog_rows.get(peer):
                row.pinned = enabled
            await asyncio.to_thread(self.store.set_pinned, peer, enabled)
        return True

    async def profile(self):
        result = await self.rpc(functions.users.GetFullUserRequest(types.InputUserSelf()))
        user = next(user for user in result.users if user.id == self.account.owner_id)
        return user, result.full_user

    async def set_profile(self, field, value):
        request = (functions.account.UpdateUsernameRequest(value) if field == "username"
                   else functions.account.UpdateProfileRequest(**{field: value}))
        result = await self.mutate("profile_edit", request)
        user, full = await self.profile()
        current = full.about if field == "about" else getattr(user, field)
        return (current or "") == value and result is not False

    async def profile_photos(self, offset, limit):
        return await self.account.read(lambda: self.client.get_profile_photos(
            "me", offset=offset, limit=limit))

    async def profile_photo(self, photo):
        return await self.account.read(lambda: self.client.download_media(photo, file=bytes))

    async def sessions(self):
        result = await self.rpc(functions.account.GetAuthorizationsRequest())
        authorizations = tuple(result.authorizations)
        known = {item.hash for item in authorizations if not item.current}
        new = 0 if self._known_sessions is None else len(known - self._known_sessions)
        self._known_sessions = known
        if new:
            await self.record("login_detected", "ok")
        return authorizations, new

    async def revoke(self, session_hash):
        sessions, _ = await self.sessions()
        if not any(item.hash == session_hash and not item.current for item in sessions):
            raise LookupError
        result = await self.mutate("session_revoke",
                                   functions.account.ResetAuthorizationRequest(session_hash))
        sessions, _ = await self.sessions()
        return result is True and all(item.hash != session_hash for item in sessions)

    async def two_factor_enabled(self):
        response = await self.rpc(functions.account.GetPasswordRequest())
        return bool(response.has_password)

    async def privacy(self, key):
        response = await self.rpc(functions.account.GetPrivacyRequest(PRIVACY_KEYS[key]()))
        return [(PRIVACY_RULES.get(type(rule), "custom"),
                 len(getattr(rule, "users", ()) or getattr(rule, "chats", ())))
                for rule in response.rules]
