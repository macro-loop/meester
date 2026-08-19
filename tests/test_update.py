"""Self-update tests. Entirely offline: 'GitHub' is a local bare repo."""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from meester.update import NEEDS_A_HUMAN, check, update


def git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True
    )
    return proc.stdout.strip()


@pytest.fixture()
def repos(tmp_path: Path) -> tuple[Path, Path]:
    """A bare 'origin' plus two clones: hers, and one to push updates from."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-q", str(origin)], check=True)

    def clone(name: str) -> Path:
        dst = tmp_path / name
        subprocess.run(["git", "clone", "-q", str(origin), str(dst)], check=True)
        git(dst, "config", "user.email", "t@t")
        git(dst, "config", "user.name", "t")
        return dst

    author = clone("author")
    (author / "file.txt").write_text("v1", encoding="utf-8")
    git(author, "add", "-A")
    git(author, "commit", "-q", "-m", "v1")
    git(author, "push", "-q", "origin", "HEAD")

    hers = clone("hers")
    return author, hers


def push_change(author: Path, content: str) -> None:
    (author / "file.txt").write_text(content, encoding="utf-8")
    git(author, "add", "-A")
    git(author, "commit", "-q", "-m", content)
    git(author, "push", "-q")


def test_up_to_date_reports_zero_behind(repos):
    _, hers = repos
    st = check(hers)
    assert st.behind == 0
    assert not st.dirty
    assert st.sha


def test_new_commit_shows_as_behind(repos):
    author, hers = repos
    push_change(author, "v2")
    assert check(hers).behind == 1


def test_update_applies_and_reports_the_sha_change(repos):
    author, hers = repos
    push_change(author, "v2")
    old = check(hers, fetch=False).sha
    result = update(hers)
    assert result["ok"] and result["changed"]
    assert result["old"] == old
    assert result["new"] != old
    assert (hers / "file.txt").read_text(encoding="utf-8") == "v2"


def test_update_when_current_is_a_clean_noop(repos):
    _, hers = repos
    result = update(hers)
    assert result["ok"] and not result["changed"]
    assert result["old"] == result["new"]


def test_local_changes_block_the_update_with_a_human_message(repos):
    """The whole design rests on her repo staying pullable; if it isn't, the
    answer must be to route it to a person, never a silent merge attempt."""
    author, hers = repos
    push_change(author, "v2")
    (hers / "file.txt").write_text("hand-edited", encoding="utf-8")
    result = update(hers)
    assert not result["ok"]
    assert NEEDS_A_HUMAN in result["error"]
    # And nothing was clobbered.
    assert (hers / "file.txt").read_text(encoding="utf-8") == "hand-edited"


def test_diverged_history_fails_softly(repos):
    author, hers = repos
    push_change(author, "v2")
    (hers / "other.txt").write_text("local", encoding="utf-8")
    git(hers, "add", "-A")
    git(hers, "commit", "-q", "-m", "local commit")
    result = update(hers)
    assert not result["ok"]
    assert NEEDS_A_HUMAN in result["error"]


def test_not_a_repo_is_an_error_not_a_crash(tmp_path):
    st = check(tmp_path)
    assert st.sha == ""
    assert st.error
    result = update(tmp_path)
    assert not result["ok"]
