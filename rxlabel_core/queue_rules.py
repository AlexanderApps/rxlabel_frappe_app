"""Queue limits (db/queue_limits.rs, commands/queue.rs)."""

from __future__ import annotations

from .errors import AppError

DEFAULT_QUEUE_SIZE = 100
DEFAULT_QUEUE_KEEP_DAYS = 30


def overflow(count: int, adding: int, limit: int) -> int:
    """How many of the oldest items adding would drop (0: it fits)."""
    return max(0, min(count, count + adding - max(1, limit)))


def _labels(n: int) -> str:
    return "1 label" if n == 1 else f"{n} labels"


def check_room(count: int, adding: int, limit: int, make_room: bool) -> None:
    """QUEUE_FULL (saying what would be dropped) unless it fits or `make_room`."""
    drop = overflow(count, adding, limit)
    if drop and not make_room:
        raise AppError(
            "QUEUE_FULL",
            f"The queue holds up to {_labels(limit)} and has {count}. "
            f"Adding {_labels(adding)} will remove the {drop} oldest.",
        )
