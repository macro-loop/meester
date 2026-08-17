"""Route-layer tests against a real server on a loopback port.

Exists because of a live bug the unit tests could not see: /api/update put a
callback function inside the result dict, json.dumps threw mid-response, and
the client got an empty reply at the exact moment it needed the answer.
"""

import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from meester.server import serve


@pytest.fixture()
def live(tmp_path):
    calls = {"after": 0}

    def do_update():
        def after():
            calls["after"] += 1

        # The exact shape that broke in production: ok payload plus callback.
        return {"ok": True, "changed": True, "old": "aaa", "new": "bbb",
                "restarting": True, "_after_response": after}

    ctx = {
        "render_report": lambda: "<title>jobs</title>",
        "render_companies": lambda token: "<title>companies</title>",
        "load_base": lambda: {"greenhouse": ["stripe"]},
        "local_path": tmp_path / "companies.local.yaml",
        "token_path": tmp_path / ".server_token",
        "verify": lambda ats, token: (True, 1, ""),
        "search": lambda q: ([], []),
        "repo_status": lambda: {"sha": "aaa", "behind": 1, "dirty": False, "error": ""},
        "do_update": do_update,
    }
    httpd = serve(ctx, port=0)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}", ctx["token"], calls
    httpd.shutdown()
    httpd.server_close()


def _get(url: str) -> tuple[int, dict]:
    with urllib.request.urlopen(url, timeout=10) as r:
        return r.status, json.loads(r.read())


def _post(url: str, headers: dict | None = None, body: bytes = b"") -> tuple[int, dict]:
    req = urllib.request.Request(url, data=body, headers=headers or {}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_status_is_readable_without_a_token(live):
    base, _, _ = live
    code, data = _get(f"{base}/api/status")
    assert code == 200
    assert data["behind"] == 1


def test_update_without_token_is_rejected_and_nothing_runs(live):
    base, _, calls = live
    code, data = _post(f"{base}/api/update")
    assert code == 403
    assert calls["after"] == 0


def test_update_response_arrives_complete_before_the_restart_hook(live):
    """The production bug: the callback must never reach json.dumps, and the
    client must receive the full payload before the after-hook runs."""
    base, token, calls = live
    code, data = _post(f"{base}/api/update", headers={"X-Meester-Token": token})
    assert code == 200
    assert data == {"ok": True, "changed": True, "old": "aaa", "new": "bbb",
                    "restarting": True}
    assert "_after_response" not in data
    assert calls["after"] == 1


def test_pages_and_ping_still_serve(live):
    base, _, _ = live
    with urllib.request.urlopen(f"{base}/jobs", timeout=10) as r:
        assert b"jobs" in r.read()
    code, data = _get(f"{base}/api/ping")
    assert code == 200 and data["ok"]
