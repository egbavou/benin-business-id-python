"""Checker behaviour that needs no HTTP client: it runs without the httpx extra."""

import asyncio
from datetime import UTC, datetime

import pytest

from benin_business_id import (
    ApiexSettings,
    AsyncIfuChecker,
    AsyncRccmChecker,
    CheckStatus,
    Ifu,
    IfuChecker,
    RccmChecker,
    UnavailableReason,
)


def test_returns_an_ifu_result_without_an_existence_source() -> None:
    checker = IfuChecker()
    invalid = checker.check("invalid")

    assert invalid.status is CheckStatus.INVALID_FORMAT
    assert invalid.input == "invalid"
    assert invalid.ifu is None
    assert invalid.unavailable_reason is None

    for value in (" 3202444139959 ", Ifu("3202444139959")):
        before = datetime.now(UTC)
        result = checker.check(value)

        assert result.status is CheckStatus.UNAVAILABLE
        assert result.unavailable_reason is UnavailableReason.NO_SOURCE
        assert result.ifu is not None
        assert result.ifu.value == "3202444139959"
        assert result.input == (value if isinstance(value, str) else value.value)
        assert result.checked_at.tzinfo is UTC
        assert before <= result.checked_at <= datetime.now(UTC)

    identifier = Ifu("3202444139959")
    assert checker.check(identifier).ifu is identifier


def test_the_async_ifu_checker_returns_the_same_results() -> None:
    result = asyncio.run(AsyncIfuChecker().check("3202444139959"))

    assert result.status is CheckStatus.UNAVAILABLE
    assert result.unavailable_reason is UnavailableReason.NO_SOURCE


@pytest.mark.parametrize("value", [3202444139959, None, b"3202444139959"])
def test_ifu_checks_reject_values_that_are_not_strings(value: object) -> None:
    with pytest.raises(TypeError):
        IfuChecker().check(value)  # type: ignore[arg-type]


def test_validates_before_checking_the_disabled_switch_without_a_client() -> None:
    checker = RccmChecker()
    invalid = checker.check("bad input")

    assert checker.enabled is False
    assert invalid.status is CheckStatus.INVALID_FORMAT
    assert invalid.rccm is None
    assert invalid.unavailable_reason is None
    assert invalid.failure is None
    assert invalid.input == "bad input"

    result = checker.check(" rb/cot/18-B-22272 ")

    assert result.status is CheckStatus.UNAVAILABLE
    assert result.unavailable_reason is UnavailableReason.DISABLED
    assert result.failure is None
    assert result.input == " rb/cot/18-B-22272 "
    assert result.rccm is not None
    assert result.rccm.value == "RB/COT/18 B 22272"
    assert result.checked_at.tzinfo is UTC


def test_the_async_rccm_checker_is_disabled_by_default() -> None:
    checker = AsyncRccmChecker()
    result = asyncio.run(checker.check("RB/COT/18 B 22272"))

    assert checker.enabled is False
    assert result.status is CheckStatus.UNAVAILABLE
    assert result.unavailable_reason is UnavailableReason.DISABLED
    asyncio.run(checker.aclose())


def test_a_disabled_checker_from_settings_needs_no_client() -> None:
    with RccmChecker.from_settings(ApiexSettings()) as checker:
        assert checker.enabled is False
        assert checker.check("RB/COT/18 B 22272").status is CheckStatus.UNAVAILABLE


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"enabled": "yes"}, TypeError),
        ({"companies_url": None}, TypeError),
        ({"establishments_url": 1}, TypeError),
        ({"timeout": 0}, ValueError),
        ({"timeout": -1.0}, ValueError),
        ({"timeout": float("nan")}, ValueError),
        ({"timeout": "10"}, TypeError),
        ({"timeout": True}, TypeError),
    ],
)
def test_rejects_invalid_configuration(kwargs: dict[str, object], error: type[Exception]) -> None:
    with pytest.raises(error):
        RccmChecker(**kwargs)  # type: ignore[arg-type]

    with pytest.raises(error):
        AsyncRccmChecker(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [123, None])
def test_rccm_checks_reject_values_that_are_not_strings(value: object) -> None:
    with pytest.raises(TypeError):
        RccmChecker().check(value)  # type: ignore[arg-type]
