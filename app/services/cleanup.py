import asyncio
import json
import os
import re
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from secrets import token_urlsafe

from telethon import errors, functions, utils

from app.telegram_client import FloodDelay, classify


class Cleanup:
    def __init__(self, workspace):
        self.workspace = workspace
        self.service = workspace.service
        self.account = workspace.management.account
        self.directory = workspace.backups.directory.parent / "cleanup"
        self.cipher = workspace.backups.cipher
        self.job = None
        self.task = None

    def status(self):
        if self.job is None:
            return None
        return {**self.job, "items": [dict(item) for item in self.job["items"]]}

    def start(self, peers):
        if self.task and not self.task.done():
            raise ValueError("A cleanup is already running")
        if not peers or len(set(peers)) != len(peers):
            raise ValueError("Invalid selection")
        chats = [self.service.chat(peer) for peer in peers]
        if not self.service.ready or any(not chat or chat.kind not in ("c", "g", "b") for chat in chats):
            raise ValueError("The selection changed. Open the chat list again.")
        self.job = {
            "id": token_urlsafe(12), "phase": "backup", "backup": None, "wait": None,
            "items": [{"id": str(chat.peer), "title": chat.title, "kind": chat.kind,
                       "status": "pending"} for chat in chats],
        }
        self.task = asyncio.create_task(self._run(chats))
        return self.status()

    async def close(self):
        if self.task and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)

    def list_backups(self):
        if not self.directory.exists():
            return []
        return [path.stem for path in sorted(self.directory.glob("*.fernet"), reverse=True)
                if not path.is_symlink() and re.fullmatch(r"\d{8}T\d{12}Z", path.stem)]

    def read_backup(self, name):
        if not re.fullmatch(r"\d{8}T\d{12}Z", name):
            raise LookupError
        path = self.directory / (name + ".fernet")
        if not path.is_file() or path.is_symlink():
            raise LookupError
        return json.loads(self.cipher.decrypt(path.read_bytes()))

    def _save(self, rows):
        self.directory.mkdir(mode=0o700, exist_ok=True)
        name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        payload = self.cipher.encrypt(json.dumps({"created": name, "items": rows},
                                                 ensure_ascii=False).encode())
        fd, temp = tempfile.mkstemp(dir=self.directory)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, self.directory / (name + ".fernet"))
        finally:
            Path(temp).unlink(missing_ok=True)
        return name

    async def _metadata(self, chat):
        entity = self.service.entities[chat.peer]
        public = f"https://t.me/{chat.username}" if chat.username else None
        info = {**asdict(chat), "peer": str(chat.peer), "entity_id": str(chat.entity_id),
                "public_url": public, "invite": None, "about": None,
                "members": getattr(entity, "participants_count", None)}
        if chat.kind in ("c", "g"):
            try:
                full = (await self.account.full_info(entity)).full_chat
                invite = getattr(full, "exported_invite", None)
                if not getattr(invite, "revoked", False):
                    info["invite"] = getattr(invite, "link", None)
                info["about"] = getattr(full, "about", None)
                count = getattr(full, "participants_count", None)
                if count is not None:
                    info["members"] = count
                participants = getattr(getattr(full, "participants", None), "participants", None)
                if participants is not None:
                    info["members"] = len(participants)
            except (errors.ChatAdminRequiredError, errors.ChannelPrivateError):
                pass
        return info

    async def _block(self, chat):
        entity = self.service.entities.get(chat.peer)
        if classify(entity) != chat:
            raise LookupError
        peer = utils.get_input_peer(entity)
        result = await self.account.request(
            lambda: self.account.client(functions.contacts.BlockRequest(peer)))
        return "blocked" if result is True else "unknown"

    async def _run(self, chats):
        job = self.job
        try:
            async with self.workspace.control.lock, self.service.lock:
                if any(self.service.chat(chat.peer) != chat for chat in chats):
                    raise LookupError
                metadata = [await self._paced(job, self._metadata, chat) for chat in chats]
                job["backup"] = await asyncio.to_thread(self._save, metadata)
                job["phase"] = "running"
                departed = []
                for chat, item in zip(chats, job["items"], strict=True):
                    item["status"] = "working"
                    try:
                        operation = self._block if chat.kind == "b" else self.service.leave_one
                        outcome = await self._paced(job, operation, chat)
                    except errors.UserCreatorError:
                        outcome = "owner"
                    except (LookupError, errors.RPCError, OSError, TimeoutError):
                        outcome = "unknown"
                    item["status"] = outcome
                    if outcome in ("left", "already_left"):
                        departed.append(chat.peer)
                if departed:
                    try:
                        await self.service._synchronize()
                    except Exception:
                        for peer in departed:
                            self.service.entities.pop(peer, None)
                            self.service.cache.pop(peer, None)
                        self.service.ready = False
                        job["refresh_failed"] = True
                job["phase"] = "done"
        except FloodDelay as error:
            job["wait"] = error.args[0]
            job["phase"] = "failed"
        except Exception:
            job["phase"] = "failed"
        finally:
            for item in job["items"]:
                if item["status"] == "pending":
                    item["status"] = "skipped"

    @staticmethod
    async def _paced(job, operation, chat):
        while True:
            try:
                return await operation(chat)
            except FloodDelay as error:
                job["wait"] = max(1, error.args[0])
                try:
                    await asyncio.sleep(job["wait"])
                finally:
                    job["wait"] = None
