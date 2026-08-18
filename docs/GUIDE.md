# Your job-search assistant — how to use it

This tool runs quietly on your Mac and does the tedious parts of a job search
for you. Every hour it checks the careers pages of dozens of companies, finds
the remote roles that fit you, ranks them best-first, and lines them up so you
can apply with a tap. **Nothing is ever sent anywhere without you approving it.**

---

## Opening it

Double-click **“Remote jobs”** on your Desktop. It opens in your browser.
It refreshes itself in the background — to see the latest, just reopen the file.

On your phone: open the Tailscale link (the `…​.ts.net` address). Your Mac needs
to be awake for the phone view to work.

At the top of the jobs page are links to the other screens: **Your profile**,
**Your CV**, **Letters**, **Queue**, and **Add companies**.

---

## The jobs list

**The “For you” tab** is the important one — the roles that match you, best
first. Each shows *why* it matched (“Title matches ‘Data Analyst’ · Asks for
SQL — on your CV”), and once the AI rating is on, a **fit %** at the front.

The other tabs — Everything, New today, This week, Salary shown — are there when
you want to browse wider. The **search box** filters by any word (a company,
a title, a place).

On the right of each role are three buttons:

- **★ Star** — mark it as interesting, to come back to.
- **✓ Applied** — mark that you’ve applied (it then drops out of “For you”).
- **✕ Hide** — not for you; it disappears from the lists.

Click a job’s **title** to open the real application page in a new tab.

---

## Your profile

This is the form that decides what “fits you” means, so it’s worth a careful
ten minutes.

- **Job titles** you’d accept — keep each short (“Data Analyst”, not “Senior
  Healthcare Data Analyst”), so it catches every variation.
- **Salary floor**, **work authorization**, and the voluntary **EEO questions**
  (these default to “always ask me”, which is safe — fill them in only if you
  want applications to answer them for you).
- The **AI rating key** — if a key is entered here, each match gets a fit
  percentage and evidence drawn from your CV. Without it, matching still works,
  just without the percentages.

Answer honestly, not aspirationally — an inflated salary floor produces an
empty list.

---

## Your CV

Upload the PDF you actually send out, click **“Read my CV into the editor,”**
and correct anything it got wrong — employer names, dates, bullet points — then
**Save**. This becomes the record the tool compares every job against, and the
foundation for any tailored applications, so getting it right matters.

Everything on this screen stays on your Mac.

---

## Letters

A couple of short cover-letter templates in your own voice. Placeholders like
`{company}` and `{role}` fill themselves in per job later. You don’t need many —
two or three is plenty.

---

## Add companies

**This is how you control what gets found.** The tool only looks at companies on
your list, so adding the right ones is the single biggest thing you can do to
improve your matches.

Type a company’s name (or paste the link to their jobs page) and it looks them
up and adds them. Add a handful whenever you think of one.

*Good ones to start with in your field:* Komodo Health, Flatiron Health, Oscar
Health, Included Health, Cedar, Spring Health, Lyra Health, Maven Clinic,
Truveta, Cohere Health, Clarify Health.

---

## Queue — where you approve applications

When you queue an application (the **Queue** button on a matching role), it
lands here as a card showing *exactly* what would be submitted: the answers,
the cover letter, your CV. Read it, edit the letter if you like, and tap
**Approve** — the tool then fills in and submits that application for you, from
your own computer, at a natural pace.

**Nothing is submitted without your tap.** If a form has something the tool
shouldn’t answer for you (an essay, a login, a CAPTCHA, an unusual question),
it stops and hands that one back to you with a link to finish by hand.

Notes to hiring managers (when that’s set up) appear here too, to approve and
send the same way.

---

## What’s automatic, and what needs you

**Automatic:** finding jobs, ranking them, drafting applications and notes.

**You:** approving each application, keeping your profile and company list
current, and pressing send. The tool does the legwork; the decisions stay yours.

---

## A simple routine

**Most days (5 minutes):**
1. Open “Remote jobs.”
2. Skim the **For you** tab. Star the good ones, hide the noise.
3. For any you want, click **Queue**, then review and **Approve** on the Queue
   screen.

**Once a week:**
- Add a few more companies in your field on the **Add companies** screen.
- Glance at anything sitting in the Queue and clear it out.

---

## Pausing everything

To stop the tool entirely: make an empty file named `PAUSED` (no extension) in
the **Meester** folder in your home folder. Delete it to start again. Or just
ask William.

---

## If something looks off

Tell William — there’s a built-in check he can run (`meester doctor`) that
reports exactly what’s working and what isn’t, so most things are a quick fix.
