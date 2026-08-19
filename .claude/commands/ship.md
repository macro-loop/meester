---
description: Check, commit and push a change, then explain how it reaches her laptop
---

Ship the current working-tree changes.

1. Refuse and stop if this folder is `~/Meester` — that is production. Tell her to
   `cd ~/meester-dev`.
2. Run `bash -n scripts/*.sh`. If any script fails to parse, stop: a broken shell
   script strands her Mac with no way to self-update.
3. Run `.venv/bin/python -m pytest tests/ -q`. Use the venv interpreter, not the
   system one.
4. Show her `git status --short` and a readable summary of the diff — what
   changed, in plain language, not a raw patch dump.
5. Ask her to confirm. Wait for an actual answer.
6. Commit with an imperative one-line message describing the change, then push.
7. If the pre-push hook blocks the push, explain in plain language which of the
   three checks failed and what to do. A block is not a disaster; say so.
8. On success, tell her how to get it onto the real thing: open
   `http://127.0.0.1:8765` and click **Update available — install**, or wait for
   the hourly run. Mention that `tail -20 ~/Meester/logs/harvest.log` confirms it
   landed — look for `updated <old> -> <new>`.
