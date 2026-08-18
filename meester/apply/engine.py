"""The apply engine: turns approved queue items into submitted applications.

Runs on her Mac only - the whole architecture pins submission to her machine,
her network, her real browser fingerprint. Safety posture, all enforced here
rather than remembered:

  * processes only `approved` items - approval is her tap, always
  * PAUSED file checked before every single item
  * daily cap; human pacing between items (60-180s jitter)
  * CAPTCHA -> needs_human, never solved
  * every outcome leaves evidence: filled-form screenshot, the exact values
    submitted and their sources, and a confirmation screenshot
  * dry_run does everything except click Submit
"""

from __future__ import annotations

import json
import random
import time
from datetime import datetime, timezone
from pathlib import Path

from .adapters import (
    FillReport,
    captcha_present,
    fill_form,
    find_submit,
    pick_adapter,
)
from .answers import NeedsHuman
from .queue import Queue

DEFAULT_DAILY_CAP = 15
PACE_SECONDS = (60, 180)


def fill_letter(body: str, job: dict, why_them: str = "") -> str:
    """Deterministic placeholder fill. {why_them}/{their_product} come from the
    queue item (LLM-drafted or her own words); an unfilled one is a hard stop
    upstream, so by the time this runs the letter is complete."""
    out = (body or "")
    out = out.replace("{company}", job.get("company", ""))
    out = out.replace("{role}", job.get("title", ""))
    if why_them:
        out = out.replace("{why_them}", why_them)
    return out


def letter_ready(body: str) -> bool:
    """A letter still carrying un-filled placeholders must not be sent."""
    import re

    return not re.search(r"\{[a-zA-Z_]+\}", body or "")


