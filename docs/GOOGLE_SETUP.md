# Connecting Gmail + Sheets (one-time, ~20 minutes)

This lets Meester read her job-search mail (only mail she has labelled
`JobSearch`), draft replies into her Gmail, send approved outreach from her
address, and read the Clay contact sheet. Everything runs on her Mac; no
credential leaves it.

Do this once, on **her** Google account.

## 1. Create a Google Cloud project

1. Go to <https://console.cloud.google.com/> and sign in as her.
2. Top bar → project dropdown → **New Project**. Name it "Meester". Create,
   then select it.

## 2. Enable the two APIs

1. **APIs & Services → Library**.
2. Search **Gmail API** → Enable.
3. Search **Google Sheets API** → Enable.

## 3. Configure the consent screen

1. **APIs & Services → OAuth consent screen**.
2. User type **External** → Create.
3. App name "Meester", her email as support + developer contact. Save through
   the steps; you can leave optional fields blank.
4. On **Test users**, add her own email address. (The app stays in "testing",
   which is fine forever for one user — no Google verification needed.)

## 4. Create the credential

1. **APIs & Services → Credentials → Create Credentials → OAuth client ID**.
2. Application type **Desktop app**. Name it "Meester". Create.
3. **Download JSON**. Save it as exactly:

   ```
   ~/Meester/profile/google_credentials.json
   ```

## 5. Connect

In Terminal on her Mac:

```bash
cd ~/Meester && .venv/bin/python -m meester google-auth
```

A browser opens; she approves the scopes (Google will warn the app is
unverified — that's expected for a personal testing app; **Advanced →
Go to Meester**). The tab says "connected", and a refreshable token is stored
at `profile/google_token.json`.

The scopes requested: Gmail read/label/draft, Gmail send (approved outreach
only), and Sheets read/write (polling Clay's contact export, and mirroring
applied jobs to the Applications tab of the tracking sheet).

> **If she connected before the tracker existed** (the token was granted when
> Sheets was read-only): sheet writes will fail with a "reconnect" hint in the
> log. The fix is running the same command above once more and approving again.

## 6. The JobSearch label + filter

So Meester only ever sees hiring mail, she makes one Gmail filter:

1. Gmail → search bar → **Show search options** (the slider icon).
2. In **From**, paste (adjust over the first week as she sees what's missed):

   ```
   greenhouse.io OR lever.co OR ashbyhq.com OR myworkday.com OR hire.lever.co OR ashbyhq.com OR notion.so OR rippling.com
   ```

3. **Create filter** → tick **Apply the label** → **New label** → `JobSearch`.
   Also tick **Skip the Inbox** if she wants hiring mail out of her main inbox.
4. Optionally tick "Also apply to matching conversations".

That's it. The filter will miss some senders in week one — when a recruiter
email lands in her main inbox, she adds that domain to the filter.

## What Meester does and doesn't do with this

- **Reads**: only `label:JobSearch` mail. This is enforced in code — every
  Gmail read is hard-scoped to that label and the code refuses to run a query
  without it.
- **Drafts**: replies to interview/recruiter mail land in her Gmail Drafts.
  She reviews and sends. Meester never sends a reply itself.
- **Sends**: only outreach notes she has explicitly approved on the queue
  screen, from her address, capped weekly.
- **Never** touches anything outside the label, and never deletes mail.
