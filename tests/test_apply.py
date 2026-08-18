"""Apply-engine tests: the answers doctrine and the queue state machine.

The doctrine tests are the most important in the repository: they pin that no
legal or unknown question can ever receive a generated answer.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from meester.apply.answers import NeedsHuman, answer_question, match_option, recognise
from meester.apply.engine import fill_letter, letter_ready
from meester.apply.queue import Queue

PROFILE = {
    "auth_us": "yes",
    "needs_sponsorship": False,
    "eeo_gender": "prefer not to say",
    "eeo_veteran": "i am not a protected veteran",
    "app_linkedin": "https://linkedin.com/in/her",
    "notice_period_weeks": 4,
}


# --- the doctrine -----------------------------------------------------------------

def test_unknown_required_question_always_stops():
    with pytest.raises(NeedsHuman):
        answer_question("Describe a project you are proud of", PROFILE, required=True)


def test_unknown_optional_question_is_left_blank():
    assert answer_question("Describe a project you are proud of", PROFILE,
                           required=False) is None


def test_always_ask_me_stops_even_on_recognised_questions():
    profile = {**PROFILE, "eeo_race": ""}
    with pytest.raises(NeedsHuman) as e:
        answer_question("Race/Ethnicity", profile,
                        form_options=["Asian", "White", "Decline to self identify"])
    assert "always ask me" in str(e.value)


def test_salary_and_how_heard_are_never_automated():
    for label in ("What are your salary expectations?", "How did you hear about us?"):
        with pytest.raises(NeedsHuman):
            answer_question(label, PROFILE, required=True)


def test_work_auth_answers_from_profile_exactly():
    a = answer_question("Are you legally authorized to work in the United States?",
                        PROFILE, form_options=["Yes", "No"])
    assert a.value == "Yes" and a.source == "auth_us"


def test_sponsorship_bool_maps_to_no():
    a = answer_question("Will you now or in the future require sponsorship "
                        "for employment visa status?", PROFILE,
                        form_options=["Yes", "No"])
    assert a.value == "No" and a.source == "needs_sponsorship"


def test_unanswered_sponsorship_bool_stops():
    with pytest.raises(NeedsHuman):
        answer_question("Do you require sponsorship?", {"needs_sponsorship": None})


def test_eeo_decline_matches_the_forms_own_wording():
    a = answer_question("Gender", PROFILE,
                        form_options=["Male", "Female", "Decline To Self Identify"])
    assert a.value == "Decline To Self Identify"


def test_ambiguous_options_refuse_rather_than_pick():
    # Two options both contain "yes" - the anchor table must refuse.
    assert match_option("yes", ["Yes, immediately", "Yes, in 30 days"]) is None
    with pytest.raises(NeedsHuman):
        answer_question("Are you authorized to work in the U.S.?", PROFILE,
                        form_options=["Yes, immediately", "Yes, in 30 days"])


def test_veteran_status_recognised_and_matched():
    a = answer_question("Veteran Status", PROFILE,
                        form_options=["I am not a protected veteran",
                                      "I identify as one or more of the classes",
                                      "I don't wish to answer"])
    assert a.value == "I am not a protected veteran"


def test_notice_period_reads_naturally():
    a = answer_question("What is your notice period?", PROFILE)
    assert a.value == "4 weeks"


def test_recognition_is_tight_not_greedy():
    assert recognise("Tell us about your leadership style") is None
    assert recognise("LinkedIn Profile") == "app_linkedin"


# --- letters ----------------------------------------------------------------------

def test_letter_fill_and_readiness():
    body = "Dear {company}, re {role}. {why_them}"
    job = {"company": "Figma", "title": "Designer"}
    assert not letter_ready(fill_letter(body, job))  # why_them still open
    done = fill_letter(body, job, why_them="Your editor changed how teams work.")
    assert letter_ready(done)
    assert "Figma" in done and "{" not in done


# --- queue ------------------------------------------------------------------------

def make_item(q: Queue, item_id="fp1"):
    return q.propose(item_id, "application", {
        "job": {"title": "T", "company": "C", "url": "u", "apply_url": "a"},
        "score": 50, "reasons": ["r"],
    })


def test_queue_lifecycle(tmp_path):
    q = Queue(tmp_path / "queue.json")
    assert make_item(q) is not None
    q.transition("fp1", "approved")
    q.transition("fp1", "submitting")
    q.transition("fp1", "submitted", confirmed=True)
    assert q.by_state("submitted")[0]["confirmed"] is True


def test_skipped_items_never_resurrect(tmp_path):
    q = Queue(tmp_path / "queue.json")
    make_item(q)
    q.transition("fp1", "skipped")
    assert make_item(q) is None, "a skipped application must not reappear each harvest"


def test_illegal_transitions_raise(tmp_path):
    q = Queue(tmp_path / "queue.json")
    make_item(q)
    with pytest.raises(ValueError):
        q.transition("fp1", "submitted")  # proposed -> submitted skips approval
    q.transition("fp1", "approved")
    q.transition("fp1", "submitting")
    with pytest.raises(ValueError):
        q.transition("fp1", "approved")  # nothing un-submits


def test_editing_is_locked_after_submission(tmp_path):
    q = Queue(tmp_path / "queue.json")
    make_item(q)
    q.update_fields("fp1", letter_body="hers")
    q.transition("fp1", "approved")
    q.transition("fp1", "submitting")
    q.transition("fp1", "submitted")
    with pytest.raises(ValueError):
        q.update_fields("fp1", letter_body="too late")


def test_stale_items_expire(tmp_path):
    q = Queue(tmp_path / "queue.json")
    make_item(q)
    q.items["fp1"]["updated"] = "2020-01-01T00:00:00+00:00"
    q._save()
    assert q.expire_stale() == 1
    assert q.items["fp1"]["state"] == "expired"


def test_needs_human_paths(tmp_path):
    q = Queue(tmp_path / "queue.json")
    make_item(q)
    q.transition("fp1", "needs_human", needs="captcha")
    q.transition("fp1", "submitted", note="applied by hand")  # she did it herself
    assert q.by_state("submitted")[0]["note"] == "applied by hand"
