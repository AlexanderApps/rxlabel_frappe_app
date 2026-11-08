"""Who may do what (session.rs, commands/settings.rs) and sign-in throttling."""

from __future__ import annotations

import time

from .errors import AppError

ADMIN, MANAGER, USER = "admin", "manager", "user"
ANY = (ADMIN, MANAGER, USER)
STAFF = (ADMIN, MANAGER)
ADMINS = (ADMIN,)

MIN_PASSWORD_LEN, MAX_PASSWORD_LEN = 8, 128

IDLE_TIMEOUT_KEY = "idle_timeout_minutes"
DEFAULT_IDLE_TIMEOUT_MINUTES = 8 * 60
MIN_IDLE_TIMEOUT_MINUTES, MAX_IDLE_TIMEOUT_MINUTES = 1, 24 * 60

THEMES = ("dark", "light", "system")

# Aux settings any signed-in user may write / only an admin may write.
USER_AUX_KEYS = frozenset({
    "printer_model", "label_template", "print_type", "queue_remove_after_print", "show_copies",
    "printer_status_sound", "preview_before_print", "show_preview_button",
    "label_search_all_words", "label_search_fuzzy", "label_search_patterns",
})
ADMIN_AUX_KEYS = frozenset({
    "last_optimization", IDLE_TIMEOUT_KEY, "queue_keep_days", "print_calibration", "label_settings",
})

# Facility fields only an admin may change.
ADMIN_SETTINGS_FIELDS = ("facility_name", "facility_address", "facility_contact", "queue_size")


def is_internal_aux_key(key: str) -> bool:
    """Backup bookkeeping: never writable, hidden from non-admins."""
    return key.startswith("backup_")


def idle_minutes(saved: object) -> int:
    try:
        return max(MIN_IDLE_TIMEOUT_MINUTES, min(MAX_IDLE_TIMEOUT_MINUTES, int(saved)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return DEFAULT_IDLE_TIMEOUT_MINUTES


def validate_new_password(password: object) -> None:
    """A new password chosen by a person (session::validate_new_password)."""
    text = password if isinstance(password, str) else ""
    if not text.strip() or len(text) < MIN_PASSWORD_LEN:
        raise AppError("VALIDATION", f"Password must be at least {MIN_PASSWORD_LEN} characters")
    if len(text) > MAX_PASSWORD_LEN:
        raise AppError("VALIDATION", f"Password must be at most {MAX_PASSWORD_LEN} characters")


# --- Managing accounts (commands/users.rs rules) --------------------------------
# The admin account comes from the licence and is never managed here, so there
# is always exactly one admin.

ROLES = (ADMIN, MANAGER, USER)


def can_manage(actor: str, target: str) -> bool:
    """Whether `actor` may create, edit or delete an account that has (or will have) `target` role."""
    return (actor, target) in {(ADMIN, MANAGER), (ADMIN, USER), (MANAGER, USER)}


def parse_role(role: object) -> str:
    if role not in ROLES:
        raise AppError("VALIDATION", f"Invalid role '{role}'")
    return role  # type: ignore[return-value]


def check_create(actor: str, new: str) -> None:
    if not can_manage(actor, new):
        raise AppError("FORBIDDEN", f"A {actor} cannot create a {new} account")


def check_update(actor: str, current: str, new: str) -> None:
    """Both the account's current role and its new role must be manageable."""
    if not (can_manage(actor, current) and can_manage(actor, new)):
        raise AppError("FORBIDDEN", f"A {actor} cannot edit this account or assign the {new} role")


def check_delete(actor_id: int, actor: str, target_id: int, target: str) -> None:
    if actor_id == target_id:
        raise AppError("FORBIDDEN", "You cannot delete your own account")
    if not can_manage(actor, target):
        raise AppError("FORBIDDEN", f"A {actor} cannot delete a {target} account")


class LoginThrottle:
    """Five free attempts per client, then growing lockouts (30 s, 60 s, ... 15 min)."""

    FREE_ATTEMPTS = 5

    def __init__(self) -> None:
        self._state: dict[str, dict] = {}

    def check(self, key: str, now: float | None = None) -> float:
        """Seconds still locked out (0: may try)."""
        now = time.time() if now is None else now
        s = self._state.get(key)
        return max(0.0, s["locked_until"] - now) if s else 0.0

    def failure(self, key: str, now: float | None = None) -> float:
        """Record a failure; returns the lockout it starts (0: none)."""
        now = time.time() if now is None else now
        s = self._state.setdefault(key, {"failures": 0, "lockouts": 0, "locked_until": 0.0})
        s["failures"] += 1
        if s["failures"] < self.FREE_ATTEMPTS:
            return 0.0
        wait = min(30 * 2 ** s["lockouts"], 15 * 60)
        s.update(failures=0, lockouts=s["lockouts"] + 1, locked_until=now + wait)
        return float(wait)

    def remaining(self, key: str) -> int:
        s = self._state.get(key)
        return self.FREE_ATTEMPTS - (s["failures"] if s else 0)

    def success(self, key: str) -> None:
        self._state.pop(key, None)


def invalid_credentials_message(remaining: int) -> str:
    message = "Invalid username or password."
    if remaining <= 2:
        message += f" {remaining} attempt(s) left before a temporary lockout."
    return message
