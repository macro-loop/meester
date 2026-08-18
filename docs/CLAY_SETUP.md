# Wiring Clay for warm outreach (William, ~30 minutes, one-time)

Her Mac can't reach your Clay workspace directly — Clay has no readable API
outside Enterprise. The supported shape is **webhook in → enrich → export out**,
so the round-trip is: her Mac POSTs a target to a Clay webhook table in your
workspace; your Clay workflow finds the contact; Clay writes the result to a
Google Sheet her Mac already has read access to.

You build this once. After that it runs itself.

## 0. Test the plumbing first (optional, 2 minutes)

Before building the Clay table, confirm the payload shape and that a webhook
receives it. In one terminal on the Mac:

```bash
python scripts/test_webhook.py serve
```

In another, fire the exact payload Meester sends:

```bash
python scripts/test_webhook.py send http://127.0.0.1:9999/
```

The receiver prints the JSON — `{fingerprint, company, role, job_url,
requested_at}`. Once your Clay webhook URL exists (step 1), `send` it there too
to confirm Clay ingests a row:

```bash
python scripts/test_webhook.py send "https://api.clay.com/…your-webhook…"
```

## 1. A webhook-source table

1. In your Clay workspace: **New table → Import → Webhook**.
2. Copy the webhook URL Clay gives you. It receives rows shaped like:

   ```json
   {"fingerprint": "...", "company": "Figma", "role": "Product Designer",
    "job_url": "https://...", "requested_at": "..."}
   ```

## 2. Enrichment columns

Add columns that turn `{company, role}` into a contact:

1. **Find People** (or Clay's recommended people-search) → filter to the
   company, and to titles matching the role's function (e.g. "Design Manager",
   "Head of Design", "Recruiter"). Take the top 1.
2. **Find Work Email** on that person.
3. You want, at minimum, columns that read as: name, work email, title,
   linkedin. Exact labels don't matter — the reader matches them loosely.

## 3. Export to a Google Sheet

1. Create a Google Sheet in **her** Google Drive (or shared so her account can
   read it). Header row: `fingerprint, name, email, title, linkedin`.
2. In Clay, add a **Write to Google Sheets** action (or HTTP export) that
   appends the enriched row, **including the `fingerprint`** passed in — that's
   how her Mac matches the contact back to the application that triggered it.
3. Copy the Sheet ID from its URL
   (`docs.google.com/spreadsheets/d/<THIS_PART>/edit`).

Optional: turn on Clay's auto-delete so rows clear after export and the table
stays cheap.

## 4. Tell her Mac

In `~/Meester/config/settings.yaml` on her machine (edit + push, or edit
locally), fill in:

```yaml
outreach:
  weekly_cap: 5
  clay_webhook_url: "https://api.clay.com/... (from step 1)"
  clay_sheet_id: "the Sheet ID from step 3"
```

Her Google connection (see GOOGLE_SETUP.md) already includes Sheets read
access, so nothing else is needed.

## How it flows once live

1. She approves and submits an application to a starred/dream company.
2. Next harvest cycle, her Mac POSTs that target to your Clay webhook.
3. Your Clay workflow enriches and writes the contact to the Sheet.
4. A later cycle reads the Sheet, drafts a 4-sentence note, and puts it on her
   **queue** as an outreach item.
5. She reads it, edits if she likes, taps **Send this note** — it goes from her
   Gmail, capped at `weekly_cap` per week.

Nothing sends without her tap, and the cap keeps this lane quality-only —
which is the entire point of outreach over volume.
