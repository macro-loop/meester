# Installing on her MacBook

Plan for ~10 minutes sitting at her machine. Do it yourself rather than talking
her through it — the only genuinely fiddly part is GitHub authentication, and
that is much faster done than explained.

---

## Step 0 — decide how her Mac gets the code

A private repo requires credentials on her machine. Pick one:

### Option A — make the repo public (simplest)

There is nothing sensitive in it. No API keys, no resume, no personal data —
`data/` and `logs/` are gitignored, so only code and a list of company names
ever reach GitHub. Nothing in the repo identifies her.

```bash
gh repo edit --visibility public
```

Her Mac then needs **no GitHub account, no login, no keys**, and auto-update
keeps working forever. If you have no specific reason to keep it private, take
this option and skip to Step 1.

### Option B — stay private, use a read-only deploy key (recommended if private)

Scoped to this one repo, read-only, and does **not** put your GitHub account
credentials on her machine. Run these **on her Mac**:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/meester_deploy -N "" -C "meester-macbook"
```

```bash
cat ~/.ssh/meester_deploy.pub
```

Copy that output, then in your browser open the repo → **Settings** → **Deploy
keys** → **Add deploy key**, paste it, leave "Allow write access" **unchecked**,
save.

Then tell SSH to use it, still on her Mac:

```bash
printf 'Host github.com\n  IdentityFile ~/.ssh/meester_deploy\n  IdentitiesOnly yes\n' >> ~/.ssh/config
```

Use the **SSH** clone URL in Step 1 (`git@github.com:...`), not the HTTPS one.

### Option C — stay private, log in as you

Fastest private option, but it stores *your* GitHub credentials in her keychain,
granting her machine access to all your repos. Only do this if you are fine with
that.

```bash
gh auth login
```

---

## Step 1 — clone it

On her Mac, open **Terminal** (Cmd+Space, type "terminal").

Public repo (Option A):

```bash
git clone https://github.com/YOUR-USERNAME/meester.git ~/Meester
```

Private repo with a deploy key (Option B):

```bash
git clone git@github.com:YOUR-USERNAME/meester.git ~/Meester
```

> The very first `git` command may pop up a dialog offering to install the Xcode
> Command Line Tools. Accept it, wait for it to finish, then run the clone again.
> This is normal macOS behaviour and not an error.

## Step 2 — run setup

```bash
cd ~/Meester && ./scripts/setup_mac.sh
```

It will find a Python, build a virtualenv, install two dependencies, verify the
job board tokens, and register the scheduled job. Expect it to take a couple of
minutes, mostly on the board verification.

If it stops with **"No Python 3.10 or newer found"**, install one and re-run:

```bash
brew install python@3.12
```

And if `brew` itself is missing, install Homebrew first from https://brew.sh,
then run the line above.

## Step 3 — confirm it actually works before you walk away

This is the step worth not skipping.

```bash
launchctl list | grep meester
```

You want a line ending in `com.meester.harvest`. The middle column is the last
exit code — `0` is good.

```bash
tail -20 ~/Meester/logs/harvest.log
```

You want to see `harvest starting` and then `harvest ok`.

```bash
~/Meester/.venv/bin/python -m meester show --limit 20
```

You want a list of real remote job postings. If you see those, it is working.

## Step 4 — show her the two things she needs to know

Everything else is your problem, not hers. She only needs:

**To see what it found:**

```bash
open ~/Meester/data
```

(For now the data is a `.jsonl` file — readable but ugly. The Airtable view
arrives with the scoring stage, and that is what she will actually use.)

**To stop it:** create an empty file called `PAUSED` in the `Meester` folder in
her home directory — she can do this in Finder, no Terminal needed. Deleting the
file starts it again.

---

## Afterwards

You push changes from your machine; her copy runs `git pull --ff-only` before
each harvest, so fixes arrive on their own. You should not need to touch her Mac
again.

To check on it remotely, ask her to send you the last few lines of
`~/Meester/logs/harvest.log`.

## If something breaks

| Symptom | Cause | Fix |
|---|---|---|
| `bad interpreter: /bin/bash^M` | Windows line endings | Shouldn't happen — `.gitattributes` forces LF. If it does: `sed -i '' 's/\r$//' ~/Meester/scripts/*.sh` |
| `permission denied: ./scripts/setup_mac.sh` | Exec bit lost | `bash ~/Meester/scripts/setup_mac.sh` |
| `Repository not found` | Private repo, auth not set up | Redo Step 0 |
| Job listed but nothing in the log | Ran while asleep | Open the lid and wait a minute; `launchd` fires a catch-up run on wake |
| Nothing runs at all | Job not registered | Re-run `./scripts/setup_mac.sh` — it is safe to repeat |
| Want it gone entirely | | `~/Meester/scripts/uninstall_mac.sh` |
