# Meester

A job-application autopilot that runs on one person's Mac. Full design lives in
the approved plan; `INSTALL.md` is the setup runbook. This README is the
architecture map.

## The pipeline, end to end

1. **Harvest** (`harvest/`) — hourly, pulls remote roles straight from company
   Greenhouse / Lever / Ashby boards, classifies genuine remoteness, dedupes,
   stores idempotently. Runs via launchd; self-updates from git.
2. **Score** (`score/`) — deterministic gates rank every job against her
   preferences and verified CV with plain-language reasons; an optional LLM
   judge (`score/judge.py`, needs an Anthropic key) adds fit % and evidence.
3. **Present** (`report.py`) — an offline HTML report (Desktop alias) plus a
   localhost server (`server.py`, token-auth, Tailscale-reachable) with screens
   for the ranked list, company watchlist, profile, CV/facts-ledger, cover
   letters, and the approve queue.
4. **Apply** (`apply/`) — approved queue items are submitted by Playwright
   adapters from her own machine. The answers doctrine (`apply/answers.py`)
   never guesses a legal question; CAPTCHAs and unknown forms route to her.
   Approve-everything at launch; one config flip enables tiered auto-submit.
5. **Follow up** (`outreach.py`, `inbox.py`, `google_api.py`) — warm outreach to
   hiring managers via Clay, and an inbox loop that classifies replies and
   drafts responses. Nothing sends without her approval.

**Safety invariants, enforced in code, not remembered:** her data never leaves
the Mac (`profile/` + `data/` gitignored, pre-push guard); Gmail reads are hard-
scoped to the `JobSearch` label; legal/EEO answers come only from exact profile
matches; `PAUSED` halts everything; the apply engine screenshots every
submission and honours a daily cap.

Earlier phase-by-phase notes follow; the harvest section documents the
live-data bugs the classifier guards against.

## Setup

```bash
python -m pip install -r requirements.txt
```

## Use

Probe every board token in `config/companies.yaml` and write a pruned list.
Do this first, and again whenever you add companies:

```bash
python -m meester verify-companies --write
```

Fetch, filter, dedupe and store. `--dry-run` writes nothing:

```bash
python -m meester harvest --dry-run
```

```bash
python -m meester harvest
```

```bash
python -m meester show --limit 40
```

## Current numbers

From a live run against 69 verified boards:

```
69 boards ok, 0 failed | 9953 raw -> 2476 remote -> 910 fresh -> 773 unique
```

Re-running immediately adds **0** rows.

## Running it on her Mac

**Step-by-step install instructions: [INSTALL.md](INSTALL.md).** Plan on ten
minutes at her machine; the only fiddly part is GitHub authentication, which is
faster done than explained over the phone.

The short version, once auth is sorted:

```bash
git clone <repo-url> ~/Meester && cd ~/Meester && ./scripts/setup_mac.sh
```

That finds a suitable Python, builds a virtualenv, installs dependencies,
verifies the board tokens, and registers a `launchd` job that runs hourly and
once at every login. Re-running it is safe.

| To do this | Run this |
|---|---|
| Pause everything | `touch ~/Meester/PAUSED` |
| Resume | `rm ~/Meester/PAUSED` |
| See what it found | `~/Meester/.venv/bin/python -m meester show --limit 40` |
| Watch it work | `tail -f ~/Meester/logs/harvest.log` |
| Confirm it's scheduled | `launchctl list \| grep meester` |
| Remove it completely | `~/Meester/scripts/uninstall_mac.sh` |

The pause switch is a file rather than a config flag on purpose: it can be
created or deleted from Finder by someone who has never opened a terminal.

**Sleep is the real constraint.** A closed MacBook Air suspends the timer.
`launchd` fires one catch-up run on wake — which is why it is used instead of
cron, which silently drops missed jobs — so in practice this harvests whenever
the laptop is awake rather than strictly hourly. That erodes some of the
timing edge over aggregators. To narrow the gap: keep it on the charger and turn
on System Settings → Battery → Options → "Wake for network access". If the edge
turns out to matter, moving *only* the harvest stage to a ~$5/mo box fixes it.

