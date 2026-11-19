FILTERS = {"all": "همه", "public": "عمومی", "private": "خصوصی"}


def button(text, data, style=None):
    result = {"text": text, "callback_data": data}
    if style:
        result["style"] = style
    return result


def keyboard(*rows):
    return {"inline_keyboard": rows}


def dashboard(t=None, *, extra=()):
    t = t or (lambda key: {"channels": "کانال‌ها", "groups": "گروه‌ها", "sync": "همگام‌سازی"}[key])
    return keyboard(
        [button(t("channels"), "list:c", "primary"),
         button(t("groups"), "list:g", "primary")],
        *extra,
        [button(t("sync"), "refresh:h")],
    )


def page_keys(chats, kind, view, page, pages, privacy="all", query="", t=None):
    t = t or (lambda key: {**FILTERS, "leave": "خروج", "prev": "قبل", "next": "بعد",
                          "search": "جست‌وجو", "refresh": "تازه‌سازی", "home": "داشبورد",
                          "clear": "پاک‌کردن جست‌وجو"}[key])
    rows = [[button(chat.title, f"info:{chat.peer}"),
             button(t("leave"), f"ask:{chat.peer}")]
            if chat.kind in ("c", "g") else
            [button(chat.title, f"info:{chat.peer}")]
            for chat in chats]
    paging = []
    if page > 0:
        paging.append(button(f"‹ {t('prev')}", f"page:{view}:{page - 1}"))
    if pages > 1:
        paging.append(button(f"{page + 1} / {pages}", f"jump:{view}", "primary"))
    if page + 1 < pages:
        paging.append(button(f"{t('next')} ›", f"page:{view}:{page + 1}"))
    if paging:
        rows.append(paging)
    rows.extend([
        [button(t(key), f"filter:{view}:{key}", "primary" if key == privacy else None)
         for key in FILTERS],
        [button(t("search"), f"search:{view}"),
         button(t("refresh"), f"refresh:{view}:{page}")],
        [button(t("home"), "home")],
    ])
    if query:
        rows[-1].insert(0, button(t("clear"), f"clear:{view}"))
    return keyboard(*rows)
