"""Shared helpers for the wiki browser tests: a headless Chromium, a static file server, a console guard.

Imported by the tests in this directory after they put the directory on sys.path. Every helper skips
the calling test (never fails it) when Playwright or the Chromium binary is not available.
"""
import contextlib
import functools
import http.server
import os
import threading
from pathlib import Path

import pytest

CHROME = "/home/bach/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome"
SKILL = Path(__file__).resolve().parents[2]  # kit/crew/skills/wiki

# Reports CSP violations through the console so console_guard sees them.
CSP_HOOK = (
    "document.addEventListener('securitypolicyviolation', (e) => "
    "console.error('securitypolicyviolation ' + e.violatedDirective + ' ' + e.blockedURI));"
)


def chrome_path() -> str:
    return os.environ.get("CHROME") or CHROME


@contextlib.contextmanager
def browser(**launch):
    """Yield a launched Chromium browser (Playwright sync API); skip when unavailable."""
    sync_api = pytest.importorskip("playwright.sync_api")
    exe = chrome_path()
    if not Path(exe).is_file():
        pytest.skip(f"chromium not found at {exe} (set CHROME)")
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch(executable_path=exe, args=["--no-sandbox"], **launch)
        try:
            yield b
        finally:
            b.close()


class _Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".js": "text/javascript",
        ".mjs": "text/javascript",
        ".css": "text/css",
        ".html": "text/html; charset=utf-8",
        ".svg": "image/svg+xml",
        ".json": "application/json",
    }

    def log_message(self, *args):  # keep test output clean
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def serve_dir(path):
    """Serve `path` statically on 127.0.0.1 (random port) in a daemon thread. Returns (url, stop)."""
    handler = functools.partial(_Handler, directory=str(path))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    srv.daemon_threads = True
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()

    def stop():
        srv.shutdown()
        srv.server_close()

    return f"http://127.0.0.1:{srv.server_address[1]}", stop


def console_guard(page) -> list:
    """Collect console errors, page errors and CSP violations of `page` into the returned list."""
    errors: list = []
    page.add_init_script(CSP_HOOK)
    page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    return errors
