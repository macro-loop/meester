"""Meester CLI.

    python -m meester harvest            # fetch, filter, dedupe, store
    python -m meester harvest --dry-run  # same, but write nothing
    python -m meester verify-companies   # probe every board token
    python -m meester show --limit 20    # print what is in the store
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

import yaml

from .harvest.run import harvest, verify_tokens
from .store import JobStore

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"


def _load(name: str) -> dict:
    path = CONFIG / name
    if not path.exists():
        sys.exit(f"missing config file: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


LOCAL_COMPANIES = CONFIG / "companies.local.yaml"


def _profile_bits() -> tuple[dict, dict | None]:
    """Preferences + verified ledger, for scoring at report time."""
    from .profile import load_ledger, load_preferences

    return (
        load_preferences(ROOT / "profile" / "preferences.yaml"),
        load_ledger(ROOT / "profile" / "facts_ledger.json"),
    )


def _load_base_companies(explicit: str | None = None) -> dict:
    """Prefer the verified token list; fall back to the raw seed list.

    Roughly 40% of hand-written board tokens are wrong or stale, so harvesting
    straight from the seed file wastes a chunk of every run on 404s.
    """
    if explicit:
        return _load(explicit)
    if (CONFIG / "companies.verified.yaml").exists():
        return _load("companies.verified.yaml")
    print("note: no companies.verified.yaml - using unverified seed list.")
    print("      run `python -m meester verify-companies --write` first.\n")
    return _load("companies.yaml")


def _load_companies(explicit: str | None = None) -> dict:
    """The tracked list plus whatever she added from the Companies screen."""
    from .watchlist import load_local, merge

    base = _load_base_companies(explicit)
    local = load_local(LOCAL_COMPANIES)
    merged = merge(base, local)
    extra = sum(len(v) for v in (local.get("added") or {}).values())
    if extra:
        print(f"watchlist: {extra} company(ies) added locally")
    return merged


def _fmt(job) -> str:
    where = ",".join(job.remote_countries) or "?"
    age = job.age_days()
    age_s = f"{age:.0f}d" if age is not None else " ?"
    return f"  [{job.source[:4]:<4}] {age_s:>4}  {job.company[:18]:<18} {job.title[:56]:<56} ({where})"


async def cmd_harvest(args: argparse.Namespace) -> int:
    settings = _load("settings.yaml")
    companies = _load_companies(args.companies)

    jobs, report = await harvest(companies, settings)
    print(f"\n{report.summary()}\n")

    if report.boards_failed:
        print(f"failed boards ({len(report.boards_failed)}):")
        for ats, token, err in report.boards_failed[:15]:
            print(f"  {ats:<11} {token:<22} {err[:70]}")
        if len(report.boards_failed) > 15:
            print(f"  ... and {len(report.boards_failed) - 15} more")
        print("  (run `verify-companies` to prune dead tokens)\n")

    if args.dry_run:
        print(f"DRY RUN - nothing written. Top {min(args.limit, len(jobs))} of {len(jobs)}:\n")
        for job in jobs[: args.limit]:
            print(_fmt(job))
        return 0

    store_cfg = settings.get("store", {})
    store = JobStore(ROOT / store_cfg.get("path", "data/jobs.jsonl"),
                     ROOT / store_cfg.get("seen_path", "data/seen.json"))
    before = len(store)
    added = store.add_new(jobs)
    print(f"store: {before} known -> {len(store)} known ({len(added)} new)")

    # Regenerate the readable report every run. This is the only output anyone
    # other than a developer ever looks at, so it must never go stale - and a
    # failure here must not lose a successful harvest.
    try:
        from .report import build_report

        rows = [
            json.loads(line)
            for line in (ROOT / store_cfg.get("path", "data/jobs.jsonl"))
            .read_text(encoding="utf-8")
            .splitlines()
            if line
        ]
        prefs, ledger = _profile_bits()
        out = build_report(
            rows, ROOT / store_cfg.get("report_path", "data/jobs.html"),
            prefs=prefs, ledger=ledger,
        )
        print(f"report: {out}\n")
    except Exception as exc:  # noqa: BLE001
        print(f"warning: could not write report ({type(exc).__name__}: {exc})\n")

    for job in added[: args.limit]:
        print(_fmt(job))
    return 0


async def cmd_verify(args: argparse.Namespace) -> int:
    settings = _load("settings.yaml")
    companies = _load("companies.yaml")

    results = await verify_tokens(companies, settings)
    good: dict[str, list[str]] = {}
    for ats, tokens in results.items():
        ok = sorted(t for t, err in tokens.items() if not err)
        bad = sorted((t, err) for t, err in tokens.items() if err)
        good[ats] = ok
        print(f"\n{ats}: {len(ok)} live, {len(bad)} dead")
        for token, err in bad:
            print(f"  DEAD  {token:<22} {err[:60]}")

    total_ok = sum(len(v) for v in good.values())
    print(f"\n{total_ok} live board tokens total")

    if args.write:
        out = CONFIG / "companies.verified.yaml"
        header = (
            "# Auto-generated by `python -m meester verify-companies --write`.\n"
            "# Only tokens that actually resolved to a live board with postings.\n\n"
        )
        out.write_text(header + yaml.safe_dump(good, sort_keys=True), encoding="utf-8")
        print(f"wrote {out}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    from .report import build_report

    settings = _load("settings.yaml")
    store_cfg = settings.get("store", {})
    path = ROOT / store_cfg.get("path", "data/jobs.jsonl")
    if not path.exists():
        print("store is empty - run `python -m meester harvest` first")
        return 1
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    prefs, ledger = _profile_bits()
    out = build_report(
        rows, ROOT / store_cfg.get("report_path", "data/jobs.html"),
        prefs=prefs, ledger=ledger,
    )
    print(f"report: {len(rows)} roles -> {out}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    """Local-only web UI: watchlist, profile, updates - no terminal needed."""
    from .harvest.base import BoardClient
    from .harvest.run import FETCHERS
    from .profile import load_preferences, save_preferences, schema_for_client
    from .report import (
        build_companies_page,
        build_letters_page,
        build_profile_page,
        build_report,
        build_resume_page,
    )
    from .server import serve

    settings = _load("settings.yaml")
    store_cfg = settings.get("store", {})
    store_path = ROOT / store_cfg.get("path", "data/jobs.jsonl")

    def render_report() -> str:
        from .report import render_report_html

        rows = (
            [json.loads(l) for l in store_path.read_text(encoding="utf-8").splitlines() if l]
            if store_path.exists()
            else []
        )
        # Refresh the Desktop file (token-free) as a side effect, then serve a
        # variant carrying the write token so the update button can install.
        # ctx["token"] is set by serve() before the first request is handled.
        prefs, ledger = _profile_bits()
        build_report(rows, ROOT / store_cfg.get("report_path", "data/jobs.html"),
                     prefs=prefs, ledger=ledger)
        return render_report_html(rows, server_token=ctx.get("token"),
                                  prefs=prefs, ledger=ledger)

    def verify(ats: str, token: str) -> tuple[bool, int, str]:
        """Check a board really exists, and report how many roles are *remote*.

        Returning the raw opening count would be misleading: Faire, for one, has
        67 openings of which 60 are office-based. Telling her "67" and then
        showing none in her list is a confusing gap, so the count reported is
        the one that will actually reach her.
        """
        from .remote import is_acceptable

        async def probe():
            hcfg = settings.get("harvest", {})
            async with BoardClient(
                concurrency=1,
                timeout=hcfg.get("timeout_seconds", 45),
                retries=0,
                user_agent=hcfg.get("user_agent", "Meester/0.1"),
            ) as client:
                return await FETCHERS[ats](client, token)

        try:
            jobs, err = asyncio.run(probe())
        except Exception as exc:  # noqa: BLE001
            return False, 0, f"could not reach the board ({type(exc).__name__})"
        if err:
            return False, 0, f"no {ats} board called '{token}'"
        if not jobs:
            return False, 0, f"'{token}' exists on {ats} but has no open roles"

        rcfg = settings.get("remote", {})
        accept = rcfg.get("accept_countries", ["ANY"])
        remote = sum(
            1
            for j in jobs
            if is_acceptable(
                j.workplace, set(j.remote_countries), accept, rcfg.get("accept_hybrid", False)
            )
        )
        return True, remote, ""

    def search(query: str) -> tuple[list[dict], list[str]]:
        """Resolve a company name or pasted careers link to live boards."""
        from .lookup import find_boards

        try:
            matches, tried = asyncio.run(
                find_boards(query, user_agent=settings.get("harvest", {}).get("user_agent", "Meester/0.1"))
            )
        except Exception:  # noqa: BLE001 - a lookup failure must not kill the server
            return [], []
        return [m.as_dict() for m in matches], tried

    # A fetch on every status poll would hammer GitHub - every page load asks.
    # Cache for a minute; an update busts the cache so the pill clears at once.
    _status_cache: dict = {"at": 0.0, "data": None}

    def repo_status() -> dict:
        import time

        from .update import check

        now = time.monotonic()
        if _status_cache["data"] is None or now - _status_cache["at"] > 60:
            _status_cache["data"] = check(ROOT).as_dict()
            _status_cache["at"] = now
        return _status_cache["data"]

    def do_update() -> dict:
        import os
        import subprocess
        import threading

        from .update import update

        result = update(ROOT)
        _status_cache["data"] = None
        if not (result.get("ok") and result.get("changed")):
            return result

        def after_response() -> None:
            # The process now running is the OLD code. Kick off a harvest on
            # the new code (detached, so it survives our exit), then exit and
            # let launchd's KeepAlive restart the server on the new version.
            script = ROOT / "scripts" / "run_harvest.sh"
            if os.name == "posix" and script.exists() and not os.environ.get("MEESTER_SKIP_HARVEST"):
                try:
                    subprocess.Popen(
                        ["/bin/bash", str(script)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True,
                    )
                except OSError:
                    pass  # harvest is a bonus here; the hourly job covers it
            threading.Timer(1.0, os._exit, args=(0,)).start()

        result["restarting"] = True
        result["_after_response"] = after_response
        return result

    prefs_path = ROOT / "profile" / "preferences.yaml"
    profile_dir = ROOT / "profile"
    ledger_path = profile_dir / "facts_ledger.json"

    def prefs_get() -> dict:
        return {"fields": schema_for_client(), "values": load_preferences(prefs_path)}

    def prefs_save(body: dict) -> dict:
        clean, errors = save_preferences(prefs_path, body)
        if errors:
            return {"ok": False, "errors": errors}
        return {"ok": True, "values": clean}

    def _stored_resume() -> Path | None:
        for name in ("resume.pdf", "resume.docx"):
            if (profile_dir / name).exists():
                return profile_dir / name
        return None

    def resume_file() -> tuple[bytes, str] | None:
        path = _stored_resume()
        if path is None:
            return None
        ctype = (
            "application/pdf"
            if path.suffix == ".pdf"
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        return path.read_bytes(), ctype

    def resume_save(body: dict) -> dict:
        import base64

        from .extract import sniff_kind

        try:
            data = base64.b64decode(str(body.get("content_b64", "")), validate=True)
        except (ValueError, TypeError):
            return {"ok": False, "error": "the file didn't upload cleanly - try again"}
        if not data or len(data) > 15_000_000:
            return {"ok": False, "error": "that file is empty or larger than 15 MB"}

        kind = sniff_kind(data)  # trusts bytes, never the filename she picked
        if not kind:
            return {"ok": False, "error": "that doesn't look like a PDF or Word file"}

        profile_dir.mkdir(parents=True, exist_ok=True)
        target = profile_dir / f"resume.{kind}"
        other = profile_dir / ("resume.docx" if kind == "pdf" else "resume.pdf")
        tmp = target.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(target)
        other.unlink(missing_ok=True)
        return {"ok": True, "kind": kind, "bytes": len(data)}

    def resume_extract() -> dict:
        from .extract import draft_ledger, to_text

        path = _stored_resume()
        if path is None:
            return {"ok": False, "error": "upload a CV first"}
        try:
            kind, text = to_text(path.read_bytes())
        except Exception as exc:  # noqa: BLE001 - a weird PDF must not 500
            return {"ok": False, "error": f"couldn't read that file ({type(exc).__name__})"}
        if not text.strip():
            return {
                "ok": False,
                "error": "no text found - this looks like a scanned image rather "
                "than a text PDF. Fill the sections in by hand instead.",
            }
        return {"ok": True, "draft": draft_ledger(text)}

    def ledger_get() -> dict:
        from .profile import load_ledger

        path = _stored_resume()
        return {
            "ledger": load_ledger(ledger_path),
            "resume": {"kind": path.suffix[1:], "bytes": path.stat().st_size} if path else None,
        }

    def ledger_save(body: dict) -> dict:
        from .profile import save_ledger

        return {"ok": True, "ledger": save_ledger(ledger_path, body)}

    letters_path = profile_dir / "cover_letters.yaml"

    def _sample_job() -> dict:
        """A real posting from the store, so letter previews use a job she has
        actually seen rather than an invented one."""
        try:
            with store_path.open(encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        row = json.loads(line)
                        return {"company": row.get("company") or "Figma",
                                "role": row.get("title") or "Product Designer"}
        except (OSError, json.JSONDecodeError):
            pass
        return {"company": "Figma", "role": "Product Designer"}

    def letters_get() -> dict:
        from .profile import lint_placeholders, load_letters

        letters = load_letters(letters_path)
        return {
            "letters": letters,
            "warnings": {str(i): w for i, l in enumerate(letters) if (w := lint_placeholders(l["body"]))},
            "sample": _sample_job(),
        }

    def letters_save(body: dict) -> dict:
        from .profile import lint_placeholders, save_letters

        clean, errors = save_letters(letters_path, body)
        if errors:
            return {"ok": False, "errors": errors}
        return {
            "ok": True,
            "letters": clean,
            "warnings": {str(i): w for i, l in enumerate(clean) if (w := lint_placeholders(l["body"]))},
        }

    ctx = {
        "render_report": render_report,
        "render_companies": build_companies_page,
        "load_base": lambda: _load_base_companies(None),
        "local_path": LOCAL_COMPANIES,
        "token_path": ROOT / "data" / ".server_token",
        "verify": verify,
        "search": search,
        "repo_status": repo_status,
        "do_update": do_update,
        "render_profile": build_profile_page,
        "prefs_get": prefs_get,
        "prefs_save": prefs_save,
        "render_resume": build_resume_page,
        "resume_file": resume_file,
        "resume_save": resume_save,
        "resume_extract": resume_extract,
        "ledger_get": ledger_get,
        "ledger_save": ledger_save,
        "render_letters": build_letters_page,
        "letters_get": letters_get,
        "letters_save": letters_save,
    }

    httpd = serve(ctx, port=args.port)
    print(f"Meester UI on http://127.0.0.1:{args.port}/  (Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    settings = _load("settings.yaml")
    path = ROOT / settings.get("store", {}).get("path", "data/jobs.jsonl")
    if not path.exists():
        print("store is empty - run `python -m meester harvest` first")
        return 0
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    print(f"{len(rows)} jobs in store\n")
    for r in rows[-args.limit:]:
        where = ",".join(r.get("remote_countries") or []) or "?"
        print(f"  [{r['source'][:4]:<4}] {r['company'][:18]:<18} {r['title'][:56]:<56} ({where})")
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="meester")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_h = sub.add_parser("harvest", help="fetch, filter, dedupe and store")
    p_h.add_argument("--dry-run", action="store_true", help="write nothing")
    p_h.add_argument("--limit", type=int, default=25)
    p_h.add_argument("--companies", help="config filename to use (default: verified list)")

    p_v = sub.add_parser("verify-companies", help="probe every configured board token")
    p_v.add_argument("--write", action="store_true", help="write config/companies.verified.yaml")

    sub.add_parser("report", help="write the readable HTML report")

    p_srv = sub.add_parser("serve", help="local UI for editing the watchlist")
    p_srv.add_argument("--port", type=int, default=8765)

    p_s = sub.add_parser("show", help="print the local store")
    p_s.add_argument("--limit", type=int, default=25)

    args = parser.parse_args(argv)
    if args.cmd == "harvest":
        return asyncio.run(cmd_harvest(args))
    if args.cmd == "verify-companies":
        return asyncio.run(cmd_verify(args))
    if args.cmd == "report":
        return cmd_report(args)
    if args.cmd == "serve":
        return cmd_serve(args)
    return cmd_show(args)


if __name__ == "__main__":
    raise SystemExit(main())
