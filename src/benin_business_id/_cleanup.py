import re
from typing import Final


def _character_class(code_points: tuple[int, ...]) -> str:
    """The contents of a regular expression character class matching these code points."""
    return "".join(f"\\U{code_point:08X}" for code_point in code_points)


# Separators removed from an identifier, like the PHP package's shared cleanup pattern
# /[\p{Z}\x{0009}-\x{000D}\x{0085}.\-]+/u (decision D37). Category Z is spelled out rather than
# read from unicodedata, whose Unicode version varies with the interpreter. Python's `\s` and
# str.isspace() differ: they also match U+001C-U+001F.
SEPARATOR_CODE_POINTS: Final = (
    *range(0x0009, 0x000E),
    0x0020,
    0x0085,
    0x00A0,
    0x1680,
    *range(0x2000, 0x200B),
    0x2028,
    0x2029,
    0x202F,
    0x205F,
    0x3000,
)

# What PCRE2's `\s` matches with PHP's `u` modifier: exactly `\h` and `\v`, which unlike the
# separators above include U+180E. The PHP package still uses `\s` in the pattern that reads a
# former number from an APIEx record, so the Python port does too.
PCRE_SPACE_CODE_POINTS: Final = (*SEPARATOR_CODE_POINTS, 0x180E)
PCRE_SPACE: Final = _character_class(PCRE_SPACE_CODE_POINTS)

_SEPARATORS: Final = re.compile(f"[{_character_class(SEPARATOR_CODE_POINTS)}.\\-]+")
_ASCII_UPPER: Final = str.maketrans("abcdefghijklmnopqrstuvwxyz", "ABCDEFGHIJKLMNOPQRSTUVWXYZ")
_ASCII_LOWER: Final = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")


def as_text(value: object, name: str) -> str:
    """Return value as an exact str, without calling methods a str subclass may override."""
    if not isinstance(value, str):
        raise TypeError(f"{name} expects a str, not {type(value).__name__}")

    return str.__str__(value)


def remove_separators(value: str) -> str:
    """Remove separators (see SEPARATOR_CODE_POINTS), dots and hyphens, like the PHP package."""
    return _SEPARATORS.sub("", value)


def ascii_upper(value: str) -> str:
    """Uppercase ASCII letters only, like PHP 8.2+ strtoupper()."""
    return value.translate(_ASCII_UPPER)


def ascii_lower(value: str) -> str:
    """Lowercase ASCII letters only, like PHP 8.2+ strtolower()."""
    return value.translate(_ASCII_LOWER)
