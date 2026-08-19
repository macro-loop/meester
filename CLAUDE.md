# Meester — notes for Claude Code

## What this is, and why it needs care

Meester runs one real person's live job search. A MacBook executes it unattended
every hour and **submits real applications to real employers under her name**.

Breakage here is not a red build. It is a week of missed roles that nobody
notices, or an application sent with the wrong answers. Prefer the boring,
reversible change. When something is ambiguous, ask her rather than guessing.

## Which folder am I in? Check this first.

| Folder | What it is |
|---|---|
| `~/Meester` | **PRODUCTION.** launchd runs it hourly. Do not edit, do not commit, do not run setup here. |
| `~/meester-dev` | The editing copy. All work happens here. |

If `pwd` is the production folder, stop and tell her to `cd ~/meester-dev`.

Why it matters: any edit in production leaves the tree dirty, which silently
disables *both* the hourly `git pull --ff-only` in `scripts/run_harvest.sh` and
the "Update available — install" button (`meester/update.py` refuses when
`st.dirty`). Neither failure is announced anywhere she looks. Meanwhile the
hourly job keeps executing whatever is on disk — including `apply-run --live`.

`scripts/setup_dev.sh` and `scripts/setup_mac.sh` both refuse to run in the wrong
folder. Do not work around those guards.

## Hard rules

**The repository is PUBLIC.** Never commit anything under `profile/` except
`README.md` and `preferences.example.yaml`. Never commit a `.pdf` or `.docx`.
Never `git add -f` to get past the ignore rules. A push cannot be undone — a
reverted commit still lives in the history and in every clone. `profile/` holds
her CV, full name, address, phone, employment history, Anthropic key and Google
token.

**Never break `scripts/*.sh`.** Broken Python self-heals: the next scheduled run
pulls the fix *before* executing it. A bash syntax error does not — bash dies
before reaching the `git pull`, and the Mac is stranded until someone physically
touches it. Run `bash -n scripts/*.sh` before every commit.

**Never run `python -m meester apply-run --live` in the dev clone.** Once
`/preview` has copied her real `data/` and `profile/` in, the dev clone has
approved queue items and working credentials, and it will submit them for real.

**Machine-local settings go in `config/settings.local.yaml`**, never in the
tracked `config/settings.yaml`. The local file is gitignored and merged one level
deep over the tracked one — see `_load()` in `meester/__main__.py`. Editing the
tracked file on her Mac blocks every future pull that touches it.

**Gmail is hard-scoped to `label:JobSearch`** (`meester/inbox.py`,
`meester/google_api.py`). She uses her personal address, and that scoping is the
entire reason automation can be trusted near it. The wrapper raises on any query
without the label. Never widen it, never add a scope, never "just this once" read
outside the label.

**`meester/apply/answers.py` never guesses.** A form question maps to a profile
answer only by exact match against the curated pattern table; anything unmapped
routes to her. Legal and EEO questions are never inferred. CAPTCHAs are never
solved — they become `needs_human`. Nothing submits or sends without an explicit
approval in the queue.

**Python 3.9 floor.** `setup_mac.sh` accepts the 3.9 macOS ships, so her laptop
may be running it. Modules use `from __future__ import annotations`, so `int |
None` is fine in an annotation but not at runtime, and there is no `match`.

## Before you commit

```bash
bash -n scripts/*.sh
.venv/bin/python -m pytest tests/ -q      # the venv one — pytest is not in the system python
```

The pre-push hook runs both plus a personal-data scan. GitHub Actions re-runs
them after the push. Do not reach for `--no-verify` unless she asks for it and
the change is docs-only.

Commit messages are imperative one-liners, matching the existing log:
`Guide: mention the Google Sheet application ledger`.

## Blast radius — say so out loud before touching these

- `scripts/run_harvest.sh` — a syntax error strands the Mac (see above).
- `scripts/setup_mac.sh` and the launchd plists — can unschedule or repoint the
  live job search.
- `meester/apply/` — sends real applications.
- `meester/inbox.py`, `meester/google_api.py`, `meester/outreach.py` — touch her
  personal mailbox.

Explain what could go wrong and how to undo it *before* making the change, not
after.

## How a change reaches her laptop

Push to `master`, and production picks it up one of three ways: the "Update
available — install" button in the app header, `bash ~/Meester/scripts/run_harvest.sh`,
or the next hourly run. Confirm with `tail -20 ~/Meester/logs/harvest.log` —
look for `updated <old> -> <new>` and `harvest starting (code <new>)`.

To undo: `git revert <sha> && git push`, then update production the same way.
This works even while `PAUSED` exists.

## Orientation

`python -m meester <cmd>` is the only entry point (`meester/__main__.py`):
`harvest`, `serve`, `apply-run`, `doctor`, `google-auth`, `inbox`, `outreach`,
`sheet-sync`, `verify-companies`, `report`, `show`.

- `meester/harvest/` — greenhouse, lever, ashby board readers
- `meester/score/` — `gates.py` deterministic ranking, `judge.py` the LLM pass
- `meester/report.py` — every HTML screen (the biggest file)
- `meester/server.py` — the localhost app; token auth, Host and Origin guards
- `meester/apply/` — queue, answers doctrine, Playwright adapters
- `meester/profile.py`, `extract.py` — preferences, CV, the facts ledger
- `tests/` — all offline; the network is stubbed

`README.md` has the architecture and a "Things that bit us, kept as tests"
section worth reading before touching harvesting or remote classification.
`docs/MAINTAINING.md` is her runbook. `docs/GUIDE.md` is her user manual —
keep it in plain language, no jargon.

The dev server runs on **port 8766**. Port 8765 belongs to the production UI
service and binding it will fail.
