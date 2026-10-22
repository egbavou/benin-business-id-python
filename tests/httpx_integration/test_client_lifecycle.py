"""Python-specific checker behaviour: client ownership, propagated exceptions, missing httpx."""

import asyncio
import math
import sys
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from tests.httpx_integration.support import FakeApiex, page

from benin_business_id import (
    ApiexSettings,
    AsyncRccmChecker,
    CheckStatus,
    RccmChecker,
    RccmCheckResult,
    UnavailableReason,
)


def test_an_injected_client_is_never_closed() -> None:
    fake = FakeApiex([page() for _ in range(4)])

    with fake.client() as client:
        with RccmChecker(client, enabled=True) as checker:
            checker.check("RB/COT/18 B 22272")

        assert not client.is_closed


def test_an_injected_async_client_is_never_closed() -> None:
    async def run() -> None:
        fake = FakeApiex([page() for _ in range(4)])

        async with fake.async_client() as client:
            async with AsyncRccmChecker(client, enabled=True) as checker:
                await checker.check("RB/COT/18 B 22272")

            assert not client.is_closed

    asyncio.run(run())


def test_creates_and_closes_its_own_client_with_the_default_timeout() -> None:
    checker = RccmChecker(enabled=True)
    client = checker._client
    assert isinstance(client, httpx.Client)
    assert client.timeout == httpx.Timeout(10.0)
    assert client.follow_redirects is False

    checker.close()

    assert client.is_closed


def test_creates_and_closes_its_own_async_client() -> None:
    async def run() -> None:
        checker = AsyncRccmChecker(enabled=True, timeout=3)
        client = checker._client
        assert isinstance(client, httpx.AsyncClient)
        assert client.timeout == httpx.Timeout(3.0)

        await checker.aclose()

        assert client.is_closed

    asyncio.run(run())


def test_an_infinite_timeout_means_no_timeout() -> None:
    with RccmChecker(enabled=True, timeout=math.inf) as checker:
        assert isinstance(checker._client, httpx.Client)
        assert checker._client.timeout == httpx.Timeout(None)


def test_rejects_a_timeout_with_an_injected_client() -> None:
    with httpx.Client() as client, pytest.raises(ValueError, match="timeout"):
        RccmChecker(client, enabled=True, timeout=5)


def test_builds_from_settings() -> None:
    settings = ApiexSettings(
        enabled=True,
        timeout=4.0,
        companies_url="https://example.test/companies",
        establishments_url="https://example.test/establishments",
    )

    with RccmChecker.from_settings(settings) as checker:
        assert checker.enabled is True
        assert isinstance(checker._client, httpx.Client)
        assert checker._client.timeout == httpx.Timeout(4.0)

    fake = FakeApiex([page([{"Numéro RC": "RB/COT/18 B 22272"}])])

    with fake.client(timeout=2.0) as client:
        result = RccmChecker.from_settings(settings, client).check("RB/COT/18 B 22272")

    assert result.status is CheckStatus.FOUND
    assert str(fake.requests[0].url).startswith("https://example.test/companies?")
    assert fake.requests[0].extensions["timeout"]["read"] == 2.0

    async def run() -> None:
        async with AsyncRccmChecker.from_settings(settings) as checker:
            assert checker.enabled is True

    asyncio.run(run())


def test_requires_httpx_only_when_enabled_without_a_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "httpx", None)

    assert RccmChecker().check("RB/COT/18 B 22272").status is CheckStatus.UNAVAILABLE

    for checker_class in (RccmChecker, AsyncRccmChecker):
        with pytest.raises(ImportError, match=r"benin-business-id\[httpx\]"):
            checker_class(enabled=True)


def test_lets_keyboard_interrupts_propagate() -> None:
    fake = FakeApiex([KeyboardInterrupt()])

    with fake.client() as client, pytest.raises(KeyboardInterrupt):
        RccmChecker(client, enabled=True).check("RB/COT/18 B 22272")


def test_lets_cancellation_propagate() -> None:
    async def run() -> None:
        fake = FakeApiex([asyncio.CancelledError()])

        async with fake.async_client() as client:
            await AsyncRccmChecker(client, enabled=True).check("RB/COT/18 B 22272")

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(run())


class BrokenStream(httpx.SyncByteStream, httpx.AsyncByteStream):
    """A body that breaks off after the headers have been received."""

    def __iter__(self) -> Iterator[bytes]:
        yield b'{"count":0,'
        raise httpx.ReadError("Connection reset while reading the body.")

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b'{"count":0,'
        raise httpx.ReadError("Connection reset while reading the body.")


def cut_off_check(mode: str) -> RccmCheckResult:
    def make() -> httpx.Response:
        return httpx.Response(200, stream=BrokenStream())

    if mode == "sync":
        with FakeApiex([make()]).client() as client:
            return RccmChecker(client, enabled=True).check("RB/COT/18 B 22272")

    async def run() -> RccmCheckResult:
        async with FakeApiex([make()]).async_client() as client:
            return await AsyncRccmChecker(client, enabled=True).check("RB/COT/18 B 22272")

    return asyncio.run(run())


@pytest.mark.parametrize("mode", ["sync", "async"])
def test_a_body_cut_off_by_the_network_is_a_transport_failure(mode: str) -> None:
    result = cut_off_check(mode)

    assert result.status is CheckStatus.UNAVAILABLE
    assert result.unavailable_reason is UnavailableReason.TRANSPORT
    assert isinstance(result.failure, httpx.ReadError)
