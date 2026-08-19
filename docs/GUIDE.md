# Your job-search assistant — the full manual

This tool runs quietly on your Mac and does the tedious parts of a job search
for you. Every hour it checks the careers pages of the companies on your list,
finds the remote roles that fit you, ranks them best-first, and lines them up
so you can apply with a tap.

Two promises it never breaks:

- **Nothing is ever sent anywhere without your tap.** Not an application, not
  an email, nothing.
- **Everything about you stays on your Mac.** Your CV, your answers, your
  letters — none of it lives on anyone's server.

---

## 1. Opening it — the two versions

There are two ways to see your jobs, and they look almost identical:

**The "Remote jobs" file on your Desktop** is a snapshot. It's great for
browsing — it always opens instantly, even if nothing else is running — but
it's **read-only**: no star, hide, or queue buttons. When the app is running
it says so at the top ("open the live app") with a link.

**The live app** is the real thing, with all the buttons. On your Mac, open
your browser and go to:

    http://127.0.0.1:8765

That address always works on your Mac — the app starts itself when you log in
and restarts itself if it ever stops. Nothing to launch, ever.

> **Tip:** open that address in Safari, then **File → Add to Dock**. You get a
> proper app icon that opens the live version directly.

**On your phone**, open the Tailscale address (it ends in `.ts.net`; run
`tailscale serve status` on your Mac to see it). Works from anywhere, as long as your Mac is awake — lid open, or
plugged in with sleep prevented. On iPhone: open it in Safari, then
**Share → Add to Home Screen** for an app icon.

Along the top of the jobs page are the other screens: **Your profile**,
**Your CV**, **Letters**, **Queue**, and **Add companies**.

---

## 2. The jobs page

The numbers across the top: total open roles found, how many appeared today,
how many companies are being watched, and how many roles match you.

### The tabs

- **For you** — the one that matters. Roles that match your profile, best
  first.
- **Everything** — every open remote role found, matched or not.
- **New today / This week** — recent arrivals, for a quick skim.
- **Salary shown** — only postings that state a salary.

The **search box** filters any tab by any word — a company, a title, a city.

### Reading a match

Each "For you" role explains itself. A line like:

> **42% fit** · In analytics, your field · Asks for Data Analysis, SQL — on
> your CV · her SQL/SAS work on CMS Medicare claims ~ their requirement to
> write complex SQL queries

has three parts:

- **The fit %** — an AI's judgment of the whole posting against your whole CV.
  Rough guide: **80+** means your record covers the core requirements; **50–79**
  means real overlap with a gap or two; **below 50** means they probably want a
  different person. Don't treat small differences as meaningful — 42% vs 40% is
  a coin flip; 75% vs 40% is not. And a low % on a job *you* like is not a
  verdict — it can't see everything about you. It's a sorting aid, not a judge.
- **The plain reasons** ("Title matches… Asks for SQL — on your CV") — simple,
  checkable facts about why it matched.
- **The evidence** ("her X ~ their Y") — the AI pairing something you've
  actually done with something the posting actually asks for. It is only
  allowed to use what's in your verified CV — it can never invent experience.

A **New** tag means it appeared in the last day. The age on the right
("6d ago") is how long the posting has been open — fresher is better odds.

### The buttons on each role (live app only)

