"""Read-only smoke check of an installed Unix socket instance."""

import asyncio
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import httpx

from app.config import Config


async def main():
    config = Config.load()
    fields = {
        "auth_date": str(int(time.time())),
        "user": json.dumps({"id": config.owner_id}, separators=(",", ":")),
    }
    data = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", config.bot_token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, data.encode(), hashlib.sha256).hexdigest()
    transport = httpx.AsyncHTTPTransport(uds=str(config.data / "miniapp.sock"))
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost", timeout=35) as http:
        response = await http.get("/api/overview")
        if response.status_code != 403:
            raise RuntimeError("Missing initData was not rejected")
        headers = {"X-Telegram-Init-Data": urlencode(fields)}
        overview = (await http.get("/api/overview", headers=headers)).raise_for_status().json()
        page = (await http.post("/api/browse", headers=headers,
                                json={"section": "chats"})).raise_for_status().json()
        print(json.dumps({**{key: overview[key] for key in ("connected", "synchronized", "syncing",
                                                            "dialogs", "channels", "groups",
                                                            "contacts")},
                          "dialog_page_items": len(page["items"]), "next_page": page["more"]}))


if __name__ == "__main__":
    asyncio.run(main())