class Engine:
    def __init__(
        self,
        queue: Queue,
        profile: dict,
        ledger: dict | None,
        resume_path: Path | None,
        evidence_dir: Path,
        paused_file: Path,
        daily_cap: int = DEFAULT_DAILY_CAP,
        pace: tuple[int, int] = PACE_SECONDS,
    ):
        self.queue = queue
        self.profile = profile
        self.ledger = ledger
        self.resume_path = resume_path
        self.evidence_dir = evidence_dir
        self.paused_file = paused_file
        self.daily_cap = daily_cap
        self.pace = pace

    # --- preflight: everything that can fail without a browser ------------------

    def preflight(self, item: dict) -> str | None:
        """Returns a needs_human reason, or None when the item can proceed."""
        if not (self.profile.get("app_first_name") and self.profile.get("app_email")
                or self.profile.get("app_email")):
            return "Fill in the Application answers section of your profile first"
        if self.resume_path is None:
            return "Upload your CV first - applications attach the real file"
        job = item.get("job") or {}
        if pick_adapter(job.get("apply_url") or job.get("url") or "") is None:
            return "This site isn't one I can fill in - apply by hand from the link"
        letter = item.get("letter_body") or ""
        if letter and not letter_ready(fill_letter(letter, job, item.get("why_them", ""))):
            return "The cover letter still has blanks - fill them in on the card"
        return None

    # --- the run ----------------------------------------------------------------

    def _launch(self, pw):
        """Launch chromium; if the binary is missing (fresh setup, or a pip
        upgrade moved the pinned browser version), install it once and retry.
        Returns None when a browser truly cannot be had this run."""
        try:
            return pw.chromium.launch(headless=True)
        except Exception as exc:  # noqa: BLE001 - playwright's Error, plus IO
            if "Executable doesn't exist" not in str(exc):
                raise
        import subprocess
        import sys
        print("apply engine: browser missing - downloading chromium (one-time)")
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True, text=True, timeout=900,
        )
        if result.returncode != 0:
            print("apply engine: chromium install failed - "
                  "approved items will retry next cycle")
            return None
        try:
            return pw.chromium.launch(headless=True)
        except Exception:  # noqa: BLE001
            return None

    def run(self, dry_run: bool = True, limit: int | None = None) -> list[dict]:
        """Process approved application items. Returns per-item outcomes."""
        outcomes: list[dict] = []
        self.queue.expire_stale()
        items = [i for i in self.queue.by_state("approved")
                 if i.get("kind") == "application"]
        if limit is not None:
            items = items[:limit]
        if not items:
            return outcomes

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = self._launch(pw)
            if browser is None:
                # Items stay `approved` - they run untouched next cycle once
                # the browser exists. Never a traceback on an unattended Mac.
                return [{"id": i["id"], "outcome": "browser-missing"} for i in items]
            for index, item in enumerate(items):
                if self.paused_file.exists():
                    outcomes.append({"id": item["id"], "outcome": "paused"})
                    break
                if not dry_run and self.queue.submitted_today() >= self.daily_cap:
                    outcomes.append({"id": item["id"], "outcome": "daily-cap"})
                    break

                reason = self.preflight(item)
                if reason:
                    self.queue.transition(item["id"], "needs_human", needs=reason)
                    outcomes.append({"id": item["id"], "outcome": "needs_human",
                                     "reason": reason})
                    continue

                if index > 0 and not dry_run:
                    time.sleep(random.randint(*self.pace))

                outcome = self._apply_one(browser, item, dry_run)
                outcomes.append(outcome)
            browser.close()
        return outcomes

    def _apply_one(self, browser, item: dict, dry_run: bool) -> dict:
        job = item.get("job") or {}
        url = job.get("apply_url") or job.get("url") or ""
        config = pick_adapter(url)
        if config and config.to_apply_url:
            url = config.to_apply_url(url)

        evidence = self.evidence_dir / item["id"]
        evidence.mkdir(parents=True, exist_ok=True)
        if not dry_run:
            self.queue.transition(item["id"], "submitting")

        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 900},
        )
        page = context.new_page()
        report = FillReport()
        try:
            page.goto(url, timeout=45_000, wait_until="domcontentloaded")
            page.wait_for_timeout(2500)  # boards hydrate their forms client-side

            if captcha_present(page):
                return self._stop(item, page, evidence, "needs_human",
                                  "This form has a CAPTCHA - open the link and "
                                  "apply by hand", dry_run)

            letter = fill_letter(item.get("letter_body") or "", job,
                                 item.get("why_them", ""))
            try:
                fill_form(page, self.profile, self.ledger, letter,
                          self.resume_path, report)
            except NeedsHuman as stop:
                return self._stop(item, page, evidence, "needs_human",
                                  str(stop), dry_run)

            page.screenshot(path=str(evidence / "filled.png"), full_page=True)
            (evidence / "submitted.json").write_text(
                json.dumps({"url": url, "dry_run": dry_run,
                            "at": datetime.now(timezone.utc).isoformat(),
                            **report.as_dict()}, ensure_ascii=False, indent=1),
                encoding="utf-8",
            )

            submit = find_submit(page, config)
            if submit is None:
                return self._stop(item, page, evidence, "needs_human",
                                  "Couldn't find the submit button - the form "
                                  "layout is unfamiliar", dry_run)

            if dry_run:
                return {"id": item["id"], "outcome": "dry-run",
                        "filled": len(report.filled),
                        "resume": report.resume_attached,
                        "evidence": str(evidence)}

            submit.click()
            confirmed = False
            try:
                page.wait_for_function(
                    "() => /thank|application.{0,40}(received|submitted)|"
                    "we.{0,20}received/i.test(document.body.innerText)",
                    timeout=20_000,
                )
                confirmed = True
            except Exception:  # noqa: BLE001
                pass
            page.screenshot(path=str(evidence / "confirm.png"), full_page=True)
            self.queue.transition(item["id"], "submitted",
                                  confirmed=confirmed, evidence=str(evidence))
            return {"id": item["id"], "outcome": "submitted", "confirmed": confirmed}

        except Exception as exc:  # noqa: BLE001 - one bad page must not stop the run
            try:
                page.screenshot(path=str(evidence / "error.png"), full_page=True)
            except Exception:  # noqa: BLE001
                pass
            if not dry_run:
                self.queue.transition(item["id"], "failed",
                                      error=f"{type(exc).__name__}: {exc}"[:300])
            return {"id": item["id"], "outcome": "failed",
                    "error": f"{type(exc).__name__}: {exc}"[:300]}
        finally:
            context.close()

    def _stop(self, item: dict, page, evidence: Path, state: str,
              reason: str, dry_run: bool) -> dict:
        try:
            page.screenshot(path=str(evidence / "stopped.png"), full_page=True)
        except Exception:  # noqa: BLE001
            pass
        if not dry_run:
            self.queue.transition(item["id"], state, needs=reason)
        return {"id": item["id"], "outcome": state, "reason": reason}
