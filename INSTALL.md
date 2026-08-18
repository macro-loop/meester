# Installation plan

End-to-end: your machine → GitHub → her MacBook → proving the update loop works.

**Budget ~30 minutes**, of which ~10 are at her Mac. Do it in one sitting; the
last phase needs both machines reachable.

| Phase | Where | Time |
|---|---|---|
| 1. Prepare and publish the repo | Your machine | 10 min |
| 2. Choose how her Mac gets the code | Decision | 2 min |
| 3. Install on her Mac | Her machine | 10 min |
| 4. Prove updates actually reach her | Both | 5 min |
| 5. Hand over | Her machine | 2 min |

---

## Before you start

> **Which shell.** Phase 1 runs on Windows in **Command Prompt** (`cmd.exe`), where
> single quotes are not quotes — they are literal characters, and any command
> wrapping an argument in `'...'` will fail. Every Phase 1 command below is
> written to work there unmodified. Phase 3 onward is bash on her Mac, where the
> usual rules apply.

**On your machine**, confirm the GitHub CLI is installed and logged in:

```bash
gh auth status
```

If that errors, run `gh auth login` (choose HTTPS, authenticate in the browser).
If `gh` isn't installed at all: https://cli.github.com

**On her Mac**, nothing to pre-install. Setup accepts the Python that macOS
already ships, and proves it works rather than assuming. Homebrew is only needed
in the unlikely case that check fails.

---

## Phase 1 — Prepare and publish the repo

Everything here is on **your** machine, in the project folder.

### 1.1 Turn on the safety gate

```bash
git config core.hooksPath scripts/githooks
```

This blocks any push where the shell scripts don't parse or the tests fail.
There is no CI — this hook is the only thing between a typo and her laptop.

### 1.2 Confirm the working tree is clean and tests pass

```bash
git status --short && python -m pytest tests/ -q
```

### 1.3 Create the GitHub repo and push

The branch is `master`. Nothing depends on the name, but note it — you'll want
it when checking things on GitHub.

```bash
gh repo create meester --private --source=. --remote=origin --push
```

### 1.4 Confirm it landed

```bash
gh repo view --web
```

You should see `README.md` rendered, and **no `data/` folder**. If you see a
`data/` folder, stop — her job-search data is being published. It shouldn't
happen (`.gitignore` covers it) but it is worth the two seconds to look.

### 1.5 Grab the clone URLs

```
gh repo view --json sshUrl,url
```

Keep both. Which one you use depends on the next decision.

For `macro-loop/meester` they are:

- HTTPS — `https://github.com/macro-loop/meester.git`
- SSH — `git@github.com:macro-loop/meester.git`

---

## Phase 2 — Choose how her Mac gets the code

> **Already decided: the repo is public** (`macro-loop/meester`, verified
> anonymously readable). Her Mac needs no GitHub account, no login and no keys,
> and auto-update works permanently. **Skip to Phase 3.2** — the deploy-key step
> in 3.1 does not apply.

Kept for reference, in case you ever make it private again.

### Option A — make the repo public *(simplest, and fine)*

```bash
gh repo edit --visibility public --accept-visibility-change-consequences
```

There is nothing sensitive in the repo: no API keys, no resume, no personal
data. `data/` and `logs/` are gitignored, so only code and a list of company
names are ever published, and nothing in it identifies her.

Her Mac then needs **no GitHub account, no login, no keys**, and auto-update
works forever. Use the **HTTPS** URL in Phase 3.

### Option B — stay private, read-only deploy key *(recommended if private)*

Scoped to this one repo, read-only, and it does **not** put your GitHub account
on her machine. Three commands on her Mac plus one paste in a browser — steps are
inline in Phase 3. Use the **SSH** URL.

### Option C — stay private, log in as you

Fastest to type, but it stores your credentials in her keychain and gives her
machine access to every repo you own. Only pick this if that genuinely doesn't
bother you. On her Mac you'd run `gh auth login` and use the HTTPS URL.

---

## Phase 3 — Install on her Mac

Open **Terminal** (Cmd+Space → "terminal").

### 3.1 Only if you chose Option B (deploy key)

```bash
ssh-keygen -t ed25519 -f ~/.ssh/meester_deploy -N "" -C "meester-macbook"
```

```bash
cat ~/.ssh/meester_deploy.pub
```

Copy that whole line. In a browser: your repo → **Settings** → **Deploy keys** →
**Add deploy key**. Paste it, leave **"Allow write access" unchecked**, save.

```bash
printf 'Host github.com\n  IdentityFile ~/.ssh/meester_deploy\n  IdentitiesOnly yes\n' >> ~/.ssh/config
```

### 3.2 Clone

She does not need to create a folder first — `git clone` creates it. Nor does she
need to `cd` anywhere: `~/Meester` is an absolute path, so it lands in the right
place no matter where Terminal opens.

```bash
git clone https://github.com/macro-loop/meester.git ~/Meester
```

