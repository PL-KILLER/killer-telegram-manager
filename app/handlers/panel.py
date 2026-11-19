import asyncio
from html import escape

from app.keyboards import button, keyboard
from app.services.control import valid_username
from app.services.management import PRIVACY_KEYS
from app.utils import confirmation_title


NAV = {
    "profile": ("حساب من", "My account"), "chats": ("گفت‌وگوها", "Chats"),
    "contacts": ("مخاطبین", "Contacts"), "messages": ("پیام‌ها", "Messages"),
    "media": ("رسانه‌ها", "Media"), "security": ("امنیت", "Security"),
    "analytics": ("آمار", "Analytics"), "activity": ("فعالیت", "Activity"),
    "backups": ("پشتیبان", "Backups"), "settings": ("تنظیمات", "Settings"),
    "folders": ("پوشه‌ها", "Folders"), "sessions": ("دستگاه‌ها", "Devices"),
    "drafts": ("پیش‌نویس‌ها", "Drafts"), "saved": ("پیام‌های ذخیره‌شده", "Saved Messages"),
    "photo": ("عکس‌ها", "Photos"), "video": ("ویدئو", "Videos"),
    "file": ("اسناد", "Documents"), "audio": ("صوت", "Audio"), "voice": ("پیام صوتی", "Voice"),
    "all": ("همه", "All"), "p": ("خصوصی", "Private chats"), "b": ("بات‌ها", "Bots"),
    "a": ("بایگانی", "Archived"), "favorites": ("علاقه‌مندی‌ها", "Favorites"),
    "tagged": ("برچسب‌دار", "Tagged"), "first_name": ("نام", "First name"),
    "last_name": ("نام خانوادگی", "Last name"), "username": ("نام کاربری", "Username"),
    "about": ("درباره", "Bio"), "phone": ("شمارهٔ تلفن", "Phone number"),
    "seen": ("آخرین بازدید", "Last seen"), "calls": ("تماس‌ها", "Calls"),
    "invites": ("دعوت‌ها", "Invites"), "forwards": ("ارجاع پیام‌ها", "Forwarded messages"),
    "cleanup": ("پاک‌سازی حساب", "Account cleanup"), "tools": ("ابزارهای حساب", "Account tools"),
    "blocked": ("مسدودشده‌ها", "Blocked accounts"),
}


