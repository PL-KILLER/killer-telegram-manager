import asyncio
import re
from dataclasses import dataclass
from secrets import token_urlsafe
from time import monotonic


@dataclass(frozen=True)
class Action:
    name: str
    target: object
    values: tuple
    label: str
    expires: float


class Control:
    def __init__(self, management, backups):
        self.management = management
        self.backups = backups
        self.pending = {}
        self.lock = asyncio.Lock()

    def prepare(self, name, target, label, *values):
        now = monotonic()
        self.pending = {key: action for key, action in self.pending.items() if action.expires > now}
        if len(self.pending) >= 128:
            self.pending.pop(next(iter(self.pending)))
        token = token_urlsafe(18)
        self.pending[token] = Action(name, target, values, label, now + 120)
        return token

    def cancel(self, token):
        return self.pending.pop(token, None)

    async def confirm(self, token):
        action = self.pending.pop(token, None)
        if not action or action.expires <= monotonic():
            raise LookupError
        async with self.lock:
            return await self.execute(action)

    async def execute(self, action):
        owner = self.management
        target, values = action.target, action.values
        if action.name == "leave":
            outcome = await owner.service.leave(target)
            await owner.record("leave", outcome)
            return outcome in ("left", "already_left", "refresh_failed", "already_refresh_failed")
        if action.name == "contact_delete":
            return await owner.delete_contact(target)
        if action.name == "contact_edit":
            return await owner.upsert_contact(*values, user_id=target)
        if action.name == "contact_add":
            return await owner.upsert_contact(*values, username=target)
        if action.name == "profile_edit":
            return await owner.set_profile(target, *values)
        if action.name == "message_delete":
            return await owner.delete_message(target, *values)
        if action.name == "draft_save":
            return await owner.save_draft(target, *values)
        if action.name == "revoke":
            return await owner.revoke(target)
        if action.name == "unblock":
            return await owner.unblock(target)
        if action.name == "search_clear":
            await asyncio.to_thread(owner.store.searches, clear=True)
            return True
        if action.name in ("archive", "pin"):
            return await owner.dialog_setting(target, action.name, *values)
        raise LookupError


def valid_username(value):
    return bool(re.fullmatch(r"[A-Za-z0-9_]{1,32}", value))
