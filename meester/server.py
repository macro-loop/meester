"""A very small local server so she can manage the watchlist without a terminal.

Bound to 127.0.0.1 only. It exists because a page opened as file:// cannot write
to disk, and Safari does not implement the File System Access API - so a local
server is the only way to give her a real editing UI on a Mac.

Security posture, since this does write to disk:
  * loopback interface only, never 0.0.0.0
  * every write requires a token generated on first run and embedded in the
    served page, so another site open in her browser cannot POST blindly
  * the Origin header is checked, which blocks the DNS-rebinding variant
  * the only thing any of it can change is which public job boards get read
"""

from __future__ import annotations

import json
import secrets
import threading
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .watchlist import ATS_CHOICES, add, load_local, merge, remove, save_local

MAX_BODY = 8192


def _token(path: Path) -> str:
    if path.exists():
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    value = secrets.token_urlsafe(24)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    return value


class Handler(BaseHTTPRequestHandler):
    server_version = "Meester"

    def __init__(self, *args, ctx: dict, **kwargs):
        self.ctx = ctx
        super().__init__(*args, **kwargs)

    # Quiet: every request would otherwise land in the launchd log.
    def log_message(self, fmt: str, *args) -> None:
        return

    # --- helpers ---------------------------------------------------------------

    def _send(self, code: int, body: bytes, ctype: str, cors: bool = False) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        # No CORS headers anywhere except /api/ping. Another origin must not be
        # able to read responses - that is what keeps the token secret. Ping is
        # the single exception because the report is opened as a file:// page,
        # whose origin is "null", and it needs some way to ask whether the
        # server is up. Ping returns no data and has no side effects, so making
        # it world-readable costs nothing.
        if cors:
            self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload: dict, cors: bool = False) -> None:
        self._send(
            code, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8", cors
        )

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        if origin is None:
            return True  # same-origin fetch from our own page sends none
        host = urlparse(origin).hostname
        return host in ("127.0.0.1", "localhost")

    def _authed(self) -> bool:
        return (
            self._origin_ok()
            and secrets.compare_digest(
                self.headers.get("X-Meester-Token", ""), self.ctx["token"]
            )
        )

    def _read_json(self) -> dict | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None
        if length <= 0 or length > MAX_BODY:
            return None
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None

    # --- routes ----------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path).path.rstrip("/") or "/"
        if route in ("/", "/jobs"):
            html = self.ctx["render_report"]()
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
        elif route == "/companies":
            html = self.ctx["render_companies"](self.ctx["token"])
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
        elif route == "/api/ping":
            self._json(200, {"ok": True}, cors=True)
        elif route == "/api/companies":
            self._json(200, self._snapshot())
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        route = urlparse(self.path).path.rstrip("/")
        if route not in ("/api/companies/add", "/api/companies/remove"):
            self._json(404, {"error": "not found"})
            return
        if not self._authed():
            self._json(403, {"error": "bad or missing token"})
            return

        body = self._read_json()
        if not isinstance(body, dict):
            self._json(400, {"error": "expected a JSON object"})
            return

        ats = str(body.get("ats", "")).strip().lower()
        token = str(body.get("token", "")).strip().lower()
        if ats not in ATS_CHOICES:
            self._json(400, {"error": f"ats must be one of {', '.join(ATS_CHOICES)}"})
            return
        if not token or len(token) > 80 or not all(c.isalnum() or c in "-_." for c in token):
            self._json(400, {"error": "that does not look like a board name"})
            return

        with self.ctx["lock"]:
            local = load_local(self.ctx["local_path"])
            if route.endswith("/add"):
                # Verify against the live board before accepting it, so a typo is
                # caught while she is looking at the screen rather than silently
                # producing a board that returns nothing for weeks.
                ok, count, err = self.ctx["verify"](ats, token)
                if not ok:
                    self._json(400, {"error": err or "no such board", "ats": ats, "token": token})
                    return
                add(local, ats, token)
                save_local(self.ctx["local_path"], local)
                self._json(200, {"ok": True, "jobs": count, **self._snapshot()})
                return
            remove(local, ats, token)
            save_local(self.ctx["local_path"], local)
            self._json(200, {"ok": True, **self._snapshot()})

    def _snapshot(self) -> dict:
        local = load_local(self.ctx["local_path"])
        base = self.ctx["load_base"]()
        merged = merge(base, local)
        return {
            "base": {k: sorted(v) for k, v in base.items() if k in ATS_CHOICES},
            "added": local.get("added") or {},
            "removed": local.get("removed") or {},
            "all": merged,
            "total": sum(len(v) for v in merged.values()),
        }


def serve(ctx: dict, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    ctx.setdefault("lock", threading.Lock())
    ctx["token"] = _token(ctx["token_path"])
    httpd = ThreadingHTTPServer((host, port), partial(Handler, ctx=ctx))
    return httpd
