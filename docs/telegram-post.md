# 📄 KILLER | مدیریت شخصی تلگرام

نسخهٔ رایگان و متن‌باز با بات و مینی‌اپ فارسی و انگلیسی

**امکانات**

- مرور و جست‌وجوی گروه‌ها، کانال‌ها و ربات‌ها همراه با عکس و اطلاعات چت.
- انتخاب چند مورد، بررسی صف و تأیید خروج از گروه و کانال یا مسدود کردن ربات. اطلاعات و لینک‌های در دسترس قبل از اجرا پشتیبان‌گیری می‌شوند.
- خواندن خودکار پیام‌ها یا پاک‌کردن نشان منشن و ریپلای، با تنظیم جداگانه برای هر گروه و کانال. این قابلیت پیامی ارسال نمی‌کند.
- مرور پیام‌ها و رسانه، مدیریت مخاطب‌ها، مشاهدهٔ دستگاه‌ها و نشست‌ها، پشتیبان و گزارش عملیات.

**راه‌اندازی**

۱. ZIP را استخراج کنید و داخل پوشهٔ `killer-allplus` ترمینال باز کنید. Python 3.11 یا جدیدتر لازم است.

۲. با [BotFather](https://t.me/BotFather) بات خودتان را بسازید و API ID و API Hash را از [my.telegram.org](https://my.telegram.org) بگیرید. طبق `README.md` یک کلید رمزگذاری بسازید و این موارد را همراه با شناسهٔ عددی تلگرام خودتان در فایل `.env` بگذارید.

۳. روی ویندوز، در PowerShell اجرا کنید

```powershell
python -m venv .venv
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

بعد از تکمیل `.env`، بات را اجرا کنید

```powershell
.\.venv\Scripts\python.exe -m app.main
```

۴. روی هاست لینوکسی دارای SSH و امکان اجرای پردازش دائمی، از داخل پوشهٔ پروژه اجرا کنید

```bash
python3.11 -m venv .venv
cp .env.example .env
chmod 600 .env
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

بعد از تکمیل `.env`، در ترمینال خصوصی هاست اجرا کنید

```bash
.venv/bin/python -m app.main
```

۵. بار اول شماره، کد و در صورت نیاز رمز دومرحله‌ای را در همان ترمینال خصوصی وارد کنید. بعد در چت خصوصی بات خودتان `/start` بفرستید. نشست رمزگذاری‌شده برای اجراهای بعدی ذخیره می‌شود.

**مینی‌اپ** با HTTPS معتبر و پراکسی فعال می‌شود. اجرای معمول بات به دامنه نیاز ندارد. برای تنظیم مینی‌اپ روی هاست یا cPanel، بخش «اجرای Mini App» در `README.md` و فایل `docs/architecture.md` را بخوانید.

**محدودهٔ نسخهٔ عمومی** هر نصب برای یک حساب مالک است. هر نفر بات، کلید و نشست خودش را روی کامپیوتر یا هاست خودش تنظیم می‌کند.

**قیمت** رایگان | **مجوز** MIT  
**پروژه** KILLER Telegram Manager  
#Python #Telethon #SQLite #TelegramMiniApp

اگر به کارت اومد، به پست ری‌اکشن بده.
