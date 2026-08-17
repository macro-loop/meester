"""Self-update: check for and apply new commits from GitHub.

Every git invocation here is a fixed argv list - no user input ever reaches a
command line, so there is no injection surface. The one subtle part is that the
process applying the update is running the old code; the server handles that by
exiting after a successful pull and letting launchd's KeepAlive restart it on
the new version (the same problem run_harvest.sh solves with a re-exec).
"""

from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


def _git(repo: Path, *args: str, timeout: float = 20.0) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return 127, "", "git is not installed"
    except subprocess.TimeoutExpired:
        return 124, "", f"git {args[0]} timed out"
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


@dataclass
class RepoStatus:
    sha: str = ""
    behind: int | None = None  # None = could not check (offline, no upstream, ...)
    dirty: bool = False
    error: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def check(repo: Path, fetch: bool = True) -> RepoStatus:
    """Where this machine stands relative to GitHub. Read-only."""
    st = RepoStatus()

    rc, out, err = _git(repo, "rev-parse", "--short", "HEAD")
    if rc != 0:
        st.error = err or "not a git repository"
        return st
    st.sha = out

    rc, out, _ = _git(repo, "status", "--porcelain")
    st.dirty = rc == 0 and bool(out)

    if fetch:
        rc, _, err = _git(repo, "fetch", "--quiet", timeout=30)
        if rc != 0:
            # Offline is a normal state for a laptop; report it as "couldn't
            # check", never as "up to date".
            st.error = "couldn't reach GitHub to check for updates"
            return st

    rc, out, err = _git(repo, "rev-list", "--count", "HEAD..@{u}")
    if rc != 0:
        st.error = err or "no upstream configured"
        return st
    try:
        st.behind = int(out)
    except ValueError:
        st.error = "unexpected git output"
    return st


def update(repo: Path) -> dict:
    """Apply whatever is on GitHub. Fast-forward only, never merges.

    Failure messages are written for her, not for a developer: a state that
    needs a human is reported as exactly that.
    """
    st = check(repo, fetch=True)
    if not st.sha:
        return {"ok": False, "error": st.error or "this doesn't look like a git checkout"}
    if st.error and st.behind is None:
        return {"ok": False, "error": st.error}
    if st.dirty:
        return {
            "ok": False,
            "error": "files on this machine have local changes, so updating "
            "automatically isn't safe - tell William",
        }
    if st.behind == 0:
        return {"ok": True, "changed": False, "old": st.sha, "new": st.sha}

    rc, _, err = _git(repo, "pull", "--ff-only", "--quiet", timeout=60)
    if rc != 0:
        return {
            "ok": False,
            "error": "the update couldn't be applied automatically - tell William",
            "detail": err[-400:],
        }

    rc, new_sha, _ = _git(repo, "rev-parse", "--short", "HEAD")
    return {
        "ok": True,
        "changed": new_sha != st.sha,
        "old": st.sha,
        "new": new_sha if rc == 0 else "",
    }
