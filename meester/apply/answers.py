"""Mapping application-form questions to her profile answers.

The doctrine, from the master plan and enforced here: a form question receives
an answer ONLY by matching a curated pattern table against her explicit profile
choices. Anything unmapped - a question we have not seen, an option list that
does not contain her choice, a field she set to "always ask me" - stops the
application and routes it to her. Guessing wrong on work authorization is not a
UX bug, it is a false statement on a hiring record.

No LLM is ever consulted here. This module is deliberately boring.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --- question recognition ---------------------------------------------------------
# Each entry: (profile_key, compiled pattern over the question's label text).
# First match wins. Patterns are tight on purpose: failing to recognise a
# question costs a manual application; misrecognising one costs the truth.

QUESTION_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("auth_us", re.compile(
        r"(legally\s+)?authori[sz]ed\s+to\s+work.{0,40}(united\s+states|u\.?s\.?\b)|"
        r"work\s+authori[sz]ation.{0,30}(united\s+states|u\.?s\.?\b)", re.I | re.S)),
    ("needs_sponsorship", re.compile(
        r"(require|need).{0,40}(visa\s+)?sponsorship|sponsorship.{0,40}(now\s+or\s+in\s+the\s+future|employment\s+visa)", re.I | re.S)),
    ("eeo_gender", re.compile(r"^\s*gender\s*$|gender\s+identity|^\s*sex\s*$", re.I)),
    ("eeo_race", re.compile(r"race|ethnicity|ethnic\s+background", re.I)),
    ("eeo_veteran", re.compile(r"veteran\s+status|protected\s+veteran|\bveteran\b", re.I)),
    ("eeo_disability", re.compile(r"disability|disabilities", re.I)),
    ("eeo_lgbtq", re.compile(r"lgbtq", re.I)),
    ("app_linkedin", re.compile(r"linkedin", re.I)),
    ("app_portfolio", re.compile(r"portfolio|personal\s+website|website\s+url", re.I)),
    ("app_location", re.compile(r"^(current\s+)?location$|city\s+of\s+residence|where\s+are\s+you\s+(currently\s+)?(based|located)", re.I)),
    ("notice_period_weeks", re.compile(r"notice\s+period|(when|how\s+soon).{0,30}(start|available)", re.I)),
    ("salary_expect", re.compile(r"salary\s+(expectation|requirement)|desired\s+(salary|compensation)|compensation\s+expectation", re.I)),
    ("how_heard", re.compile(r"how\s+did\s+you\s+hear", re.I)),
]

# Boolean profile answers rendered onto yes/no form options. auth_us is NOT
# here - it is a three-state select whose empty state means "always ask me".
_BOOL_KEYS = {"needs_sponsorship"}

# For select/radio questions: her stored value -> substrings that identify an
# acceptable option in the form's own list. The form's wording varies; these
# anchors do not.
OPTION_ANCHORS: dict[str, list[str]] = {
    "yes": ["yes"],
    "no": ["no"],
    "prefer not to say": ["prefer not", "decline", "don't wish", "do not wish", "not to answer"],
    "male": ["male"],
    "female": ["female"],
    "non-binary": ["non-binary", "nonbinary", "non binary"],
    "i am not a protected veteran": ["not a protected veteran", "am not", "no,"],
    "i identify as one or more": ["identify as", "yes,"],
    "yes, i have a disability": ["yes"],
    "no, i do not have a disability": ["no"],
    "american indian or alaska native": ["american indian", "alaska"],
    "asian": ["asian"],
    "black or african american": ["black", "african american"],
    "hispanic or latino": ["hispanic", "latino"],
    "native hawaiian or other pacific islander": ["hawaiian", "pacific islander"],
    "white": ["white"],
    "two or more races": ["two or more"],
}


@dataclass
class Answer:
    value: str          # what to type or which option to pick
    source: str         # the profile key it came from, for the evidence record
    kind: str           # "text" | "option"


class NeedsHuman(Exception):
    """Raised whenever the doctrine says stop. The message is shown to her."""


def recognise(question_label: str) -> str | None:
    """Which profile key answers this question, or None if unrecognised."""
    label = " ".join((question_label or "").split())[:300]
    if not label:
        return None
    for key, pattern in QUESTION_PATTERNS:
        if pattern.search(label):
            return key
    return None


def _profile_value(key: str, profile: dict) -> str | None:
    """Her stored answer for a mapped key, or None when she has not answered
    (which includes the explicit 'always ask me' empty state)."""
    value = profile.get(key)
    if key in _BOOL_KEYS:
        if not isinstance(value, bool):
            return None  # unanswered bool = ask her, never default
        return "yes" if value else "no"
    if value is None or str(value).strip() == "":
        return None
    if key == "notice_period_weeks":
        return f"{value} weeks"
    return str(value).strip()


def match_option(profile_value: str, form_options: list[str]) -> str | None:
    """Pick the form's own option matching her stored value, or None.

    Only the anchor table decides; a value with no anchors, or anchors that
    match zero or MULTIPLE options, refuses rather than picks."""
    value = profile_value.strip().lower()
    anchors = None
    for stored, subs in OPTION_ANCHORS.items():
        if value.startswith(stored[:24]):
            anchors = subs
            break
    if anchors is None:
        return None
    hits = []
    for option in form_options:
        low = option.strip().lower()
        if any(a in low for a in anchors):
            hits.append(option)
    return hits[0] if len(hits) == 1 else None


def answer_question(
    question_label: str,
    profile: dict,
    form_options: list[str] | None = None,
    required: bool = True,
) -> Answer | None:
    """The single entry point adapters use.

    Returns an Answer, or None for an optional question we choose to leave
    blank, or raises NeedsHuman when a required question cannot be answered
    within the doctrine.
    """
    key = recognise(question_label)
    if key is None:
        if not required:
            return None
        raise NeedsHuman(f'Form asks "{question_label[:120]}" - not a question '
                         "I answer for you")

    if key in ("salary_expect", "how_heard"):
        # Deliberately never automated: salary anchoring is strategy, and
        # "how did you hear" honesty is hers to phrase.
        if not required:
            return None
        raise NeedsHuman(f'Form asks "{question_label[:120]}" - answer this one yourself')

    value = _profile_value(key, profile)
    if value is None:
        if not required:
            return None
        raise NeedsHuman(f'Form asks "{question_label[:120]}" and your profile '
                         'says "always ask me"')

    if form_options:
        chosen = match_option(value, form_options)
        if chosen is None:
            raise NeedsHuman(
                f'Form asks "{question_label[:120]}" but none of its options '
                f'clearly matches your answer "{value}"'
            )
        return Answer(value=chosen, source=key, kind="option")
    return Answer(value=value, source=key, kind="text")
