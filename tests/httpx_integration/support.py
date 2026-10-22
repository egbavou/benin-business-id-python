"""A fake APIEx directory on httpx.MockTransport, the counterpart of the PHP FakeHttpClient."""

import asyncio
import json
from collections.abc import Callable
from typing import Any, Protocol

import httpx

from benin_business_id import AsyncRccmChecker, RccmChecker, RccmCheckResult


class NoQueuedResponseError(Exception):
    pass


class FakeApiex:
    """Records requests and replies with queued responses, or raises queued exceptions."""

    def __init__(self, responses: list[httpx.Response | BaseException] | None = None) -> None:
        self.responses = list(responses or [])
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)

        if not self.responses:
            raise NoQueuedResponseError("No fake response was queued.")

        response = self.responses.pop(0)

        if isinstance(response, BaseException):
            raise response

        return response

    def client(self, **options: Any) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler), **options)

    def async_client(self, **options: Any) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler), **options)


def page(records: list[dict[str, object]] | None = None) -> httpx.Response:
    records = records or []

    return httpx.Response(
        200, content=json.dumps({"count": len(records), "results": records}).encode()
    )


def raw(status: int, body: bytes | str = b"") -> httpx.Response:
    return httpx.Response(status, content=body.encode() if isinstance(body, str) else body)


class Check(Protocol):
    def __call__(
        self,
        value: object,
        responses: list[httpx.Response | BaseException] | None = None,
        **options: Any,
    ) -> tuple[RccmCheckResult, FakeApiex]: ...


def make_check(mode: str) -> Check:
    """Run one check with a sync or async checker on a fake directory."""

    def check(
        value: object,
        responses: list[httpx.Response | BaseException] | None = None,
        **options: Any,
    ) -> tuple[RccmCheckResult, FakeApiex]:
        fake = FakeApiex(responses)
        client_options = options.pop("client_options", {})
        options.setdefault("enabled", True)

        if mode == "sync":
            with fake.client(**client_options) as client:
                result = RccmChecker(client, **options).check(value)  # type: ignore[arg-type]
        else:

            async def run() -> RccmCheckResult:
                async with fake.async_client(**client_options) as client:
                    return await AsyncRccmChecker(client, **options).check(value)  # type: ignore[arg-type]

            result = asyncio.run(run())

        return result, fake

    return check


MODES = ["sync", "async"]
Factory = Callable[[str], Check]


_REAL_CLIENT = httpx.Client
_REAL_ASYNC_CLIENT = httpx.AsyncClient


def route_owned_clients(monkeypatch: Any, fake: FakeApiex) -> None:
    """Make the clients that checkers create themselves talk to the fake directory."""

    def client(**options: Any) -> httpx.Client:
        return _REAL_CLIENT(transport=httpx.MockTransport(fake.handler), **options)

    def async_client(**options: Any) -> httpx.AsyncClient:
        return _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(fake.handler), **options)

    monkeypatch.setattr(httpx, "Client", client)
    monkeypatch.setattr(httpx, "AsyncClient", async_client)
