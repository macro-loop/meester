# The handover session

A one-time checklist for moving maintenance of Meester from William to her. Work
through it in order — later steps assume earlier ones.

**Who does what** is marked on every step: **[W]** William, **[H]** her, **[both]**
at the same keyboard. Everything from Part 1 onward happens on her Mac.

Budget: ~20 minutes of prep, ~45 minutes of setup, ~90 minutes of rehearsal. The
rehearsal is the part that decides whether this worked. Don't skip it, and don't
compress it into the same sitting if either of you is tired.

Once this is done, the day-to-day manual is **`docs/MAINTAINING.md`**.

---

## Part 0 — Before the session

### 0.1 [W] Give her push access

```
gh api -X PUT repos/macro-loop/meester/collaborators/HER_GITHUB_USERNAME -f permission=push
```

She gets an email invite and has to accept it. Do this a day early, so a stalled
invite doesn't eat the session.

Confirm it took. Check the **invitations** endpoint, not the collaborators one —
`collaborators` lists only people who have already accepted, so straight after
inviting it shows William alone, which looks exactly like a failure:

```
gh api repos/macro-loop/meester/invitations --jq '.[] | "\(.invitee.login)  \(.permissions)"'
```

Once she has accepted, the invitation disappears from that list and she appears
here instead:

```
gh api repos/macro-loop/meester/collaborators --jq '.[].login'
```

### 0.2 [W] Confirm master is current

```
git status -sb
```

Expect `## master...origin/master` with no "ahead" or "behind". Anything unpushed
exists only on your machine — push it now.

### 0.3 [H] Check the live system is healthy before anything is touched

The most important pre-flight check, because a problem found here is pre-existing
rather than something the handover caused.

```
git -C ~/Meester status --porcelain
```

**Expect no output at all.**

If it prints anything, files in the live folder have been hand-edited — which
means auto-updates have been silently failing, possibly for a long time. Don't
discard the changes. Run `git -C ~/Meester diff`, screenshot it, and sort it out
before continuing. The most likely culprit is an old copy of `docs/CLAY_SETUP.md`,
which used to tell you to edit the tracked `config/settings.yaml`.

Then confirm it is actually running:

```
tail -20 ~/Meester/logs/harvest.log
```

You want a recent `harvest ok`.

---

## Part 1 — Setup on her Mac (~45 min, [both])

### 1.1 Back up `profile/` — do this first

Nothing backs it up today, and it holds the CV, the verified work history, the
letters, the answers, the Anthropic key and the Google token. It exists in exactly
one place.

```
mkdir -p ~/Meester-backup && ditto -c -k --keepParent ~/Meester/profile ~/Meester-backup/profile-$(date +%F).zip && ls -lh ~/Meester-backup
```

Expect a zip of a few hundred KB to a few MB. Keep it on the Mac — it contains the
key and the token, so not in a shared Drive.

Check Time Machine is switched on while you're here.

### 1.2 GitHub access

```
brew install gh
```

```
gh auth login
```

Choose **GitHub.com → HTTPS → authenticate in browser**. Then:

```
gh auth setup-git
```

```
git config --global user.name "Her Name" && git config --global user.email "her@email.example"
```

`gh auth setup-git` puts the credentials in the macOS Keychain, so she never
handles a token by hand. Confirm with `gh auth status`.

No Homebrew? Get the `.pkg` from https://cli.github.com instead.

### 1.3 Create the workbench

```
git clone https://github.com/macro-loop/meester.git ~/meester-dev
```

```
cd ~/meester-dev && ./scripts/setup_dev.sh
```

It builds a venv, installs the dependencies plus pytest, turns on the pre-push
checks, and runs the whole test suite once to prove the setup works.

**Expect it to end with a green test run and a `Ready.` block.** If the tests do
not pass in a fresh clone, stop — that is a real bug and has nothing to do with
her.

It deliberately installs no scheduled job, no browser download and no Desktop
shortcut. This folder never runs her job search.

