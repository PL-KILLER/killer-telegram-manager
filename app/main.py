import argparse
import asyncio
import logging
import os
import signal
import sqlite3
import sys
from contextlib import closing, nullcontext
import json
from pathlib import Path

import httpx
from telethon import TelegramClient, errors

from app.auth import existing_account, local_login, local_qr_login
from app.config import Config
from app.database import Store
from app.handlers import Bot
from app.handlers.api import BotAPI, BotError
from app.handlers.panel import Panel
from app.security import EncryptedSession
from app.services import AccountService
from app.services.backups import Backups
from app.services.control import Control
from app.services.jobs import background
from app.services.integrations import organizer_import_rows
from app.services.management import Management
from app.services.workspace import Workspace
from app.telegram_client import FloodDelay, TelegramAccount

PUBLIC_EDITION = (Path(__file__).resolve().parents[1] / "PUBLIC_EDITION.txt").is_file()


def make_client(config, *, qr=False):
    session = EncryptedSession(config.data / "account.fernet", config.cipher)
    client = TelegramClient(session, config.api_id, config.api_hash, receive_updates=qr,
                            flood_sleep_threshold=0, request_retries=0, connection_retries=2,
                            raise_last_call_error=True)
    return client, session


async def initialize(bot, config, *, qr=False):
    client = bot.service.account.client
    session = client.session
    login = local_qr_login if qr else local_login
    try:
        fresh = not session.persisted
        if session.persisted:
            account = await existing_account(client)
            if account is None:
                await client.disconnect()
                session.invalidate()
                client, session = make_client(config, qr=qr)
                bot.service.account.client = client
                fresh = True
                account = await login(client)
        else:
            account = await login(client)
        if account is None or account.bot or account.id != config.owner_id:
            bot.sign_in_state = "sign_in"
            print("ورود کامل نشد یا شناسهٔ حساب با مالک یکسان نبود.", flush=True)
            if account is not None and fresh:
                if not await client.log_out():
                    print("نشست اشتباه را از بخش دستگاه‌های تلگرام لغو کنید.", flush=True)
            await client.disconnect()
            return
        session.enable()
        if qr:
            await client.set_receive_updates(False)
    except (errors.RPCError, OSError, ValueError, EOFError, Warning) as error:
        bot.sign_in_state = "sign_in"
        print(f"ورود ناموفق بود ({type(error).__name__}).", flush=True)
        return
    bot.authorized = True
    workspace = bot.panel.workspace
    workspace.authorized = True
    workspace.auto_read.start()
    bot.refreshing = True
    try:
        await workspace.sync()
    except (errors.UnauthorizedError, errors.AuthKeyError):
        bot.authorized = bot.service.ready = False
        workspace.authorized = False
        bot.sign_in_state = "expired_session"
    except FloodDelay as error:
        print(f"همگام‌سازی پس از {error.args[0]} ثانیه دوباره ممکن است.", flush=True)
    except (errors.RPCError, OSError, TimeoutError) as error:
        print(f"همگام‌سازی اولیه ناموفق بود ({type(error).__name__}).", flush=True)
    finally:
        bot.refreshing = False
    if workspace.authorized and bot.service.ready:
        try:
            await workspace.management.contacts()
            await workspace.management.sessions()
        except (FloodDelay, errors.RPCError, OSError, TimeoutError):
            print("بارگیری اولیهٔ مخاطبین یا دستگاه‌ها کامل نشد.", flush=True)


