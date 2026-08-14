"""Ashby signal-merge tests.

Every fixture below is a real posting shape copied from a live board, because the
bug these guard against was invisible in synthetic data: OpenAI publishes
``isRemote: true`` on hundreds of San Francisco hybrid roles.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from meester.harvest.ashby import _classify, _secondary_location_strings
from meester.models import Workplace


def classify(job: dict):
    text = "; ".join(
        [p for p in [job.get("location", ""), *_secondary_location_strings(job)] if p]
    )
    return _classify(job, text)


def test_isremote_does_not_override_hybrid_office_role():
    # OpenAI, 438 live postings in this exact shape.
    job = {"location": "San Francisco", "isRemote": True, "workplaceType": "Hybrid",
           "secondaryLocations": []}
    mode, _ = classify(job)
    assert mode == Workplace.HYBRID, "isRemote must not launder an office job into remote"


def test_remote_secondary_location_makes_it_remote():
    # Ramp: primary is the HQ, the remote option hides in the secondaries.
    job = {
        "location": "New York, NY (HQ)",
        "isRemote": True,
        "workplaceType": "Hybrid",
        "secondaryLocations": [
            {"location": "Remote (Canada)", "address": {"postalAddress": {"addressCountry": "Canada"}}},
            {"location": "Remote (US)", "address": {"postalAddress": {"addressCountry": "United States"}}},
        ],
    }
    mode, countries = classify(job)
    assert mode == Workplace.REMOTE
    assert {"US", "CA"} <= countries


def test_declared_remote_workplace_type_is_trusted():
    job = {"location": "US - Remote", "isRemote": True, "workplaceType": "Remote",
           "secondaryLocations": [{"location": "Seattle"}]}
    mode, countries = classify(job)
    assert mode == Workplace.REMOTE
    assert "US" in countries


def test_onsite_stays_onsite():
    job = {"location": "San Francisco", "isRemote": False, "workplaceType": "OnSite",
           "secondaryLocations": []}
    mode, _ = classify(job)
    assert mode == Workplace.ONSITE


def test_bare_isremote_with_no_location_is_trusted():
    # Nothing to contradict the boolean, so it is the only signal available.
    job = {"location": "", "isRemote": True, "workplaceType": None, "secondaryLocations": []}
    mode, _ = classify(job)
    assert mode == Workplace.REMOTE


def test_missing_signals_are_not_remote():
    job = {"location": "London", "isRemote": None, "workplaceType": None,
           "secondaryLocations": []}
    mode, _ = classify(job)
    assert mode == Workplace.ONSITE
