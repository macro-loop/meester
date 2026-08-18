"""A test harness for the Clay outreach webhook - both directions.

Clay does not let you invent a webhook URL; it generates one when you create a
webhook-source table (Import -> Webhook). Use this to verify the payload shape
before wiring Clay up, and to fire a test row at the real Clay URL once you have
it.

  # 1. Run a local receiver that prints whatever Meester would send:
  python scripts/test_webhook.py serve            # listens on 127.0.0.1:9999

  # 2. In another terminal, fire the exact payload Meester sends, at the
  #    receiver above OR at your real Clay webhook URL:
  python scripts/test_webhook.py send http://127.0.0.1:9999/
  python scripts/test_webhook.py send https://api.clay.com/v3/sources/webhook/...

To point Meester itself at the local receiver, set in config/settings.yaml:
  outreach:
    clay_webhook_url: "http://127.0.0.1:9999/"
then trigger the outreach flow - the receiver prints the real request.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

# The exact shape meester/outreach.py -> request_contact() POSTs.
SAMPLE = {
    "fingerprint": "test0000deadbeef",
    "company": "Figma",
    "role": "Senior Product Designer",
    "job_url": "https://job-boards.greenhouse.io/figma/jobs/1234567",
    "requested_at": datetime.now(timezone.utc).isoformat(),
}


class Receiver(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8", "replace") if length else ""
        print("\n" + "=" * 60, flush=True)
        print(f"POST {self.path}  ({datetime.now().strftime('%H:%M:%S')})")
        print("-" * 60)
        try:
            print(json.dumps(json.loads(raw), indent=2))
        except json.JSONDecodeError:
            print(raw or "(empty body)")
        print("=" * 60, flush=True)
        body = b'{"ok": true, "received": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Meester test webhook receiver - POST here.\n")

    def log_message(self, *a) -> None:
        return


def serve(port: int = 9999) -> None:
    server = HTTPServer(("127.0.0.1", port), Receiver)
    print(f"Test webhook receiver on http://127.0.0.1:{port}/")
    print("Point clay_webhook_url here, or `send` to it. Ctrl-C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


def send(url: str) -> None:
    data = json.dumps(SAMPLE).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    print(f"POSTing sample payload to {url}\n{json.dumps(SAMPLE, indent=2)}\n")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"-> HTTP {resp.status}")
            print(resp.read().decode("utf-8", "replace")[:1000])
    except Exception as exc:  # noqa: BLE001
        print(f"-> failed: {type(exc).__name__}: {exc}")
        sys.exit(1)


def main(argv: list[str]) -> int:
    if len(argv) >= 1 and argv[0] == "serve":
        serve(int(argv[1]) if len(argv) > 1 else 9999)
    elif len(argv) >= 2 and argv[0] == "send":
        send(argv[1])
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
