"""Google (Gmail + Sheets) over raw REST - no Google SDK.

The SDK pulls a large dependency tree for what is, for our needs, token refresh
plus a handful of REST calls. This is ~200 lines we control, on the httpx we
already depend on.

The personal-email contract lives in gmail_search(): it is the ONLY way to read
her mail, and it hard-requires the JobSearch label on every query, raising
otherwise. That mirrors the apply-answers doctrine - a safety rule made
unbypassable by making the safe path the only path.

Credentials she downloads once from Google Cloud land in
profile/google_credentials.json; the refreshable token is cached in
profile/google_token.json. Both sit in the gitignored, pre-push-guarded profile
dir. Scopes: gmail.modify (read + label + draft), gmail.send, spreadsheets
read-only (for the Clay export sheet).
"""

from __future__ import annotations

import base64
import json
import time
import webbrowser
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import httpx

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/spreadsheets.readonly",
]
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REQUIRED_LABEL = "JobSearch"


class GoogleAuthError(RuntimeError):
    pass


class GoogleApiError(RuntimeError):
    """A Google API returned an error. Carries Google's own reason so callers
    can show something better than a bare HTTP 403."""


class LabelScopeError(RuntimeError):
    """A Gmail read was attempted without the JobSearch label restriction."""


def _check(resp, what: str):
    """Raise GoogleApiError with Google's own message on any non-2xx.

    A raw resp.raise_for_status() gives '403 Forbidden' and nothing useful;
    the JSON body says whether it's a disabled API, a missing scope, or no
    access to a resource - exactly what someone needs to fix it."""
    if resp.status_code < 400:
        return resp
    detail = ""
    try:
        err = resp.json().get("error", {})
        detail = err.get("message") or err.get("status") or ""
    except Exception:  # noqa: BLE001
        detail = (resp.text or "")[:200]
    hint = ""
    low = detail.lower()
    if "has not been used" in low or "disabled" in low:
        hint = " — enable that API in your Google Cloud project (see docs/GOOGLE_SETUP.md)."
    elif "scope" in low:
        hint = " — reconnect with `python -m meester google-auth` to grant all permissions."
    elif resp.status_code == 403:
        hint = " — the connected account may not have access to it."
    raise GoogleApiError(f"{what}: {resp.status_code} {detail}{hint}")