- **Queue** — the big one. Drafts a complete application and parks it on the
  Queue screen for your review. Nothing is sent yet. (Only appears on matches
  you haven't applied to.)
- **★ Star** — interesting, come back later. Starred roles keep the star
  visible everywhere.
- **✓ Applied** — you applied (here or anywhere else). It leaves "For you" and
  an **Applied** chip appears next to the tabs so you can always find them.
  Marking applied also stops the tool from ever queueing that job again.
- **✕ Hide** — not for you. It disappears; a **Hidden** chip appears so you
  can un-hide if you change your mind.

Click a job's **title** to open the company's real posting in a new tab.

---

## 3. Your profile

This form defines what "fits you" means. It's worth a careful ten minutes, and
worth revisiting once a month.

### Matching — what to look for

- **Job titles you'd accept** — the most important field. Keep each title
  short and generic: "Data Analyst", not "Senior Healthcare Data Analyst".
  Short titles catch every variation; long ones catch almost nothing. List
  every title you'd genuinely take.
- **Seniority** and **fields you're open to** — refine the match.
- **Lowest yearly salary you'd seriously consider** — postings that state a
  lower ceiling are filtered out. Be honest: an aspirational number silently
  empties your list. Postings that don't state a salary are *not* filtered.
- **Countries / sponsorship / timezone** — keeps out roles you can't take.
- **Companies or industries never to show** — the block list.
- **Companies you'd be genuinely excited by** — the dream list. Their roles get
  a ★ and are always left for you to apply personally — never automated.
- **What you're moving away from / what matters most** — free text, in your
  own words. The AI reads these when scoring fit, so say the true thing.

### Application answers — what forms get filled with

Name, email, phone, location, LinkedIn — exactly as you want them to appear
on applications.

- **Work authorization / sponsorship** — answered on forms only by exact
  match, only from what you set here.
- **The EEO questions** (gender, race/ethnicity, veteran status, disability) —
  these are the voluntary questions on US applications. Each one offers the
  real options, plus **"Prefer not to say"**, plus **"Always ask me"**.
  "Always ask me" is the default and the safe choice: any form containing that
  question simply comes back to you instead of being answered. The tool will
  **never guess** an answer to a legal or EEO question — that rule is built in,
  not a setting.

### The AI key

With a key entered, matches get the fit % and evidence. The key comes from
your own Anthropic account and you paste it in here yourself — see
`docs/MAINTAINING.md`.
Without it, matching still works — you just get the plain reasons alone.

---

## 4. Your CV

Upload the PDF you actually send out, click **"Read my CV into the editor"**,
then — this is the important part — **fix anything it misread** (employer
names, dates, bullets) and press **Save**.

Saving marks the record *verified*, and verified matters: this record is the
only thing the AI is allowed to cite when it claims you match a job, and the
only source applications are filled from. Wrong record, wrong applications.
The uploaded PDF itself is what gets attached to applications — exactly as
you made it.

If your CV changes, upload the new one and repeat. Everything on this screen
stays on your Mac.

---

## 5. Letters

Two or three short cover-letter templates in your own voice — that's plenty.
Placeholders fill themselves per job:

- `{company}` and `{role}` — filled automatically.
- `{why_them}` — one sentence about why this company, filled by the AI from
  the match evidence, or by you on the queue card. A letter with an unfilled
  blank **cannot be approved** — the Approve button stays off until it's dealt
  with.

---

## 6. Add companies

**This is how you steer the whole machine.** It only looks at companies on
your list, so the list *is* your job search. Adding the right companies does
more for your matches than any other single thing.

Type a company's name — or paste a link to their jobs page — and it finds
their board and adds it. Add a few whenever one comes to mind: a company from
a job ad, a competitor of somewhere you liked, a name from a newsletter.

*Good starters in your field:* Komodo Health, Flatiron Health, Oscar Health,
Included Health, Cedar, Spring Health, Lyra Health, Maven Clinic, Truveta,
Cohere Health, Clarify Health.

(Not every company can be added — it works for companies whose careers pages
run on Greenhouse, Lever, or Ashby, which covers most tech and health-tech
companies. If one can't be found, it says so.)

---

## 7. The Queue — where things actually happen

The Queue screen has three sections:

**Waiting for you** — cards that need a decision. Each card shows *exactly*
what would be submitted: the job (click the title to see the real posting),
why it matched, every answer, and the letter as it would be sent. Your
choices:

- **Approve** — it will be submitted on the next run, from your own computer,
  at a human pace. What you saw on the card is exactly what goes — no more.
- **Skip** — not this one. It never comes back on its own.
- **Edit first** — the letter (and the `{why_them}` line) are editable right
  on the card; **Save letter**, then Approve.

**Approved — will submit on the next run** — approved and waiting their turn.
Runs happen automatically about once an hour; **Run now** at the top starts
one immediately (results appear after a few minutes — the pacing is
deliberately unhurried, like a person filling a form). You can still
**Withdraw** anything here before it goes.

**Recently done** — what happened, including proof: every submission saves a
screenshot of the filled form and one of the confirmation page.

### When a card says it needs you

Some forms contain things the tool refuses to do for you — an essay question,
a login wall, a CAPTCHA, a question it doesn't recognize, or an EEO question
you've set to "Always ask me". Those cards come back marked **needs human**
with:

- **Open the application** — the direct link; finish it by hand (usually the
  hard part — the answers — is on the card to copy from).
- **I applied by hand** — tell it you did; it's tracked like any other
  application.
- **Try again / Skip** — if the hiccup was temporary, or if you'd rather not.

This isn't a malfunction — it's the design. The tool does the typing; anything
resembling a judgment call is yours.

Cards nobody touches for 48 hours quietly expire, so the queue never silts up.
There's also a daily submission cap, so it can never firehose applications in
your name.

### Two settings you can flip

- **Auto-propose:** strong matches queue *themselves* as drafts each hour, so
  you wake up to cards waiting for review instead of clicking Queue yourself.
  Still nothing sends without your tap.
- **Auto-submit:** after the first thirty or so supervised applications prove
  everything trustworthy, approving can become automatic for strong matches.
  That's a decision for later, together.

Both live in `config/settings.local.yaml` on your Mac. Open the dev folder and
ask Claude to set them — `docs/MAINTAINING.md` has the steps.

---

## 8. After you apply — the mail loop

*(This part switches on once Gmail is connected — see `docs/GOOGLE_SETUP.md`.)*

A one-time Gmail filter labels job-search mail (application confirmations,
recruiter replies) with a **JobSearch** label. The tool reads **only** mail
with that label — that's a hard rule in the code, not a preference — and:

- **Updates each job's status by itself.** A rejection flips the job to
  *rejected* (no need to read it if you'd rather not). A scheduling email or
  interview request flips it to *interview* and pops a notification on your
  Mac. An assessment invite becomes *assessment*.
- **Drafts replies, never sends them.** For interview and scheduling emails, a
  suggested reply appears in your Gmail **Drafts** — in your voice, for you to
  edit and send from your own Gmail like any other email. The tool cannot send
  mail on its own.
- **Notices silence.** Applied three weeks ago and heard nothing? The job gets
  a quiet note so you know it's likely gone cold.
- **Keeps a ledger in a Google Sheet.** Every job you apply to —
  automatically, by hand from a queue card, or just ticked ✓ on the jobs
  list — becomes one row on a shared spreadsheet: date, company, title,
  how, and a link. It only ever *adds* rows, so the sheet is yours to live
  in — add a notes column, color things, sort however you like; nothing
  you write there is ever touched.

### Warm outreach

*(Also switches on later.)* For companies you starred or dream-listed, a few
days after you apply the tool finds the actual recruiter or hiring manager
and drafts a short, specific note to them. The draft appears on your Queue —
you read it, edit it, and only **Send this note** sends it, from your own
email address. Capped at a handful per week on purpose: this lane is
quality-only.

---

## 9. What's automatic, and what's yours

| The tool does | You do |
|---|---|
| Checks every company on your list, hourly | Keep the company list growing |
| Ranks and explains every match | Star / hide / queue what you like |
| Drafts applications, letters, notes | Read the card, **Approve** |
| Fills and submits approved forms | Handle the "needs you" cards |
| Tracks statuses from your mail | Send the replies (from your Gmail) |
| Keeps itself updated | Nothing — updates install themselves |

---

## 10. A simple routine

**Most days — five minutes:**

1. Open the app (Dock icon or phone).
2. Skim **For you**. Star the good, hide the noise.
3. **Queue** anything you want. Then the Queue screen: read, edit if needed,
   **Approve**.

**Once a week — ten minutes:**

- Add a few companies.
- Clear the queue: approve, finish the needs-you ones, skip the rest.
- Glance at Applied — anything flipped to *interview* deserves a same-day
  reply (there's probably already a draft in your Gmail).

---

## 11. Pausing everything

Make an empty file named `PAUSED` (no extension) in the **Meester** folder in
your home folder — everything stops: no harvests, no submissions, no mail
reading. Delete the file to resume. No terminal needed — you can do it in
Finder.

---

## 12. When something looks off

- **No star/queue buttons?** You're in the Desktop snapshot. Click "open the
  live app" at the top, or go to `http://127.0.0.1:8765`.
- **Page looks stale?** Reopen the file, or reload the live app. New results
  arrive roughly hourly.
- **Phone link dead?** Your Mac is asleep. Open the lid.
- **No fit percentages?** Usually the CV isn't saved-and-verified yet, or the
  AI key is missing — both live on Profile / Your CV.
- **Anything else** — there's a built-in checkup (`meester doctor`) that
  reports exactly what's working, so most fixes are quick. Run it, then open
  the dev folder and ask Claude. `docs/MAINTAINING.md` has the steps.

---

## Changing the tool itself

This manual covers *using* it. Changing it — adding a feature, fixing something,
adjusting how matches are scored — is a separate manual: **`docs/MAINTAINING.md`**.
You don't need to write code for that; you describe what you want and Claude makes
the change in your `~/meester-dev` folder. The one rule is that the editing
happens there, never in the folder that runs your job search.

---

One last thing worth knowing: everything the tool ever does in your name
leaves a record on your Mac — every submission, every screenshot, every note.
Nothing is ever quietly done for you.
