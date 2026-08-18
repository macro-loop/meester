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

    saved = {}

    def prefs_save(body):
        saved.update(body)
        return {"ok": True, "values": body}

    ctx = {
        "render_report": lambda: "<title>jobs</title>",
        "render_companies": lambda token: "<title>companies</title>",
        "render_profile": lambda token: "<title>profile</title>",
        "load_base": lambda: {"greenhouse": ["stripe"]},
        "local_path": tmp_path / "companies.local.yaml",
        "token_path": tmp_path / ".server_token",
        "verify": lambda ats, token: (True, 1, ""),
        "search": lambda q: ([], []),
        "repo_status": lambda: {"sha": "aaa", "behind": 1, "dirty": False, "error": ""},
        "do_update": do_update,
        "prefs_get": lambda: {"fields": [], "values": {"salary_floor": 1}},
        "prefs_save": prefs_save,
        "job_status_set": lambda body: {"ok": True, "got": body.get("state")},
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
    # The hook is *supposed* to run after the response is on the wire, so the
    # client observing the payload before the counter ticks is by design - poll
    # briefly rather than racing the handler thread.
    import time
    deadline = time.monotonic() + 5
    while calls["after"] != 1 and time.monotonic() < deadline:
        time.sleep(0.05)
    assert calls["after"] == 1


def test_pages_and_ping_still_serve(live):
    base, _, _ = live
    for page, marker in (("/jobs", b"jobs"), ("/profile", b"profile")):
        with urllib.request.urlopen(f"{base}{page}", timeout=10) as r:
            assert marker in r.read()
    code, data = _get(f"{base}/api/ping")
    assert code == 200 and data["ok"]


def test_preferences_read_open_write_gated(live):
    base, token, _ = live
    code, data = _get(f"{base}/api/profile/preferences")
    assert code == 200 and data["values"]["salary_floor"] == 1

    code, _ = _post(f"{base}/api/profile/preferences", body=b'{"salary_floor": 2}',
                    headers={"Content-Type": "application/json"})
    assert code == 403

    code, data = _post(
        f"{base}/api/profile/preferences", body=b'{"salary_floor": 2}',
        headers={"Content-Type": "application/json", "X-Meester-Token": token},
    )
    assert code == 200 and data["ok"]


def test_job_status_write_is_gated(live):
    base, token, _ = live
    body = b'{"fingerprint": "abc", "state": "starred"}'
    code, _ = _post(f"{base}/api/jobs/status", body=body,
                    headers={"Content-Type": "application/json"})
    assert code == 403
    code, data = _post(f"{base}/api/jobs/status", body=body,
                       headers={"Content-Type": "application/json",
                                "X-Meester-Token": token})
    assert code == 200 and data["ok"] and data["got"] == "starred"


def test_tailscale_hosts_are_allowed_but_others_still_rejected(live):
    """Mobile access rides `tailscale serve`, which proxies with Host set to
    the Mac's MagicDNS name. That namespace is Tailscale-controlled, so
    allowing it does not reopen the rebinding hole for anyone else."""
    base, _, _ = live
    req = urllib.request.Request(f"{base}/api/ping",
                                 headers={"Host": "her-mac.tail1234.ts.net"})
    with urllib.request.urlopen(req, timeout=10) as r:
        assert r.status == 200
    # A name merely CONTAINING ts.net must not pass.
    for evil in ("ts.net.evil.example", "evilts.net", "notts.nett"):
        req = urllib.request.Request(f"{base}/api/ping", headers={"Host": evil})
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req, timeout=10)
        assert e.value.code == 403, evil


def test_wrong_host_header_is_rejected_everywhere(live):
    """DNS-rebinding guard: an attacker's domain resolving to 127.0.0.1 sends
    their hostname in Host, and every route must refuse it - reads included,
    because preferences and soon the resume flow through GET responses."""
    base, token, _ = live
    for path in ("/api/profile/preferences", "/api/status", "/jobs"):
        req = urllib.request.Request(f"{base}{path}", headers={"Host": "evil.example"})
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req, timeout=10)
        assert e.value.code == 403

    req = urllib.request.Request(
        f"{base}/api/update", data=b"", method="POST",
        headers={"Host": "evil.example", "X-Meester-Token": token},
    )
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req, timeout=10)
    assert e.value.code == 403
