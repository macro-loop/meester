"""Empirical check that this interpreter can actually run Meester.

macOS ships Python 3.9.6. The code is written to work there - every annotated
module carries `from __future__ import annotations`, and nothing uses match
statements or runtime unions - but "should work" is not good enough for
something that will then run unattended for months.

So instead of asserting a version number, setup runs this: it exercises one real
path through every module. If it passes on the interpreter setup picked, that
interpreter is fine and no Homebrew detour is needed. If it fails, setup asks
for a newer Python and says why.

Offline, no network, under a second.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

failures: list[str] = []


def check(label: str, got, want) -> None:
    if got != want:
        failures.append(f"{label}: got {got!r}, expected {want!r}")


def main() -> int:
    print(f"  interpreter: {sys.version.split()[0]} at {sys.executable}")

    # --- imports: dataclasses + lazy annotations are the 3.9 risk ---------------
    from meester.dedupe import dedupe
    from meester.models import Job, Workplace, normalize_company, normalize_title
    from meester.remote import classify_location_text, is_acceptable
    from meester.store import JobStore
    from meester.textutil import html_to_text

    # --- remote classification -------------------------------------------------
    mode, countries = classify_location_text("Remote, Canada; Remote, United States")
    check("multi-location remote", mode, Workplace.REMOTE)
    check("country extraction", countries == {"US", "CA"}, True)
    check("hybrid is not remote", classify_location_text("NYC (Hybrid)")[0], Workplace.HYBRID)
    check("policy accepts US remote", is_acceptable(Workplace.REMOTE, {"US"}, ["US"]), True)

    # --- normalisation ---------------------------------------------------------
    check("company normalisation",
          normalize_company("Stripe, Inc.") == normalize_company("stripe"), True)
    check("title normalisation", normalize_title("Backend Engineer (Remote)"), "backend engineer")

    # --- HTML decoding (Greenhouse double-escapes) -----------------------------
    check("double-unescape", html_to_text("&lt;p&gt;Hello&lt;/p&gt;").strip(), "Hello")

    # --- dataclass construction + dedupe ---------------------------------------
    def make(ext: str, source: str) -> Job:
        return Job(
            source=source, company="Stripe", company_token="stripe", external_id=ext,
            title="Senior Engineer", url=f"https://x/{ext}", workplace=Workplace.REMOTE,
            posted_at=datetime.now(timezone.utc),
        )

    merged = dedupe([make("1", "greenhouse"), make("2", "remoteok")])
    check("dedupe collapses cross-source duplicates", len(merged), 1)
    check("age_days works", merged[0].age_days() < 1, True)

    # --- store round-trip ------------------------------------------------------
    with TemporaryDirectory() as tmp:
        store = JobStore(Path(tmp) / "jobs.jsonl", Path(tmp) / "seen.json")
        check("first write", len(store.add_new(merged)), 1)
        check("idempotent second write", len(store.add_new(merged)), 0)

    if failures:
        print("\n  SMOKE TEST FAILED:")
        for f in failures:
            print(f"    - {f}")
        return 1

    print("  smoke test passed - this interpreter works")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
