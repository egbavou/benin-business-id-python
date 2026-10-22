import re
from typing import Final

# What PCRE2's `\s` matches with PHP's `u` modifier: exactly `\h` and `\v`. Python's own `\s`
# differs (it matches U+001C-U+001F but not U+180E), so the set is spelled out.
PCRE_SPACE_CODE_POINTS: Final = (
    0x0009,
    0x000A,
    0x000B,
    0x000C,
    0x000D,
    0x0020,
    0x0085,
    0x00A0,
    0x1680,
    0x180E,
    *range(0x2000, 0x200B),
    0x2028,
    0x2029,
    0x202F,
    0x205F,
    0x3000,
)
# The same set, as the contents of a regular expression character class.
PCRE_SPACE: Final = "".join(f"\\U{code_point:08X}" for code_point in PCRE_SPACE_CODE_POINTS)

_SEPARATORS: Final = re.compile(f"[{PCRE_SPACE}.\\-]+")
_ASCII_UPPER: Final = str.maketrans("abcdefghijklmnopqrstuvwxyz", "ABCDEFGHIJKLMNOPQRSTUVWXYZ")
_ASCII_LOWER: Final = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")


def as_text(value: object, name: str) -> str:
    """Return value as an exact str, without calling methods a str subclass may override."""
    if not isinstance(value, str):
        raise TypeError(f"{name} expects a str, not {type(value).__name__}")

    return str.__str__(value)


def remove_separators(value: str) -> str:
    """Remove spaces (PCRE's set), dots and hyphens, like the PHP package."""
    return _SEPARATORS.sub("", value)


def ascii_upper(value: str) -> str:
    """Uppercase ASCII letters only, like PHP 8.2+ strtoupper()."""
    return value.translate(_ASCII_UPPER)


def ascii_lower(value: str) -> str:
    """Lowercase ASCII letters only, like PHP 8.2+ strtolower()."""
    return value.translate(_ASCII_LOWER)
