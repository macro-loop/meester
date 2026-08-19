---
description: Add companies to the watchlist and ship it
argument-hint: [company or board token]
---

Add one or more companies to the job-board watchlist: $ARGUMENTS

1. Open `config/companies.yaml` and work out which section each belongs in —
   `greenhouse`, `lever` or `ashby`. The entry is the board token from the
   company's careers URL, not the company's display name.
2. If you are unsure of a token, say so and ask rather than guessing. A wrong
   token silently harvests nothing.
3. Check it isn't already listed.
4. Add it, keeping the existing ordering and formatting of the file.
5. Then run the `/ship` flow.

After it lands, her Mac notices the file changed and re-verifies every board
token on the next run — she should expect one slower cycle, and a
`re-verifying board tokens (companies.yaml changed)` line in the log.