**Updates.** See [Pushing updates](#pushing-updates) below.

**Her data never leaves her machine.** `data/` and `logs/` are gitignored, so
postings, rejections, salary expectations and application evidence stay local.
Only code moves through GitHub.

**One upside of running it all on her Mac:** when the apply stage lands, it *has*
to execute there anyway — her browser profile, her session cookies, her
residential IP. Submitting from a datacenter would be the exact device
fingerprint that spam screening looks for. So this choice costs some harvest
freshness and buys the right execution environment for everything downstream.

## Pushing updates

Enable the pre-push hook once, on your machine:

```bash
git config core.hooksPath scripts/githooks
```

Then the loop is just:

```bash
git add -A && git commit -m "what changed" && git push
```

Her Mac runs `git pull --ff-only` before every harvest, so the change lands on
her next run — within the hour if the laptop is awake, otherwise on next wake.
She does nothing.

**There is no CI and no staging.** Whatever reaches `master` executes unattended
on her laptop within the hour. The pre-push hook is the only gate, and it checks
two things:

1. **Every shell script parses.** This matters more than the tests. Broken Python
   self-heals — the next run pulls the fix *before* executing it. A broken
   `run_harvest.sh` does not: bash dies before reaching the `git pull`, so her Mac
   is stranded until someone physically touches it. Treat `scripts/*.sh` as the
   dangerous files.
2. **The tests pass.**

Override with `git push --no-verify` only when you genuinely mean it.

### Adding companies to the watchlist

Edit `config/companies.yaml`, commit, push. Her machine notices the file changed
and re-runs verification automatically before the next harvest.

This needs saying because it was broken at first: harvest reads
`companies.verified.yaml`, which is gitignored and generated locally, so pushing
new companies had no effect at all. `run_harvest.sh` now re-verifies whenever the
tracked seed list changes, and weekly regardless, to catch boards that have died.

### Confirming which version she is running

Every run logs its commit:

```
2026-08-14 09:14:02  harvest starting (code 503a8d2)
```

Ask her for the last few lines of `~/Meester/logs/harvest.log` and compare
against `git log --oneline -1`.

### If you push something broken

Revert and push again — her next run picks up the fix on its own:

```bash
git revert HEAD && git push
```

The only case needing hands-on recovery is a syntax error in a shell script,
which is exactly what the hook exists to prevent.

## Why it is built this way

**Discovery is an API, submission is a browser.** Greenhouse's application-submit
endpoint needs the *employer's* secret key and its docs warn it must never be
exposed client-side; Ashby and Lever are the same. There is no applicant-facing
apply API anywhere. So harvesting is clean structured JSON, and applying — later,
in Stage 6 — has to be Playwright.

**Company boards beat aggregators on timing.** A role appears on the employer's own
board hours to days before an aggregator indexes it. Growing `companies.yaml` is
the highest-leverage maintenance task in the system.

**Board tokens must be verified, never assumed.** Of 121 hand-written seed tokens,
69 resolved. Guessing `company-name` is right about 57% of the time.

## Things that bit us, kept as tests

Each of these was found by auditing live data against ground truth, not by
reading code. All are covered in `tests/`.

- **`isRemote` is not authoritative.** OpenAI publishes `isRemote: true` on 438 of
  734 postings that are simultaneously `workplaceType: "Hybrid"`, located
  "San Francisco", with no remote secondary location. Trusting the boolean
  admitted 438 office jobs as remote from one employer alone. It is now treated
  as corroborating evidence only. See `meester/harvest/ashby.py:_classify`.
- **Ashby hides remote options in `secondaryLocations`.** Ramp lists roles as
  "New York, NY (HQ)" with "Remote (US)" tucked into the secondaries. Reading only
  the primary location silently discards real remote roles.
- **Greenhouse `content` is double HTML-escaped.** The payload literally begins
  `&lt;div class=&quot;`. One `html.unescape` yields HTML, not text. Skipping the
  second pass feeds `&lt;p&gt;` soup to the scorer and quietly degrades every fit
  score. See `meester/textutil.py`.
- **`#` inside a `re.VERBOSE` pattern starts a comment.** An unescaped one turned
  the last alternative of the title-cleaning regex into a bare `\s*`, which matched
  the space in every title — "Backend Engineer" normalised to "backendengineer"
  and unrelated roles began merging. See the note in `meester/models.py`.
- **Do not union geography across separate postings.** One title posted once per
  city on a single board is not one role open in every city. Merging them produced
  a Datadog posting located "Lisbon, Portugal" advertised as open in five other
  countries. Geography is only unioned across *different sources*.
- **`\b` does not follow a trailing period.** `\bu\.s\.\b` never matches
  "U.S. Remote", so a common US phrasing resolved to no country at all.

## Layout

```
config/
  settings.yaml           policy: concurrency, max age, accepted countries
  companies.yaml          seed watchlist (unverified)
  companies.verified.yaml generated by verify-companies
meester/
  models.py               Job model, company/title normalisation
  remote.py               remote classification + country extraction
  textutil.py             HTML -> text
  dedupe.py               cross-source and same-board collapsing
  store.py                idempotent JSONL store
  harvest/                greenhouse.py lever.py ashby.py run.py base.py
tests/                    31 tests, all offline
```

`data/` is gitignored and holds the local store.

## Known limits

- Bare two-letter state codes after a dash ("Remote - CA") stay unscoped on
  purpose: about half the US state codes collide with ISO country codes
  (CA/Canada, IN/India, IL/Israel). An unscoped remote role is accepted anyway
  and gets pinned down at scoring, so a wrong country is the costlier error.
- Only three ATSs are wired. Workday, iCIMS and Taleo are not, by design — the
  paid tool covers that long tail.
- Remote feeds (RemoteOK, Remotive, Himalayas, WWR, HN) are specified in the plan
  but not implemented yet.

## Next

Stage 3, Score: deterministic gates first, then an LLM judge on survivors.
Needs the intake profile and facts ledger, which need a session with the
job seeker.
