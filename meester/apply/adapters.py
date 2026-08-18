"""Form adapters for the three ATSs, sharing one label-driven filler.

Philosophy: fill what is provably understood, refuse everything else. Every
control is identified by its human-visible label; base fields (name, email,
resume, ...) come from her application-answers profile and verified ledger,
question fields go through the answers doctrine, and anything unrecognised on
a required control raises NeedsHuman with a message she can act on. The
adapters differ only in URL shapes, submit-button wording and confirmation
heuristics - the filler is common.

Nothing in this module clicks Submit when dry_run is set.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .answers import NeedsHuman, answer_question

# --- per-ATS configuration --------------------------------------------------------

@dataclass
class ATSConfig:
    name: str
    hosts: tuple[str, ...]
    submit_words: tuple[str, ...] = ("submit application", "submit", "apply")
    confirm_pattern: str = r"thank|application.{0,30}(received|submitted)|we.{0,12}received"
    to_apply_url: "callable | None" = None


def _lever_apply_url(url: str) -> str:
    # jobs.lever.co/company/uuid -> .../apply (the posting page itself has no form)
    base = url.split("?")[0].rstrip("/")
    return base if base.endswith("/apply") else base + "/apply"


ADAPTERS: dict[str, ATSConfig] = {
    "greenhouse": ATSConfig(
        name="greenhouse",
        hosts=("job-boards.greenhouse.io", "boards.greenhouse.io", "greenhouse.io"),
    ),
    "lever": ATSConfig(
        name="lever",
        hosts=("jobs.lever.co", "jobs.eu.lever.co"),
        submit_words=("submit application", "submit"),
        to_apply_url=_lever_apply_url,
    ),
    "ashby": ATSConfig(
        name="ashby",
        hosts=("jobs.ashbyhq.com",),
    ),
}


def pick_adapter(url: str) -> ATSConfig | None:
    low = (url or "").lower()
    for config in ADAPTERS.values():
        if any(host in low for host in config.hosts):
            return config
    return None


# --- base fields ------------------------------------------------------------------
# Label patterns for the identity fields every board asks. These are not
# "questions" in the doctrine sense - they are her contact block.

_BASE_FIELDS: list[tuple[str, re.Pattern]] = [
    ("first_name", re.compile(r"^first\s*name", re.I)),
    ("last_name", re.compile(r"^last\s*name|^surname|^family\s*name", re.I)),
    ("full_name", re.compile(r"^(full\s*)?name$", re.I)),
    ("email", re.compile(r"^e-?mail", re.I)),
    ("phone", re.compile(r"^phone|^mobile", re.I)),
    ("location", re.compile(r"^location|^city$|current\s+location", re.I)),
    ("linkedin", re.compile(r"linkedin", re.I)),
    ("website", re.compile(r"portfolio|website|personal\s+site", re.I)),
    ("github", re.compile(r"github", re.I)),
    ("current_company", re.compile(r"^(current\s+)?company$|^current\s+employer|^organi[sz]ation$", re.I)),
    ("current_title", re.compile(r"^current\s+(title|role)$", re.I)),
    ("cover_letter", re.compile(r"cover\s*letter|additional\s+information", re.I)),
]


def base_field_value(kind: str, profile: dict, ledger: dict | None, letter: str) -> str | None:
    ledger = ledger or {}
    jobs = ledger.get("employment") or []
    latest = jobs[0] if jobs else {}
    first = (profile.get("app_first_name") or "").strip()
    last = (profile.get("app_last_name") or "").strip()
    values = {
        "first_name": first,
        "last_name": last,
        "full_name": f"{first} {last}".strip(),
        "email": (profile.get("app_email") or ledger.get("email") or "").strip(),
        "phone": (profile.get("app_phone") or ledger.get("phone") or "").strip(),
        "location": (profile.get("app_location") or ledger.get("location") or "").strip(),
        "linkedin": (profile.get("app_linkedin") or "").strip(),
        "website": (profile.get("app_portfolio") or "").strip(),
        "github": (profile.get("app_github") or "").strip(),
        "current_company": (latest.get("employer") or "").strip(),
        "current_title": (latest.get("title") or "").strip(),
        "cover_letter": letter.strip(),
    }
    return values.get(kind) or None


# --- captcha ----------------------------------------------------------------------

# The rule is "never SOLVE a captcha", which is not the same as "never touch a
# form containing one". Most Greenhouse forms carry an *invisible* reCAPTCHA
# badge that needs no human at all - refusing those would turn nearly every
# Greenhouse application into apply-by-hand. So: a visible challenge widget
# blocks; an invisible badge does not. If a challenge pops after submitting,
# the confirmation check fails and the evidence screenshot shows why.

_WIDGET_SELECTORS = (".g-recaptcha", ".h-captcha", "[data-hcaptcha-widget-id]",
                     ".cf-turnstile")
_CHALLENGE_IFRAMES = ("iframe[src*='recaptcha/api2/anchor']",
                      "iframe[src*='recaptcha/enterprise/anchor']",
                      "iframe[src*='hcaptcha.com']",
                      "iframe[src*='challenges.cloudflare.com']")


def captcha_present(page) -> bool:
    """True only for a captcha a human would have to interact with."""
    for selector in _WIDGET_SELECTORS:
        try:
            widgets = page.locator(selector)
            for i in range(widgets.count()):
                widget = widgets.nth(i)
                if not widget.is_visible():
                    continue
                if (widget.get_attribute("data-size") or "").lower() == "invisible":
                    continue
                return True
        except Exception:  # noqa: BLE001
            continue
    for selector in _CHALLENGE_IFRAMES:
        try:
            frames = page.locator(selector)
            for i in range(frames.count()):
                frame = frames.nth(i)
                if not frame.is_visible():
                    continue
                box = frame.bounding_box()
                # The checkbox anchor is ~300x78; invisible-mode anchors are
                # zero-sized or hidden.
                if box and box["width"] > 50 and box["height"] > 50:
                    return True
        except Exception:  # noqa: BLE001
            continue
    return False


# --- the filler -------------------------------------------------------------------

@dataclass
class FillReport:
    filled: list[dict] = field(default_factory=list)   # {label, value, source}
    skipped: list[str] = field(default_factory=list)   # optional + unanswerable
    resume_attached: bool = False

    def as_dict(self) -> dict:
        return {"filled": self.filled, "skipped": self.skipped,
                "resume_attached": self.resume_attached}


def _label_for(control) -> str:
    """The human-visible label of a form control, however the DOM spells it."""
    try:
        aria = control.get_attribute("aria-label")
        if aria and aria.strip():
            return aria.strip()
        cid = control.get_attribute("id")
        if cid:
            label = control.page.locator(f'label[for="{cid}"]')
            if label.count():
                return label.first.inner_text().strip()
        wrapper = control.locator("xpath=ancestor::label[1]")
        if wrapper.count():
            return wrapper.first.inner_text().strip()
        block = control.locator(
            "xpath=ancestor::*[self::div or self::fieldset]"
            "[.//label or .//legend][1]//*[self::label or self::legend][1]"
        )
        if block.count():
            return block.first.inner_text().strip()
    except Exception:  # noqa: BLE001
        pass
    return ""


def _is_required(control, label: str) -> bool:
    try:
        if control.get_attribute("required") is not None:
            return True
        if (control.get_attribute("aria-required") or "").lower() == "true":
            return True
    except Exception:  # noqa: BLE001
        pass
    return "*" in label or "✱" in label


def _classify_base(label: str) -> str | None:
    clean = label.replace("*", " ").replace("✱", " ")
    clean = re.sub(r"\s+", " ", clean).strip()
    for kind, pattern in _BASE_FIELDS:
        if pattern.search(clean):
            return kind
    return None


def fill_form(page, profile: dict, ledger: dict | None, letter: str,
              resume_path: Path | None, report: FillReport) -> None:
    """Fill every recognisable control on the page. Raises NeedsHuman on the
    first required control the doctrine cannot answer."""

    # File inputs first: the resume is the one attachment that must land.
    file_inputs = page.locator("input[type='file']")
    for i in range(file_inputs.count()):
        control = file_inputs.nth(i)
        label = _label_for(control).lower()
        if resume_path and ("resume" in label or "cv" in label or i == 0):
            control.set_input_files(str(resume_path))
            report.resume_attached = True
            break
    if resume_path and not report.resume_attached and file_inputs.count() == 0:
        # Some boards use a styled button wrapping a hidden input.
        hidden = page.locator("input[type='file']").first if page.locator("input[type='file']").count() else None
        if hidden:
            hidden.set_input_files(str(resume_path))
            report.resume_attached = True

    # Text-like controls.
    controls = page.locator(
        "input[type='text'], input[type='email'], input[type='tel'], "
        "input[type='url'], input:not([type]), textarea"
    )
    for i in range(controls.count()):
        control = controls.nth(i)
        try:
            if not control.is_visible() or control.input_value():
                continue
        except Exception:  # noqa: BLE001
            continue
        label = _label_for(control)
        required = _is_required(control, label)
        base = _classify_base(label)
        if base:
            value = base_field_value(base, profile, ledger, letter)
            if value:
                control.fill(value)
                report.filled.append({"label": label[:120], "value": value[:200],
                                      "source": f"base:{base}"})
            elif required:
                raise NeedsHuman(f'The form requires "{label[:120]}" and your '
                                 "profile has no value for it")
            else:
                report.skipped.append(label[:120])
            continue
        # Not a base field: it is a question, and the doctrine decides.
        answer = answer_question(label, profile, form_options=None, required=required)
        if answer is None:
            report.skipped.append(label[:120])
        else:
            control.fill(answer.value)
            report.filled.append({"label": label[:120], "value": answer.value[:200],
                                  "source": answer.source})

    # Selects: options are read from the form itself and matched via anchors.
    selects = page.locator("select")
    for i in range(selects.count()):
        control = selects.nth(i)
        try:
            if not control.is_visible():
                continue
        except Exception:  # noqa: BLE001
            continue
        label = _label_for(control)
        required = _is_required(control, label)
        options = [o.strip() for o in control.locator("option").all_inner_texts()
                   if o.strip() and not o.strip().lower().startswith(("select", "please", "--"))]
        answer = answer_question(label, profile, form_options=options, required=required)
        if answer is None:
            report.skipped.append(label[:120])
            continue
        control.select_option(label=answer.value)
        report.filled.append({"label": label[:120], "value": answer.value,
                              "source": answer.source})


def find_submit(page, config: ATSConfig):
    buttons = page.locator("button[type='submit'], input[type='submit'], button")
    for i in range(buttons.count()):
        button = buttons.nth(i)
        try:
            text = (button.inner_text() or button.get_attribute("value") or "").strip().lower()
        except Exception:  # noqa: BLE001
            continue
        if any(word in text for word in config.submit_words) and "linkedin" not in text:
            return button
    return None
