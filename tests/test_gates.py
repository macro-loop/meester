import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from meester.score.gates import (
    MATCH_THRESHOLD,
    has_usable_preferences,
    parse_salary_max,
    score_job,
)

PREFS = {
    "titles": ["Product Designer", "UX Designer"],
    "functions": ["design"],
    "seniority": "senior",
    "salary_floor": 120000,
    "exclude_companies": ["Meta"],
    "exclude_industries": ["gambling"],
    "exclude_agencies": True,
    "dream_companies": ["Figma"],
    "moving_away_from": "agency client-services work",
}

LEDGER = {"verified": True, "skills": ["Figma", "prototyping", "design systems"]}


def job(**kw):
    base = {"title": "Senior Product Designer", "company": "Acme",
            "description": "", "salary_raw": ""}
    base.update(kw)
    return base


def test_title_and_seniority_match_clears_the_bar_with_reasons():
    v = score_job(job(), PREFS)
    assert v["match"]
    assert any("Product Designer" in r for r in v["reasons"])
    assert any("Senior" in r for r in v["reasons"])


def test_unrelated_role_does_not_match():
    v = score_job(job(title="Staff Accountant"), PREFS)
    assert not v["match"]


def test_excluded_company_is_dropped_with_her_own_words():
    v = score_job(job(company="Meta"), PREFS)
    assert v["score"] <= -900
    assert "You excluded Meta" in v["why_not"]


def test_excluded_industry_in_title_is_dropped():
    v = score_job(job(title="Senior Designer, Gambling Products"), PREFS)
    assert v["score"] <= -900


def test_agency_posting_is_dropped_when_she_said_so():
    v = score_job(job(description="On behalf of our client we are seeking..."), PREFS)
    assert v["score"] <= -900
    v2 = score_job(job(description="On behalf of our client..."),
                   {**PREFS, "exclude_agencies": False})
    assert v2["score"] > -900


def test_pay_below_floor_pushes_down_with_numbers_in_the_reason():
    v = score_job(job(salary_raw="$80K - $100K"), PREFS)
    assert any("100,000" in w and "120,000" in w for w in v["why_not"])
    good = score_job(job(salary_raw="$130K - $160K"), PREFS)
    assert any("floor" in r for r in good["reasons"])
    assert good["score"] > v["score"]


def test_unpriced_postings_are_not_punished():
    priced_ok = score_job(job(salary_raw="$130K"), PREFS)["score"]
    unpriced = score_job(job(), PREFS)["score"]
    below = score_job(job(salary_raw="$90K"), PREFS)["score"]
    assert below < unpriced < priced_ok


def test_seniority_gap_pushes_down():
    v = score_job(job(title="Director of Product Design"), PREFS)
    assert any("director" in w.lower() for w in v["why_not"])


def test_verified_skills_boost_and_unverified_do_not():
    d = "You will own our design systems and prototyping practice in Figma."
    with_ledger = score_job(job(description=d), PREFS, LEDGER)
    assert any("your CV" in r for r in with_ledger["reasons"])
    unverified = score_job(job(description=d), PREFS, {**LEDGER, "verified": False})
    assert not any("your CV" in r for r in unverified["reasons"])


def test_dream_company_is_flagged_and_boosted():
    v = score_job(job(company="Figma"), PREFS)
    assert v["dream"]
    assert any("dream" in r.lower() for r in v["reasons"])


def test_moving_away_from_pushes_down():
    v = score_job(job(title="Senior Product Designer, Agency Team"), PREFS)
    assert any("moving away" in w for w in v["why_not"])


def test_blank_profile_means_no_scoring_at_all():
    assert not has_usable_preferences({"titles": [], "functions": []})
    assert has_usable_preferences({"titles": ["X"]})


def test_salary_parsing():
    assert parse_salary_max("$218K – $300K • Offers Equity") == 300000
    assert parse_salary_max("USD 100,000 - 150,000 a year") == 150000
    assert parse_salary_max("competitive") is None
    assert parse_salary_max("$45/hour") is None, "hourly must not compare to a yearly floor"
    assert parse_salary_max("") is None


def test_threshold_is_reachable_by_title_alone():
    v = score_job({"title": "Product Designer", "company": "X", "description": "",
                   "salary_raw": ""}, {"titles": ["Product Designer"]})
    assert v["score"] >= MATCH_THRESHOLD