class Panel:
    def __init__(self, bot, workspace, miniapp_url=None):
        self.bot = bot
        self.workspace = workspace
        self.owner = workspace.management
        self.store = workspace.store
        self.miniapp_url = miniapp_url
        self.input_requests = {}
        self.cleanup_selection = {}

    def label(self, key):
        return self.bot.l(*NAV[key]) if key in NAV else key

    def nav_button(self, section, style=None):
        return button(self.label(section), f"panel:{section}", style)

    def navigation(self):
        rows = [
            [self.nav_button("cleanup", "primary")],
            [self.nav_button("chats"), self.nav_button("messages")],
            [self.nav_button("security"), self.nav_button("tools")],
        ]
        if self.miniapp_url:
            rows.append([{"text": self.bot.l("باز کردن ALLPLUS", "Open ALLPLUS"),
                          "web_app": {"url": self.miniapp_url}}])
        return rows

    async def cleanup_screen(self, kind, page, message_id, query=""):
        items, more = await self.workspace.browse("chats", page, query, kind)
        view = self.workspace.ref("bot_cleanup_view", (kind, page, query))
        categories = (("c", self.bot.t("channels")), ("g", self.bot.t("groups")),
                      ("b", self.label("b")))
        rows = [[button(label, f"uclist:{key}", "primary" if key == kind else None)
                 for key, label in categories]]
        for item in items:
            peer = int(item["id"])
            active = peer in self.cleanup_selection
            title = confirmation_title(str(item["title"]))[:60] or "—"
            rows.append([button(title, f"info:{peer}"),
                         button("✓" if active else self.bot.l("انتخاب", "Select"),
                                f"uctick:{view}:{peer}", "success" if active else None)])
        paging = []
        if page:
            paging.append(button(self.bot.t("prev"), f"ucpage:{view}:{page - 1}"))
        if more:
            paging.append(button(self.bot.t("next"), f"ucpage:{view}:{page + 1}"))
        if paging:
            rows.append(paging)
        rows.append([button(self.bot.t("search"), f"ucsearch:{view}"),
                     button(self.bot.l("گزارش صف", "Queue report"), "ucreport:0")])
        if self.cleanup_selection:
            rows.append([button(self.bot.l("مرور و اجرای صف", "Review and run queue"), "ucreview:0", "primary")])
        if self.miniapp_url:
            rows.append([{"text": self.bot.l("پاک‌سازی در Mini App", "Cleanup in Mini App"),
                          "web_app": {"url": self.miniapp_url + "?view=cleanup"}}])
        text = self.bot.l(f"انتخاب‌شده: <b>{len(self.cleanup_selection)}</b> · صفحه {page + 1}",
                          f"<b>{len(self.cleanup_selection)}</b> selected · Page {page + 1}")
        if query:
            text += f"\n{self.bot.t('search')}: {escape(query)}"
        await self.screen(self.label("cleanup"), text, rows, message_id)

    async def cleanup_review(self, page, message_id):
        selected = list(self.cleanup_selection.items())
        page = max(0, min(page, max(0, len(selected) - 1) // 8))
        rows = []
        for peer, item in selected[page * 8:page * 8 + 8]:
            label = confirmation_title(str(item["title"]))[:60] or "—"
            action = self.bot.l("مسدودکردن", "Block") if item["kind"] == "b" else self.bot.t("leave")
            rows.append([button(f"{label} · {action}", f"ucremove:{page}:{peer}")])
        if selected:
            rows.append([button(self.bot.l("اجرای صف", "Run queue"), "ucrun", "danger")])
        paging = []
        if page:
            paging.append(button(self.bot.t("prev"), f"ucreview:{page - 1}"))
        if (page + 1) * 8 < len(selected):
            paging.append(button(self.bot.t("next"), f"ucreview:{page + 1}"))
        if paging:
            rows.append(paging)
        rows.append([button(self.bot.t("prev"), "uclist:c")])
        text = (self.bot.l(f"{len(selected)} مورد انتخاب شده. برای حذف از صف روی نام بزنید. ",
                           f"{len(selected)} selected. Tap a name to remove it. ") +
                self.bot.l("اطلاعات و لینک‌های در دسترس پیش از اجرا ذخیره می‌شوند.",
                           "Available details and links are saved before execution."))
        await self.screen(self.bot.l("صف پاک‌سازی", "Cleanup queue"), text, rows, message_id)

    async def cleanup_report(self, page, message_id):
        job = self.workspace.cleanup.status()
        rows = [[button(self.bot.t("refresh"), f"ucreport:{page}"),
                 self.nav_button("cleanup")]]
        if not job:
            await self.screen(self.bot.l("گزارش صف", "Queue report"),
                              self.bot.l("هنوز صفی اجرا نشده.", "No cleanup has run yet."),
                              rows, message_id)
            return
        states = {
            "pending": ("در صف", "Queued"), "working": ("در حال اجرا", "Working"),
            "left": ("خارج شد", "Left"), "already_left": ("عضویت نداشتید", "Already left"),
            "blocked": ("مسدود شد", "Blocked"), "skipped": ("اجرا نشد", "Skipped"),
            "unknown": ("تأیید نشد", "Unverified"), "owner": ("حساب مالک است", "Account is owner"),
        }
        items = job["items"]
        page = max(0, min(page, max(0, len(items) - 1) // 8))
        done = sum(item["status"] not in ("pending", "working") for item in items)
        text = f"<b>{done} / {len(items)}</b>"
        if job.get("wait"):
            text += f"\n{self.bot.t('wait')} {job['wait']} {self.bot.t('seconds')}"
        if job["phase"] == "failed":
            text += f"\n{self.bot.t('failed')}"
        text += "\n\n" + "\n".join(
            f"{escape(confirmation_title(item['title'])[:90])} · "
            f"{self.bot.l(*states.get(item['status'], states['unknown']))}"
            for item in items[page * 8:page * 8 + 8])
        paging = []
        if page:
            paging.append(button(self.bot.t("prev"), f"ucreport:{page - 1}"))
        if (page + 1) * 8 < len(items):
            paging.append(button(self.bot.t("next"), f"ucreport:{page + 1}"))
        if paging:
            rows.insert(0, paging)
        if job["backup"] and self.miniapp_url:
            rows.append([{"text": self.bot.l("دیدن پشتیبان", "View backup"),
                          "web_app": {"url": self.miniapp_url + "?view=cleanup"}}])
        await self.screen(self.bot.l("گزارش صف", "Queue report"), text, rows, message_id)

    async def dashboard_status(self):
        overview = await self.workspace.overview()
        contacts = overview["contacts"]
        status = self.bot.l("متصل", "Connected") if overview["connected"] else self.bot.l(
            "قطع", "Disconnected")
        text = f"\n{self.label('contacts')}  <b>{contacts if contacts is not None else '—'}</b>"
        text += f"\n\n{self.bot.l('وضعیت حساب', 'Account status')}: {status}"
        if overview["activity"]:
            when, operation, outcome = overview["activity"][0]
            if operation == "sync" and outcome == "ok":
                text += "\n" + self.bot.l("گفت‌وگوها به‌روز شدند.", "Chats are up to date.")
        return text

    async def screen(self, title, text, rows, message_id):
        rows = [*rows, [button(self.bot.t("home"), "home")]]
        header = f"<b>{escape(title)}</b>"
        await self.bot.render(f"{header}\n\n{text}" if text else header, keyboard(*rows), message_id)

    async def browse(self, section, message_id, *, page=0, query="", kind="all", peer=None, mode=""):
        state = section, query, kind, peer, mode
        items, more = await self.workspace.browse(section, page, query, kind, peer=peer, mode=mode)
        ref = self.workspace.ref("view", state)
        rows = []
        summaries = []
        for number, item in enumerate(items, 1):
            key = self.workspace.ref("item", (state, item))
            title = confirmation_title(str(item["title"]))[:75] or "—"
            if section in ("messages", "media"):
                line = item.get("file") or item.get("info")
                if item.get("protected"):
                    line = self.bot.l("محتوای محافظت‌شده", "Protected content")
                preview = confirmation_title(line or "")[:135]
                time = item.get("date", "") or ""
                meta = f" · {time[:16].replace('T', ' ')} UTC" if time else ""
                summaries.append(f"<b>{number}. {escape(title)}</b>{meta}"
                                 + (f"\n{escape(preview)}" if preview else ""))
                title = f"{number}. {title}"
            rows.append([button(title, f"uitem:{key}")])
        moves = []
        if page:
            moves.append(button(self.bot.t("prev"), f"upage:{ref}:{page - 1}"))
        if more:
            moves.append(button(self.bot.t("next"), f"upage:{ref}:{page + 1}"))
        if moves:
            rows.append(moves)
        if section in ("chats", "contacts", "messages", "media") or section == "folders" and mode:
            rows.append([button(self.bot.t("search"), f"uquery:{ref}")])
        if section == "contacts":
            rows.append([button(self.bot.l("افزودن", "Add"), "uform:contact_add"),
                         button(self.bot.t("sync"), "ucontacts:sync")])
        if section == "backups":
            rows.append([button(self.bot.l("ساخت پشتیبان رمز‌شده", "Create encrypted backup"), "ubackup:create")])
        details = f"{self.bot.t('page')} {page + 1}"
        if query:
            details += f" · {escape(query)}"
        if not items:
            details += f"\n{self.bot.t('empty')}"
        elif summaries:
            details += "\n\n" + "\n\n".join(summaries)
        title = self.label(section)
        await self.screen(title, details, rows, message_id)

    async def main_screen(self, section, message_id):
        if section == "cleanup":
            await self.cleanup_screen("c", 0, message_id)
        elif section == "tools":
            keys = ("profile", "contacts", "media", "analytics", "activity", "backups", "settings")
            rows = [[self.nav_button(key) for key in keys[i:i + 2]] for i in range(0, len(keys), 2)]
            await self.screen(self.label(section), "", rows, message_id)
        elif section == "chats":
            sections = ("all", "p", "b", "a", "favorites", "tagged")
            rows = [[button(self.label(key), f"uchats:{key}") for key in sections[i:i + 2]]
                    for i in range(0, len(sections), 2)]
            rows.append([self.nav_button("folders")])
            await self.screen(self.label(section), "", rows, message_id)
        elif section == "messages":
            state = self.workspace.ref("view", ("messages", "", "all", None, ""))
            await self.screen(self.label(section), self.bot.l(
                "برای پیدا کردن پیام، بخشی از متنش را جست‌وجو کنید.",
                "Search for a word or phrase to find a message."), [
                [button(self.bot.t("search"), f"uquery:{state}")],
                [self.nav_button("saved"), self.nav_button("drafts")],
            ], message_id)
        elif section == "saved":
            await self.browse("messages", message_id, peer="me")
        elif section == "media":
            await self.screen(self.label(section), "", [
                [button(self.label(mode), f"umedia:{mode}") for mode in ("photo", "video")],
                [button(self.label(mode), f"umedia:{mode}") for mode in ("file", "audio", "voice")],
            ], message_id)
        elif section == "profile":
            data = await self.workspace.profile()
            labels = ("first_name", "last_name", "username", "about")
            text = "\n".join(f"{self.label(key)}: {escape(data[key]) or '—'}" for key in labels)
            text += f"\nPremium: {'✓' if data['premium'] else '—'} · ID {data['id']}"
            rows = [[button(self.label(key), f"uform:profile_edit:{key}")] for key in labels]
            if data["photo"]:
                rows.append([button(self.label("photo"), "uphoto:me")])
            await self.screen(self.label(section), text, rows, message_id)
        elif section == "security":
            data = await self.workspace.security()
            status = self.bot.l("فعال", "Enabled") if data["two_factor"] else self.bot.l(
                "غیرفعال", "Disabled")
            rows = [[self.nav_button("sessions"), self.nav_button("blocked")],
                    [self.nav_button("activity")]]
            rows += [[button(self.label(key), f"uprivacy:{key}")] for key in PRIVACY_KEYS]
            await self.screen(self.label(section), f"2FA · {status}", rows, message_id)
        elif section == "analytics":
            data = await asyncio.to_thread(self.store.analytics)
            text = (f"{self.label('analytics')} · {self.bot.l('دادهٔ محلی', 'Local data')}\n"
                    f"{self.label('a')}  {data['archived']:,}\n"
                    f"{self.label('b')}  {data['kinds'].get('b', 0):,}\n"
                    f"{self.label('p')}  {data['kinds'].get('p', 0):,}\n"
                    f"SQLite  {data['database_bytes']:,} B")
            await self.screen(self.label(section), text, [[self.nav_button("activity")]], message_id)
        elif section == "settings":
            await self.screen(self.label(section), self.bot.t("language"), [
                [button("فارسی", "ulang:fa"), button("English", "ulang:en")],
            ], message_id)
        elif section in ("contacts", "folders", "sessions", "blocked", "drafts", "activity", "backups"):
            await self.browse(section, message_id)
        else:
            raise LookupError

    async def chat(self, peer, message_id):
        info = await self.workspace.chat_detail(peer)
        rows = []
        for setting, enabled, fa_on, en_on, fa_off, en_off in (
            ("archive", info["archived"], "بایگانی", "Archive", "بازیابی از بایگانی", "Unarchive"),
            ("pin", info["pinned"], "سنجاق", "Pin", "برداشتن سنجاق", "Unpin"),
            ("favorite", info["favorite"], "علاقه‌مندی", "Favorite", "حذف علاقه‌مندی", "Unfavorite"),
        ):
            label = self.bot.l(fa_off, en_off) if enabled else self.bot.l(fa_on, en_on)
            key = self.workspace.ref("action", (setting, peer, info["title"], (not enabled,)))
            rows.append([button(label, f"uaction:{key}")])
        rows.append([button(self.bot.l("برچسب", "Tag"), f"uform:tag:{peer}"),
                     button(self.label("drafts"), f"uform:draft_save:{peer}")])
        for mode, label in (("", self.label("messages")), ("scheduled", self.bot.l("زمان‌بندی‌شده", "Scheduled")),
                            ("pinned", self.bot.l("پیام سنجاق‌شده", "Pinned messages"))):
            ref = self.workspace.ref("view", ("messages", "", "all", peer, mode))
            rows.append([button(label, f"upage:{ref}:0")])
        text = escape(info.get("about") or self.bot.t("unavailable"))
        if info.get("tag"):
            text += f"\n#{escape(info['tag'])}"
        await self.screen(info["title"], text, rows, message_id)

    async def item(self, state, item, message_id):
        section, _, _, _, mode = state
        if section == "chats" or section == "folders" and mode:
            await self.bot.show_info(self.workspace.service.chat(int(item["id"])))
            return
        if section == "folders":
            await self.browse("folders", message_id, mode=item["mode"])
            return
        rows = []
        text = escape(item.get("info", ""))
        if item.get("date"):
            text += f"\n{escape(item['date'])}"
        if section == "contacts":
            user = await self.owner.contact(int(item["id"]))
            if user.phone:
                text += f"\n<code>{escape(user.phone)}</code>"
            ref = self.workspace.ref("action", ("contact_delete", user.id, item["title"], ()))
            rows.append([button(self.bot.l("ویرایش", "Edit"), f"uform:contact_edit:{user.id}"),
                         button(self.bot.l("حذف", "Delete"), f"uaction:{ref}", "danger")])
        elif section == "sessions" and not item["current"]:
            session = self.workspace.resolve(item["id"], "session")
            ref = self.workspace.ref("action", ("revoke", session.hash, item["title"], ()))
            rows.append([button(self.bot.l("پایان نشست", "Terminate session"), f"uaction:{ref}", "danger")])
        elif section == "blocked":
            entity = self.workspace.resolve(item["id"], "blocked")
            ref = self.workspace.ref("action", ("unblock", entity, item["title"], ()))
            rows.append([button(self.bot.l("رفع مسدودی", "Unblock"), f"uaction:{ref}")])
        elif section == "messages" or section == "media":
            message, peer, selected = self.workspace.resolve(item["id"], "message")
            if not item["protected"]:
                text = escape((message.message or "")[:3400])
            if item["file"]:
                text += f"\n{escape(item['file'])} · {item['bytes'] or 0:,} B"
            if item["has_media"]:
                rows.append([button(self.bot.l("دریافت فایل", "Get file"), f"ufile:{item['id']}")])
            if item["deletable"]:
                ref = self.workspace.ref("action", ("message_delete", peer, f"#{message.id}",
                                                     (message.id, selected == "scheduled")))
                rows.append([button(self.bot.l("حذف پیام", "Delete message"), f"uaction:{ref}", "danger")])
        elif section == "drafts":
            rows.append([button(self.bot.l("ویرایش پیش‌نویس", "Edit draft"), f"uform:draft_save:{item['id']}")])
        elif section == "backups":
            meta = await asyncio.to_thread(self.workspace.backups.inspect, item["id"])
            text = f"{meta['chats']:,} · SQLite {meta['schema']} · {item['bytes']:,} B"
        await self.screen(item["title"], text, rows, message_id)

    async def ask(self, name, target, label, values):
        token = self.workspace.control.prepare(name, target, label, *values)
        await self.bot.api.send(
            f"{self.bot.l('تأیید عملیات', 'Confirm operation')}\n"
            f"{confirmation_title(label)}\n\n{self.bot.t('expires')}",
            keyboard([button(self.bot.l("تأیید", "Confirm"), f"uconfirm:{token}", "danger"),
                      button(self.bot.t("cancel"), f"ucancel:{token}")]))

    async def form(self, operation, target, message_id):
        labels = {
            "contact_add": ("در پاسخ بفرستید: username | نام | نام خانوادگی",
                            "Reply with: username | first name | last name"),
            "contact_edit": ("در پاسخ بفرستید: نام | نام خانوادگی",
                             "Reply with: first name | last name"),
            "profile_edit": ("مقدار تازه را در پاسخ بفرستید. برای پاک‌کردن - بفرستید.",
                             "Reply with the new value. Send - to clear."),
            "draft_save": ("متن پیش‌نویس را بفرستید. برای پاک‌کردن - بفرستید.",
                           "Reply with the draft. Send - to clear."),
            "tag": ("برچسب را بفرستید. برای پاک‌کردن - بفرستید.",
                    "Reply with a tag. Send - to clear."),
            "query": (self.bot.t("query_prompt"), self.bot.t("query_prompt")),
            "cleanup_query": (self.bot.t("query_prompt"), self.bot.t("query_prompt")),
        }
        prompt = await self.bot.api.send(self.bot.l(*labels[operation]), {"force_reply": True})
        token = self.workspace.ref("input", (operation, target, message_id))
        if len(self.input_requests) >= 64:
            self.input_requests.pop(next(iter(self.input_requests)))
        self.input_requests[prompt["message_id"]] = token

    async def message(self, message):
        reply = message.get("reply_to_message", {}).get("message_id")
        raw = message.get("text", "").strip()
        token = self.input_requests.pop(reply, None) if raw else None
        if not token:
            return False
        operation, target, source = self.workspace.resolve(token, "input")
        if operation == "query":
            section, _, kind, peer, mode = self.workspace.resolve(target, "view")
            await self.browse(section, source, query=raw[:150], kind=kind, peer=peer, mode=mode)
        elif operation == "cleanup_query":
            kind, _, _ = self.workspace.resolve(target, "bot_cleanup_view")
            await self.cleanup_screen(kind, 0, source, raw[:150])
        elif operation in ("contact_add", "contact_edit"):
            names = [field.strip() for field in raw.split("|")]
            if operation == "contact_add":
                target, *names = names
                if not valid_username(target.lstrip("@")):
                    raise ValueError
                target = "@" + target.lstrip("@")
                label = target
            else:
                target = int(target)
                user = await self.owner.contact(target)
                label = user.first_name or str(target)
            if not 1 <= len(names) <= 2 or not names[0] or any(len(value) > 64 for value in names):
                raise ValueError
            names += [""] * (2 - len(names))
            await self.ask(operation, target, f"{label} → {' '.join(names)}", tuple(names))
        elif operation == "profile_edit":
            value = "" if raw == "-" else raw
            if len(value) > 160 or target == "first_name" and not value or (
                target == "username" and value and not valid_username(value)
            ):
                raise ValueError
            await self.ask(operation, target, f"{self.label(target)} → {value or '—'}", (value,))
        elif operation in ("draft_save", "tag"):
            peer = int(target)
            entity = self.owner.entity(peer)
            chat = self.workspace.service.chat(peer)
            value = "" if raw == "-" else raw
            if operation == "tag":
                await asyncio.to_thread(self.store.organize, peer, tag=value[:64])
                await self.chat(peer, source)
            else:
                await self.ask(operation, peer, f"{chat.title} · {value[:120]}", (value,))
        return True

    async def callback(self, action, arg, message_id):
        if action == "panel":
            await self.main_screen(arg, message_id)
        elif action == "uclist" and arg in ("c", "g", "b"):
            await self.cleanup_screen(arg, 0, message_id)
        elif action in ("uctick", "ucpage"):
            token, value = arg.split(":", 1)
            kind, page, query = self.workspace.resolve(token, "bot_cleanup_view")
            if action == "uctick":
                peer = int(value)
                chat = self.workspace.service.chat(peer)
                if not chat or chat.kind != kind:
                    raise LookupError
                if peer in self.cleanup_selection:
                    del self.cleanup_selection[peer]
                else:
                    self.cleanup_selection[peer] = {"title": chat.title, "kind": chat.kind}
            else:
                page = max(0, int(value))
            await self.cleanup_screen(kind, page, message_id, query)
        elif action == "ucsearch":
            await self.form("cleanup_query", arg, message_id)
        elif action == "ucreview":
            await self.cleanup_review(int(arg), message_id)
        elif action == "ucremove":
            page, peer = arg.split(":", 1)
            self.cleanup_selection.pop(int(peer), None)
            await self.cleanup_review(int(page), message_id)
        elif action == "ucrun":
            self.workspace.cleanup.start(list(self.cleanup_selection))
            self.cleanup_selection.clear()
            await self.cleanup_report(0, message_id)
        elif action == "ucreport":
            await self.cleanup_report(int(arg), message_id)
        elif action == "uchats":
            await self.browse("chats", message_id, kind=arg)
        elif action == "umedia":
            await self.browse("media", message_id, mode=arg)
        elif action == "uchat":
            await self.chat(int(arg), message_id)
        elif action == "uitem":
            state, item = self.workspace.resolve(arg, "item")
            await self.item(state, item, message_id)
        elif action == "upage":
            token, page = arg.split(":")
            section, query, kind, peer, mode = self.workspace.resolve(token, "view")
            await self.browse(section, message_id, page=int(page), query=query, kind=kind,
                              peer=peer, mode=mode)
        elif action == "uquery":
            await self.form("query", arg, message_id)
        elif action == "uform":
            operation, _, target = arg.partition(":")
            await self.form(operation, target, message_id)
        elif action == "uaction":
            name, target, label, values = self.workspace.resolve(arg, "action")
            if name == "favorite":
                await asyncio.to_thread(self.store.organize, target, favorite=values[0])
                await self.chat(target, message_id)
            else:
                await self.ask(name, target, label, values)
        elif action == "uconfirm":
            result = await self.workspace.control.confirm(arg)
            await self.bot.api.edit(message_id, self.bot.l("انجام شد.", "Completed.") if result
                                    else self.bot.t("failed"), keyboard())
        elif action == "ucancel":
            self.workspace.control.cancel(arg)
            await self.bot.api.edit(message_id, self.bot.t("cancelled"), keyboard())
        elif action == "ucontacts":
            await self.owner.contacts(refresh=True)
            await self.browse("contacts", message_id)
        elif action == "ubackup":
            await self.workspace.backup()
            await self.browse("backups", message_id)
        elif action == "uprivacy":
            rules = await self.owner.privacy(arg)
            text = "\n".join(f"{kind} · {count}" for kind, count in rules)
            await self.screen(self.label(arg), text, [[self.nav_button("security")]], message_id)
        elif action == "ulang" and arg in ("fa", "en"):
            self.bot.language = arg
            await asyncio.to_thread(self.store.set_preference, "language", arg)
            await self.bot.show_home(message_id)
        elif action == "uphoto":
            photo = await self.owner.account.photo("me")
            if not photo:
                raise LookupError
            await self.bot.api.call("sendPhoto", photo=photo, chat_id=str(self.bot.api.owner_id),
                                    protect_content="true")
        elif action == "ufile":
            message, _, _ = self.workspace.resolve(arg, "message")
            payload = await self.owner.media(message)
            if not payload:
                raise LookupError
            await self.bot.api.call("sendDocument", document=payload,
                                    chat_id=str(self.bot.api.owner_id), protect_content="true")
        else:
            return False
        return True
