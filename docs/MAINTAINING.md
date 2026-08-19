# Looking after Meester yourself

This is the *maintainer's* manual — how to change the tool. `GUIDE.md` is the
other half: how to use it day to day. You don't need this one to run your job
search. You need it when you want the tool to do something different.

You do not need to be able to write code. You describe the change, Claude makes
it, the safety checks run, and you push. The checks are real: several of them
exist specifically to stop a bad change from reaching your laptop.

---

## 1. Two folders, and the one rule

| Folder | What it is |
|---|---|
| `~/Meester` | **The real thing.** It runs by itself every hour and sends real applications. |
| `~/meester-dev` | **Your workbench.** Nothing here runs on a schedule. |

**The one rule: never edit `~/Meester`.**

Not because it's fragile, but because of a specific, silent failure. `~/Meester`
updates itself by pulling from GitHub, and git refuses to pull into a folder with
unsaved edits in it. So the moment you change a file there, your Mac quietly stops
receiving updates — including any fix you just made. Nothing warns you. The job
search appears to run normally for weeks on stale code.

`~/meester-dev` exists so that never happens. The setup scripts refuse to run in
the wrong folder, and pushing from `~/Meester` is disabled outright.

---

## 2. Making a change

```bash
cd ~/meester-dev
git pull
claude
```

Then say what you want in plain language — "the jobs page should show the salary
range next to the title", "stop showing me contract roles", "add these five
companies". Claude has a briefing (`CLAUDE.md` in this folder) covering the rules
of this project, so you don't have to remember them.

When it looks right, ship it:

```
/ship
```

That runs the checks, shows you the change, and pushes it after you confirm.

**To see a screen change before shipping**, run `/preview`. It copies your real
jobs and profile into the workbench and opens the app at
`http://127.0.0.1:8766` — port 8766, not 8765, so it can't collide with the real
one.

### What the checks actually stop

- **A broken shell script.** These are the dangerous ones: they'd leave your Mac
  unable to update itself, so it can't even receive the fix. Blocked outright.
- **Personal files.** This repo is public. Your CV, anything from `profile/`, any
  PDF — blocked. A push cannot be undone, so this one is worth trusting.
- **Failing tests.** 160-odd of them, all offline, a few seconds to run.

If a push is blocked, nothing has gone wrong. Read what it says, or paste it to
Claude.

---

## 3. Getting the change onto the real thing

Three ways, fastest first:

1. **Open the app** at `http://127.0.0.1:8765`. An **"Update available —
   install"** button appears in the header. One click: it pulls, restarts, and
   starts a fresh run.
2. **Terminal:** `bash ~/Meester/scripts/run_harvest.sh`
3. **Wait.** It picks it up within the hour, or when the laptop next wakes.

**Check it landed:**

```bash
tail -20 ~/Meester/logs/harvest.log
```

You want two lines: `updated abc1234 -> def5678`, and `harvest starting (code
def5678)` with the same code. That second line is the proof — it's the version
that actually ran.

---

## 4. When something breaks

Work down this list. Stop when it's fixed.

### Tier 0 — Make it stop

Create an empty file called **`PAUSED`** (no extension) in the `Meester` folder.
Finder is fine; no terminal needed. Everything halts: no harvests, no
applications, no mail. Delete the file to resume. Or run `/unpause`.

> **Important:** while `PAUSED` exists, updates don't arrive either. If you pause
> it and then push a fix, the fix will not install on its own. Use the **Update
> available** button — that still works while paused — or delete `PAUSED` once
> you're ready (`/unpause`).

### Tier 1 — Undo the change

Nearly everything lands here.

```bash
cd ~/meester-dev
/rollback
```

It shows recent changes, undoes the one you pick, runs the tests and pushes. Then
click **Update available — install** on the real app.

You do not need to understand what broke to undo it.

### Tier 2 — Nothing is running at all

Symptoms: nothing new in `~/Meester/logs/harvest.log` for hours, and no Update
button. This is the rare case — a broken shell script — where the machine can't
fix itself, because it dies before it gets as far as downloading the fix.

Three commands, in order, stopping when it works:

```bash
git -C ~/Meester status --porcelain
git -C ~/Meester pull --ff-only
bash ~/Meester/scripts/run_harvest.sh
```

If the first command printed anything at all, something edited files in the real
folder. Don't delete it — show it to Claude in `~/meester-dev` first. It's
evidence for how things got this way.

### Tier 3 — Start over

The laptop died, or nothing above worked.

```bash
cp -R ~/Meester/profile ~/profile-rescue          # skip if the folder is gone
rm -rf ~/Meester
git clone https://github.com/macro-loop/meester.git ~/Meester
cp -R ~/profile-rescue/. ~/Meester/profile/       # or from your backup
cd ~/Meester && ./scripts/setup_mac.sh
```

Then re-paste your Anthropic key on the Profile screen and, if mail stopped
working, run `~/Meester/.venv/bin/python -m meester google-auth`.

### Anything else

```bash
cd ~/meester-dev
/checkup
```

That runs the built-in diagnostic and reads the recent log, in plain language.

---

## 5. Back up `profile/`

**`~/Meester/profile` is the one thing git will never save for you.** It's
deliberately excluded, because the repo is public and that folder holds your CV,
your verified work history, your letters, your answers, your API key and your
Google login.

It exists in exactly one place. If the laptop dies, it's gone, and rebuilding the
facts ledger by hand is genuinely tedious.

Make sure Time Machine is on. And roughly monthly:

```
/backup
```

which writes a dated zip to `~/Meester-backup/`. Keep those local — that zip
contains your key and your Google token, so don't put it in a shared Drive.

---

## 6. Things worth knowing

**Settings.** Two files. `config/settings.yaml` is shared and lives in GitHub —
change it in `~/meester-dev` and ship it like any other change. `config/settings.local.yaml`
is only on your Mac and never leaves it; that's where anything machine-specific
goes. Never edit either one inside `~/Meester`.

**Adding companies** is the change you'll make most often, and there's a shortcut
for it: `/add-company` in `~/meester-dev`. Your Mac notices the list changed and
re-checks every board automatically on the next run.

**Dependency versions** in `requirements.txt` are pinned deliberately. When you
change one, your laptop reinstalls on the next run. Change one at a time, and not
the day before you travel.

**`--no-verify`** skips the pre-push checks. It exists, and it's occasionally the
right call for a typo in a document. It is never the right call for anything
under `scripts/` or `meester/`.

---

## 7. What still needs William

Short, and deliberately so:

- **The Anthropic key** (the AI fit percentages) is on his account and billed
  there. If it stops working or you want the spending limit changed, ask him.
- **Clay** (the hiring-manager outreach) runs in his Clay workspace. See
  `docs/CLAY_SETUP.md`.
- **The Google Cloud project** behind the Gmail connection is one he set up. You
  won't normally touch it, but re-authorising is yours: `python -m meester
  google-auth`.

Everything else — the code, the companies, the scoring, the screens, the letters,
the settings — is yours to change.
