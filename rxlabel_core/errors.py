"""Errors the frontend understands (src/ipc/bindings/ErrorCode.ts).

`message` is always safe to show to the person using the app: it never
contains label text, client names or anything typed at sign-in.
"""

# HTTP status for each code; the frontend reads `code`, the status is for
# logs and proxies (Frappe uses the same idea with its exception classes).
STATUS = {
    "UNAUTHORIZED": 401,
    "FORBIDDEN": 403,
    "NOT_FOUND": 404,
    "VALIDATION": 417,
    "CONFLICT": 409,
    "INVALID_CREDENTIALS": 401,
    "RATE_LIMITED": 429,
    "LICENSE_INVALID": 403,
    "LICENSE_EXPIRED": 403,
    "INVALID_PATTERN": 417,
    "QUEUE_FULL": 409,
    "PRINT_ASSISTANT_UNAVAILABLE": 503,
    "NO_PRINTER": 503,
    "PRINT_FAILED": 500,
    "PRINTER": 500,
    "DATABASE": 500,
    "INTERNAL": 500,
}


class AppError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    @property
    def status(self) -> int:
        return STATUS.get(self.code, 500)

    def to_json(self) -> dict:
        return {"exc_type": "RxLabelError", "code": self.code, "message": self.message}


def validation(message: str) -> AppError:
    return AppError("VALIDATION", message)


def forbidden(message: str = "You don't have permission to do that.") -> AppError:
    return AppError("FORBIDDEN", message)


def not_found(message: str = "Not found.") -> AppError:
    return AppError("NOT_FOUND", message)


def unavailable(feature: str) -> AppError:
    """For features this version doesn't have yet."""
    return AppError("NOT_FOUND", f"{feature} is not available in this version yet.")


def unique_message(field: str) -> str:
    """For a UNIQUE constraint on `table.column` (error.rs unique_message)."""
    return {
        "users.name": "A user with this username already exists.",
        "users.email": "A user with this email already exists.",
        "clients.name": "A client with this name already exists.",
    }.get(field, f"This value already exists ({field}).")
