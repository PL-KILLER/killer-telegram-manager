import asyncio
from html import escape
import json
from collections import deque
from secrets import token_urlsafe
from time import monotonic

from telethon import errors

from app.handlers.api import BotError
from app.i18n import LANGUAGES, translate
from app.keyboards import FILTERS, button, dashboard, keyboard, page_keys
from app.telegram_client import FloodDelay
from app.utils import confirmation_title


LABELS = {"c": "channels", "g": "groups"}
LEAVE_STATUS = {
    "left": "خروج در تلگرام تأیید شد و فهرست تازه شد.",
    "already_left": "تلگرام تأیید کرد که از قبل عضو نبودید. فهرست تازه شد.",
    "refresh_failed": "خروج در تلگرام تأیید شد. تازه‌سازی فهرست ناموفق بود.",
    "already_refresh_failed": "تلگرام تأیید کرد که از قبل عضو نبودید. تازه‌سازی فهرست ناموفق بود.",
    "unknown": "وضعیت عضویت قابل تأیید نبود. پیش از تلاش دوباره، فهرست را تازه کنید.",
    "still_member": "تلگرام همچنان عضویت شما را نشان می‌دهد.",
}


class Bot:
    def __init__(self, api, service, *, public_start_url=None, username=None):
        self.api = api
        self.service = service
        self.authorized = False
        self.sign_in_state = "sign_in"
        self.views = {}
        self.confirmations = {}
        self.prompts = {}
        self.jobs = set()
        self.refreshing = False
        self.leaving = set()
        self.panel = None
        self.language = "fa"
        self.requests = deque()
        self.public_start_url = public_start_url
        self.username = username

    def t(self, key):
        return translate(self.language, key)

    def l(self, fa, en):
        return en if self.language == "en" else fa

    async def run(self):
        offset = None
        delay = 1
        while True:
            try:
                batch = await self.api.call("getUpdates", offset=offset, timeout=25,
                                            allowed_updates=["message", "callback_query"])
                delay = 1
            except BotError as error:
                if error.code in (401, 403, 409):
                    raise
                await asyncio.sleep(delay)
                delay = min(30, delay * 2)
                continue
            for update in batch:
                offset = update["update_id"] + 1
                owner = self.allowed(update)
                guest = None if owner else self.guest_start(update)
                if not owner and guest is None:
                    continue
                now = monotonic()
                while self.requests and now - self.requests[0] >= 60:
                    self.requests.popleft()
                if len(self.requests) >= 120:
                    continue
                self.requests.append(now)
                if len(self.jobs) >= 24:
                    await asyncio.wait(self.jobs, return_when=asyncio.FIRST_COMPLETED)
                task = asyncio.create_task(self.handle(update) if owner else self.welcome_guest(guest))
                self.jobs.add(task)
                task.add_done_callback(self.jobs.discard)

    def guest_start(self, update):
        if not self.public_start_url or "callback_query" in update:
            return None
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        actor = message.get("from") or {}
        user_id = actor.get("id")
        text = message.get("text", "").split(maxsplit=1)
        commands = {"/start"}
        if self.username:
            commands.add(f"/start@{self.username.lower()}")
        if (chat.get("type") != "private" or type(user_id) is not int or user_id <= 0
                or user_id != chat.get("id") or actor.get("is_bot") or not text
                or text[0].lower() not in commands):
            return None
        return user_id

    async def welcome_guest(self, user_id):
        try:
            await self.api.call(
                "sendMessage", chat_id=user_id,
                text="برای اتصال و مدیریت حساب خودت، مینی‌اپ را باز کن.\nOpen the Mini App to connect your account.",
                reply_markup=keyboard([{"text": "باز کردن مینی‌اپ · Open Mini App",
                                        "web_app": {"url": self.public_start_url}}]),
            )
        except BotError:
            pass

    def allowed(self, update):
        callback = update.get("callback_query")
        message = (callback or {}).get("message") if callback else update.get("message")
        actor = (callback or message or {}).get("from", {})
        chat = (message or {}).get("chat", {})
        return (chat.get("type") == "private"
                and actor.get("id") == chat.get("id") == self.api.owner_id)

    async def handle(self, update):
        try:
            for entries in (self.views, self.confirmations, self.prompts):
                for key, value in list(entries.items()):
                    if value[0] <= monotonic():
                        entries.pop(key, None)
            if callback := update.get("callback_query"):
                try:
                    await self.api.call("answerCallbackQuery", callback_query_id=callback["id"])
                except BotError:
                    pass
                await self.callback(callback.get("data", ""), callback["message"]["message_id"])
            else:
                await self.message(update["message"])
        except BotError:
            print("ارسال پاسخ بات ناموفق بود.", flush=True)
        except FloodDelay as error:
            await self.report(f"{self.t('wait')} {error.args[0]} {self.t('seconds')}")
        except (errors.UnauthorizedError, errors.AuthKeyError):
            self.authorized = self.service.ready = False
            self.sign_in_state = "expired_session"
            if self.panel:
                self.panel.workspace.authorized = False
            await self.report(self.t(self.sign_in_state))
        except LookupError:
            await self.report(self.t("expired"))
        except errors.UserCreatorError:
            await self.report(self.t("creator"))
        except (errors.RPCError, OSError, TimeoutError) as error:
            await self.report(f"{self.t('failed')} ({type(error).__name__})")
        except Exception as error:
            print(json.dumps({"event": "bot_handler_failed", "error": type(error).__name__}),
                  flush=True)
            await self.report(self.t("failed"))

    async def report(self, text):
        try:
            await self.api.send(text)
        except BotError:
            print(text, flush=True)

    async def show_home(self, message_id=None):
        if not self.authorized or self.panel and not self.panel.workspace.authorized:
            state = self.sign_in_state if not self.authorized else "expired_session"
            await self.api.send(self.t(state))
            return
        if self.panel:
            self.language = await asyncio.to_thread(self.service.store.preference, "language", "fa")
        if self.service.ready:
            channels, groups, dialogs = await asyncio.to_thread(self.service.store.counts)
            text = (f"<b>KILLER ALLPLUS</b>\n{self.t('home')}\n\n"
                    f"{self.t('dialogs')}  <b>{dialogs:,}</b>\n"
                    f"{self.t('channels')}  <b>{channels:,}</b>  ·  "
                    f"{self.t('groups')}  <b>{groups:,}</b>")
            if self.panel:
                text += await self.panel.dashboard_status()
            if self.refreshing:
                text += f"\n\n{self.t('syncing')}"
        else:
            status = self.t("syncing") if self.refreshing else self.l(
                "برای بارگیری گفت‌وگوها، همگام‌سازی را بزنید.", "Choose Sync to load your chats.")
            text = f"<b>KILLER ALLPLUS</b>\n{self.t('home')}\n\n{status}"
        extra = self.panel.navigation() if self.panel else ()
        await self.render(text, dashboard(self.t, extra=extra), message_id)

    async def render(self, text, markup, message_id):
        if message_id is None:
            await self.api.send(text, markup, html=True)
        else:
            await self.api.edit(message_id, text, markup, html=True)

    def new_view(self, kind, query="", privacy="all"):
        view = token_urlsafe(8)
        if len(self.views) >= 128:
            del self.views[next(iter(self.views))]
        self.views[view] = monotonic() + 3600, kind, query, privacy
        return view

    async def show_list(self, view, page, message_id=None):
        context = self.views.get(view)
        if context is None:
            await self.report(self.t("expired"))
            return
        if not self.service.ready:
            await self.show_home(message_id)
            return
        _, kind, query, privacy = context
        chats, page, pages, total = await asyncio.to_thread(
            self.service.store.page, kind, query, page, 8, privacy)
        title = f"<b>{self.t(LABELS[kind])}</b>"
        if query:
            title += f"\n{self.t('search')}: {escape(query)}"
        text = f"{title}\n\n{self.t('page')} <b>{page + 1}</b> / {pages} · {total:,} {self.t('results')}"
        if not chats:
            text += f"\n{self.t('empty')}"
        await self.render(text, page_keys(chats, kind, view, page, pages, privacy, query, self.t),
                          message_id)

    async def message(self, message):
        text = message.get("text", "").strip()
        if text in ("/start", "/menu"):
            await self.show_home()
            return
        if text == "/cleanup" and self.panel and self.authorized and self.panel.workspace.authorized:
            await self.panel.cleanup_screen("c", 0, None)
            return
        if self.panel and self.authorized and self.panel.workspace.authorized:
            shortcuts = {"/profile": "profile", "/chats": "chats", "/contacts": "contacts",
                         "/messages": "messages", "/media": "media", "/security": "security",
                         "/sessions": "sessions", "/backups": "backups", "/blocked": "blocked",
                         "/stats": "analytics", "/settings": "settings"}
            if text in shortcuts:
                await self.panel.main_screen(shortcuts[text], None)
                return
            if text in ("/channels", "/groups"):
                await self.show_list(self.new_view("c" if text == "/channels" else "g"), 0)
                return
            if text == "/status":
                await self.show_home()
                return
            if text == "/help":
                await self.api.send(self.l(
                    "شروع: /start · وضعیت: /status\nگفت‌وگوها: /chats · کانال‌ها: /channels · گروه‌ها: /groups\n"
                    "پاک‌سازی: /cleanup · حساب: /profile · پیام‌ها: /messages · رسانه: /media\n"
                    "مخاطبین: /contacts · امنیت: /security · دستگاه‌ها: /sessions · مسدودها: /blocked\n"
                    "آمار: /stats · پشتیبان: /backups · تنظیمات: /settings",
                    "Home: /start · Status: /status\nChats: /chats · Channels: /channels · Groups: /groups\n"
                    "Cleanup: /cleanup · Profile: /profile · Messages: /messages · Media: /media\n"
                    "Contacts: /contacts · Security: /security · Devices: /sessions · Blocked: /blocked\n"
                    "Statistics: /stats · Backups: /backups · Settings: /settings"))
                return
        if self.panel and self.authorized and await self.panel.message(message):
            return
        reply = message.get("reply_to_message", {}).get("message_id")
        context = self.prompts.get(reply) if text and self.authorized else None
        if not context:
            return
        _, action, view, source = context
        state = self.views.get(view)
        if not state:
            del self.prompts[reply]
            await self.report(self.t("expired"))
            return
        _, kind, _, privacy = state
        if action == "jump":
            if not text.isdecimal() or len(text) > 8 or int(text) < 1:
                await self.report(self.t("page_invalid"))
                return
            del self.prompts[reply]
            await self.show_list(view, int(text) - 1, source)
        else:
            del self.prompts[reply]
            await self.show_list(self.new_view(kind, text[:150], privacy), 0, source)

    async def refresh(self, view, message_id, page=0):
        if self.refreshing:
            await self.report(self.t("syncing"))
            return
        self.refreshing = True
        try:
            if self.panel:
                await self.panel.workspace.sync()
            else:
                await self.service.synchronize()
        finally:
            self.refreshing = False
        if view == "h":
            await self.show_home(message_id)
        else:
            await self.show_list(view, page, message_id)

    async def callback(self, data, message_id):
        action, _, arg = data.partition(":")
        if action == "home" or not self.authorized or self.panel and not self.panel.workspace.authorized:
            await self.show_home(message_id)
        elif self.panel and await self.panel.callback(action, arg, message_id):
            return
        elif action == "refresh":
            view, _, page = arg.partition(":")
            await self.refresh(view, message_id, int(page) if page.isascii() and page.isdigit() else 0)
        elif action == "list" and arg in LABELS:
            await self.show_list(self.new_view(arg), 0, message_id)
        elif action == "page":
            view, _, page = arg.partition(":")
            if page.isascii() and page.isdigit():
                await self.show_list(view, int(page), message_id)
        elif action in ("search", "jump"):
            view = self.new_view(arg) if action == "search" and arg in LABELS else arg
            if view not in self.views:
                await self.show_list(view, 0, message_id)
                return
            title = self.t("page_prompt" if action == "jump" else "query_prompt")
            prompt = await self.api.send(title, {"force_reply": True})
            self.prompts[prompt["message_id"]] = monotonic() + 300, action, view, message_id
        elif action in ("filter", "clear"):
            view, _, selected = arg.partition(":")
            state = self.views.get(view)
            if not state:
                await self.show_list(view, 0, message_id)
                return
            _, kind, query, privacy = state
            if action == "clear":
                query = ""
            elif selected in FILTERS:
                if selected == privacy:
                    return
                privacy = selected
            await self.show_list(self.new_view(kind, query, privacy), 0, message_id)
        elif action in ("yes", "no"):
            await self.resolve_leave(arg, message_id, action == "yes")
        elif action in ("info", "ask") and self.service.ready:
            peer = int(arg)
            chat = self.service.chat(peer)
            if chat is None:
                raise LookupError
            if action == "info":
                await self.show_info(chat)
            elif self.panel:
                self.panel.workspace.cleanup.start([peer])
                rows = []
                if self.panel.miniapp_url:
                    url = self.panel.miniapp_url + "?view=cleanup"
                    rows.append([{"text": self.l("دیدن نتیجه", "View progress"),
                                  "web_app": {"url": url}}])
                rows.append([button(self.t("home"), "home")])
                await self.api.edit(message_id,
                                    self.l("خروج در صف ثبت شد.", "Departure queued."),
                                    keyboard(*rows))
            else:
                await self.ask_leave(chat)

    async def show_info(self, chat):
        details = await self.service.details(chat.peer)
        public = self.t("public" if chat.username else "private")
        absent = self.t("unavailable")
        title = f"<b>{escape(chat.title)}</b>\n{self.chat_kind(chat)} · {public}"
        fields = []
        if chat.username:
            fields.append(f"{self.t('username')}: @{escape(chat.username)}")
        if details.count is not None:
            fields.append(f"{self.t('members')}: <b>{details.count:,}</b>")
        if details.invite:
            fields.append(f"{self.t('link')}: {escape(details.invite)}")
        fields.extend((f"{self.t('id')}: <code>{chat.entity_id}</code>",
                       f"{self.t('peer')}: <code>{chat.peer}</code>"))
        text = f"{title}\n\n" + "\n".join(fields)
        if details.about:
            text += f"\n\n<b>{self.t('about')}</b>\n{escape(details.about)}"
        if details.partial:
            text += f"\n\n{self.t('partial')}"
        rows = []
        if chat.username:
            rows.append([{"text": self.t("open"), "url": f"https://t.me/{chat.username}",
                          "style": "primary"}])
        if self.panel:
            rows.append([button(self.l("مدیریت گفت‌وگو", "Manage chat"), f"uchat:{chat.peer}")])
        rows.append([{"text": self.t("copy"), "copy_text": {"text": str(chat.entity_id)}},
                     button(self.t("home"), "home")])
        markup = keyboard(*rows)
        if details.photo:
            # This conservative length check also covers Telegram's UTF-16 offsets.
            if len(text.encode("utf-16-le")) <= 2048:
                try:
                    await self.api.send_photo_card(details.photo, text, markup)
                    return
                except BotError as error:
                    if error.code == 0:
                        raise
            else:
                try:
                    await self.api.call("sendPhoto", photo=details.photo,
                                        chat_id=str(self.api.owner_id), protect_content="true",
                                        caption=chat.title)
                except BotError:
                    pass
        await self.api.send(text, markup, html=True)

    async def ask_leave(self, chat):
        if chat.kind not in ("c", "g"):
            raise LookupError
        token = token_urlsafe(16)
        label = (f"«{confirmation_title(chat.title)}»\n{self.t('kind')}: {self.chat_kind(chat)}"
                 f"\n{self.t('id')}: {chat.entity_id}")
        message = await self.api.send(
            f"{self.t('confirm')}\n\n{label}\n\n{self.t('expires')}",
            keyboard([button(self.t("leave"), f"yes:{token}", "danger"),
                      button(self.t("cancel"), f"no:{token}")]),
        )
        self.confirmations[token] = monotonic() + 120, chat, message["message_id"]

    def chat_kind(self, chat):
        if chat.kind == "c":
            return self.t("channel")
        if chat.kind == "g":
            return self.t("supergroup" if chat.subtype == "سوپرگروه" else "group")
        return "Bot" if chat.kind == "b" else self.t("private")

    async def resolve_leave(self, token, message_id, approved):
        context = self.confirmations.get(token)
        if not context or context[2] != message_id or context[0] <= monotonic():
            await self.report(self.t("bad_confirm"))
            return
        del self.confirmations[token]
        _, chat, _ = context
        empty = keyboard()
        if not approved:
            await self.api.edit(message_id, f"«{chat.title}»\n{self.t('cancelled')}", empty)
            return
        if not self.service.ready or self.service.chat(chat.peer) != chat:
            await self.api.edit(message_id, self.t("changed"), empty)
            return
        if chat.peer in self.leaving:
            await self.api.edit(message_id, self.t("busy"), empty)
            return
        self.leaving.add(chat.peer)
        try:
            result = await self.service.leave(chat)
        finally:
            self.leaving.discard(chat.peer)
        if self.panel:
            await self.panel.workspace.management.record("leave", result)
        status_key = {"already_left": "already", "already_refresh_failed": "refresh_failed"}.get(
            result, result)
        status = LEAVE_STATUS[result] if self.language == "fa" else self.t(status_key)
        await self.api.edit(message_id, f"«{chat.title}»\n{status}", empty)
        if self.service.ready and result in ("left", "already_left"):
            await self.show_list(self.new_view(chat.kind), 0)
        elif not self.service.ready:
            await self.show_home()
