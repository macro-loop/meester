---
description: Diagnose the live system and translate the result into plain language
---

Check on the running job search in `~/Meester`.

Run, without changing anything:

- `~/Meester/.venv/bin/python -m meester doctor`
- `tail -40 ~/Meester/logs/harvest.log`
- `git -C ~/Meester status --porcelain` (anything printed here is a problem —
  production has been hand-edited and is no longer receiving updates)
- `git -C ~/Meester log --oneline -1` and compare to `git log --oneline -1` here,
  to see whether production is behind

Then tell her, in plain language:

- Is it running? When did it last succeed?
- Is anything actually broken, or just idle because the laptop was asleep?
- Is production up to date with what has been pushed?

Do not dump raw output at her. Quote a line only when it is the evidence for
something you are telling her. End with one concrete next step, or "nothing to do".