async def run(config, *, qr=False, web_port=None, web_socket=False):
    store = Store(config.data / "metadata.sqlite3")
    client, _ = make_client(config, qr=qr)
    service = AccountService(TelegramAccount(client, config.owner_id), store)
    workspace = Workspace(Control(Management(service), Backups(config.data, config.cipher)))
    async with httpx.AsyncClient(timeout=httpx.Timeout(40, connect=10), trust_env=False) as http:
        api = BotAPI(config.bot_token, config.owner_id, http)
        identity = await api.call("getMe")
        print(f"بات @{identity['username']} فعال است. در گفت‌وگوی خصوصی، /start را بفرستید.", flush=True)
        public_start = not PUBLIC_EDITION and os.environ.get("KILLER_SHARED_START") == "1"
        bot = Bot(api, service, public_start_url=config.miniapp_url if public_start else None,
                  username=identity.get("username"))
        bot.language = await asyncio.to_thread(store.preference, "language", "fa")
        bot.panel = Panel(bot, workspace, config.miniapp_url if web_port or web_socket else None)
        polling = asyncio.create_task(bot.run())
        startup = asyncio.create_task(initialize(bot, config, qr=qr))
        automation = asyncio.create_task(background(workspace, bot, config.sync_interval))
        web_task = None
        if web_port or web_socket:
            import uvicorn

            from app.web import create_app

            options = {"uds": str(config.data / "miniapp.sock")} if web_socket else {
                "host": "127.0.0.1", "port": web_port}
            web_app = create_app(workspace, config)
            if not PUBLIC_EDITION and os.environ.get("KILLER_SHARED_MINIAPP") == "1":
                from app.shared import shared_app

                web_app = shared_app(web_app, config, make_client)
            server = uvicorn.Server(uvicorn.Config(web_app, access_log=False,
                                                   log_config=None, timeout_graceful_shutdown=10,
                                                   **options))
            server.capture_signals = nullcontext
            web_task = asyncio.create_task(server.serve())
        loop = asyncio.get_running_loop()
        stop = asyncio.Event()
        signal_registered = False
        if os.name != "nt":
            loop.add_signal_handler(signal.SIGTERM, stop.set)
            signal_registered = True
        shutdown = asyncio.create_task(stop.wait())
        try:
            active = {polling, startup, automation, shutdown}
            if web_task:
                active.add(web_task)
            while active:
                done, active = await asyncio.wait(active, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
                    if task in (polling, web_task, shutdown):
                        return
        finally:
            if web_task:
                server.should_exit = True
            if signal_registered:
                loop.remove_signal_handler(signal.SIGTERM)
            tasks = (startup, polling, automation, shutdown, *bot.jobs)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if web_task:
                await asyncio.gather(web_task, return_exceptions=True)
            await workspace.cleanup.close()
            await workspace.auto_read.close()
            await service.account.client.disconnect()


def main():
    if sys.version_info < (3, 11):
        print("اجرای برنامه به Python 3.11 یا جدیدتر نیاز دارد.", file=sys.stderr)
        return 1
    # Library records and HTTP exception strings can contain sensitive values.
    logging.disable(logging.CRITICAL)
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument("--qr", action="store_true", help="interactive QR sign-in")
    web = parser.add_mutually_exclusive_group()
    web.add_argument("--web-port", type=int, help="serve Mini App on the loopback interface")
    web.add_argument("--web-socket", action="store_true", help="serve Mini App on a private Unix socket")
    maintenance = parser.add_mutually_exclusive_group()
    maintenance.add_argument("--backup", action="store_true")
    maintenance.add_argument("--preview-backup", metavar="NAME")
    maintenance.add_argument("--restore-backup", nargs=2, metavar=("NAME", "NEW_DB_PATH"))
    maintenance.add_argument("--export-organizer", metavar="NEW_JSON_PATH")
    maintenance.add_argument("--preview-organizer", metavar="JSON_PATH")
    maintenance.add_argument("--import-organizer", metavar="JSON_PATH")
    parser.add_argument("--confirm-import", action="store_true")
    args = parser.parse_args()
    try:
        config = Config.load()
        config.data.mkdir(mode=0o700, exist_ok=True, parents=True)
        with closing(sqlite3.connect(config.data / "instance.sqlite3", timeout=0)) as lock:
            try:
                lock.execute("BEGIN EXCLUSIVE")
            except sqlite3.OperationalError:
                print("قفل اجرای برنامه در دسترس نیست. نمونهٔ دیگری ممکن است فعال باشد.", file=sys.stderr)
                return 1
            backups = Backups(config.data, config.cipher)
            if args.backup:
                Store(config.data / "metadata.sqlite3")
                print(backups.create())
            elif args.preview_backup:
                print(backups.inspect(args.preview_backup))
            elif args.restore_backup:
                name, path = args.restore_backup
                target = Path(path)
                if target.exists() or target.is_symlink():
                    raise FileExistsError
                print(backups.inspect(name, target=target))
            elif args.export_organizer:
                store = Store(config.data / "metadata.sqlite3")
                with Path(args.export_organizer).open("x", encoding="utf-8") as handle:
                    json.dump(store.organizer_export(), handle, ensure_ascii=False, indent=2)
            elif args.preview_organizer or args.import_organizer:
                path = Path(args.preview_organizer or args.import_organizer)
                if path.stat().st_size > 20 * 1024 * 1024:
                    raise ValueError("Organizer import is too large")
                rows = organizer_import_rows(json.loads(path.read_text(encoding="utf-8")))
                print(json.dumps({"entries": len(rows)}))
                if args.import_organizer:
                    if not args.confirm_import:
                        raise ValueError("Use --confirm-import after previewing")
                    store = Store(config.data / "metadata.sqlite3")
                    print(json.dumps({"updated": store.organizer_import(rows)}))
            else:
                asyncio.run(run(config, qr=args.qr, web_port=args.web_port, web_socket=args.web_socket))
    except KeyboardInterrupt:
        return 0
    except BotError as error:
        print(f"خطای Bot API ({error.code}). توکن، اتصال و تنظیمات polling بات را بررسی کنید.",
              file=sys.stderr)
        return 1
    except KeyError as error:
        print(f"تنظیم لازم وارد نشده است ({error.args[0]}). فایل .env.example را ببینید.",
              file=sys.stderr)
        return 1
    except Exception as error:
        print(f"اجرای برنامه ناموفق بود ({type(error).__name__}).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