### 1.4 Make production pull-only

So a stray commit in the live folder fails loudly instead of shipping.

```
git -C ~/Meester remote set-url --push origin no-pushing-from-production
```

Prove both halves — the first must fail, the second must work:

```
git -C ~/Meester push
```

```
git -C ~/Meester pull --ff-only
```

### 1.5 Pin the dependency versions

Five open-ended version ranges on a laptop that reinstalls unattended is the
sharpest remaining hazard: a future release of any of them breaks the job search,
and the only symptom is silence.

Read the versions actually working on her machine right now:

```
~/Meester/.venv/bin/python -m pip freeze | grep -iE '^(httpx|PyYAML|pypdf|playwright|pymupdf)=='
```

In `~/meester-dev/requirements.txt`, replace the five `>=` lines with those exact
`==` lines, keeping the comment at the top. Then ship it:

```
cd ~/meester-dev && git add requirements.txt && git commit -m "Pin dependency versions to what her Mac is running" && git push
```

**Watch for the reinstall.** After production next updates, the log shows
`requirements changed - installing`. That line is expected here and almost nowhere
else — seeing it once, deliberately, is worth more than reading about it.

### 1.6 Install Claude Code

```
npm install -g @anthropic-ai/claude-code
```

Needs Node 18+. If Node isn't installed or npm errors, use the installer linked
from https://claude.com/claude-code — there is also a desktop app.

```
cd ~/meester-dev && claude
```

Run `/login` and sign in with **her own** Claude subscription.

### 1.7 Prove Claude has the briefing

Still inside `claude`, ask:

> which folder am I in, and what are the rules for this project?

It should say this is the dev folder, that `~/Meester` is production and must not
be edited, and that the repo is public so nothing from `profile/` may ever be
committed. If it doesn't, it isn't reading `CLAUDE.md` — check she is actually in
`~/meester-dev`.

Then type `/` and confirm the commands are there: `/ship`, `/checkup`,
`/rollback`, `/preview`, `/add-company`, `/pause`, `/unpause`, `/sync`, `/backup`.

---

## Part 2 — The rehearsal (~90 min)

> ### [W] The rule for this part: William says nothing.
>
> Not "nothing unless she's stuck" — nothing. If she gets stuck, that is a
> documentation bug. Write down where, let her work it out with Claude, and fix
> the doc afterwards. Every question answered out loud here is a question she has
> to ask again in three months when you aren't there.
>
> Bring something to read.

Six exercises. Each proves a different path, and none can reach an employer.

### A — Ship a real change

In `~/meester-dev`, run `/add-company` and add a company she'd genuinely like to
watch.

Get it onto production — the **Update available — install** button at
`http://127.0.0.1:8765` is fastest — then:

```
tail -30 ~/Meester/logs/harvest.log
```

**Pass:** all three lines present.

- `updated <old> -> <new>`
- `re-verifying board tokens (companies.yaml changed)`
- `harvest starting (code <new>)`, with the same code as `<new>`

That third line is the real proof: it names the version that actually ran.

### B — Ship a change she can see

Ask Claude to change some visible wording on the jobs page — a heading, a button
label. `/preview` first if she wants to see it before shipping.

**Pass:** `app screens restarted on code <sha>` in the log, and the new wording
visible at `http://127.0.0.1:8765`.

This proves the restart-on-update path, which has genuinely failed before in this
project: the screens once kept serving old code after an update, and the only
symptom was buttons quietly answering "not found".

### C — Get blocked on purpose

Ask Claude to introduce a syntax error into `scripts/run_harvest.sh`, then try to
push it.

**Pass:** the push is refused — `has a syntax error. This would strand her Mac
with no way to self-update.`

Undo it:

```
git checkout -- scripts/run_harvest.sh
```

The point of this one is emotional, not technical. The first time a push is
blocked should not be a day when something actually matters.

