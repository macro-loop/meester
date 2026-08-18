"""The one gateway to the Anthropic API.

Raw Messages API over httpx - no SDK dependency. Everything LLM-flavoured in
Meester goes through call_json(), which gives three properties in one place:

  * feature-flagging: no key on disk means available() is False and every
    caller degrades to its stated keyless behaviour, never a broken screen
  * a spend guard: a per-day call cap in settings, so a bug that loops can
    cost at most one day's cap, not a month of surprise billing
  * strict JSON out: the model is asked for JSON only, and one repair retry
    is attempted before giving up

The key lives in profile/api_key - gitignored, covered by the pre-push
personal-file guard, chmod 600 where the OS supports it.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import date
from pathlib import Path

import httpx

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"

# Cheap model for classification, strong model for judging and writing.
MODEL_FAST = "claude-haiku-4-5-20251001"
MODEL_STRONG = "claude-sonnet-5"

DEFAULT_DAILY_CAP = 300


class LLMUnavailable(RuntimeError):
    """No key configured. Callers catch this and take their keyless path."""


class LLMBudgetExceeded(RuntimeError):
    """Today's call cap is spent. Protects against loops, not against use."""


def key_path(profile_dir: Path) -> Path:
    return profile_dir / "api_key"


def load_key(profile_dir: Path) -> str:
    try:
        return key_path(profile_dir).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def save_key(profile_dir: Path, key: str | None) -> None:
    path = key_path(profile_dir)
    if not key:
        path.unlink(missing_ok=True)
        return
    profile_dir.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(key.strip(), encoding="utf-8")
    tmp.replace(path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # Windows dev box; on her Mac this succeeds


def looks_like_key(key: str) -> bool:
    return bool(re.fullmatch(r"sk-ant-[A-Za-z0-9_-]{20,200}", key.strip()))


def available(profile_dir: Path) -> bool:
    return bool(load_key(profile_dir))


class LLM:
    def __init__(self, profile_dir: Path, data_dir: Path, daily_cap: int = DEFAULT_DAILY_CAP):
        self.profile_dir = profile_dir
        self.spend_path = data_dir / "llm_spend.json"
        self.daily_cap = daily_cap

    # --- spend guard ------------------------------------------------------------

    def _spend(self) -> dict:
        try:
            raw = json.loads(self.spend_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return raw
        except (OSError, json.JSONDecodeError):
            pass
        return {}

    def calls_today(self) -> int:
        return int(self._spend().get(date.today().isoformat(), 0))

    def _count_call(self) -> None:
        today = date.today().isoformat()
        spend = {today: self._spend().get(today, 0) + 1}  # old days pruned
        self.spend_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.spend_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(spend), encoding="utf-8")
        tmp.replace(self.spend_path)

    # --- the call ---------------------------------------------------------------

    def call_json(
        self,
        prompt: str,
        system: str = "",
        model: str = MODEL_FAST,
        max_tokens: int = 1000,
    ) -> dict:
        """One prompt in, one parsed JSON object out."""
        key = load_key(self.profile_dir)
        if not key:
            raise LLMUnavailable("no API key configured")
        if self.calls_today() >= self.daily_cap:
            raise LLMBudgetExceeded(f"daily cap of {self.daily_cap} calls reached")

        body = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system + "\nRespond with a single JSON object and nothing else."

        text = self._post(key, body)
        try:
            return self._parse(text)
        except ValueError:
            # One repair attempt: show the model its own output.
            self._count_call()  # the repair bills too; count it against the cap
            repair = self._post(key, {
                "model": MODEL_FAST,
                "max_tokens": max_tokens,
                "messages": [{
                    "role": "user",
                    "content": "Extract the single JSON object from this text, "
                    "fixing any syntax errors. Reply with the JSON only.\n\n" + text[:6000],
                }],
            })
            return self._parse(repair)

    def _post(self, key: str, body: dict) -> str:
        self._count_call()
        last_err: Exception | None = None
        for attempt in range(2):
            try:
                resp = httpx.post(
                    API_URL,
                    json=body,
                    headers={"x-api-key": key, "anthropic-version": API_VERSION},
                    timeout=90,
                )
                if resp.status_code in (429, 500, 502, 503, 529):
                    time.sleep(3 * (attempt + 1))
                    last_err = RuntimeError(f"API {resp.status_code}")
                    continue
                resp.raise_for_status()
                data = resp.json()
                return "".join(
                    block.get("text", "") for block in data.get("content", [])
                )
            except httpx.HTTPError as exc:
                last_err = exc
                time.sleep(2)
        raise RuntimeError(f"Anthropic API call failed: {last_err}")

    @staticmethod
    def _parse(text: str) -> dict:
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("no JSON object in response")
        parsed = json.loads(text[start : end + 1])
        if not isinstance(parsed, dict):
            raise ValueError("expected a JSON object")
        return parsed
