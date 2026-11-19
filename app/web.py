import asyncio
import csv
import io
from collections import deque
from pathlib import Path
from time import monotonic

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from telethon import errors, utils
from cryptography.fernet import InvalidToken

from app.security.webapp import verify_init_data
from app.services.control import valid_username
from app.services.integrations import BUILTINS
from app.services.management import PRIVACY_KEYS
from app.telegram_client import FloodDelay


class Command(BaseModel):
    action: str = Field(max_length=40)
    target: str = Field(default="", max_length=120)
    value: str = Field(default="", max_length=4096)
    extra: str = Field(default="", max_length=128)


class Listing(BaseModel):
    section: str = Field(max_length=24)
    page: int = Field(default=0, ge=0, le=10000)
    query: str = Field(default="", max_length=150)
    kind: str = Field(default="all", max_length=16)
    privacy: str = Field(default="all", pattern="^(all|public|private)$")
    sort: str = Field(default="name", pattern="^(name|recent|latest|unread|type)$")
    state: str = Field(default="", pattern="^(|unread|pinned|muted)$")
    peer: str = Field(default="", max_length=25)
    mode: str = Field(default="", max_length=20)
    after: str = Field(default="", pattern="^([0-9]{4}-[0-9]{2}-[0-9]{2})?$")
    before: str = Field(default="", pattern="^([0-9]{4}-[0-9]{2}-[0-9]{2})?$")
    sender: str = Field(default="", pattern="^(@?[a-zA-Z0-9_]{1,32})?$")
    tag: str = Field(default="", max_length=64)


