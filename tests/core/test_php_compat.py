"""PHP behaviours reproduced by the package. Expected values were checked on PHP 8.5."""

import math

import pytest

from benin_business_id import _php

NBSP = chr(0x00A0)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (f" \t\n\r\0\x0b{NBSP}x{NBSP}\0 ", f"{NBSP}x{NBSP}"),
        ("\x0c x \x0c", "\x0c x \x0c"),
        ("\x1c x", "\x1c x"),
    ],
)
def test_trims_only_the_php_trim_characters(value: str, expected: str) -> None:
    assert _php.trim(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (12.5, "12.5"),
        (1.0, "1"),
        (0.0, "0"),
        (-0.0, "-0"),
        (0.1 + 0.2, "0.3"),
        (1e20, "1.0E+20"),
        (1e15, "1.0E+15"),
        (1e14, "1.0E+14"),
        (1e13, "10000000000000"),
        (123456789012345.0, "1.2345678901234E+14"),
        (1e-7, "1.0E-7"),
        (1e-5, "1.0E-5"),
        (0.0001, "0.0001"),
        (1.5e300, "1.5E+300"),
        (100000.0, "100000"),
        (math.inf, "INF"),
        (-math.inf, "-INF"),
        (math.nan, "NAN"),
    ],
)
def test_converts_floats_like_php(value: float, expected: str) -> None:
    assert _php.float_to_string(value) == expected


def nested(depth: int, value: str = "1") -> bytes:
    return ("[" * depth + value + "]" * depth).encode()


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (b'{"a":1,"a":2}', {"a": 2}),
        (b'{"":1,"a\\u0000":2}', {"": 1, "a\0": 2}),
        (b"9223372036854775807", 9223372036854775807),
        (b"-9223372036854775808", -9223372036854775808),
        (b"9223372036854775808", 9223372036854775808.0),
        (b"-9223372036854775809", -9223372036854775809.0),
        (b"1" + b"0" * 5000, math.inf),
        (b"-0", 0),
        (b"1e400", math.inf),
        (b'"\\ud83d\\ude00"', chr(0x1F600)),
        (b' [ "x" ]\r\n', ["x"]),
        (nested(511), nested(511).decode()),
    ],
)
def test_decodes_what_json_decode_accepts(body: bytes, expected: object) -> None:
    if body == nested(511):
        decoded = _php.json_decode(body)
        for _ in range(511):
            assert isinstance(decoded, list)
            decoded = decoded[0]
        assert decoded == 1
        return

    decoded = _php.json_decode(body)

    assert decoded == expected
    assert isinstance(decoded, type(expected))


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b" ",
        b"NaN",
        b"[Infinity]",
        b"[-Infinity]",
        b"\xef\xbb\xbf{}",
        b"\xff",
        '"x"'.encode("utf-16"),
        b'{"\\u0000a":1}',
        b'[{"\\u0000":1}]',
        b'"\\ud800"',
        b'{"a":"\\udc00\\ud800"}',
        b'{"count":0,"results":[],"a":"\\ud800","a":"ok"}',
        b'{"a":' + nested(511) + b',"a":1}',
        nested(512),
        nested(5000),
        b"01",
        b"[1,]",
        b'"\x01"',
    ],
)
def test_rejects_what_json_decode_rejects(body: bytes) -> None:
    with pytest.raises((ValueError, RecursionError)):
        _php.json_decode(body)


@pytest.mark.parametrize(
    ("environ", "expected"),
    [
        ({}, "default"),
        ({"KEY": "true"}, True),
        ({"KEY": "(TRUE)"}, True),
        ({"KEY": "FALSE"}, False),
        ({"KEY": "(false)"}, False),
        ({"KEY": "empty"}, ""),
        ({"KEY": "(Empty)"}, ""),
        ({"KEY": "null"}, None),
        ({"KEY": "(NULL)"}, None),
        ({"KEY": "'quoted'"}, "quoted"),
        ({"KEY": '"quoted"'}, "quoted"),
        ({"KEY": "'mismatched\""}, "'mismatched\""),
        ({"KEY": "'multi\nline'"}, "'multi\nline'"),
        ({"KEY": ""}, ""),
        ({"KEY": " true "}, " true "),
    ],
)
def test_reads_environment_values_like_laravel_env(
    environ: dict[str, str], expected: object
) -> None:
    assert _php.env_value(environ, "KEY", "default") == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, True),
        (False, False),
        (None, False),
        (1, True),
        (0, False),
        (2, False),
        (1.0, True),
        (1.5, False),
        ("1", True),
        ("yes", True),
        ("On", True),
        (" TRUE ", True),
        ("\x0btrue\x0b", True),
        ("\ttrue\n\r", True),
        ("\x0ctrue\x0c", False),
        ("\0true", False),
        (f"{NBSP}true", False),
        ("maybe", False),
        ("", False),
        (["true"], False),
    ],
)
def test_filters_booleans_like_filter_var(value: object, expected: bool) -> None:
    assert _php.filter_bool(value) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("5", 5.0),
        (" 5 ", 5.0),
        ("\x0b2.5\x0c", 2.5),
        ("5.", 5.0),
        (".5", 0.5),
        ("+1e3", 1000.0),
        ("1e999", math.inf),
        (7, 7.0),
        (2.5, 2.5),
        (10**400, math.inf),
        ("1_0", None),
        ("inf", None),
        ("nan", None),
        ("0x1A", None),
        (f"{NBSP}2", None),
        ("\x002", None),
        ("", None),
        ("abc", None),
        (True, None),
        (None, None),
    ],
)
def test_reads_numbers_like_is_numeric(value: object, expected: float | None) -> None:
    assert _php.numeric_value(value) == expected
