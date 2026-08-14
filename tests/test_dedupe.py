import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from meester.dedupe import dedupe
from meester.models import Job, Workplace, normalize_company, normalize_title


def make(**kw) -> Job:
    base = dict(
        source="greenhouse",
        company="Stripe",
        company_token="stripe",
        external_id="1",
        title="Senior Software Engineer",
        url="https://example.com/1",
        workplace=Workplace.REMOTE,
    )
    base.update(kw)
    return Job(**base)


def test_company_normalisation_collapses_legal_suffixes():
    assert normalize_company("Stripe, Inc.") == normalize_company("stripe")
    assert normalize_company("Acme Technologies Ltd") == normalize_company("Acme")


def test_title_normalisation_strips_decorations():
    assert normalize_title("Backend Engineer (Remote)") == "backend engineer"
    assert normalize_title("Backend Engineer [R-12345]") == "backend engineer"
    assert normalize_title("Backend Engineer - Remote, US") == "backend engineer"
    # Two decorations at once must both come off.
    assert normalize_title("Backend Engineer (Remote) [R-9]") == "backend engineer"


def test_same_role_from_two_sources_collapses_to_one():
    a = make(source="greenhouse", description="full text here", apply_url="https://gh/apply")
    b = make(source="remoteok", external_id="2", url="https://rok/2", description="")
    out = dedupe([a, b])
    assert len(out) == 1
    # The company's own board wins, because it carries the real apply URL.
    assert out[0].source == "greenhouse"


def test_merge_fills_gaps_from_the_discarded_record():
    a = make(source="greenhouse", description="", salary_raw="")
    b = make(source="remoteok", external_id="2", description="body", salary_raw="$200k")
    out = dedupe([a, b])
    assert len(out) == 1
    assert out[0].description == "body"
    assert out[0].salary_raw == "$200k"


def test_near_identical_titles_collapse():
    a = make(title="Senior Software Engineer, Backend")
    b = make(title="Senior Software Engineer - Backend", external_id="2")
    assert len(dedupe([a, b])) == 1


def test_same_board_postings_do_not_invent_a_combined_location_set():
    """The Datadog bug: one title posted once per city on a single board is not
    one role open in every city. Unioning produced {CH,DE,FR,GB,IE} on a posting
    whose location was 'Lisbon, Portugal' - a country set matching no posting."""
    lisbon = make(source="greenhouse", title="Software Engineer",
                  locations=["Lisbon, Portugal"], remote_countries=["PT"])
    dublin = make(source="greenhouse", title="Software Engineer", external_id="2",
                  locations=["Dublin, Ireland"], remote_countries=["IE"])
    out = dedupe([lisbon, dublin])
    assert len(out) == 1
    assert set(out[0].remote_countries) in ({"PT"}, {"IE"}), (
        "same-board dedupe must not union geography across separate postings"
    )


def test_identical_fingerprint_does_union_geography():
    # Same role, two sources, each seeing a different slice of its locations.
    a = make(source="greenhouse", remote_countries=["US"], locations=["Remote, US"])
    b = make(source="ashby", external_id="2", remote_countries=["CA"],
             locations=["Remote, Canada"])
    out = dedupe([a, b])
    assert len(out) == 1
    assert set(out[0].remote_countries) == {"US", "CA"}


def test_different_workplace_modes_stay_separate():
    remote = make(title="Data Analyst", workplace=Workplace.REMOTE)
    onsite = make(title="Data Analyst", external_id="2", workplace=Workplace.ONSITE)
    assert len(dedupe([remote, onsite])) == 2


def test_age_days_handles_naive_and_missing_timestamps():
    assert make().age_days() is None
    j = make(posted_at=datetime.now(timezone.utc))
    assert j.age_days() < 1
