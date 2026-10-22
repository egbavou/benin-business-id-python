from datetime import UTC, datetime


def now() -> datetime:
    """The current time, timezone-aware, in UTC."""
    return datetime.now(UTC)


def current_year() -> int:
    """The current year in UTC, like gmdate('Y') in the PHP package."""
    return now().year