> **Clone to `~/Meester`, not into Documents or Desktop.** Most Macs have
> iCloud's "Desktop & Documents Folders" sync enabled. If the repo lives in
> either, iCloud tries to sync `.venv/` — thousands of files — and can evict them
> under "Optimize Mac Storage", silently breaking the virtualenv. It would also
> copy her job-search data to iCloud, which is what the gitignore rules exist to
> prevent. The home folder root is not synced.

Nothing is hardcoded to that path — every script derives its location from its
own file, so any folder works. But every command in this document says
`~/Meester`, and **moving the folder after setup breaks the scheduled job**,
because launchd stores an absolute path. If she moves it, re-run
`./scripts/setup_mac.sh`.

If you kept the repo private and used a deploy key (Option B), use the SSH URL
instead:

```bash
git clone git@github.com:macro-loop/meester.git ~/Meester
```

> The first `git` command may pop a dialog offering to install the Xcode Command
> Line Tools. Accept it, wait, then run the clone again. This is normal, not an
> error, and it is the single most likely thing to make you think something broke.

### 3.3 Run setup

```bash
cd ~/Meester && ./scripts/setup_mac.sh
```

It finds a Python, builds a virtualenv, installs two dependencies, **proves the
interpreter can actually run Meester**, verifies the job board tokens, and
registers the scheduled job. Two to three minutes, mostly board verification.

If it stops at the interpreter check, install a newer Python and re-run —
the script is safe to repeat:

```bash
brew install python@3.12
```

### 3.4 Verify — don't skip this

```bash
launchctl list | grep meester
```

Expect a line ending `com.meester.harvest`. The middle column is the last exit
code; `0` is good.

```bash
tail -20 ~/Meester/logs/harvest.log
```

Expect `harvest starting (code abc1234)` followed by `harvest ok`.

```bash
~/Meester/.venv/bin/python -m meester show --limit 20
```

Expect real remote job postings. If you see those, it works.

---

## Phase 4 — Prove updates actually reach her

The most valuable five minutes here, and the easiest to skip. If auto-update is
silently broken you won't find out for weeks — and you already have one instance
of exactly that failure mode in this repo's history.

**4.1** Make a one-line change to `config/companies.yaml` and get it onto
`master`. Either route works — pick whichever machine you are sitting at.

*From a browser* (no laptop needed — this is the point of doing it this way):

```
https://github.com/macro-loop/meester/edit/master/config/companies.yaml
```

Add one line under `greenhouse:` and commit straight to `master`.

*From your own machine*, if it's to hand — simpler:

```bash
git add -A && git commit -m "Add airbnb to watchlist" && git push
```

Either way, the line to add is:

```yaml
  - airbnb
```

`airbnb` is deliberate: it is not already in the seed list, and its board is live
with ~190 roles, so the test doubles as a real addition. Do **not** use a token
already present — a duplicate still changes the file hash and would trigger the
re-verify, but you'd learn nothing about whether it actually works.

**4.2** Note the new commit's short SHA on GitHub.

**4.3** Back in her Terminal, force a run instead of waiting the hour:

```bash
bash ~/Meester/scripts/run_harvest.sh
```

**4.4** Check what happened:

```bash
tail -30 ~/Meester/logs/harvest.log
```

You are looking for three things:

- `updated <old> -> <new>` — the pull worked
- `re-verifying board tokens (companies.yaml changed)` — watchlist changes propagate
- `harvest starting (code <new-sha>)` — matching the SHA from 4.2

If all three appear, the update loop is proven and you should not need to touch
her Mac again.

---

## Phase 5 — Hand over

**How she uses it:** double-click **"Remote jobs"** on her Desktop. It opens in
her browser, refreshes on its own, and every row links straight to the real
application page. Setup puts it there.

**Then sit with her for ~15 minutes and fill in the three screens** linked at
the top of that page — no files, no TextEdit, no terminal:

- **Your profile** — titles she'd accept, salary floor, hard exclusions, dream
  companies. Honest answers, not aspirational ones: an inflated salary floor
  produces an empty list.
- **Your CV** — she uploads the PDF she actually sends out, clicks *Read my CV
  into the editor*, and corrects what the read-in got wrong. The corrected
  record is the **facts ledger** — what every later stage treats as the only
  truth about her history. The read-in is rough on purpose; her correction pass
  is the point.
- **Cover letters** — two starters to rewrite in her own voice. Placeholders
  like `{company}` fill per job later; the preview shows each letter against a
  real posting from her own list.

