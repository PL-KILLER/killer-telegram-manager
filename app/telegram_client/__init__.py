import asyncio
import time

from telethon import errors, functions, types, utils

from app.database import Chat


def classify(entity):
    if isinstance(entity, types.Channel) and not entity.left:
        if entity.megagroup or entity.gigagroup:
            kind, subtype = "g", "سوپرگروه"
        elif entity.broadcast:
            kind, subtype = "c", "کانال"
        else:
            return None
    elif isinstance(entity, types.Chat) and not (
        entity.left or entity.deactivated or entity.migrated_to
    ):
        kind, subtype = "g", "گروه"
    elif isinstance(entity, types.User) and not entity.deleted:
        kind = "b" if entity.bot else "p"
        title = utils.get_display_name(entity) or entity.username or str(entity.id)
        return Chat(utils.get_peer_id(entity), entity.id, kind, "bot" if entity.bot else "private",
                    title, entity.username)
    else:
        return None
    username = getattr(entity, "username", None)
    if not username:
        username = next((item.username for item in getattr(entity, "usernames", None) or []
                         if item.active), None)
    return Chat(utils.get_peer_id(entity), entity.id, kind, subtype, entity.title, username)


class FloodDelay(Exception):
    pass


class DialogSnapshot(dict):
    def __init__(self):
        super().__init__()
        self.archived = set()
        self.rows = {}


class TelegramAccount:
    def __init__(self, client, owner_id):
        self.client = client
        self.owner_id = owner_id
        self.resume_at = 0

    async def read(self, operation):
        return await self.request(operation, retry=True)

    async def request(self, operation, *, retry=False):
        for attempt in range(3 if retry else 1):
            remaining = self.resume_at - time.monotonic()
            if remaining > 0:
                raise FloodDelay(int(remaining) + 1)
            try:
                async with asyncio.timeout(45):
                    if not self.client.is_connected():
                        await self.client.connect()
                    return await operation()
            except errors.FloodWaitError as error:
                self.resume_at = max(self.resume_at, time.monotonic() + error.seconds)
                raise FloodDelay(error.seconds) from None
            except (OSError, TimeoutError, errors.ServerError):
                if not retry or attempt == 2:
                    raise
                await asyncio.sleep(2 ** attempt)

    async def membership(self, entity):
        if isinstance(entity, types.Channel):
            try:
                result = await self.read(lambda: self.client(
                    functions.channels.GetParticipantRequest(entity, types.InputPeerSelf())))
            except errors.UserNotParticipantError:
                return False
            participant = result.participant
            return not (isinstance(participant, types.ChannelParticipantLeft)
                        or getattr(participant, "left", False))
        result = await self.full_info(entity)
        chat = next((chat for chat in result.chats if chat.id == entity.id), None)
        if isinstance(chat, types.ChatForbidden) or getattr(chat, "left", False):
            return False
        participants = result.full_chat.participants
        if isinstance(participants, types.ChatParticipants):
            return any(item.user_id == self.owner_id for item in participants.participants)
        if getattr(participants, "self_participant", None):
            return True
        return None

    async def leave(self, entity):
        if isinstance(entity, types.Channel):
            request = functions.channels.LeaveChannelRequest(entity)
        else:
            request = functions.messages.DeleteChatUserRequest(
                entity.id, types.InputUserSelf(), revoke_history=False)
        result = await self.request(lambda: self.client(request))
        return any(type(chat) is type(entity) and chat.id == entity.id and chat.left
                   for chat in getattr(result, "chats", ()))

    async def full_info(self, entity):
        request = (functions.channels.GetFullChannelRequest(entity)
                   if isinstance(entity, types.Channel)
                   else functions.messages.GetFullChatRequest(entity.id))
        return await self.read(lambda: self.client(request))

    async def photo(self, entity):
        return await self.read(lambda: self.client.download_profile_photo(entity, file=bytes))

    async def snapshot(self):
        # Walk every folder and commit only after all pages have arrived.
        async def collect():
            dialogs = DialogSnapshot()
            iterator = self.client.iter_dialogs(limit=None, ignore_migrated=False)
            page_waits = 0
            while True:
                try:
                    # The deadline applies to each step, not to the whole account.
                    async with asyncio.timeout(45):
                        dialog = await anext(iterator)
                except StopAsyncIteration:
                    break
                except errors.FloodWaitError as error:
                    if error.seconds > 120 or page_waits >= 3:
                        raise
                    # Leave the iterator at its current offset while Telegram cools down.
                    page_waits += 1
                    self.resume_at = max(self.resume_at, time.monotonic() + error.seconds)
                    await asyncio.sleep(max(0, self.resume_at - time.monotonic()))
                    continue
                page_waits = 0
                dialogs[dialog.id] = dialog.entity
                dialogs.rows[dialog.id] = dialog
                if getattr(dialog, "archived", False):
                    dialogs.archived.add(dialog.id)
            return dialogs

        # Keep the overall scan independent of the single-request deadline.
        for attempt in range(3):
            remaining = self.resume_at - time.monotonic()
            if remaining > 0:
                raise FloodDelay(int(remaining) + 1)
            try:
                if not self.client.is_connected():
                    await self.client.connect()
                return await collect()
            except errors.FloodWaitError as error:
                self.resume_at = max(self.resume_at, time.monotonic() + error.seconds)
                raise FloodDelay(error.seconds) from None
            except (OSError, TimeoutError, errors.ServerError):
                if attempt == 2:
                    raise
                await asyncio.sleep(2 ** attempt)