### D — Break it, then roll it back

**The most important exercise here.**

Ship something obviously wrong but harmless — rename the page heading to `BROKEN`.
Watch it reach production. Then run `/rollback` and watch it come back.

**Pass:** she did the whole loop — noticed, undid, confirmed — without help.

This is the one that means she never *needs* William. Everything else is
convenience.

### E — Meet the privacy guard

Copy her real CV into the dev folder and try to force it into a commit:

```
cp ~/Meester/profile/resume.pdf ~/meester-dev/ && cd ~/meester-dev && git add -f resume.pdf && git commit -m "test" && git push
```

**Pass:** `push blocked: these look like personal files and this repo is PUBLIC`.

Clean up properly — the commit still exists locally:

```
git reset --hard HEAD~1 && rm -f resume.pdf && git status --porcelain
```

That last command should print nothing. The repo is public and a push cannot be
undone, so this is the one guard worth meeting deliberately, once, rather than by
accident.

### F — The switches

```
touch ~/Meester/PAUSED && bash ~/Meester/scripts/run_harvest.sh
```

Expect `PAUSED file present - skipping run`. Then:

```
rm ~/Meester/PAUSED
```

Run `/checkup` in the dev folder and read the result together. Finally, type out
the "nothing is running" recovery commands once, while nothing is wrong:

```
git -C ~/Meester status --porcelain
```

```
git -C ~/Meester pull --ff-only
```

**The thing to remember from this exercise:** while `PAUSED` exists, updates don't
arrive either. A fix pushed during a pause will not install by itself — the
**Update available** button still works, or delete `PAUSED` first.

### The exam

After A–F, she writes the "Making a change" and "When something breaks" sections
of `docs/MAINTAINING.md` **in her own words**, and ships them with `/ship`.

That is both the real test of whether this landed and a genuinely useful commit.
If she can't write a step, that step isn't learned yet — go back to it.

---

## Part 3 — The soak (2 weeks)

**[W]** Change nothing. Answer nothing that isn't an emergency. Resist the urge to
"just quickly fix" anything.

**[H]** Make at least one real change a week. Adding companies counts, and is the
highest-value maintenance in the system anyway.

At the end, read the log together:

```
grep updated ~/Meester/logs/harvest.log
```

Every `updated a -> b` line is a change she shipped on her own. Any question that
came up which the docs didn't answer is the backlog.

---

## What still needs William, permanently

Deliberately short, and by choice rather than oversight.

| Thing | Why |
|---|---|
| The **Anthropic key** | On his account, billed there. Ask him to rotate it or change the spend limit. |
| **Clay** (hiring-manager outreach) | Runs in his Clay workspace. See `docs/CLAY_SETUP.md`. |
| The **Google Cloud project** | He set it up. Re-authorising is hers, though: `python -m meester google-auth`. |

Everything else — the code, the companies, the scoring, the screens, the letters,
the settings — is hers.

---

## If setup goes wrong

| Symptom | Cause | Fix |
|---|---|---|
| `setup_dev.sh` says "this folder is the one the scheduled job runs from" | Run inside `~/Meester` | `cd ~/meester-dev` and run it there |
| `setup_mac.sh` says "the scheduled job currently runs from another folder" | Run from the dev clone | Correct behaviour — don't override it. It is stopping you moving her live job search. |
| `push blocked: ... has no pytest` | The venv predates `requirements-dev.txt` | Run `./scripts/setup_dev.sh` again |
| `Permission denied` or `403` on push | Invite not accepted, or `gh auth setup-git` not run | `gh auth status`, then re-check the invite |
| `xcrun: error: invalid active developer path` | Xcode command line tools missing | `xcode-select --install` |
| Update button says "ask Claude in the dev folder" | Production has local changes | `git -C ~/Meester status --porcelain`, then §0.3 |
| Tests fail in a *fresh* clone | Not her fault | Stop. That is a real bug — check CI on GitHub. |
