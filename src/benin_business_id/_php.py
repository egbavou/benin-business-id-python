"""Reproductions of the PHP behaviours the PHP package relies on, checked against PHP 8.5."""

import json
import math
import re
from collections.abc import Mapping
from typing import Final

from benin_business_id._cleanup import ascii_lower

_TRIM_CHARACTERS: Final = " \t\n\r\0\x0b"
# json_decode($json, depth: 512) accepts at most 511 nested arrays or objects.
_MAX_JSON_DEPTH: Final = 511
_INT64_MIN: Final = -(2**63)
_INT64_MAX: Final = 2**63 - 1
_SURROGATE: Final = re.compile("[\ud800-\udfff]")
_QUOTED: Final = re.compile(r"(['\"])(.*)\1")
_BOOL_WHITESPACE: Final = " \t\n\r\x0b"
_NUMERIC_WHITESPACE: Final = " \t\n\r\x0b\x0c"
_NUMERIC: Final = re.compile(
    r"[ \t\n\r\x0b\x0c]*[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?[ \t\n\r\x0b\x0c]*"
)


class JsonDecodeError(ValueError):
    """A body that PHP's json_decode() rejects while Python's json module accepts it."""


def trim(value: str) -> str:
    """trim() with its default character list.

    str.strip is called on the str type, so that a str subclass cannot override it.
    """
    return str.strip(value, _TRIM_CHARACTERS)


def float_to_string(value: float) -> str:
    """(string) $float with PHP's default precision of 14 significant digits.

    PHP's zend_dtoa keeps a trailing zero in rare exact ties at the 15th digit; that case
    is not reproduced.
    """
    if math.isnan(value):
        return "NAN"

    if math.isinf(value):
        return "INF" if value > 0 else "-INF"

    text = format(value, ".14G")
    mantissa, separator, exponent = text.partition("E")

    if not separator:
        return text

    if "." not in mantissa:
        mantissa += ".0"

    power = int(exponent)

    return f"{mantissa}E{'+' if power >= 0 else '-'}{abs(power)}"


class _Object(dict[str, object]):
    """A decoded JSON object that also keeps every pair, duplicate keys included."""

    __slots__ = ("pairs",)

    def __init__(self, pairs: list[tuple[str, object]]) -> None:
        super().__init__(pairs)
        self.pairs = pairs


def json_decode(body: bytes) -> object:
    """json_decode($body, false, 512, JSON_THROW_ON_ERROR), with objects as dicts.

    PHP validates the whole document, including values that a duplicate key later
    overwrites, so the checks walk every pair. The walk is iterative: a valid document can
    nest 511 levels deep.
    """
    tree = json.loads(
        body.decode("utf-8"),
        object_pairs_hook=_Object,
        parse_constant=_reject_constant,
        parse_int=_parse_int,
    )
    pending: list[tuple[object, int]] = [(tree, 0)]

    while pending:
        node, depth = pending.pop()

        if isinstance(node, _Object):
            _check_depth(depth)

            for key, value in node.pairs:
                _check_string(key)

                if key.startswith("\0"):
                    raise JsonDecodeError("The decoded property name is invalid.")

                pending.append((value, depth + 1))
        elif isinstance(node, list):
            _check_depth(depth)
            pending.extend((item, depth + 1) for item in node)
        elif isinstance(node, str):
            _check_string(node)

    return tree


def _reject_constant(name: str) -> object:
    raise JsonDecodeError(f"Syntax error: {name} is not valid JSON.")


def _parse_int(token: str) -> int | float:
    # Integers beyond the signed 64-bit range become floats in PHP. Long tokens go straight
    # to float(), which has no digit limit, unlike int().
    if len(token.lstrip("-")) > 19:
        return float(token)

    number = int(token)

    return number if _INT64_MIN <= number <= _INT64_MAX else float(token)


def _check_depth(depth: int) -> None:
    if depth >= _MAX_JSON_DEPTH:
        raise JsonDecodeError("Maximum stack depth exceeded.")


def _check_string(value: str) -> None:
    if _SURROGATE.search(value):
        raise JsonDecodeError("Single unpaired UTF-16 surrogate in unicode escape.")


def env_value(environ: Mapping[str, str], key: str, default: object) -> object:
    """Laravel's env($key, $default) on an environment mapping."""
    if key not in environ:
        return default

    value = environ[key]
    lowered = ascii_lower(value)

    if lowered in ("true", "(true)"):
        return True

    if lowered in ("false", "(false)"):
        return False

    if lowered in ("empty", "(empty)"):
        return ""

    if lowered in ("null", "(null)"):
        return None

    quoted = _QUOTED.fullmatch(value)

    return quoted.group(2) if quoted else value


def filter_bool(value: object) -> bool:
    """filter_var($value, FILTER_VALIDATE_BOOL, FILTER_NULL_ON_FAILURE) ?? false."""
    if isinstance(value, bool):
        return value

    if isinstance(value, int):
        text = str(value)
    elif isinstance(value, float):
        text = float_to_string(value)
    elif isinstance(value, str):
        text = value
    else:
        return False

    return ascii_lower(text.strip(_BOOL_WHITESPACE)) in ("1", "true", "on", "yes")


def numeric_value(value: object) -> float | None:
    """(float) $value when is_numeric($value) holds, else None.

    Covers the scalar types a configuration can hold.
    """
    if isinstance(value, bool):
        return None

    if isinstance(value, str):
        if _NUMERIC.fullmatch(value) is None:
            return None

        return float(value.strip(_NUMERIC_WHITESPACE))

    if isinstance(value, float):
        return value

    if isinstance(value, int):
        try:
            return float(value)
        except OverflowError:
            return math.inf if value > 0 else -math.inf

    return None
