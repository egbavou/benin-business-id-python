"""Checks against the real APIEx directory. Port of the PHP tests/Live/ApiexTest.php.

Excluded by default and from CI. Run them with:

    BENIN_BUSINESS_ID_LIVE=1 uv run pytest -m live
"""

import asyncio
import os

import pytest

from benin_business_id import (
    AsyncRccmChecker,
    CheckStatus,
    RccmChecker,
    RccmCheckResult,
    RccmRegister,
)

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("BENIN_BUSINESS_ID_LIVE") != "1",
        reason="Set BENIN_BUSINESS_ID_LIVE=1 to allow live APIEx requests.",
    ),
]

MODES = ["sync", "async"]


def live_check(mode: str, number: str) -> RccmCheckResult:
    if mode == "sync":
        with RccmChecker(enabled=True, timeout=10) as checker:
            return checker.check(number)

    async def run() -> RccmCheckResult:
        async with AsyncRccmChecker(enabled=True, timeout=10) as checker:
            return await checker.check(number)

    return asyncio.run(run())


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("number", ["RB/COT/18 B 22272", "RB/COT/07 B 2058"])
def test_finds_a_public_company_in_the_live_apiex_directory(mode: str, number: str) -> None:
    result = live_check(mode, number)

    assert result.status is CheckStatus.FOUND, result.failure
    assert result.unavailable_reason is None

    if number == "RB/COT/18 B 22272":
        assert result.register is RccmRegister.COMPANIES
        assert result.name is not None
        assert result.creation_date is not None


@pytest.mark.parametrize("mode", MODES)
def test_returns_not_found_for_an_absent_well_formed_number(mode: str) -> None:
    result = live_check(mode, "RB/COT/05 B 0041")

    assert result.status is CheckStatus.NOT_FOUND, result.failure
    assert result.unavailable_reason is None
