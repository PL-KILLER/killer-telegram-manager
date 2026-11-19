"""Optional browser smoke test. Install Playwright separately and set KILLER_BROWSER."""

import functools
import os
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect, sync_playwright


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


FIXTURES = {
    "/api/overview": {"dialogs": 14, "channels": 3, "groups": 2, "contacts": 10,
                      "connected": True, "synchronized": True, "syncing": False,
                      "activity": [["2026-01-01T08:00:00Z", "sync", "ok"]]},
    "/api/settings": {"language": "fa"},
    "/api/search-history": [],
    "/api/security": {"two_factor": True, "privacy": ["seen"]},
    "/api/profile": {"first_name": "Example", "id": "123", "photo": False},
    "/api/privacy/seen": [["contacts", 0]],
    "/api/command": {"ok": True},
    "/api/cleanup": {"job": None, "backups": ["20261119T000000000000Z"]},
    "/api/chat/31": {"username": "example", "about": "A channel about books.", "count": 23,
                      "photo": True, "title": "Public channel", "kind": "c"},
}


def request_path(request):
    url = urlsplit(request.url)
    if url.path.endswith("/api.php"):
        return "/" + parse_qs(url.query).get("path", [""])[0].lstrip("/")
    return url.path


def fixtures(route):
    path = request_path(route.request)
    assert route.request.headers.get("x-telegram-init-data") == "mock-init-data"
    if path == "/api/photo/31":
        route.fulfill(status=200, content_type="image/svg+xml",
                      body='<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"><rect width="8" height="8" fill="gold"/></svg>')
        return
    if path == "/api/browse":
        payload = route.request.post_data_json
        data = ({"items": [{"title": "Public channel", "id": "31", "info": "@sample"}], "more": False}
                if payload["section"] == "chats" else {"items": [], "more": False})
        if payload["section"] == "messages":
            data["items"] = [{"title": "Example chat", "id": "one", "info": "Most recent message",
                              "date": "2026-01-01T08:00:00Z"}]
        elif payload["section"] == "blocked":
            data["items"] = [{"title": "Blocked fixture", "id": "blocked-ref", "info": "@fixture"}]
    else:
        data = FIXTURES.get(path)
    route.fulfill(status=200 if data is not None else 404, json=data)


def main():
    root = Path(__file__).resolve().parents[1]
    handler = functools.partial(QuietHandler, directory=root / "miniapp")
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    executable_path=os.environ.get("KILLER_BROWSER"), headless=True)
                page = browser.new_page(viewport={"width": 1320, "height": 840})
                failures = []
                page.on("pageerror", lambda error: failures.append(str(error)))
                page.add_init_script("""window.Telegram = {WebApp: {
                    initData: "mock-init-data", ready() {}, expand() {}
                }};""")
                page.route("https://telegram.org/**", lambda route: route.abort())
                page.route("**/api/**", fixtures)
                page.route("**/api.php?**", fixtures)
                target = os.environ.get("KILLER_PUBLIC_PREVIEW") or f"http://127.0.0.1:{server.server_port}/"
                page.goto(target)
                expect(page).to_have_title("KILLER SELF")
                expect(page.locator("#content").get_by_text("متصل به حساب")).to_be_visible()
                expect(page.locator("html")).to_have_attribute("dir", "rtl")
                expect(page.locator(".hero")).to_be_visible()
                assert page.locator("html").evaluate(
                    "(node) => getComputedStyle(node).getPropertyValue('--midnight').trim()"
                ).lower() == "#101216"
                if len(sys.argv) > 2:
                    page.set_viewport_size({"width": 390, "height": 844})
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    page.screenshot(path=sys.argv[2], full_page=True, animations="disabled")
                    page.set_viewport_size({"width": 1320, "height": 840})
                page.locator("#language").click()
                expect(page.locator("html")).to_have_attribute("dir", "ltr")
                page.locator("#navigation").get_by_role("button", name="Chats", exact=True).click()
                expect(page.get_by_role("button", name="Public channel")).to_be_visible()
                page.locator(".workspace-filter summary").click()
                with page.expect_request(lambda request: request_path(request) == "/api/browse"
                                         and request.post_data_json.get("state") == "unread"):
                    page.locator(".tools select").filter(
                        has=page.locator('option[value="unread"]', has_text="Unread chats")
                    ).select_option("unread")
                page.get_by_role("button", name="Public channel").click()
                expect(page.get_by_role("heading", name="Public channel")).to_be_visible()
                page.get_by_role("button", name="Back").click()
                expect(page.locator(".workspace-filter select").filter(
                    has=page.locator('option[value="unread"]', has_text="Unread chats"))).to_have_value("unread")
                page.set_viewport_size({"width": 390, "height": 844})
                page.locator("#command").click()
                expect(page.get_by_role("heading", name="Unified search")).to_be_visible()
                expect(page.locator("dialog")).not_to_be_visible()
                page.locator("#mobile-nav").get_by_role("button", name="More").click()
                page.locator("dialog").get_by_role("button", name="Account & Security").click()
                page.get_by_role("button", name="Security", exact=True).click()
                expect(page.get_by_text("Two-step verification")).to_be_visible()
                page.get_by_role("button", name="Blocked accounts").click()
                expect(page.get_by_role("button", name="Blocked fixture")).to_be_visible()
                page.locator("#mobile-nav").get_by_role("button", name="Content").click()
                page.get_by_role("button", name="Saved Messages").click()
                expect(page.get_by_text("Most recent message")).to_be_visible()
                expect(page.get_by_text("Newest messages first")).to_be_visible()
                page.locator("#mobile-nav").get_by_role("button", name="Tools").click()
                page.get_by_role("button", name="Operation queue").click()
                expect(page.get_by_role("button", name="Run queue")).to_be_disabled()
                page.locator("#mobile-nav").get_by_role("button", name="Tools").click()
                expect(page.get_by_text("A channel about books.")).not_to_be_visible()
                page.get_by_role("button", name="Show profile · Public channel").click()
                expect(page.get_by_text("A channel about books.")).to_be_visible()
                expect(page.get_by_role("img", name="Photo")).to_be_visible()
                page.get_by_role("checkbox", name="Public channel").check()
                expect(page.get_by_text("A channel about books.")).to_be_visible()
                page.get_by_role("button", name="Compact list").click()
                expect(page.get_by_role("checkbox", name="Public channel")).to_be_checked()
                expect(page.get_by_text("A channel about books.")).not_to_be_visible()
                page.get_by_role("button", name="Operation queue").click()
                page.get_by_role("button", name="Run queue").click()
                with page.expect_request(lambda request: request_path(request) == "/api/command"
                                         and request.post_data_json["action"] == "cleanup_start") as call:
                    page.locator("dialog").get_by_role("button", name="Run queue").click()
                assert call.value.post_data_json["value"] == "31"
                expect(page.locator("dialog")).not_to_be_visible()
                expect(page.locator(".cleanup-report").get_by_text("Cleanup backups")).to_be_visible()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                if len(sys.argv) > 1:
                    page.screenshot(path=sys.argv[1], full_page=True, animations="disabled")
                assert not failures, failures
                browser.close()
        finally:
            server.shutdown()
            thread.join()
    print("Mini App browser smoke passed (RTL, LTR, chats, mobile navigation, security).")


if __name__ == "__main__":
    main()