**What she gets immediately:** with titles in her profile, the jobs page opens
on a **"For you" tab** — matches ranked with plain-language reasons ("Title
matches 'Product Designer' · Pay meets your floor"), dream companies starred,
agency spam dropped. Editing preferences re-ranks on the next page load. With a
blank profile the tab hides entirely rather than showing an empty list.

Be straight about what it is: ranked matching, not applying. Nothing is
submitted anywhere by anything in this repo.

Her data — profile, CV, ledger, letters — stays on her Mac: `profile/` is
gitignored and the pre-push hook refuses anything that looks personal. Both
layers are tested. The repo being public changes nothing about her data.

**To stop it:** create an empty file named `PAUSED` in the `Meester` folder in
her home directory — Finder is fine, no Terminal needed. Deleting it resumes.
**Companies come and go from the Companies screen**; updates install from the
blue button that appears when you push one.

---

## Phone access with Tailscale

Optional, ~15 minutes, and what makes the approve queue usable from anywhere.
Nothing becomes public: Tailscale is a private WireGuard network between her
own devices only.

1. On her Mac: install Tailscale (App Store or `brew install --cask tailscale`),
   sign in (an Apple/Google login works).
2. On her phone: install the Tailscale app, sign in to the **same** account.
3. On her Mac, in Terminal, once:

```bash
tailscale serve --bg http://127.0.0.1:8765
```

4. On the phone, open the address `tailscale serve` printed — it looks like
   `https://her-mac.tailXXXX.ts.net`. Add it to the home screen.

The server itself stays bound to 127.0.0.1; Tailscale proxies it inside the
tailnet with proper HTTPS. The app accepts `.ts.net` hostnames by design (that
namespace is Tailscale-controlled, so nobody else can point one at her machine);
everything else still gets a 403. **Do not use `tailscale funnel`** — that
variant makes the page public internet-facing, which this app's auth model is
deliberately not built for.

Phone pages work while the Mac is awake — same charger-and-lid advice as the
harvest.

## Updating an install that already exists

If her Mac was set up before some of this landed, one command on her Mac brings
it fully current:

```bash
cd ~/Meester && git pull && bash scripts/run_harvest.sh
```

Pulling *first*, in the shell rather than inside the script, matters: bash keeps
reading the copy of `run_harvest.sh` it opened at startup, so a self-update
inside the script would not apply to the run that performed it. The script now
detects that case and re-execs itself, but pulling first sidesteps it entirely.

Expect afterwards: `~/Meester/data/jobs.html` exists, and a **Remote jobs** file
appears on her Desktop.

Nothing needs re-running if she hasn't been set up yet — a fresh clone gets
everything.

## Ongoing: pushing updates

```bash
git add -A && git commit -m "what changed" && git push
```

Her Mac pulls before every harvest, so changes land within the hour while the
laptop is awake, otherwise on next wake.

**Or she installs it herself:** when her copy is behind GitHub, an
"Update available — install" button appears in the header of her jobs page and
the Companies screen. One click pulls, restarts the app on the new version, and
kicks off a fresh harvest. So "there's an update for you" over text is now a
complete handoff — no terminal on her side. If her copy can't fast-forward
(hand-edited files, diverged history) the button reports "tell William" instead
of attempting anything clever.

**Adding companies** — edit `config/companies.yaml`, commit, push. Her machine
notices the file changed and re-verifies automatically.

**Checking her version remotely** — ask for the last lines of
`~/Meester/logs/harvest.log` and compare the logged SHA to `git log --oneline -1`.

**If you push something broken** — `git revert HEAD && git push`. Her next run
pulls the fix before executing, so Python breakage self-heals. The one exception
is a syntax error in `scripts/*.sh`: bash dies before reaching the pull and the
machine is stranded. That is precisely what the pre-push hook guards, which is
why you enable it in Phase 1.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `xcrun: error: invalid active developer path` | Xcode CLT missing | Accept the install dialog, or `xcode-select --install` |
| `Repository not found` | Private repo, auth incomplete | Redo Phase 2 |
| `Permission denied (publickey)` | Deploy key not registered or SSH config missing | Recheck 3.1; confirm the key is on the repo, not your account |
| `permission denied: ./scripts/setup_mac.sh` | Exec bit lost | `bash ~/Meester/scripts/setup_mac.sh` |
| `bad interpreter: /bin/bash^M` | CRLF line endings | Shouldn't happen — `.gitattributes` forces LF. If it does: `sed -i '' 's/\r$//' ~/Meester/scripts/*.sh` |
| Profile/CV/Letters buttons answer `{"error": "not found"}` | The app service is still running pre-update code — a pull changes disk, not a running process | Fixed automatically since `run_harvest.sh` restarts the service on code drift; by hand: `launchctl kickstart -k gui/$(id -u)/com.meester.ui` |
| No update button | Either nothing is pending (it only appears when her copy is behind GitHub) or the app service predates the feature | Push something, or the kickstart above |
| Job is listed but the log is empty | It ran while asleep | Open the lid, wait a minute; launchd fires a catch-up run on wake |
| Nothing runs at all | Job not registered | Re-run `./scripts/setup_mac.sh`, it is safe to repeat |
| Remove it entirely | | `~/Meester/scripts/uninstall_mac.sh` |
