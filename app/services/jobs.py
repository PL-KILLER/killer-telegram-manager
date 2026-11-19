import asyncio
from datetime import datetime, timezone

from telethon import errors

from app.telegram_client import FloodDelay


async def background(workspace, bot, interval):
    if not interval:
        return
    while True:
        await asyncio.sleep(interval)
        if not workspace.authorized:
            continue
        store = workspace.store
        today = datetime.now(timezone.utc).date().isoformat()
        jobs = (
            ("sync_enabled", "on", workspace.sync),
            ("contacts_sync", "on", workspace.management.contacts),
            ("login_alerts", "on", lambda: security_alert(workspace, bot)),
            ("automatic_backup", "off", lambda: daily(workspace, "backup_date", today,
                                                     workspace.backup)),
            ("summary", "off", lambda: daily(workspace, "summary_date", today, bot.show_home)),
            ("inactivity_report", "off", lambda: daily(workspace, "inactivity_date", today,
                                                       lambda: inactivity_report(workspace, bot))),
        )
        for key, fallback, run in jobs:
            if await asyncio.to_thread(store.preference, key, fallback) != "on":
                continue
            try:
                await run()
            except (errors.AuthKeyError, errors.UnauthorizedError):
                workspace.authorized = bot.authorized = workspace.service.ready = False
                bot.sign_in_state = "expired_session"
                break
            except (FloodDelay, errors.RPCError, OSError, TimeoutError):
                await workspace.management.record(key, "failed")


async def security_alert(workspace, bot):
    _, count = await workspace.management.sessions()
    if count:
        await bot.report(bot.l(f"نشست تازهٔ تلگرام شناسایی شد: {count}",
                               f"New Telegram sessions detected: {count}"))


async def daily(workspace, key, today, run):
    store = workspace.store
    previous = await asyncio.to_thread(store.preference, key, "")
    if previous == today:
        return
    await run()
    await asyncio.to_thread(store.set_preference, key, today)


async def inactivity_report(workspace, bot):
    if await asyncio.to_thread(workspace.store.preference, "plugin:inactivity", "on") != "on":
        return
    dialogs = await asyncio.to_thread(workspace.store.inactive)
    if dialogs:
        await bot.report(bot.l("گفت‌وگوهای بدون پیام اخیر (نمونهٔ محلی):",
                               "Dialogs without recent messages (local sample):")
                         + "\n" + "\n".join(title[:90] for title, _ in dialogs[:10]))
