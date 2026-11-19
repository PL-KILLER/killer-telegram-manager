import asyncio
import json

import httpx


class BotError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class BotAPI:
    def __init__(self, token, owner_id, http):
        self.url = f"https://api.telegram.org/bot{token}"
        self.owner_id = owner_id
        self.http = http

    async def call(self, method, *, photo=None, document=None, **data):
        for attempt in range(3):
            try:
                if photo is None and document is None:
                    response = await self.http.post(f"{self.url}/{method}", json=data)
                else:
                    files = ({"photo": ("profile.jpg", photo, "image/jpeg")} if photo is not None
                             else {"document": ("telegram-media", document, "application/octet-stream")})
                    response = await self.http.post(f"{self.url}/{method}", data=data, files=files)
            except httpx.RequestError:
                # Sending a message can have succeeded before a timeout.
                raise BotError(0) from None
            try:
                payload = response.json()
            except ValueError:
                raise BotError(response.status_code) from None
            if payload.get("ok"):
                return payload["result"]
            code = payload.get("error_code", response.status_code)
            if code != 429 or attempt == 2:
                if method == "editMessageText" and code == 400 and (
                    "message is not modified" in payload.get("description", "").lower()
                ):
                    return None
                raise BotError(code)
            await asyncio.sleep(max(1, payload.get("parameters", {}).get("retry_after", 1)))

    async def send(self, text, markup=None, *, html=False):
        data = {"chat_id": self.owner_id, "text": text, "protect_content": True,
                "link_preview_options": {"is_disabled": True}}
        if markup:
            data["reply_markup"] = markup
        if html:
            data["parse_mode"] = "HTML"
        return await self.call("sendMessage", **data)

    async def send_photo_card(self, photo, caption, markup):
        return await self.call(
            "sendPhoto", photo=photo, chat_id=str(self.owner_id), caption=caption,
            parse_mode="HTML", protect_content="true",
            reply_markup=json.dumps(markup, ensure_ascii=False),
        )

    async def edit(self, message_id, text, markup, *, html=False):
        formatting = {"parse_mode": "HTML"} if html else {}
        try:
            await self.call("editMessageText", chat_id=self.owner_id, message_id=message_id,
                            text=text, reply_markup=markup,
                            link_preview_options={"is_disabled": True}, **formatting)
        except BotError as error:
            if error.code != 400:
                raise
            # An old message may no longer be editable. Send a fresh view.
            await self.send(text, markup, html=html)
