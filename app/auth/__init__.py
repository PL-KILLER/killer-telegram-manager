import asyncio
import getpass
import sys
import warnings

from telethon import errors


async def existing_account(client):
    await client.connect()
    try:
        return await client.get_me()
    except (errors.UnauthorizedError, errors.AuthKeyError):
        return None


async def local_login(client):
    if not sys.stdin.isatty():
        print("برای ورود، برنامه را از ترمینال محلی اجرا کنید.", flush=True)
        return None
    await client.connect()
    phone = (await asyncio.to_thread(input, "شماره با پیش‌شماره کشور: ")).strip()
    for attempt in range(3):
        try:
            sent = await client.send_code_request(phone)
            break
        except (errors.PhoneMigrateError, errors.NetworkMigrateError) as error:
            # Telethon changes DC before surfacing the error when RPC retries are off.
            if attempt == 2 or client.session.dc_id != error.new_dc:
                raise
    delivery = {
        "SentCodeTypeApp": "پیام رسمی Telegram در یکی از دستگاه‌های واردشده",
        "SentCodeTypeSms": "پیامک",
        "SentCodeTypeCall": "تماس تلفنی",
        "SentCodeTypeEmailCode": "ایمیل ورود",
    }.get(type(getattr(sent, "type", None)).__name__)
    if delivery:
        print(f"مسیر تحویل کد اعلام‌شده توسط تلگرام: {delivery}", flush=True)
    for _ in range(3):
        code = await asyncio.to_thread(secret, "کد ورود: ")
        try:
            return await client.sign_in(phone=phone, code=code.strip(),
                                        phone_code_hash=sent.phone_code_hash)
        except errors.PhoneCodeInvalidError:
            print("کد ورود نادرست است.", flush=True)
        except errors.SessionPasswordNeededError:
            return await local_password(client)
    return None


async def local_password(client):
    for _ in range(3):
        password = await asyncio.to_thread(secret, "رمز دومرحله‌ای: ")
        try:
            return await client.sign_in(password=password)
        except errors.PasswordHashInvalidError:
            print("رمز دومرحله‌ای نادرست است.", flush=True)
    return None


async def local_qr_login(client):
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("ورود با QR به ترمینال تعاملی نیاز دارد.", flush=True)
        return None
    await client.connect()
    while True:
        answer = await asyncio.to_thread(input, "برای ساخت QR اینتر بزنید یا q را وارد کنید: ")
        if answer.strip().lower() == "q":
            return None
        qr = await client.qr_login()
        waiting = asyncio.create_task(wait_for_qr(qr))
        try:
            await asyncio.sleep(0)
            print(f"QR_LOGIN {qr.url}", flush=True)
            account = await waiting
            if account is not None:
                return account
        except errors.SessionPasswordNeededError:
            return await local_password(client)
        finally:
            if not waiting.done():
                waiting.cancel()
                await asyncio.gather(waiting, return_exceptions=True)
        print("زمان اسکن این QR تمام شد.", flush=True)


async def wait_for_qr(qr):
    try:
        return await qr.wait()
    except TimeoutError:
        return None


def secret(prompt):
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        return getpass.getpass(prompt)
