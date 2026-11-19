import asyncio
import json
from time import monotonic

from telethon import errors, functions, types, utils

from app.telegram_client import FloodDelay


class AutoRead:
    modes = {"messages", "mentions", "both"}
    intervals = {30, 60, 300, 900}

    def __init__(self, workspace):
        self.workspace = workspace
        self.lock = asyncio.Lock()
        self.rules = None
        self.due = {}
        self.task = None

    async def load(self):
        if self.rules is None:
            self.rules = json.loads(await asyncio.to_thread(
                self.workspace.store.preference, "auto_read", "{}"))

    async def get(self, peer):
        async with self.lock:
            await self.load()
            return self.rules.get(str(peer))

    async def set(self, peer, mode, interval):
        chat = self.workspace.service.chat(peer)
        if not chat or chat.kind not in {"c", "g"}:
            raise LookupError
        if mode not in self.modes | {"off"} or interval not in self.intervals:
            raise ValueError
        async with self.lock:
            await self.load()
            updated = dict(self.rules)
            key = str(peer)
            if mode == "off":
                updated.pop(key, None)
                self.due.pop(key, None)
            else:
                updated[key] = {"mode": mode, "interval": interval}
                self.due[key] = 0
            await asyncio.to_thread(self.workspace.store.set_preference,
                                    "auto_read", json.dumps(updated))
            self.rules = updated

    def start(self):
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self.run())

    async def close(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)

    async def run(self):
        while self.workspace.authorized:
            try:
                await self.tick()
            except FloodDelay as error:
                await asyncio.sleep(max(10, error.args[0]))
            except (errors.UnauthorizedError, errors.AuthKeyError):
                self.workspace.authorized = self.workspace.service.ready = False
                return
            except (errors.RPCError, OSError, TimeoutError):
                await asyncio.sleep(30)
            await asyncio.sleep(10)

    async def tick(self):
        service = self.workspace.service
        if not service.ready:
            return
        now = monotonic()
        async with self.lock:
            await self.load()
            pending = [(peer, rule) for peer, rule in self.rules.items()
                       if self.due.get(peer, 0) <= now and int(peer) in service.entities]
        # Small batches avoid starving the user's interactive Telegram operations.
        for start in range(0, len(pending), 16):
            batch = {}
            for peer, rule in pending[start:start + 16]:
                entity = service.entities.get(int(peer))
                chat = service.chat(int(peer))
                if entity is not None and chat and chat.kind in {"c", "g"}:
                    batch[int(peer)] = (utils.get_input_peer(entity), rule)
                self.due[peer] = now + rule["interval"]
            if not batch:
                continue
            account = service.account
            result = await account.read(lambda: account.client(functions.messages.GetPeerDialogsRequest(
                [types.InputDialogPeer(entity) for entity, _ in batch.values()])))
            for dialog in result.dialogs:
                peer = utils.get_peer_id(dialog.peer)
                if peer not in batch or not isinstance(dialog, types.Dialog):
                    continue
                entity, rule = batch[peer]
                async with self.lock:
                    if self.rules.get(str(peer)) is not rule or not self.workspace.authorized:
                        continue
                    row = service.dialog_rows.get(peer)
                    try:
                        if rule["mode"] in {"messages", "both"} and dialog.unread_count and dialog.top_message > 0:
                            await account.request(lambda: account.client.send_read_acknowledge(
                                entity, max_id=dialog.top_message))
                            if row:
                                row.unread_count = 0
                        if rule["mode"] in {"mentions", "both"} and dialog.unread_mentions_count:
                            await account.request(lambda: account.client(
                                functions.messages.ReadMentionsRequest(entity)))
                    except (errors.ChannelPrivateError, errors.ChatIdInvalidError):
                        continue
