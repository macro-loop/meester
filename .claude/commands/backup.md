---
description: Snapshot the profile folder, which git deliberately never saves
---

Back up `~/Meester/profile`.

```bash
mkdir -p ~/Meester-backup
ditto -c -k --keepParent ~/Meester/profile ~/Meester-backup/profile-$(date +%F).zip
```

Confirm the file was written and report its size.

Remind her why this matters: `profile/` is excluded from git on purpose, because
this repo is public and that folder holds her CV, verified work history, letters,
answers, Anthropic key and Google token. It exists in exactly one place, and
rebuilding the facts ledger by hand is slow.

Also: **that zip contains her key and her Google token.** It stays on the Mac —
not in a shared Drive or anywhere synced to other people.

If there are more than about six old snapshots, offer to delete the oldest ones.
