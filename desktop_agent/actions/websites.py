"""Safe default-browser navigation for explicit website requests."""

from __future__ import annotations

from urllib.parse import urlsplit
import webbrowser


def open_website(url: str) -> dict[str, str]:
    """Open a validated HTTP(S) URL without invoking a shell."""
    if not isinstance(url, str) or not url.strip() or len(url) > 2048:
        raise ValueError("A valid website URL is required.")
    try:
        parsed = urlsplit(url.strip())
    except ValueError as exc:
        raise ValueError("The website URL is malformed.") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only HTTP and HTTPS websites can be opened.")
    if parsed.username or parsed.password or any(ch.isspace() for ch in url):
        raise ValueError("The website URL contains unsupported characters or credentials.")
    opened = webbrowser.open_new_tab(url.strip())
    if not opened:
        raise RuntimeError("Windows could not open the website in your default browser.")
    return {"success": True, "url": url.strip(), "message": "Opened " + parsed.hostname + " in your default browser."}
