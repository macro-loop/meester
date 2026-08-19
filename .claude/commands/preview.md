---
description: Run the app here with her real data, on port 8766
---

Start a preview of the app in this dev folder, so a screen change can be seen
against real jobs.

1. Refuse if this folder is `~/Meester`.
2. Copy her live data in — both are gitignored in every clone, so this is safe:
   - `rsync -a ~/Meester/profile/ ./profile/`
   - `rsync -a ~/Meester/data/ ./data/`
3. Start `.venv/bin/python -m meester serve --port 8766`.
   **Port 8766, never 8765** — 8765 is the real app's service and binding it fails.
4. Open `http://127.0.0.1:8766` and tell her which screen to look at.

**Never run `apply-run` in this folder, with or without `--live`.** The copy above
brings real approved queue items and working credentials with it; running the
apply engine here would submit real applications from the workbench.

When she is done, stop the server and mention that the copied `profile/` and
`data/` are still sitting here — leaving them is fine, they are ignored by git.
