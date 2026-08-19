---
description: Undo a change that has already been pushed
---

Undo a pushed change.

1. Show the last several commits with `git log --oneline -10`, described in plain
   language, and ask which one to undo. If she has just said "the last one",
   don't make her pick from a list.
2. `git revert --no-edit <sha>`. Never rewrite history, never force-push — her Mac
   pulls fast-forward only and a rewritten history would strand it.
3. Run the tests, then push.
4. Tell her to click **Update available — install** at `http://127.0.0.1:8765`.
   Mention that this works even if `PAUSED` exists.
5. If she paused things first, remind her the fix will not arrive on its own
   until either she clicks that button or deletes `PAUSED`.

If the revert conflicts, stop and explain the situation rather than guessing at a
resolution.
