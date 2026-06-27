from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path


STATIC_ROOT = Path(__file__).resolve().parents[1] / "app" / "static"


class NavParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_nav = False
        self.nav_buttons: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "nav" and values.get("id") == "viewTabs":
            self.in_nav = True
        if self.in_nav and tag == "button" and values.get("data-view-tab"):
            self.nav_buttons.append(str(values["data-view-tab"]))

    def handle_endtag(self, tag: str) -> None:
        if tag == "nav" and self.in_nav:
            self.in_nav = False


def test_bottom_navigation_has_four_centered_tabs() -> None:
    html = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
    parser = NavParser()
    parser.feed(html)

    assert parser.nav_buttons == ["monitor", "transcripts", "summaries", "more"]
    assert 'data-view-tab="chat"' not in html

    css = (STATIC_ROOT / "styles.css").read_text(encoding="utf-8")
    assert "grid-template-columns: repeat(4, minmax(0, 1fr));" in css


def test_activity_chat_thread_is_persistent_and_pending_aware() -> None:
    html = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
    js = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")

    assert 'id="activityChatSendBtn" type="button"' in html
    assert 'action="javascript:void 0"' in html
    assert 'const activityChatThreadStorageKey = "repeaterwatch.activityChatThread";' in js
    assert "activityChatSendBtn: document.querySelector" in js
    assert "loadActivityChatMessages()" in js
    assert "saveActivityChatMessages()" in js
    assert "async function sendActivityChatMessage()" in js
    assert 'status: "pending"' in js
    assert 'message.status !== "pending" && message.status !== "error"' in js
    assert "activityChatMessages.map((item) => item.id === pendingMessage.id ? replacement : item)" in js


def test_service_worker_forces_static_shell_refresh() -> None:
    html = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
    sw = (STATIC_ROOT / "sw.js").read_text(encoding="utf-8")

    assert 'href="/styles.css?v=60"' in html
    assert 'src="/app.js?v=60"' in html
    assert 'const CACHE_NAME = "repeaterwatch-static-v60";' in sw
    assert '"/styles.css?v=60"' in sw
    assert '"/app.js?v=60"' in sw
    assert "caches.delete(key)" in sw
    assert "client.navigate(client.url)" in sw
