# profile/ — her CV and preferences

This is where the scoring stage reads from. Two files go here.

> ## Nothing in this folder is ever committed
>
> **This repository is public.** A CV carries full name, address, phone number,
> email and complete employment history. Everything in `profile/` except this
> README and the example file is gitignored, and the pre-push hook blocks the
> push outright if anything personal becomes tracked.
>
> Do not "temporarily" `git add -f` anything here. A push cannot be undone — a
> reverted commit still sits in the history and in every clone that already
> pulled it.

## 1. Her CV

Drop it in as `resume.pdf` (`.docx` also works):

```
~/Meester/profile/resume.pdf
```

Use the real one she actually sends out. It is read for facts, never rewritten
in place — the tailoring stage builds new documents and leaves this untouched.

## 2. Her preferences

Copy the template and fill it in — about ten minutes, and it decides the quality
of everything downstream:

```bash
cp ~/Meester/profile/preferences.example.yaml ~/Meester/profile/preferences.yaml
```

Then open it in TextEdit and answer honestly. Aspirational answers produce
aspirational matches.

## What happens to these

The scoring stage reads both to rank each posting against her, and builds a
locked **facts ledger** — every employer, title, date range and credential —
that later stages may rephrase but never invent. That ledger is what stops a
tailored CV from claiming something untrue.

Both files stay on her machine. Nothing here is uploaded anywhere except the
job-description scoring calls, which send the posting and a summary of her
experience — never the raw file.
