"""The branch's print queue."""

from __future__ import annotations

from rxlabel_core import queue_rules

from .. import branches, checks, licensing, prefs, printqueue, session
from .base import command


def _branch() -> str:
    return branches.current(session.require()["id"])


@command
def get_queue() -> list[dict]:
    branch = _branch()
    keep = prefs.get("queue_keep_days", branch, queue_rules.DEFAULT_QUEUE_KEEP_DAYS)
    printqueue.purge_older_than(branch, int(keep or 0))
    return printqueue.items(branch)


@command
def check_queue_room(adding: int) -> None:
    branch = _branch()
    queue_rules.check_room(printqueue.count(branch), max(0, checks.ident(adding, "count")),
                           printqueue.limit(branch), False)


@command
def add_to_queue(product: str, instructions: str | None = None, warning: str | None = None,
                 client: str | None = None, make_room: bool | None = False) -> None:
    branch = _branch()
    licensing.require_active()
    product = checks.text(product, "Product", required=True)
    instructions = checks.long_text(instructions, "Instructions")
    warning = checks.long_text(warning, "Warning")
    client = checks.text(client, "Client")
    limit = printqueue.limit(branch)
    queue_rules.check_room(printqueue.count(branch), 1, limit, checks.flag(make_room))
    printqueue.add(branch, product, instructions, warning, client)
    printqueue.trim(branch, limit)


@command
def remove_from_queue(id: int) -> None:
    branch = _branch()
    licensing.require_active()
    printqueue.remove(branch, [checks.ident(id)])


@command
def count_queue() -> int:
    return printqueue.count(_branch())


@command
def clear_queue() -> None:
    branch = _branch()
    licensing.require_active()
    printqueue.clear(branch)
