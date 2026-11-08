"""The branch the user works in (Frappe app only)."""

from __future__ import annotations

from .. import branches, session
from .base import command


@command
def get_branches() -> dict:
    """The user's current branch and the ones they may switch to."""
    me = session.current_user()
    return {"current": branches.current(me["id"]),
            "choices": [{"name": b, **branches.facility(b)} for b in branches.allowed(me["id"])]}


@command
def set_branch(branch: str) -> None:
    me = session.current_user()
    branches.choose(me["id"], branch)