def create_app(workspace, config):
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    calls = deque()
    webroot = Path(__file__).resolve().parents[1] / "miniapp"
    service = workspace.service
    owner = workspace.management
    control = workspace.control
    store = workspace.store

    @app.middleware("http")
    async def response_headers(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    async def authorize(request: Request, x_telegram_init_data: str = Header(default="")):
        if not verify_init_data(x_telegram_init_data, config.bot_token, config.owner_id):
            raise HTTPException(403, "Open this Mini App from the authorized Telegram account.")
        now = monotonic()
        while calls and now - calls[0] >= 60:
            calls.popleft()
        if len(calls) >= 90:
            raise HTTPException(429, "Too many requests.")
        calls.append(now)
        if request.method == "POST":
            try:
                length = int(request.headers.get("content-length", "0"))
            except ValueError:
                raise HTTPException(400, "Invalid request length") from None
            if not 0 < length <= 16384:
                raise HTTPException(413, "Request body too large")

    async def connected(_=Depends(authorize)):
        if not workspace.authorized:
            raise HTTPException(503, "The personal account is not connected.")

    @app.exception_handler(FloodDelay)
    async def flood(_, error):
        return JSONResponse({"detail": "Telegram rate limit", "wait": error.args[0]},
                            status_code=429, headers={"Retry-After": str(error.args[0])})

    @app.exception_handler(LookupError)
    async def missing(_, error):
        return JSONResponse({"detail": "This item expired or is unavailable."}, status_code=404)

    @app.exception_handler(ValueError)
    async def invalid(_, error):
        return JSONResponse({"detail": "Invalid selection."}, status_code=400)

    @app.exception_handler(errors.RPCError)
    async def telegram_error(_, error):
        if isinstance(error, (errors.UnauthorizedError, errors.AuthKeyError)):
            workspace.authorized = service.ready = False
        return JSONResponse({"detail": "Telegram could not complete the operation.",
                             "code": type(error).__name__}, status_code=409)

    @app.exception_handler(OSError)
    async def connection_error(_, error):
        return JSONResponse({"detail": "The operation could not be verified."}, status_code=503)

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.get("/api/overview", dependencies=[Depends(authorize)])
    async def overview():
        return await workspace.overview()

    @app.get("/api/profile", dependencies=[Depends(connected)])
    async def profile():
        return await workspace.profile()

    @app.get("/api/analytics", dependencies=[Depends(connected)])
    async def analytics():
        return await asyncio.to_thread(store.analytics)

    @app.get("/api/security", dependencies=[Depends(connected)])
    async def security():
        return await workspace.security()

    @app.get("/api/privacy/{key}", dependencies=[Depends(connected)])
    async def privacy(key: str):
        if key not in PRIVACY_KEYS:
            raise LookupError
        return await owner.privacy(key)

    @app.get("/api/list/{section}", dependencies=[Depends(connected)])
    async def browse(section: str, page: int = Query(0, ge=0, le=10000),
                     query: str = Query("", max_length=150), kind: str = Query("all", max_length=16),
                     privacy: str = Query("all", pattern="^(all|public|private)$"),
                     sort: str = Query("name", pattern="^(name|recent|latest|unread|type)$"),
                     state: str = Query("", pattern="^(|unread|pinned|muted)$"),
                     peer: str = Query("", max_length=25), mode: str = Query("", max_length=20)):
        peer = "me" if peer == "me" else int(peer) if peer else None
        rows, more = await workspace.browse(section, page, query, kind, privacy, peer, mode, sort,
                                            state=state)
        return {"items": rows, "more": more}

    @app.get("/api/chat/{peer}", dependencies=[Depends(connected)])
    async def chat(peer: int):
        return await workspace.chat_detail(peer)

    @app.get("/api/contact/{user_id}", dependencies=[Depends(connected)])
    async def contact(user_id: int):
        user = await owner.contact(user_id)
        return {"id": str(user.id), "first_name": user.first_name or "",
                "last_name": user.last_name or "", "username": user.username or "",
                "phone": user.phone or ""}

    @app.get("/api/contact/{user_id}/groups", dependencies=[Depends(connected)])
    async def contact_groups(user_id: int):
        return await owner.common_chats(user_id)

    @app.post("/api/browse", dependencies=[Depends(connected)])
    async def private_browse(filters: Listing):
        if filters.query and filters.page == 0:
            ciphertext = config.cipher.encrypt(filters.query.encode())
            await asyncio.to_thread(store.searches, ciphertext)
        peer = "me" if filters.peer == "me" else int(filters.peer) if filters.peer else None
        rows, more = await workspace.browse(
            filters.section, filters.page, filters.query, filters.kind,
            filters.privacy, peer, filters.mode, filters.sort, filters.after, filters.before,
            int(filters.sender) if filters.sender.isdecimal() else filters.sender, filters.tag,
            filters.state)
        return {"items": rows, "more": more}

    @app.get("/api/search-history", dependencies=[Depends(connected)])
    async def search_history():
        encrypted = await asyncio.to_thread(store.searches)
        queries = []
        for item in encrypted:
            try:
                value = config.cipher.decrypt(item).decode()
            except (InvalidToken, UnicodeError):
                continue
            if value not in queries:
                queries.append(value)
        return queries

    @app.get("/api/collections", dependencies=[Depends(connected)])
    async def collections():
        return await asyncio.to_thread(store.collections)

    @app.get("/api/photo/{peer}", dependencies=[Depends(connected)])
    async def photo(peer: int):
        payload = (await service.details(peer)).photo
        if not payload:
            raise LookupError
        return Response(payload, media_type="image/jpeg")

    @app.get("/api/profile-photo", dependencies=[Depends(connected)])
    async def profile_photo():
        payload = await owner.account.photo("me")
        if not payload:
            raise LookupError
        return Response(payload, media_type="image/jpeg")

    @app.get("/api/profile-photos", dependencies=[Depends(connected)])
    async def profile_photos(page: int = Query(0, ge=0, le=100)):
        photos = await owner.profile_photos(page * 8, 9)
        return {"items": [workspace.ref("profile_photo", item) for item in photos[:8]],
                "more": len(photos) > 8}

    @app.get("/api/profile-photos/{reference}", dependencies=[Depends(connected)])
    async def profile_photo_item(reference: str):
        photo = workspace.resolve(reference, "profile_photo")
        payload = await owner.profile_photo(photo)
        if not payload:
            raise LookupError
        return Response(payload, media_type="image/jpeg")

    @app.get("/api/message/{reference}", dependencies=[Depends(connected)])
    async def message_detail(reference: str):
        message, peer, mode = workspace.resolve(reference, "message")
        item = workspace.message_item(message, peer, mode)
        if not item["protected"]:
            item["info"] = (message.message or "")[:4096]
        item["sender"] = str(message.sender_id or "")
        return item

    @app.get("/api/media/{reference}", dependencies=[Depends(connected)])
    async def media(reference: str):
        message, _, _ = workspace.resolve(reference, "message")
        payload = await owner.media(message)
        if not payload:
            raise LookupError
        return Response(payload, media_type="application/octet-stream",
                        headers={"Content-Disposition": 'attachment; filename="telegram-media"'})

    @app.get("/api/backup/{name}", dependencies=[Depends(connected)])
    async def backup(name: str, export: bool = False):
        if export:
            path = await asyncio.to_thread(workspace.backups.path, name)
            return FileResponse(path, filename=path.name, media_type="application/octet-stream")
        return await asyncio.to_thread(workspace.backups.inspect, name)

    @app.get("/api/export/{format}", dependencies=[Depends(connected)])
    async def export_rows(format: str):
        if format not in ("json", "csv"):
            raise LookupError
        overview = await workspace.overview()
        analytics = await asyncio.to_thread(store.analytics)
        if format == "json":
            return JSONResponse({"overview": overview, "analytics": analytics})
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(("time", "dialogs", "channels", "groups", "archived"))
        writer.writerows(analytics["history"])
        return Response(output.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="killer-statistics.csv"'})

    @app.get("/api/settings", dependencies=[Depends(connected)])
    async def settings():
        return {key: await asyncio.to_thread(store.preference, key, fallback)
                for key, fallback in {"language": "fa", "login_alerts": "on",
                                      "automatic_backup": "off", "sync_enabled": "on",
                                      "backup_keep": "10", "summary": "off",
                                      "inactivity_report": "off"}.items()}

    @app.get("/api/plugins", dependencies=[Depends(connected)])
    async def plugins():
        return [{"id": key, "version": value.version, "permissions": value.permissions,
                 "enabled": await asyncio.to_thread(store.preference, "plugin:" + key, "on") == "on"}
                for key, value in BUILTINS.items()]

    @app.get("/api/inactivity", dependencies=[Depends(connected)])
    async def inactivity(days: int = Query(default=90, ge=14, le=365)):
        if await asyncio.to_thread(store.preference, "plugin:inactivity", "on") != "on":
            raise LookupError
        return await asyncio.to_thread(store.inactive, days)

    @app.post("/api/command", dependencies=[Depends(connected)])
    async def command(data: Command):
        action, target, value = data.action, data.target, data.value
        if action == "auto_read":
            await workspace.auto_read.set(int(target), value, int(data.extra))
            workspace.auto_read.start()
            return {"ok": True}
        if action == "cleanup_start":
            return workspace.cleanup.start([int(peer) for peer in value.split(",")])
        if action == "cleanup_stage":
            peers = [int(peer) for peer in value.split(",")]
            if any(peer not in service.entities for peer in peers):
                raise LookupError
            if not target:
                target = workspace.ref("cleanup_draft", {})
            draft = workspace.resolve(target, "cleanup_draft")
            draft.update(dict.fromkeys(peers))
            return {"token": target}
        if action == "cleanup_commit":
            draft = workspace.resolve(target, "cleanup_draft")
            result = workspace.cleanup.start(list(draft))
            workspace.refs.pop(target, None)
            return result
        if action == "sync":
            return {"ok": await workspace.sync()}
        if action == "contacts_sync":
            return {"count": len(await owner.contacts(refresh=True))}
        if action == "backup":
            return {"name": await workspace.backup()}
        if action == "confirm":
            return {"ok": bool(await control.confirm(target))}
        if action == "cancel":
            return {"ok": control.cancel(target) is not None}
        if action in ("favorite", "tag"):
            peer = int(target)
            owner.entity(peer)
            kwargs = {"favorite": value == "1"} if action == "favorite" else {"tag": value[:64]}
            return await asyncio.to_thread(store.organize, peer, **kwargs)
        if action == "preference":
            allowed = {"login_alerts", "automatic_backup", "sync_enabled", "summary",
                       "inactivity_report", *("plugin:" + key for key in BUILTINS)}
            if not ((target in allowed and value in {"on", "off"})
                    or (target == "language" and value in {"fa", "en"})
                    or (target == "backup_keep" and value.isdecimal() and 1 <= int(value) <= 100)):
                raise ValueError
            await asyncio.to_thread(store.set_preference, target, value)
            return {"ok": True}
        name, key, label, values = await prepare(action, target, value, data.extra)
        return {"token": control.prepare(name, key, label, *values), "label": label}

    @app.get("/api/cleanup", dependencies=[Depends(connected)])
    async def cleanup_status():
        return {"job": workspace.cleanup.status(),
                "backups": await asyncio.to_thread(workspace.cleanup.list_backups)}

    @app.get("/api/cleanup/{name}", dependencies=[Depends(connected)])
    async def cleanup_backup(name: str):
        return await asyncio.to_thread(workspace.cleanup.read_backup, name)

    async def prepare(action, target, value, extra):
        if action == "search_clear":
            return action, None, "", ()
        if action == "profile_edit":
            if target not in ("first_name", "last_name", "username", "about") or len(value) > 160:
                raise ValueError
            if (target == "username" and value and not valid_username(value)) or (
                target == "first_name" and not value
            ):
                raise ValueError
            return action, target, f"{target} → {value}", (value,)
        if action in ("contact_add", "contact_edit", "contact_delete"):
            if action == "contact_add":
                if not valid_username(target.lstrip("@")):
                    raise ValueError
                key, label = "@" + target.lstrip("@"), target
            else:
                key = int(target)
                user = await owner.contact(key)
                label = user.first_name or str(key)
            if action != "contact_delete" and (not value or len(value) > 64 or len(extra) > 64):
                raise ValueError
            return action, key, f"{label} → {value} {extra}".strip(), (value, extra)
        if action == "revoke":
            session = workspace.resolve(target, "session")
            if session.current:
                raise ValueError
            return action, session.hash, session.device_model, ()
        if action == "unblock":
            entity = workspace.resolve(target, "blocked")
            return action, entity, utils.get_display_name(entity) or str(entity.id), ()
        if action == "message_delete":
            message, peer, mode = workspace.resolve(target, "message")
            if not peer or mode != "scheduled" and peer != "me" and not message.out:
                raise ValueError
            chat = service.chat(peer) if peer != "me" else None
            title = chat.title if chat else "Saved Messages"
            return action, peer, f"{title} · #{message.id}", (message.id, mode == "scheduled")
        peer = int(target)
        chat = service.chat(peer)
        if not chat:
            raise LookupError
        if action in ("archive", "pin") and value in ("0", "1"):
            return action, peer, chat.title, (value == "1",)
        if action == "draft_save":
            return action, peer, f"{chat.title} · {value[:120]}", (value,)
        raise ValueError

    @app.get("/")
    async def index():
        return FileResponse(webroot / "index.html", headers={"Cache-Control": "no-store"})

    app.mount("/assets", StaticFiles(directory=webroot / "assets"), name="assets")
    return app
