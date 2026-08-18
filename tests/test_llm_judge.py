"""LLM gateway + judge tests. Entirely offline: the API is monkeypatched."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from meester.llm import LLM, LLMBudgetExceeded, LLMUnavailable, looks_like_key, save_key
from meester.score.judge import (
    cache_key,
    judge_survivors,
    judged_for_report,
    load_cache,
    prefs_hash,
)

PREFS = {"titles": ["Product Designer"], "functions": ["design"], "seniority": "senior"}
LEDGER = {"verified": True, "saved_at": "2026-08-17T00:00:00",
          "employment": [{"employer": "Acme", "title": "Designer",
                          "start": "2020", "end": "now", "bullets": ["did a redesign"]}],
          "skills": ["Figma"]}


def job(fp="fp1", title="Senior Product Designer"):
    return {"fingerprint": fp, "title": title, "company": "X",
            "description": "design systems", "salary_raw": ""}


class FakeResponse:
    status_code = 200

    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return {"content": [{"type": "text", "text": json.dumps(self._payload)}]}


@pytest.fixture()
def llm(tmp_path, monkeypatch):
    """Patched at the httpx boundary, so _post's own call-counting runs -
    an earlier version patched _post itself and the cap test silently tested
    nothing."""
    inst = LLM(tmp_path / "profile", tmp_path / "data", daily_cap=10)
    save_key(tmp_path / "profile", "sk-ant-" + "a" * 30)
    calls = {"n": 0}

    def fake_post(url, json=None, headers=None, timeout=None):
        calls["n"] += 1
        return FakeResponse({"fit": 77,
                             "evidence": ["her redesign ~ their design systems"],
                             "gaps": ["management"]})

    import meester.llm as llm_mod

    monkeypatch.setattr(llm_mod.httpx, "post", fake_post)
    inst._calls = calls
    return inst


def test_key_format_validation():
    assert looks_like_key("sk-ant-" + "x" * 30)
    assert not looks_like_key("sk-proj-openai-style")
    assert not looks_like_key("sk-ant-short")
    assert not looks_like_key("")


def test_no_key_raises_unavailable(tmp_path):
    inst = LLM(tmp_path / "profile", tmp_path / "data")
    with pytest.raises(LLMUnavailable):
        inst.call_json("hi")


def test_daily_cap_is_a_hard_stop(tmp_path, monkeypatch):
    inst = LLM(tmp_path / "profile", tmp_path / "data", daily_cap=2)
    save_key(tmp_path / "profile", "sk-ant-" + "a" * 30)
    import meester.llm as llm_mod

    monkeypatch.setattr(
        llm_mod.httpx, "post",
        lambda url, json=None, headers=None, timeout=None: FakeResponse({"ok": 1}),
    )
    inst.call_json("one")
    inst.call_json("two")
    with pytest.raises(LLMBudgetExceeded):
        inst.call_json("three")
    assert inst.calls_today() == 2


def test_judge_caches_and_never_rebills(tmp_path, llm):
    cache = tmp_path / "judge_cache.jsonl"
    rows = [job("fp1"), job("fp2")]

    first = judge_survivors(rows, PREFS, LEDGER, cache, llm)
    assert set(first) == {"fp1", "fp2"}
    assert first["fp1"]["fit"] == 77
    billed = llm._calls["n"]

    second = judge_survivors(rows, PREFS, LEDGER, cache, llm)
    assert set(second) == {"fp1", "fp2"}
    assert llm._calls["n"] == billed, "a second pass over cached jobs must bill zero"

    # Render-time lookup is cache-only.
    assert judged_for_report(rows, PREFS, LEDGER, cache)["fp2"]["fit"] == 77


def test_prefs_change_invalidates_but_cosmetic_change_does_not():
    base = prefs_hash(PREFS)
    assert prefs_hash({**PREFS, "titles": ["Architect"]}) != base
    assert prefs_hash({**PREFS, "notice_period_weeks": 12}) == base
    key1 = cache_key("fp", PREFS, LEDGER)
    key2 = cache_key("fp", PREFS, {**LEDGER, "saved_at": "2026-09-01"})
    assert key1 != key2, "a re-verified ledger must re-judge"


def test_unverified_ledger_means_no_judging(tmp_path, llm):
    cache = tmp_path / "judge_cache.jsonl"
    out = judge_survivors([job()], PREFS, {**LEDGER, "verified": False}, cache, llm)
    assert out == {}
    assert llm._calls["n"] == 0, "judging against an unchecked history is confident nonsense"


def test_non_matching_jobs_are_never_sent_to_the_model(tmp_path, llm):
    cache = tmp_path / "judge_cache.jsonl"
    judge_survivors([job("fp9", title="Staff Accountant")], PREFS, LEDGER, cache, llm)
    assert llm._calls["n"] == 0


def test_corrupt_cache_lines_are_skipped(tmp_path):
    cache = tmp_path / "judge_cache.jsonl"
    cache.write_text('{"k": "good", "fit": 50}\n{broken\n', encoding="utf-8")
    assert "good" in load_cache(cache)