class GoogleClient:
    def __init__(self, profile_dir: Path):
        self.creds_path = profile_dir / "google_credentials.json"
        self.token_path = profile_dir / "google_token.json"
        self._token: dict | None = None

    # --- availability -----------------------------------------------------------

    def configured(self) -> bool:
        return self.creds_path.exists()

    def connected(self) -> bool:
        return self.token_path.exists()

    def _client_config(self) -> dict:
        if not self.creds_path.exists():
            raise GoogleAuthError("no google_credentials.json - see the setup docs")
        raw = json.loads(self.creds_path.read_text(encoding="utf-8"))
        return raw.get("installed") or raw.get("web") or raw

    # --- the consent flow (interactive, once) -----------------------------------

    def authorize(self) -> None:
        """Loopback OAuth. Opens the browser, catches the redirect locally."""
        import http.server
        import socket
        import urllib.parse

        cfg = self._client_config()
        # Find a free loopback port for the redirect.
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        redirect = f"http://127.0.0.1:{port}/"

        params = {
            "client_id": cfg["client_id"],
            "redirect_uri": redirect,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",
            "prompt": "consent",
        }
        captured: dict = {}

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                captured.update(urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query))
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<h2>Meester is connected. You can close this tab.</h2>")

            def log_message(self, *a):
                return

        print(f"Opening your browser to authorize Meester...\n{AUTH_URL}?"
              + urllib.parse.urlencode(params))
        webbrowser.open(f"{AUTH_URL}?{urllib.parse.urlencode(params)}")
        server = http.server.HTTPServer(("127.0.0.1", port), Handler)
        server.handle_request()
        server.server_close()

        if "code" not in captured:
            raise GoogleAuthError(f"authorization failed: {captured}")

        resp = httpx.post(TOKEN_URL, data={
            "client_id": cfg["client_id"],
            "client_secret": cfg.get("client_secret", ""),
            "code": captured["code"][0],
            "grant_type": "authorization_code",
            "redirect_uri": redirect,
        }, timeout=30)
        resp.raise_for_status()
        token = resp.json()
        token["obtained_at"] = int(time.time())
        self._write_token(token)
        print("Connected. Token stored on this Mac only.")

    def _write_token(self, token: dict) -> None:
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.token_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(token), encoding="utf-8")
        tmp.replace(self.token_path)
        try:
            self.token_path.chmod(0o600)
        except OSError:
            pass

    def _access_token(self) -> str:
        if self._token is None:
            if not self.token_path.exists():
                raise GoogleAuthError("not connected - run: python -m meester google-auth")
            self._token = json.loads(self.token_path.read_text(encoding="utf-8"))
        tok = self._token
        fresh_enough = (tok.get("obtained_at", 0) + tok.get("expires_in", 0) - 120) > time.time()
        if tok.get("access_token") and fresh_enough:
            return tok["access_token"]
        # Refresh.
        cfg = self._client_config()
        resp = httpx.post(TOKEN_URL, data={
            "client_id": cfg["client_id"],
            "client_secret": cfg.get("client_secret", ""),
            "refresh_token": tok["refresh_token"],
            "grant_type": "refresh_token",
        }, timeout=30)
        resp.raise_for_status()
        refreshed = resp.json()
        tok["access_token"] = refreshed["access_token"]
        tok["expires_in"] = refreshed.get("expires_in", 3600)
        tok["obtained_at"] = int(time.time())
        self._write_token(tok)
        return tok["access_token"]

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._access_token()}"}

    # --- Gmail ------------------------------------------------------------------

    def gmail_search(self, query: str, max_results: int = 25) -> list[dict]:
        """Read her mail - ONLY within the JobSearch label.

        The label restriction is appended here and its presence is asserted, so
        no caller can widen the scope even by accident. This is the whole basis
        of the personal-email promise.
        """
        scoped = f"label:{REQUIRED_LABEL} {query}".strip()
        if f"label:{REQUIRED_LABEL}" not in scoped:
            raise LabelScopeError("refusing a Gmail read outside the JobSearch label")
        resp = httpx.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            headers=self._headers(),
            params={"q": scoped, "maxResults": max_results},
            timeout=30,
        )
        _check(resp, "reading your JobSearch mail")
        return resp.json().get("messages", [])

    def gmail_message(self, message_id: str) -> dict:
        resp = httpx.get(
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}",
            headers=self._headers(), params={"format": "full"}, timeout=30,
        )
        _check(resp, "reading a message")
        data = resp.json()
        headers = {h["name"].lower(): h["value"]
                   for h in data.get("payload", {}).get("headers", [])}
        return {
            "id": message_id,
            "threadId": data.get("threadId"),
            "from": headers.get("from", ""),
            "subject": headers.get("subject", ""),
            "date": headers.get("date", ""),
            "snippet": data.get("snippet", ""),
            "body": _extract_body(data.get("payload", {})),
        }

    def gmail_create_draft(self, to: str, subject: str, body: str,
                           thread_id: str | None = None) -> dict:
        """Draft only - never sends. Reply drafts land in her Gmail for review."""
        message = EmailMessage()
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        payload: dict[str, Any] = {"message": {"raw": raw}}
        if thread_id:
            payload["message"]["threadId"] = thread_id
        resp = httpx.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/drafts",
            headers=self._headers(), json=payload, timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def gmail_send(self, to: str, subject: str, body: str) -> dict:
        """Actually send - used only for approved outreach, her address."""
        message = EmailMessage()
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        resp = httpx.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            headers=self._headers(), json={"raw": raw}, timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    # --- Sheets (the Clay export) -----------------------------------------------

    def sheet_rows(self, spreadsheet_id: str, range_a1: str = "A:Z") -> list[list[str]]:
        resp = httpx.get(
            f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{range_a1}",
            headers=self._headers(), timeout=30,
        )
        _check(resp, "reading the Clay contact sheet")
        return resp.json().get("values", [])


def _extract_body(payload: dict) -> str:
    """First text/plain part, decoded. Good enough for classification."""
    def walk(part) -> str:
        if part.get("mimeType") == "text/plain":
            data = part.get("body", {}).get("data")
            if data:
                return base64.urlsafe_b64decode(data + "===").decode("utf-8", "replace")
        for sub in part.get("parts", []) or []:
            found = walk(sub)
            if found:
                return found
        return ""

    return walk(payload)[:8000]
